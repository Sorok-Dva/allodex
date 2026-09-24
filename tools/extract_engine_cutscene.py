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
import io
import json
import math
import os
import re
import shutil
import struct
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

from tools.allods_fev import FevResolver  # noqa: E402
from tools.allods_characters import bake_skin, read_character_template, read_variation, read_visual_item, resolve_appearance  # noqa: E402
from tools.allods_fx import FxBuild, ParticlePool, fsb5_stream_names  # noqa: E402
from tools.allods_gltf import Exporter, TexturePool, load_animation, load_geometry  # noqa: E402
from tools.allods_packdb import EXTERN, PackDB, open_catalog, open_map, open_pack, packs_path  # noqa: E402
from tools.allods_scenes import (  # noqa: E402
    VM_SCALE, VM_VARIATION, buff_camera_track, buff_scripts, mob_name_index, mob_visual, read_client_line, read_lightvrt,
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
# Hauteur d'œil du joueur au-dessus d'un repère où il est déplacé : celle des points de vue du
# manifeste (« à 2 m »), choix documenté, pas une donnée.
EYE_HEIGHT = 2.0
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

    Établi sur les données :

    * **octet 2** : lumières ponctuelles de la carte, `255 · Σ intensité · (1 − d / rayon)^atténuation ·
      max(0, N·L)` (corrélation 1,000 sur le pilote et `Ferris4`) ; couleur `PointLightColor` ;
    * **octet 1** (`128 + 127 · v`, 4 bits) : visibilité du ciel `v`, part de l'hémisphère supérieur
      dégagée — corrélation 0,81 sur le pilote (tirs de rayons sur le décor), 0,73 sur `Isa` (feuillages
      comptés opaques), pente 106 et ordonnée 138 pour 127 et 128 attendus ;
    * **octet 0** (3 bits) : visibilité du soleil (ombre portée) — corrélation 0,81 sur le pilote pour
      un soleil à 45° de hauteur ; le soleil de la cuisson est celui de la zone du lieu (`Isa` : lacet
      225°, pas celui de la première zone de la carte), d'où un écart possible avec `sunDirection`.

    Total : `AmbientColor · (f + (1 − f) · v) + DiffuseColor · max(0, N·S) · ombre + ponctuelles`, avec
    `f` = `AmbientFactor` (0,5 partout) pris comme la part d'ambiante qui reste à l'ombre du ciel —
    choix du lecteur, le shader du jeu n'étant pas lu."""
    point = raw[:, 2:3] / 255.0 * _rgb(light.get("pointLight", 0xFFFFFFFF))
    sky = np.clip((raw[:, 1:2].astype(np.float64) - 128.0) / 127.0, 0.0, 1.0)
    shadow = raw[:, 0:1].astype(np.float64) / 255.0
    factor = float(light.get("ambientFactor", 0.5) or 0.0)
    ambient = _rgb(light.get("ambient")) * (factor + (1.0 - factor) * sky)
    sun = 0.0
    if normals is not None and len(normals) == len(raw):
        sun = np.clip(normals @ sun_direction(light), 0, None)[:, None] * _rgb(light.get("diffuse")) * shadow
    return ambient + sun + point


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
                areas: list[tuple[list[float] | None, float]], report: list[str], extras: list[dict] | None = None,
                doors: list[dict] | None = None, cutout: bool = True) -> dict:
    """Décor d'une carte, **commun aux scènes qui s'y jouent** : les gabarits des objets posés dans
    l'une des zones (`areas` : centre, rayon de chaque scène) une fois chacun dans `decor.glb`, les
    instances avec ce qu'il faut pour éclairer chacune (`light_decor`, par scène : l'éclairage
    dépend du temps de la scène)."""
    # feuillages : matériaux opaques à texture alphée découpés par leur alpha (`cutout`), comme la
    # création de personnage ; sans lui, les frondaisons des cartes d'extérieur sortent en aplats
    # `cutout=False` (`"decor_cutout": false` d'une scène de la carte) : le 17.0 ne marque pas les
    # matériaux découpés, et l'alpha d'une texture opaque y est parfois un masque (planches du pont du
    # navire de l'Empire, `Hadagan_Inst_Board` : alpha sous 0,5 sur 80 % de la texture ; `Heraldic_Base` :
    # alpha nul partout) ; la découpe y creuse le décor.
    fx = FxBuild(Exporter(textures, DECOR_TEXTURE_MAX, generator=GENERATOR, texture_prefix="textures/", cutout=cutout), mp, cat, bins,
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
        door = next((d for d in doors or [] if all(abs(a - b) <= 0.05 for a, b in zip(d["p"], obj.position))), None)
        if door is not None:
            # Porte (`DoorResource` de l'objet dans l'arbre 7.0) : états ouvert et fermé, tenus.
            variants = {key: fx.emit_state(vot, door[key]["clips"][0]) if door.get(key) else None
                        for key in ("open", "closed")}
            if all(variants.values()):
                inst["_door"] = {"script": door["script"], "isOpen": door["isOpen"], **variants}
            else:
                report.append(f"décor {map_name} : porte {door['script']} sans animation d'état ({variants})")
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
    for extra in extras or []:
        # Modèle posé par une stèle à la place d'un objet du décor (sol effondré de l'étage 6) : propre à
        # une scène (`_only`), présent de `t` à `until` ; sans `lightvrt` (hors région), l'ambiante seule.
        vot = extra["show"] | EXTERN if getattr(mp, "parent", None) is not None else extra["show"]
        vis = read_visobject(mp, cat, vot)
        name = fx.name_of(vot)
        if name not in emitted:
            node = fx.emit(vot)
            emitted.add(name)
            if node is not None:
                fx.roots.append(node)
        if name not in fx.meta:
            report.append(f"décor {map_name} : modèle de stèle {extra.get('name')} non exporté")
            continue
        inst = {"vot": name, "p": [round(v, 4) for v in extra["p"]], "yaw": extra["yaw"], "_only": extra["only"],
                "_t": extra["t"], "_until": extra["until"]}
        if abs(extra.get("scale", 1.0) - 1) > 1e-6:
            inst["scale"] = extra["scale"]
        if vis.geometry is not None:
            if vis.geometry not in geometries:
                geometries[vis.geometry] = load_geometry(mp, cat, bins, vis.geometry)
            m = np.eye(3)
            c, s_ = math.cos(extra["yaw"]), math.sin(extra["yaw"])
            m[:2, :2] = [[c, -s_], [s_, c]]
            inst["_geo"], inst["_m"] = vis.geometry, m
        instances.append(inst)
    glb = fx.exporter.finish(fx.roots)
    report.append(f"décor {map_name} : {len(instances)} objets posés ({len(emitted)} gabarits), {skipped} sans gabarit visuel, "
                  f"{sum(1 for i in instances if '_raw' in i)} avec éclairage précalculé")
    report += fx.exporter.notes
    return {"glb": glb, "instances": instances, "objects": fx.meta, "sounds": fx.sounds, "geometries": geometries,
            "solids": np.concatenate(solids) if solids else np.zeros((0, 3, 3)),
            "pointLights": point_lights(mp, objects)}


REGION_SIZE = 256.0


LIGHTMAP_FILES = ("_lightmap.bin", "_lightmapDown.bin")    # couche 0 (haut), couche 1 (sol du dessous)
LIGHTMAP_ATLAS_MAX = 4096
LIGHTMAP_TEXELS = 512
LIGHTMAP_MARGIN = 2       # texels de bordure de chaque côté : 508 texels couvrent les 256 m de la région


def lightmap_uv(points: np.ndarray, cell: tuple[int, int], grid: int) -> np.ndarray:
    """Coordonnées dans l'atlas des `lightmap` (origine en haut à gauche) de sommets en mètres
    locaux à la région. Le `<région>_lightmap.bin` (512²) a une **bordure de deux texels** : les
    508 du milieu couvrent les 256 m (0,504 m chacun), bords de la région au milieu des texels 1-2
    et 509-510, qui recopient à l'identique ceux de la voisine (colonnes 509-510 de A = 1-2 de la
    région suivante en x, lignes 1-2 = 509-510 de la suivante en y, écart moyen 0,00 sur `Ferris4`
    et `Inst_ZoneContested12_Start`, 55 et 102 bords). Axe Y retourné (corrélations sur `Isa` et
    `Ferris4` ; sans le retournement elles tombent à 0). La lecture reste à deux texels du bord de
    la case : pas de fuite de la case voisine de l'atlas."""
    span = (LIGHTMAP_TEXELS - 2 * LIGHTMAP_MARGIN) / LIGHTMAP_TEXELS
    edge = LIGHTMAP_MARGIN / LIGHTMAP_TEXELS
    u = edge + span * np.clip(points[:, 0] / REGION_SIZE, 0.0, 1.0)
    v = edge + span * np.clip(1.0 - points[:, 1] / REGION_SIZE, 0.0, 1.0)
    return np.stack([(cell[0] + u) / grid, (cell[1] + v) / grid], axis=1).astype(np.float32)


class LightmapAtlas:
    """Lumière cuite du sol, une case par (région, couche) : **R** = visibilité du ciel (255 = ciel
    dégagé ; corrélation 0,59 avec un facteur de vue du ciel du seul relief sur `Isa` 3_6), **G** =
    visibilité du soleil de la cuisson, ombres portées comprises (0,73 avec les ombres du relief pour
    le soleil de la zone, lacet 225° et hauteur 45°), **B** = lumières ponctuelles *sans* `N·L`
    (0,83 et 0,91 sur `Ferris4` 4_4 et 5_4, pente 0,82 à 0,92). `_lightmapDown.bin` éclaire la couche
    du dessous (`Isa` 7_6 : elle couvre exactement les sous-carreaux de niveau 1, 10 m plus bas). Une
    carte sans cuisson (fichier absent ou nul) n'a pas de case : ses sommets prennent `(1, 1, 0)`."""

    def __init__(self, textures: TexturePool):
        self.textures = textures
        self.images: list[np.ndarray] = []
        self.slots: dict[tuple[str, int], int | None] = {}

    def slot(self, path: str, level: int) -> int | None:
        key = (path, level)
        if key not in self.slots:
            name = path.replace("_MapRegion.xdb", LIGHTMAP_FILES[min(level, 1)])
            img = self.textures.image(name, 512)
            rgb = np.asarray(img.convert("RGB").resize((LIGHTMAP_TEXELS,) * 2)) if img is not None else None
            self.slots[key] = None if rgb is None or not rgb.any() else len(self.images)
            if self.slots[key] is not None:
                self.images.append(rgb)
        return self.slots[key]

    @property
    def grid(self) -> int:
        return max(1, math.ceil(math.sqrt(len(self.images))))

    def cell(self, slot: int) -> tuple[int, int]:
        return slot % self.grid, slot // self.grid

    def png(self) -> bytes | None:
        if not self.images:
            return None
        grid = self.grid
        size = min(512, LIGHTMAP_ATLAS_MAX // grid)
        atlas = Image.new("RGB", (grid * size, grid * size))
        for k, rgb in enumerate(self.images):
            cx, cy = self.cell(k)
            atlas.paste(Image.fromarray(rgb).resize((size, size), Image.BILINEAR), (cx * size, cy * size))
        out = io.BytesIO()
        atlas.save(out, "PNG", optimize=True)
        return out.getvalue()


def build_terrain(mp: PackDB, cat, bins, textures: TexturePool, areas: list[tuple[list[float] | None, float]],
                  report: list[str], lightmap_out: Path | None = None) -> tuple[bytes | None, np.ndarray]:
    """Sol des scènes (`terrain.glb` de la carte) : sous-carreaux de 8 m du `terrainDump` des
    régions (niveau de détail fin), ceux dont le centre tombe dans une zone de scène (+ 16 m). Chaque
    sommet porte les calques de ses deux passes au plus (`_LAYERS0/1`, indices dans la liste des
    calques de la carte, `extras.terrainLayers` : texture et taille de répétition) et leurs poids lus
    dans le `SplatMap_N` de leur jeu (`_WEIGHTS0/1`) ; le lecteur les mélange. La lumière cuite des
    `lightmap` des régions est rangée dans un atlas (`lightmap_out`, `extras.terrainLightmap`), lue
    par `_LIGHTUV`. Rend aussi les triangles du sol, pour poser les acteurs."""
    from tools.allods_scenes import region_origin
    from tools.allods_terrain import pass_weights, region_patches, region_splats, terrain_layers
    from tools.allods_terrain_extras import ExtrasBuilder
    extras = ExtrasBuilder(mp, cat, textures, lambda name, size: textures.uri(name, size, "textures/"))
    palette: dict[str, int] = {}
    tilings: list[float] = []
    pos, nor, lay0, wei0, lay1, wei1, idx, solids, lmuv = [], [], [], [], [], [], [], [], []
    lightmaps = LightmapAtlas(textures)
    base = count = 0
    for path, region in sorted(mp.paths.items()):
        if not path.endswith("_MapRegion.xdb"):
            continue
        ox, oy = region_origin(path)
        near = [(c, r) for c, r in areas if c is None or
                (ox - r - 16 <= c[0] <= ox + REGION_SIZE + r + 16 and oy - r - 16 <= c[1] <= oy + REGION_SIZE + r + 16)]
        if not near:
            continue
        parsed = region_patches(bins.get, "", path)
        if parsed is None:
            continue
        layer_sets, patches = parsed
        layers = terrain_layers(mp, cat, mp.ptr(region + 0x98))
        splats = region_splats(bins.get, path)
        extras.add_region(bins.get, path, mp.ptr(region + 0x98), (ox, oy), patches,
                          lambda x, y: any(c is None or math.hypot(x - c[0], y - c[1]) <= r + 16 for c, r in near),
                          light_slot=lambda: lightmaps.slot(path, 0))

        def slot(layer_id: int) -> int:
            name, tiling = layers[layer_id] if layer_id < len(layers) else (None, 30.0)
            key = name or ""
            if key not in palette:
                palette[key] = len(palette)
                tilings.append(float(tiling))
            return palette[key]
        for patch in patches:
            cx, cy = ox + 8 * patch.sx + 4, oy + 8 * patch.sy + 4
            if not any(c is None or math.hypot(cx - c[0], cy - c[1]) <= r + 16 for c, r in near):
                continue
            n = len(patch.points)
            ids_w = []
            for first, set_index, bc, bd, splat_map in patch.passes[:2]:
                ids = list(layer_sets[set_index]) if set_index < len(layer_sets) else []
                w = pass_weights(splats[splat_map] if splat_map < len(splats) else None, patch, (bc, bd))
                slots = [slot(i) for i in ids] + [0] * (3 - len(ids))
                w[:, len(ids):] = 0.0
                ids_w.append((np.tile(np.array(slots[:3], np.float32), (n, 1)), w.astype(np.float32)))
            if not ids_w:
                ids_w.append((np.zeros((n, 3), np.float32), np.tile(np.array([1, 0, 0], np.float32), (n, 1))))
            while len(ids_w) < 2:
                ids_w.append((np.zeros((n, 3), np.float32), np.zeros((n, 3), np.float32)))
            pts = patch.points + np.array([ox, oy, 0.0])
            pos.append(pts.astype(np.float32))
            lm_slot = lightmaps.slot(path, patch.level)
            lmuv.append((patch.points, lm_slot))
            nor.append(patch.normals.astype(np.float32))
            (l0, w0), (l1, w1) = ids_w
            lay0.append(l0); wei0.append(w0); lay1.append(l1); wei1.append(w1)
            idx.append((patch.triangles + base).astype(np.uint32))
            solids.append(pts[patch.triangles])
            base += n
            count += 1
    if not pos:
        return None, np.zeros((0, 3, 3))
    ex = Exporter(textures, DECOR_TEXTURE_MAX, generator=GENERATOR, texture_prefix="textures/")
    names = sorted(palette, key=palette.get)
    # Sans case : coordonnée négative, que le lecteur prend pour « pas de cuisson ».
    uvs = [lightmap_uv(p, lightmaps.cell(k), lightmaps.grid) if k is not None else np.full((len(p), 2), -1.0, np.float32)
           for p, k in lmuv]
    atlas_png = lightmaps.png()
    if lightmap_out is not None:
        if atlas_png:
            lightmap_out.write_bytes(atlas_png)
        else:
            lightmap_out.unlink(missing_ok=True)
    layer_meta = [{"texture": textures.uri(name, DECOR_TEXTURE_MAX, "textures/") if name else None,
                   "tiling": round(tilings[k], 3), "name": Path(name).name if name else None} for k, name in enumerate(names)]
    acc = lambda a, kind="VEC3": ex.gltf.add_accessor(np.concatenate(a), kind, "f32", target=34962)  # noqa: E731
    primitive = {"attributes": {"POSITION": ex.gltf.add_accessor(np.concatenate(pos), "VEC3", "f32", target=34962, minmax=True),
                                "NORMAL": acc(nor), "_LAYERS0": acc(lay0), "_WEIGHTS0": acc(wei0),
                                "_LAYERS1": acc(lay1), "_WEIGHTS1": acc(wei1), "_LIGHTUV": acc(uvs, "VEC2")},
                 "indices": ex.gltf.add_accessor(np.concatenate(idx).reshape(-1), "SCALAR", "u32", target=34963), "mode": 4}
    ex.gltf.json["meshes"].append({"name": "terrain", "primitives": [primitive]})
    root = ex.gltf.add_node({"name": "terrain", "mesh": len(ex.gltf.json["meshes"]) - 1,
                             "extras": {"terrain": True, "terrainLayers": layer_meta,
                                        "terrainLightmap": lightmap_out.name if atlas_png and lightmap_out else None}})
    report.append(f"sol : {count} sous-carreaux de 8 m, {len(names)} calques mélangés, "
                  f"{len(lightmaps.images)} lightmap(s) de région, {extras.tufts} touffes d'herbe "
                  f"({len(extras.kinds)} sortes), {extras.water_elements // 64} carrés d'eau")
    report += ex.notes
    more = extras.emit(ex, lambda p, k: lightmap_uv(p, lightmaps.cell(k), lightmaps.grid))
    return ex.finish([root, *more]), np.concatenate(solids) if solids else np.zeros((0, 3, 3))


DOOR_BEFORE = -1e5          # état posé avant la scène : montré à la fin de son animation


def door_states(door: dict, initial: dict[str, bool], switches: list[dict]) -> list[dict]:
    """États d'une porte pendant une scène : celui du départ (`initial`, laissé par le tutoriel et
    donné par le manifeste, sinon `isOpen` de sa `DoorResource`), puis les `DoorSwitch` du déroulé."""
    is_open = initial.get(door["script"], door["isOpen"])
    out = [{"t": DOOR_BEFORE, "vot": door["open" if is_open else "closed"]}]
    for sw in sorted((s for s in switches if s["spawn"] == door["script"]), key=lambda s: s["t"]):
        if sw["open"] != is_open:
            is_open = sw["open"]
            out.append({"t": round(sw["t"], 3), "vot": door["open" if is_open else "closed"]})
    return out


def light_decor(decor: dict, light: dict, center: list[float] | None, radius: float,
                scene: dict | None = None, doors: tuple[dict[str, bool], list[dict]] | None = None) -> tuple[list[dict], bytes]:
    """Instances d'une scène (dans son cercle) et leur éclairage de sommets (`decor-light.bin`) :
    ambiante + soleil (`N·S`) + octet 2 du `lightvrt`, avec la lumière de la scène. `scene` (id,
    `decor_windows` du plan) : modèles de stèle propres à la scène, objets retirés pendant un état."""
    out, blobs, offset = [], [], 0
    hides = [w for w in (scene or {}).get("decor_windows", []) if "hide" in w]
    for inst in decor["instances"]:
        x, y = inst["p"][0], inst["p"][1]
        if center is not None and math.hypot(x - center[0], y - center[1]) > radius:
            continue
        if inst.get("_only") is not None and inst["_only"] != (scene or {}).get("id"):
            continue
        entry = {k: v for k, v in inst.items() if not k.startswith("_")}
        if inst.get("_only") is not None:
            entry["t"], entry["until"] = inst["_t"], inst["_until"]
        for w in hides:
            if inst["vot"].split("#")[0].lower() == w["hide"].lower() and math.dist(inst["p"], w["p"]) < 0.05:
                entry["hidden"] = entry.get("hidden", []) + [[w["t"], w["until"]]]
        if inst.get("_door"):
            entry["states"] = door_states(inst["_door"], *(doors or ({}, [])))
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
        for e in elements:
            # Nuages de ciel « alpha » dont la texture n'a pas d'alpha (`Sky03_UpperCloud`, DXT1) :
            # fond noir, donc rendus additifs (sinon des cartes noires barrent le ciel de Ferris4).
            textures.uri(e.material.texture, DECOR_TEXTURE_MAX, texture_prefix)
            if e.material.transparent and e.material.blend == "BLEND_EFFECT_ALPHA" and \
                    not textures.has_alpha.get(e.material.texture, True):
                e.material.blend = "BLEND_EFFECT_ADD"
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
    # Variante de modèle (`KaniaMale_CutScene`) sans l'animation : celle du modèle de base
    # (`KaniaMale.Special08`, même squelette), comme le Luka de CutScene_EngineerDeathKania.
    stems = [stem] + ([stem.split("_")[0]] if "_" in stem else [])
    index = {name.lower(): name for name in bins._pak_index()} if not hasattr(bins, "_lower_index") else bins._lower_index
    bins._lower_index = index
    for candidate in stems:
        hit = index.get(f"{folder}/Animations/{candidate}.{anim}.(SkeletalAnimation).bin".lower())
        if hit:
            return hit
    return None


def build_actor_offset(actor: dict, mob: int | None, db: PackDB, cat, bins, textures: TexturePool,
                       report: list[str]) -> tuple[bytes, dict]:
    """Acteur : gabarit de sa `VisualMob` ; un personnage (gabarit à tenue par défaut) est habillé
    par `allods_characters` avec la variation et les objets de sa `VisualMob`."""
    if mob is not None and getattr(db, "parent", None) is not None:
        mob |= EXTERN   # ressource de pack.bin vue depuis la base de carte
    if actor.get("vot") is not None:
        # Modèle d'une stèle (navire de `League_Ship_Final`) : gabarit visuel seul, sans tenue.
        template, visual = None, None
        vot = read_visobject(db, cat, actor["vot"])
    else:
        if mob is None and actor.get("visual") is None:
            raise ValueError(f"{actor['id']} : MobWorld {actor['mob']} introuvable")
        # Acteur d'une `GameViewScene` : sa `VisualMob` est donnée directement (pas de `MobWorld`).
        visual = actor["visual"] if actor.get("visual") is not None else mob_visual(db, mob)
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
    if fallback and template is not None and template.default_dress is None and \
            any(e.material.visible and not e.material.texture for e in geo_elements) and bins.get(fallback):
        for e in geo_elements:
            if e.material.visible and not e.material.texture:
                e.material.texture = fallback
        report.append(f"{actor['id']} : texture de géométrie par le nom : {fallback}")
    untextured = any(e.material.visible and not e.material.texture for e in geo_elements)
    if template is not None and (template.default_dress is not None or (template.variations is not None and untextured)):
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
            baked_name = f"actors/{actor.get('file', actor['id'])}-skin"
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
    # Modèle sans rien à dessiner (`Dummy` d'une GameViewScene) : squelette seul, pas de peau.
    mesh_node = {"name": f"{actor['id']}_mesh", "mesh": mesh} if mesh is not None else {"name": f"{actor['id']}_mesh"}
    if skinned and mesh is not None:
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
    # Échelle de la `VisualMob` (le Спрутоглав est à 0,4) : appliquée au porteur par le lecteur.
    visual_scale = db.f32(visual + VM_SCALE) if visual is not None else 1.0
    visual_scale = visual_scale if 0 < visual_scale < 100 else 1.0
    meta = {"geometry": loaded.geo.binary, "height": round(float(loaded.vertices["position"][:, 2].max() * scale), 3),
            "animations": durations, "name_index": mob_name_index(db, mob) if mob is not None else None,
            "visual_scale": round(float(visual_scale), 4)}
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


def fx_length(meta: dict, name: str, depth: int = 0) -> float:
    """Durée d'un gabarit d'effet : son animation, ses particules, ses composants retardés."""
    info = meta.get(name, {})
    length = float(info.get("duration") or 0.0)
    system = info.get("particles") or {}
    length = max(length, float(system.get("duration") or system.get("lifeTime") or 0.0))
    if depth < 8:
        for comp in info.get("components", []):
            length = max(length, float(comp.get("start", 0.0)) + fx_length(meta, comp["vot"], depth + 1))
    return length


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
        entry = {k: v for k, v in spawn.items() if k not in ("vot", "mob", "buff", "_note", "_source")}
        entry["vot"] = name
        if entry.get("until") is None and "t" in entry:
            # Effet ponctuel (explosion d'un `ClientData`) : il dure le temps de son gabarit.
            entry["until"] = round(entry["t"] + max(fx_length(fx.meta, name), 0.5), 3)
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
    `_lp` (boucle), `_nm` ou d'un numéro (première variante). Repli des événements que le
    fichier d'événements `.bev` ne résout pas (`resolve_wave`), et chemin des voix."""
    tail = _key(event.split("/")[-1])
    for suffix in ("", "lp", "nm", "loop", "1", "01"):
        hits = index.get(tail + suffix)
        if hits:
            hits = sorted(hits, key=lambda h: (prefer not in h[0], h[0]))
            return hits[0]
    # Voix enregistrées en variantes et reprises (`IL1/15_Amanda_04` → `15_amanda_04_v1_patch403`,
    # `_v2`, `_v3` : l'événement en tire une au hasard) : la première variante.
    variants = sorted((h for k, hs in index.items() if k.startswith(tail) and re.fullmatch(r"(v\d+)?(patch\d+)?", k[len(tail):])
                       for h in hs), key=lambda h: (prefer not in h[0], _key(h[2]), h[0]))
    if tail and variants:
        return variants[0]
    grouped = grouped_wave(event, index, prefer)
    if grouped is not None:
        return grouped
    # préréglage d'ambiance (`Demonic_AP`) : la boucle de fond de même préfixe (`demonic_drone_lp`)
    stem = re.sub(r"ap$", "", tail)
    loops = sorted((h for k, hs in index.items() if k.startswith(stem) and k.endswith("lp") for h in hs),
                   key=lambda h: ("Ambience" not in h[0], h[2]))
    return loops[0] if stem and loops else None


def fev_resolver(bins, index: dict) -> FevResolver:
    """Résolveur des `.bev` (`tools/allods_fev.py`) : noms des sous-pistes repris de l'index."""
    by_bank: dict[str, dict[int, str]] = {}
    for hits in index.values():
        for bank, sub, stream in hits:
            by_bank.setdefault(bank, {})[sub - 1] = stream

    def streams_of(bank: str) -> list[str]:
        subs = by_bank.get(bank, {})
        return [subs.get(i, "") for i in range(max(subs) + 1)] if subs else []

    return FevResolver(bins._pak_index().keys(), bins.get, streams_of)


def resolve_wave(event: str, index: dict, fev: FevResolver, report: list[str], prefer: str | None = None,
                 voice: bool = False, layer: str | None = None) -> tuple[tuple[str, int, str] | None, str]:
    """Onde d'un événement : celle que nomme son `.bev` (définition de son du premier son de son
    premier calque, ou du calque dont l'onde est `layer` : choix justifié du manifeste,
    `audio_layers`), sinon l'appariement par le nom (`find_wave`). Deuxième valeur : la source.
    Voix : le paramètre de leurs calques (la distance des sons 3D) n'est pas signalé."""
    waves, why = fev.waves(event)
    if waves:
        chosen = [w for w in waves if layer and w["stream"].lower() == layer.lower()]
        if layer and not chosen:
            report.append(f"{event} : calque {layer} absent du .bev, premier calque joué")
        first = chosen[0] if chosen else waves[0]
        rest = [w["stream"] for w in waves if w is not first]
        if rest:
            how = "calque choisi par le manifeste" if chosen else "le premier"
            report.append(f"{event} : {len(waves)} sons dans le .bev, un seul joué ({first['stream']}, {how}) ; "
                          f"non repris : {', '.join(rest)}")
        if first["param"] >= 0 and not voice:
            report.append(f"{event} : calque piloté par un paramètre du jeu (enveloppes non reproduites)")
        return (first["bank"], first["sub"], first["stream"]), "bev"
    report.append(f"{event} : .bev sans onde ({why}), appariement par le nom")
    if prefer is None:
        prefer = "Music" if event.startswith("Music/") else ""
    return find_wave(event, index, prefer), "name"


def export_waves(events: set[str], bins, out_dir: Path, vgmstream: Path, report: list[str],
                 music_seconds: float | None = None, layers: dict[str, str] | None = None) -> dict[str, dict]:
    """Ondes des événements, encodées en Ogg Vorbis et MP3 dans `sfx/`. La musique de zone est
    coupée à la durée de la scène (`music_seconds`, fondu de sortie de 2 s) : le poids du site.
    `layers` : onde jouée d'un événement adaptatif à plusieurs calques (`audio_layers` du manifeste)."""
    from tools.extract_audio import encode_outputs
    index = sound_index(bins, Path(os.environ.get("ALLODEX_CACHE") or Path.home() / ".cache" / "allodex"))
    fev = fev_resolver(bins, index)
    found: dict[str, dict] = {}
    target = out_dir / "sfx"
    with tempfile.TemporaryDirectory(prefix="allodex-sfx-") as tmp:
        for event in sorted(events):
            hit, source = resolve_wave(event, index, fev, report, layer=(layers or {}).get(event))
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
            found[event] = {"file": f"sfx/{base.name}", "wave": stream, "bank": bank, "duration": round(duration, 3),
                            "match": source}
    return found


def export_voices(events: list[str | None], bins, out_dir: Path, vgmstream: Path, report: list[str],
                  index: dict) -> list[dict | None]:
    """Voix des répliques : onde que nomme le `.bev` de l'événement (`IE1/13_Master_07` →
    `13_Master_07_Captain_StartTheReactor_patch403`), sinon onde nommée comme la fin de l'événement
    (`Cutscenes/Eden2/Prologue04_Cutscene_1` → `Prologue04_Cutscene_1`), banques `SFX/Voice/*` d'abord."""
    out_dir.mkdir(parents=True, exist_ok=True)
    result: list[dict | None] = []
    fev = fev_resolver(bins, index)
    with tempfile.TemporaryDirectory(prefix="allodex-voice-") as tmp:
        for n, event in enumerate(events, 1):
            hit = resolve_wave(event, index, fev, report, "SFX/Voice/", voice=True)[0] if event else None
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


def model_yaw(server: float) -> float:
    """Lacet d'un modèle (avant −Y) posé à la place d'un `SpawnPlacePoint` des `ServerObjects` : le
    lacet du serveur est un cap (direction de l'axe X tourné, comme celui d'une téléportation, lu au
    centième sur la direction du Grand Mage) ; le modèle tourne de ce cap + π/2. Recoupé sur le
    navire kanien : stèle `League_Ship_Final` à 3,26141, sa collision posée dans la région au même
    point à 4,82951 (+1,568)."""
    return round(server - MODEL_FORWARD, 5)


def heading(position: list[float], face: list[float]) -> float:
    """Cap (convention des `ServerObjects`) de `position` vers `face`."""
    return round(math.atan2(face[1] - position[1], face[0] - position[0]), 4)


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
        self.fr_voice_all: dict[str, list[int]] = {}
        self.fr_root = Path(fr_spec["root"])

    def load_fr_voices(self) -> None:
        if self.fr_voice or self.fr is None:
            return
        from tools.allods_packdb import default_cache_dir
        from tools.allods_scenes import PackBinView
        from tools.packbin import PackBin
        pak = packs_path(self.fr_root / "data" / "Packs" / "BaseLocfra_x64.pak")
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
                self.fr_voice_all.setdefault(cl.voice, []).append(cl.text_index)

    def line(self, idx: int | None, voice: str | None, delay_ms: int, anchor_delta: int | None,
             same_voice: list[int] | None = None) -> dict:
        """`same_voice` : indices de texte du 17.0 des répliques qui partagent cette voix ; la réplique
        française est alors celle de même rang parmi celles de la voix dans le client FR."""
        text: dict[str, str] = {}
        if idx is not None:
            text["ru"] = clean_text(self.main.texts["ru"][idx])
            en = clean_text(self.main.texts["en"][idx])
            if en and not has_cyrillic(en):
                text["en"] = en
        if self.fr is not None:
            self.load_fr_voices()
            j = None
            fr_all = sorted(set(self.fr_voice_all.get(voice or "", [])))
            if same_voice and idx in same_voice and len(fr_all) == len(same_voice):
                j = fr_all[sorted(same_voice).index(idx)]
            elif voice and voice in self.fr_voice:
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

    def same_voice(self, voice: str | None) -> list[int]:
        return sorted({self.lines[o].text_index for o in self.by_voice.get(voice or "", []) if self.lines[o].text_index is not None})

    def find(self, voice: str | None, ru: str) -> object | None:
        from tools.extract_cinematics import norm_key
        # Le texte russe d'abord : deux répliques du 7.0 partagent parfois une même voix
        # (`CS_FR_SwarmArch01` pour « Адаптация… » et « Не нужно сопротивляться… »).
        for key, table in ((norm_key(ru) if ru else None, self.by_text), (voice, self.by_voice)):
            if key and key in table:
                return self.lines[table[key][0]]
        return None


# Textes posés dans une ressource plutôt que dans un sous-titre : bulle au-dessus d'un PNJ
# (`InterfaceAction` `ENUM_SHOW_BUBBLE`, indice du texte en +0x78, sous le `customData` d'un
# `ClientData`) et message de PNJ (`TextMessage`, +0x40) — recoupés sur les textes 7.0 de
# `Inst_LeagueStart` (« Портал открыт, заходите! »).
OWNED_TEXT = {"InterfaceAction": 0x78, "TextMessage": 0x40}


class ResourceTexts:
    """Texte d'une bulle ou d'un message de PNJ : RU/EN du 17.0 par l'indice que porte la ressource.
    FR : les identifiants de ces ressources diffèrent entre le 16.0 FR et le 17.0 (`PackBinView` ne
    s'applique pas ici) et l'écart d'indice change d'un bloc à l'autre ; le manifeste donne les blocs
    alignés (`fr_blocks` : `{ru, fr, count}`, relus réplique par réplique)."""

    def __init__(self, db: PackDB, texts: Texts) -> None:
        from tools.extract_cinematics import norm_key
        self.db, self.texts = db, texts
        self.words = np.frombuffer(db.raw, dtype="<u4", count=(len(db.raw) - db.data) // 4, offset=db.data)
        self.by_ru: dict[str, list[int]] = {}
        for i, t in enumerate(texts.main.texts["ru"]):
            if t:
                self.by_ru.setdefault(norm_key(clean_text(t)), []).append(i)

    def owned(self, idx: int) -> list[str]:
        """Types des structures (bulle, message) qui portent l'indice de texte `idx`."""
        out = []
        for hit in np.where(self.words == idx)[0]:
            loc = int(hit) * 4
            j = int(np.searchsorted(self.db.vt_loc, loc, side="right")) - 1
            owner = int(self.db.vt_loc[j])
            kind = self.db.vtype(owner)
            if OWNED_TEXT.get(kind) == loc - owner:
                out.append(kind)
        return out

    def find(self, ru: str, prefer: str = "InterfaceAction", fr_blocks: list[dict] | None = None) -> dict:
        from tools.extract_cinematics import norm_key
        candidates = [i for i in self.by_ru.get(norm_key(ru), []) if self.owned(i)]
        candidates.sort(key=lambda i: prefer not in self.owned(i))
        text: dict[str, str] = {"ru": ru}
        for idx in candidates:
            text["ru"] = clean_text(self.texts.main.texts["ru"][idx])
            en = clean_text(self.texts.main.texts["en"][idx])
            if en and not has_cyrillic(en):
                text["en"] = en
            block = next((b for b in fr_blocks or [] if b["ru"] <= idx < b["ru"] + b["count"]), None)
            if block is not None and self.texts.fr is not None:
                j = block["fr"] + idx - block["ru"]
                if j < len(self.texts.fr.texts["fr"]) and self.texts.fr.texts["fr"][j]:
                    text["fr"] = clean_text(self.texts.fr.texts["fr"][j])
            if "fr" in text or not fr_blocks:
                break
        return text


def find_mob_by_name(db: PackDB, cat, texts: Texts, name: str, model_hint: str) -> int | None:
    """`MobWorld` du 17.0 au nom russe `name` ; entre plusieurs, celui dont le modèle vient du même
    dossier que le `MobWorld` 7.0 (`Characters/Hadagan_male/…`)."""
    from tools.extract_cinematics import norm_key
    want = norm_key(name)
    if not want:
        return None         # PNJ sans nom (paladins `KIS_NoobPaladin_live`) : le nom ne départage rien
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


def _stem(name: str | None) -> str:
    return Path(name.split("#")[0]).name.split(".(")[0].lower() if name else ""


def visual_signature_70(root: Path, visual: str) -> tuple[int, int, set[str]] | None:
    """Signature d'une `VisualMob` 7.0 : couleurs de peau et de cheveux, textures de remplacement de
    sa tenue (`armorShapes` des `VisualItem`), qui départagent les `VisualMob` du 17.0."""
    from tools import cutscene_xdb70 as x70
    tree = x70.Tree(Path(root))
    path = tree.root / visual
    doc = x70._read(path)
    if doc is None:
        return None
    textures: set[str] = set()
    for item in doc.findall("items/Item/item"):
        if not item.get("href"):
            continue
        idoc = x70._read(tree.resolve(path, item.get("href")))
        for rep in (idoc.iter("replacement") if idoc is not None else []):
            if rep.get("href"):
                textures.add(_stem(rep.get("href")))
    var = doc.find("variation")
    return int(_f70(var, "skinColor", -1)), int(_f70(var, "hairColor", -1)), textures


def _f70(node, tag: str, default: float) -> float:
    from tools import cutscene_xdb70 as x70
    return x70._f(node, tag, default)


def find_visual_by_content(db: PackDB, cat, root: Path, visual: str | None) -> tuple[int | None, str]:
    """`VisualMob` du 17.0 d'un PNJ sans nom (`KIS_NoobPaladin_live`) : mêmes couleurs de peau et de
    cheveux que la `VisualMob` 7.0, et les textures de tenue les plus proches (au moins la moitié en
    commun, seule en tête). Rend l'offset et le motif, ou `None` et la raison."""
    from tools.allods_characters import CV_HAIR_COLOR, CV_SKIN_COLOR
    sig = visual_signature_70(root, visual) if visual else None
    if sig is None:
        return None, "VisualMob 7.0 illisible"
    skin, hair, want = sig
    scored = []
    for off in db.resources("VisualMob"):
        v = off + VM_VARIATION
        if db.i32(v + CV_SKIN_COLOR) != skin or db.i32(v + CV_HAIR_COLOR) != hair:
            continue
        have = {_stem(s.replacement) for item in visual_dress(db, off) for shapes in read_visual_item(db, cat, item).shapes.values()
                for s in shapes if s.replacement}
        score = len(want & have) / len(want | have) if want | have else 1.0
        scored.append((score, off))
    scored.sort(reverse=True)
    if not scored or scored[0][0] < 0.5 or (len(scored) > 1 and scored[1][0] == scored[0][0]):
        return None, f"{len(scored)} VisualMob aux mêmes couleurs, meilleur accord {scored[0][0]:.2f}" if scored else "aucune"
    return scored[0][1], f"couleurs {skin}/{hair}, textures de tenue {scored[0][0]:.2f} ({len(scored)} candidates)"


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
    # Le nom du locuteur vient en fin d'événement (`CS_FR_SwarmRysina03` : Rysina, pas l'essaim) :
    # parmi les acteurs présents cités, celui dont le nom (ou l'alias) apparaît le plus à droite.
    best, best_at = None, -1
    for key, actor in summoned.items():
        if not any(a - 1e-3 <= line["t"] < b for a, b in actor["presence"]):
            continue
        names = {actor["voice_key"], (actor.get("name") or "").lower()}
        keys = [actor["voice_key"]] + [k for k, v in aliases.items() if v in names]
        # le nom doit clore l'événement (suivi seulement de chiffres) : `swarm` de `SwarmRysina03` ne compte pas
        at = max((m.start() for k in keys if k for m in [re.search(re.escape(k) + r"\d*$", voice)] if m), default=-1)
        if at >= 0 and at > best_at:
            best, best_at = key, at
    return best


# Vitesse des PNJ du serveur qui courent (`GoThroughPath.runningMode`) : le `MobWorld` ne donne que
# `walkSpeed` ; la course est prise à la vitesse des foules qui courent dans les `GameViewScript`
# de la même instance (6,5 m/s, `Device_Floor1_*` de `Inst_LeagueStart`) — approximation documentée.
RUN_SPEED = 6.5
# Durée d'affichage d'une bulle non doublée (`ENUM_SHOW_BUBBLE` ne la porte pas) : choix documenté,
# coupée au départ de la réplique suivante.
BUBBLE_SECONDS = 5.0


def find_game_scene(db: PackDB, place: list[float] | None, mobs: list[str]) -> int | None:
    """`GameViewScene` du 17.0 à la place (au millimètre) et aux PNJ (`scriptID`) de celle du 7.0."""
    if place is None:
        return None
    for off in db.resources("GameViewScene"):
        p, _ = _placement(db, off + GVS_PLACE)
        if max(abs(a - b) for a, b in zip(p, place)) > 5e-3:
            continue
        names = [db.string(e + GVS_MOB_SCRIPT) for e in db.elements(off + GVS_MOBS, GVS_MOB_STRIDE)]
        if names == mobs or not mobs:
            return off
    return None


def find_game_script(db: PackDB, scene: int, count: int) -> int | None:
    """`GameViewScript` qu'un `ShowSceneAction` du 17.0 joue avec `scene`, au même nombre d'actions que
    celui du 7.0 (une scène a souvent deux scripts : PNJ debout, PNJ qui meurent)."""
    scripts = []
    for i in np.where((db.rtgt == scene) & (db.rkind == 0))[0]:
        loc = int(db.rloc[i])
        j = int(np.searchsorted(db.vt_loc, loc, side="right")) - 1
        owner = int(db.vt_loc[j])
        if db.vtype(owner) == "ShowSceneAction" and loc - owner == SHOW_SCENE:
            script = db.ptr(owner + SHOW_SCRIPT)
            if script is not None and script not in scripts:
                scripts.append(script)
    return next((s for s in scripts if len(db.pointers(s + GVSCRIPT_ACTIONS)) == count), None)


def merge_bubbles(lines: list[dict], chats: list[dict]) -> list[dict]:
    """Voix et bulle d'une même réplique (deux `ClientData` posés au même instant sur le même PNJ :
    `15_Elf01` et `15_Elf01_Bubble`) → une réplique, la voix sous-titrée par la bulle ; message de PNJ
    (`ImpactMobChat`) au même texte : la même réplique (fenêtre de discussion), sinon une réplique."""
    out: list[dict] = []
    for line in lines:
        if line.get("bubble"):
            twin = next((o for o in out if o["t"] == line["t"] and o["speaker"] == line["speaker"] and o["voice"]
                         and not o.get("bubble") and not o["ru"]), None)
            if twin is not None and not twin["voice"].startswith("World/"):
                twin["bubble"] = line["bubble"]
                twin["clientdata"] += " + " + line["clientdata"]
                continue
        elif line["voice"] and not line["ru"]:
            twin = next((o for o in out if o["t"] == line["t"] and o["speaker"] == line["speaker"]
                         and o.get("bubble") and not o["voice"]), None)
            if twin is not None and not line["voice"].startswith("World/"):
                twin["voice"] = line["voice"]
                twin["clientdata"] = line["clientdata"] + " + " + twin["clientdata"]
                continue
        out.append(dict(line))
    from tools.extract_cinematics import norm_key
    for chat in chats:
        if any(norm_key(o.get("bubble") or o["ru"]) == norm_key(chat["ru"]) and abs(o["t"] - chat["t"]) < 2.5 for o in out):
            continue
        out.append({"t": chat["t"], "speaker": chat["speaker"], "ru": "", "bubble": chat["ru"], "voice": None,
                    "animations": [], "delay_ms": 0, "clientdata": chat["message"]})
    out.sort(key=lambda l: l["t"])
    return out


def plan_xdb70(spec: dict, root: Path, db: PackDB, cat, texts: Texts, lines17: ClientLines, anim_names: dict,
               report: list[str], rtexts: "ResourceTexts | None" = None) -> dict:
    """Plan d'une scène de 7.0 ou d'avant : déroulé serveur de l'arbre 7.0 (`tools/cutscene_xdb70.py`)
    rapporté aux ressources du 17.0 (répliques, PNJ)."""
    from tools import cutscene_xdb70 as x70
    open_end = bool(spec.get("until_last"))
    tl = x70.simulate(root, spec.get("first_buff"), trigger=spec.get("trigger"), trigger_effect=spec.get("trigger_effect"),
                      owner=spec.get("trigger_owner", "player"), trigger_tag=spec.get("trigger_tag"), until_last=open_end,
                      home=spec.get("map"))
    map_name = spec.get("map") or sorted(tl.maps)[0]
    # PNJ posés : ceux du déroulé, les stèles et les PNJ que le manifeste place (`start_at`, laissés là
    # par une zone ou une quête précédente, même si le déroulé ne les nomme pas)
    spawns = x70.find_spawns(root, map_name, tl.scripts | set(spec.get("states", {})) | set(spec.get("start_at", {})) |
                             {v["locator"] for v in spec.get("start_at", {}).values()})
    inter = spec.get("interlocutor")
    if inter:
        # Donneur de la quête (`ImpactsToInterlocutor`) : PNJ qui accompagne le joueur, sans place fixe
        # sur la carte ; le manifeste donne son `MobWorld` 7.0 et sa place.
        tree = x70.Tree(Path(root))
        spawns["interlocutor"] = {"p": inter["p"], "yaw": inter.get("yaw", 0.0), "mob": inter["mob"],
                                  "name": x70.mob_name(tree, tree.root / inter["mob"]),
                                  "visual": x70.mob_visual(tree, tree.root / inter["mob"]), "file": "manifest"}
    for script, start in spec.get("start_at", {}).items():
        # PNJ déplacé avant le déroulé (par une zone voisine, justifié par le manifeste) : il part de là.
        # `"yaw": "walk"` : il y est arrivé en marchant depuis sa place (`GoThroughPath`) et garde le
        # cap de cette marche, comme un PNJ du déroulé à la fin de la sienne.
        if script in spawns and start["locator"] in spawns:
            there = spawns[start["locator"]]["p"]
            moved = {**spawns[script], "p": there}
            if start.get("yaw") == "walk":
                moved["yaw"] = heading(spawns[script]["p"], there)
            spawns[script] = moved
    if tl.shots:
        camera = x70.camera_keys(tl.shots)
    else:
        # Aucune caméra dans le déroulé (scène jouée dans la vue du joueur) : vue donnée par le manifeste.
        cam = spec.get("camera") or {}
        camera = {"points": [dict(k) for k in cam.get("points", [])], "targets": [dict(k) for k in cam.get("targets", [])]}
        for tp in tl.teleports:
            # Le joueur est déplacé sur la carte (`ImpactTeleport` vers un repère) : sa vue le suit, à la
            # hauteur d'œil du point de vue du manifeste (`EYE_HEIGHT`), tournée selon le lacet donné.
            dest = spawns.get(tp["locator"])
            if dest is None or not camera["points"]:
                continue
            yaw = tp["yaw"] if tp["yaw"] is not None else dest["yaw"]
            p = [dest["p"][0], dest["p"][1], dest["p"][2] + EYE_HEIGHT]
            q = [p[0] + 10 * math.cos(yaw), p[1] + 10 * math.sin(yaw), p[2]]
            for track, value in ((camera["points"], p), (camera["targets"], q)):
                track.append({"t": round(tp["t"] - 1e-3, 3), "p": list(track[-1]["p"])})
                track.append({"t": tp["t"], "p": [round(v, 4) for v in value]})
            report.append(f"{spec['id']} : joueur déplacé à {tp['t']} s vers {tp['locator']} (lacet {yaw}) : la vue le suit")
    camera["duration"] = round(tl.duration, 3)
    player = spec.get("player") or (camera["points"][0]["p"] if camera["points"] else None)
    if inter and inter.get("face") == "player" and player is not None:
        # Le donneur de la quête se tourne vers le joueur qui lui parle (comportement du client, pas
        # une donnée) : le joueur est à la place que donne le manifeste (`"player"`), sinon au point de vue.
        spawns["interlocutor"]["yaw"] = heading(inter["p"], player)
    actors: dict[str, dict] = {}
    for script, sp in spawns.items():
        if sp["mob"] is None:            # repère nu : place d'une invocation ou but d'une marche
            continue
        if sp["mob"].endswith(".(SteleResource).xdb"):   # stèle : ses états visuels (voir trigger_extras)
            continue
        mob = find_mob_by_name(db, cat, texts, sp["name"], sp.get("visual") or sp["mob"] or "")
        visual = None
        if mob is None and not sp["name"] and sp.get("visual"):
            # `MobWorld` sans nom (paladins `Paladin_live1…4`) : sa `VisualMob` retrouvée par son contenu.
            visual, why = find_visual_by_content(db, cat, root, sp["visual"])
            report.append(f"{spec['id']} : {script} sans nom : VisualMob {'introuvable' if visual is None else 'retrouvée'} "
                          f"({sp['visual']} ; {why})")
        if mob is None and visual is None:
            report.append(f"{spec['id']} : PNJ introuvable dans le 17.0 : {sp['name']} ({script})")
            continue
        actors[script] = {"id": re.sub(r"[^a-z0-9]+", "-", script.lower()).strip("-"), "mob_offset": mob,
                          "path": [{"t": 0, "p": sp["p"], "yaw": model_yaw(sp["yaw"])}], "server": sp,
                          **({"visual": visual, "name": {}} if visual is not None else {})}
    summoned = summon_actors(spec, tl, spawns, db, cat, texts, report)
    for key, info in summoned.items():
        actors[key] = info
    plan_lines, content = [], [0.0]
    for line in merge_bubbles(tl.lines, tl.chats):
        if not line["ru"] and not line["voice"] and not line.get("bubble"):
            # `ClientData` d'animation seule (`Modif1_go`) : une action jouée une fois par le PNJ visé.
            info = actors.get(line["speaker"]) or next((a for a in summoned.values() if line["speaker"] in a["summons"]), None)
            if info is not None and line["animations"]:
                info.setdefault("actions", []).append({"t": line["t"], "until": line["t"] + 30.0,
                                                       "clips": [clip_name(a) for a in line["animations"]], "loop": False})
            continue
        if line["speaker"] == "player":
            line["speaker"] = voice_speaker(line, summoned, spec) or "player"
        if line.get("bubble"):
            # Bulle (ou message) du PNJ : son texte officiel, RU/EN du 17.0, FR par bloc aligné.
            text = rtexts.find(line["bubble"], fr_blocks=spec.get("fr_blocks")) if rtexts is not None else {"ru": line["bubble"]}
        else:
            cl = lines17.find(line["voice"], line["ru"])
            idx = cl.text_index if cl is not None else None
            text = texts.line(idx, line["voice"], line["delay_ms"], None, lines17.same_voice(line["voice"]))
            if "ru" not in text and line["ru"]:
                text["ru"] = line["ru"]
        speaker = actors.get(line["speaker"], {}).get("id") or \
            next((a["id"] for a in summoned.values() if line["speaker"] in a["summons"]), None)
        # Une bulle reste affichée le temps de sa voix (posé à l'extraction), sinon `BUBBLE_SECONDS`.
        duration = line["delay_ms"] / 1000.0 or (BUBBLE_SECONDS if line.get("bubble") else 0.0)
        plan_lines.append({"start": line["t"], "duration": duration, "voice_event": line["voice"],
                           "speaker": speaker, "clips": [clip_name(a) for a in line["animations"]], "text": text,
                           "source": line["clientdata"], **({"bubble": True} if line.get("bubble") else {})})
        content.append(line["t"] + duration)
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
        # musique : type `Music` de l'action, ou événement du projet FMOD `Music` (catégorie
        # `music` de ses événements dans `Music.bev`, même sans type d'action)
        key = "music" if snd["kind"] == "Music" or snd["name"].startswith("Music/") else "ambience"
        sounds[key].append({"event": snd["name"], "t": snd["t"], "until": snd["until"]})
    post = [{"t": p["t"], "until": p["until"], "kind": "veil", "fadeIn": p["fadeIn"], "fadeOut": p["fadeOut"]}
            for p in tl.post if p["black"]]
    centre = np.mean([k["p"] for k in camera["points"]], axis=0) if camera["points"] else np.zeros(3)
    shakes = []
    for sh in tl.shakes:
        # Secousse (`ShakeAction`) : pleine dans `minRadius` de sa source, nulle au-delà de `maxRadius`
        # (entre les deux, décroissance linéaire : choix, le moteur n'en dit pas plus) ; source joueur : pleine.
        src = spawns.get(sh["source"]) if sh["source"] != "player" else None
        weight = 1.0
        if src is not None and camera["points"]:
            d = math.dist(src["p"], camera["points"][0]["p"])
            span = max(sh["maxRadius"] - sh["minRadius"], 1e-6)
            weight = 1.0 if d <= sh["minRadius"] else max(0.0, 1.0 - (d - sh["minRadius"]) / span)
        if weight > 0 and sh["keys"]:
            shakes.append({"t": sh["t"], "fps": sh["fps"], "amplitude": round(sh["amplitude"] * weight, 4),
                           "timeScale": sh["timeScale"], "keys": sh["keys"], "_source": sh["clientdata"]})
    plan = {"map": map_name, "camera": camera, "lines": plan_lines, "actors": list(actors.values()),
            "weather": weather[0] if weather else None, "sounds": sounds, "post": post, "shakes": shakes,
            "decor_center": [float(centre[0]), float(centre[1])], "timing": "server",
            "sources": {"timeline": spec.get("first_buff") or spec.get("trigger"), "buffs": [b["buff"] for b in tl.buffs],
                        "spawns": sorted({sp["file"] for sp in spawns.values()})}}
    if spec.get("trigger"):
        trigger_extras(spec, plan, tl, spawns, root, db, cat, anim_names, report)
    if open_end:
        # Déroulé sans buff qui le borne (quête, zone du tutoriel) : jusqu'à la fin de ce qu'il montre —
        # répliques (prolongées par la durée de leur voix à l'extraction), marches, animations posées
        # par buff (jusqu'à la fin du buff quand il a une durée), scripts des scènes du client ; pas
        # les remises à zéro des stèles des minutes suivantes.
        content += [a.get("walk_end", 0.0) for a in plan["actors"]]
        # plans de caméra du déroulé (cinéma pridien : le travelling vers l'écran)
        content += [k["t"] + plan["sources"].get("window", [0.0])[0] for k in plan["camera"]["points"] if tl.shots]
        content += [s["t"] + (s["duration"] or 0.0) for s in tl.shots if s["t"] + (s["duration"] or 0.0) < tl.duration - 1e-3]
        content += [e["until"] if e["until"] < tl.duration - 1e-3 else e["t"] for e in tl.effects]
        content += [s["t"] for s in tl.summons] + [s["t"] for s in plan.get("spawns", [])]
        switches = {round(c["t"], 3) for c in tl.states}
        for actor in plan["actors"]:
            if actor.get("visual") is not None and actor.get("presence"):
                # PNJ d'une scène du client : fin de son script (trajet, animations, disparition), pas
                # le changement d'état de la stèle qui la retire des minutes plus tard.
                ends = [k["t"] for k in actor["path"]] + [a["t"] for a in actor.get("actions", [])]
                ends += [b for _, b in actor["presence"] if b not in switches and b < tl.duration - 1e-3]
                content.append(max(ends))
        # temps du déroulé ; la scène filmée commence au premier plan de caméra (`window`)
        plan["camera"]["duration"] = round(max(content) - plan["sources"].get("window", [0.0])[0], 3)
        plan["duration_from_voices"] = True
    return plan


# --- déroulé d'un déclencheur : stèles, effets, sons, PNJ posés ------------------------------------

# `SteleResource` (17.0) : place (`SpawnLocation` : repère local en f32 + case de 32 m en i32),
# gabarit visuel, scripts visuels (`DeviceVisScripts` : action par défaut, états).
STELE_SPAWN = 0x70
STELE_VISOBJ = 0x110
STELE_VISSCRIPTS = 0x118
SPAWNLOC_LOCAL = 0x24
SPAWNLOC_CELL = 0x30
SPAWNLOC_CELL_SIZE = 32.0
DVS_DEFAULT = 0x28
DVS_STATES = 0x30
DEVLIST_ELEMENTS = 0x50
DEVANIM_LIST = 0x58            # `DeviceAnimationAction` : animations (u32 de l'énumération), mode
DEVANIM_MODE = 0x7C            # 1 LOOP, 2 CLAMP (recoupé sur `League_Ship_Final` du 7.0)
GVSCRIPT_DELAY = 0x2C          # `playbackParameters.delayBefore` (ms, i32 ; 500/700/1000 du 7.0)
GVS_MOB_YAW = 0xB8           # lacet propre du PNJ (recoupé sur les quatre lacets du 7.0 de IE1_EmpireShip_Fight1)


def stele_position(db: PackDB, stele: int) -> list[float] | None:
    loc = db.ptr(stele + STELE_SPAWN)
    if loc is None or db.vtype(loc) != "SpawnLocation":
        return None
    x, y, z = db.floats(loc + SPAWNLOC_LOCAL, 3)
    cx, cy = db.i32(loc + SPAWNLOC_CELL), db.i32(loc + SPAWNLOC_CELL + 4)
    return [cx * SPAWNLOC_CELL_SIZE + x, cy * SPAWNLOC_CELL_SIZE + y, z]


def find_stele(db: PackDB, position: list[float], tolerance: float = 0.05) -> int | None:
    """Stèle du 17.0 posée au même point que celle de l'arbre 7.0 (le client ne garde pas les noms)."""
    for off in db.resources("SteleResource"):
        p = stele_position(db, off)
        if p is not None and all(abs(a - b) <= tolerance for a, b in zip(p, position)):
            return off
    return None


def device_states(db: PackDB, stele: int, anim_names: dict) -> tuple[dict | None, list[dict]]:
    """Action par défaut et états d'une stèle : scène du client (`ShowSceneAction` : `GameViewScene`
    + `GameViewScript`) ou animation du modèle (`DeviceAnimationAction`)."""
    def decode(action: int | None) -> dict | None:
        kind = db.vtype(action) if action is not None else None
        if kind == "ShowSceneAction":
            return {"kind": "scene", "scene": db.ptr(action + SHOW_SCENE), "script": db.ptr(action + SHOW_SCRIPT)}
        if kind == "DeviceAnimationAction":
            v = db.vec(action + DEVANIM_LIST)
            clips = [clip_name(anim_names.get(db.u32(v[0] + 4 * k), "")) for k in range(v[1] // 4)] if v else []
            return {"kind": "anim", "clips": [c for c in clips if c],
                    "mode": {1: "LOOP", 2: "CLAMP"}.get(db.u32(action + DEVANIM_MODE), "DIE")}
        if kind == "DeviceVisActionList":
            parts = [decode(a) for a in db.pointers(action + DEVLIST_ELEMENTS)]
            return next((x for x in parts if x is not None), None)
        return None
    scripts = db.ptr(stele + STELE_VISSCRIPTS)
    if scripts is None:
        return None, []
    return decode(db.ptr(scripts + DVS_DEFAULT)), [decode(a) for a in db.pointers(scripts + DVS_STATES)]


def gameview_script(db: PackDB, script: int | None, anim_names: dict) -> dict[str, list[dict]]:
    """Actions d'un `GameViewScript` par créature (`scriptID` de la scène) : animation (en boucle ou
    une fois, après `delayBefore` et les `VisActionDelay` d'une liste), mort (`Death`, tenue),
    disparition (`CreatureSetTransparencyAction` à 0)."""
    out: dict[str, list[dict]] = {}
    for action in (db.pointers(script + GVSCRIPT_ACTIONS) if script is not None else []):
        kind = db.vtype(action)
        delay = max(0, db.i32(action + GVSCRIPT_DELAY)) / 1000.0
        if kind == "GameViewActionMoveCreature":
            # Marche le long d'un chemin de la scène (`pathID`) à sa vitesse (`speed`, m/s).
            mob = db.string(action + GVA_MOVE_MOB)
            if mob:
                out.setdefault(mob, []).append({"delay": delay, "move": db.string(action + GVA_MOVE_PATH) or "",
                                                "speed": max(db.f32(action + GVA_MOVE_SPEED), 0.1)})
            continue
        creature = db.string(action + GVACTION_CREATURE)
        if not creature:
            continue
        steps = out.setdefault(creature, [])
        if kind == "GameViewActionCreatureDeath":
            steps.append({"delay": delay, "clips": ["Death"], "loop": False, "hold": True})
            continue
        if kind == "GameViewActionClientData":
            for akind, act in client_data_actions(db, db.ptr(action + GVA_DATA)):
                if akind in ("CreatureScaleAction", "CreatureSetTransparencyAction"):
                    steps.append({"delay": delay, "hide": True})     # échelle 0, transparence 0 : seules valeurs employées
                elif akind == "CreatureEffectsAction":
                    for fx in db.elements(act + CVA_EFFECTS, CVA_EFFECT_STRIDE):
                        if db.ptr(fx + CVA_EFFECT_FX) is not None:
                            steps.append({"delay": delay, "fx": db.ptr(fx + CVA_EFFECT_FX)})
            continue
        if kind != "GameViewActionCreatureVisScript":
            continue            # `GameViewActionCreatureEmote` (`idle`) : l'attente du modèle
        node = read_action(db, db.ptr(action + GVACTION_ACTION))
        wait = 0.0
        for item in (node.get("elements", []) if node and node["type"] == "VisActionList" else [node] if node else []):
            if item["type"] == "VisActionDelay":
                wait += item["time"]
            elif item["type"] == "CreatureAnimationAction":
                clips = [clip_name(anim_names.get(a, "")) for a in item["animations"]]
                steps.append({"delay": delay + wait, "clips": [c for c in clips if c], "loop": item["mode"] == "LOOP",
                              "hold": item["mode"] == "CLAMP"})
            elif item["type"] == "CreatureSetTransparencyAction" and item["transparency"] <= 0:
                steps.append({"delay": delay + wait, "hide": True})
    return out


def stele_components(db: PackDB, cat, vot: int, ident: str, actions: list[dict], horizon: float, anim_names: dict,
                     report: list[str]) -> list[dict]:
    """Composants du modèle d'une stèle, posés comme effets accrochés à elle (`attach`) : un
    `StateComponent` est montré pendant les actions dont l'animation est l'une des siennes (jusqu'à
    la fin de la scène s'il ne s'arrête pas à l'animation suivante, `stopForOtherAnimation` faux),
    un composant simple tout le temps. Le navire kanien `League_Ship_Final` n'est que cela : son
    modèle `KaniaShip` est une boîte invisible, sa coque (`KaniaShip_Clear`, puis `KaniaShip_Break`
    en flammes) et le Спрутоглав qui l'enserre sont des composants d'état."""
    rev = {v: k for k, v in db.ids.items()}
    out = []
    for comp in read_visobject(db, cat, vot).components:
        if comp.visobject is None or comp.cancelled:
            continue
        if comp.visobject not in rev:
            report.append(f"{ident} : composant {read_visobject(db, cat, comp.visobject).name} sans identifiant, non posé")
            continue
        if comp.state_ids is None:
            windows = [(-1e5, horizon)]
        else:
            wanted = {anim_names.get(i, "").lower() for i in comp.state_ids}
            spans = sorted((act["t"], act["until"] if comp.stop_other else horizon) for act in actions
                           if act["clips"] and act["clips"][0].lower() in wanted)
            merged: list[list[float]] = []
            for t0, t1 in spans:
                if merged and t0 <= merged[-1][1] + 1e-6:
                    merged[-1][1] = max(merged[-1][1], t1)
                else:
                    merged.append([t0, t1])
            windows = [(a, b) for a, b in merged]
        x, y, z, w = comp.rotation
        if abs(x) > 1e-4 or abs(y) > 1e-4:
            report.append(f"{ident} : composant incliné, seul son lacet est repris")
        yaw = 2 * math.atan2(z, w)
        for t0, t1 in windows:
            if t1 <= t0:
                continue
            kind = "StateComponent" if comp.state_ids is not None else "AttachedVisObjectComponent"
            item = {"vot": rev[comp.visobject], "attach": ident, "t": round(t0, 3), "until": round(t1, 3),
                    "_source": f"{kind} {comp.locator or '-'}"}
            if any(abs(v) > 1e-6 for v in comp.offset):
                item["p"] = [round(float(v), 4) for v in comp.offset]
            if abs(yaw) > 1e-5:
                item["yaw"] = round(yaw, 5)
            if abs(comp.scale - 1) > 1e-6 and comp.scale > 0:
                item["scale"] = round(comp.scale, 5)
            out.append(item)
    return out


def state_windows(initial: int, changes: list[dict], horizon: float) -> list[tuple[float, float, int]]:
    """Fenêtres `(début, fin, état)` d'une stèle : état initial (celui que lui a laissé le tutoriel,
    donné par le manifeste) puis ses `ImpactSetVisualState`, 1 = premier état du script."""
    out, t, state = [], -1e6, initial
    for change in sorted(changes, key=lambda c: c["t"]):
        out.append((t, change["t"], state))
        t, state = change["t"], change["state"]
    out.append((t, horizon, state))
    return [w for w in out if w[1] > w[0]]


def projectile_fx(db: PackDB, cat, explosion: str | None, projectile: str | None, the_ge: float,
                  root: Path | None = None) -> int | None:
    """Gabarit d'explosion du 17.0 d'un `CreatureFixedPointProjectileAction` 7.0 : l'action du client
    aux mêmes gabarits (nommés par leur binaire) et au même `theGe` (`+0x78`)."""
    from tools.allods_visdb import vot_name

    def stem(path: str | None) -> str | None:
        return Path(path).name.split(".(")[0] if path else None
    want_e, want_p = stem(explosion), stem(projectile)
    fallback = None
    for action in db.structs("CreatureFixedPointProjectileAction"):
        e, pr = db.ptr(action + 0x48), db.ptr(action + 0x70)
        if e is None or vot_name(db, cat, e) != want_e:
            continue
        fallback = fallback or e
        if (pr is not None and vot_name(db, cat, pr) == want_p) and abs(db.f32(action + 0x78) - the_ge) < 1e-3:
            return e
    if fallback is None and root is not None and explosion:
        # Gabarit 7.0 propre à la scène (`Descending_Dust_enlarge`), nommé dans le 17.0 par son binaire
        # (`Descending_Dust`) : celui du 17.0 aux mêmes binaire, fondus et échelle, tiré par une action
        # du même projectile.
        from tools import cutscene_xdb70 as x70
        from tools.allods_visdb import VOT_FADE_IN, VOT_FADE_OUT, VOT_SCALE
        doc = x70._read(Path(root) / explosion)
        if doc is None:
            return None
        names = {stem(n.get("href").split("#")[0]) for n in (doc.find("geometry"), doc.find("particle")) if n is not None and n.get("href")}
        want = (int(x70._f(doc, "fadeInMS")), int(x70._f(doc, "fadeOutMS")), x70._f(doc, "scale", 1.0))
        found = set()
        for action in db.structs("CreatureFixedPointProjectileAction"):
            e, pr = db.ptr(action + 0x48), db.ptr(action + 0x70)
            if e is None or vot_name(db, cat, e) not in names or (pr is not None and vot_name(db, cat, pr) != want_p):
                continue
            if (db.i32(e + VOT_FADE_IN), db.i32(e + VOT_FADE_OUT)) == want[:2] and abs(db.f32(e + VOT_SCALE) - want[2]) < 1e-4:
                found.add(e)
        return found.pop() if len(found) == 1 else None
    return fallback


_VOT_BY_NAME: dict[int, dict[str, list[int]]] = {}


def vots_named(db: PackDB, cat, name: str) -> list[int]:
    """Gabarits du 17.0 nommés `name` (nom du binaire de leur géométrie ou de leurs particules)."""
    from tools.allods_visdb import vot_name
    index = _VOT_BY_NAME.get(id(db))
    if index is None:
        index = _VOT_BY_NAME[id(db)] = {}
        for off in db.resources("VisObjectTemplate"):
            index.setdefault(vot_name(db, cat, off).lower(), []).append(off)
    return index.get(name.lower(), [])


def pick_vot_70(db: PackDB, root: Path, template: str | None, found: list[int]) -> list[int]:
    """Entre des gabarits du 17.0 homonymes, ceux qui ont les fondus (`fadeInMS`/`fadeOutMS`) et
    l'échelle du gabarit 7.0 `template` (chemin `.xdb` de l'arbre)."""
    from tools import cutscene_xdb70 as x70
    from tools.allods_visdb import VOT_FADE_IN, VOT_FADE_OUT, VOT_GEOMETRY, VOT_PARTICLE, VOT_SCALE
    doc = x70._read(Path(root) / template.split("#")[0].lstrip("/")) if template else None
    if doc is None or len(found) < 2:
        return found
    want = (int(x70._f(doc, "fadeInMS")), int(x70._f(doc, "fadeOutMS")), x70._f(doc, "scale", 1.0))
    kept = [off for off in found if (db.i32(off + VOT_FADE_IN), db.i32(off + VOT_FADE_OUT)) == want[:2]
            and abs(db.f32(off + VOT_SCALE) - want[2]) < 1e-4]

    def content(off: int) -> tuple:
        geo = db.ptr(off + VOT_GEOMETRY)
        return (db.binary_ref(geo) if geo is not None else None, db.ptr(off + VOT_PARTICLE),
                db.bytes(off, 0x140))
    if len(kept) > 1 and len({content(off) for off in kept}) == 1:
        # doublons du 17.0 (`Magic_Wall` : même binaire de géométrie, mêmes particules, octets égaux)
        return [min(kept)]
    return kept


VOT_COMPONENTS_17 = 0x138     # composants du gabarit (pointeurs)
STATECOMP_ANIMS = 0x68         # `StateComponent` : animations (u32 de l'énumération)
STATECOMP_COMPONENT = 0x88     # composant joué (`AttachedVisObjectComponent`)
ATTACHED_VISOBJECT = 0x88      # `AttachedVisObjectComponent.visObject` (recoupé sur les trois états du cinéma pridien)


def state_components_17(db: PackDB, vot: int, anim_names: dict) -> dict[str, int]:
    """Composants d'état d'un gabarit du 17.0 : animation (minuscules) → gabarit accroché."""
    out: dict[str, int] = {}
    for sc in db.pointers(vot + VOT_COMPONENTS_17):
        if db.vtype(sc) != "StateComponent":
            continue
        comp = db.ptr(sc + STATECOMP_COMPONENT)
        target = db.ptr(comp + ATTACHED_VISOBJECT) if comp is not None and db.vtype(comp) == "AttachedVisObjectComponent" else None
        if target is None or db.vtype(target) != "VisObjectTemplate":
            continue
        v = db.vec(sc + STATECOMP_ANIMS)
        for k in range(v[1] // 4 if v else 0):
            name = anim_names.get(db.u32(v[0] + 4 * k))
            if name:
                out[name.lower()] = target
    return out


def static_device_states(root: Path, sp: dict) -> list[dict | None]:
    """États (7.0) d'une stèle posée sur un objet du décor (`StaticDevice`) : changement de modèle
    (`DeviceVisActionChangeModel` : nom du gabarit) ou animation (`DeviceAnimationAction`)."""
    from tools import cutscene_xdb70 as x70
    tree = x70.Tree(Path(root))
    stele = tree.root / sp["mob"]
    doc = x70._read(stele)
    vis = doc.find("visScripts") if doc is not None else None
    base = tree.resolve(stele, vis.get("href")) if vis is not None and vis.get("href") else None
    vdoc = x70._read(base) if base is not None else None
    out: list[dict | None] = []
    for item in (vdoc.findall("states/Item") if vdoc is not None else []):
        action = item.find("action")
        kind = (action.get("type") or "") if action is not None else ""
        if kind.endswith("DeviceVisActionChangeModel"):
            href = (action.find("visObj").get("href") or "") if action.find("visObj") is not None else ""
            out.append({"kind": "model", "name": Path(href.split("#")[0]).name.split(".(")[0]} if href else None)
        elif kind.endswith("DeviceAnimationAction"):
            clips = [clip_name(a.text) for a in action.findall("animations/Item") if a.text]
            out.append({"kind": "anim", "clips": clips, "mode": action.findtext("mode") or "DIE"})
        else:
            out.append(None)
    return out


def static_device_extras(spec: dict, plan: dict, script: str, sp: dict, windows: list, root: Path, db: PackDB, cat,
                         report: list[str]) -> None:
    """Stèle d'un objet du décor : l'objet posé (gabarit statique de la carte) est retiré pendant un
    état qui change son modèle (le gabarit de l'état le remplace, à la même place) ou l'anime (le
    gabarit joue les animations de l'état, en acteur)."""
    base = Path(sp.get("static") or "").name.split(".(")[0]
    states = static_device_states(root, sp)
    ident = re.sub(r"[^a-z0-9]+", "-", script.lower()).strip("-")
    for t0, t1, state in windows:
        st = states[state - 1] if 1 <= state <= len(states) else None
        if st is None or t0 < -1e5:
            continue
        if st["kind"] == "model":
            found = vots_named(db, cat, st["name"])
            if len(found) != 1:
                report.append(f"{spec['id']} : stèle {script}, état {state} : gabarit {st['name']} "
                              f"{'introuvable' if not found else 'ambigu'} dans le 17.0")
                continue
            plan.setdefault("decor_windows", []).append({"hide": base, "p": sp["p"], "t": t0, "until": t1})
            plan["decor_windows"].append({"show": found[0], "name": st["name"], "p": sp["p"], "yaw": round(sp["yaw"], 5),
                                          "t": t0, "until": t1})
            report.append(f"{spec['id']} : stèle {script} (objet {base}) → modèle {st['name']} de {t0} à {t1} s")
        else:
            found = vots_named(db, cat, base)
            if len(found) != 1:
                report.append(f"{spec['id']} : stèle {script} : gabarit {base} {'introuvable' if not found else 'ambigu'}")
                continue
            if any(c.state_ids is None for c in read_visobject(db, cat, found[0]).components):   # hors composants d'état
                report.append(f"{spec['id']} : stèle {script} : gabarit {base} à composants, animation d'état non jouée")
                continue
            plan.setdefault("decor_windows", []).append({"hide": base, "p": sp["p"], "t": t0, "until": t1})
            plan["actors"].append({"id": ident, "mob_offset": None, "visual": None, "vot": found[0],
                                   "path": [{"t": 0, "p": sp["p"], "yaw": round(sp["yaw"], 5)}],
                                   "presence": [[round(t0, 3), round(t1, 3)]], "animations": st["clips"],
                                   "clips_wanted": st["clips"], "idle": None, "name": {},
                                   "actions": [{"t": round(t0, 3), "until": round(t1, 3), "clips": st["clips"],
                                                "loop": st["mode"] == "LOOP", **({"hold": True} if st["mode"] == "CLAMP" else {})}]})
            report.append(f"{spec['id']} : stèle {script} (objet {base}) → animation {st['clips']} de {t0} à {t1} s")


def channel_spawn(spec: dict, plan: dict, item: dict, spawns: dict, db: PackDB, cat, rev: dict, root: Path,
                  report: list[str]) -> dict | None:
    """Rayon canalisé (`CreatureChannelDirectAction`) d'un PNJ vers un repère : gabarit du 17.0 au nom
    du `channelingFx` 7.0, longueur modelée (`fxLength`) et fondus de l'action du client qui le tire ;
    départ au locator de l'acteur, arrivée au repère ; jusqu'à son arrêt (`VisActionStopAction`)."""
    from tools.allods_visdb import vot_name
    ch = item["channel"]
    want = Path((ch.get("fx") or "").split("#")[0]).name.split(".(")[0]
    actor = next((a for a in plan["actors"] if a.get("server") is spawns.get(item["owner"])), None)
    end = spawns.get(item["locators"][0]) if item["locators"] else None
    found = {}
    for off in db.structs("CreatureChannelDirectAction"):
        node = read_action(db, off)
        vis = node.get("visObject") if node else None
        if vis is not None and vot_name(db, cat, vis) == want:
            found.setdefault((vis, round(node.get("length") or 0.0, 3)), node)
    if len(found) > 1 and ch.get("locator"):
        # plusieurs actions du 17.0 tirent ce gabarit : celles qui partent du même locator que la 7.0
        same = {k: v for k, v in found.items() if (v.get("start") or {}).get("locator") == ch["locator"]}
        report.append(f"{spec['id']} : rayon {want} : départs du 17.0 "
                      f"{sorted((k[1], (v.get('start') or {}).get('locator')) for k, v in found.items())}")
        found = same or found
    if len({k[0] for k in found}) > 1:
        keep = set(pick_vot_70(db, root, ch.get("fx"), sorted({k[0] for k in found})))
        found = {k: v for k, v in found.items() if k[0] in keep}
    if actor is None or end is None or len({k[0] for k in found}) != 1 or found and next(iter(found))[0] not in rev:
        report.append(f"{spec['id']} : rayon non rendu ({item['clientdata']} : gabarit {want}, "
                      f"{len(found)} actions du 17.0, acteur {'trouvé' if actor else 'absent'})")
        return None
    (vis, length), node = next(iter(found.items()))
    if len(found) > 1:
        report.append(f"{spec['id']} : rayon {want} non rendu : longueurs {sorted(k[1] for k in found)} dans le 17.0, "
                      f"aucune établie pour cette action")
        return None
    return {"vot": rev[vis], "t": item["t"], "until": item["until"] if item["until"] is not None else item["t"] + 600,
            "channel": {"from": actor["id"], "locator": ch.get("locator") or "Global", "to": end["p"], "length": length},
            "_source": item["clientdata"]}


def table_steles(spec: dict, tl, spawns: dict, root: Path, db: PackDB, cat, rev: dict, horizon: float,
                 report: list[str]) -> list[dict]:
    """Tables d'apparition posées par le déroulé (`SpawnTableObjects`) dont l'objet est une stèle d'effet
    (mur magique de `Floor_Firewall`) : son gabarit (`visObj`, à son `scale`) à la place de la table."""
    from tools import cutscene_xdb70 as x70
    tree = x70.Tree(Path(root))
    out = []
    for item in tl.tables:
        path = tree.root / item["table"]
        doc = x70._read(path)
        objs = [o.get("href") for o in (doc.iter("object") if doc is not None else []) if o.get("href")]
        steles = [tree.resolve(path, h) for h in objs if ".(SteleResource)" in h]
        if not steles:
            report.append(f"{spec['id']} : table {Path(item['table']).name} ({len(objs)} PNJ du jeu) non montée")
            continue
        sp = spawns.get("table:" + item["table"])
        sdoc = x70._read(steles[0])
        vis = sdoc.find("visObj") if sdoc is not None else None
        name = Path((vis.get("href") or "").split("#")[0]).name.split(".(")[0] if vis is not None else ""
        found = vots_named(db, cat, name) if name else []
        found = pick_vot_70(db, root, vis.get("href") if vis is not None else None, found)
        if sp is None or len(found) != 1 or found[0] not in rev:
            report.append(f"{spec['id']} : stèle de table {Path(item['table']).name} non posée (gabarit {name or '—'}, "
                          f"{len(found)} au 17.0, place {'trouvée' if sp else 'absente'})")
            continue
        out.append({"vot": rev[found[0]], "p": sp["p"], "yaw": round(sp["yaw"], 5), "scale": x70._f(sdoc, "scale", 1.0),
                    "t": item["t"], "until": item["until"] if item["until"] is not None else horizon,
                    "_source": item["table"]})
        report.append(f"{spec['id']} : table {Path(item['table']).name} → gabarit {name} de {item['t']} s")
    return out


def trigger_extras(spec: dict, plan: dict, tl, spawns: dict, root: Path, db: PackDB, cat, anim_names: dict,
                   report: list[str]) -> None:
    """Scène ouverte par un déclencheur (zone de script, capacité) : stèles et leurs états (scènes du
    client, animation du modèle), PNJ posés qui marchent ou disparaissent, porteur mort d'un
    `HealthTrigger`, explosions des `ClientData` aux repères, sons ponctuels ; puis la fenêtre de
    la scène : du premier plan de caméra (avant, la vue est celle du joueur) à sa fin."""
    from tools import cutscene_xdb70 as x70
    rev = {v: k for k, v in db.ids.items()}
    horizon = plan["camera"]["duration"]
    actors = plan["actors"]
    # PNJ posés : trajets (`GoThroughPath`, à la `walkSpeed` du `MobWorld`), retrait (`Disintegrate`).
    for actor in actors:
        script = next((k for k, sp in spawns.items() if actor.get("server") is sp), None)
        if script is None:
            continue
        moves = tl.spawn_moves.get(script, [])
        if moves:
            speed = x70.walk_speed(root / actor["server"]["mob"])
            path, t, here = actor["path"], 0.0, np.array(actor["path"][0]["p"], float)
            for move in moves:
                # course (`runningMode`) : le `MobWorld` ne donne que `walkSpeed` (voir `RUN_SPEED`)
                pace = RUN_SPEED if move.get("run") else speed
                dest = spawns.get(move["locator"])
                if dest is None:
                    report.append(f"{spec['id']} : repère introuvable : {move['locator']}")
                    continue
                there = np.array(dest["p"], float)
                start = max(move["t"], t)
                heading = face_yaw(list(here), list(there))
                path.append({"t": round(start, 3), "p": path[-1]["p"], "yaw": heading})
                t = start + float(np.linalg.norm(there[:2] - here[:2])) / max(pace, 0.1)
                path.append({"t": round(t, 3), "p": [round(float(v), 4) for v in there], "yaw": heading})
                here = there
            actor["move"] = "Run" if any(m.get("run") for m in moves) else "Walk"
            actor["walk_end"] = round(t, 3)
        if script in tl.kills:
            actor.setdefault("actions", []).append({"t": tl.kills[script], "until": 1e6, "clips": ["Death"], "loop": False,
                                                    "hold": True})
            actor["animations"] = sorted(set(actor.get("animations", [])) | {"Death"})
            actor["clips_wanted"] = actor["animations"]
        if script in tl.spawn_until:
            actor["presence"] = [[-1e6, tl.spawn_until[script]]]
        if script == spec.get("trigger_owner") and spec.get("trigger_effect") == "HealthTrigger":
            # Capacité de mort (`HealthTrigger` à `FloatZero`) : son porteur est tombé à l'instant 0.
            actor.setdefault("actions", []).append({"t": 0.0, "until": 1e6, "clips": ["Death"], "loop": False, "hold": True})
            actor["animations"] = sorted(set(actor.get("animations", [])) | {"Death"})
            actor["clips_wanted"] = actor["animations"]
    # Stèles : états visuels.
    initial = spec.get("states", {})
    scene_fx: list[dict] = []
    for script, sp in spawns.items():
        if not (sp["mob"] or "").endswith(".(SteleResource).xdb"):
            continue
        changes = [c for c in tl.states if c["spawn"] == script]
        if not changes and script not in initial:
            continue
        if sp.get("static"):
            static_device_extras(spec, plan, script, sp, state_windows(int(initial.get(script, 0)), changes, horizon),
                                 root, db, cat, report)
            continue
        stele = find_stele(db, sp["p"])
        if stele is not None:
            default, states = device_states(db, stele, anim_names)
        else:
            default, states = None, stele_states_70(root, sp, db)
            if not any(states):
                report.append(f"{spec['id']} : stèle {script} absente du 17.0 (aucune stèle en {sp['p']})")
                continue
            report.append(f"{spec['id']} : stèle {script} sans place dans le 17.0 : états relus dans l'arbre 7.0")
        windows = state_windows(int(initial.get(script, 0)), changes, horizon)
        ident = re.sub(r"[^a-z0-9]+", "-", script.lower()).strip("-")
        scene_states = [st for st in states if st and st["kind"] == "scene"]
        if scene_states:
            scene = scene_states[0]["scene"]
            place, place_yaw = _placement(db, scene + GVS_PLACE)
            c, s_ = math.cos(place_yaw), math.sin(place_yaw)
            scripts = [gameview_script(db, st["script"], anim_names) if st and st["kind"] == "scene" else {} for st in states]
            routes = scene_paths(db, scene)
            for e in db.elements(scene + GVS_MOBS, GVS_MOB_STRIDE):
                visual, name = db.ptr(e + GVS_MOB_VISUAL), db.string(e + GVS_MOB_SCRIPT) or ""
                if visual is None:
                    continue
                ox, oy, oz = db.floats(e + GVS_MOB_OFFSET, 3)
                pos = [round(place[0] + ox * c - oy * s_, 4), round(place[1] + ox * s_ + oy * c, 4), round(place[2] + oz, 4)]
                actions, presence, clips = [], [], set()
                path = [{"t": 0, "p": pos, "yaw": round(place_yaw + db.f32(e + GVS_MOB_YAW), 5)}]
                move = None
                for t0, t1, state in windows:
                    if not 1 <= state <= len(states) or not states[state - 1] or states[state - 1]["kind"] != "scene" \
                            or states[state - 1]["scene"] != scene:
                        continue        # état sans scène (ou `NoScene`) : les créatures du client ne sont pas montrées
                    shown = [t0, t1]
                    for step in scripts[state - 1].get(name, []):
                        at = t0 + step["delay"] if t0 > -1e5 else -1e5 + step["delay"]
                        if step.get("hide"):
                            shown[1] = min(shown[1], max(t0, at))
                            continue
                        if "move" in step:
                            # le long du chemin de la scène, depuis la place où il se trouve
                            start = max(at, path[-1]["t"])
                            here = path[-1]["p"]
                            if start - path[-1]["t"] > 2e-3:
                                path.append({"t": round(start, 3), "p": here, "yaw": path[-1]["yaw"]})
                            for q in routes.get(step["move"], []):
                                if math.dist(here[:2], q[:2]) < 0.05:
                                    continue
                                heading = face_yaw(here, q)
                                start = start + math.dist(here[:2], q[:2]) / step["speed"]
                                path.append({"t": round(start, 3), "p": q, "yaw": heading})
                                here = q
                            move = "Run" if step["speed"] >= RUN_SPEED_MIN else "Walk"
                            continue
                        if "fx" in step:
                            if step["fx"] in rev:
                                key = max((k for k in path if k["t"] <= at + 1e-6), key=lambda k: k["t"], default=path[0])
                                scene_fx.append({"vot": rev[step["fx"]], "p": key["p"], "t": round(at, 3), "until": None,
                                                 "_source": f"GameViewScript {rev.get(states[state - 1]['script'])}"})
                            continue
                        actions.append({"t": round(at, 3), "until": round(t1, 3), "clips": step["clips"], "loop": step["loop"],
                                        **({"hold": True} if step.get("hold") else {})})
                        clips.update(step["clips"])
                    if shown[1] > shown[0]:
                        presence.append([round(shown[0], 3), round(shown[1], 3)])
                if not presence:
                    continue
                actors.append({"id": f"{ident}-{name.lower()}", "mob_offset": None, "visual": visual,
                               "path": path, **({"move": move} if move else {}),
                               "animations": sorted(clips), "clips_wanted": sorted(clips), "actions": actions,
                               "presence": presence, "name": {}})
            report.append(f"{spec['id']} : stèle {script} → GameViewScene {rev.get(scene)}, états {windows}")
            continue
        vot = db.ptr(stele + STELE_VISOBJ)
        if vot is None:
            continue
        actions, clips = [], set()
        for t0, t1, state in windows:
            st = states[state - 1] if 1 <= state <= len(states) else default
            if not st or st["kind"] != "anim":
                continue
            actions.append({"t": round(max(t0, -1e5), 3), "until": round(t1, 3), "clips": st["clips"],
                            "loop": st["mode"] == "LOOP", **({"hold": True} if st["mode"] == "CLAMP" else {})})
            clips.update(st["clips"])
        actors.append({"id": ident, "mob_offset": None, "visual": None, "vot": vot, "path": [{"t": 0, "p": sp["p"],
                       "yaw": model_yaw(sp["yaw"])}], "animations": sorted(clips), "clips_wanted": sorted(clips),
                       "actions": actions, "idle": None, "name": {}})
        parts = stele_components(db, cat, vot, ident, actions, horizon, anim_names, report)
        scene_fx.extend(parts)
        report.append(f"{spec['id']} : stèle {script} → modèle {rev.get(vot)}, états {windows}, "
                      f"{len(parts)} composant(s) posé(s)")
    # Explosions posées aux repères (`CreatureFixedPointProjectileAction`, à l'arrivée du projectile).
    fx = []
    for item in tl.fx:
        if item.get("channel") is not None and not isinstance(item["channel"], bool):
            spawn = channel_spawn(spec, plan, item, spawns, db, cat, rev, root, report)
            if spawn is not None:
                fx.append(spawn)
            continue
        locs = item["locators"]
        end = spawns.get(locs[min(item["end"], len(locs) - 1)]) if locs else None
        vot = projectile_fx(db, cat, item["explosion"], item["projectile"], item["theGe"], root)
        if end is None or vot is None or vot not in rev:
            report.append(f"{spec['id']} : effet non posé : {item['clientdata']} ({locs})")
            continue
        if item["throw"] > 0 and len(set(locs)) > 1:
            report.append(f"{spec['id']} : vol du projectile non rendu ({Path(item['projectile'] or '').name}, "
                          f"{item['throw']} s, theGe {item['theGe']}) ; explosion à l'arrivée")
        fx.append({"vot": rev[vot], "p": end["p"], "t": round(item["t"] + item["throw"], 3), "until": None,
                   "_source": item["clientdata"]})
    fx += table_steles(spec, tl, spawns, root, db, cat, rev, horizon, report)
    # Stèles du décor qui lisent un drapeau posé sur le joueur (`CreatureSetFlagVisAction`) : animées
    # tant qu'il est posé (cinéma pridien : `special` en boucle).
    for dev in x70.flag_devices(root, plan["map"], {f["flag"] for f in tl.flags}):
        base = Path(dev["static"] or "").name.split(".(")[0]
        found = vots_named(db, cat, base)
        if len(found) != 1:
            report.append(f"{spec['id']} : stèle à drapeau {base} : gabarit {'introuvable' if not found else 'ambigu'}")
            continue
        if any(c.state_ids is None for c in read_visobject(db, cat, found[0]).components):   # hors composants d'état
            # gabarit fait de composants (cinéma : écran animé + bâtiment) : l'acteur n'exporte que la
            # géométrie squelettique ; l'objet du décor reste, son animation d'état n'est pas jouée
            report.append(f"{spec['id']} : stèle à drapeau {base} : gabarit à composants, animation d'état non jouée "
                          f"(l'objet du décor reste tel quel)")
            continue
        states = state_components_17(db, found[0], anim_names)
        for branch in dev["branches"]:
            for f in (f for f in tl.flags if f["flag"] == branch["flag"]):
                t0, t1 = f["t"], f["until"] if f["until"] is not None else horizon
                clips = [clip_name(c) for c in branch["clips"]]
                if states:
                    # Gabarit à composants d'état (`StateComponent` : un modèle accroché par animation ; le
                    # cinéma : `idle` → Hadagan_Cinema_Priden, `special` → Hadagan_Cinema_PridenReview du
                    # 7.0) : le modèle de l'état joué est posé à la place de l'objet, le temps du drapeau
                    # (locator `Slot_Special01` pris à la racine : le gabarit de base n'a pas de squelette).
                    # l'objet du décor montre l'état par défaut de ses composants (`FxBuild.default_state`) :
                    # retiré le temps de l'état joué, que son modèle remplace
                    plan.setdefault("decor_windows", []).append({"hide": base, "p": dev["p"], "t": t0, "until": t1})
                    for clip in branch["clips"]:
                        comp = states.get(clip.lower())
                        if comp is None or comp not in rev:
                            report.append(f"{spec['id']} : {base} : pas de composant d'état pour {clip}")
                            continue
                        plan.setdefault("decor_windows", []).append(
                            {"show": comp, "name": f"{base}:{clip}", "p": dev["p"], "yaw": round(dev["yaw"], 5),
                             "scale": round(dev["scale"], 5), "t": t0, "until": t1})
                        report.append(f"{spec['id']} : stèle {base} : état {clip} → composant {rev[comp]} "
                                      f"tant que {Path(f['flag']).name} est posé ({t0} à {t1} s)")
                    continue
                plan.setdefault("decor_windows", []).append({"hide": base, "p": dev["p"], "t": t0, "until": t1})
                plan["actors"].append({"id": re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-"), "mob_offset": None,
                                       "visual": None, "vot": found[0], "scale": round(dev["scale"], 5),
                                       "path": [{"t": 0, "p": dev["p"], "yaw": round(dev["yaw"], 5)}],
                                       "presence": [[round(t0, 3), round(t1, 3)]], "animations": clips,
                                       "clips_wanted": clips, "idle": None, "name": {},
                                       "actions": [{"t": round(t0, 3), "until": round(t1, 3), "clips": clips,
                                                    "loop": branch["mode"] == "LOOP"}]})
                report.append(f"{spec['id']} : stèle {base} ({dev['file']}) : {clips} tant que {Path(f['flag']).name} "
                              f"est posé ({t0} à {t1} s)")
    plan["spawns"] = fx + scene_fx
    plan["doors"] = list(tl.doors)
    plan["sounds"]["sfx"] = [{"event": s["name"], "t": s["t"]} for s in tl.sfx]
    # Fenêtre : du premier plan de caméra à la fin de la scène.
    t0 = min((k["t"] for k in plan["camera"]["points"]), default=0.0)
    if t0 > 0:
        shift_plan(plan, t0, report, spec["id"])


def shift_plan(plan: dict, t0: float, report: list[str], ident: str) -> None:
    """Ramène l'instant `t0` (début de la scène filmée) à 0 ; ce qui finit avant est ôté."""
    cam = plan["camera"]
    for track in ("points", "targets"):
        cam[track] = [{**k, "t": round(k["t"] - t0, 3)} for k in cam[track]]
    cam["duration"] = round(cam["duration"] - t0, 3)
    dropped = [l for l in plan["lines"] if l["start"] is not None and l["start"] + l["duration"] <= t0]
    for line in dropped:
        report.append(f"{ident} : réplique avant le premier plan, hors scène : {line['voice_event']} ({line['start']} s)")
    plan["lines"] = [{**l, "start": round(l["start"] - t0, 3)} for l in plan["lines"] if l not in dropped]
    for actor in plan["actors"]:
        actor["path"] = [{**k, "t": round(k.get("t", 0) - t0, 3)} for k in actor["path"]]
        for action in actor.get("actions", []):
            action["t"], action["until"] = round(action["t"] - t0, 3), round(action["until"] - t0, 3)
        if actor.get("presence"):
            actor["presence"] = [[round(a - t0, 3), round(b - t0, 3)] for a, b in actor["presence"]]
    # PNJ qui ne sont plus là quand la scène commence (retirés avant le premier plan).
    plan["actors"] = [a for a in plan["actors"] if not a.get("presence") or any(b > 0 for _, b in a["presence"])]
    # Effets encore là au premier plan (composants d'état d'une stèle, posés avant la scène) : gardés.
    plan["spawns"] = [{**s, "t": round(s["t"] - t0, 3), **({"until": round(s["until"] - t0, 3)} if s.get("until") is not None else {})}
                      for s in plan.get("spawns", []) if s["t"] >= t0 or (s.get("until") is not None and s["until"] > t0)]
    plan["doors"] = [{**d, "t": round(d["t"] - t0, 3)} for d in plan.get("doors", [])]
    for key, items in plan["sounds"].items():
        plan["sounds"][key] = [{**s, "t": round(s["t"] - t0, 3), **({"until": round(s["until"] - t0, 3)} if "until" in s else {})}
                               for s in items if s.get("until", s["t"] + 30) > t0]
    plan["post"] = [{**p, "t": round(p["t"] - t0, 3), "until": round(p["until"] - t0, 3)} for p in plan["post"] if p["until"] > t0]
    plan["shakes"] = [{**s, "t": round(s["t"] - t0, 3)} for s in plan.get("shakes", []) if s["t"] >= t0]
    for item in plan.get("decor_windows", []):
        for key in ("t", "until"):
            if item.get(key) is not None:
                item[key] = round(item[key] - t0, 3)
    plan["sources"]["window"] = [t0, round(t0 + cam["duration"], 3)]


def move_clip(move: str | None, animations: dict) -> str | None:
    """Clip de déplacement : la marche, ou la course d'un modèle qui n'a pas de marche (le
    Спрутоглав, `AstralCtulhu` : `Run` sans `Walk`, qui se déplace à sa `walkSpeed` de 8 m/s) ;
    choix documenté : le client choisit l'allure, les données ne disent pas laquelle il montre."""
    if move == "Walk" and "Walk" not in animations and "Run" in animations:
        return "Run"
    return move


def actor_model_key(actor: dict) -> int:
    if actor.get("vot") is not None:
        return actor["vot"]
    return actor["visual"] if actor.get("visual") is not None else actor["mob_offset"]


def actor_file_key(actor: dict) -> str:
    if actor.get("vot") is not None:
        return f"vot-{actor['vot']:x}"
    return f"mob-{actor['mob_offset']:x}" if actor.get("visual") is None else f"vis-{actor['visual']:x}"


# `GameViewScene` (17.0) : place et placement de caméra en doubles x, y, puis f32 lacet, puis double z.
GVS_CAMERA = 0x38
GVS_MOBS = 0xA0
GVS_MOB_STRIDE = 192
GVS_MOB_VISUAL = 0xB0
GVS_MOB_OFFSET = 0x70
GVS_MOB_SCRIPT = 0x80
GVS_MAP = 0xE8
GVS_PLACE = 0xF0
SHOW_SCENE = 0x50
SHOW_SCRIPT = 0x58
GVSCRIPT_ACTIONS = 0x48
GVACTION_CREATURE = 0xA0
GVACTION_ACTION = 0xB8


def _placement(db: PackDB, off: int) -> tuple[list[float], float]:
    x, y = struct.unpack_from("<2d", db.raw, db.data + off)
    z, = struct.unpack_from("<d", db.raw, db.data + off + 0x18)
    return [round(x, 4), round(y, 4), round(z, 4)], db.f32(off + 0x10)


# `GameViewScript` : actions recoupées sur les `.xdb` 7.0 de `Inst_LeagueStart` (`Device_Floor1_*`).
GVS_PATHS = 0xC0             # chemins de la scène (72 o : +0x08 points f32 x, y, z relatifs, +0x28 scriptID)
GVS_PATH_STRIDE = 72
GVS_PATH_POINTS = 0x08
GVS_PATH_ID = 0x28
GVA_MOVE_MOB = 0xC0          # `GameViewActionMoveCreature` : mobID, pathID, speed (m/s)
GVA_MOVE_PATH = 0xD8
GVA_MOVE_SPEED = 0xF0
GVA_DATA = 0xC0              # `GameViewActionClientData` : creature en +0xA0, `ClientData` en +0xC0
CLIENT_DATA = 0x28           # `ClientData.customData` : une action (`CreatureVisActionData`) ou une liste
CVA_ACTION = 0x30
CVA_EFFECTS = 0x48           # `CreatureEffectsAction.visualEffects` (176 o : +0x40 `effectFx`)
CVA_EFFECT_STRIDE = 176
CVA_EFFECT_FX = 0x40
# Allure d'un PNJ de scène qui suit un chemin : course au-delà de 4 m/s (les scènes de
# `Inst_LeagueStart` font courir leurs foules à 6,5 m/s, la marche des PNJ est à 2 m/s) ; choix documenté.
RUN_SPEED_MIN = 4.0


def client_data_actions(db: PackDB, cd: int | None) -> list[tuple[str, int]]:
    """Actions visuelles d'un `ClientData` (`CreatureVisActionData` seule ou dans une liste)."""
    data = db.ptr(cd + CLIENT_DATA) if cd is not None else None
    if data is None:
        return []
    elements = db.pointers(data + 0x30) if db.vtype(data) == "CustomClientDataList" else [data]
    out = []
    for el in elements:
        act = db.ptr(el + CVA_ACTION) if db.vtype(el) == "CreatureVisActionData" else None
        if act is not None and db.vtype(act):
            out.append((db.vtype(act), act))
    return out


def scene_paths(db: PackDB, scene: int) -> dict[str, list[list[float]]]:
    """Chemins d'une `GameViewScene` (points relatifs à sa place, tournés par son lacet)."""
    place, yaw = _placement(db, scene + GVS_PLACE)
    c, s_ = math.cos(yaw), math.sin(yaw)
    out = {}
    for e in db.elements(scene + GVS_PATHS, GVS_PATH_STRIDE):
        v = db.vec(e + GVS_PATH_POINTS)
        pts = [db.floats(v[0] + 12 * i, 3) for i in range(v[1] // 12)] if v else []
        out[db.string(e + GVS_PATH_ID) or ""] = [[round(place[0] + x * c - y * s_, 4), round(place[1] + x * s_ + y * c, 4),
                                                   round(place[2] + z, 4)] for x, y, z in pts]
    return out


def stele_states_70(root: Path, sp: dict, db: PackDB) -> list[dict | None]:
    """États d'une stèle relus dans l'arbre 7.0 (`SteleResource.visScripts` → `states`) quand le 17.0
    n'a pas de stèle à sa place (`Device_Floor6_GameScene`, posée par une table d'apparition) : chaque
    `ShowSceneAction` rapportée au 17.0 par la place et les PNJ de sa `GameViewScene`, et par le nombre
    d'actions de son `GameViewScript`."""
    from tools import cutscene_xdb70 as x70
    tree = x70.Tree(Path(root))
    stele = tree.root / sp["mob"]
    doc = x70._read(stele)
    vis = doc.find("visScripts") if doc is not None else None
    vdoc = x70._read(tree.resolve(stele, vis.get("href"))) if vis is not None and vis.get("href") else None
    out: list[dict | None] = []
    for item in (vdoc.findall("states/Item") if vdoc is not None else []):
        action = item.find("action")
        if action is None or not (action.get("type") or "").endswith("ShowSceneAction"):
            out.append(None)
            continue
        base = tree.resolve(stele, vis.get("href"))
        scene_href = action.find("scene").get("href", "")
        script = action.find("script")
        info = x70.read_game_scene(root, tree.rel(tree.resolve(base, scene_href)))
        scene = find_game_scene(db, info["place"], info["mobs"])
        count = x70.script_actions(root, tree.rel(tree.resolve(base, script.get("href")))) \
            if script is not None and script.get("href") else 0
        out.append({"kind": "scene", "scene": scene, "script": find_game_script(db, scene, count) if scene else None}
                   if scene is not None else None)
    return out


CAMMOVES_GROUPS = 0x48
CAMMOVE_GROUP_STRIDE = 48
CAMMOVE_GROUP_DELAY = 0x04
CAMMOVE_GROUP_MOVES = 0x08
CAMMOVE_STRIDE = 120
CAMMOVE_PITCH = 0x10
CAMMOVE_XY = 0x18          # doubles x, y ; f32 lacet en +0x28, roulis en +0x2C ; double z en +0x30
CAMMOVE_TIME = 0x6C
CAMMOVE_TIME_START = 0x70


def find_action(db: PackDB, off: int | None, kind: str, depth: int = 0) -> int | None:
    if off is None or depth > 8:
        return None
    if db.vtype(off) == kind:
        return off
    for loc, rk, target in db.relocs(off, off + 0x120):
        for child in ([db.ptr(loc)] if rk == 0 else db.pointers(loc) if rk == 3 else []):
            if child is not None and db.vtype(child):
                found = find_action(db, child, kind, depth + 1)
                if found is not None:
                    return found
    return None


def camera_moves(db: PackDB, action: int) -> list[dict]:
    """`CameraMovesAction` : groupes de mouvements (48 o : `+0x04` délai de départ, `+0x08` mouvements),
    mouvement (120 o : pose de départ en doubles x, y, z et f32 lacet, tangage, roulis ; `+0x6C`
    durée vers la pose suivante, `+0x70` `timeStart`) — recoupé au millième sur le `.xdb` 7.0 de
    `ShipExplosion_Script`. Rend les poses datées (s) ; un groupe coupe le précédent."""
    groups = db.elements(action + CAMMOVES_GROUPS, CAMMOVE_GROUP_STRIDE)
    keys = []
    for k, g in enumerate(groups):
        t = db.f32(g + CAMMOVE_GROUP_DELAY)
        end = db.f32(groups[k + 1] + CAMMOVE_GROUP_DELAY) if k + 1 < len(groups) else None
        for m in db.elements(g + CAMMOVE_GROUP_MOVES, CAMMOVE_STRIDE):
            x, y = struct.unpack_from("<2d", db.raw, db.data + m + CAMMOVE_XY)
            z, = struct.unpack_from("<d", db.raw, db.data + m + CAMMOVE_XY + 0x18)
            if end is not None and t >= end - 1e-3:
                # pose d'arrivée atteinte à l'instant de la coupe
                keys.append({"t": round(end - 1e-3, 3), "p": [round(x, 4), round(y, 4), round(z, 4)],
                             "yaw": db.f32(m + CAMMOVE_XY + 0x10), "pitch": db.f32(m + CAMMOVE_PITCH)})
                break
            keys.append({"t": round(t, 3), "p": [round(x, 4), round(y, 4), round(z, 4)],
                         "yaw": db.f32(m + CAMMOVE_XY + 0x10), "pitch": db.f32(m + CAMMOVE_PITCH)})
            t += db.f32(m + CAMMOVE_TIME) or 1.0
    return keys


def plan_gameview(spec: dict, db: PackDB, texts: Texts, anim_names: dict, report: list[str]) -> dict:
    """Scène entièrement du client (`GameViewScene` + `GameViewScript` d'un `ShowSceneAction`) : PNJ
    posés à la place de la scène (leur animation de cinématique porte leur déplacement), chacun jouant
    l'animation que le script lui donne, caméra au `cameraPlacement` de la scène."""
    import numpy as np
    from tools.allods_visdb import ANIM_LIST, ANIM_MODE
    scene = db.ids[int(spec["scene"])]
    place, place_yaw = _placement(db, scene + GVS_PLACE)
    cam, cam_yaw = _placement(db, scene + GVS_CAMERA)
    map_res = db.ptr(scene + GVS_MAP)
    map_path = next((p for p, o in db.paths.items() if o == map_res), "")
    map_name = spec.get("map") or (map_path.split("/")[1] if map_path.startswith("Maps/") else "")
    script = db.ids[int(spec["script"])] if spec.get("script") else None
    if script is None:
        hits = np.where((db.rtgt == scene) & (db.rkind == 0))[0]
        for i in hits:
            loc = int(db.rloc[i])
            j = int(np.searchsorted(db.vt_loc, loc, side="right")) - 1
            owner = int(db.vt_loc[j])
            if db.vtype(owner) == "ShowSceneAction" and loc - owner == SHOW_SCENE:
                script = db.ptr(owner + SHOW_SCRIPT)
                break
    clips: dict[int, list[str]] = {}
    for action in (db.pointers(script + GVSCRIPT_ACTIONS) if script is not None else []):
        creature = db.string(action + GVACTION_CREATURE)
        anim = db.ptr(action + GVACTION_ACTION)
        if not creature or not creature.isdigit() or anim is None or db.vtype(anim) != "CreatureAnimationAction":
            continue
        v = db.vec(anim + ANIM_LIST)
        names = [anim_names.get(db.u32(v[0] + 4 * k), "") for k in range(v[1] // 4)] if v else []
        clips[int(creature)] = [clip_name(n) for n in names if n]
    actors = []
    c, s_ = math.cos(place_yaw), math.sin(place_yaw)
    for k, e in enumerate(db.elements(scene + GVS_MOBS, GVS_MOB_STRIDE), 1):
        visual = db.ptr(e + GVS_MOB_VISUAL)
        if visual is None:
            continue
        ox, oy, oz = db.floats(e + GVS_MOB_OFFSET, 3)
        p = [place[0] + ox * c - oy * s_, place[1] + ox * s_ + oy * c, place[2] + oz]
        wanted = clips.get(k, [])
        actors.append({"id": f"{spec.get('actor_prefix', 'mob')}{k}", "mob_offset": None, "visual": visual,
                       "path": [{"t": 0, "p": [round(v, 4) for v in p], "yaw": round(place_yaw, 5)}],
                       "animations": wanted, "clips_wanted": wanted, "idle": wanted[0] if wanted else None,
                       "actions": [{"t": 0.0, "until": 1e6, "clips": wanted, "loop": False}] if wanted else [],
                       "name": spec.get("names", {}).get(str(k), {})})
    # Le `cameraPlacement` pose le spectateur (l'avatar) : caméra à hauteur d'yeux au-dessus, du côté
    # opposé à son regard (vue à la troisième personne du jeu), regard selon son lacet.
    eye = float(spec.get("eye_height", 2.0))
    back = float(spec.get("camera_back", 0.0))
    direction = [math.cos(cam_yaw), math.sin(cam_yaw), 0.0]
    cam = [round(cam[0] - back * direction[0], 4), round(cam[1] - back * direction[1], 4), round(cam[2] + eye, 4)]
    target = [round(cam[i] + 20 * direction[i], 4) for i in range(3)]
    camera = {"points": [{"t": 0, "p": cam}], "targets": [{"t": 0, "p": target}], "duration": float(spec.get("duration", 0))}
    moves_action = find_action(db, script, "CameraMovesAction") if script is not None else None
    if moves_action is not None:
        # Caméra animée du script : poses datées, visée à 20 m selon lacet et tangage (même
        # convention que le `cameraPlacement`).
        points, targets = [], []
        for key in camera_moves(db, moves_action):
            cp, sp = math.cos(key["pitch"]), math.sin(key["pitch"])
            yaw = key["yaw"] + float(spec.get("yaw_offset", 0.0))
            d = [math.cos(yaw) * cp, math.sin(yaw) * cp, sp]
            points.append({"t": key["t"], "p": key["p"]})
            targets.append({"t": key["t"], "p": [round(key["p"][i] + 20 * d[i], 4) for i in range(3)]})
        if points:
            if points[0]["t"] > 0:
                points.insert(0, {"t": 0, "p": points[0]["p"]})
                targets.insert(0, {"t": 0, "p": targets[0]["p"]})
            camera = {"points": points, "targets": targets, "duration": float(spec.get("duration", 0))}
    report.append(f"{spec['id']} : GameViewScene {spec['scene']} sur {map_name}, {len(actors)} PNJ, "
                  f"{sum(1 for a in actors if a['animations'])} animés")
    return {"map": map_name, "camera": camera, "lines": [], "actors": actors, "weather": None,
            "sounds": {"music": [], "ambience": []}, "post": spec.get("post", []),
            "decor_center": [cam[0], cam[1]], "timing": "client", "duration_from_clips": not spec.get("duration"),
            "sources": {"scene": spec["scene"], "script": spec.get("script")}}


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
        if anchor is None and not spec.get("fr_anchor") and texts.fr is not None and cl.text_index is not None and cl.voice:
            # Ancrage par une réplique doublée : sa voix donne son indice FR, le décalage vaut pour les
            # répliques non doublées voisines (vérifié par la durée d'affichage).
            texts.load_fr_voices()
            if cl.voice in texts.fr_voice:
                anchor = cl.text_index - texts.fr_voice[cl.voice][0]
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
                     ("pointLight", "PointLightColor"), ("selfIllum", "SelfIllumColor"), ("specular", "SpecularColor"),
                     ("waterSpecular", "SpecularWaterColor"), ("waterGradientStart", "WaterGradientStart"),
                     ("waterGradientEnd", "WaterGradientEnd")):
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
    if not light and spec.get("zone_lights"):
        # Base de carte sans éclairage propre : la `ZoneLights` de `pack.bin` que le manifeste désigne
        # (reconnue à ses couleurs, égales à celles de la zone de la carte dans l'arbre 7.0).
        off = pack_offset(mp, spec["zone_lights"])
        light = read_zone_light(mp, off) if off is not None else {}
        if not light:
            report.append(f"{spec['id']} : ZoneLights {spec['zone_lights']} illisible")
    if spec.get("sky") is not None:
        # Ciel désigné par le manifeste (`SkyMesh` de `pack.bin`) : celui de la zone dans l'arbre 7.0,
        # quand le 17.0 ne relie plus le lieu à un éclairage (pont du navire de l'Empire).
        off = pack_offset(mp, spec["sky"])
        if off is not None and mp.vtype(off) == "SkyMesh":
            light = {**light, "sky": off, "skyGeometry": None}
        else:
            report.append(f"{spec['id']} : SkyMesh {spec['sky']} introuvable")
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
    areas = [scene_area(s, plans[s["id"]]) for s in specs]
    extras = [{**w, "only": s["id"]} for s in specs for w in plans[s["id"]].get("decor_windows", []) if "show" in w]
    from tools import cutscene_xdb70 as x70
    doors = x70.map_doors(root, map_name) if root is not None and (Path(root) / "Maps" / map_name).is_dir() else []
    cutout = all(s.get("decor_cutout", True) for s in specs)
    decor = build_decor(mp, cat, bins, textures, particles, map_name, areas, report, extras, doors, cutout)
    (map_dir / "decor.glb").write_bytes(decor["glb"])
    terrain_glb, ground = build_terrain(mp, cat, bins, textures, areas, report, map_dir / "terrain-light.png")
    decor["terrain"] = terrain_glb is not None
    if terrain_glb:
        (map_dir / "terrain.glb").write_bytes(terrain_glb)
        decor["solids"] = np.concatenate([decor["solids"], ground]) if len(decor["solids"]) else ground
    else:
        (map_dir / "terrain.glb").unlink(missing_ok=True)
    prefix = map_prefix(map_name) + "textures/"
    lights, fx, sky = {}, {}, {}
    for spec in specs:
        out = out_root / "engine" / spec["id"]
        out.mkdir(parents=True, exist_ok=True)
        lights[spec["id"]] = light = scene_light(spec, plans[spec["id"]], mp, cat, root, report)
        sky_glb, sky_meta = build_sky(mp, cat, bins, textures, light, prefix, report)
        sky[spec["id"]] = (sky_glb, sky_meta)
        (out / "sky.glb").write_bytes(sky_glb) if sky_glb else (out / "sky.glb").unlink(missing_ok=True)
        fx_glb, fx_objects, fx_sounds, spawns = build_fx(spec.get("spawns", []) + plans[spec["id"]].get("spawns", []), mp, cat,
                                                         bins, textures, particles, report, texture_prefix=prefix)
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
    packs = packs_path(client / "data" / "Packs")
    bins = BinSource([], [str(packs / "*.pak")])
    texts = Texts(manifest, report)
    anim_names = animation_names(db)
    lines17 = ClientLines(db, texts)
    rtexts = ResourceTexts(db, texts)
    root = Path(server_root or manifest.get("server_root") or "/mnt/f/ALLODS ONLINE SERVER/Allods 7.0/game/data")
    index = sound_index(bins, Path(os.environ.get("ALLODEX_CACHE") or Path.home() / ".cache" / "allodex"))
    entries = []
    pack_cat = open_catalog(db, client)
    # Plans de toutes les scènes : le décor d'une carte est commun à toutes celles qui s'y jouent,
    # il couvre donc leurs zones à toutes, même quand une seule est réextraite (`--only`).
    plans: dict[str, dict] = {}
    # Une scène sans chapitre dans le film (en attente) ne s'extrait que demandée (`--only`).
    chapters = {c["id"] for c in manifest["cinematics"]}
    selected = [s for s in manifest["engine_scenes"] if (s["id"] in only if only else s["id"] in chapters)]
    for spec in manifest["engine_scenes"]:
        source = spec.get("source")
        try:
            plans[spec["id"]] = plan_xdb70(spec, root, db, pack_cat, texts, lines17, anim_names, report, rtexts) \
                if source == "xdb70" \
                else plan_gameview(spec, db, texts, anim_names, report) if source == "gameview" \
                else plan_manual(spec, db, texts, lines17, anim_names, report)
        except (AttributeError, KeyError, ValueError) as err:
            # Scène non demandée (`--only`) dont le plan ne se lit plus (ressource du client déplacée par
            # une mise à jour) : elle ne bloque pas les autres, mais ne contribue pas au décor commun
            # de sa carte (signalé).
            if spec in selected:
                raise
            report.append(f"{spec['id']} : plan illisible, scène ignorée, décor de sa carte sans ses zones "
                          f"({type(err).__name__}: {err})")
    wanted_maps = {plans[s["id"]]["map"] for s in selected}
    maps: dict[str, dict] = {}
    for map_name in sorted(wanted_maps):
        on_map = [s for s in manifest["engine_scenes"] if s["id"] in plans and plans[s["id"]]["map"] == map_name
                  and (s["id"] in chapters or s in selected)]
        maps[map_name] = build_map(map_name, on_map, plans, db, client, bins, root, out_root, report)
    # Acteurs communs : un modèle par PNJ (et par jeu d'animations réuni sur toutes les scènes du
    # film), dans `engine/shared/actors/`, textures dans `engine/shared/textures/`.
    shared = out_root / "engine" / "shared"
    shared_tex = TexturePool(db, pack_cat, bins, shared, jpeg=True)
    clips_of: dict[int, set[str]] = {}
    for s_id in {s["id"] for s in manifest["engine_scenes"] if s["id"] in chapters} | {s["id"] for s in selected}:
        for actor in plans.get(s_id, {}).get("actors", []):
            clips_of.setdefault(actor_model_key(actor), set()).update(
                set(actor.get("animations", [])) | {actor.get("idle") or "Idle", "Idle01", "Idle"} |
                set(actor.get("clips_wanted", [])) | ({actor["move"]} if actor.get("move") else set()) |
                # modèle sans marche (le Спрутоглав) : sa course, voir `move_clip`
                ({"Run"} if actor.get("move") == "Walk" else set()))
    built: dict = {}
    for spec in selected:
        plan = plans[spec["id"]]
        ctx = maps[plan["map"]]
        mp, cat, prefix = ctx["mp"], ctx["cat"], map_prefix(plan["map"])
        out = out_root / "engine" / spec["id"]
        out.mkdir(parents=True, exist_ok=True)
        for stale in ("textures", "particles", "decor.glb", "actors"):   # dossiers de la carte et communs
            path = out / stale
            shutil.rmtree(path, ignore_errors=True) if path.is_dir() else path.unlink(missing_ok=True)
        textures = shared_tex
        light = ctx["lights"][spec["id"]]
        camera = plan["camera"]
        camera["fov"] = spec.get("fov", 45)
        decor = ctx["decor"]
        center, radius = scene_area(spec, plan)
        doors = ({k: v == "open" for k, v in spec.get("doors", {}).items() if not k.startswith("_")},
                 plan.get("doors", []))
        instances, light_blob = light_decor(decor, light, center, radius, {"id": spec["id"], **plan}, doors)
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
        for line, meta in zip(plan["lines"], voice_meta):
            if line.get("bubble") and meta:
                line["duration"] = meta["duration"]      # bulle doublée : le temps de sa voix
        if plan.get("duration_from_voices"):
            camera["duration"] = round(max([camera["duration"]] + [l["start"] + (m["duration"] if m else 0.0)
                                                                   for l, m in zip(plan["lines"], voice_meta)]), 3)

        actors_meta = []
        shutil.rmtree(out / "actors", ignore_errors=True)
        for actor in plan["actors"]:
            key = actor_file_key(actor)
            spec_actor = {"id": actor["id"], "file": key, "mob": None, "sex": actor.get("sex"),
                          "animations": sorted(clips_of[actor_model_key(actor)])}
            glb = f"../shared/actors/{key}.glb"
            if key in built:            # PNJ déjà exporté (double, ou autre scène du même passage)
                meta = json.loads(json.dumps(built[key]))
            else:
                spec_actor["visual"] = actor.get("visual")
                spec_actor["vot"] = actor.get("vot")
                data, meta = build_actor_offset(spec_actor, actor["mob_offset"], db, pack_cat, bins, shared_tex, report)
                (shared / "actors").mkdir(parents=True, exist_ok=True)
                (shared / "actors" / f"{key}.glb").write_bytes(data)
                built[key] = json.loads(json.dumps(meta))
            idle = actor.get("idle") or next((c for c in ("Idle01", "Idle") if c in meta["animations"]), None)
            move = move_clip(actor.get("move"), meta["animations"])
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
            visual_scale = meta.pop("visual_scale", 1.0)
            name = {"ru": clean_text(texts.main.texts["ru"][name_idx]), "en": clean_text(texts.main.texts["en"][name_idx])} \
                if name_idx is not None else actor.get("name", {})
            actors_meta.append({"id": actor["id"], "glb": glb,
                                "name": name,
                                "path": path, "scale": round(actor.get("scale", 1.0) * visual_scale, 4), "idle": idle,
                                "talk": actor.get("talk"), "move": move, "appear": actor.get("appear", 0.0),
                                **({"presence": actor["presence"]} if actor.get("presence") else {}),
                                **({"actions": sorted(actor["actions"], key=lambda a: a["t"])} if actor.get("actions") else {}),
                                "light": light_at(path[0]["p"], decor["pointLights"], light), **meta})

        if plan.get("duration_from_clips"):
            # Scène du client : elle dure le temps de la plus longue animation jouée.
            camera["duration"] = round(max([sum(a["animations"].get(c, 0) for c in (act["clips"] if act else []))
                                            for a in actors_meta for act in (a.get("actions") or [None])] + [1.0]), 3)
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
        # Une seule musique à la fois : le jeu joue celle de la zone où se tient le joueur (canal
        # `Music`, qu'une action `Music` du déroulé remplace). Les musiques de zone de la carte
        # (`map_sounds`) ne se superposent donc jamais : la première est gardée, faute de zone connue.
        music = list(dict.fromkeys(audio.get("music", [])))
        if len(music) > 1:
            report.append(f"{spec['id']} : {len(music)} musiques de zone sur la carte ({', '.join(music)}), "
                          f"une seule jouée ({music[0]}) ; préciser `audio.music` au manifeste")
        audio["music"] = music[:1]
        wanted =set(decor["sounds"]) | set(fx_sounds) | set(audio.get("music", [])) | set(audio.get("ambience", [])) | \
            {s["event"] for key in ("music", "ambience", "sfx") for s in timed.get(key, [])}
        waves = export_waves(wanted, bins, out, vgmstream, report, camera["duration"] + 1,
                             spec.get("audio_layers")) if voices or not (out / "scene.json").is_file() else \
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
                      "skyGlb": "sky.glb" if sky_glb else None,
                      "terrainGlb": prefix + "terrain.glb" if decor.get("terrain") else None,
                      # Décor opaque d'une seule face, comme le jeu : vérifié sur `ferris-locus-fall`, dont
                      # la caméra d'ouverture, sous la plateforme du Locus, montre alors le Cœur au-dessus.
                      "oneSided": True},
            "fx": {"glb": "fx.glb" if fx_glb else None, "spawns": spawns},
            "objects": objects, "particleAtlas": atlas,
            "light": {**zone, "sunDirection": [round(float(v), 4) for v in sun_direction(light)]},
            "pointLights": decor["pointLights"],
            "sounds": {"music": loops("music"), "ambience": loops("ambience"),
                       # Sons ponctuels du déroulé (`ClientData` : `Sound2DAction`), joués une fois.
                       "sfx": [{"file": waves[s["event"]]["file"], "t": s["t"],
                                "until": round(s["t"] + waves[s["event"]]["duration"], 3)}
                               for s in timed.get("sfx", []) if s["event"] in waves],
                       "events": audio, "waves": waves, "volume": spec.get("mix", {})},
            "post": plan["post"], "sources": plan["sources"],
            # Secousses de caméra (`ShakeAction`) : décalages `keys` (m, repère de la caméra) à `fps`.
            **({"shakes": [{k: v for k, v in s.items() if not k.startswith("_")} for s in plan["shakes"]]}
               if plan.get("shakes") else {}),
        }
        (out / "scene.json").write_text(json.dumps(scene, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        report.append(f"{spec['id']} : {len(instances)} objets du décor de {plan['map']}, textures des acteurs "
                      f"{textures.bytes_written / 1e6:.1f} Mo, {len(actors_meta)} acteurs, {len(spawns)} effets, "
                      f"{len(waves)} sons, {len(scene_lines)} répliques, {camera['duration']:.0f} s")
        entries.append({"spec": spec, "duration": camera["duration"], "tracks": tracks, "lines": len(scene_lines),
                        "timing": plan["timing"]})
    update_index(manifest, out_root, entries)
    prune_shared_actors(out_root / "engine")
    return report


def prune_shared_actors(engine: Path) -> None:
    """Retire les modèles communs qu'aucune scène ne cite plus."""
    used = set()
    for scene in engine.glob("*/scene.json"):
        for actor in json.loads(scene.read_text(encoding="utf-8")).get("actors", []):
            used.add(Path(actor["glb"]).name)
    images = set()
    for glb in (engine / "shared" / "actors").glob("*.glb"):
        if glb.name not in used:
            glb.unlink()
            continue
        raw = glb.read_bytes()
        size = struct.unpack_from("<I", raw, 12)[0]
        for image in json.loads(raw[20:20 + size]).get("images", []):
            if "uri" in image:
                images.add(Path(image["uri"]).name)
    for texture in (engine / "shared" / "textures").glob("*"):
        if texture.name not in images:
            texture.unlink()


def update_index(manifest: dict, out_root: Path, entries: list[dict]) -> None:
    """Ajoute (ou remplace) les chapitres moteur dans `cinematics.json`, à leur place chronologique."""
    path = out_root / "cinematics.json"
    index = json.loads(path.read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in manifest["cinematics"]}
    # Chapitres moteur retirés du film (scène en attente) : ôtés de l'index.
    index["cinematics"] = [c for c in index["cinematics"] if not (c.get("engine") and c["id"] not in by_id)]
    for e in entries:
        spec = by_id.get(e["spec"]["id"])
        if spec is None:
            continue
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
