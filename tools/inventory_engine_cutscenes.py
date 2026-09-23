#!/usr/bin/env python3
"""Inventaire des cinématiques jouées par le moteur (« mini-cinématiques » des quêtes).

Ce ne sont pas des vidéos : le jeu les monte en temps réel avec des ressources de mécanique.
Deux sources, croisées :

* **l'arbre serveur 7.0 (xdb, XML)** — seul endroit où ces ressources ont encore leurs noms et
  leur structure (il contient aussi des quêtes 11.0/12.0). Une scène = un dossier de quête, de
  raid ou de carte qui contient au moins une ressource de mise en scène : buff du groupe
  `CutScene.(ActionGroup)`, `CameraTrackAction` (trajet de caméra), `CameraAnimationAction`
  ou `ShowSceneAction` (`GameViewScene` + `GameViewScript`). On y relève la carte, la quête
  (nom, intrigue), les buffs et leur durée, les trajets de caméra, et les `ClientData`
  (répliques : animation, sous-titre `UISubtitleShow` + durée, voix `Sound2D/3DAction`).
* **le dernier client (17.0)** — base compilée `Bin/pack.bin` sans noms de ressources. On y
  retrouve les noms d'événements vocaux FMOD (`Cutscenes/<arc>/<réplique>`, projets
  `VoiceDialogs*`) et les éléments de sous-titres (voir `tools/extract_cinematics.py`) ; un
  sous-titre est apparié à la voix sérialisée juste après lui dans le même objet. Les
  répliques de l'arbre 7.0 sont retrouvées dans le 17.0 par leur texte russe ; les répliques
  vocales du 17.0 qu'aucune scène 7.0 ne porte (Isa, Eden…) forment des scènes « 17.0 seul »,
  regroupées par arc et par préfixe de nom.

Sortie : la clé `engine_cutscenes.scenes` de `tools/cinematics_manifest.json` (et un
résumé sur la sortie standard).

Usage : python3 tools/inventory_engine_cutscenes.py [--server-root DIR] [--client DIR]
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import struct
import sys
import zipfile
import zlib
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.extract_cinematics import clean_text, norm_key, scan_subtitles, unpack_loc  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_SERVER = "/mnt/f/ALLODS ONLINE SERVER/Allods 7.0/game/data"
DEFAULT_CLIENT = "/mnt/h/MyGames/AllodsRU"
MANIFEST = HERE / "cinematics_manifest.json"
MARKERS = ("CutScene.(ActionGroup)", "CameraTrackAction", "CameraAnimationAction", "ShowSceneAction")
# Dossiers écartés : trajets de vol d'aigle (caméra de monture) et la définition du groupe.
SKIP_PREFIXES = ("Creatures/Eagle/", "Mechanics/Spells/Groups", "Creatures/CutScenes/CameraAnimationAction_Test")
# Faction d'une scène : déduite de la carte quand son nom la porte, sinon commune (les zones de
# fin de jeu, raids et îles astrales sont partagées par les deux factions).
FACTION_BY_MAP = {"Inst_EmpireStart": "empire", "Inst_LeagueStart": "league", "AstralHangarHadagan": "empire",
                  "AstralHangarLeague": "league", "Hadagan_Sanatorium": "empire"}


def faction_of(scene: dict) -> str:
    if scene.get("map") in FACTION_BY_MAP:
        return FACTION_BY_MAP[scene["map"]]
    return "common"


def has_content(scene: dict) -> bool:
    """Une scène vide (ni caméra, ni scène de jeu, ni réplique) est un faux positif du repérage."""
    return bool(scene.get("camera_tracks") or scene.get("game_scenes") or scene["lines"])
VOICE_EVENT_RE = re.compile(rb"(?<![A-Za-z0-9_/])(Cutscenes/[A-Za-z0-9_]+/[A-Za-z0-9_\-/]+)\x00")


# --- arbre serveur 7.0 ---------------------------------------------------------------------

def read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-16", "utf-8", "cp1251"):
        try:
            txt = raw.decode(enc)
            return txt.lstrip("﻿")
        except UnicodeDecodeError:
            continue
    return ""


def parse_xml(path: Path) -> ET.Element | None:
    try:
        return ET.fromstring(path.read_bytes())
    except (ET.ParseError, OSError):
        return None


def resolve_href(folder: Path, root: Path, href: str) -> Path:
    href = href.split("#", 1)[0]
    return root / href.lstrip("/") if href.startswith("/") else folder / href


def client_data_lines(path: Path, root: Path) -> list[dict]:
    """Répliques d'une ressource ClientData : sous-titres (texte + durée), voix, animations."""
    doc = parse_xml(path)
    if doc is None:
        return []
    voices = [el.findtext("name") for el in doc.iter("sound") if el.findtext("name")]
    anims = [a.text for a in doc.iter("animations") for a in a if a.text]
    lines = []
    for sub in doc.iter("subtitles"):
        for item in sub:
            href = item.find("text")
            text = ""
            if href is not None and href.get("href"):
                p = resolve_href(path.parent, root, href.get("href"))
                if p.is_file():
                    text = clean_text(read_text(p))
            lines.append({"ru": text, "delay_ms": int(item.findtext("delayMs") or 0)})
    if not lines and voices:
        lines.append({"ru": "", "delay_ms": 0})
    for line in lines:
        line["voice"] = voices[0] if voices else None
        line["anims"] = anims
        line["resource"] = path.name
    return lines


def scan_folder(folder: Path, root: Path) -> dict:
    rel = folder.relative_to(root).as_posix()
    scene = {"id": rel, "source": "7.0 xdb", "map": None, "quest": None, "plotline": None,
             "buffs": 0, "buff_ms": 0, "camera_tracks": 0, "camera_points": 0, "game_scenes": 0, "lines": []}
    maps = collections.Counter()
    for name in sorted(os.listdir(folder)):
        path = folder / name
        if not name.endswith(".xdb") or not path.is_file():
            continue
        raw = path.read_bytes()
        for m in re.finditer(rb'href="/Maps/([^/"]+)/', raw):
            maps[m.group(1).decode()] += 1
        if b"(ClientData)" in name.encode():
            scene["lines"] += client_data_lines(path, root)
        elif name.endswith("(BuffResource).xdb") and b"CutScene.(ActionGroup)" in raw:
            scene["buffs"] += 1
            m = re.search(rb"<duration>(\d+)</duration>", raw)
            scene["buff_ms"] += int(m.group(1)) if m else 0
        elif b"CameraTrackAction" in raw:
            scene["camera_tracks"] += raw.count(b'type="CameraTrackAction"')
            scene["camera_points"] += raw.count(b"<position ")
        elif name.endswith("(GameViewScene).xdb") or b"ShowSceneAction" in raw:
            scene["game_scenes"] += 1
        if b"QuestResource" in raw[:400] and scene["quest"] is None:
            doc = parse_xml(path)
            if doc is not None:
                href = doc.find("name")
                if href is not None and href.get("href"):
                    p = resolve_href(folder, root, href.get("href"))
                    scene["quest"] = clean_text(read_text(p)) if p.is_file() else None
                scene["plotline"] = doc.findtext("plotline")
    scene["map"] = maps.most_common(1)[0][0] if maps else None
    return scene


def server_scenes(root: Path, hits: list[str]) -> list[dict]:
    folders = sorted({(Path(h) if Path(h).is_absolute() else root / h).parent for h in hits})
    out = []
    for folder in folders:
        rel = folder.relative_to(root).as_posix()
        if rel.startswith(SKIP_PREFIXES):
            continue
        scene = scan_folder(folder, root)
        if has_content(scene):
            out.append(scene)
    return out


def find_markers(root: Path) -> list[str]:
    """Fichiers xdb portant un marqueur de mise en scène (parcours de l'arbre, lent sur 9P)."""
    hits = []
    for base in ("World", "Maps", "Mechanics", "Items"):
        for dp, _, fn in os.walk(root / base):
            for f in fn:
                if f.endswith(".xdb"):
                    p = Path(dp) / f
                    try:
                        raw = p.read_bytes()
                    except OSError:
                        continue
                    if any(m.encode() in raw for m in MARKERS):
                        hits.append(str(p))
    return hits


# --- dernier client (17.0) ---------------------------------------------------------------------

def client_events(client: Path) -> tuple[list[dict], dict[str, int], list[str], list[str]]:
    """Sous-titres du 17.0 (idx, durée, textes, voix appariée) et noms d'événements vocaux."""
    with zipfile.ZipFile(client / "data/Packs/Texts_x64.pak") as z:
        ru = unpack_loc(z.read("Bin/pack.rus.loc"))
        en = unpack_loc(z.read("Bin/pack.eng_eu.loc"))
    with zipfile.ZipFile(client / "data/Packs/BaseLocall_x64.pak") as z:
        blob = zlib.decompress(z.read("Bin/pack.bin"))
    subs = scan_subtitles(blob, min(len(ru), len(en)))
    # position de chaque élément de sous-titre (même motif que scan_subtitles)
    positions = {}
    for m in re.finditer(rb"\x01\x00\x00\x00\x00\x00\x00[\x00\x80]", blob):
        t = m.start() - 16
        if t < 56:
            continue
        idx = struct.unpack_from("<Q", blob, t)[0]
        if idx in subs and idx not in positions and struct.unpack_from("<QQ", blob, t - 56) == (40, 40):
            positions[idx] = t
    voices = [(m.start(1), m.group(1).decode()) for m in VOICE_EVENT_RE.finditer(blob)]
    events = sorted([(o, "sub", i) for i, o in positions.items()] + [(o, "voice", v) for o, v in voices])
    # Appariement : la voix sérialisée juste après le sous-titre, sinon juste avant (l'ordre
    # des éléments d'un CustomClientDataList varie), à moins de 900 octets.
    paired: dict[int, str] = {}
    used: set[int] = set()
    for k, (off, kind, val) in enumerate(events):
        if kind == "sub" and k + 1 < len(events) and events[k + 1][1] == "voice" and events[k + 1][0] - off < 900:
            paired[val] = events[k + 1][2]
            used.add(k + 1)
    for k, (off, kind, val) in enumerate(events):
        if kind == "voice" and k not in used and k + 1 < len(events):
            nxt = events[k + 1]
            if nxt[1] == "sub" and nxt[2] not in paired and nxt[0] - off < 900:
                paired[nxt[2]] = val
    lines = [{"idx": i, "delay_ms": subs[i], "voice": paired.get(i), "ru": clean_text(ru[i]), "en": clean_text(en[i])}
             for i in sorted(positions)]
    ru_index = {}
    for i in subs:
        ru_index.setdefault(norm_key(ru[i]), i)
    all_voices = sorted({v for _, v in voices})
    return lines, ru_index, all_voices, ru


def voice_scene_key(event: str) -> str:
    """`Cutscenes/Isa/Isa_Arrival_2_Urun_Replika_03` → `Cutscenes/Isa/Isa_Arrival_2_Urun`."""
    parts = event.split("/")
    stem = re.sub(r"(_?(Replika|Replic|Line|Say)?_?[A-Z]?_?\d+)$", "", parts[-1])
    stem = re.sub(r"_(F|M)$", "", stem)
    tokens = stem.split("_")
    return "/".join(parts[:2] + ["_".join(tokens[:4])])


def build(root: Path, client: Path, hits: list[str]) -> list[dict]:
    scenes = server_scenes(root, hits)
    lines17, ru_index, voices17, _ = client_events(client)
    by_idx = {l["idx"]: l for l in lines17}
    matched_voices = set()
    for scene in scenes:
        for line in scene["lines"]:
            idx = ru_index.get(norm_key(line["ru"])) if line["ru"] else None
            line["in_17"] = idx is not None
            if idx is not None:
                line["en"] = by_idx[idx]["en"]
                if by_idx[idx]["voice"]:
                    matched_voices.add(by_idx[idx]["voice"])
            if line.get("voice"):
                tail = line["voice"].split("/")[-1]
                for v in voices17:
                    if v.endswith("/" + tail) and v.split("/")[1].lower() in line["voice"].lower():
                        matched_voices.add(v)
        scene["voiced_lines"] = sum(1 for l in scene["lines"] if l.get("voice"))
        scene["subtitled_lines"] = sum(1 for l in scene["lines"] if l["ru"])
    # scènes « 17.0 seul » : répliques vocales Cutscenes/* qu'aucune scène 7.0 ne porte
    groups: dict[str, dict] = {}
    subtitle_by_voice = {l["voice"]: l for l in lines17 if l["voice"]}
    for v in voices17:
        if v in matched_voices:
            continue
        key = voice_scene_key(v)
        g = groups.setdefault(key, {"id": key, "source": "17.0 pack.bin", "map": None, "quest": None,
                                    "plotline": None, "arc": v.split("/")[1], "lines": []})
        sub = subtitle_by_voice.get(v)
        g["lines"].append({"voice": v, "ru": sub["ru"] if sub else "", "en": sub["en"] if sub else "",
                           "delay_ms": sub["delay_ms"] if sub else 0, "in_17": True})
    for scene in scenes:
        scene["faction"] = faction_of(scene)
    for g in groups.values():
        g["faction"] = "common"
        g["voiced_lines"] = len(g["lines"])
        g["subtitled_lines"] = sum(1 for l in g["lines"] if l["ru"])
    return scenes + sorted(groups.values(), key=lambda g: g["id"])


def summarize(scenes: list[dict]) -> dict:
    server = [s for s in scenes if s["source"] == "7.0 xdb"]
    client = [s for s in scenes if s["source"] != "7.0 xdb"]
    return {
        "scenes": len(scenes),
        "from_7_0_xdb": len(server),
        "only_17_0": len(client),
        "with_camera_track": sum(1 for s in server if s.get("camera_tracks")),
        "with_game_scene": sum(1 for s in server if s.get("game_scenes")),
        "lines": sum(len(s["lines"]) for s in scenes),
        "voiced_lines": sum(s["voiced_lines"] for s in scenes),
        "subtitled_lines": sum(s["subtitled_lines"] for s in scenes),
        "lines_still_in_17_0": sum(1 for s in scenes for l in s["lines"] if l.get("in_17")),
        "by_faction": dict(collections.Counter(s["faction"] for s in scenes)),
    }


# --- dernier client : ressources de mise en scène compilées (pack.bin) -----------------------------

# Fenêtre d'identifiants de ressources autour d'un buff de caméra : `pack.bin` range les ressources
# dossier par dossier, avec des identifiants consécutifs (le dossier `AO12_Prologue04` va de 507555 à
# 507582). Rattacher une réplique ou un PNJ à un buff par cette proximité est une **approximation**,
# signalée comme telle dans la sortie.
CLUSTER_WINDOW = 40


def client_scenes(client: Path) -> dict:
    """Inventaire du 17.0 seul : tous les `CameraTrackAction` (rangés par ressource de tête), les
    `GameViewScene`/`GameViewScript` reliés par `ShowSceneAction`, et, autour de chaque buff de
    caméra, les répliques (`ClientData` avec sous-titre ou voix) et les noms de PNJ voisins."""
    import bisect
    import numpy as np
    from tools.allods_packdb import open_pack
    from tools.allods_scenes import read_camera_track, read_client_line
    from tools.extract_cinematics import clean_text as _clean
    db = open_pack(client)
    with zipfile.ZipFile(Path(client) / "data/Packs/Texts_x64.pak") as z:
        ru = unpack_loc(z.read("Bin/pack.rus.loc"))
    rev = {v: k for k, v in db.ids.items()}
    mask = db.rkind == 0
    src, dst = db.rloc[mask], db.rtgt[mask]
    order = dst.argsort()
    ds, ss = dst[order], src[order]
    bounds = sorted(int(a) for a in db.vt_loc)

    def owner(a: int) -> int:
        return bounds[bisect.bisect_right(bounds, a) - 1]

    def referrers(t: int) -> list[int]:
        lo, hi = np.searchsorted(ds, t), np.searchsorted(ds, t, side="right")
        return [owner(int(x)) for x in ss[lo:hi]]

    def head(a: int, depth: int = 0) -> int:
        if a in rev or depth > 8:
            return a
        up = referrers(a)
        return head(up[0], depth + 1) if up else a

    by_head: dict[int, list] = collections.defaultdict(list)
    for a in db.structs("CameraTrackAction"):
        by_head[head(a)].append(read_camera_track(db, a))
    heads = collections.Counter(db.vtype(h) for h in by_head)
    buffs = []
    for h, tracks in sorted(by_head.items(), key=lambda kv: rev.get(kv[0], 0)):
        if db.vtype(h) != "BuffVisScripts":
            continue
        rid = rev[h]
        lines, mobs = [], []
        for k in range(rid - CLUSTER_WINDOW, rid + CLUSTER_WINDOW + 1):
            off = db.ids.get(k)
            if off is None:
                continue
            kind = db.vtype(off)
            if kind == "ClientData":
                try:
                    cl = read_client_line(db, off)
                except Exception:  # noqa: BLE001 — ClientData d'une autre forme
                    continue
                if cl.voice or cl.text_index is not None:
                    text = _clean(ru[cl.text_index]) if cl.text_index is not None and cl.text_index < len(ru) else ""
                    lines.append({"id": k, "voice": cl.voice, "ru": text[:120], "delay_ms": cl.delay_ms})
            elif kind == "MobWorld":
                n = db.u32(off + 0x68)
                if n < len(ru) and ru[n]:
                    mobs.append(_clean(ru[n]))
        buffs.append({"buff_vis_scripts": rid, "tracks": len(tracks),
                      "duration": round(sum(t.duration for t in tracks), 2),
                      "points": sum(len(t.points) for t in tracks),
                      "nearby_lines": lines, "nearby_mobs": sorted(set(mobs))})
    shows = []
    paths = {v: k for k, v in db.paths.items()}
    for a in db.structs("ShowSceneAction"):
        scene, script = db.ptr(a + 0x50), db.ptr(a + 0x58)
        entry = {"scene": rev.get(scene), "script": rev.get(script), "map": None, "mobs": []}
        if scene is not None:
            mp = db.ptr(scene + 0xE8)
            entry["map"] = paths.get(mp, "").split("/")[1] if mp in paths else None
            entry["mobs"] = [db.string(e + 0x80) for e in db.elements(scene + 0xA0, 192)]
        shows.append(entry)
    with_lines = [b for b in buffs if b["nearby_lines"]]
    return {
        "_note": ("Relevé du client 17.0 seul (tools/inventory_engine_cutscenes.py --client-only). "
                  "nearby_lines / nearby_mobs : ressources à ±40 identifiants du buff (même dossier "
                  "d'origine le plus souvent), rattachement approché. Les positions des PNJ et "
                  "l'enchaînement des répliques sont décidés par le serveur, absents du client."),
        "summary": {"camera_tracks": sum(len(v) for v in by_head.values()),
                    "camera_tracks_by_head": dict(heads),
                    "cutscene_buffs": len(buffs), "cutscene_buffs_with_lines": len(with_lines),
                    "game_view_scenes": len(db.resources("GameViewScene")),
                    "game_view_scripts": len(db.resources("GameViewScript")),
                    "show_scene_actions": len(shows),
                    "subtitle_resources": len(db.structs("UISubtitleShow")) + len(db.resources("UISubtitleShow"))},
        "cutscene_buffs": buffs,
        "show_scene_actions": shows,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--server-root", default=DEFAULT_SERVER)
    p.add_argument("--client", default=DEFAULT_CLIENT)
    p.add_argument("--hits", help="liste de fichiers xdb déjà repérés (un par ligne), évite le parcours")
    p.add_argument("--client-only", action="store_true", help="ne refait que le relevé du 17.0 (engine_cutscenes.client_17)")
    args = p.parse_args(argv)
    if args.client_only:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        engine = manifest.setdefault("engine_cutscenes", {})
        engine["client_17"] = client_scenes(Path(args.client))
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(json.dumps(engine["client_17"]["summary"], ensure_ascii=False, indent=1))
        return 0
    root = Path(args.server_root)
    hits = Path(args.hits).read_text().split("\n") if args.hits else find_markers(root)
    hits = [h for h in hits if h.strip()]
    scenes = build(root, Path(args.client), hits)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    engine = manifest.setdefault("engine_cutscenes", {})
    engine["summary"] = summarize(scenes)
    engine["scenes"] = scenes
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(engine["summary"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
