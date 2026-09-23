"""Décors de la création de personnage : la carte `MainMenu` du client 17.

Les objets de carte ne sont pas dans `pack.bin` mais dans une base par carte, `Bin/Maps_MainMenu.bin`
(pak `BaseLocall_x64.pak`), liée à `pack.bin` (`allods_packdb.open_map`). Elle contient les huit décors
de race (`World/MainMenu/Chargen_<Race>/…_Scene`), leurs objets accrochés, leurs lumières
(`ZoneLights`) et leurs ambiances.

Le décor est construit par la chaîne commune des cinématiques moteur
(`tools/extract_engine_cutscene.py` : `build_decor`, `light_decor`, `build_sky`, `build_terrain`,
`export_waves`), qui apporte l'éclairage précalculé de chaque objet (`lightvrt` : lumières
ponctuelles — lanternes, cristaux), les particules (feuilles qui tombent, lueurs), les animations
des gabarits, le ciel et les sons. Ce module n'ajoute que ce qui est propre à la création :

* la **place** du personnage et de la caméra (`UICharacterScenes`, `CharacterSelect<Race>`) ;
* l'**origine** de chaque décor : l'objet `World/MainMenu/Chargen_*` le plus proche de la place, dont
  l'estrade est à l'origine de la géométrie (celle des aèdes est 32 m sous la place de sélection) ;
* l'**éclairage de zone** de la place, lu dans la grille 16 × 16 de la région (`+0x160`) : les
  `ZoneLights` du menu portent un seul éclairage, en ligne à `+0x48` (mêmes champs que ceux de
  `allods_scenes.read_zone_light`), et leur `SkyMesh*` en `+0x150` ;
* l'**ambiance sonore** de la place, grille des `Sound2DTassel` (`+0xE0`, événement `+0x58`).
"""
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

from tools import allods_chargen as ac
from tools.allods_fx import ParticlePool
from tools.allods_gltf import BinSource, TexturePool, _slug
from tools.allods_packdb import PackDB, open_catalog, open_map, packs_path
from tools.allods_scenes import read_regions, static_visobject
from tools.allods_visdb import read_visobject

MAP = "MainMenu"
REGION = 256.0
REGION_ZONE_LIGHTS = 0x160
REGION_AMBIENCES = 0xE0
TASSEL_EVENT = 0x58          # Sound2DTassel : événement FMOD de l'ambiance
ZONE_ITEM = 0x48             # ZoneLights du menu : éclairage unique en ligne
ZONE_SKY = 0x150
PEDESTAL_TOP = 0.28          # dessus de l'estrade de `Chargen_Aed` (sommets à moins de 3 m de l'axe)
SCENE_RADIUS = 40.0          # rayon (m) autour du décor : le décor et ses voisins immédiats
# Lumières ponctuelles de la carte (lanternes, feux, cristaux) : leur couleur de zone vaut
# `0xFFFFFF` partout au menu, soit 2 en unités du jeu (0x80 = 1) — décor et personnages sortaient
# surexposés (statues de l'elfe 184/157/35 contre 133/94/48 à l'écran du 17.0). Ramenée à 1 : écart
# de calibrage mesuré, la formule de l'octet 2 (`vertex_light`) restant celle des cinématiques.
POINT_LIGHT_SCALE = 0.5
# Textures du décor : taille native (décision : pas de réduction, WebP).
DECOR_TEXTURE_MAX = 4096


class WebpTexturePool(TexturePool):
    """Textures en WebP à leur taille d'origine (décision de l'utilisateur, septembre 2026) :
    avec pertes (qualité 90) — alpha compris, gardé sans perte —, trois à cinq fois plus légères
    que le PNG. `three.js` (`GLTFLoader`) décode l'image par son contenu."""

    def _write(self, name: str, img: Image.Image, max_size: int) -> str:
        if max(img.size) > max_size:
            img = img.resize((min(img.width, max_size), min(img.height, max_size)), Image.LANCZOS)
        alpha = img.mode == "RGBA" and img.getextrema()[3][0] < 255
        file = f"{_slug(name)}{'' if max_size >= 1024 else f'@{max_size}'}.webp"
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / file
        self.has_alpha[name] = alpha
        if not alpha:
            img = img.convert("RGB")
        img.save(path, format="WEBP", quality=90, method=6, alpha_quality=100)
        self.bytes_written += path.stat().st_size
        return file


def scale_argb(value: int, k: float) -> int:
    a, r, g, b = (value >> 24) & 255, (value >> 16) & 255, (value >> 8) & 255, value & 255
    return (a << 24) | (min(255, round(r * k)) << 16) | (min(255, round(g * k)) << 8) | min(255, round(b * k))


def zone_lights_at(m: PackDB, pos, grid: int = REGION_ZONE_LIGHTS, reach: int = 0) -> int | None:
    """Objet de la grille 16 × 16 d'une région (lumières en `+0x160`, ambiances sonores en
    `+0xE0`) sous une position de la carte ; `reach` > 0 : à défaut, la case pleine la plus proche
    à moins de `reach` cases (la place de l'elfe est une case sous la zone `AI36` de son décor)."""
    rx, ry = int(pos[0] // REGION), int(pos[1] // REGION)
    a = m.paths.get(f"Maps/{MAP}/000_000/{rx}_{ry}_MapRegion.xdb")
    if a is None:
        return None
    cx, cy = int((pos[0] % REGION) // 16), int((pos[1] % REGION) // 16)
    rows = []
    for row in m.elements(a + grid, 32):   # cases vides comprises (`pointers` les sauterait)
        v = m.vec(row)
        rows.append([m.ptr(v[0] + 8 * k) for k in range(v[1] // 8)] if v else [])
    best = None
    for j, cells in enumerate(rows):
        for i, cell in enumerate(cells):
            d = max(abs(i - cx), abs(j - cy))
            if cell is not None and d <= reach and (best is None or d < best[0]):
                best = (d, cell)
    return best[1] if best else None


def zone_light(m: PackDB, zl: int) -> dict:
    """Éclairage d'une zone du menu, au format de `allods_scenes.read_zone_light` (couleurs ARGB,
    unité 0x80 = 1) : ambiante, diffuse (soleil), brouillard, lumière ponctuelle, auto-illumination,
    spéculaire, soleil (degrés), ciel."""
    e = zl + ZONE_ITEM
    sky = m.ptr(zl + ZONE_SKY)
    return {"ambient": m.u32(e + 0x24), "ambientFactor": round(m.f32(e + 0x28), 4),
            "diffuse": m.u32(e + 0x30), "fog": m.u32(e + 0x3C), "fogEnd": round(m.f32(e + 0x40), 3),
            "fogStart": round(m.f32(e + 0x44), 3), "pointLight": m.u32(e + 0x48),
            "selfIllum": m.u32(e + 0x4C), "specular": m.u32(e + 0x54),
            "sunPitch": round(m.f32(e + 0x5C), 3), "sunYaw": round(m.f32(e + 0x60), 3),
            "sky": sky if sky is not None and m.vtype(sky) == "SkyMesh" else None}


def scene_origin(mp: PackDB, cat, objects, place, radius: float = 10.0) -> tuple[float, float, float] | None:
    """Position de l'objet de décor de création le plus proche (horizontalement) de la place."""
    best = None
    for obj in objects:
        d = math.hypot(obj.position[0] - place[0], obj.position[1] - place[1])
        if d > radius or (best is not None and d >= best[0]):
            continue
        vot = static_visobject(mp, obj.static_object)
        if vot is None:
            continue
        vis = read_visobject(mp, cat, vot)
        name = cat.name(mp.binary_ref(vis.geometry)) if vis.geometry is not None else None
        if name and name.startswith("World/MainMenu/Chargen_"):
            best = (d, obj.position)
    return tuple(float(v) for v in best[1]) if best else None


def _tokens(name: str) -> list[str]:
    """`SteppeWindy_AP` → ['steppe', 'wind'] ; `DeathRealm` → ['death', 'realm']."""
    import re
    words = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", re.sub(r"_AP$", "", name))
    return [w.lower().rstrip("y") if len(w) > 4 else w.lower() for w in words]


def ambience_wave(event: str, index: dict) -> tuple[str, int, str] | None:
    """Onde d'une ambiance du menu, quand le nom de l'événement ne la donne pas (le projet d'événements
    FMOD des ambiances n'est pas livré, seules les banques le sont) : la **boucle** (`_lp`) des banques
    d'ambiance dont le nom contient tous les mots de l'événement — `SteppeWindy_AP` → `steppe_wind_lp`,
    `DeathRealm` → `DeathRealmAmbient_lp`. Sans correspondance complète, pas de son (pas d'invention)."""
    words = _tokens(event.split("/")[-1])
    if not words:
        return None
    best = None
    for key, hits in index.items():
        if not key.endswith("lp") or not all(w in key for w in words):
            continue
        for bank, sub, name in hits:
            if "Ambience" in bank or "Music_Zone" in bank:
                cand = (len(key), bank, sub, name)
                if best is None or cand < best:
                    best = cand
    return best[1:] if best else None


# Sons de l'interface de création (`SFX/Interface/Chargen.bsb`) : sélection de faction et de classe,
# répliques d'une combinaison race/classe (`ChargenLiga<Race><Classe>Male`, `ChargenImp…` : voix
# masculines seulement dans le client).
CHARGEN_RACE_TOKENS = {"Elf": "LigaElf", "Gibberling": "LigaGibb", "Kania": "LigaKania", "Hadagan": "ImpHadagan",
                       "Orc": "ImpOrc", "Undead": "ImpUndead"}


def chargen_sound_events(index: dict) -> dict[str, str]:
    """{clé du site: nom d'onde de `Chargen.bsb`} (`class:MAGE`, `faction`, `voice:Elf/MAGE`)."""
    names = {name for hits in index.values() for bank, _, name in hits if bank.endswith("Interface/Chargen.bsb")}
    out = {}
    for name in names:
        if name == "FactionSelect":
            out["faction"] = name
        elif name.startswith("ClassSelect"):
            out[f"class:{name[len('ClassSelect'):].upper()}"] = name
        elif name.startswith("Chargen") and name.endswith("Male"):
            core = name[len("Chargen"):-len("Male")]
            for race, token in CHARGEN_RACE_TOKENS.items():
                if core.startswith(token):
                    out[f"voice:{race}/{core[len(token):].upper()}"] = name
    return out


def export_scenes(ctx, races: list[str], race_scene: dict[str, str], vgmstream: Path | None = None) -> dict:
    """Décor commun (`maps/MainMenu/`) et, par race, `scenes/<Race>.json` (+ éclairage des sommets
    `scenes/<Race>-light.bin`, ciel `scenes/<Race>-sky.glb`), sons dans `sfx/`."""
    import tools.extract_engine_cutscene as eec
    from tools.extract_engine_cutscene import (
        DEFAULT_VGMSTREAM, build_decor, build_sky, export_waves, light_at, light_decor, map_sounds,
        rebase_objects, sun_direction,
    )
    # Réglages propres à la création, posés sur la chaîne commune le temps de l'extraction :
    # textures du décor à leur taille native (bornées à 512 pour les cinématiques) et feuillages
    # découpés par l'alpha de leur texture (`Exporter.cutout` : sans lui, les frondaisons
    # d'automne du décor elfe sortent en grands aplats rouges).
    import functools
    from tools.allods_gltf import Exporter
    eec.DECOR_TEXTURE_MAX = DECOR_TEXTURE_MAX
    eec.Exporter = functools.partial(Exporter, cutout=True)
    client = Path(ctx.cat.packs_dir).parent.parent
    mp = open_map(ctx.db, client, MAP)
    cat = open_catalog(mp, client)
    bins = BinSource([], [str(packs_path(client / "data" / "Packs") / "*.pak")])
    map_dir = ctx.out / "maps" / MAP
    for stale in ("textures", "particles"):
        shutil.rmtree(map_dir / stale, ignore_errors=True)
    map_dir.mkdir(parents=True, exist_ok=True)
    scenes_dir = ctx.out / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    for race in races:   # décor par race de l'ancien format (un .glb par race)
        (scenes_dir / f"{race}.glb").unlink(missing_ok=True)
    textures = WebpTexturePool(mp, cat, bins, map_dir)
    particles = ParticlePool(mp, cat, bins, map_dir)
    objects = read_regions(mp)
    places = {s.name: s for s in ac.character_scenes(ctx.db)}

    # Places et origines d'abord : le décor commun couvre les zones de **toutes** les races (même
    # avec `--only`, qui ne réécrit que les scènes demandées).
    plans: dict[str, dict] = {}
    for race in race_scene:
        place = places.get(race_scene.get(race, ""))
        if place is None:
            ctx.notes.append(f"décor : place absente pour {race}")
            continue
        P = np.array(place.character)
        decor_at = scene_origin(mp, cat, objects, P)
        origin = np.array(decor_at) if decor_at is not None else P
        plans[race] = {"place": place, "P": P, "origin": origin}
    report: list[str] = []
    areas = [([float(p["origin"][0]), float(p["origin"][1])], SCENE_RADIUS) for p in plans.values()]
    decor = build_decor(mp, cat, bins, textures, particles, MAP, areas, report)
    (map_dir / "decor.glb").write_bytes(decor["glb"])
    # Pas de sol de carte : chaque décor de création porte le sien ; celui de la carte, sous le
    # décor elfe, sortait sans texture (tache blanche à droite de l'estrade).
    terrain_glb = None
    (map_dir / "terrain.glb").unlink(missing_ok=True)
    prefix = f"maps/{MAP}/"
    objects_meta = rebase_objects(decor["objects"], prefix)

    # Sons : boucles des objets du décor et ambiance de chaque place.
    ambiences = {}
    for race, plan in plans.items():
        amb = zone_lights_at(mp, plan["place"].character, REGION_AMBIENCES, reach=2)
        if amb is not None and mp.vtype(amb) == "Sound2DTassel" and mp.string(amb + TASSEL_EVENT):
            ambiences[race] = mp.string(amb + TASSEL_EVENT)
    music = map_sounds(mp).get("music", [])
    index = eec.sound_index(bins, Path.home() / ".cache" / "allodex")
    ui_sounds = chargen_sound_events(index)
    events = set(decor["sounds"]) | set(ambiences.values()) | set(ui_sounds.values())
    tool = Path(vgmstream or DEFAULT_VGMSTREAM)
    # Ambiances : correspondance par les mots de l'événement quand son nom ne désigne pas l'onde.
    by_name = eec.find_wave
    eec.find_wave = lambda event, idx, prefer="": by_name(event, idx, prefer) or ambience_wave(event, idx)
    try:
        waves = export_waves(events, bins, ctx.out, tool, report) if tool.is_file() else {}
    finally:
        eec.find_wave = by_name
    if not tool.is_file():
        report.append(f"sons non exportés : vgmstream introuvable ({tool})")
    ctx.sounds = {key: waves[name]["file"] for key, name in sorted(ui_sounds.items()) if name in waves}
    for info in objects_meta.values():
        if info.get("sound") in waves:
            info["sfx"] = waves[info["sound"]]["file"]

    atlas = particles.write_atlas(textures)
    if atlas:
        atlas = {**atlas, "file": prefix + atlas["file"]}
    out: dict[str, dict] = {}
    for race, plan in plans.items():
        if race not in races:
            continue
        place, P, origin = plan["place"], plan["P"], plan["origin"]
        zl = zone_lights_at(mp, place.character)
        light = zone_light(mp, zl) if zl is not None and mp.vtype(zl) == "ZoneLights" else {}
        if light and POINT_LIGHT_SCALE != 1:
            light["pointLight"] = scale_argb(light["pointLight"], POINT_LIGHT_SCALE)
        instances, blob = light_decor(decor, light, [float(origin[0]), float(origin[1])], SCENE_RADIUS)
        (scenes_dir / f"{race}-light.bin").write_bytes(blob)
        sky_glb, sky = build_sky(mp, cat, bins, textures, light, f"../{prefix}textures/", report) if light.get("sky") else (None, None)
        if sky_glb:
            (scenes_dir / f"{race}-sky.glb").write_bytes(sky_glb)
        offset = P - origin
        # Le personnage se tient sur l'estrade : à sa place quand elle est sur le décor (sept
        # races, 0,2 à 0,4 m au-dessus de l'origine = dessus de l'estrade), sinon au centre de
        # l'estrade (aèdes : dessus mesuré à 0,28 m dans `Chargen_Aed`).
        stand = offset if np.linalg.norm(offset) < 2.0 else np.array([0.0, 0.0, PEDESTAL_TOP])
        zone = {k: v for k, v in light.items() if k not in ("sky", "skyGeometry", "skyParts")}
        meta: dict = {
            # Coordonnées de la carte ; le lecteur les ramène à l'origine du décor.
            "origin": [round(float(v), 4) for v in origin],
            "character": {"yaw": round(place.character_yaw, 3), "scale": round(place.character_scale, 3),
                          "position": [round(float(v), 3) for v in stand],
                          # Lumière du personnage (ambiante + ponctuelles de la carte à sa place, 1 = 0x80).
                          "light": light_at(list(origin + stand), decor["pointLights"], light) if light else None},
            "camera": {"position": [round(float(v), 4) for v in (np.array(place.camera) - P)],
                       "yaw": round(place.camera_yaw, 3), "pitch": round(place.camera_pitch, 3),
                       "height": round(place.camera_height, 3), "fov": round(place.fov, 4)},
            "decor": {"glb": prefix + "decor.glb", "light": f"scenes/{race}-light.bin", "instances": instances,
                      "sky": sky, "skyGlb": f"scenes/{race}-sky.glb" if sky_glb else None,
                      "terrainGlb": prefix + "terrain.glb" if terrain_glb else None},
            "objects": objects_meta,
            "particleAtlas": atlas,
            "light": {**zone, "sunDirection": [round(float(v), 4) for v in sun_direction(light)]} if light else {},
            "sounds": {"ambience": [waves[ambiences[race]]["file"]] if ambiences.get(race) in waves else [],
                       "events": {"ambience": ambiences.get(race), "music": music}},
            "source": {"scene": place.name, "map": place.map, "position": [round(float(v), 3) for v in P]},
        }
        (scenes_dir / f"{race}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        out[race] = {"file": f"scenes/{race}.json", "character": meta["character"], "camera": meta["camera"],
                     "instances": len(instances)}
        print(f"  décor {race:>10} : {len(instances)} objets, lumière {len(blob) // 4} sommets, "
              f"ciel {'oui' if sky_glb else 'non'}, ambiance {ambiences.get(race) or '—'}")
    report.append(f"textures du décor {textures.bytes_written / 1e6:.1f} Mo, particules {particles.bytes_written / 1e6:.2f} Mo, "
                  f"{len(waves)} sons")
    ctx.notes.extend(report)
    return out
