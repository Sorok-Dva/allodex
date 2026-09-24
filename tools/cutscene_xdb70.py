"""Déroulé serveur d'une cinématique moteur, relu dans l'arbre serveur 7.0 (`.xdb`).

Le client ne sait pas quand ni par qui une réplique est dite : c'est le serveur qui enchaîne les
buffs de la cinématique. L'arbre serveur 7.0 garde ces buffs (`BuffResource`) avec toute leur
mécanique, ce qui donne, pour les scènes de 7.0 et d'avant, le **déroulé exact** :

* `duration` du buff, et `EffectOnBuffTimeout` → `BuffAttacher` / `BuffDetacher` : l'enchaînement ;
* `EffectsDeferred` (`delay` en ms) → effets différés ; `Switch` → `impactsOn` (à la pose) ;
* `ImpactsToSingleSpawn` (`scriptID`) → `ImpactClientDataParams` : **le PNJ qui dit la réplique**
  (`ClientData` : sous-titre, voix, animation) ; `BuffAttacher` sur un PNJ : son script visuel ;
* `visScript` du buff (sur le joueur) : `CameraTrackAction` (plan de caméra), `PostEffectVisAction`
  (fondu : `UserPostEffect` `fadeInTimeMSec`/`fadeOutTimeMSec`), `WeatherCreatureVisAction` (ciel,
  lumière, brouillard, désaturation), `Sound2DAction` (ambiance, musique) ;
* placement des PNJ : `Maps/<carte>/<bloc>/<i>_<j>_*ServerObjects.xdb` (`SingleSpawnResource` :
  `scriptID`, `center` local à la région, `yaw`, `MobWorld`) ;
* PNJ invoqués pour la scène (`ImpactSummon` : `MobWorld`, `DestinationLocator` → `scriptID` d'un
  repère des mêmes `ServerObjects`, `yaw` en degrés) ; leurs `impacts` les visent (buffs, répliques),
  `ImpactGoTo` les fait marcher jusqu'à un autre repère, `Disintegrate` les retire ;
  `ImpactClientData` (réplique posée sur le joueur) et `ImpactsDeferred` (`delay` en ms).

Le module ne rend que des chemins `.xdb` et des valeurs ; `tools/extract_engine_cutscene.py` les
rapporte aux ressources du client 17.0 (voix, textes, modèles) et vérifie les plans de caméra.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

REGION_SIZE = 256.0


def _read(path: Path) -> ET.Element | None:
    try:
        return ET.fromstring(path.read_bytes())
    except (OSError, ET.ParseError):
        return None


def _text(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    for enc in ("utf-16", "utf-8", "cp1251"):
        try:
            return raw.decode(enc).lstrip("﻿")
        except UnicodeDecodeError:
            continue
    return ""


def clean(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return "\n".join(ln.strip() for ln in text.replace("\r", "").split("\n") if ln.strip())


def _f(node: ET.Element | None, tag: str, default: float = 0.0) -> float:
    v = node.findtext(tag) if node is not None else None
    try:
        return float(v) if v not in (None, "") else default
    except ValueError:
        return default


@dataclass
class Tree:
    """Arbre serveur : résolution des `href` (absolus depuis la racine, ou relatifs au fichier)."""

    root: Path

    def resolve(self, base: Path, href: str) -> Path:
        href = href.split("#", 1)[0]
        return self.root / href.lstrip("/") if href.startswith("/") else base.parent / href

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()


@dataclass
class Timeline:
    duration: float = 0.0
    shots: list[dict] = field(default_factory=list)
    lines: list[dict] = field(default_factory=list)
    effects: list[dict] = field(default_factory=list)
    weather: list[dict] = field(default_factory=list)
    sounds: list[dict] = field(default_factory=list)
    post: list[dict] = field(default_factory=list)
    buffs: list[dict] = field(default_factory=list)
    scripts: set[str] = field(default_factory=set)
    maps: set[str] = field(default_factory=set)
    # PNJ invoqués : {id, mob, name, locator, yaw (rad), t, until, moves: [{t, locator}]}
    summons: list[dict] = field(default_factory=list)
    # Déroulé ouvert par un déclencheur (`trigger`, zone de script ou effet d'une capacité) :
    # états visuels posés sur les stèles (`ImpactSetVisualState`), effets de `ClientData` posés sur
    # des repères (projectile, explosion, rayon), sons ponctuels, trajets et retrait des PNJ posés,
    # sortie du joueur de la carte (`ImpactTeleport`).
    states: list[dict] = field(default_factory=list)
    fx: list[dict] = field(default_factory=list)
    sfx: list[dict] = field(default_factory=list)
    spawn_moves: dict[str, list[dict]] = field(default_factory=dict)
    spawn_until: dict[str, float] = field(default_factory=dict)
    exit: float | None = None
    # PNJ posés tués par le déroulé (`ImpactKill`) : scriptID → t ; messages de PNJ (`ImpactMobChat`
    # → `TextMessage`) : {t, speaker, ru, message}.
    kills: dict[str, float] = field(default_factory=dict)
    chats: list[dict] = field(default_factory=list)
    # Déroulé d'un déclencheur, suite : secousses de caméra (`ShakeAction` d'un `ClientData` :
    # {t, source, params}), téléportations du joueur sur la carte même ({t, locator, yaw}), drapeaux
    # visuels posés sur le joueur (`CreatureSetFlagVisAction` : {t, until, flag}) que lisent les stèles.
    shakes: list[dict] = field(default_factory=list)
    teleports: list[dict] = field(default_factory=list)
    flags: list[dict] = field(default_factory=list)
    # Tables d'apparition posées par le déroulé (`SpawnTableObjects`, retirées par `ResetSpawnTable`).
    tables: list[dict] = field(default_factory=list)


def read_client_data(tree: Tree, path: Path) -> dict:
    """Réplique d'un `ClientData` 7.0 : texte russe, durée, voix, animations ; bulle au-dessus du
    PNJ (`InterfaceAction` `ENUM_SHOW_BUBBLE` : `bubble`, texte russe)."""
    doc = _read(path)
    out = {"clientdata": tree.rel(path), "ru": "", "delay_ms": 0, "voice": None, "animations": []}
    if doc is None:
        return out
    for data in doc.iter():
        # `customData` seul, ou élément d'une `CustomClientDataList` (bulle + message + animation)
        if data.tag not in ("customData", "Item"):
            continue
        if (data.get("type") or "").endswith("InterfaceAction") and data.findtext("sysId") == "ENUM_SHOW_BUBBLE":
            href = data.find("text")
            if href is not None and href.get("href"):
                out["bubble"] = clean(_text(tree.resolve(path, href.get("href"))))
    for item in doc.iter("subtitles"):
        for sub in item:
            href = sub.find("text")
            if href is not None and href.get("href"):
                out["ru"] = clean(_text(tree.resolve(path, href.get("href"))))
            out["delay_ms"] = int(_f(sub, "delayMs"))
            break
    for sound in doc.iter("sound"):
        name = sound.findtext("name")
        if name:
            out["voice"] = name
            break
    for anims in doc.iter("animations"):
        out["animations"] += [a.text for a in anims if a.text]
    action = doc.find("customData/action")
    kind = (action.get("type") or "").rsplit(".", 1)[-1] if action is not None else ""
    out["kind"] = kind
    if kind == "CreatureFixedPointProjectileAction":
        # Projectile d'un repère à l'autre (`lines` : `endPointIndex`, `throwDuration` ms), explosion
        # à l'arrivée : un effet posé, sans PNJ.
        def ref(tag: str) -> str | None:
            node = action.find(tag)
            return tree.rel(tree.resolve(path, node.get("href"))) if node is not None and node.get("href") else None
        line = action.find("lines/Item")
        out["projectile"] = {"projectile": ref("projectileFx"), "explosion": ref("explosionFx"),
                             "theGe": _f(action, "theGe"), "throw": _f(line, "throwDuration") / 1000.0,
                             "end": int(_f(line, "endPointIndex"))}
        out["voice"] = None
    elif kind == "CreatureChannelDirectAction":
        # Rayon canalisé : gabarit (`channelingFx`), départ (locator de la créature), nom de l'action
        # (`visActionID`, qu'un `VisActionStopAction` arrête).
        fx, start = action.find("channelingFx"), action.find("startPoint")
        out["channel"] = {"fx": tree.rel(tree.resolve(path, fx.get("href"))) if fx is not None and fx.get("href") else None,
                          "locator": start.findtext("locator") if start is not None else None,
                          "id": action.findtext("visActionID")}
    elif kind == "VisActionStopAction":
        out["stop"] = action.findtext("stoppedActionID")
    elif kind == "ShakeAction":
        # Secousse de caméra : `CameraShakeParameters` (rayons, échelles) et sa courbe
        # `AnimatedParameters.cameraTranslate` (décalages x, y, z à `fps` images par seconde).
        out["shake"] = read_shake(tree, path, action)
        out["voice"] = None
    elif kind in ("Sound2DAction", "Sound3DAction"):
        project = action.find("sound/project")
        href = project.get("href", "") if project is not None else ""
        if out["voice"] and "VoiceDialogs" not in href and not out["ru"]:
            # Son d'effet (projet `World`, `Ambience`…) : pas une réplique.
            out["sound"] = {"name": out["voice"], "kind": kind, "type": action.findtext("actionType") or "Simple"}
    return out


def read_shake(tree: Tree, base: Path, action: ET.Element) -> dict | None:
    """`ShakeAction` → `CameraShakeParameters` (`minRadius`/`maxRadius` m, `amplitudeScale`,
    `timeScale`) et courbe `cameraTranslate` de son `AnimatedParameters` (`fps`)."""
    href = action.find("params")
    if href is None or not href.get("href"):
        return None
    ppath = tree.resolve(base, href.get("href"))
    params = _read(ppath)
    anim = params.find("animation") if params is not None else None
    adoc = _read(tree.resolve(ppath, anim.get("href"))) if anim is not None and anim.get("href") else None
    if adoc is None:
        return None
    keys = [[round(float(i.get(k, 0)), 6) for k in "xyz"] for i in adoc.findall("cameraTranslate/Item")]
    return {"params": tree.rel(ppath), "minRadius": _f(params, "minRadius"), "maxRadius": _f(params, "maxRadius"),
            "amplitude": _f(params, "amplitudeScale", 1.0), "timeScale": _f(params, "timeScale", 1.0),
            "fps": _f(adoc, "fps", 30.0), "keys": keys}


def read_camera(action: ET.Element) -> dict:
    def pts(tag: str):
        return [(_f(p, "duration"), tuple(float(p.find("position").get(k, 0)) for k in "xyz"))
                for p in action.findall(f"{tag}/Item") if p.find("position") is not None]
    return {"points": pts("cameraPoints"), "targets": pts("targetPoints")}


class Simulator:
    """Déroule une chaîne de buffs à partir de son premier buff."""

    def __init__(self, tree: Tree, horizon: float = 600.0, extended: bool = False, home: str | None = None) -> None:
        self.tree = tree
        self.tl = Timeline()
        self.horizon = horizon
        self.open: dict[str, dict] = {}     # buff sans durée → entrée, fermée par un BuffDetacher
        # Déroulé d'un déclencheur (zone de script, capacité) : branches `ImpactIfTarget`, impacts
        # instanciés ou sur les avatars voisins, états des stèles, effets et sons des `ClientData`,
        # PNJ posés qui marchent ou disparaissent. Les chaînes de buffs gardent leur lecture.
        self.extended = extended
        # Carte de la scène : une téléportation du joueur vers un repère de cette carte le déplace
        # (vue du joueur), elle ne le sort pas de la scène.
        self.home = home

    def attach(self, path: Path, t: float, target: str = "player") -> None:
        if t > self.horizon or len(self.tl.buffs) > 400:
            return
        doc = _read(path)
        if doc is None:
            return
        duration = _f(doc, "duration") / 1000.0
        entry = {"buff": self.tree.rel(path), "t": round(t, 3), "duration": duration or None, "target": target}
        self.tl.buffs.append(entry)
        if not duration:
            self.open[entry["buff"]] = entry
        vis = doc.find("visScript")
        if vis is not None and vis.get("href"):
            self.vis(self.tree.resolve(path, vis.get("href")), t, duration, target, entry)
            if self.extended and target not in ("player", "interlocutor") and not target.startswith(("summon", "table:")):
                # PNJ posé sur qui le déroulé pose un buff visible (chute, émote) : il est en scène.
                self.tl.scripts.add(target)
        for effect in doc.findall("effects/Item"):
            self.effect(path, effect, t, duration, target)
        end = t + duration if duration else None
        if end:
            self.tl.duration = max(self.tl.duration, end)

    def effect(self, base: Path, node: ET.Element, t: float, duration: float, target: str) -> None:
        kind = (node.get("type") or "").rsplit(".", 1)[-1]
        if kind == "EffectOnBuffTimeout" and duration:
            for impact in node.findall("impacts/Item"):
                self.impact(base, impact, t + duration, target)
        elif kind == "EffectsDeferred":
            delay = _f(node, "delay") / 1000.0
            for sub in node.findall("effects/Item"):
                self.effect(base, sub, t + delay, 0.0, target)
        elif kind == "Switch":
            for impact in node.findall("impactsOn/Item"):
                self.impact(base, impact, t, target)
            if self.extended and duration:
                # `impactsOff` : au retrait du buff, à la fin de sa durée (chute puis relevé des paladins).
                for impact in node.findall("impactsOff/Item"):
                    self.impact(base, impact, t + duration, target)
        elif kind == "EffectInstantiating":
            for sub in node.findall("effects/Item"):
                self.effect(base, sub, t, duration, target)
        elif kind in ("EffectOnBuffApply", "EffectInstant"):
            for impact in node.findall("impacts/Item"):
                self.impact(base, impact, t, target)

    def impact(self, base: Path, node: ET.Element, t: float, target: str) -> None:
        kind = (node.get("type") or "").rsplit(".", 1)[-1]
        if kind == "BuffAttacher":
            href = node.find("buff")
            if href is not None and href.get("href"):
                self.attach(self.tree.resolve(base, href.get("href")), t, target)
            if self.extended:
                # `impactsOnAttach` : joués à la pose du buff, sur la même cible.
                for sub in node.findall("impactsOnAttach/Item"):
                    self.impact(base, sub, t, target)
        elif kind == "BuffDetacher":
            href = node.find("buff")
            if href is not None and href.get("href"):
                key = self.tree.rel(self.tree.resolve(base, href.get("href")))
                entry = self.open.pop(key, None)
                if entry is not None:
                    entry["until"] = round(t, 3)
                    for bucket in (self.tl.weather, self.tl.sounds, self.tl.effects):
                        for item in bucket:
                            if item.get("buff") == key and item.get("until") is None:
                                item["until"] = round(t, 3)
        elif kind == "ImpactsToSingleSpawn":
            spawn = node.find("spawn")
            script = spawn.findtext("scriptID") if spawn is not None else None
            mp = spawn.find("map") if spawn is not None else None
            if mp is not None and mp.get("href"):
                m = re.search(r"/Maps/([^/]+)/", mp.get("href"))
                if m:
                    self.tl.maps.add(m.group(1))
            for sub in node.findall("impacts/Item"):
                self.impact(base, sub, t, script or target)
        elif kind in ("ImpactsDeferred", "DeviceImpactsDeferred"):
            delay = _f(node, "delay") / 1000.0
            for sub in node.findall("impacts/Item"):
                self.impact(base, sub, t + delay, target)
        elif self.extended and kind == "ImpactsToInterlocutor":
            # PNJ à qui parle le joueur (le donneur de la quête) : « interlocutor », que le manifeste
            # rattache à un PNJ.
            for sub in node.findall("impacts/Item"):
                self.impact(base, sub, t, "interlocutor")
        elif self.extended and kind == "ImpactKill" and target != "player":
            self.tl.kills.setdefault(target, round(t, 3))
            self.tl.scripts.add(target)
        elif self.extended and kind == "ImpactMobChat":
            msg = node.find("msg")
            doc = _read(self.tree.resolve(base, msg.get("href"))) if msg is not None and msg.get("href") else None
            href = next((e.get("href") for e in doc.iter() if e.tag.lower() == "text" and e.get("href")), None) \
                if doc is not None else None
            if href:
                path = self.tree.resolve(base, msg.get("href"))
                self.tl.chats.append({"t": round(t, 3), "speaker": target, "message": self.tree.rel(path),
                                      "ru": clean(_text(self.tree.resolve(path, href)))})
        elif self.extended and kind in ("SpawnTableObjects", "ResetSpawnTable"):
            # Table d'apparition posée (stèle d'effet : mur magique) puis retirée.
            href = node.find("table")
            if href is not None and href.get("href"):
                rel = self.tree.rel(self.tree.resolve(base, href.get("href")))
                if kind == "SpawnTableObjects":
                    self.tl.tables.append({"t": round(t, 3), "table": rel, "until": None})
                    self.tl.scripts.add("table:" + rel)
                else:
                    for item in self.tl.tables:
                        if item["table"] == rel and item["until"] is None and item["t"] <= t:
                            item["until"] = round(t, 3)
        elif kind == "ImpactSummon":
            self.summon(base, node, t)
        elif kind == "ImpactFindSpawnTable":
            table = self.spawn_table(base, node)
            for sub in node.findall("impacts/Item"):
                self.impact(base, sub, t, table or target)
        elif kind == "GoThroughPath":
            summon = self.summon_by_id(target)
            for step in node.findall("path/Item"):
                locator = step.findtext("scriptID")
                mp = step.find("map")
                if mp is not None and mp.get("href"):
                    m = re.search(r"/Maps/([^/]+)/", mp.get("href"))
                    if m:
                        self.tl.maps.add(m.group(1))
                if summon is not None and locator:
                    summon["moves"].append({"t": round(t, 3), "locator": locator})
                    self.tl.scripts.add(locator)
                elif self.extended and locator and target != "player":
                    # PNJ posé sur la carte (`ImpactsToSingleSpawn`) qui suit un chemin (`runningMode` : en courant).
                    run = (node.findtext("runningMode") or "").strip() == "true"
                    self.tl.spawn_moves.setdefault(target, []).append({"t": round(t, 3), "locator": locator,
                                                                       **({"run": True} if run else {})})
                    self.tl.scripts.update({target, locator})
        elif kind == "ImpactGoTo":
            summon = self.summon_by_id(target)
            locator = self.locator(node.find("destination"))
            if summon is not None and locator:
                summon["moves"].append({"t": round(t, 3), "locator": locator})
                self.tl.scripts.add(locator)
            elif self.extended and locator and target != "player":
                self.tl.spawn_moves.setdefault(target, []).append({"t": round(t, 3), "locator": locator})
                self.tl.scripts.update({target, locator})
        elif kind == "Disintegrate":
            summon = self.summon_by_id(target)
            if summon is not None and summon.get("until") is None:
                summon["until"] = round(t, 3)
            elif summon is None and self.extended and target != "player":
                self.tl.spawn_until[target] = min(self.tl.spawn_until.get(target, t), round(t, 3))
        elif self.extended and kind == "ImpactIfTarget":
            # Branche prise par la scène : celle où les conditions tiennent (joueur hors combat,
            # cible avatar…) ; `impactsElse` est le cas hors cinématique.
            for sub in node.findall("impactsIf/Item"):
                self.impact(base, sub, t, target)
        elif self.extended and kind in ("ImpactInstantiating", "ImpactInstantiatingWithAddressee"):
            for sub in node.findall("impacts/Item"):
                self.impact(base, sub, t, target)
        elif self.extended and kind == "ImpactCreaturesAround":
            flt = node.find("filter")
            if flt is not None and (flt.get("type") or "").endswith("AvatarFilter"):   # avatars voisins : le joueur
                for sub in node.findall("impacts/Item"):
                    self.impact(base, sub, t, "player")
        elif self.extended and kind == "ImpactTeleport" and target == "player":
            dest = node.find("destination")
            loc = dest.find("locator") if dest is not None else None
            mp = loc.find("map") if loc is not None else None
            m = re.search(r"/Maps/([^/]+)/", mp.get("href", "")) if mp is not None else None
            if self.home is not None and loc is not None and (m is None or m.group(1) == self.home):
                # Repère de la carte même : le joueur y est déplacé (sa vue avec lui), la scène continue.
                yaw = dest.find("yaw")
                self.tl.teleports.append({"t": round(t, 3), "locator": loc.findtext("scriptID"),
                                          "yaw": _f(yaw, "value") if yaw is not None else None})
                self.tl.scripts.add(loc.findtext("scriptID") or "")
            else:
                self.tl.exit = t if self.tl.exit is None else min(self.tl.exit, t)
        elif self.extended and kind == "ImpactSetVisualState" and target != "player":
            self.tl.states.append({"t": round(t, 3), "spawn": target, "state": int(_f(node, "visualState"))})
            self.tl.scripts.add(target)
        elif kind in ("ImpactClientDataParams", "ImpactClientData"):
            data = node.find("data")
            if data is not None and data.get("href"):
                path = self.tree.resolve(base, data.get("href"))
                line = read_client_data(self.tree, path)
                locators = [x.text for x in node.findall("locators/Item/scriptID") if x.text]
                if self.extended and line.get("projectile"):
                    self.tl.fx.append({"t": round(t, 3), "clientdata": line["clientdata"], "locators": locators,
                                       "owner": target, **line["projectile"]})
                    self.tl.scripts.update(locators)
                    return
                if self.extended and line.get("kind") == "ShakeAction":
                    if line.get("shake"):
                        self.tl.shakes.append({"t": round(t, 3), "source": target, "clientdata": line["clientdata"],
                                               **line["shake"]})
                    return
                if self.extended and line.get("sound"):
                    self.tl.sfx.append({"t": round(t, 3), "clientdata": line["clientdata"], **line["sound"]})
                    return
                if self.extended and line.get("stop"):
                    # `VisActionStopAction` : arrête le rayon (ou l'action) nommé, lancé plus tôt.
                    for item in self.tl.fx:
                        if item.get("channel") and item["channel"].get("id") == line["stop"] and item.get("until") is None:
                            item["until"] = round(t, 3)
                    return
                if self.extended and line.get("kind") == "CreatureChannelDirectAction":
                    # Rayon canalisé d'un PNJ vers un repère : le PNJ est en scène.
                    self.tl.fx.append({"t": round(t, 3), "clientdata": line["clientdata"], "locators": locators,
                                       "owner": target, "channel": line.get("channel") or {}, "until": None})
                    if target != "player":
                        self.tl.scripts.add(target)
                    return
                if line["ru"] or line["voice"] or line["animations"] or line.get("bubble"):
                    line.update({"t": round(t, 3), "speaker": target})
                    self.tl.lines.append(line)
                    if target not in ("player", "interlocutor") and not target.startswith("summon"):
                        self.tl.scripts.add(target)

    def locator(self, dest: ET.Element | None) -> str | None:
        if dest is None:
            return None
        loc = dest.find("locator")
        mp = loc.find("map") if loc is not None else None
        if mp is not None and mp.get("href"):
            m = re.search(r"/Maps/([^/]+)/", mp.get("href"))
            if m:
                self.tl.maps.add(m.group(1))
        return loc.findtext("scriptID") if loc is not None else None

    def summon_by_id(self, target: str) -> dict | None:
        return next((s for s in self.tl.summons if s["id"] == target), None)

    def spawn_table(self, base: Path, node: ET.Element) -> str | None:
        """PNJ d'une table d'apparition posée sur la carte (`SpawnLocus`) : un acteur présent dès le
        début, à la place de la table ; les impacts qui suivent le visent."""
        ref = node.find("spawnResource")
        if ref is None or not ref.get("href"):
            return None
        table = self.tree.resolve(base, ref.get("href"))
        ident = "table:" + self.tree.rel(table) if table.is_file() else None
        if ident is None:
            return None
        if self.summon_by_id(ident) is None:
            doc = _read(table)
            obj = doc.find("singles/Item/object") if doc is not None else None
            mob = self.tree.resolve(table, obj.get("href")) if obj is not None and obj.get("href") else None
            if mob is None or not mob.is_file():
                return None
            self.tl.summons.append({"id": ident, "mob": self.tree.rel(mob), "name": mob_name(self.tree, mob),
                                    "visual": mob_visual(self.tree, mob), "locator": ident, "walkSpeed": walk_speed(mob),
                                    "yaw": None, "t": 0.0, "until": None, "moves": []})
            self.tl.scripts.add(ident)
        return ident

    def summon(self, base: Path, node: ET.Element, t: float) -> None:
        dest = node.find("destination")
        locator = self.locator(dest)
        obj = node.find("object")
        if not locator or obj is None or not obj.get("href"):
            return
        mob = self.tree.resolve(base, obj.get("href"))
        if not mob.name.endswith(".(MobWorld).xdb"):
            return          # projectile ou stèle d'effet (`CutScene_Boom.(SteleResource)`) : pas un PNJ
        yaw = dest.find("yaw") if dest is not None else None
        entry = {"id": f"summon{len(self.tl.summons) + 1}", "mob": self.tree.rel(mob) if mob.is_file() else obj.get("href"),
                 "name": mob_name(self.tree, mob), "visual": mob_visual(self.tree, mob) if mob.is_file() else None,
                 "locator": locator, "walkSpeed": walk_speed(mob),
                 "yaw": math.radians(_f(yaw, "value")) if yaw is not None else None,
                 "t": round(t, 3), "until": None, "moves": []}
        self.tl.summons.append(entry)
        self.tl.scripts.add(locator)
        for sub in node.findall("impacts/Item"):
            self.impact(base, sub, t, entry["id"])

    def timed_actions(self, doc: ET.Element, t: float, duration: float) -> list[tuple[ET.Element, float, float | None]]:
        """Actions d'un `BuffVisScripts` et leur fenêtre, pour un déroulé de déclencheur : une
        `VisActionList` se lit dans l'ordre, `VisActionDelay` avance le temps (ms),
        `VisActionStopAction` arrête l'action nommée (`visActionID`) ; `postAction` se joue au retrait
        du buff (fin de sa durée)."""
        until = t + duration if duration else None
        out: list[list] = []

        def walk(node: ET.Element, at: float) -> float:
            kind = (node.get("type") or "").rsplit(".", 1)[-1]
            if kind == "VisActionList":
                for item in node.findall("elements/Item"):
                    at = walk(item, at)
                return at
            if kind == "VisActionDelay":
                return at + _f(node, "time") / 1000.0
            if kind == "VisActionStopAction":
                name = node.findtext("stoppedActionID")
                for entry in out:
                    if name and entry[0].findtext("visActionID") == name and (entry[2] is None or entry[2] > at):
                        entry[2] = at
                return at
            out.append([node, at, until])
            # conteneur d'une autre sorte : ses actions typées jouent au même instant
            out.extend([sub, at, until] for sub in node.iter() if sub is not node and sub.get("type"))
            return at
        action = doc.find("action")
        if action is not None:
            walk(action, t)
        post = doc.find("postAction")
        if post is not None and until is not None:
            out.append([post, until, None])
        return [(n, a, b) for n, a, b in out]

    def vis(self, path: Path, t: float, duration: float, target: str, buff: dict) -> None:
        doc = _read(path)
        if doc is None:
            return
        if self.extended:
            for action, start, until in self.timed_actions(doc, t, duration):
                self.vis_action(path, action, start, until, target, buff)
            return
        for action in doc.iter():
            self.vis_action(path, action, t, t + duration if duration else None, target, buff, duration)

    def vis_action(self, path: Path, action: ET.Element, t: float, until: float | None, target: str, buff: dict,
                   duration: float | None = None) -> None:
        """Une action d'un script visuel de buff, jouée de `t` à `until` (fin du buff, ou arrêt)."""
        kind = (action.get("type") or "").rsplit(".", 1)[-1]
        if duration is None:
            duration = (until - t) if until is not None else 0.0
        if self.extended and kind == "Sound3DAction" and target == "player":
            kind = "Sound2DAction"      # son du joueur (`onlyForMainAvatar`) : entendu comme un son 2D
        if self.extended and kind == "CreatureSetFlagVisAction" and target == "player":
            flag = action.find("visualFlag")
            if flag is not None and flag.get("href"):
                self.tl.flags.append({"t": round(t, 3), "until": round(until, 3) if until is not None else None,
                                      "flag": self.tree.rel(self.tree.resolve(path, flag.get("href")))})
            return
        if kind == "CameraTrackAction":
            self.tl.shots.append({"t": round(t, 3), "duration": duration, "buff": buff["buff"], **read_camera(action)})
        elif kind == "PostEffectVisAction":
            eff = action.find("userPostEffect")
            if eff is not None and eff.get("href"):
                pe = _read(self.tree.resolve(path, eff.get("href")))
                tex = pe.find("textureMultiply") if pe is not None else None
                self.tl.post.append({"t": round(t, 3), "until": until, "buff": buff["buff"],
                                     "fadeIn": _f(pe, "fadeInTimeMSec") / 1000.0,
                                     "fadeOut": _f(pe, "fadeOutTimeMSec") / 1000.0,
                                     "black": bool(tex is not None and "Black" in (tex.get("href") or ""))})
        elif kind == "WeatherCreatureVisAction":
            params = action.find("params")
            light = params.find("light") if params is not None else None
            sky = params.find("skyMesh") if params is not None else None
            self.tl.weather.append({
                "t": round(t, 3), "until": until, "buff": buff["buff"],
                "sky": self.tree.rel(self.tree.resolve(path, sky.get("href"))) if sky is not None and sky.get("href") else None,
                "fadeTime": _f(params, "fadeTime"),
                "light": {c.tag: (c.text or c.get("href")) for c in light} if light is not None else {}})
        elif kind == "Sound2DAction" and target == "player":
            sound = action.find("sound")
            name = sound.findtext("name") if sound is not None else None
            if name:
                project = sound.find("project")
                music = self.extended and "/Music/" in (project.get("href", "") if project is not None else "")
                self.tl.sounds.append({"t": round(t, 3), "until": until, "buff": buff["buff"], "name": name,
                                       "kind": "Music" if music else action.findtext("actionType") or "Sound"})
        elif kind in ("CreatureIndependentFxAction", "CreatureEffectsAction", "CreatureAnimationAction") and target != "player":
            entry = {"t": round(t, 3), "until": until, "buff": buff["buff"], "target": target, "kind": kind}
            if kind == "CreatureAnimationAction":
                entry["animations"] = [a.text for a in action.findall("animations/Item") if a.text]
                entry["mode"] = action.findtext("mode") or "DIE"
            else:
                hrefs = [e.get("href") for e in action.iter() if e.tag in ("visObject", "fx") and e.get("href")]
                entry["visObjects"] = [self.tree.rel(self.tree.resolve(path, h)) for h in hrefs]
            self.tl.effects.append(entry)


def trigger_impacts(doc: ET.Element, effect: str | None = None, tag: str | None = None) -> list[ET.Element]:
    """Impacts d'un déclencheur : `impactsIn` d'une zone de script (`ScriptZone`, à l'entrée du
    joueur), ou `impactsOn` de l'effet `effect` (`HealthTrigger`…) d'une capacité (`AbilityResource`) ;
    ou la liste nommée `tag` (`startImpacts` d'une quête, `impactsOut` d'une zone)."""
    if tag:
        return doc.findall(f"{tag}/Item")
    if doc.find("impactsIn") is not None:
        return doc.findall("impactsIn/Item")
    out: list[ET.Element] = []
    for item in doc.findall("effects/Item"):
        if effect is None or (item.get("type") or "").rsplit(".", 1)[-1] == effect:
            out += item.findall("impactsOn/Item")
    return out


def simulate(root: Path, first_buff: str | None = None, horizon: float = 600.0, trigger: str | None = None,
             trigger_effect: str | None = None, owner: str = "player", trigger_tag: str | None = None,
             until_last: bool = False, home: str | None = None) -> Timeline:
    """Déroulé depuis un premier buff (`first_buff`, posé sur le joueur) ou depuis un déclencheur
    (`trigger` : zone de script ou capacité ; `owner` : `scriptID` du porteur de la capacité, cible
    de ses impacts directs ; `trigger_tag` : liste d'impacts nommée). `until_last` : scène sans buff
    qui la borne (quête, zone du tutoriel), jusqu'au dernier événement du déroulé — l'extraction la
    prolonge de ce qu'il montre (voix, scènes du client, marches)."""
    tree = Tree(Path(root))
    sim = Simulator(tree, horizon, extended=trigger is not None, home=home)
    if trigger is not None:
        path = tree.root / trigger
        doc = _read(path)
        for impact in trigger_impacts(doc, trigger_effect, trigger_tag) if doc is not None else []:
            sim.impact(path, impact, 0.0, owner)
        if owner != "player":
            sim.tl.scripts.add(owner)
        if until_last:
            # Rien ne borne la scène ici : tout est gardé jusqu'à l'horizon ; l'extraction la coupe à la
            # fin de ce qu'elle montre.
            sim.tl.duration = horizon
    root_doc = None
    if first_buff is not None:
        sim.attach(tree.root / first_buff, 0.0)
        root_doc = _read(tree.root / first_buff)
    if root_doc is not None and _f(root_doc, "duration") and root_doc.find(".//impactsOff") is not None:
        # Buff racine à durée dont le `Switch` retire toute la chaîne à la fin : la scène s'arrête là.
        sim.tl.duration = min(sim.tl.duration, _f(root_doc, "duration") / 1000.0)
    for entry in sim.open.values():
        entry.setdefault("until", round(sim.tl.duration, 3))
    for summon in sim.tl.summons:
        summon["moves"].sort(key=lambda m: m["t"])
    for moves in sim.tl.spawn_moves.values():
        moves.sort(key=lambda m: m["t"])
    sim.tl.chats.sort(key=lambda c: c["t"])
    sim.tl.shakes.sort(key=lambda c: c["t"])
    sim.tl.teleports.sort(key=lambda c: c["t"])
    if sim.tl.exit is not None:
        # Le joueur quitte la carte : la scène s'arrête là (ses buffs locaux tombent avec elle).
        sim.tl.duration = min(sim.tl.duration, sim.tl.exit) if sim.tl.duration else sim.tl.exit
    for bucket in (sim.tl.weather, sim.tl.sounds, sim.tl.effects, sim.tl.post):
        for item in bucket:
            if item.get("until") is None:
                item["until"] = round(sim.tl.duration, 3)
    end = sim.tl.duration
    sim.tl.lines = [line for line in sim.tl.lines if line["t"] < end]
    sim.tl.shots = [shot for shot in sim.tl.shots if shot["t"] < end]
    for summon in sim.tl.summons:
        if summon["until"] is None or summon["until"] > end:
            summon["until"] = round(end, 3)
    sim.tl.lines.sort(key=lambda l: l["t"])
    sim.tl.shots.sort(key=lambda s: s["t"])
    return sim.tl


def region_origin(path: str) -> tuple[float, float]:
    m = re.search(r"/(\d+)_(\d+)/(\d+)_(\d+)_[A-Za-z0-9_]*ServerObjects", path)
    if not m:
        return 0.0, 0.0
    bx, by, i, j = (int(g) for g in m.groups())
    return (bx + i) * REGION_SIZE, (by + j) * REGION_SIZE


def walk_speed(mob: Path) -> float:
    """`walkSpeed` d'un `MobWorld` (m/s ; 2 quand il n'est pas donné, valeur la plus courante)."""
    doc = _read(mob)
    return _f(doc, "walkSpeed", 2.0) if doc is not None else 2.0


def mob_visual(tree: Tree, mob: Path) -> str | None:
    """Chemin de la `VisualMob` d'un `MobWorld` 7.0 (`Characters/Elf_female/VisualMob/…`) : le dossier
    du modèle, qui départage les PNJ homonymes du 17.0."""
    doc = _read(mob)
    vis = doc.find("visMob") if doc is not None else None
    if vis is None or not vis.get("href"):
        return None
    return tree.rel(tree.resolve(mob, vis.get("href")))


def mob_name(tree: Tree, mob: Path) -> str:
    """Nom russe d'un `MobWorld` 7.0 (`.Name.txt` voisin, sinon son `name`)."""
    name_file = mob.with_name(mob.name.replace(".(MobWorld).xdb", ".(MobWorld).Name.txt"))
    name = clean(_text(name_file)) if name_file.is_file() else ""
    if not name:
        doc_mob = _read(mob)
        href = doc_mob.find("name") if doc_mob is not None else None
        if href is not None and href.get("href"):
            name = clean(_text(tree.resolve(mob, href.get("href"))))
    return name


def find_spawns(root: Path, map_name: str, scripts: set[str]) -> dict[str, dict]:
    """Placement des PNJ nommés (`scriptID`) dans les `ServerObjects` de la carte."""
    tree = Tree(Path(root))
    out: dict[str, dict] = {}
    folder = tree.root / "Maps" / map_name
    for path in sorted(folder.glob("*/*ServerObjects.xdb")):
        raw = path.read_bytes()
        if not any(s.split("/")[-1].encode() in raw for s in scripts):
            continue
        doc = _read(path)
        if doc is None:
            continue
        ox, oy = region_origin(tree.rel(path))
        for item in doc.iter("Item"):
            script = item.findtext("scriptID")
            table = item.find("spawnTable")
            if table is not None and table.get("href"):       # `SpawnLocus` : table d'apparition posée
                script = "table:" + tree.rel(tree.resolve(path, table.get("href")))
                place = item.find("places/Item")
                center = place.find("center") if place is not None else None
                if script in scripts and script not in out and center is not None:
                    out[script] = {"p": [float(center.get("x", 0)) + ox, float(center.get("y", 0)) + oy,
                                         float(center.get("z", 0))], "yaw": _f(place, "yaw"), "mob": None,
                                   "name": "", "visual": None, "file": tree.rel(path)}
                continue
            if script not in scripts or script in out:
                continue
            place = item.find("place")
            center = place.find("center") if place is not None else None
            if center is None:                   # `gameMechanics.map.Locator` : position, yaw
                center, place = item.find("position"), item
            obj = item.find("object")
            if center is None:
                continue
            # Repère nu (`MapLocator`, cible d'une invocation ou d'une marche) : pas de `MobWorld`.
            mob = tree.resolve(path, obj.get("href", "")) if obj is not None and obj.get("href") else None
            out[script] = {"p": [float(center.get("x", 0)) + ox, float(center.get("y", 0)) + oy, float(center.get("z", 0))],
                           "yaw": _f(place, "yaw"),
                           "mob": (tree.rel(mob) if mob.is_file() else obj.get("href")) if mob is not None else None,
                           "name": mob_name(tree, mob) if mob is not None and mob.is_file() else "",
                           "visual": mob_visual(tree, mob) if mob is not None and mob.is_file() else None,
                           "file": tree.rel(path)}
    # Stèles posées sur un objet du décor (`MapRegion` : `serverStatic` `StaticDevice` — sol de l'étage 6,
    # portail kanien) : place et lacet de l'objet, stèle, gabarit statique qu'elle remplace ou anime.
    for path in sorted(folder.glob("*/*_MapRegion.xdb")):
        raw = path.read_bytes()
        if b"StaticDevice" not in raw or not any(s.split("/")[-1].encode() in raw for s in scripts):
            continue
        doc = _read(path)
        m = re.search(r"/(\d+)_(\d+)/(\d+)_(\d+)_MapRegion", tree.rel(path))
        if doc is None or not m:
            continue
        bx, by, i, j = (int(g) for g in m.groups())
        ox, oy = (bx + i) * REGION_SIZE, (by + j) * REGION_SIZE
        for item in doc.iter("Item"):
            static = item.find("serverStatic")
            script = static.findtext("scriptID") if static is not None else None
            if not script or script not in scripts or script in out:
                continue
            pos, rot = item.find("Position"), item.find("Rotation")
            device, tpl = static.find("device"), item.find("StaticObjectTemplate")
            if pos is None or device is None or not device.get("href"):
                continue
            out[script] = {"p": [float(pos.get("X", 0)) + ox, float(pos.get("Y", 0)) + oy, float(pos.get("Z", 0))],
                           "yaw": float(rot.get("Yaw", 0)) if rot is not None else 0.0,
                           "mob": tree.rel(tree.resolve(path, device.get("href"))), "name": "", "visual": None,
                           "static": tree.rel(tree.resolve(path, tpl.get("href"))) if tpl is not None and tpl.get("href") else None,
                           "file": tree.rel(path)}
    return out


def flag_devices(root: Path, map_name: str, flags: set[str]) -> list[dict]:
    """Stèles du décor (`StaticDevice` d'un `MapRegion`, avec ou sans `scriptID`) dont le script visuel
    lit l'un des drapeaux `flags` (`DeviceIfFlagVisAction`, posé sur le joueur par le déroulé : le
    cinéma pridien) : place, lacet, échelle, gabarit statique, et animation jouée par drapeau."""
    tree = Tree(Path(root))
    out: list[dict] = []
    if not flags:
        return out
    cache: dict[Path, list[dict]] = {}
    for path in sorted((tree.root / "Maps" / map_name).glob("*/*_MapRegion.xdb")):
        raw = path.read_bytes()
        if b"StaticDevice" not in raw:
            continue
        doc = _read(path)
        m = re.search(r"/(\d+)_(\d+)/(\d+)_(\d+)_MapRegion", tree.rel(path))
        if doc is None or not m:
            continue
        bx, by, i, j = (int(g) for g in m.groups())
        for item in doc.iter("Item"):
            static = item.find("serverStatic")
            device = static.find("device") if static is not None else None
            if device is None or not device.get("href"):
                continue
            stele = tree.resolve(path, device.get("href"))
            if stele not in cache:
                cache[stele] = []
                sdoc = _read(stele)
                vis = sdoc.find("visScripts") if sdoc is not None else None
                vpath = tree.resolve(stele, vis.get("href")) if vis is not None and vis.get("href") else None
                vdoc = _read(vpath) if vpath is not None else None
                for branch in (vdoc.iter() if vdoc is not None else []):
                    if not (branch.get("type") or "").endswith("DeviceIfFlagVisAction"):
                        continue
                    flag, loop = branch.find("visualFlag"), branch.find("visScriptLoop")
                    if flag is None or not flag.get("href") or loop is None:
                        continue
                    cache[stele].append({"flag": tree.rel(tree.resolve(vpath, flag.get("href"))),
                                         "clips": [a.text for a in loop.findall("animations/Item") if a.text],
                                         "mode": loop.findtext("mode") or "DIE"})
            branches = [b for b in cache[stele] if b["flag"] in flags]
            if not branches:
                continue
            pos, rot, scale = item.find("Position"), item.find("Rotation"), item.find("Scale")
            tpl = item.find("StaticObjectTemplate")
            out.append({"p": [float(pos.get("X", 0)) + (bx + i) * REGION_SIZE, float(pos.get("Y", 0)) + (by + j) * REGION_SIZE,
                              float(pos.get("Z", 0))],
                        "yaw": float(rot.get("Yaw", 0)) if rot is not None else 0.0,
                        "scale": float(scale.get("Ratio", 1)) if scale is not None else 1.0,
                        "mob": tree.rel(stele), "static": tree.rel(tree.resolve(path, tpl.get("href"))) if tpl is not None else None,
                        "branches": branches, "file": tree.rel(path)})
    return out


def read_game_scene(root: Path, path: str) -> dict:
    """`GameViewScene` 7.0 : place (x, y, z) et `scriptID` de ses PNJ — de quoi retrouver celle du 17.0."""
    doc = _read(Path(root) / path)
    place = doc.find("place") if doc is not None else None
    p = [_f(place, k) for k in ("x", "y", "z")] if place is not None else None
    mobs = [m.findtext("scriptID") for m in doc.findall("mobs/Item")] if doc is not None else []
    return {"place": p, "mobs": mobs}


def script_actions(root: Path, path: str | None) -> int:
    """Nombre d'actions d'un `GameViewScript` 7.0."""
    doc = _read(Path(root) / path) if path else None
    return len(doc.findall("actions/Item")) if doc is not None else 0


def track_keys(src: list, t0: float, duration: float | None) -> list[dict]:
    """Clés d'une piste (caméra ou visée) d'un plan. La durée d'un point est le temps pour
    rejoindre le suivant ; quand le buff a une durée, les durées sont prises comme des **poids**
    étalés sur toute la durée du buff (la dernière ne compte pas). Établi sur les plans de
    `Ferris_4_secret1` : `Cutscene_01` (12, 10 dans un buff de 12 s) et `Cutscene_03` (95, 10 dans
    un buff de 10,5 s) ne se lisent ensemble ni en secondes ni en dixièmes ; en poids, les deux
    couvrent exactement leur buff. Sans durée de buff (client 17.0 seul), secondes."""
    total = sum(d for d, _ in src[:-1])
    scale = duration / total if duration and total > 0 else 1.0
    out, t = [], t0
    for dur, pos in src:
        out.append({"t": round(t, 3), "p": [round(v, 4) for v in pos]})
        t += dur * scale
    return out


def camera_keys(shots: list[dict]) -> dict:
    """Plans enchaînés ; au plan suivant, coupe franche (clé tenue jusqu'à l'instant de la coupe).
    Un plan aux points tous nuls rend la caméra au jeu (vue du joueur, inconnue ici) : il est
    ignoré, le plan précédent tient (ou le suivant, s'il ouvre la scène)."""
    def blank(track: list) -> bool:
        return all(not any(p) for _, p in track)
    start = shots[0]["t"] if shots else 0.0
    shots = [s for s in shots if not (blank(s["points"]) and blank(s["targets"]))]
    points, targets = [], []
    for k, shot in enumerate(shots):
        end = shots[k + 1]["t"] if k + 1 < len(shots) else shot["t"] + (shot["duration"] or 0)
        for out, src in ((points, shot["points"]), (targets, shot["targets"])):
            keys = track_keys(src, shot["t"], shot["duration"])
            kept = [key for key in keys if key["t"] < end - 1e-6] or keys[:1]
            out += kept
            nxt = next((key for key in keys if key["t"] >= end - 1e-6), None)
            last = kept[-1]
            if nxt is not None and nxt is not last:
                u = (end - last["t"]) / max(nxt["t"] - last["t"], 1e-9)
                p = [round(a + (b - a) * min(1.0, u), 4) for a, b in zip(last["p"], nxt["p"])]
            else:
                p = last["p"]
            if last["t"] < end - 2e-3:
                out.append({"t": round(end - 1e-3, 3), "p": p})
    for track in (points, targets):
        if track and track[0]["t"] > start:
            track.insert(0, {"t": round(start, 3), "p": track[0]["p"]})
    return {"points": points, "targets": targets}
