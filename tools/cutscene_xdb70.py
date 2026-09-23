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
  `scriptID`, `center` local à la région, `yaw`, `MobWorld`).

Le module ne rend que des chemins `.xdb` et des valeurs ; `tools/extract_engine_cutscene.py` les
rapporte aux ressources du client 17.0 (voix, textes, modèles) et vérifie les plans de caméra.
"""
from __future__ import annotations

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


def read_client_data(tree: Tree, path: Path) -> dict:
    """Réplique d'un `ClientData` 7.0 : texte russe, durée, voix, animations."""
    doc = _read(path)
    out = {"clientdata": tree.rel(path), "ru": "", "delay_ms": 0, "voice": None, "animations": []}
    if doc is None:
        return out
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
        elif kind == "ImpactClientDataParams":
            data = node.find("data")
            if data is not None and data.get("href"):
                path = self.tree.resolve(base, data.get("href"))
                line = read_client_data(self.tree, path)
                if line["ru"] or line["voice"] or line["animations"]:
                    line.update({"t": round(t, 3), "speaker": target})
                    self.tl.lines.append(line)
                    if target != "player":
                        self.tl.scripts.add(target)

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


def simulate(root: Path, first_buff: str, horizon: float = 600.0) -> Timeline:
    tree = Tree(Path(root))
    sim = Simulator(tree, horizon)
    sim.attach(tree.root / first_buff, 0.0)
    for entry in sim.open.values():
        entry.setdefault("until", round(sim.tl.duration, 3))
    for bucket in (sim.tl.weather, sim.tl.sounds, sim.tl.effects, sim.tl.post):
        for item in bucket:
            if item.get("until") is None:
                item["until"] = round(sim.tl.duration, 3)
    sim.tl.lines.sort(key=lambda l: l["t"])
    sim.tl.shots.sort(key=lambda s: s["t"])
    return sim.tl


def region_origin(path: str) -> tuple[float, float]:
    m = re.search(r"/(\d+)_(\d+)/(\d+)_(\d+)_[A-Za-z0-9_]*ServerObjects", path)
    if not m:
        return 0.0, 0.0
    bx, by, i, j = (int(g) for g in m.groups())
    return (bx + i) * REGION_SIZE, (by + j) * REGION_SIZE


def find_spawns(root: Path, map_name: str, scripts: set[str]) -> dict[str, dict]:
    """Placement des PNJ nommés (`scriptID`) dans les `ServerObjects` de la carte."""
    tree = Tree(Path(root))
    out: dict[str, dict] = {}
    folder = tree.root / "Maps" / map_name
    for path in sorted(folder.glob("*/*ServerObjects.xdb")):
        raw = path.read_bytes()
        if not any(s.encode() in raw for s in scripts):
            continue
        doc = _read(path)
        if doc is None:
            continue
        ox, oy = region_origin(tree.rel(path))
        for item in doc.iter("Item"):
            script = item.findtext("scriptID")
            if script not in scripts or script in out:
                continue
            place = item.find("place")
            center = place.find("center") if place is not None else None
            obj = item.find("object")
            if center is None or obj is None:
                continue
            mob = tree.resolve(path, obj.get("href", ""))
            name_file = mob.with_name(mob.name.replace(".(MobWorld).xdb", ".(MobWorld).Name.txt"))
            name = clean(_text(name_file)) if name_file.is_file() else ""
            if not name:
                doc_mob = _read(mob)
                href = doc_mob.find("name") if doc_mob is not None else None
                if href is not None and href.get("href"):
                    name = clean(_text(tree.resolve(mob, href.get("href"))))
            out[script] = {"p": [float(center.get("x", 0)) + ox, float(center.get("y", 0)) + oy, float(center.get("z", 0))],
                           "yaw": _f(place, "yaw"), "mob": tree.rel(mob) if mob.is_file() else obj.get("href"),
                           "name": name, "file": tree.rel(path)}
    return out


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
    """Plans enchaînés ; au plan suivant, coupe franche (clé tenue jusqu'à l'instant de la coupe)."""
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
    return {"points": points, "targets": targets}
