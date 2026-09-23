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
    # États visuels posés sur une stèle (`ImpactSetVisualState`) : {t, device (scriptID), state}
    devices: list[dict] = field(default_factory=list)
    # PNJ posés sur la carte que le déroulé fait marcher (`GoThroughPath`, `ImpactGoTo`) :
    # scriptID → [{t, locator, run}] ; retirés (`Disintegrate`) : scriptID → t
    moves: dict[str, list[dict]] = field(default_factory=dict)
    gone: dict[str, float] = field(default_factory=dict)
    # Messages de PNJ (`ImpactMobChat` → `TextMessage`) : {t, speaker, ru, message}
    chats: list[dict] = field(default_factory=list)


def read_client_data(tree: Tree, path: Path) -> dict:
    """Réplique d'un `ClientData` 7.0 : texte russe, durée, voix, animations ; bulle au-dessus du
    PNJ (`InterfaceAction` `ENUM_SHOW_BUBBLE` : `bubble`, texte russe)."""
    doc = _read(path)
    out = {"clientdata": tree.rel(path), "ru": "", "delay_ms": 0, "voice": None, "animations": []}
    if doc is None:
        return out
    for data in doc.iter("customData"):
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
    return out


def read_camera(action: ET.Element) -> dict:
    def pts(tag: str):
        return [(_f(p, "duration"), tuple(float(p.find("position").get(k, 0)) for k in "xyz"))
                for p in action.findall(f"{tag}/Item") if p.find("position") is not None]
    return {"points": pts("cameraPoints"), "targets": pts("targetPoints")}


class Simulator:
    """Déroule une chaîne de buffs à partir de son premier buff."""

    def __init__(self, tree: Tree, horizon: float = 600.0) -> None:
        self.tree = tree
        self.tl = Timeline()
        self.horizon = horizon
        self.open: dict[str, dict] = {}     # buff sans durée → entrée, fermée par un BuffDetacher

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
        elif kind in ("ImpactInstantiating", "ImpactInstantiatingWithAddressee"):
            for sub in node.findall("impacts/Item"):
                self.impact(base, sub, t, target)
        elif kind == "ImpactsToInterlocutor":
            # PNJ à qui parle le joueur (donneur de la quête) : désigné « interlocutor », le manifeste
            # le rattache à un PNJ.
            for sub in node.findall("impacts/Item"):
                self.impact(base, sub, t, "interlocutor")
        elif kind == "ImpactIfTarget":
            # Seules conditions rencontrées : `PredicateNot(PredicateHasContentKey China)` — la version
            # chinoise passe par `impactsElse` ; les autres clients jouent `impactsIf`.
            for sub in node.findall("impactsIf/Item"):
                self.impact(base, sub, t, target)
        elif kind == "ImpactSetVisualState" and target not in ("player", "interlocutor"):
            self.tl.devices.append({"t": round(t, 3), "device": target, "state": int(_f(node, "visualState"))})
            self.tl.scripts.add(target)
        elif kind == "ImpactMobChat":
            msg = node.find("msg")
            if msg is not None and msg.get("href"):
                path = self.tree.resolve(base, msg.get("href"))
                doc = _read(path)
                href = next((e.get("href") for e in doc.iter() if e.tag.lower() == "text" and e.get("href")), None) \
                    if doc is not None else None
                if href:
                    self.tl.chats.append({"t": round(t, 3), "speaker": target, "message": self.tree.rel(path),
                                          "ru": clean(_text(self.tree.resolve(path, href)))})
        elif kind == "ImpactSummon":
            self.summon(base, node, t)
        elif kind == "ImpactFindSpawnTable":
            table = self.spawn_table(base, node)
            for sub in node.findall("impacts/Item"):
                self.impact(base, sub, t, table or target)
        elif kind == "GoThroughPath":
            summon = self.summon_by_id(target)
            run = (node.findtext("runningMode") or "").strip() == "true"
            for step in node.findall("path/Item"):
                locator = step.findtext("scriptID")
                mp = step.find("map")
                if mp is not None and mp.get("href"):
                    m = re.search(r"/Maps/([^/]+)/", mp.get("href"))
                    if m:
                        self.tl.maps.add(m.group(1))
                if not locator:
                    continue
                if summon is not None:
                    summon["moves"].append({"t": round(t, 3), "locator": locator})
                    self.tl.scripts.add(locator)
                elif target != "player":
                    self.tl.moves.setdefault(target, []).append({"t": round(t, 3), "locator": locator, "run": run})
                    self.tl.scripts.update({locator, target})
        elif kind == "ImpactGoTo":
            summon = self.summon_by_id(target)
            locator = self.locator(node.find("destination"))
            if summon is not None and locator:
                summon["moves"].append({"t": round(t, 3), "locator": locator})
                self.tl.scripts.add(locator)
            elif locator and target != "player":
                self.tl.moves.setdefault(target, []).append({"t": round(t, 3), "locator": locator, "run": False})
                self.tl.scripts.update({locator, target})
        elif kind == "Disintegrate":
            summon = self.summon_by_id(target)
            if summon is not None and summon.get("until") is None:
                summon["until"] = round(t, 3)
            elif summon is None and target != "player":
                self.tl.gone.setdefault(target, round(t, 3))
        elif kind in ("ImpactClientDataParams", "ImpactClientData"):
            data = node.find("data")
            if data is not None and data.get("href"):
                path = self.tree.resolve(base, data.get("href"))
                line = read_client_data(self.tree, path)
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

    def vis(self, path: Path, t: float, duration: float, target: str, buff: dict) -> None:
        doc = _read(path)
        if doc is None:
            return
        for action in doc.iter():
            kind = (action.get("type") or "").rsplit(".", 1)[-1]
            until = t + duration if duration else None
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
                    self.tl.sounds.append({"t": round(t, 3), "until": until, "buff": buff["buff"], "name": name,
                                           "kind": action.findtext("actionType") or "Sound"})
            elif kind in ("CreatureIndependentFxAction", "CreatureEffectsAction", "CreatureAnimationAction") and target != "player":
                entry = {"t": round(t, 3), "until": until, "buff": buff["buff"], "target": target, "kind": kind}
                if kind == "CreatureAnimationAction":
                    entry["animations"] = [a.text for a in action.findall("animations/Item") if a.text]
                    entry["mode"] = action.findtext("mode") or "DIE"
                else:
                    hrefs = [e.get("href") for e in action.iter() if e.tag in ("visObject", "fx") and e.get("href")]
                    entry["visObjects"] = [self.tree.rel(self.tree.resolve(path, h)) for h in hrefs]
                self.tl.effects.append(entry)


def simulate(root: Path, first_buff: str, horizon: float = 600.0, impacts: str | None = None,
             duration: float | None = None) -> Timeline:
    """Déroulé d'une chaîne de buffs à partir de son premier buff ; ou, avec `impacts`, de la liste
    d'impacts `impacts` d'une autre ressource (`startImpacts` d'une quête, `impactsIn` d'une zone de
    script), jouée à 0 s par le joueur. Sans buff à durée pour la borner, la scène dure `duration`
    (sinon jusqu'au dernier événement)."""
    tree = Tree(Path(root))
    sim = Simulator(tree, horizon)
    if impacts:
        path = tree.root / first_buff
        doc = _read(path)
        for node in (doc.findall(f"{impacts}/Item") if doc is not None else []):
            sim.impact(path, node, 0.0, "player")
        events = [x["t"] for bucket in (sim.tl.lines, sim.tl.devices, sim.tl.chats, sim.tl.summons) for x in bucket]
        events += [m["t"] for ms in sim.tl.moves.values() for m in ms]
        # Fin : dernier événement, prolongée par l'extraction (durée des voix, des scènes du client).
        sim.tl.duration = float(duration) if duration else max([sim.tl.duration] + events) + 1e-3
    else:
        sim.attach(tree.root / first_buff, 0.0)
    root_doc = _read(tree.root / first_buff)
    if not impacts and root_doc is not None and _f(root_doc, "duration") and root_doc.find(".//impactsOff") is not None:
        # Buff racine à durée dont le `Switch` retire toute la chaîne à la fin : la scène s'arrête là.
        sim.tl.duration = min(sim.tl.duration, _f(root_doc, "duration") / 1000.0)
    for entry in sim.open.values():
        entry.setdefault("until", round(sim.tl.duration, 3))
    for summon in sim.tl.summons:
        summon["moves"].sort(key=lambda m: m["t"])
    for moves in sim.tl.moves.values():
        moves.sort(key=lambda m: m["t"])
    sim.tl.devices.sort(key=lambda d: d["t"])
    sim.tl.chats.sort(key=lambda c: c["t"])
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
    return out


def device_scenes(root: Path, map_name: str, devices: list[dict]) -> list[dict]:
    """Scènes du client jouées par les stèles du déroulé : l'état visuel posé (`ImpactSetVisualState`)
    choisit l'état de la `DeviceVisScripts` de la stèle (`SteleResource.visScripts`, `states[i]`),
    dont l'action `ShowSceneAction` joue une `GameViewScene` avec son `GameViewScript`, jusqu'au
    changement d'état suivant de la même stèle (`until`, `None` : jusqu'à la fin)."""
    tree = Tree(Path(root))
    spawns = find_spawns(root, map_name, {d["device"] for d in devices})
    devices = [d for k, d in enumerate(devices) if d not in devices[:k]]      # impacts posés deux fois
    out = []
    for k, dev in enumerate(devices):
        sp = spawns.get(dev["device"])
        stele = tree.root / sp["mob"] if sp and sp.get("mob") else None
        doc = _read(stele) if stele is not None else None
        vis = doc.find("visScripts") if doc is not None else None
        if vis is None or not vis.get("href"):
            continue
        vis_path = tree.resolve(stele, vis.get("href"))
        vdoc = _read(vis_path)
        states = vdoc.findall("states/Item") if vdoc is not None else []
        # État visuel `n` → `states[n - 1]` (0 : la stèle posée, sans état) : la quête « Эвакуация »
        # pose 1 sur ses trois stèles de scène (`states[0]` : la scène) puis 2 à l'échéance
        # (`states[1]` : `NoScene`, qui retire les PNJ).
        index = dev["state"] - 1
        if not 0 <= index < len(states):
            continue
        action = states[index].find("action")
        if action is None or not (action.get("type") or "").endswith("ShowSceneAction"):
            continue
        scene, script = action.find("scene"), action.find("script")
        if scene is None or not scene.get("href"):
            continue
        nxt = next((d["t"] for d in devices[k + 1:] if d["device"] == dev["device"]), None)
        out.append({"t": dev["t"], "until": nxt, "device": dev["device"], "state": dev["state"],
                    "stele": tree.rel(stele), "at": sp["p"],
                    "scene": tree.rel(tree.resolve(vis_path, scene.get("href"))),
                    "script": tree.rel(tree.resolve(vis_path, script.get("href"))) if script is not None and script.get("href") else None})
    return out


def read_game_scene(root: Path, path: str) -> dict:
    """`GameViewScene` 7.0 : place (x, y, z), `scriptID` de ses PNJ ; et nombre d'actions d'un
    `GameViewScript` (`actions`) — de quoi retrouver les ressources du 17.0."""
    doc = _read(Path(root) / path)
    place = doc.find("place") if doc is not None else None
    p = [_f(place, k) for k in ("x", "y", "z")] if place is not None else None
    mobs = [m.findtext("scriptID") for m in doc.findall("mobs/Item")] if doc is not None else []
    return {"place": p, "mobs": mobs}


def script_actions(root: Path, path: str | None) -> int:
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
