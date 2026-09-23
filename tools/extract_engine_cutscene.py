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
import shutil
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

from tools.allods_characters import bake_skin, read_character_template, read_variation, read_visual_item, resolve_appearance  # noqa: E402
from tools.allods_fx import FxBuild, ParticlePool, fsb5_stream_names  # noqa: E402
from tools.allods_gltf import Exporter, TexturePool, load_animation, load_geometry  # noqa: E402
from tools.allods_packdb import EXTERN, PackDB, open_catalog, open_map, open_pack  # noqa: E402
from tools.allods_scenes import (  # noqa: E402
    VM_VARIATION, buff_camera_track, buff_scripts, mob_name_index, mob_visual, read_client_line, read_lightvrt,
    read_regions, read_zone_light, sky_parts, static_visobject, visual_dress, visual_template,
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
    +0x64 intensity, +0x6C pivot, +0x78 radius ; recoupé sur `AC6_Torch_Cup_Red` 7.0). Pivot et
    rayon suivent l'échelle de l'objet (lumières de `Ferris4` posées à l'échelle 2,8 à 6,2 : sans
    elle, l'octet 2 des murs éclairés n'a pas de source) ; une intensité négative assombrit."""
    out = []
    for obj in objects:
        vot = static_visobject(db, obj.static_object)
        if vot is None:
            continue
        scale = obj.scale if obj.scale > 0 else 1.0
        for comp in db.pointers(vot + 0x138):
            if db.vtype(comp) != "LightComponent":
                continue
            pivot = np.array(db.floats(comp + 0x6C, 3), float)
            pos = np.array(obj.position) + obj.matrix() @ pivot * scale
            out.append({"p": [round(float(v), 3) for v in pos], "intensity": round(db.f32(comp + 0x64), 4),
                        "radius": round(db.f32(comp + 0x78) * scale, 3), "attenuation": round(db.f32(comp + 0x44), 4)})
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
    rgb = _rgb(light.get("ambient")) + min(max(total, 0.0), 1.0) * _rgb(light.get("pointLight", 0xFFFFFFFF))
    return [round(float(v), 4) for v in rgb]


# --- décor ---------------------------------------------------------------------------------------

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


def build_decor(mp: PackDB, cat, bins, textures: TexturePool, particles: ParticlePool, map_name: str,
                areas: list[tuple[list[float] | None, float]], report: list[str]) -> dict:
    """Décor d'une carte, **commun aux scènes qui s'y jouent** : les gabarits des objets posés dans
    l'une des zones (`areas` : centre, rayon de chaque scène) une fois chacun dans `decor.glb`, les
    instances avec ce qu'il faut pour éclairer chacune (`light_decor`, par scène : l'éclairage
    dépend du temps de la scène)."""
    fx = FxBuild(Exporter(textures, DECOR_TEXTURE_MAX, generator=GENERATOR, texture_prefix="textures/"), mp, cat, bins,
                 particles=particles, report=report)
    lightvrt = read_lightvrt(mp, map_name, lambda name, pak: bins.get(name))
    objects = read_regions(mp)
    instances, solids = [], []
    emitted: set[str] = set()
    geometries: dict[int, object] = {}
    skipped = 0

    def inside(x: float, y: float) -> bool:
        return any(c is None or math.hypot(x - c[0], y - c[1]) <= r for c, r in areas)
    for obj in objects:
        x, y, z = obj.position
        if not inside(x, y):
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
        if any(abs(math.sin(a)) > 1e-4 for a in obj.tilt):
            inst["tilt"] = [round(a, 5) for a in obj.tilt]
        if abs(obj.scale - 1) > 1e-6 and obj.scale > 0:
            inst["scale"] = round(obj.scale, 5)
        loaded = None
        if vis.geometry is not None:
            if vis.geometry not in geometries:
                geometries[vis.geometry] = load_geometry(mp, cat, bins, vis.geometry)
            loaded = geometries[vis.geometry]
        if loaded is not None:
            world = np.eye(4)
            world[:3, :3] = obj.matrix() * (obj.scale if obj.scale > 0 else 1.0)
            world[:3, 3] = obj.position
            raw = lightvrt.get((obj.region, obj.index))
            # Données privées (préfixe `_`) pour l'éclairage de chaque scène, retirées du JSON.
            inst["_geo"], inst["_m"] = vis.geometry, world[:3, :3]
            if raw is not None and len(raw) == len(loaded.vertices["position"]):
                inst["_raw"] = raw
            tris = [loaded.indices[e.ib0:e.ib1] for e in loaded.geo.doc.elements
                    if e.material.visible and not e.material.transparent and e.material.texture]
            if tris:
                idx = np.concatenate(tris)
                idx = idx[: len(idx) // 3 * 3]
                pts = np.column_stack([loaded.vertices["position"].astype(np.float64), np.ones(len(loaded.vertices["position"]))])
                solids.append(((pts @ world.T)[:, :3])[idx].reshape(-1, 3, 3))
        instances.append(inst)
    glb = fx.exporter.finish(fx.roots)
    report.append(f"décor {map_name} : {len(instances)} objets posés ({len(emitted)} gabarits), {skipped} sans gabarit visuel, "
                  f"{sum(1 for i in instances if '_raw' in i)} avec éclairage précalculé")
    report += fx.exporter.notes
    return {"glb": glb, "instances": instances, "objects": fx.meta, "sounds": fx.sounds, "geometries": geometries,
            "solids": np.concatenate(solids) if solids else np.zeros((0, 3, 3)),
            "pointLights": point_lights(mp, objects)}


def light_decor(decor: dict, light: dict, center: list[float] | None, radius: float) -> tuple[list[dict], bytes]:
    """Instances d'une scène (dans son cercle) et leur éclairage de sommets (`decor-light.bin`) :
    ambiante + soleil (`N·S`) + octet 2 du `lightvrt`, avec la lumière de la scène."""
    out, blobs, offset = [], [], 0
    for inst in decor["instances"]:
        x, y = inst["p"][0], inst["p"][1]
        if center is not None and math.hypot(x - center[0], y - center[1]) > radius:
            continue
        entry = {k: v for k, v in inst.items() if not k.startswith("_")}
        loaded = decor["geometries"].get(inst.get("_geo"))
        if loaded is not None:
            normals = loaded.vertices.get("normal")
            wn = normals.astype(np.float64) @ inst["_m"].T if normals is not None else None
            if wn is not None:
                wn /= np.maximum(np.linalg.norm(wn, axis=1, keepdims=True), 1e-9)
            if "_raw" in inst:
                colors = encode_light(vertex_light(inst["_raw"], light, wn))
                blobs.append(colors.tobytes())
                entry["light"] = [offset, len(colors)]
                offset += len(colors)
            else:
                entry["ambient"] = [round(float(v), 4) for v in _rgb(light.get("ambient"))]
        out.append(entry)
    return out, b"".join(blobs)


def build_sky(mp: PackDB, cat, bins, textures: TexturePool, light: dict, texture_prefix: str,
              report: list[str]) -> tuple[bytes | None, dict | None]:
    """Ciel d'une scène (`sky.glb`) : tous les calques du `SkyMesh` de la zone, ou de celui du temps
    de la scène (`skyParts`)."""
    parts = light.get("skyParts") or sky_parts(mp, light.get("sky"))
    ex = Exporter(textures, DECOR_TEXTURE_MAX, generator=GENERATOR, texture_prefix=texture_prefix)
    children, radius = [], 0.0
    for geo, _anim, shift in parts:
        loaded = load_geometry(mp, cat, bins, geo)
        if loaded is None:
            continue
        elements = [e for e in loaded.geo.doc.elements if e.material.visible and e.material.texture]
        mesh, _ = ex.emit_mesh("sky", loaded.geo, loaded.vertices, loaded.indices, elements, None)
        if mesh is not None:
            node = {"mesh": mesh}
            if shift:
                node["translation"] = [0.0, 0.0, float(shift)]
            children.append(ex.gltf.add_node(node))
            radius = max(radius, float(np.max(np.abs(np.concatenate(loaded.geo.doc.aabb)))))
    if not children:
        return None, None
    root = ex.gltf.add_node({"name": "sky", "children": children, "extras": {"sky": True}})
    report += ex.notes
    return ex.finish([root]), {"radius": round(radius, 2), "parts": len(children)}


def map_prefix(map_name: str) -> str:
    """Chemin du dossier commun d'une carte vu depuis le dossier d'une scène."""
    return f"../maps/{map_name}/"


def rebase_objects(objects: dict, prefix: str) -> dict:
    """Copie des métadonnées de gabarits, fichiers de particules rapportés au dossier de la carte."""
    out = json.loads(json.dumps(objects))
    for info in out.values():
        system = info.get("particles")
        if isinstance(system, dict) and str(system.get("file", "")).startswith("particles/"):
            system["file"] = prefix + system["file"]
    return out


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


def build_actor_offset(actor: dict, mob: int | None, db: PackDB, cat, bins, textures: TexturePool,
                       report: list[str]) -> tuple[bytes, dict]:
    """Acteur : gabarit de sa `VisualMob` ; un personnage (gabarit à tenue par défaut) est habillé
    par `allods_characters` avec la variation et les objets de sa `VisualMob`."""
    if mob is not None and getattr(db, "parent", None) is not None:
        mob |= EXTERN   # ressource de pack.bin vue depuis la base de carte
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
    # Géosets dont la texture est une relocation de genre 2 (non résolue dans pack.bin : PNJ uniques
    # `Creatures/Rysina`, `Creatures/Mirianna`) : la texture du dossier nommée comme la géométrie,
    # présente dans les paks (`Creatures/Rysina/Rysina.(Texture).bin`).
    stem = (loaded.geo.binary or "").replace(".(Geometry).bin", "")
    fallback = f"{stem}.(Texture).bin" if stem else None
    if fallback and template.default_dress is None and \
            any(e.material.visible and not e.material.texture for e in geo_elements) and bins.get(fallback):
        for e in geo_elements:
            if e.material.visible and not e.material.texture:
                e.material.texture = fallback
        report.append(f"{actor['id']} : texture de géométrie par le nom : {fallback}")
    untextured = any(e.material.visible and not e.material.texture for e in geo_elements)
    if template.default_dress is not None or (template.variations is not None and untextured):
        # Personnage, ou PNJ unique habillé comme un personnage (`Creatures/Mirianna` : géosets
        # sans texture, peau et tenue données par la `VisualMob`).
        variation = read_variation(db, cat, visual + VM_VARIATION)
        items = [read_visual_item(db, cat, off) for off in visual_dress(db, visual)]
        skin = template.main_texture or (template.variations.main_textures[0]
                                         if template.variations and template.variations.main_textures else None)
        appearance = resolve_appearance(template, [e.name for e in geo_elements],
                                        {e.name: e.material.texture or skin for e in geo_elements if e.material.visible},
                                        variation=variation, items=items)
        override = dict(appearance.replacements)
        base = textures.image(skin, 2048) if skin else None
        if base is not None:
            image_of = lambda name: textures.image(name, 2048)  # noqa: E731
            mask = textures.image(appearance.skin_mask, 2048) if appearance.skin_mask else None
            baked_name = f"actors/{actor['id']}-skin"
            textures.add_image(baked_name, bake_skin(base, appearance, image_of, mask, min(max(base.size), ACTOR_TEXTURE_MAX)),
                               ACTOR_TEXTURE_MAX)
            for e in geo_elements:
                if e.name not in override and (e.material.texture == skin or not e.material.texture):
                    override[e.name] = baked_name
        visible = set(appearance.visible)
        elements = [e for e in geo_elements if e.name in visible]
        ex.tints = appearance.tints
        for item in [i for i in [template.default_dress] if i is not None] + variation.items() + items:
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
            if anim not in ("Idle", "Idle01"):
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
             report: list[str], texture_prefix: str = "textures/") -> tuple[bytes | None, dict, set[str], list[dict]]:
    fx = FxBuild(Exporter(textures, DECOR_TEXTURE_MAX, generator=GENERATOR, texture_prefix=texture_prefix), db, cat, bins,
                 particles=particles, report=report)
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


def grouped_wave(event: str, index: dict, prefer: str = "") -> tuple[str, int, str] | None:
    """Onde d'une voix rangée par groupe : `FerrisRaid602/FR_PreRaidRysina01` → onde `Rysina01` de
    la banque `Voice_FerrisRaid602Pre_rus` (le groupe dans le nom de banque, la fin de l'événement
    comme nom d'onde, et le reste du nom — `Pre` — pour départager `…Pre`, `…Portal`, `…General`)."""
    parts = event.split("/")
    if len(parts) < 2:
        return None
    group, tail = _key(parts[0]), _key(parts[-1])
    best, best_score = None, 0
    for k in range(len(tail) - 4, 0, -1):
        key, rest = tail[k:], tail[:k]
        for bank, sub, name in index.get(key, []):
            bank_key = _key(bank.split("/")[-1])
            if group not in bank_key:
                continue
            extra = bank_key.replace(group, " ")
            overlap = max((n for n in range(len(rest), 2, -1) for i in range(len(rest) - n + 1) if rest[i:i + n] in extra),
                          default=0)
            score = len(key) * 100 + overlap * 10 + int(bool(prefer) and prefer in bank) * 5 + int("rus" in bank_key)
            if score > best_score:
                best, best_score = (bank, sub, name), score
    return best


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
    grouped = grouped_wave(event, index, prefer)
    if grouped is not None:
        return grouped
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


def export_voices(events: list[str | None], bins, out_dir: Path, vgmstream: Path, report: list[str],
                  index: dict) -> list[dict | None]:
    """Voix des répliques : onde nommée comme la fin de l'événement (`Cutscenes/Eden2/Prologue04_Cutscene_1`
    → `Prologue04_Cutscene_1`), cherchée dans les banques `SFX/Voice/*` d'abord."""
    out_dir.mkdir(parents=True, exist_ok=True)
    result: list[dict | None] = []
    with tempfile.TemporaryDirectory(prefix="allodex-voice-") as tmp:
        for n, event in enumerate(events, 1):
            hit = find_wave(event, index, "SFX/Voice/") if event else None
            if hit is None:
                if event:
                    report.append(f"voix introuvable : {event}")
                result.append(None)
                continue
            bank, sub, stream = hit
            raw = bins.get(bank)
            if bank.lower().endswith(".bsb"):
                raw = zlib.decompress(raw)
            fsb = Path(tmp) / "bank.fsb"
            fsb.write_bytes(raw[raw.find(b"FSB5"):])
            wav = Path(tmp) / f"{n}.wav"
            subprocess.run([str(vgmstream), "-i", "-s", str(sub), "-o", str(wav), str(fsb)], check=True, capture_output=True)
            base = out_dir / f"{n:02d}"
            for ext, args in (("ogg", ["-c:a", "libopus", "-b:a", "48k"]), ("mp3", ["-c:a", "libmp3lame", "-b:a", "64k"])):
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-ac", "1", *args,
                                str(base.with_suffix(f".{ext}"))], check=True)
            duration = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                             "default=nw=1:nk=1", str(base.with_suffix(".ogg"))],
                                            capture_output=True, text=True).stdout.strip() or 0)
            result.append({"event": event, "wave": stream, "bank": bank, "ogg": f"voice/{n:02d}.ogg",
                           "mp3": f"voice/{n:02d}.mp3", "duration": round(duration, 3)})
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


def schedule_lines(spec: dict, camera: dict, voices: list[dict | None], lines: list) -> list[float]:
    """Départ de chaque réplique (scènes sans déroulé serveur) : chaque groupe du manifeste s'ouvre au
    début du tronçon de caméra indiqué (+ `lead`), les répliques d'un groupe s'enchaînent à la fin de
    la voix précédente (+ `gap`)."""
    starts = [0.0] * len(lines)
    times = [k["t"] for k in camera["points"]]
    lead, gap = spec["timing"].get("lead", 0.5), spec["timing"].get("gap", 0.6)
    for group in spec["timing"]["groups"]:
        t = times[group["segment"]] + lead
        for n in group["lines"]:
            i = n - 1
            starts[i] = round(t, 3)
            length = voices[i]["duration"] if voices[i] else lines[i]["duration"]
            t += length + gap
    return starts


def place(point: list[float], solids: np.ndarray, ground: bool) -> list[float]:
    """Pose un point sur le décor (`ground`) : z = surface opaque sous `point[2]`."""
    if not ground:
        return [round(float(v), 4) for v in point]
    z = ground_z(solids, point[0], point[1], point[2] if len(point) > 2 else 1e9)
    return [round(point[0], 4), round(point[1], 4), round(z if z is not None else point[2], 4)]


def face_yaw(position: list[float], face: list[float]) -> float:
    return round(math.atan2(face[1] - position[1], face[0] - position[0]) - MODEL_FORWARD, 4)


def clip_name(anim: str) -> str:
    """Nom d'animation du jeu (`emoteSpeech`) → nom de fichier (`EmoteSpeech`)."""
    return anim[:1].upper() + anim[1:]


class Texts:
    """Textes des répliques : RU/EN du 17.0 par indice ; FR du client 16.0 par l'événement de voix de
    son `ClientData` (même voix, autre construction), sinon par décalage d'indice ancré."""

    def __init__(self, manifest: dict, report: list[str]) -> None:
        main_spec, fr_spec = manifest["sources"]["main"], manifest["sources"]["fr"]
        self.main = load_textset(Path(main_spec["root"]), main_spec)
        try:
            self.fr = load_textset(Path(fr_spec["root"]), fr_spec)
        except (OSError, KeyError, zipfile.BadZipFile) as exc:
            report.append(f"textes FR illisibles : {exc}")
            self.fr = None
        self.fr_voice: dict[str, tuple[int, int]] = {}
        self.fr_root = Path(fr_spec["root"])

    def load_fr_voices(self) -> None:
        if self.fr_voice or self.fr is None:
            return
        from tools.allods_packdb import default_cache_dir
        from tools.allods_scenes import PackBinView
        from tools.packbin import PackBin
        pak = self.fr_root / "data" / "Packs" / "BaseLocfra_x64.pak"
        stat = pak.stat()
        raw_path = default_cache_dir() / f"pack-fr-{stat.st_size}-{int(stat.st_mtime)}.raw"
        if not raw_path.is_file():
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_bytes(zlib.decompress(zipfile.ZipFile(pak).read("Bin/pack.bin")))
        pb = PackBin(raw_path.read_bytes())
        view = PackBinView(pb)
        for off in pb.objects_of("ClientData"):
            try:
                cl = read_client_line(view, off)
            except Exception:  # noqa: BLE001 — ClientData d'une autre forme
                continue
            if cl.voice and cl.text_index is not None:
                self.fr_voice.setdefault(cl.voice, (cl.text_index, cl.delay_ms))

    def line(self, idx: int | None, voice: str | None, delay_ms: int, anchor_delta: int | None) -> dict:
        text: dict[str, str] = {}
        if idx is not None:
            text["ru"] = clean_text(self.main.texts["ru"][idx])
            en = clean_text(self.main.texts["en"][idx])
            if en and not has_cyrillic(en):
                text["en"] = en
        if self.fr is not None:
            self.load_fr_voices()
            j = None
            if voice and voice in self.fr_voice:
                j = self.fr_voice[voice][0]
            elif anchor_delta is not None and idx is not None and self.fr.subtitles.get(idx - anchor_delta) == delay_ms:
                j = idx - anchor_delta
            if j is not None and j < len(self.fr.texts["fr"]):
                text["fr"] = clean_text(self.fr.texts["fr"][j])
        return text


class ClientLines:
    """Répliques du 17.0 indexées par événement de voix et par texte russe."""

    def __init__(self, db: PackDB, texts: Texts) -> None:
        from tools.extract_cinematics import norm_key
        self.by_voice: dict[str, list[int]] = {}
        self.by_text: dict[str, list[int]] = {}
        self.lines: dict[int, object] = {}
        for off in db.resources("ClientData"):
            try:
                cl = read_client_line(db, off)
            except Exception:  # noqa: BLE001
                continue
            if not (cl.voice or cl.text_index is not None):
                continue
            self.lines[off] = cl
            if cl.voice:
                self.by_voice.setdefault(cl.voice, []).append(off)
            if cl.text_index is not None and cl.text_index < len(texts.main.texts["ru"]):
                self.by_text.setdefault(norm_key(texts.main.texts["ru"][cl.text_index]), []).append(off)

    def find(self, voice: str | None, ru: str) -> object | None:
        from tools.extract_cinematics import norm_key
        for key, table in ((voice, self.by_voice), (norm_key(ru) if ru else None, self.by_text)):
            if key and key in table:
                return self.lines[table[key][0]]
        return None


def find_mob_by_name(db: PackDB, cat, texts: Texts, name: str, model_hint: str) -> int | None:
    """`MobWorld` du 17.0 au nom russe `name` ; entre plusieurs, celui dont le modèle vient du même
    dossier que le `MobWorld` 7.0 (`Characters/Hadagan_male/…`)."""
    from tools.extract_cinematics import norm_key
    want = norm_key(name)
    ru = texts.main.texts["ru"]
    hint = "/".join(model_hint.split("/")[:2]).lower() if model_hint else ""
    best = None
    for off in db.resources("MobWorld"):
        idx = mob_name_index(db, off)
        if idx >= len(ru) or norm_key(ru[idx]) != want:
            continue
        visual = mob_visual(db, off)
        tpl = visual_template(db, visual) if visual is not None else None
        if tpl is None:
            continue
        best = best or off
        vot = db.ptr(tpl + 0x90)
        geo = db.ptr(vot + 0xC0) if vot is not None else None
        path = (cat.name(db.binary_ref(geo)) or "").lower() if geo is not None else ""
        if hint and path.startswith(hint):
            return off
    return best


# Mots des noms de `MobWorld` qui ne désignent pas le PNJ (`CutScene_BossLast`, `Cut_Scene_Boss`).
GENERIC_TOKENS = {"cutscene", "cut", "scene", "cs", "mob", "npc"}


def summon_actors(spec: dict, tl, spawns: dict, db: PackDB, cat, texts: Texts, report: list[str]) -> dict[str, dict]:
    """PNJ invoqués par le déroulé (`ImpactSummon`) → acteurs, un par nom : chaque invocation le
    (ré)apparaît sur son repère, `ImpactGoTo` le fait marcher (à la `walkSpeed` du `MobWorld`)
    jusqu'au repère visé, `Disintegrate` le retire (`presence`)."""
    groups: dict[str, dict] = {}
    for summon in tl.summons:
        loc = spawns.get(summon["locator"])
        if loc is None:
            report.append(f"{spec['id']} : repère introuvable : {summon['locator']}")
            continue
        name = summon["name"] or summon["mob"]
        # Un même PNJ réinvoqué reprend son acteur une fois le précédent retiré ; deux présents à la
        # fois (le jeu en montre alors deux) font deux acteurs.
        twins = [a for a in groups.values() if a["name"] == name]
        actor = next((a for a in twins if a["presence"][-1][1] <= summon["t"] + 1e-3), None)
        if actor is None:
            mob = find_mob_by_name(db, cat, texts, summon["name"], summon.get("visual") or summon["mob"] or "")
            if mob is None:
                report.append(f"{spec['id']} : PNJ invoqué introuvable dans le 17.0 : {summon['name']}")
                continue
            tokens = [t for t in Path(summon["mob"] or "x").name.split(".")[0].lower().split("_") if t not in GENERIC_TOKENS]
            stem = tokens[0] if tokens else "summon"
            base = re.sub(r"[^a-z0-9]+", "-", stem).strip("-") or "summon"
            used = {a["id"] for a in groups.values()}
            ident, n = base, 1
            while ident in used:
                n += 1
                ident = f"{base}-{n}"
            actor = {"id": ident, "name": name, "mob_offset": mob,
                     "path": [], "presence": [], "move": "Walk", "voice_key": stem, "summons": [], "server": summon}
            groups[summon["id"]] = actor
        actor["summons"].append(summon["id"])
        path = actor["path"]
        pos = [round(v, 4) for v in loc["p"]]
        yaw = summon["yaw"] if summon["yaw"] is not None else loc["yaw"]
        if path and path[-1]["t"] < summon["t"] - 2e-3:
            path.append({"t": round(summon["t"] - 1e-3, 3), "p": path[-1]["p"], "yaw": path[-1]["yaw"]})
        path.append({"t": summon["t"], "p": pos, "yaw": round(yaw, 5)})
        t, here = summon["t"], np.array(pos, float)
        for move in summon["moves"]:
            dest = spawns.get(move["locator"])
            if dest is None:
                report.append(f"{spec['id']} : repère introuvable : {move['locator']}")
                continue
            there = np.array(dest["p"], float)
            start = max(move["t"], t)
            heading = face_yaw(list(here), list(there))
            if start - t > 2e-3:
                path.append({"t": round(start, 3), "p": path[-1]["p"], "yaw": path[-1]["yaw"]})
            else:
                path[-1]["yaw"] = heading
            t = start + float(np.linalg.norm(there[:2] - here[:2])) / max(summon["walkSpeed"], 0.1)
            path.append({"t": round(t, 3), "p": [round(float(v), 4) for v in there], "yaw": heading})
            here = there
        actor["presence"].append([summon["t"], summon["until"]])
    return groups


def voice_speaker(line: dict, summoned: dict[str, dict], spec: dict) -> str | None:
    """Locuteur d'une réplique posée sur le joueur : l'acteur invoqué présent dont le nom de modèle
    (`Rysina_CutScene`) figure dans l'événement de voix (`FR_PreRaidRysina01`) ; le manifeste
    donne les autres (`speakers` : `{"Vayatel": "colossus"}` — le Ваятель est un Колосс)."""
    voice = (line.get("voice") or "").lower()
    aliases = {k.lower(): v.lower() for k, v in spec.get("speakers", {}).items()}
    wanted = {v for k, v in aliases.items() if k in voice}
    for key, actor in summoned.items():
        present = any(a - 1e-3 <= line["t"] < b for a, b in actor["presence"])
        names = {actor["voice_key"], (actor.get("name") or "").lower()}
        if present and (actor["voice_key"] in voice or names & wanted):
            return key
    return None


def plan_xdb70(spec: dict, root: Path, db: PackDB, cat, texts: Texts, lines17: ClientLines, anim_names: dict,
               report: list[str]) -> dict:
    """Plan d'une scène de 7.0 ou d'avant : déroulé serveur de l'arbre 7.0 (`tools/cutscene_xdb70.py`)
    rapporté aux ressources du 17.0 (répliques, PNJ)."""
    from tools import cutscene_xdb70 as x70
    tl = x70.simulate(root, spec["first_buff"])
    map_name = spec.get("map") or sorted(tl.maps)[0]
    spawns = x70.find_spawns(root, map_name, tl.scripts)
    camera = x70.camera_keys(tl.shots)
    camera["duration"] = round(tl.duration, 3)
    actors: dict[str, dict] = {}
    for script, sp in spawns.items():
        if sp["mob"] is None:            # repère nu : place d'une invocation ou but d'une marche
            continue
        mob = find_mob_by_name(db, cat, texts, sp["name"], sp.get("visual") or sp["mob"] or "")
        if mob is None:
            report.append(f"{spec['id']} : PNJ introuvable dans le 17.0 : {sp['name']} ({script})")
            continue
        actors[script] = {"id": re.sub(r"[^a-z0-9]+", "-", script.lower()).strip("-"), "mob_offset": mob,
                          "path": [{"t": 0, "p": sp["p"], "yaw": round(sp["yaw"], 5)}], "server": sp}
    summoned = summon_actors(spec, tl, spawns, db, cat, texts, report)
    for key, info in summoned.items():
        actors[key] = info
    plan_lines = []
    for line in tl.lines:
        if not line["ru"] and not line["voice"]:
            continue
        if line["speaker"] == "player":
            line["speaker"] = voice_speaker(line, summoned, spec) or "player"
        cl = lines17.find(line["voice"], line["ru"])
        idx = cl.text_index if cl is not None else None
        text = texts.line(idx, line["voice"], line["delay_ms"], None)
        if "ru" not in text and line["ru"]:
            text["ru"] = line["ru"]
        speaker = actors.get(line["speaker"], {}).get("id") or \
            next((a["id"] for a in summoned.values() if line["speaker"] in a["summons"]), None)
        plan_lines.append({"start": line["t"], "duration": line["delay_ms"] / 1000.0, "voice_event": line["voice"],
                           "speaker": speaker, "clips": [clip_name(a) for a in line["animations"]], "text": text,
                           "source": line["clientdata"]})
    # Animations posées par buff sur un PNJ (`CreatureAnimationAction` : `LOOP`, sinon une fois).
    for effect in tl.effects:
        if effect["kind"] != "CreatureAnimationAction" or not effect.get("animations"):
            continue
        info = actors.get(effect["target"]) or next((a for a in summoned.values() if effect["target"] in a["summons"]), None)
        if info is None:
            continue
        info.setdefault("actions", []).append({"t": effect["t"], "until": effect["until"],
                                               "clips": [clip_name(a) for a in effect["animations"]],
                                               "loop": effect.get("mode") == "LOOP"})
    for info in actors.values():
        used = sorted({c for l in plan_lines if l["speaker"] == info["id"] for c in l["clips"]} |
                      {c for a in info.get("actions", []) for c in a["clips"]})
        info.update({"animations": used, "clips_wanted": used})
    weather = [w for w in tl.weather if (w["until"] - w["t"]) >= 0.8 * tl.duration - tl.weather[0]["t"]] if tl.weather else []
    sounds = {"music": [], "ambience": []}
    for snd in tl.sounds:
        key = "music" if snd["kind"] == "Music" else "ambience"
        sounds[key].append({"event": snd["name"], "t": snd["t"], "until": snd["until"]})
    post = [{"t": p["t"], "until": p["until"], "kind": "veil", "fadeIn": p["fadeIn"], "fadeOut": p["fadeOut"]}
            for p in tl.post if p["black"]]
    centre = np.mean([k["p"] for k in camera["points"]], axis=0) if camera["points"] else np.zeros(3)
    return {"map": map_name, "camera": camera, "lines": plan_lines, "actors": list(actors.values()),
            "weather": weather[0] if weather else None, "sounds": sounds, "post": post,
            "decor_center": [float(centre[0]), float(centre[1])], "timing": "server",
            "sources": {"timeline": spec["first_buff"], "buffs": [b["buff"] for b in tl.buffs],
                        "spawns": sorted({sp["file"] for sp in spawns.values()})}}


def plan_manual(spec: dict, db: PackDB, texts: Texts, lines17: ClientLines, anim_names: dict, report: list[str]) -> dict:
    """Plan d'une scène sans déroulé serveur connu (après 7.0) : ressources du 17.0 nommées par le
    manifeste, mise en scène et minutage du manifeste."""
    track = buff_camera_track(db, db.ids[int(spec["buff"])])
    camera = camera_keys(track)
    plan_lines = []
    anchor = None
    for n, rid in enumerate(spec["lines"], 1):
        cd = db.ids.get(int(rid))
        if cd is None:
            raise ValueError(f"ClientData {rid} introuvable")
        cl = read_client_line(db, cd)
        if anchor is None and spec.get("fr_anchor") and texts.fr is not None and cl.text_index is not None:
            anchor = cl.text_index - texts.fr.find("fr", spec["fr_anchor"])
        text = texts.line(cl.text_index, cl.voice, cl.delay_ms, anchor)
        speaker = next((a["id"] for a in spec["actors"] if any(text.get("ru", "").startswith(p) for p in a.get("speaker_prefixes", []))), None)
        actor = next((a for a in spec["actors"] if a["id"] == speaker), None)
        clips = [actor["talk"]] if actor and actor.get("talk") and cl.animations else []
        plan_lines.append({"start": None, "duration": cl.delay_ms / 1000.0, "voice_event": cl.voice, "speaker": speaker,
                           "clips": clips, "text": text, "source": f"ClientData {rid}"})
    actors = []
    for a in spec["actors"]:
        entry = dict(a)
        entry["mob_offset"] = pack_offset(db, a["mob"])
        entry["path"] = a.get("path") or [{"t": 0, "p": a["position"], "face": a.get("face")}]
        actors.append(entry)
    return {"map": spec["map"], "camera": camera, "lines": plan_lines, "actors": actors, "weather": None,
            "sounds": {"music": [], "ambience": []}, "post": spec.get("post", []),
            "decor_center": spec.get("decor_center"), "timing": "estimated", "sources": spec.get("sources", {})}


def weather_light(weather: dict, base: dict) -> dict:
    """Lumière d'un `WeatherCreatureVisAction` (valeurs ARGB signées du `.xdb`) au format de la zone."""
    light = dict(base)
    values = weather.get("light", {})

    def num(tag: str):
        try:
            return float(values[tag]) if tag in values else None
        except (TypeError, ValueError):
            return None
    for key, tag in (("ambient", "AmbientColor"), ("diffuse", "DiffuseColor"), ("fog", "FogColor"),
                     ("pointLight", "PointLightColor"), ("selfIllum", "SelfIllumColor"), ("specular", "SpecularColor")):
        v = num(tag)
        if v is not None:
            light[key] = int(v) & 0xFFFFFFFF
    for key, tag in (("fogStart", "FogStart"), ("fogEnd", "FogEnd"), ("sunYaw", "SunLightYaw"), ("sunPitch", "SunLightPitch"),
                     ("desaturation", "desaturation")):
        v = num(tag)
        if v is not None:
            light[key] = v
    return light


def weather_sky(root: Path, db: PackDB, cat, sky_path: str) -> list[tuple[int, int | None, float]]:
    """Calques 17.0 du `SkyMesh` d'un déroulé 7.0 : le `SkyMesh` du client dont un calque porte la
    géométrie d'un des calques du `.xdb` (la ressource a pu changer de calques depuis)."""
    from xml.etree import ElementTree as ET
    try:
        doc = ET.fromstring((Path(root) / sky_path).read_bytes())
    except (OSError, ET.ParseError):
        return []
    base = (Path(root) / sky_path).parent
    wanted = set()
    for e in doc.iter("geometry"):
        href = (e.get("href") or "").split("#")[0]
        if href:
            path = Path(root) / href.lstrip("/") if href.startswith("/") else base / href
            wanted.add(path.resolve().relative_to(Path(root).resolve()).as_posix().replace("(Geometry).xdb", "(Geometry).bin").lower())
    root_db = getattr(db, "parent", None) or db
    for sky in root_db.resources("SkyMesh"):
        parts = sky_parts(root_db, sky)
        if any((cat.name(root_db.binary_ref(g)) or "").lower() in wanted for g, _, _ in parts):
            ext = EXTERN if root_db is not db else 0
            return [(g | ext, (a | ext) if a is not None else None, sh) for g, a, sh in parts]
    return []


# --- export ---------------------------------------------------------------------------------------

def scene_area(spec: dict, plan: dict) -> tuple[list[float] | None, float]:
    return spec.get("decor_center") or plan.get("decor_center"), float(spec.get("decor_radius", 150))


def scene_light(spec: dict, plan: dict, mp: PackDB, cat, root: Path, report: list[str]) -> dict:
    """Éclairage d'une scène : celui de la zone, remplacé par le temps du déroulé s'il en pose un."""
    light = read_zone_light(mp)
    if plan["weather"]:
        light = weather_light(plan["weather"], light)
        if plan["weather"].get("sky"):
            parts = weather_sky(root, mp, cat, plan["weather"]["sky"])
            if parts:
                light["skyParts"] = parts
            else:
                report.append(f"{spec['id']} : ciel du déroulé introuvable dans le 17.0 : {plan['weather']['sky']}")
    return light


def build_map(map_name: str, specs: list[dict], plans: dict[str, dict], db: PackDB, client: Path, bins, root: Path,
              out_root: Path, report: list[str]) -> dict:
    """Dossier commun d'une carte (`engine/maps/<carte>/`) : décor des zones de toutes ses scènes,
    textures du décor, des effets et des ciels, particules et leur atlas ; puis, dans le dossier de
    chaque scène, son ciel (`sky.glb`) et ses effets (`fx.glb`), qui y renvoient."""
    mp = open_map(db, client, map_name)
    cat = open_catalog(mp, client)
    map_dir = out_root / "engine" / "maps" / map_name
    for stale in ("textures", "particles"):
        shutil.rmtree(map_dir / stale, ignore_errors=True)
    map_dir.mkdir(parents=True, exist_ok=True)
    textures = TexturePool(mp, cat, bins, map_dir, jpeg=True)
    particles = ParticlePool(mp, cat, bins, map_dir)
    decor = build_decor(mp, cat, bins, textures, particles, map_name, [scene_area(s, plans[s["id"]]) for s in specs], report)
    (map_dir / "decor.glb").write_bytes(decor["glb"])
    prefix = map_prefix(map_name) + "textures/"
    lights, fx, sky = {}, {}, {}
    for spec in specs:
        out = out_root / "engine" / spec["id"]
        out.mkdir(parents=True, exist_ok=True)
        lights[spec["id"]] = light = scene_light(spec, plans[spec["id"]], mp, cat, root, report)
        sky_glb, sky_meta = build_sky(mp, cat, bins, textures, light, prefix, report)
        sky[spec["id"]] = (sky_glb, sky_meta)
        (out / "sky.glb").write_bytes(sky_glb) if sky_glb else (out / "sky.glb").unlink(missing_ok=True)
        fx_glb, fx_objects, fx_sounds, spawns = build_fx(spec.get("spawns", []), mp, cat, bins, textures, particles, report,
                                                         texture_prefix=prefix)
        fx[spec["id"]] = (fx_glb, fx_objects, fx_sounds, spawns)
        (out / "fx.glb").write_bytes(fx_glb) if fx_glb else (out / "fx.glb").unlink(missing_ok=True)
    atlas = particles.write_atlas(textures)
    report.append(f"carte {map_name} : décor {len(decor['glb']) / 1e6:.1f} Mo, textures {textures.bytes_written / 1e6:.1f} Mo, "
                  f"particules {particles.bytes_written / 1e6:.2f} Mo, pour {len(specs)} scène(s)")
    return {"mp": mp, "cat": cat, "decor": decor, "lights": lights, "fx": fx, "sky": sky, "atlas": atlas}


def run(manifest: dict, out_root: Path, client: Path, only: list[str] | None, voices: bool, vgmstream: Path,
        server_root: Path | None = None) -> list[str]:
    report: list[str] = []
    db = open_pack(client)
    packs = client / "data" / "Packs"
    bins = BinSource([], [str(packs / "*.pak")])
    texts = Texts(manifest, report)
    anim_names = animation_names(db)
    lines17 = ClientLines(db, texts)
    root = Path(server_root or manifest.get("server_root") or "/mnt/f/ALLODS ONLINE SERVER/Allods 7.0/game/data")
    index = sound_index(bins, Path(os.environ.get("ALLODEX_CACHE") or Path.home() / ".cache" / "allodex"))
    entries = []
    pack_cat = open_catalog(db, client)
    # Plans de toutes les scènes : le décor d'une carte est commun à toutes celles qui s'y jouent,
    # il couvre donc leurs zones à toutes, même quand une seule est réextraite (`--only`).
    plans: dict[str, dict] = {}
    for spec in manifest["engine_scenes"]:
        plans[spec["id"]] = plan_xdb70(spec, root, db, pack_cat, texts, lines17, anim_names, report) \
            if spec.get("source") == "xdb70" else plan_manual(spec, db, texts, lines17, anim_names, report)
    wanted_maps = {plans[s["id"]]["map"] for s in manifest["engine_scenes"] if not only or s["id"] in only}
    maps: dict[str, dict] = {}
    for map_name in sorted(wanted_maps):
        on_map = [s for s in manifest["engine_scenes"] if plans[s["id"]]["map"] == map_name]
        maps[map_name] = build_map(map_name, on_map, plans, db, client, bins, root, out_root, report)
    for spec in manifest["engine_scenes"]:
        if only and spec["id"] not in only:
            continue
        plan = plans[spec["id"]]
        ctx = maps[plan["map"]]
        mp, cat, prefix = ctx["mp"], ctx["cat"], map_prefix(plan["map"])
        out = out_root / "engine" / spec["id"]
        out.mkdir(parents=True, exist_ok=True)
        for stale in ("textures", "particles", "decor.glb"):   # décor et particules : dossier de la carte
            path = out / stale
            shutil.rmtree(path, ignore_errors=True) if path.is_dir() else path.unlink(missing_ok=True)
        textures = TexturePool(mp, cat, bins, out, jpeg=True)          # textures des acteurs
        light = ctx["lights"][spec["id"]]
        camera = plan["camera"]
        camera["fov"] = spec.get("fov", 45)
        decor = ctx["decor"]
        center, radius = scene_area(spec, plan)
        instances, light_blob = light_decor(decor, light, center, radius)
        (out / "decor-light.bin").write_bytes(light_blob)
        solids = decor["solids"]

        # voix d'abord : le minutage estimé (scènes sans déroulé) en dépend
        events = [l["voice_event"] for l in plan["lines"]]
        voice_meta: list[dict | None] = [None] * len(events)
        if voices:
            voice_meta = export_voices(events, bins, out / "voice", vgmstream, report, index)
        elif (out / "scene.json").is_file():
            old = json.loads((out / "scene.json").read_text(encoding="utf-8"))
            old_lines = old.get("lines", [])
            if len(old_lines) == len(events):
                voice_meta = [l.get("voice") for l in old_lines]
        if plan["timing"] == "estimated":
            starts = schedule_lines(spec, camera, voice_meta, plan["lines"])
            for line, t in zip(plan["lines"], starts):
                line["start"] = t

        actors_meta = []
        built: dict = {}
        shutil.rmtree(out / "actors", ignore_errors=True)
        # Animations voulues par modèle : les doubles d'un même PNJ partagent un seul fichier.
        clips_of: dict[int, set[str]] = {}
        for actor in plan["actors"]:
            clips_of.setdefault(actor["mob_offset"], set()).update(
                set(actor.get("animations", [])) | {actor.get("idle") or "Idle", "Idle01", "Idle"} |
                set(actor.get("clips_wanted", [])) | ({actor["move"]} if actor.get("move") else set()))
        for actor in plan["actors"]:
            spec_actor = {"id": actor["id"], "mob": None, "sex": actor.get("sex"), "animations": sorted(clips_of[actor["mob_offset"]])}
            glb = f"actors/{actor['id']}.glb"
            twin = built.get((actor["mob_offset"], tuple(spec_actor["animations"])))
            if twin is not None:          # même PNJ en double (deux invocations à la fois) : même modèle
                glb, meta = twin[0], json.loads(json.dumps(twin[1]))
            else:
                data, meta = build_actor_offset(spec_actor, actor["mob_offset"], mp, cat, bins, textures, report)
                (out / "actors").mkdir(exist_ok=True)
                (out / "actors" / f"{actor['id']}.glb").write_bytes(data)
                built[(actor["mob_offset"], tuple(spec_actor["animations"]))] = (glb, json.loads(json.dumps(meta)))
            idle = actor.get("idle") or next((c for c in ("Idle01", "Idle") if c in meta["animations"]), None)
            ground = bool(actor.get("ground"))
            path = []
            for key in actor["path"]:
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
            actors_meta.append({"id": actor["id"], "glb": glb,
                                "name": {"ru": clean_text(texts.main.texts["ru"][name_idx]), "en": clean_text(texts.main.texts["en"][name_idx])},
                                "path": path, "scale": actor.get("scale", 1.0), "idle": idle,
                                "talk": actor.get("talk"), "move": actor.get("move"), "appear": actor.get("appear", 0.0),
                                **({"presence": actor["presence"]} if actor.get("presence") else {}),
                                **({"actions": sorted(actor["actions"], key=lambda a: a["t"])} if actor.get("actions") else {}),
                                "light": light_at(path[0]["p"], decor["pointLights"], light), **meta})

        fx_glb, fx_objects, fx_sounds, spawns = ctx["fx"][spec["id"]]
        spawns = json.loads(json.dumps(spawns))
        for spawn in spawns:
            if "p" in spawn:
                spawn["p"] = place(spawn["p"], solids, bool(spawn.pop("ground", False)))
        sky_glb, sky = ctx["sky"][spec["id"]]
        objects = rebase_objects({**decor["objects"], **fx_objects}, prefix)

        cue_lines = [Line(l["duration"], l["text"]) for l in plan["lines"]]
        cues = build_cues(cue_lines, [l["start"] for l in plan["lines"]], camera["duration"])
        tracks = []
        for lang in LANGS:
            vtt = to_vtt(cues, lang)
            path = out / f"{lang}.vtt"
            if vtt:
                path.write_text(vtt, encoding="utf-8")
                tracks.append({"lang": lang, "label": LANG_LABELS[lang], "src": f"engine/{spec['id']}/{lang}.vtt",
                               "lines": sum(1 for c in cues if lang in c[2])})
            elif path.exists():
                path.unlink()

        audio = map_sounds(mp)
        timed = plan["sounds"]
        for key in ("music", "ambience"):
            if timed.get(key):
                audio[key] = []   # le déroulé remplace la musique et l'ambiance de la carte
        audio.update({k: v for k, v in spec.get("audio", {}).items() if not k.startswith("_")})
        wanted = set(decor["sounds"]) | set(fx_sounds) | set(audio.get("music", [])) | set(audio.get("ambience", [])) | \
            {s["event"] for key in ("music", "ambience") for s in timed.get(key, [])}
        waves = export_waves(wanted, bins, out, vgmstream, report, camera["duration"] + 1) if voices or not (out / "scene.json").is_file() else \
            json.loads((out / "scene.json").read_text(encoding="utf-8")).get("sounds", {}).get("waves", {})
        for info in objects.values():
            if info.get("sound") in waves:
                info["sfx"] = waves[info["sound"]]["file"]

        def loops(key: str) -> list:
            out_list: list = [waves[m]["file"] for m in audio.get(key, []) if m in waves]
            out_list += [{"file": waves[s["event"]]["file"], "t": s["t"], "until": s["until"]}
                         for s in timed.get(key, []) if s["event"] in waves]
            return out_list

        atlas = json.loads(json.dumps(ctx["atlas"])) if ctx["atlas"] else None
        if atlas:
            atlas["file"] = prefix + atlas["file"]
        scene_lines = []
        for i, line in enumerate(plan["lines"]):
            scene_lines.append({"n": i + 1, "start": line["start"], "duration": line["duration"], "speaker": line["speaker"],
                                "voice": voice_meta[i], "clips": line["clips"], "animations": line["clips"],
                                "text": line["text"], "source": line["source"]})
        zone = {k: v for k, v in light.items() if k not in ("sky", "skyGeometry", "skyParts")}
        scene = {
            "id": spec["id"], "map": plan["map"], "up": [0, 0, 1], "mirror": True, "duration": camera["duration"],
            "timing": plan["timing"], "camera": camera, "lines": scene_lines, "actors": actors_meta,
            "decor": {"glb": prefix + "decor.glb", "light": "decor-light.bin", "instances": instances, "sky": sky,
                      "skyGlb": "sky.glb" if sky_glb else None},
            "fx": {"glb": "fx.glb" if fx_glb else None, "spawns": spawns},
            "objects": objects, "particleAtlas": atlas,
            "light": {**zone, "sunDirection": [round(float(v), 4) for v in sun_direction(light)]},
            "pointLights": decor["pointLights"],
            "sounds": {"music": loops("music"), "ambience": loops("ambience"), "events": audio, "waves": waves,
                       "volume": spec.get("mix", {})},
            "post": plan["post"], "sources": plan["sources"],
        }
        (out / "scene.json").write_text(json.dumps(scene, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        report.append(f"{spec['id']} : {len(instances)} objets du décor de {plan['map']}, textures des acteurs "
                      f"{textures.bytes_written / 1e6:.1f} Mo, {len(actors_meta)} acteurs, {len(spawns)} effets, "
                      f"{len(waves)} sons, {len(scene_lines)} répliques, {camera['duration']:.0f} s")
        entries.append({"spec": spec, "duration": camera["duration"], "tracks": tracks, "lines": len(scene_lines),
                        "timing": plan["timing"]})
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
            "subtitles": {"status": "official", "lines": e["lines"], "timing": e.get("timing", "estimated"), "audio": {"language": "ru"}},
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
