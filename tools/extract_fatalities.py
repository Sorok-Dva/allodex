#!/usr/bin/env python3
"""Export des fatalités d'Allods Online : personnages, effets, chronologies et sons.

Source : le **dernier client** (RU 17.x, `/mnt/h/MyGames/AllodsRU`). Il ne contient plus de
`.xdb` : tout ce que l'arbre serveur 7.0 décrivait en XML est compilé dans `Bin/pack.bin`,
relu par `tools/allods_packdb.py` et décodé par `tools/allods_visdb.py`. Chaîne de données
d'une fatalité (voir le README, § « Fatalités ») :

1. `Interface/System/SlonSettings.(SlonRoot)` → vecteur `fatalities` : 26 entrées
   `(type, offenderDeathScript, casterFxScript, fadeStartTime, fadeDuration, sparkDelay)` —
   10 de classe, 16 de boutique (Occultiste, Universelles, Exécuteurs, Lotus, Phénix…) ;
2. `offenderDeathScript` : arbre de `VisAction` joué sur la victime, aplati par
   `tools/fatality_script.py` en chronologie par personnage (animations et vitesses, échelle,
   transparence, objets posés et accrochés, secousses) ;
3. chaque objet posé est un `VisObjectTemplate` : géométrie skinnée + animation (+ système
   de particules), composants accrochés à ses locators, son (événement FMOD dont l'onde porte
   le même nom dans `SFX/Spells/Fatality*.bsb`).

Sorties (`public/game/fatalities/`) :

* `characters/<id>.glb` — squelette et clips d'un personnage (`Idle01` et toutes les animations
  que les scripts de la victime et du tueur demandent), sans maillage : le lecteur les joue sur
  les modèles habillés de la création de personnage (`public/game/character/`) ;
* `fx/<id>.glb` — les gabarits d'objets d'une fatalité, un nœud `vot:<nom>` chacun, avec
  leur squelette, leur clip et leurs composants accrochés ; textures communes dans `textures/` ;
* `sfx/<nom>.ogg|.mp3` — les ondes des fatalités ;
* `fatalities.json` — index : personnages, fatalités, chronologies par personnage (victime et
  tueur : `casterFxScript`, effets et rayons), gabarits ;
* `scene/scene.glb` — le décor (terrain, ornements, ciel des Prés bénis).

Le repère du jeu (main gauche, Z en haut) est conservé dans les `.glb` : le lecteur les place
sous un nœud miroir unique.

Usage : python3 tools/extract_fatalities.py [--only-fx phoenix] [--only kania-male]
        [--client /mnt/h/MyGames/AllodsRU] [--no-characters] [--no-sounds]
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import shutil
import struct
import sys
import tempfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.allods_characters import find_character_template, read_character_template  # noqa: E402
from tools.allods_packdb import PackDB, PakCatalog, open_catalog, open_pack, packs_path  # noqa: E402
from tools.allods_visdb import (  # noqa: E402
    GeometryInfo, VisObject, animation_names, read_fatalities, read_geometry, read_texture,
    read_visobject,
)
from tools import extract_menu_scene as _ems  # noqa: E402
from tools.extract_menu_scene import (  # noqa: E402
    BLOCK_BYTES, FOURCC, BinSource, GeometryDoc, GltfBuilder, Skeleton, SkeletalAnimation,
    decode_vertex_buffer, parse_skeletal_animation, parse_skeleton, read_chunks, rest_local,
    rest_world_matrices, skin_attributes, validate_glb,
)
from tools.fatality_script import flatten  # noqa: E402
from tools.scenes.v5_0 import restore_fixed_rotations  # noqa: E402
from tools.scenes.v8_0 import restore_static_binds  # noqa: E402
from tools.uitexture import build_dds  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE / "fatalities_manifest.json"
DEFAULT_OUT = HERE.parent / "public" / "game" / "fatalities"

# Côté maximal des textures exportées : 512 pour les effets (quads additifs flous, jamais vus de
# près), 1024 pour les peaux des personnages. Écart assumé pour le poids du site (les sources
# montent à 2048).
FX_TEXTURE_MAX = 512
CHARACTER_TEXTURE_MAX = 1024

# Animation d'attente des personnages (le client joue `idle` via ses gabarits d'animation ;
# `Idle01` est la première variante présente pour les seize personnages).
IDLE_ANIMATION = "Idle01"


# --- textures, glTF, chargement : tools/allods_gltf.py (partagé avec la création de personnage
# et les cinématiques moteur) ---------------------------------------------------------------------

from tools.allods_gltf import (  # noqa: E402,F401
    Exporter, Loaded, MAX_KEY_GAP, ROTATION_TOLERANCE, TRANSLATION_TOLERANCE, TexturePool, _slug,
    bind_pose_positions, clean_animation, infer_texture_dims, is_soft_geometry, load_animation, load_geometry,
    reduce_keys,
)


# --- personnages -------------------------------------------------------------------------------

def _read_xml(path: Path) -> ET.Element | None:
    try:
        return ET.fromstring(path.read_text(errors="replace"))
    except (OSError, ET.ParseError):
        return None


def _href(node: ET.Element | None) -> str | None:
    href = node.get("href") if node is not None else None
    return href.split("#")[0] if href else None


def build_character(spec: dict, db: PackDB, cat: PakCatalog, bins: BinSource, textures: TexturePool,
                    wanted: set[str]) -> tuple[bytes, dict, list[str]]:
    """**Animations** d'un personnage jouable : son squelette et les clips demandés (`Idle01`,
    animations des scripts de la victime et du tueur), sans maillage. Le personnage lui-même,
    habillé de la tenue de sa classe, vient des modèles de la création de personnage
    (`public/game/character/models/<Gabarit>.glb`, `tools/extract_character_creation.py`) : même
    squelette, mêmes noms d'articulations (`<Gabarit>/<Articulation>`), les clips s'y lient tels
    quels. L'apparence du client reste décrite par `tools/allods_characters.py`."""
    exporter = Exporter(textures, CHARACTER_TEXTURE_MAX)
    off = find_character_template(db, cat, spec["model"], spec["dir"])
    if off is None:
        raise ValueError(f"gabarit introuvable : {spec['model']}")
    template = read_character_template(db, cat, off)
    if template.gender != spec["sex"]:
        raise ValueError(f"{spec['id']} : le gabarit est {template.gender}")
    vot = read_visobject(db, cat, template.visobject)
    loaded = load_geometry(db, cat, bins, vot.geometry) if vot.geometry is not None else None
    if loaded is None or loaded.skeleton is None:
        raise ValueError(f"géométrie ou squelette illisible : {spec['model']}")
    skeleton = loaded.skeleton
    joint_nodes = exporter.emit_skeleton(skeleton, spec["model"])
    roots = [joint_nodes[i] for i in range(len(skeleton)) if not (0 <= skeleton.parents[i] < len(skeleton))]
    span = float(np.max(np.abs(loaded.vertices["position"])) * 4.0)
    durations: dict[str, float] = {}
    for anim in sorted(wanted | {IDLE_ANIMATION}):
        file = animation_file(cat, spec, anim)
        animation = load_animation(bins, file, skeleton, span)
        if animation is None:
            exporter.notes.append(f"{spec['id']} : animation absente {anim}")
            continue
        durations[anim] = round(exporter.emit_clip(anim, skeleton, joint_nodes, animation), 4)
    root = exporter.gltf.add_node({"name": spec["model"], "children": roots,
                                   **({"scale": [vot.scale] * 3} if abs(vot.scale - 1) > 1e-6 else {})})
    glb = exporter.finish([root])
    height = float(loaded.vertices["position"][:, 2].max() * vot.scale)
    meta = {"id": spec["id"], "race": spec["race"], "sex": spec["sex"], "model": spec["model"],
            "glb": f"characters/{spec['id']}.glb", "scale": vot.scale, "height": round(height, 3),
            "animations": sorted(durations), "durations": durations, "stats": exporter.stats}
    return glb, meta, exporter.notes


def animation_file(cat: PakCatalog, spec: dict, anim: str) -> str | None:
    """Fichier d'une animation du personnage : `<Modèle>.<Nom>` sans égard à la casse."""
    prefix = f"Characters/{spec['dir']}/Animations/{spec['model']}.".lower()
    target = f"{prefix}{anim.lower()}.(skeletalanimation).bin"
    for pak in ("Characters.Mini.pak",):
        for name in cat.names.get(pak, []):
            if name.lower() == target:
                return name
    return None


# --- effets, particules, sons : tools/allods_fx.py (partagé avec les cinématiques moteur) -------

from tools.allods_fx import (  # noqa: E402,F401
    PARTICLE_ATLAS_WIDTH, SOUND_BANKS, FxBuild, ParticlePool, _qmul, _rotate, _sound_key, export_sounds,
)


# --- décor -------------------------------------------------------------------------------------

# Convention des couleurs du jeu (lumières de zone comme couleurs de sommets) : 0x80 = 1.
GAME_COLOR_UNIT = 128.0


def _rgb(value: int) -> list[float]:
    return [round(((value >> 16) & 255) / GAME_COLOR_UNIT, 4), round(((value >> 8) & 255) / GAME_COLOR_UNIT, 4),
            round((value & 255) / GAME_COLOR_UNIT, 4)]


def zone_light(server_root: Path, path: str, time: float) -> dict | None:
    """Lumière d'une zone à une heure donnée (`ZoneLights` de l'arbre serveur 7.0 : le
    `ZoneLights` compilé du client n'est pas encore décodé)."""
    root = _read_xml(server_root / path)
    if root is None:
        return None
    chosen = None
    for item in root.findall("instantLights/Item"):
        if abs(float(item.findtext("time") or "-1") - time) < 1e-6:
            chosen = item.find("light")
    if chosen is None:
        chosen = root.find("defaultLight/light")
    if chosen is None:
        return None

    def num(tag: str, default: float = 0.0) -> float:
        return float(chosen.findtext(tag) or default)

    def color(tag: str) -> int:
        return int(float(chosen.findtext(tag) or "0")) & 0xFFFFFF

    yaw, pitch = math.radians(num("SunLightYaw", 45)), math.radians(num("SunLightPitch", 45))
    return {
        "ambient": _rgb(color("AmbientColor")), "ambientFactor": num("AmbientFactor", 0.5),
        "sun": _rgb(color("DiffuseColor")),
        "sunDirection": [round(math.cos(pitch) * math.cos(yaw), 4), round(math.cos(pitch) * math.sin(yaw), 4),
                         round(math.sin(pitch), 4)],
        "fog": {"color": _rgb(color("FogColor")), "near": num("FogStart", 100), "far": num("FogEnd", 500)},
    }


# Terrain : sous-carreaux de 8 m au niveau de détail fin jusqu'à `TERRAIN_FINE` m du centre, puis
# grossier jusqu'au rayon du manifeste (le brouillard du jeu commence à 80 m).
TERRAIN_FINE = 90.0
# Rayon de l'herbe autour du centre (m) : la caméra orbite près de la victime et l'herbe se dissout
# à 70 m de la caméra (`GRASS_FADE_FAR` du lecteur).
GRASS_RADIUS = 110.0


def terrain_ground(ex: Exporter, spec: dict, db: PackDB, client: Path, trample: dict | None) -> tuple[list[int], object]:
    """Sol réel d'un coin de carte (`tools/allods_terrain.py`, `terrainDump` de 17.0, hauteurs
    vérifiées sur 7.0) centré sur `spec.center` : nœuds glTF (un primitif par calque, marqués
    `ground`) et fonction de hauteur `z(x, y)` du sol dans le repère du décor (centre à z = 0).
    Chaque sous-carreau prend le premier calque de sa première passe (le mélange du `SplatMap`
    n'est pas élucidé) ; la tache de terre battue (`trample`) est redessinée par-dessus le terrain
    au centre, son bord estompé par l'alpha des sommets."""
    from tools.allods_packdb import open_map
    from tools.allods_scenes import region_origin
    from tools.allods_terrain import region_patches, terrain_layers
    mp = open_map(db, client, spec["map"])
    cat = open_catalog(mp, client)
    packs = packs_path(client / "data" / "Packs")
    bins = BinSource([], [str(packs / f"{spec['map']}_000_000_512_512.Client.pak")])
    cx, cy = spec["center"]
    radius = float(spec.get("radius", 300.0))
    groups: dict[str, list] = {}
    grid: dict[tuple[int, int], float] = {}
    regions: list = []
    for path, region in sorted(mp.paths.items()):
        if not path.endswith("_MapRegion.xdb"):
            continue
        ox, oy = region_origin(path)
        if not (ox - radius <= cx <= ox + 256 + radius and oy - radius <= cy <= oy + 256 + radius):
            continue
        parsed = region_patches(bins.get, spec["map"], path)
        if parsed is None:
            continue
        layer_sets, patches = parsed
        layers = terrain_layers(mp, cat, mp.ptr(region + 0x98))
        regions.append((path, mp.ptr(region + 0x98), (ox, oy), patches))
        for patch in patches:
            if patch.level:
                continue
            d = math.hypot(ox + 8 * patch.sx + 4 - cx, oy + 8 * patch.sy + 4 - cy)
            if d > radius:
                continue
            ids = layer_sets[patch.passes[0][1]] if patch.passes and patch.passes[0][1] < len(layer_sets) else ()
            layer = layers[ids[0]] if ids and ids[0] < len(layers) else (None, 30.0)
            pts = patch.points + np.array([ox - cx, oy - cy, 0.0])
            tris = patch.triangles if d <= TERRAIN_FINE or not len(patch.coarse) else patch.coarse
            groups.setdefault(layer[0] or "", []).append((pts, patch.normals, tris, layer[1], d))
            for x, y, z in pts:
                grid[(round(x), round(y))] = float(z)
    if not grid:
        raise ValueError(f"terrain introuvable : {spec['map']} {spec['center']}")
    base = grid.get((0, 0), 0.0)

    def height(x: float, y: float) -> float:
        # Grille des sommets au mètre (maillage adaptatif) : le plus proche dans un rayon de 8 m.
        for r in range(0, 9):
            best = [grid[(round(x) + i, round(y) + j)] for i in range(-r, r + 1) for j in range(-r, r + 1)
                    if (round(x) + i, round(y) + j) in grid]
            if best:
                return float(np.mean(best)) - base
        return 0.0

    nodes: list[int] = []

    def emit(name: str, parts: list, texture: str | None, fade: float | None) -> None:
        pos, nor, uv, idx, rgba, count = [], [], [], [], [], 0
        for pts, normals, tris, tiling, _d in parts:
            p = pts - np.array([0.0, 0.0, base])
            # Couleurs de sommet toujours présentes (le lecteur multiplie par elles) : blanc, et
            # l'alpha du bord estompé pour la tache de terre battue.
            a = np.ones(len(p))
            if fade is not None:
                p = p + np.array([0.0, 0.0, 0.02])
                dist = np.linalg.norm(p[:, :2], axis=1)
                a = np.clip((trample["radius"] - dist) / max(trample["radius"] - fade, 1e-3), 0, 1)
            rgba.append(np.column_stack([np.full((len(p), 3), 255), np.round(a * 255)]).astype(np.uint8))
            pos.append(p.astype(np.float32))
            nor.append(normals.astype(np.float32))
            uv.append((pts[:, :2] / tiling).astype(np.float32))
            idx.append((tris + count).astype(np.uint32))
            count += len(p)
        tex = ex.texture(texture) if texture else None
        mat = ex.gltf.add_material(name, tex, "BLEND" if fade is not None else "OPAQUE", True, False)
        ex.gltf.json["materials"][mat].setdefault("extras", {}).update({"lit": True, "terrain": True})
        attrs = {"POSITION": ex.gltf.add_accessor(np.concatenate(pos), "VEC3", "f32", target=34962, minmax=True),
                 "NORMAL": ex.gltf.add_accessor(np.concatenate(nor), "VEC3", "f32", target=34962),
                 "TEXCOORD_0": ex.gltf.add_accessor(np.concatenate(uv), "VEC2", "f32", target=34962)}
        if rgba:
            attrs["COLOR_0"] = ex.gltf.add_accessor(np.concatenate(rgba), "VEC4", "u8", normalized=True, target=34962)
        ex.gltf.json["meshes"].append({"name": name, "primitives": [{
            "attributes": attrs, "indices": ex.gltf.add_accessor(np.concatenate(idx).reshape(-1), "SCALAR", "u32", target=34963),
            "mode": 4, "material": mat}]})
        nodes.append(ex.gltf.add_node({"name": name, "mesh": len(ex.gltf.json["meshes"]) - 1, "extras": {"ground": True}}))

    for layer, parts in sorted(groups.items()):
        emit(f"ground {Path(layer).stem if layer else 'nu'}", parts, layer or None, None)
    if trample:
        near = [(pts, n, t, trample.get("tile", 4.0), d) for parts in groups.values() for pts, n, t, _tl, d in parts
                if d <= trample["radius"] + 8]
        emit("ground_patch", near, trample["texture"], trample["radius"] * 0.45)
    # Herbe (autour du centre : l'orbite de la caméra y reste) et eau du `terrainDump`, sans lumière
    # cuite (le sol des fatalités est éclairé par la lumière de la zone).
    from tools.allods_terrain_extras import ExtrasBuilder
    extras = ExtrasBuilder(mp, cat, ex.textures, lambda name, size: ex.textures.uri(name, size, ex.texture_prefix))
    grass_radius = min(radius, float(spec.get("grass_radius", GRASS_RADIUS)))
    for path, terra, origin, patches in regions:
        extras.add_region(bins.get, path, terra, origin, patches,
                          lambda x, y: math.hypot(x - cx, y - cy) <= grass_radius, shift=(-cx, -cy, -base),
                          keep_water=lambda x, y: math.hypot(x - cx, y - cy) <= radius)
    nodes += extras.emit(ex)
    ex.notes.append(f"sol : {sum(len(v) for v in groups.values())} sous-carreaux, {len(groups)} calques ({spec['map']}), "
                    f"{extras.tufts} touffes d'herbe ({len(extras.kinds)} sortes), {extras.water_elements // 64} carrés d'eau")
    return nodes, height


def build_scene(spec: dict, db: PackDB, cat: PakCatalog, bins: BinSource, textures: TexturePool,
                server_root: Path, client: Path | None = None) -> tuple[bytes, dict, list[str]]:
    """Petit décor : sol réel d'un coin des Prés bénis (`scene.terrain` : carte, centre), à
    défaut un disque texturé ; ornements (arbres, rochers, buissons de la zone, à leur pose de
    bind, posés sur le sol) ; dôme de ciel du client. Tout vient du client ; seule la disposition
    des ornements (manifeste, `scene.props`) est une mise en scène."""
    ex = Exporter(textures, CHARACTER_TEXTURE_MAX, cutout=True)
    roots: list[int] = []
    geometries: dict[str, int] = {}
    for off in db.resources("Geometry"):
        name = cat.name(db.binary_ref(off))
        if name:
            geometries.setdefault(name, off)

    # Sol : disque maillé en anneaux, UV répétées tous les `tile` mètres, et une tache de terre
    # battue au centre dont le bord s'estompe (alpha de sommet).
    ground = spec["ground"]

    def disc(radius: float, tile: float, texture: str, fade: float | None, z: float, name: str) -> int | None:
        rings, sectors = 24, 64
        pts = [(0.0, 0.0)]
        for i in range(1, rings + 1):
            r = radius * (i / rings) ** 1.5
            for j in range(sectors):
                a = 2 * math.pi * j / sectors
                pts.append((r * math.cos(a), r * math.sin(a)))
        pos = np.array([[x, y, z] for x, y in pts], np.float32)
        uv = (pos[:, :2] / tile).astype(np.float32)
        dist = np.linalg.norm(pos[:, :2], axis=1)
        alpha = np.ones(len(pos)) if fade is None else np.clip((radius - dist) / max(radius - fade, 1e-3), 0, 1)
        rgba = np.column_stack([np.full((len(pos), 3), 255), np.round(alpha * 255)]).astype(np.uint8)
        tris = []
        for j in range(sectors):
            tris += [0, 1 + j, 1 + (j + 1) % sectors]
        for i in range(rings - 1):
            a0, b0 = 1 + i * sectors, 1 + (i + 1) * sectors
            for j in range(sectors):
                j1 = (j + 1) % sectors
                tris += [a0 + j, b0 + j, b0 + j1, a0 + j, b0 + j1, a0 + j1]
        tex = ex.texture(texture)
        mat = ex.gltf.add_material(name, tex, "BLEND" if fade is not None else "OPAQUE", True, False)
        ex.gltf.json["materials"][mat].setdefault("extras", {})["lit"] = True
        attrs = {"POSITION": ex.gltf.add_accessor(pos, "VEC3", "f32", target=34962, minmax=True),
                 "TEXCOORD_0": ex.gltf.add_accessor(uv, "VEC2", "f32", target=34962),
                 "NORMAL": ex.gltf.add_accessor(np.tile([0, 0, 1], (len(pos), 1)).astype(np.float32), "VEC3", "f32", target=34962),
                 "COLOR_0": ex.gltf.add_accessor(rgba, "VEC4", "u8", normalized=True, target=34962)}
        idx = ex.gltf.add_accessor(np.array(tris, np.uint32), "SCALAR", "u32", target=34963)
        ex.gltf.json["meshes"].append({"name": name, "primitives": [{"attributes": attrs, "indices": idx, "material": mat, "mode": 4}]})
        return ex.gltf.add_node({"name": name, "mesh": len(ex.gltf.json["meshes"]) - 1})

    height = lambda x, y: 0.0  # noqa: E731
    if spec.get("terrain") and client is not None:
        nodes, height = terrain_ground(ex, spec["terrain"], db, client, ground.get("patch"))
        roots.extend(nodes)
    else:
        roots.append(disc(ground["radius"], ground["tile"], ground["texture"], None, 0.0, "ground"))
        if ground.get("patch"):
            patch = ground["patch"]
            roots.append(disc(patch["radius"], patch.get("tile", ground["tile"]), patch["texture"], patch["radius"] * 0.45,
                              0.01, "ground_patch"))

    def static_object(name: str, off: int) -> int | None:
        loaded = load_geometry(db, cat, bins, off)
        if loaded is None:
            ex.notes.append(f"décor illisible : {name}")
            return None
        vertices = dict(loaded.vertices)
        if loaded.skeleton is not None and "indices" in vertices and "weights" in vertices:
            static = np.zeros(len(vertices["position"]), bool)
            for e in loaded.geo.doc.elements:
                if e.skin_index < 0:
                    static[np.unique(loaded.indices[e.ib0:e.ib1])] = True
            vertices["position"] = bind_pose_positions(vertices, loaded.skeleton, static)
        # Éléments sans texture lisible écartés (calques d'effet du ciel en L8 ou absents).
        elements = [e for e in loaded.geo.doc.elements if e.material.visible and e.material.texture
                    and ex.texture(e.material.texture) is not None]
        mesh, _ = ex.emit_mesh(Path(name).stem, loaded.geo, vertices, loaded.indices, elements, None)
        return None if mesh is None else ex.gltf.add_node({"name": Path(name).stem, "mesh": mesh})

    for prop in spec.get("props", []):
        off = geometries.get(prop["geometry"])
        if off is None:
            ex.notes.append(f"décor absent du client : {prop['geometry']}")
            continue
        child = static_object(prop["geometry"], off)
        if child is None:
            continue
        x, y = prop["at"]
        yaw = math.radians(prop.get("yaw", 0.0))
        holder = {"name": f"prop:{Path(prop['geometry']).stem}", "children": [child],
                  # Enfoncé de 10 cm : le pied des troncs épouse la pente.
                  "translation": [float(x), float(y), round(height(x, y) - 0.1, 3)],
                  "rotation": [0.0, 0.0, math.sin(yaw / 2), math.cos(yaw / 2)]}
        if abs(prop.get("scale", 1.0) - 1) > 1e-6:
            holder["scale"] = [float(prop["scale"])] * 3
        roots.append(ex.gltf.add_node(holder))

    # Ciel : les géométries des parties du `SkyMesh` choisi (dômes centrés sur la caméra).
    sky_nodes: list[int] = []
    sky_name = spec.get("sky")
    if sky_name:
        for sky in db.resources("SkyMesh"):
            parts = []
            for loc, kind, target in db.relocs(sky, sky + 0x60):
                if kind != 3:
                    continue
                size = db.u32(loc + 8)
                for l2, k2, t2 in db.relocs(target, target + size):
                    if k2 == 0 and db.vtype(t2) == "Geometry":
                        parts.append(t2)
            names = [cat.name(db.binary_ref(p)) or "" for p in parts]
            if names and sky_name in names[0]:
                for p, n in zip(parts, names):
                    child = static_object(n, p)
                    if child is not None:
                        ex.gltf.json["nodes"][child]["extras"] = {"sky": True}
                        sky_nodes.append(child)
                break
    if sky_nodes:
        roots.append(ex.gltf.add_node({"name": "sky", "children": sky_nodes, "extras": {"sky": True}}))
    glb = ex.finish([r for r in roots if r is not None])
    light = zone_light(server_root, spec["zoneLights"], spec.get("time", 12)) if spec.get("zoneLights") else None
    meta = {"glb": "scene/scene.glb", "label": spec.get("label")}
    if light:
        meta["environment"] = light
    return glb, meta, ex.notes


# --- index -------------------------------------------------------------------------------------

def collect_vots(node: dict | None, out: set[int]) -> None:
    if not node:
        return
    if node.get("visObject") is not None:
        out.add(node["visObject"])
    for effect in node.get("effects", []):
        if effect.get("visObject") is not None:
            out.add(effect["visObject"])
    for child in node.get("elements", []):
        collect_vots(child, out)
    collect_vots(node.get("playWhile"), out)


def collect_animations(node: dict | None, names: dict[int, str], out: set[str]) -> None:
    if not node:
        return
    if node.get("type") == "CreatureAnimationAction":
        for idx in node.get("animations", []):
            name = names.get(idx)
            if name:
                out.add(name[:1].upper() + name[1:])
    for child in node.get("elements", []):
        collect_animations(child, names, out)
    collect_animations(node.get("playWhile"), names, out)


def run(manifest: dict, out_dir: Path, client: Path, only: list[str] | None = None,
        only_fx: list[str] | None = None, characters: bool = True, sounds: bool = True,
        report: list[str] | None = None, scene: bool = True) -> dict:
    report = report if report is not None else []
    server_root = Path(manifest["server_root"])
    db = open_pack(client)
    cat = open_catalog(db, client)
    packs = packs_path(client / "data" / "Packs")
    bins = BinSource([], [str(packs / p) for p in sorted(cat.names)])
    textures = TexturePool(db, cat, bins, out_dir)
    particles = ParticlePool(db, cat, bins, out_dir)
    schema = {int(k): v for k, v in manifest.get("animation_enum", {}).items()}
    anim_names = animation_names(db, schema or None)
    fatalities = read_fatalities(db)
    by_type = {f["type"]: f for f in manifest["fatalities"]}

    # Animations demandées par les scripts (noms de fichiers : initiale en majuscule).
    wanted: set[str] = set()
    for fd in fatalities:
        collect_animations(fd.offender, anim_names, wanted)
        collect_animations(fd.caster, anim_names, wanted)

    index_path = out_dir / "fatalities.json"
    previous = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else {}
    prev_chars = {c["id"]: c for c in previous.get("characters", [])}
    if only_fx:
        particles.seed(previous.get("particleAtlas"))

    chars: list[dict] = []
    for spec in manifest["characters"]:
        if not characters or (only and spec["id"] not in only):
            if spec["id"] in prev_chars:
                chars.append(prev_chars[spec["id"]])
            continue
        try:
            glb, meta, notes = build_character(spec, db, cat, bins, textures, wanted)
        except (ValueError, struct.error) as error:
            report.append(f"AVERTISSEMENT : {spec['id']} — {error}")
            if spec["id"] in prev_chars:
                chars.append(prev_chars[spec["id"]])
            continue
        (out_dir / "characters").mkdir(parents=True, exist_ok=True)
        (out_dir / "characters" / f"{spec['id']}.glb").write_bytes(glb)
        report.extend(f"AVERTISSEMENT : {n}" for n in notes)
        print(f"{spec['id']:>18}  {len(glb) / 1024:.0f} Kio  {meta['stats']['triangles']} triangles, "
              f"{len(meta['animations'])} animations")
        meta.pop("stats", None)
        chars.append(meta)
    templates = {c["id"]: c["model"] for c in chars}

    prev_fx = {f["id"]: f for f in previous.get("fatalities", [])}
    entries: list[dict] = []
    all_sounds: set[str] = set()
    for fd in fatalities:
        spec = by_type.get(fd.type)
        if spec is None:
            report.append(f"AVERTISSEMENT : fatalité de type {fd.type} absente du manifeste")
            continue
        if only_fx and spec["id"] not in only_fx:
            if spec["id"] in prev_fx:
                entries.append(prev_fx[spec["id"]])
            continue
        build = FxBuild(Exporter(textures, FX_TEXTURE_MAX), db, cat, bins, particles=particles, report=report)
        roots: set[int] = set()
        collect_vots(fd.offender, roots)
        collect_vots(fd.caster, roots)
        for off in sorted(roots):
            node = build.emit(off)
            if node is not None:
                build.roots.append(node)
        entry = {"id": spec["id"], "type": fd.type, "kind": spec["kind"], "label": spec["label"],
                 "fadeStart": round(fd.fade_start, 4), "fadeDuration": round(fd.fade_duration, 4),
                 "sparkDelay": round(fd.spark_delay, 4)}
        if "note" in spec:
            entry["note"] = spec["note"]
        if build.roots:
            glb = build.exporter.finish(build.roots)
            (out_dir / "fx").mkdir(parents=True, exist_ok=True)
            (out_dir / "fx" / f"{spec['id']}.glb").write_bytes(glb)
            entry["fx"] = f"fx/{spec['id']}.glb"
            print(f"{spec['id']:>18}  fx {len(glb) / 1024:.0f} Kio  {len(build.meta)} gabarits, "
                  f"{build.exporter.stats['triangles']} triangles")
        report.extend(f"AVERTISSEMENT : {spec['id']} — {n}" for n in build.exporter.notes)
        entry["objects"] = build.meta
        all_sounds |= build.sounds
        timelines: dict[str, dict] = {}
        for char in chars:
            tl = flatten(fd.offender, templates.get(char["id"], ""), _lower_keys(char.get("durations", {})),
                         {k: v for k, v in anim_names.items()})
            bound_loops(tl, fd.fade_start + fd.fade_duration)
            timelines[char["id"]] = timeline_json(tl, build, anim_names)
            ctl = flatten(fd.caster, templates.get(char["id"], ""), _lower_keys(char.get("durations", {})),
                          dict(anim_names))
            timelines[char["id"]]["caster"] = caster_json(ctl, build, fd.fade_start + fd.fade_duration)
        entry["timelines"] = timelines
        entries.append(entry)

    sound_files: dict[str, str] = {}
    if sounds and all_sounds:
        from tools.extract_audio import DEFAULT_VGMSTREAM
        vgm = Path(os.environ.get("VGMSTREAM", DEFAULT_VGMSTREAM))
        if vgm.exists():
            sound_files = export_sounds(all_sounds, bins, out_dir, vgm, report)
        else:
            report.append(f"AVERTISSEMENT : vgmstream absent ({vgm}), sons non exportés")
    for entry in entries:
        for info in entry.get("objects", {}).values():
            if info.get("sound") in sound_files:
                info["sfx"] = sound_files[info["sound"]]

    index = {"races": manifest["races"], "characters": chars, "fatalities": entries}
    if manifest.get("scene") and scene:
        glb, meta, notes = build_scene(manifest["scene"], db, cat, bins, textures, server_root, client)
        (out_dir / "scene").mkdir(parents=True, exist_ok=True)
        (out_dir / "scene" / "scene.glb").write_bytes(glb)
        report.extend(f"AVERTISSEMENT : décor — {n}" for n in notes)
        print(f"décor : {len(glb) / 1024:.0f} Kio")
        index["scene"] = meta
    elif previous.get("scene"):
        index["scene"] = previous["scene"]
    atlas = particles.write_atlas(textures)
    if atlas is not None:
        index["particleAtlas"] = atlas
    elif previous.get("particleAtlas"):
        index["particleAtlas"] = previous["particleAtlas"]
    print(f"particules : {particles.bytes_written / 1024:.0f} Kio écrits")
    out_dir.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"textures : {textures.bytes_written / 1024:.0f} Kio écrits")
    return index


def bound_loops(tl, fade_end: float) -> None:
    """Une animation en boucle sans borne (`Stun` de l'Avatar, d'Avril 2024…) dure jusqu'à ce
    que la victime ait disparu : le fondu de fin (`fadeStartTime + fadeDuration`) l'efface, le
    client n'a plus rien à montrer ensuite."""
    from tools.fatality_script import UNBOUNDED_LOOP
    for step in tl.victim:
        if step["mode"] == "LOOP" and step["end"] - step["t"] >= UNBOUNDED_LOOP - 1e-6:
            step["end"] = round(max(step["t"], fade_end), 4)
    tl.end = max([s["end"] for s in tl.victim] + [0.0])


def _lower_keys(durations: dict[str, float]) -> dict[str, float]:
    """Durées indexées par nom d'énumération (`deathFatalityBard`) à partir des noms de clips."""
    return {k[:1].lower() + k[1:]: v for k, v in durations.items()}


def timeline_json(tl, build: FxBuild, anim_names: dict[int, str]) -> dict:
    def clip(name: str | None) -> str | None:
        return None if not name else name[:1].upper() + name[1:]

    out = {
        "end": round(tl.end, 4),
        "victim": [{**step, "anim": clip(step["anim"]),
                    "alternatives": [clip(a) for a in step.get("alternatives", [])]} for step in tl.victim],
        "scale": tl.scale,
        "alpha": tl.alpha,
        "spawns": [{**s, "vot": build.names.get(s["vot"])} for s in tl.spawns if s["vot"] in build.names],
        "attached": [{**a, "vot": build.names.get(a["vot"])} for a in tl.attached if a["vot"] in build.names],
    }
    if tl.shakes:
        out["shakes"] = tl.shakes
    if tl.tints:
        out["tints"] = tl.tints
    if tl.ignored:
        out["ignored"] = sorted(set(tl.ignored))
    for key in ("victim", "spawns", "attached"):
        for item in out[key]:
            for k in list(item):
                if item[k] is None or item[k] == []:
                    del item[k]
    return out


def caster_json(tl, build: FxBuild, fade_end: float) -> dict:
    """Chronologie du tueur (`casterFxScript`) : ses animations, les effets accrochés à ses
    locators et les rayons tendus vers la victime. Le script n'a pas de borne propre : il
    s'éteint avec la victime (`fadeStartTime + fadeDuration`)."""
    def bounded(until):
        return round(fade_end if until is None else min(until, fade_end), 4)

    out = {
        "anims": [{"t": s["t"], "end": bounded(s["end"]), "anim": s["anim"][:1].upper() + s["anim"][1:],
                   "speed": s["speed"], "mode": s["mode"]} for s in tl.victim if s.get("anim")],
        "attached": [{**a, "vot": build.names[a["vot"]], "until": bounded(a.get("until"))}
                     for a in tl.attached if a["vot"] in build.names],
        "channels": [{**c, "vot": build.names[c["vot"]], "until": bounded(c.get("until"))}
                     for c in tl.channels if c["vot"] in build.names],
    }
    for item in out["attached"]:
        for k in [k for k, v in item.items() if v is None]:
            del item[k]
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export des fatalités (personnages, effets, chronologies, sons)")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--client", type=Path, default=None)
    parser.add_argument("--only", action="append")
    parser.add_argument("--only-fx", action="append")
    parser.add_argument("--no-characters", action="store_true")
    parser.add_argument("--no-sounds", action="store_true")
    parser.add_argument("--no-scene", action="store_true")
    parser.add_argument("--no-fx", action="store_true", help="ne réexporte aucune fatalité (garde l'index)")
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    client = Path(args.client or os.environ.get("ALLODS_RU_CLIENT_DIR") or manifest["client_root"])
    report: list[str] = []
    only_fx = ["__none__"] if args.no_fx else args.only_fx
    run(manifest, args.out, client, args.only, only_fx, not args.no_characters, not args.no_sounds, report,
        not args.no_scene)
    for line in report:
        print(line, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
