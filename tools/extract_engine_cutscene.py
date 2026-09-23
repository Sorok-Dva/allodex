#!/usr/bin/env python3
"""Cinématiques moteur des quêtes recréées en 3D pour le film (`/cinematics`).

Le jeu ne livre pas ces scènes en vidéo : il les joue en temps réel. Ce script en rassemble les
éléments dans le **dernier client (17.0)**, avec les lecteurs communs des exports 3D
(`allods_packdb`, `allods_visdb`, `allods_characters`, `allods_gltf`, `allods_fx`) et ceux des
scènes (`allods_scenes`), puis les exporte pour le lecteur three.js
(`src/components/scene/EngineCutscene`) :

* **caméra** — `CameraTrackAction` du buff de la cinématique : points de caméra et de visée,
  chacun avec sa durée (le temps pour rejoindre le suivant) ;
* **répliques** — `ClientData` : sous-titre (RU/EN du 17.0, FR du client 16.0), voix (événement
  `Cutscenes/…`, onde des banques `SFX/Voice/*.bsb`), animation du locuteur ;
* **décor** — base de la carte `Bin/Maps_<carte>.bin` : objets posés des régions, gabarits avec
  leurs animations, composants et **particules** (`FxBuild`), **éclairage précalculé** de chaque
  objet (`lightvrt`, voir `vertex_light`), **ciel** (`SkyMesh` de l'éclairage de zone),
  **brouillard et lumières** de zone (`ZoneLights`), **lumières ponctuelles** (`LightComponent`) ;
* **acteurs** — `MobWorld` → `VisualMob` : créature (gabarit, squelette, animations) ou
  personnage habillé comme le client (`allods_characters` : tenue par défaut, variation de la
  `VisualMob`, objets portés, peau cuite, objets accrochés) ;
* **effets de scène** — gabarits des buffs de la quête et des PNJ d'effet (hologramme, portail),
  posés par le manifeste ;
* **sons** — boucles du décor, ambiance et musique de la carte (`Sound2DTassel`), sons des
  effets ; onde retrouvée par son nom dans les banques FSB des paks (`fsb5_stream_names`).

Ce que le client ne contient pas (le serveur le décide) et que le manifeste fournit, justifié :
position et trajets des acteurs, instant des répliques et des effets (`engine_scenes`).

Sorties : `public/game/cinematics/engine/<id>/` — `decor.glb`, `decor-light.bin`, `fx.glb`,
`actors/*.glb`, `textures/`, `particles/`, `voice/`, `sfx/`, `{fr,en,ru}.vtt`, `scene.json` — et
l'entrée du chapitre dans `public/game/cinematics/cinematics.json`.

Usage : python3 tools/extract_engine_cutscene.py [--only ao12-prologue04] [--no-voices]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path

import numpy as np
from PIL import Image

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import extract_menu_scene as _ems  # noqa: E402
from tools.allods_characters import bake_skin, read_character_template, read_variation, read_visual_item, resolve_appearance  # noqa: E402
from tools.allods_fx import FxBuild, ParticlePool, fsb5_stream_names  # noqa: E402
from tools.allods_gltf import Exporter, TexturePool, load_animation, load_geometry  # noqa: E402
from tools.allods_packdb import EXTERN, PackDB, open_catalog, open_map, open_pack  # noqa: E402
from tools.allods_scenes import (  # noqa: E402
    VM_VARIATION, buff_camera_track, buff_scripts, mob_name_index, mob_visual, read_client_line, read_lightvrt,
    read_regions, read_zone_light, static_visobject, visual_dress, visual_template,
)
from tools.allods_visdb import animation_names, read_action, read_visobject  # noqa: E402
from tools.extract_cinematics import (  # noqa: E402
    LANG_LABELS, LANGS, Line, TextSet, build_cues, clean_text, has_cyrillic, load_textset, to_vtt,
)
from tools.extract_menu_scene import BinSource  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE / "cinematics_manifest.json"
DEFAULT_OUT = HERE.parent / "public" / "game" / "cinematics"
DEFAULT_CLIENT = Path("/mnt/h/MyGames/AllodsRU")
# vgmstream du dépôt voisin `allods-texts-packer` (cherché en remontant : les worktrees sont plus profonds).
DEFAULT_VGMSTREAM = next((p / "allods-texts-packer" / "voices" / "tools" / "vgmstream" / "vgmstream-cli"
                          for p in HERE.parents if (p / "allods-texts-packer").is_dir()), Path("vgmstream-cli"))

# Côté maximal des textures : 512 pour le décor et les effets (vus de 40 à 70 m dans le pilote),
# 1024 pour les acteurs. Écart assumé pour le poids du site (les sources montent à 2048).
DECOR_TEXTURE_MAX = 512
ACTOR_TEXTURE_MAX = 1024
# Axe avant des modèles dans leur repère : −Y (queue du dragon et traîne de Klavdia vers +Y ; même
# constat que les fatalités, `CHANNEL_AXIS`). Lacet pour regarder un point : atan2(dy, dx) + π/2.
MODEL_FORWARD = -math.pi / 2
# Couleurs du jeu : 0x80 = 1 (lumières de zone comme couleurs de sommets, règle des fatalités).
GAME_COLOR_UNIT = 128.0
GENERATOR = "allodex/extract_engine_cutscene"


# --- lumière --------------------------------------------------------------------------------------

def _rgb(value: int | None) -> np.ndarray:
    v = (value or 0) & 0xFFFFFFFF
    return np.array([(v >> 16) & 255, (v >> 8) & 255, v & 255], np.float64) / GAME_COLOR_UNIT


def sun_direction(light: dict) -> np.ndarray:
    """Direction d'où vient le soleil (repère du jeu), convention des fatalités (`zone_light`)."""
    yaw, pitch = math.radians(light.get("sunYaw", 45.0)), math.radians(light.get("sunPitch", 45.0))
    return np.array([math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)])


def vertex_light(raw: np.ndarray, light: dict, normals: np.ndarray | None = None) -> np.ndarray:
    """Lumière d'un sommet du décor (unités du jeu, 1 = 0x80), depuis son `lightvrt`.

    Établi sur les données : l'**octet 2** est l'éclairage précalculé des lumières ponctuelles de
    la carte, `255 · Σ intensité · (1 − d / rayon)^atténuation · max(0, N·L)` borné à 255 — la
    formule redonne l'octet à 1,000 de corrélation sur les objets du pilote (164 `LightComponent`,
    `pivot`, `intensity`, `radius`, `attenuationPower`) ; leur couleur est la `PointLightColor` de
    la zone. Les octets 0 et 1 (quantifiés sur 3 et 4 bits) ne sont pas élucidés : le soleil est
    donc appliqué sans ombre portée, `DiffuseColor · max(0, N·S)`. Total : ambiante + soleil +
    ponctuelles, comme le jeu éclaire ses personnages (`texture × (ambiante + soleil · N·L)`)."""
    point = raw[:, 2:3] / 255.0 * _rgb(light.get("pointLight", 0xFFFFFFFF))
    sun = 0.0
    if normals is not None and len(normals) == len(raw):
        sun = np.clip(normals @ sun_direction(light), 0, None)[:, None] * _rgb(light.get("diffuse"))
    return _rgb(light.get("ambient")) + sun + point


def encode_light(values: np.ndarray) -> np.ndarray:
    """Lumière (1 = 0x80) → couleurs de sommets RGBA u8 à moitié (le lecteur double : `modulate2x`)."""
    rgb = np.clip(np.round(values * 127.5), 0, 255)
    return np.concatenate([rgb, np.full((len(values), 1), 255)], axis=1).astype(np.uint8)


def point_lights(db: PackDB, objects) -> list[dict]:
    """Lumières ponctuelles des objets posés (`LightComponent` : +0x44 attenuationPower,
    +0x64 intensity, +0x6C pivot, +0x78 radius ; recoupé sur `AC6_Torch_Cup_Red` 7.0)."""
    out = []
    for obj in objects:
        vot = static_visobject(db, obj.static_object)
        if vot is None:
            continue
        for comp in db.pointers(vot + 0x138):
            if db.vtype(comp) != "LightComponent":
                continue
            pivot = np.array(db.floats(comp + 0x6C, 3))
            c, s = math.cos(obj.yaw), math.sin(obj.yaw)
            pos = np.array(obj.position) + np.array([pivot[0] * c - pivot[1] * s, pivot[0] * s + pivot[1] * c, pivot[2]])
            out.append({"p": [round(float(v), 3) for v in pos], "intensity": round(db.f32(comp + 0x64), 4),
                        "radius": round(db.f32(comp + 0x78), 3), "attenuation": round(db.f32(comp + 0x44), 4)})
    return out


def light_at(position, lights: list[dict], light: dict) -> list[float]:
    """Lumière d'un acteur (1 = 0x80) : ambiante + ponctuelles à sa position (sans N·L, moyenne
    ½ d'une sphère) ; le soleil, orienté, est laissé au lecteur."""
    p = np.array(position, float) + np.array([0, 0, 1.0])
    total = 0.0
    for lt in lights:
        d = float(np.linalg.norm(np.array(lt["p"]) - p))
        if d < lt["radius"]:
            total += lt["intensity"] * (1 - d / lt["radius"]) ** lt["attenuation"] * 0.5
    rgb = _rgb(light.get("ambient")) + min(total, 1.0) * _rgb(light.get("pointLight", 0xFFFFFFFF))
    return [round(float(v), 4) for v in rgb]


# --- décor ---------------------------------------------------------------------------------------

def yaw_quaternion(yaw: float) -> list[float]:
    return [0.0, 0.0, math.sin(yaw / 2), math.cos(yaw / 2)]


def ground_z(solids: np.ndarray, x: float, y: float, below: float) -> float | None:
    """Plus haute surface opaque du décor sous le point (x, y), sous l'altitude `below`."""
    if not len(solids):
        return None
    a, b, c = solids[:, 0, :2], solids[:, 1, :2], solids[:, 2, :2]
    p = np.array([x, y])
    v0, v1, v2 = c - a, b - a, p - a
    d00 = (v0 * v0).sum(1); d01 = (v0 * v1).sum(1); d11 = (v1 * v1).sum(1)
    d20 = (v2 * v0).sum(1); d21 = (v2 * v1).sum(1)
    den = d00 * d11 - d01 * d01
    ok = np.abs(den) > 1e-12
    u = np.where(ok, (d11 * d20 - d01 * d21) / np.where(ok, den, 1), -1)
    v = np.where(ok, (d00 * d21 - d01 * d20) / np.where(ok, den, 1), -1)
    inside = ok & (u >= 0) & (v >= 0) & (u + v <= 1)
    if not inside.any():
        return None
    z = solids[inside, 0, 2] + u[inside] * (solids[inside, 2, 2] - solids[inside, 0, 2]) + v[inside] * (solids[inside, 1, 2] - solids[inside, 0, 2])
    z = z[z < below]
    return float(z.max()) if len(z) else None


def build_decor(mp: PackDB, cat, bins, textures: TexturePool, particles: ParticlePool, light: dict,
                spec: dict, report: list[str]) -> dict:
    """Décor : gabarits des objets posés (une fois chacun) dans `decor.glb`, instances dans
    `scene.json`, éclairage précalculé de chaque instance dans `decor-light.bin`."""
    fx = FxBuild(Exporter(textures, DECOR_TEXTURE_MAX, generator=GENERATOR, texture_prefix="textures/"), mp, cat, bins, particles=particles, report=report)
    lightvrt = read_lightvrt(mp, spec["map"], lambda name, pak: bins.get(name))
    objects = read_regions(mp)
    center, radius = spec.get("decor_center"), spec.get("decor_radius", 1e9)
    instances, blobs, solids = [], [], []
    offset = 0
    emitted: set[str] = set()
    geometries: dict[int, object] = {}
    skipped = 0
    for obj in objects:
        x, y, z = obj.position
        if center and math.hypot(x - center[0], y - center[1]) > radius:
            continue
        vot = static_visobject(mp, obj.static_object)
        if vot is None:
            skipped += 1
            continue
        vis = read_visobject(mp, cat, vot)
        if vis.geometry is None and vis.particle is None and not vis.components:
            continue
        name = fx.name_of(vot)
        if name not in emitted:
            node = fx.emit(vot)
            emitted.add(name)
            if node is not None:
                fx.roots.append(node)
        if name not in fx.meta:
            continue
        inst = {"vot": name, "p": [round(v, 4) for v in obj.position], "yaw": round(obj.yaw, 5)}
        if abs(obj.scale - 1) > 1e-6 and obj.scale > 0:
            inst["scale"] = round(obj.scale, 5)
        raw = lightvrt.get((obj.region, obj.index))
        loaded = None
        if vis.geometry is not None:
            if vis.geometry not in geometries:
                geometries[vis.geometry] = load_geometry(mp, cat, bins, vis.geometry)
            loaded = geometries[vis.geometry]
        if loaded is not None:
            world = np.eye(4)
            world[:3, :3] = _ems.quat_matrix(np.array(yaw_quaternion(obj.yaw))) * (obj.scale if obj.scale > 0 else 1.0)
            world[:3, 3] = obj.position
            normals = loaded.vertices.get("normal")
            wn = normals.astype(np.float64) @ world[:3, :3].T if normals is not None else None
            if wn is not None:
                wn /= np.maximum(np.linalg.norm(wn, axis=1, keepdims=True), 1e-9)
            if raw is not None and len(raw) == len(loaded.vertices["position"]):
                colors = encode_light(vertex_light(raw, light, wn))
                blobs.append(colors.tobytes())
                inst["light"] = [offset, len(colors)]
                offset += len(colors)
            else:
                inst["ambient"] = [round(float(v), 4) for v in _rgb(light.get("ambient"))]
            tris = [loaded.indices[e.ib0:e.ib1] for e in loaded.geo.doc.elements
                    if e.material.visible and not e.material.transparent and e.material.texture]
            if tris:
                idx = np.concatenate(tris)
                idx = idx[: len(idx) // 3 * 3]
                pts = np.column_stack([loaded.vertices["position"].astype(np.float64), np.ones(len(loaded.vertices["position"]))])
                solids.append(((pts @ world.T)[:, :3])[idx].reshape(-1, 3, 3))
        instances.append(inst)
    sky = None
    if light.get("skyGeometry") is not None:
        loaded = load_geometry(mp, cat, bins, light["skyGeometry"])
        if loaded is not None:
            elements = [e for e in loaded.geo.doc.elements if e.material.visible and e.material.texture]
            mesh, _ = fx.exporter.emit_mesh("sky", loaded.geo, loaded.vertices, loaded.indices, elements, None)
            if mesh is not None:
                fx.roots.append(fx.exporter.gltf.add_node({"name": "sky", "mesh": mesh, "extras": {"sky": True}}))
                aabb = loaded.geo.doc.aabb
                sky = {"radius": round(float(np.max(np.abs(np.concatenate(aabb)))), 2)}
    glb = fx.exporter.finish(fx.roots)
    report.append(f"décor : {len(instances)} objets posés ({len(emitted)} gabarits), {skipped} sans gabarit visuel, "
                  f"{sum(1 for i in instances if 'light' in i)} avec éclairage précalculé")
    report += fx.exporter.notes
    return {"glb": glb, "light": b"".join(blobs), "instances": instances, "objects": fx.meta, "sounds": fx.sounds,
            "solids": np.concatenate(solids) if solids else np.zeros((0, 3, 3)), "sky": sky,
            "pointLights": point_lights(mp, objects)}


def map_sounds(mp: PackDB) -> dict[str, list[str]]:
    """Musique et ambiance de la carte : `Sound2DTassel` propres à sa base (`+0x58` événement),
    rangés par préfixe (`Music/…`, `Ambience/…`). Les préréglages d'ambiance que la base
    embarque tous (`AmbiencePresets/*`, repérés par leur nom commun) sont écartés, sauf le premier
    qui précède le bloc des préréglages (celui des régions de la carte)."""
    out: dict[str, list[str]] = {"music": [], "ambience": []}
    tassels = sorted(o for o in mp.resources("Sound2DTassel") if not o & EXTERN)
    names = [(o, mp.string(o + 0x58) or "") for o in tassels]
    for off, name in names:
        if name.startswith("Music/"):
            out["music"].append(name)
    ambience = [n for _, n in names if n.startswith("Ambience/")]
    if ambience:
        out["ambience"].append(ambience[0])
    return out


# --- acteurs --------------------------------------------------------------------------------------

def animation_file(bins, geometry_binary: str, anim: str) -> str | None:
    """`X/Y.(Geometry).bin` + `Idle` → `X/Animations/Y.Idle.(SkeletalAnimation).bin` (sans égard à la casse)."""
    folder, stem = geometry_binary.rsplit("/", 1)
    stem = stem.split(".(")[0]
    want = f"{folder}/Animations/{stem}.{anim}.(SkeletalAnimation).bin".lower()
    for name in bins._pak_index():
        if name.lower() == want:
            return name
    return None


def build_actor(actor: dict, db: PackDB, cat, bins, textures: TexturePool, report: list[str]) -> tuple[bytes, dict]:
    """Acteur : gabarit de sa `VisualMob` ; un personnage (gabarit à tenue par défaut) est habillé
    par `allods_characters` avec la variation et les objets de sa `VisualMob`."""
    mob = pack_offset(db, actor["mob"])
    if mob is None:
        raise ValueError(f"{actor['id']} : MobWorld {actor['mob']} introuvable")
    visual = mob_visual(db, mob)
    tpl_off = visual_template(db, visual) if visual is not None else None
    if tpl_off is None:
        raise ValueError(f"{actor['id']} : gabarit visuel introuvable")
    template = read_character_template(db, cat, tpl_off)
    vot = read_visobject(db, cat, template.visobject)
    loaded = load_geometry(db, cat, bins, vot.geometry) if vot.geometry is not None else None
    if loaded is None or loaded.skeleton is None:
        raise ValueError(f"{actor['id']} : géométrie ou squelette illisible")
    ex = Exporter(textures, ACTOR_TEXTURE_MAX, generator=GENERATOR, lit=True)
    geo_elements = loaded.geo.doc.elements
    override: dict[str, str] = {}
    attachments: list[tuple[str, int, str]] = []
    if template.default_dress is not None:
        variation = read_variation(db, cat, visual + VM_VARIATION)
        items = [read_visual_item(db, cat, off) for off in visual_dress(db, visual)]
        appearance = resolve_appearance(template, [e.name for e in geo_elements],
                                        {e.name: e.material.texture for e in geo_elements if e.material.visible},
                                        variation=variation, items=items)
        override = dict(appearance.replacements)
        skin = template.main_texture
        base = textures.image(skin, 2048) if skin else None
        if base is not None:
            image_of = lambda name: textures.image(name, 2048)  # noqa: E731
            mask = textures.image(appearance.skin_mask, 2048) if appearance.skin_mask else None
            baked_name = f"actors/{actor['id']}-skin"
            textures.add_image(baked_name, bake_skin(base, appearance, image_of, mask, min(max(base.size), ACTOR_TEXTURE_MAX)),
                               ACTOR_TEXTURE_MAX)
            for e in geo_elements:
                if e.name not in override and e.material.texture == skin:
                    override[e.name] = baked_name
        visible = set(appearance.visible)
        elements = [e for e in geo_elements if e.name in visible]
        ex.tints = appearance.tints
        for item in [template.default_dress] + variation.items() + items:
            for shape in item.shapes_for(template.gender):
                if shape.scene is not None and shape.locator:
                    attachments.append((shape.locator, shape.scene, shape.shape))
        report.append(f"{actor['id']} : {len(elements)} géosets, {len(appearance.patches)} calques, "
                      f"{len(attachments)} objets accrochés")
    else:
        elements = [e for e in geo_elements if e.material.visible and e.material.texture]
    mesh, skinned = ex.emit_mesh(actor["id"], loaded.geo, loaded.vertices, loaded.indices, elements, loaded.skeleton, override)
    skeleton = loaded.skeleton
    joints = ex.emit_skeleton(skeleton, actor["id"])
    static_node = ex.gltf.add_node({"name": f"{actor['id']}/Static"})
    mesh_node = {"name": f"{actor['id']}_mesh", "mesh": mesh}
    if skinned:
        mesh_node["skin"] = ex.skin(actor["id"], skeleton, joints, static_node)
    for locator, scene, shape_name in attachments:
        if locator not in skeleton.names:
            report.append(f"{actor['id']} : locator absent du squelette {locator}")
            continue
        vis = read_visobject(db, cat, scene)
        att = load_geometry(db, cat, bins, vis.geometry) if vis.geometry is not None else None
        if att is None:
            continue
        # la géométrie accrochée porte souvent les deux côtés (« L », « R ») ou un élément par
        # gabarit (casques) : le nom de la forme choisit l'élément dessiné
        chosen = [e for e in att.geo.doc.elements if e.name == shape_name] or \
            [e for e in att.geo.doc.elements if e.material.visible and e.material.texture]
        index, _ = ex.emit_mesh(f"{actor['id']}:{locator}", att.geo, att.vertices, att.indices, chosen, None)
        if index is not None:
            node = ex.gltf.add_node({"name": f"attach:{locator}", "mesh": index})
            ex.gltf.json["nodes"][joints[skeleton.names.index(locator)]].setdefault("children", []).append(node)
    roots = [joints[i] for i in range(len(skeleton)) if not (0 <= skeleton.parents[i] < len(skeleton))]
    span = float(np.max(np.abs(loaded.vertices["position"])) * 4.0)
    durations = {}
    for anim in actor.get("animations", ["Idle"]):
        file = animation_file(bins, loaded.geo.binary, anim)
        animation = load_animation(bins, file, skeleton, span)
        if animation is None:
            report.append(f"{actor['id']} : animation absente {anim}")
            continue
        durations[anim] = round(ex.emit_clip(anim, skeleton, joints, animation), 4)
    scale = vot.scale if vot.scale > 0 else 1.0
    root = ex.gltf.add_node({"name": actor["id"], "children": roots + [static_node, ex.gltf.add_node(mesh_node)],
                             **({"scale": [scale] * 3} if abs(scale - 1) > 1e-6 else {})})
    report += [f"{actor['id']} : {n}" for n in ex.notes]
    meta = {"geometry": loaded.geo.binary, "height": round(float(loaded.vertices["position"][:, 2].max() * scale), 3),
            "animations": durations, "name_index": mob_name_index(db, mob)}
    return ex.finish([root]), meta


# --- effets de scène ------------------------------------------------------------------------------

def pack_offset(db: PackDB, rid) -> int | None:
    """Ressource de `pack.bin` par identifiant, vue depuis la base de carte `db` (bit `EXTERN`)."""
    root = getattr(db, "parent", None) or db
    off = root.ids.get(int(rid))
    return None if off is None else (off | EXTERN if root is not db else off)


def spawn_template(db: PackDB, spawn: dict) -> int | None:
    """Gabarit d'un effet du manifeste : `vot` (ressource), `mob` (PNJ d'effet : son gabarit visuel),
    `buff` (premier gabarit des effets du script du buff)."""
    if "vot" in spawn:
        return pack_offset(db, spawn["vot"])
    if "mob" in spawn:
        mob = pack_offset(db, spawn["mob"])
        visual = mob_visual(db, mob) if mob is not None else None
        tpl = visual_template(db, visual) if visual is not None else None
        return db.ptr(tpl + 0x90) if tpl is not None else None
    if "buff" in spawn:
        scripts = buff_scripts(db, pack_offset(db, spawn["buff"]))
        found: list[int] = []

        def walk(node):
            if not node:
                return
            if node.get("visObject"):
                found.append(node["visObject"])
            for e in node.get("effects", []):
                if e.get("visObject"):
                    found.append(e["visObject"])
            for child in node.get("elements", []):
                walk(child)
        walk(read_action(db, db.ptr(scripts + 0x48)) if scripts is not None else None)
        return found[0] if found else None
    return None


def build_fx(spawns: list[dict], db: PackDB, cat, bins, textures: TexturePool, particles: ParticlePool,
             report: list[str]) -> tuple[bytes | None, dict, set[str], list[dict]]:
    fx = FxBuild(Exporter(textures, DECOR_TEXTURE_MAX, generator=GENERATOR, texture_prefix="textures/"), db, cat, bins, particles=particles, report=report)
    out = []
    for spawn in spawns:
        vot = spawn_template(db, spawn)
        if vot is None:
            report.append(f"effet introuvable : {spawn}")
            continue
        name = fx.name_of(vot)
        if name not in fx.meta:
            node = fx.emit(vot)
            if node is not None:
                fx.roots.append(node)
        entry = {k: v for k, v in spawn.items() if k not in ("vot", "mob", "buff", "_note")}
        entry["vot"] = name
        out.append(entry)
    glb = fx.exporter.finish(fx.roots) if fx.roots else None
    report += fx.exporter.notes
    return glb, fx.meta, fx.sounds, out


# --- sons -----------------------------------------------------------------------------------------

def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def sound_index(bins, cache: Path) -> dict[str, list[tuple[str, int, str]]]:
    """Index des ondes de toutes les banques FSB des paks (`SFX/**/*.fsb|bsb`) : clé → (banque,
    sous-piste, nom). Mis en cache (`~/.cache/allodex/streams-<n>.json`)."""
    names = sorted(n for n in bins._pak_index() if n.startswith("SFX/") and n.lower().endswith((".fsb", ".bsb")))
    path = cache / f"streams-{len(names)}.json"
    if path.is_file():
        data = json.loads(path.read_text())
    else:
        data = {}
        for bank in names:
            raw = bins.get(bank)
            if not raw:
                continue
            if bank.lower().endswith(".bsb"):
                try:
                    raw = zlib.decompress(raw)
                except zlib.error:
                    continue
            at = raw.find(b"FSB5")
            if at >= 0:
                data[bank] = fsb5_stream_names(raw[at:])
        cache.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
    index: dict[str, list[tuple[str, int, str]]] = {}
    for bank, streams in data.items():
        for i, stream in enumerate(streams, 1):
            index.setdefault(_key(stream), []).append((bank, i, stream))
    return index


def find_wave(event: str, index: dict, prefer: str = "") -> tuple[str, int, str] | None:
    """Onde d'un événement FMOD par son nom (dernier segment) : nom identique, sinon suivi de
    `_lp` (boucle), `_nm` ou d'un numéro (première variante). Le fichier d'événements `.bev`
    (qui relie événements et ondes) n'est pas lu : appariement par le nom, documenté."""
    tail = _key(event.split("/")[-1])
    for suffix in ("", "lp", "nm", "loop", "1", "01"):
        hits = index.get(tail + suffix)
        if hits:
            hits = sorted(hits, key=lambda h: (prefer not in h[0], h[0]))
            return hits[0]
    # préréglage d'ambiance (`Demonic_AP`) : la boucle de fond de même préfixe (`demonic_drone_lp`)
    stem = re.sub(r"ap$", "", tail)
    loops = sorted((h for k, hs in index.items() if k.startswith(stem) and k.endswith("lp") for h in hs),
                   key=lambda h: ("Ambience" not in h[0], h[2]))
    return loops[0] if stem and loops else None


def export_waves(events: set[str], bins, out_dir: Path, vgmstream: Path, report: list[str],
                 music_seconds: float | None = None) -> dict[str, dict]:
    """Ondes des événements, encodées en Ogg Vorbis et MP3 dans `sfx/`. La musique de zone est
    coupée à la durée de la scène (`music_seconds`, fondu de sortie de 2 s) : le poids du site."""
    from tools.extract_audio import encode_outputs
    index = sound_index(bins, Path(os.environ.get("ALLODEX_CACHE") or Path.home() / ".cache" / "allodex"))
    found: dict[str, dict] = {}
    target = out_dir / "sfx"
    with tempfile.TemporaryDirectory(prefix="allodex-sfx-") as tmp:
        for event in sorted(events):
            hit = find_wave(event, index, "Music" if event.startswith("Music/") else "")
            if hit is None:
                report.append(f"onde introuvable pour l'événement {event}")
                continue
            bank, sub, stream = hit
            base = target / re.sub(r"[^A-Za-z0-9_.-]", "_", stream)
            if not (base.with_suffix(".ogg").exists() and base.with_suffix(".mp3").exists()):
                raw = bins.get(bank)
                if bank.lower().endswith(".bsb"):
                    raw = zlib.decompress(raw)
                fsb = Path(tmp) / "bank.fsb"
                fsb.write_bytes(raw[raw.find(b"FSB5"):])
                wav = Path(tmp) / "out.wav"
                subprocess.run([str(vgmstream), "-i", "-s", str(sub), "-o", str(wav), str(fsb)], check=True, capture_output=True)
                if music_seconds and event.startswith("Music/"):
                    cut = Path(tmp) / "cut.wav"
                    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-t", f"{music_seconds:.2f}", "-af",
                                    f"afade=t=out:st={max(0.0, music_seconds - 2):.2f}:d=2", str(cut)], check=True)
                    wav = cut
                target.mkdir(parents=True, exist_ok=True)
                encode_outputs(wav, base, "sfx")
            duration = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                             "default=nw=1:nk=1", str(base.with_suffix(".ogg"))],
                                            capture_output=True, text=True).stdout.strip() or 0)
            found[event] = {"file": f"sfx/{base.name}", "wave": stream, "bank": bank, "duration": round(duration, 3)}
    return found


def export_voices(events: list[str | None], bank: str, bins, out_dir: Path, vgmstream: Path,
                  report: list[str]) -> list[dict | None]:
    data = bins.get(bank)
    if data is None:
        report.append(f"banque vocale introuvable : {bank}")
        return [None] * len(events)
    if bank.endswith(".bsb"):
        data = zlib.decompress(data)
    payload = data[data.find(b"FSB5"):]
    names = fsb5_stream_names(payload)
    out_dir.mkdir(parents=True, exist_ok=True)
    result: list[dict | None] = []
    with tempfile.TemporaryDirectory(prefix="allodex-voice-") as tmp:
        fsb = Path(tmp) / "bank.fsb"
        fsb.write_bytes(payload)
        for n, event in enumerate(events, 1):
            tail = (event or "").split("/")[-1]
            if tail not in names:
                report.append(f"voix absente de la banque : {event}")
                result.append(None)
                continue
            wav = Path(tmp) / f"{n}.wav"
            subprocess.run([str(vgmstream), "-i", "-s", str(names.index(tail) + 1), "-o", str(wav), str(fsb)],
                           check=True, capture_output=True)
            base = out_dir / f"{n:02d}"
            for ext, args in (("ogg", ["-c:a", "libopus", "-b:a", "48k"]), ("mp3", ["-c:a", "libmp3lame", "-b:a", "64k"])):
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-ac", "1", *args,
                                str(base.with_suffix(f".{ext}"))], check=True)
            duration = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                             "default=nw=1:nk=1", str(base.with_suffix(".ogg"))],
                                            capture_output=True, text=True).stdout.strip() or 0)
            result.append({"event": event, "ogg": f"voice/{n:02d}.ogg", "mp3": f"voice/{n:02d}.mp3", "duration": round(duration, 3)})
    return result


# --- chronologie ----------------------------------------------------------------------------------

def camera_keys(track) -> dict:
    """Clés de caméra : la durée d'un point est le temps mis à rejoindre le suivant (le dernier
    tient jusqu'à la fin). Vérifié sur le pilote : les trois groupes de répliques tombent chacun
    dans un tronçon (39 s, 21 s, 15 s) de la trajectoire."""
    def keys(points):
        out, t = [], 0.0
        for dur, pos in points:
            out.append({"t": round(t, 3), "p": list(pos)})
            t += dur
        return out, t
    cam, total = keys(track.points)
    tgt, _ = keys(track.targets)
    return {"points": cam, "targets": tgt, "duration": round(total, 3)}


def schedule_lines(spec: dict, camera: dict, voices: list[dict | None], lines: list[Line]) -> list[float]:
    """Départ de chaque réplique : chaque groupe du manifeste s'ouvre au début du tronçon de caméra
    indiqué (+ `lead`), les répliques d'un groupe s'enchaînent à la fin de la voix précédente (+ `gap`)."""
    starts = [0.0] * len(lines)
    times = [k["t"] for k in camera["points"]]
    lead, gap = spec["timing"].get("lead", 0.5), spec["timing"].get("gap", 0.6)
    for group in spec["timing"]["groups"]:
        t = times[group["segment"]] + lead
        for n in group["lines"]:
            i = n - 1
            starts[i] = round(t, 3)
            length = voices[i]["duration"] if voices[i] else lines[i].duration
            t += length + gap
    return starts


def resolve_scene_lines(spec: dict, db: PackDB, main: TextSet, fr: TextSet | None, report: list[str]) -> tuple[list[Line], list]:
    lines, raw = [], []
    delta = None
    for n, rid in enumerate(spec["lines"], 1):
        cd = db.ids.get(int(rid))
        if cd is None:
            raise ValueError(f"ClientData {rid} introuvable")
        cl = read_client_line(db, cd)
        raw.append(cl)
        idx = cl.text_index
        text = {"ru": clean_text(main.texts["ru"][idx])}
        en = clean_text(main.texts["en"][idx])
        if en and not has_cyrillic(en):
            text["en"] = en
        if fr is not None:
            if delta is None and spec.get("fr_anchor"):
                delta = idx - fr.find("fr", spec["fr_anchor"])
            j = idx - (delta or 0)
            if delta is not None and fr.subtitles.get(j) == cl.delay_ms:
                text["fr"] = clean_text(fr.texts["fr"][j])
            else:
                report.append(f"réplique {n} : pas de français (index {j})")
        lines.append(Line(cl.delay_ms / 1000, text))
    return lines, raw


def speaker_of(line: Line, actors: list[dict]) -> str | None:
    ru = line.text.get("ru", "")
    for a in actors:
        if any(ru.startswith(p) for p in a.get("speaker_prefixes", [])):
            return a["id"]
    return None


def place(point: list[float], solids: np.ndarray, ground: bool) -> list[float]:
    """Pose un point du manifeste sur le décor (`ground`) : z = surface sous `point[2]`."""
    if not ground:
        return [round(float(v), 4) for v in point]
    z = ground_z(solids, point[0], point[1], point[2] if len(point) > 2 else 1e9)
    return [round(point[0], 4), round(point[1], 4), round(z if z is not None else point[2], 4)]


def face_yaw(position: list[float], face: list[float]) -> float:
    return round(math.atan2(face[1] - position[1], face[0] - position[0]) - MODEL_FORWARD, 4)


# --- export ---------------------------------------------------------------------------------------

def run(manifest: dict, out_root: Path, client: Path, only: list[str] | None, voices: bool, vgmstream: Path) -> list[str]:
    report: list[str] = []
    db = open_pack(client)
    packs = client / "data" / "Packs"
    bins = BinSource([], [str(packs / "*.pak")])
    main_spec, fr_spec = manifest["sources"]["main"], manifest["sources"]["fr"]
    main = load_textset(Path(main_spec["root"]), main_spec)
    try:
        fr = load_textset(Path(fr_spec["root"]), fr_spec)
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        report.append(f"textes FR illisibles : {exc}")
        fr = None
    anim_names = animation_names(db)
    entries = []
    for spec in manifest["engine_scenes"]:
        if only and spec["id"] not in only:
            continue
        out = out_root / "engine" / spec["id"]
        out.mkdir(parents=True, exist_ok=True)
        mp = open_map(db, client, spec["map"])
        cat = open_catalog(mp, client)
        textures = TexturePool(mp, cat, bins, out, jpeg=True)
        particles = ParticlePool(mp, cat, bins, out)
        light = read_zone_light(mp)
        track = buff_camera_track(db, db.ids[int(spec["buff"])])
        camera = camera_keys(track)
        camera["fov"] = spec.get("fov", 45)
        lines, raw = resolve_scene_lines(spec, db, main, fr, report)

        decor = build_decor(mp, cat, bins, textures, particles, light, spec, report)
        (out / "decor.glb").write_bytes(decor["glb"])
        (out / "decor-light.bin").write_bytes(decor["light"])
        solids = decor["solids"]

        actors_meta = []
        for actor in spec["actors"]:
            data, meta = build_actor(actor, mp, cat, bins, textures, report)
            (out / "actors").mkdir(exist_ok=True)
            (out / "actors" / f"{actor['id']}.glb").write_bytes(data)
            ground = bool(actor.get("ground"))
            path = []
            for key in actor.get("path") or [{"t": 0, "p": actor["position"], "face": actor.get("face")}]:
                p = place(key["p"], solids, ground and not key.get("air"))
                if key.get("lift"):
                    p[2] = round(p[2] + key["lift"], 4)
                entry = {"t": key.get("t", 0), "p": p}
                if key.get("face"):
                    entry["yaw"] = face_yaw(p, key["face"])
                elif "yaw" in key:
                    entry["yaw"] = key["yaw"]
                path.append(entry)
            name_idx = meta.pop("name_index")
            actors_meta.append({"id": actor["id"], "glb": f"actors/{actor['id']}.glb",
                                "name": {"ru": clean_text(main.texts["ru"][name_idx]), "en": clean_text(main.texts["en"][name_idx])},
                                "path": path, "scale": actor.get("scale", 1.0), "idle": actor.get("idle", "Idle"),
                                "talk": actor.get("talk"), "move": actor.get("move"), "appear": actor.get("appear", 0.0),
                                "light": light_at(path[0]["p"], decor["pointLights"], light), **meta})

        fx_glb, fx_objects, fx_sounds, spawns = build_fx(spec.get("spawns", []), mp, cat, bins, textures, particles, report)
        for spawn in spawns:
            if "p" in spawn:
                spawn["p"] = place(spawn["p"], solids, bool(spawn.pop("ground", False)))
        if fx_glb:
            (out / "fx.glb").write_bytes(fx_glb)

        voice_meta = [None] * len(lines)
        events = [cl.voice for cl in raw]
        if voices:
            voice_meta = export_voices(events, spec["voice_bank"], bins, out / "voice", vgmstream, report)
        elif (out / "scene.json").is_file():
            old = json.loads((out / "scene.json").read_text(encoding="utf-8"))
            voice_meta = [l.get("voice") for l in old.get("lines", [])] or voice_meta
        starts = schedule_lines(spec, camera, voice_meta, lines)
        cues = build_cues(lines, starts, camera["duration"])
        tracks = []
        for lang in LANGS:
            vtt = to_vtt(cues, lang)
            path = out / f"{lang}.vtt"
            if vtt:
                path.write_text(vtt, encoding="utf-8")
                tracks.append({"lang": lang, "label": LANG_LABELS[lang], "src": f"engine/{spec['id']}/{lang}.vtt",
                               "lines": sum(1 for c in cues if lang in c[2])})

        audio = map_sounds(mp)
        audio.update({k: v for k, v in spec.get("audio", {}).items() if not k.startswith("_")})
        wanted = set(decor["sounds"]) | set(fx_sounds) | set(audio.get("music", [])) | set(audio.get("ambience", []))
        waves = export_waves(wanted, bins, out, vgmstream, report, camera["duration"] + 1) if voices or not (out / "scene.json").is_file() else \
            json.loads((out / "scene.json").read_text(encoding="utf-8")).get("sounds", {}).get("waves", {})
        for objects in (decor["objects"], fx_objects):
            for info in objects.values():
                if info.get("sound") in waves:
                    info["sfx"] = waves[info["sound"]]["file"]

        atlas = particles.write_atlas(textures)
        scene_lines = []
        for i, (line, cl) in enumerate(zip(lines, raw)):
            scene_lines.append({"n": i + 1, "start": starts[i], "duration": line.duration, "speaker": speaker_of(line, spec["actors"]),
                                "voice": voice_meta[i], "animations": [anim_names.get(a, str(a)) for a in cl.animations],
                                "text": line.text})
        zone = {k: v for k, v in light.items() if k not in ("sky", "skyGeometry")}
        scene = {
            "id": spec["id"], "map": spec["map"], "up": [0, 0, 1], "mirror": True, "duration": camera["duration"],
            "camera": camera, "lines": scene_lines, "actors": actors_meta,
            "decor": {"glb": "decor.glb", "light": "decor-light.bin", "instances": decor["instances"], "sky": decor["sky"]},
            "fx": {"glb": "fx.glb" if fx_glb else None, "spawns": spawns},
            "objects": {**decor["objects"], **fx_objects}, "particleAtlas": atlas,
            "light": {**zone, "sunDirection": [round(float(v), 4) for v in sun_direction(light)]},
            "pointLights": decor["pointLights"],
            "sounds": {"music": [waves[m]["file"] for m in audio.get("music", []) if m in waves],
                       "ambience": [waves[a]["file"] for a in audio.get("ambience", []) if a in waves],
                       "events": audio, "waves": waves, "volume": spec.get("mix", {})},
            "post": spec.get("post", []),
        }
        (out / "scene.json").write_text(json.dumps(scene, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        report.append(f"{spec['id']} : décor {len(decor['glb']) / 1e6:.1f} Mo, textures {textures.bytes_written / 1e6:.1f} Mo, "
                      f"particules {particles.bytes_written / 1e6:.2f} Mo, {len(actors_meta)} acteurs, {len(spawns)} effets, "
                      f"{len(waves)} sons, {len(lines)} répliques, {camera['duration']:.0f} s")
        entries.append({"spec": spec, "duration": camera["duration"], "tracks": tracks, "lines": len(lines)})
    update_index(manifest, out_root, entries)
    return report


def update_index(manifest: dict, out_root: Path, entries: list[dict]) -> None:
    """Ajoute (ou remplace) les chapitres moteur dans `cinematics.json`, à leur place chronologique."""
    path = out_root / "cinematics.json"
    index = json.loads(path.read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in manifest["cinematics"]}
    for e in entries:
        spec = by_id[e["spec"]["id"]]
        entry = {
            "id": spec["id"], "arc": spec["arc"], "version": spec["version"], "faction": spec["faction"],
            "order": spec["order"], "event": spec.get("event"), "title": spec["title"], "chronology": spec["chronology"],
            "bonus": bool(spec.get("bonus")), "duration": round(e["duration"], 3),
            "files": {"poster": f"engine/{spec['id']}/poster.jpg"},
            "engine": {"scene": f"engine/{spec['id']}/scene.json"},
            "tracks": e["tracks"],
            "subtitles": {"status": "official", "lines": e["lines"], "timing": "estimated", "audio": {"language": "ru"}},
            "audio": {"language": "ru"},
        }
        index["cinematics"] = [c for c in index["cinematics"] if c["id"] != spec["id"]] + [entry]
    index["arcs"] = manifest["arcs"]
    index["cinematics"].sort(key=lambda c: (c["order"], c["id"]))
    path.write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--client", type=Path, default=DEFAULT_CLIENT)
    p.add_argument("--only", action="append")
    p.add_argument("--no-voices", action="store_true", help="garde les voix et les sons déjà extraits")
    p.add_argument("--vgmstream", type=Path, default=DEFAULT_VGMSTREAM)
    args = p.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = run(manifest, args.out, args.client, args.only, not args.no_voices, args.vgmstream)
    print("\n".join(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
