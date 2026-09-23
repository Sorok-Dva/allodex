#!/usr/bin/env python3
"""Cinématiques moteur des quêtes recréées en 3D (pilote : `AO12_Prologue04`, la Citadelle de Nihaz).

Le jeu ne livre pas ces scènes en vidéo : il les joue en temps réel. Ce script en rassemble les
éléments dans le **dernier client (17.0)** et les exporte pour le lecteur three.js du site
(`src/components/scene/EngineCutscene`) :

* **caméra** — `CameraTrackAction` du buff de la cinématique (`BuffResource` → `BuffVisScripts`) :
  points de caméra et de visée, chacun avec sa durée (voir `camera_keys`) ;
* **répliques** — `ClientData` de la scène : sous-titre `UISubtitleShow` (indice du texte dans
  `pack.rus.loc` / `pack.eng_eu.loc`, durée d'affichage), voix (événement FMOD `Cutscenes/…`),
  animation du locuteur (`emoteSpeech`…) ; texte français du client FR 16.0 (même méthode que
  `tools/extract_cinematics.py`) ; voix russes extraites des banques `SFX/Voice/*.bsb` de
  `BaseLocall_x64.pak` (sous-piste nommée comme la fin de l'événement) ;
* **décor** — base de la carte `Bin/Maps_<carte>.bin` : régions (`MapRegion`), objets posés
  (`StaticObject` → `VisObjectTemplate` → `Geometry`, composants accrochés), éclairage de zone
  (`ZoneLights`) ; géométries et textures lues dans les paks ;
* **acteurs** — `MobWorld` (nom) → `VisualMob` → `VisCharacterTemplate` → `VisObjectTemplate` :
  géométrie, squelette et animations du modèle.

Ce que le client **ne contient pas** (le serveur le décide) et que le manifeste fournit, justifié :
la position des acteurs et l'instant de départ de chaque réplique (voir `engine_scenes` dans
`tools/cinematics_manifest.json` et le README, § « Cinématiques moteur »).

Sorties : `public/game/cinematics/engine/<id>/` — `decor.glb`, `actors/<acteur>.glb`,
`textures/*`, `voice/<n>.{ogg,mp3}`, `{fr,en,ru}.vtt`, `scene.json` — et l'entrée du chapitre
dans `public/game/cinematics/cinematics.json`.

Usage : python3 tools/extract_engine_cutscene.py [--only ao12-prologue04] [--no-voices]
"""
from __future__ import annotations

import argparse
import os
import io
import json
import math
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import extract_menu_scene as _ems  # noqa: E402
from tools.allods_bins17 import Base, PakFiles, Ref, open_map, open_pack  # noqa: E402
from tools.allods_vis17 import (  # noqa: E402
    VisualItem, dressed_items, GeometryInfo, animation_names, buff_camera_track, read_client_line, read_geometry, read_regions,
    read_texture, read_visobject, static_visobject, visual_character, mob_name_index, mob_visual,
)
from tools.extract_cinematics import (  # noqa: E402
    LANG_LABELS, LANGS, TextSet, build_cues, clean_text, has_cyrillic, load_textset, to_vtt, unpack_loc, Line,
)
from tools.extract_menu_scene import (  # noqa: E402
    BLOCK_BYTES, FOURCC, GltfBuilder, Skeleton, SkeletalAnimation, decode_vertex_buffer,
    parse_skeletal_animation, parse_skeleton, read_chunks, rest_local, rest_world_matrices, skin_attributes,
    validate_glb,
)
from tools.scenes.v5_0 import restore_fixed_rotations  # noqa: E402
from tools.scenes.v8_0 import restore_static_binds  # noqa: E402
from tools.uitexture import build_dds  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE / "cinematics_manifest.json"
DEFAULT_OUT = HERE.parent / "public" / "game" / "cinematics"
DEFAULT_CLIENT = Path("/mnt/h/MyGames/AllodsRU")
# vgmstream du dépôt voisin `allods-texts-packer` (cherché en remontant : les worktrees sont plus profonds).
DEFAULT_VGMSTREAM = next((p / "allods-texts-packer" / "voices" / "tools" / "vgmstream" / "vgmstream-cli"
                          for p in HERE.parents if (p / "allods-texts-packer").is_dir()), Path("vgmstream-cli"))

# Côté maximal des textures exportées : 512 pour le décor (vu de 40 à 70 m dans le pilote), 1024
# pour les acteurs. Écart assumé pour le poids du site (les sources montent à 2048).
DECOR_TEXTURE_MAX = 512
ACTOR_TEXTURE_MAX = 1024
# Clés d'animation redondantes retirées (même tolérance que les fatalités).
TRANSLATION_TOLERANCE = 1e-3
ROTATION_TOLERANCE = 2e-4
MAX_KEY_GAP = 48

# Axe avant des modèles (personnages et créatures) dans leur repère : −Y (la queue du dragon et la
# traîne de Klavdia s'étendent vers +Y ; vérifié sur les captures du pilote). Lacet pour regarder
# un point : atan2(dy, dx) + π/2.
MODEL_FORWARD = -math.pi / 2
VERTEX_LIGHT_MODEL = os.environ.get("ALLODEX_VERTEX_LIGHT", "point")

_ems.COMPONENT.setdefault("i16", 5122)
_ems.COMPONENT_BYTES.setdefault(5122, 2)


# --- textures ----------------------------------------------------------------------------------

def _slug(name: str) -> str:
    stem = re.sub(r"\.\(Texture\)\.(hi\.)?bin$", "", name)
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", stem.split("/")[-1])


class TexturePool:
    """Textures du client décodées une fois, écrites dans `textures/` (PNG si alpha, sinon JPEG)."""

    def __init__(self, files: PakFiles, out_dir: Path) -> None:
        self.files = files
        self.dir = out_dir / "textures"
        self.done: dict[tuple[str, int], str | None] = {}
        self.has_alpha: dict[str, bool] = {}
        self.custom: dict[str, Image.Image] = {}
        self.bytes_written = 0

    def image(self, ref: Ref | None, name: str, max_size: int) -> Image.Image | None:
        info = read_texture(ref) if ref is not None else None
        if info is None:
            return None
        mips: dict[int, bytes] = {}
        for binary in (info.binary, info.binary_hi):
            data = self.files.get(binary) if binary else None
            if data:
                try:
                    mips.update(read_chunks(data))
                except zlib.error:
                    pass
        fmt = info.fmt
        if (fmt not in FOURCC and fmt != "RGBA") or not info.width or not info.height:
            return None
        for level in sorted(mips):
            w, h = max(1, info.width >> level), max(1, info.height >> level)
            if max(w, h) > max_size and level < max(mips):
                continue
            payload = mips[level]
            if fmt == "RGBA":
                if len(payload) < w * h * 4:
                    continue
                bgra = np.frombuffer(payload[:w * h * 4], np.uint8).reshape(h, w, 4)
                return Image.fromarray(bgra[:, :, [2, 1, 0, 3]].copy(), "RGBA")
            need = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * BLOCK_BYTES[fmt]
            if len(payload) < need:
                continue
            img = Image.open(io.BytesIO(build_dds(w, h, FOURCC[fmt], payload[:need])))
            img.load()
            return img.convert("RGBA")
        return None

    def put(self, name: str, img: Image.Image) -> None:
        """Image composée par l'export (atlas de peau habillée), servie sous le nom `name`."""
        self.custom[name] = img

    def uri(self, ref: Ref | None, name: str | None, max_size: int, prefix: str) -> str | None:
        if not name:
            return None
        key = (name, max_size)
        if key not in self.done:
            img = self.custom[name] if name in self.custom else self.image(ref, name, max_size)
            if img is not None and max(img.size) > max_size:
                img = img.resize((max(1, img.width * max_size // max(img.size)), max(1, img.height * max_size // max(img.size))),
                                 Image.LANCZOS)
            if img is None:
                self.done[key] = None
            else:
                self.dir.mkdir(parents=True, exist_ok=True)
                alpha = img.getextrema()[3][0] < 255
                self.has_alpha[name] = alpha
                file = f"{_slug(name)}{'' if max_size >= 1024 else f'@{max_size}'}.{'png' if alpha else 'jpg'}"
                path = self.dir / file
                if alpha:
                    img.save(path, format="PNG", optimize=True)
                else:
                    img.convert("RGB").save(path, format="JPEG", quality=88, optimize=True)
                self.bytes_written += path.stat().st_size
                self.done[key] = file
        file = self.done[key]
        return None if file is None else prefix + file


# --- géométries --------------------------------------------------------------------------------

@dataclass
class Loaded:
    geo: GeometryInfo
    vertices: dict[str, np.ndarray]
    indices: np.ndarray
    skeleton: Skeleton | None


def load_geometry(files: PakFiles, ref: Ref) -> Loaded | None:
    geo = read_geometry(ref)
    data = files.get(geo.binary) if geo.binary else None
    if data is None or not geo.doc.layouts:
        return None
    chunks = read_chunks(data)
    vb, ib = chunks.get(0), chunks.get(1)
    layout = geo.doc.layouts[0]
    if vb is None or ib is None or layout.stride <= 0 or len(vb) < layout.stride:
        return None
    vertices = decode_vertex_buffer(vb, layout, len(vb) // layout.stride)
    indices = np.frombuffer(ib, "<u2").astype(np.uint32)
    skeleton = None
    if geo.doc.skeleton_id is not None and geo.doc.skeleton_id in chunks:
        try:
            skeleton = parse_skeleton(chunks[geo.doc.skeleton_id])
        except (struct.error, ValueError, IndexError):
            skeleton = None
    return Loaded(geo, vertices, indices, skeleton)


def load_animation(files: PakFiles, name: str | None, skeleton: Skeleton, span: float) -> SkeletalAnimation | None:
    data = files.get(name) if name else None
    if not data:
        return None
    payload = read_chunks(data).get(0)
    if not payload:
        return None
    try:
        return parse_skeletal_animation(payload, skeleton, span)
    except (struct.error, ValueError, IndexError):
        return None


def bind_pose_positions(vertices: dict[str, np.ndarray], skeleton: Skeleton, static: np.ndarray) -> np.ndarray:
    """Sommets skinnés à la pose de bind (règle des fatalités : `Σ w · monde_bind · inverse_native · v`)."""
    world = rest_world_matrices(skeleton, None)
    inverse = np.tile(np.eye(4), (len(skeleton), 1, 1))
    inverse[:, :3, :] = skeleton.inverse.transpose(0, 2, 1)
    palette = world @ inverse
    joints, weights = skin_attributes(vertices, len(skeleton))
    points = np.column_stack((vertices["position"].astype(np.float64), np.ones(len(vertices["position"]))))
    out = np.zeros_like(points)
    for slot in range(4):
        out += np.einsum("nij,nj->ni", palette[joints[:, slot]], points) * (weights[:, slot] / 255.0)[:, None]
    result = out[:, :3].astype(np.float32)
    result[static] = vertices["position"][static].astype(np.float32)
    return result


def reduce_keys(values: np.ndarray, tolerance: float) -> np.ndarray:
    n = len(values)
    if n <= 2:
        return np.arange(n)
    if np.max(np.ptp(values, axis=0)) <= tolerance:
        return np.array([0, n - 1])
    keep = [0]
    anchor = 0
    i = 2
    while i < n:
        span = np.arange(anchor + 1, i)
        w = ((span - anchor) / (i - anchor))[:, None]
        interp = values[anchor] * (1 - w) + values[i] * w
        if i - anchor > MAX_KEY_GAP or np.max(np.abs(interp - values[span])) > tolerance:
            keep.append(i - 1)
            anchor = i - 1
        i += 1
    keep.append(n - 1)
    return np.array(keep)


class Glb:
    """Assemblage glTF (adapté de l'`Exporter` des fatalités) : matériaux, maillages, squelettes, clips."""

    def __init__(self, textures: TexturePool, texture_max: int, uri_prefix: str) -> None:
        self.textures = textures
        self.texture_max = texture_max
        self.prefix = uri_prefix
        self.gltf = GltfBuilder()
        self.gltf.json["asset"]["generator"] = "allodex/extract_engine_cutscene"
        self.images: dict[str, int | None] = {}
        self.materials: dict[tuple, int] = {}
        self.notes: list[str] = []
        self.quantized = False
        self.stats = {"triangles": 0, "meshes": 0, "animations": 0}
        self._shared: dict[tuple, tuple] = {}
        self._indices: dict[tuple, int] = {}

    def texture(self, name: str | None, ref: Ref | None) -> int | None:
        if not name:
            return None
        if name not in self.images:
            uri = self.textures.uri(ref, name, self.texture_max, self.prefix)
            if uri is None:
                self.images[name] = None
                self.notes.append(f"texture illisible : {name}")
            else:
                self.gltf.json["images"].append({"uri": uri, "name": Path(name).name})
                self.gltf.json["textures"].append({"sampler": 0, "source": len(self.gltf.json["images"]) - 1})
                self.images[name] = len(self.gltf.json["textures"]) - 1
        return self.images[name]

    def material(self, element, geo: GeometryInfo, lit: bool) -> int:
        mat = element.material
        additive = mat.blend in ("BLEND_EFFECT_ADD", "BLEND_EFFECT_ALPHA_ADD", "BLEND_EFFECT_COLOR_ADD") and mat.transparent
        tex = self.texture(mat.texture, geo.textures.get(mat.texture or ""))
        key = (tex, additive, mat.transparent, round(mat.alpha, 4), mat.blend, lit)
        if key not in self.materials:
            index = self.gltf.add_material(mat.name, tex, "BLEND" if mat.transparent else "OPAQUE", True, additive, mat.alpha)
            extras = self.gltf.json["materials"][index].setdefault("extras", {})
            extras["gameBlend"] = mat.blend
            if lit and not additive:
                extras["lit"] = True
            if not mat.transparent and self.textures.has_alpha.get(mat.texture or ""):
                extras["cutout"] = True
            self.materials[key] = index
        return self.materials[key]

    def mesh(self, name: str, loaded: Loaded, elements: list | None = None, skinned_export: bool = False,
             lit: bool = True, texture_override: dict[str, tuple[str, Ref | None]] | None = None,
             colors: np.ndarray | None = None) -> int | None:
        """Maillage glTF d'une géométrie. `colors` (RGBA u8 par sommet) : éclairage précalculé d'une
        instance du décor ; les autres accesseurs sont partagés entre instances de la même géométrie."""
        geo, vertices, indices, skeleton = loaded.geo, loaded.vertices, loaded.indices, loaded.skeleton
        cache_key = (id(loaded), skinned_export, lit)
        cached = self._shared.get(cache_key)
        elements = [e for e in geo.doc.elements if e.material.visible] if elements is None else elements
        position = vertices["position"].astype(np.float32)
        static = np.zeros(len(position), bool)
        for e in geo.doc.elements:
            if e.skin_index < 0:
                static[np.unique(indices[e.ib0:e.ib1])] = True
        has_skin = skeleton is not None and "indices" in vertices and "weights" in vertices
        if has_skin:
            position = bind_pose_positions(vertices, skeleton, static)
        uv = vertices.get("texcoord0", np.zeros((len(position), 2), np.float32)).astype(np.float32).copy()
        uv[:, 1] = 1.0 - uv[:, 1]
        if cached is not None:
            attributes = dict(cached[0])
        else:
            attributes = {
                "POSITION": self.gltf.add_accessor(position, "VEC3", "f32", target=34962, minmax=True),
                "TEXCOORD_0": self.gltf.add_accessor(uv, "VEC2", "f32", target=34962),
            }
        color = vertices.get("color")
        if colors is not None and len(colors) == len(position):
            attributes["COLOR_0"] = self.gltf.add_accessor(np.ascontiguousarray(colors, np.uint8), "VEC4", "u8",
                                                           normalized=True, target=34962)
        elif cached is not None:
            pass
        elif color is not None:
            rgb = np.minimum(color[:, :3].astype(np.uint16) * 2, 255).astype(np.uint8)
            rgb[color[:, :3].max(axis=1) == 0] = 255
            attributes["COLOR_0"] = self.gltf.add_accessor(np.concatenate([rgb, color[:, 3:4]], axis=1), "VEC4", "u8",
                                                           normalized=True, target=34962)
        if cached is None and "normal" in vertices:
            normal = vertices["normal"].astype(np.float32)
            norm = np.linalg.norm(normal, axis=1, keepdims=True)
            normal = np.where(norm > 1e-6, normal / np.maximum(norm, 1e-9), np.array([0, 0, 1], np.float32))
            attributes["NORMAL"] = self.gltf.add_accessor(normal.astype(np.float32), "VEC3", "f32", target=34962)
        if cached is None and has_skin and skinned_export:
            joints, weights = skin_attributes(vertices, len(skeleton), static_joint=len(skeleton))
            joints[static] = 0
            joints[static, 0] = len(skeleton)
            weights[static] = 0
            weights[static, 0] = 255
            attributes["JOINTS_0"] = self.gltf.add_accessor(joints, "VEC4", "u8", target=34962)
            attributes["WEIGHTS_0"] = self.gltf.add_accessor(weights, "VEC4", "u8", normalized=True, target=34962)
        primitives = []
        for element in elements:
            tri = indices[element.ib0:element.ib1]
            if tri.size < 3 or int(tri.max()) >= len(position):
                continue
            if texture_override and element.name in texture_override:
                tex_name, tex_ref = texture_override[element.name]
                element.material.texture = tex_name
                geo.textures[tex_name] = tex_ref
            if not element.material.texture:
                continue  # sans texture, le client ne dessine pas l'élément (formes d'émission, emplacements vides)
            self.stats["triangles"] += tri.size // 3
            idx_key = (cache_key, element.ib0, element.ib1)
            if idx_key not in self._indices:
                self._indices[idx_key] = self.gltf.add_accessor(tri.astype(np.uint32), "SCALAR", "u32", target=34963)
            prim = {"attributes": attributes, "mode": 4, "indices": self._indices[idx_key],
                    "material": self.material(element, geo, lit), "extras": {"element": element.name}}
            su, sv = element.material.uv_scroll
            if su or sv:
                prim["extras"]["uvScroll"] = [su, sv]
            primitives.append(prim)
        if cached is None:
            self._shared[cache_key] = ({k: v for k, v in attributes.items() if k != "COLOR_0"},)
        if not primitives:
            return None
        self.gltf.json["meshes"].append({"name": name, "primitives": primitives})
        self.stats["meshes"] += 1
        return len(self.gltf.json["meshes"]) - 1

    def skeleton_nodes(self, skeleton: Skeleton, prefix: str) -> list[int]:
        nodes = []
        for i, name in enumerate(skeleton.names):
            t, q, s = rest_local(skeleton, None, i)
            node = {"name": f"{prefix}/{name}", "translation": [float(v) for v in t], "rotation": [float(v) for v in q]}
            if np.any(np.abs(s - 1.0) > 1e-7):
                node["scale"] = [float(v) for v in s]
            nodes.append(self.gltf.add_node(node))
        for i in range(len(skeleton)):
            p = skeleton.parents[i]
            if 0 <= p < len(skeleton) and p != i:
                self.gltf.json["nodes"][nodes[p]].setdefault("children", []).append(nodes[i])
        return nodes

    def skin(self, name: str, skeleton: Skeleton, joints: list[int], static_node: int) -> int:
        world = rest_world_matrices(skeleton, None)
        inverse = np.zeros((len(skeleton) + 1, 16), np.float32)
        for i in range(len(skeleton)):
            inverse[i] = np.linalg.inv(world[i]).T.reshape(-1)
        inverse[len(skeleton)] = np.eye(4, dtype=np.float32).reshape(-1)
        self.gltf.json["skins"].append({"name": f"{name}_skin", "joints": joints + [static_node],
                                        "inverseBindMatrices": self.gltf.add_accessor(inverse, "MAT4", "f32")})
        return len(self.gltf.json["skins"]) - 1

    def clip(self, name: str, skeleton: Skeleton, nodes: list[int], animation: SkeletalAnimation) -> float:
        obj = SimpleNamespace(skeleton=skeleton, animation=animation)
        restore_static_binds(obj)
        restore_fixed_rotations(obj)
        tracks = [t for t in animation.tracks if t.name in skeleton.names]
        frames = max(animation.frames, 1)
        duration = (frames - 1) / float(animation.fps) if frames > 1 else 0.0
        if not tracks:
            return duration
        times = np.arange(frames, dtype=np.float32) / float(animation.fps) if frames > 1 else np.array([0.0], np.float32)
        cache: dict[bytes, int] = {}
        samplers, channels = [], []

        def channel(node: int, path: str, values: np.ndarray, kind: str) -> None:
            values = np.asarray(values, np.float64)
            if len(values) != len(times):
                values = np.repeat(values[:1], len(times), axis=0)
            keep = reduce_keys(values, ROTATION_TOLERANCE if path == "rotation" else TRANSLATION_TOLERANCE)
            token = keep.tobytes()
            if token not in cache:
                cache[token] = self.gltf.add_accessor(times[keep].astype(np.float32), "SCALAR", "f32", minmax=True)
            if path == "rotation":
                acc = self.gltf.add_accessor(np.round(np.clip(values[keep], -1, 1) * 32767).astype(np.int16), kind, "i16",
                                             normalized=True)
                self.quantized = True
            else:
                acc = self.gltf.add_accessor(values[keep].astype(np.float32), kind, "f32")
            samplers.append({"input": cache[token], "output": acc, "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": node, "path": path}})

        for track in tracks:
            node = nodes[skeleton.names.index(track.name)]
            channel(node, "translation", np.asarray(track.translation), "VEC3")
            channel(node, "rotation", np.asarray(track.rotation), "VEC4")
            scale = np.asarray(track.scale, float)
            if len(scale) == frames and np.ptp(scale) > 1e-7:
                channel(node, "scale", np.repeat(scale[:, None], 3, axis=1), "VEC3")
        self.gltf.json["animations"].append({"name": name, "samplers": samplers, "channels": channels})
        self.stats["animations"] += 1
        return duration

    def finish(self, roots: list[int]) -> bytes:
        self.gltf.json["scenes"][0]["nodes"].extend(roots)
        if self.quantized:
            for key in ("extensionsUsed", "extensionsRequired"):
                used = self.gltf.json.setdefault(key, [])
                if "KHR_mesh_quantization" not in used:
                    used.append("KHR_mesh_quantization")
        glb = self.gltf.to_glb()
        validate_glb(glb)
        return glb


def yaw_quaternion(yaw: float) -> list[float]:
    return [0.0, 0.0, math.sin(yaw / 2), math.cos(yaw / 2)]


# --- décor -------------------------------------------------------------------------------------

def locator_matrix(loaded: Loaded | None, name: str) -> np.ndarray:
    """Transformation d'un locator de la géométrie (position, rotation xyzw, échelle), identité sinon."""
    m = np.eye(4)
    if loaded is None:
        return m
    for loc in loaded.geo.doc.locators:
        if loc.name == name:
            m[:3, :3] = _ems.quat_matrix(np.array(loc.rotation)) * (loc.scale or 1.0)
            m[:3, 3] = loc.position
            break
    return m


def matrix_node(matrix: np.ndarray) -> dict:
    return {"matrix": [float(v) for v in matrix.T.reshape(-1)]}


def read_lightvrt(map_base: Base, files: PakFiles) -> dict[tuple[str, int], np.ndarray]:
    """Éclairage précalculé des objets posés : `<région>_lightvrt.bin` du pak de la carte
    (`<carte>_000_000_512_512.Client.pak`). Blocs `(u32 id, u32 taille)` : bloc 0 = nombre
    d'entrées, bloc 1 = taille par objet, bloc `k + 2` = sommets de l'objet `k` de la région, 4 octets
    par sommet (le nombre de sommets est celui de la géométrie, vérifié sur les 27 objets du pilote)."""
    pak = f"{map_base.name[len('Maps_'):-len('.bin')]}_000_000_512_512.Client.pak"
    out: dict[tuple[str, int], np.ndarray] = {}
    for path in map_base.pb.paths:
        if not path.endswith("_MapRegion.xdb"):
            continue
        data = files.get(path.replace("_MapRegion.xdb", "_lightvrt.bin"), pak)
        if not data:
            continue
        raw = zlib.decompress(data)
        off = 0
        while off + 8 <= len(raw):
            cid, size = struct.unpack_from("<II", raw, off)
            if cid >= 2:
                out[(path, cid - 2)] = np.frombuffer(raw[off + 8:off + 8 + size], np.uint8).reshape(-1, 4)
            off += 8 + size
    return out


def _rgb(argb: int) -> np.ndarray:
    return np.array([(argb >> 16) & 255, (argb >> 8) & 255, argb & 255], np.float64) / 255.0


def vertex_light(raw: np.ndarray, light: dict) -> np.ndarray:
    """Couleur de sommet d'un objet du décor depuis son `lightvrt` (4 octets par sommet).

    Ce qui est établi : un sommet par sommet de la géométrie ; octet 3 toujours nul ; octet 2 sur
    8 bits pleins, fort près des 164 lumières ponctuelles de la carte (portails : 163 en moyenne) et
    faible sur le grand bâtiment (16) ; octets 0 et 1 quantifiés (0, 32, …, 224, 255 et 128, 136, …,
    248, 255). Ce qui ne l'est pas : le shader du client qui les combine. Choix du lecteur, réglable
    par `VERTEX_LIGHT_MODEL` : `point` = ambiante × 2 + octet 2 × couleur d'auto-illumination × 2
    (lumière des feux de la zone), `flat` = ambiante seule (sans précalcul)."""
    amb = _rgb(light.get("ambient", 0)) * 2
    if VERTEX_LIGHT_MODEL == "flat":
        rgb = np.tile(np.clip(amb + 0.5, 0, 1), (len(raw), 1))
    else:
        glow = _rgb(light.get("selfIllum", 0xFFFFFFFF)) * 2
        rgb = np.clip(amb + (raw[:, 2:3] / 255.0) * glow, 0, 1)
    return np.concatenate([np.round(rgb * 255), np.full((len(raw), 1), 255)], axis=1).astype(np.uint8)


def ambient_color(light: dict, raw_mean: np.ndarray | None) -> np.ndarray:
    if raw_mean is not None and raw_mean.ndim == 1:
        return vertex_light(raw_mean[None, :], light)[0]
    rgb = np.clip(_rgb(light.get("ambient", 0)) * 2, 0, 1)
    return np.append(np.round(rgb * 255), 255).astype(np.uint8)


def read_zone_light(map_base: Base) -> dict:
    """Éclairage de zone (`ZoneLights` de la carte, premier éclairage du vecteur en `+0x168`, éléments de
    280 o). Champs rangés par ordre alphabétique de leur nom (recoupé sur `AC5_base` 7.0 ↔ 17.0) :
    +0x24 AmbientColor, +0x28 AmbientFactor, +0x2C ContourColor, +0x30 DiffuseColor, +0x3C FogColor,
    +0x40 FogEnd, +0x44 FogStart, +0x48 PointLightColor, +0x4C SelfIllumColor, +0x54 SpecularColor,
    +0x5C SunLightPitch, +0x60 SunLightYaw ; ciel : `+0x2C0` SkyMesh."""
    zones = map_base.objects("ZoneLights")
    if not zones:
        return {}
    items = zones[0].elements(0x168, 280)
    if not items:
        return {}
    e = items[0]
    return {"ambient": e.u32(0x24), "ambientFactor": round(e.f32(0x28), 4), "diffuse": e.u32(0x30),
            "fog": e.u32(0x3C), "fogEnd": round(e.f32(0x40), 3), "fogStart": round(e.f32(0x44), 3),
            "pointLight": e.u32(0x48), "selfIllum": e.u32(0x4C), "sunPitch": round(e.f32(0x5C), 3),
            "sunYaw": round(e.f32(0x60), 3)}


def build_decor(map_base: Base, files: PakFiles, textures: TexturePool, report: list[str],
                around: tuple[float, float] | None = None, radius: float = 1e9) -> tuple[bytes, dict]:
    light = read_zone_light(map_base)
    glb = Glb(textures, DECOR_TEXTURE_MAX, "textures/")
    meshes: dict[tuple, tuple[int | None, Loaded | None]] = {}
    solids: list[np.ndarray] = []   # triangles opaques en coordonnées monde (pour poser les acteurs)
    samples: list[np.ndarray] = []  # sommets du décor (x, y, z, r, g, b) : lumière locale des acteurs
    roots: list[int] = []
    placed = skipped = 0
    fx_only = 0

    lightvrt = read_lightvrt(map_base, files)

    def mesh_of(vot: Ref, depth: int = 0, raw_light: np.ndarray | None = None) -> tuple[list[dict], Loaded | None]:
        """Nœuds (hors transformation de pose) d'un gabarit : sa géométrie (éclairée par son `lightvrt`
        quand il en a un) + ses composants accrochés (éclairés par la moyenne de leur parent)."""
        vis = read_visobject(vot)
        loaded = None
        children: list[dict] = []
        mean = None
        if vis.geometry is not None:
            key = (vis.geometry.base.name, vis.geometry.off)
            if key not in meshes:
                meshes[key] = (None, load_geometry(files, vis.geometry))
            _, loaded = meshes[key]
            index = None
            if loaded is not None:
                count = len(loaded.vertices["position"])
                if raw_light is not None and len(raw_light) == count:
                    colors = vertex_light(raw_light, light)
                else:
                    colors = np.tile(ambient_color(light, raw_light), (count, 1))
                mean = raw_light if raw_light is not None and raw_light.ndim == 1 else (
                    np.round(raw_light.mean(axis=0)).astype(np.uint8) if raw_light is not None and len(raw_light) else None)
                index = glb.mesh(Path(loaded.geo.binary or "geo").stem, loaded, colors=colors, lit=False)
            if index is not None:
                node = {"mesh": index}
                if abs(vis.scale - 1) > 1e-6 and vis.scale > 0:
                    node["scale"] = [vis.scale] * 3
                children.append(node)
        if depth < 3:
            for comp in vis.components:
                if comp.visobject is None:
                    continue
                sub, _ = mesh_of(comp.visobject, depth + 1, mean)
                if not sub:
                    continue
                m = locator_matrix(loaded, comp.locator)
                local = np.eye(4)
                local[:3, :3] = _ems.quat_matrix(np.array(comp.rotation)) * (comp.scale or 1.0)
                local[:3, 3] = comp.offset
                node = matrix_node(m @ local)
                node["children"] = [glb.gltf.add_node(n) for n in sub]
                node["name"] = f"component:{comp.locator}"
                children.append(node)
        return children, loaded

    for obj in read_regions(map_base):
        x, y, z = obj.position
        if around is not None and math.hypot(x - around[0], y - around[1]) > radius:
            continue
        vot = static_visobject(obj.static_object)
        if vot is None:
            skipped += 1
            continue
        children, _ = mesh_of(vot, 0, lightvrt.get((obj.region, obj.index)))
        if not children:
            fx_only += 1
            continue
        world = np.eye(4)
        world[:3, :3] = _ems.quat_matrix(np.array(yaw_quaternion(obj.yaw))) * (obj.scale if obj.scale > 0 else 1.0)
        world[:3, 3] = (x, y, z)
        loaded = meshes.get((read_visobject(vot).geometry.base.name, read_visobject(vot).geometry.off), (None, None))[1] \
            if read_visobject(vot).geometry is not None else None
        if loaded is not None:
            tris = [loaded.indices[e.ib0:e.ib1] for e in loaded.geo.doc.elements
                    if e.material.visible and not e.material.transparent and e.material.texture]
            if tris:
                idx = np.concatenate(tris)
                idx = idx[: len(idx) // 3 * 3]
                pts = np.column_stack([loaded.vertices["position"].astype(np.float64), np.ones(len(loaded.vertices["position"]))])
                wpts = (pts @ world.T)[:, :3]
                solids.append(wpts[idx].reshape(-1, 3, 3))
                raw = lightvrt.get((obj.region, obj.index))
                if raw is not None and len(raw) == len(wpts):
                    samples.append(np.column_stack([wpts, vertex_light(raw, light)[:, :3] / 255.0])[::3])
        node = {"name": f"{Path(obj.region).stem}#{obj.index}", "translation": [x, y, z],
                "rotation": yaw_quaternion(obj.yaw), "children": [glb.gltf.add_node(n) for n in children]}
        if abs(obj.scale - 1) > 1e-6 and obj.scale > 0:
            node["scale"] = [obj.scale] * 3
        roots.append(glb.gltf.add_node(node))
        placed += 1
    report.append(f"décor : {placed} objets posés, {fx_only} gabarits sans géométrie (particules, sons), "
                  f"{skipped} sans gabarit visuel (collisions)")
    report += glb.notes
    data = glb.finish([glb.gltf.add_node({"name": "decor", "children": roots})])
    return data, {"objects": placed, "stats": glb.stats, "light": light,
                  "samples": np.concatenate(samples) if samples else np.zeros((0, 6)), "solids": np.concatenate(solids) if solids else np.zeros((0, 3, 3))}


def local_light(samples: np.ndarray, position: list[float], radius: float = 12.0) -> list[float] | None:
    """Lumière précalculée moyenne du décor autour d'un acteur (sommets à moins de `radius` m) : le
    lecteur en éclaire l'acteur, que le client éclaire lui-même avec les lumières de la zone."""
    if not len(samples):
        return None
    d = np.hypot(samples[:, 0] - position[0], samples[:, 1] - position[1])
    near = samples[(d < radius) & (np.abs(samples[:, 2] - position[2]) < radius)]
    return [round(float(v), 3) for v in near[:, 3:].mean(axis=0)] if len(near) else None


def ground_z(solids: np.ndarray, x: float, y: float, below: float) -> float | None:
    """Plus haute surface opaque du décor sous le point (x, y), sous l'altitude `below`."""
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


# --- acteurs -----------------------------------------------------------------------------------

def animation_file(files: PakFiles, geometry_binary: str, anim: str) -> str | None:
    """`Creatures/X/X.(Geometry).bin` + `Idle` → `Creatures/X/Animations/X.Idle.(SkeletalAnimation).bin`
    (sans égard à la casse)."""
    folder, stem = geometry_binary.rsplit("/", 1)
    stem = stem.split(".(")[0]
    want = f"{folder}/Animations/{stem}.{anim}.(SkeletalAnimation).bin".lower()
    for name in files.index():
        if name.lower() == want:
            return name
    return None


def _variant_family(name: str) -> str | None:
    m = re.match(r"^([a-z]+)_(\d+|special)$", name)
    return m.group(1) if m else None


def dress_character(actor_id: str, loaded: Loaded, default: VisualItem, variations: list[VisualItem],
                    dress: list[VisualItem], sex: str, textures: TexturePool, files: PakFiles,
                    report: list[str]) -> tuple[list, dict, list]:
    """Habille un personnage joueur/PNJ comme le client : géosets (tenue par défaut, variations de
    visage et de coiffure, objets portés), géosets cachés, objets accrochés aux locators, et atlas
    de peau composé des patchs de texture des objets (rectangles UV, V = 0 en bas)."""
    items = [default] + variations + dress
    hidden: set[str] = set()
    shown: dict[str, Ref | None] = {}
    attachments: list[tuple[str, Ref, str | None]] = []
    for item in items:
        hidden.update(item.hidden)
        for shape in item.shapes:
            if shape.scene is not None and shape.locator:
                # la géométrie accrochée porte souvent les deux côtés (éléments « L » et « R ») : le
                # nom de la forme choisit l'élément dessiné
                attachments.append((shape.locator, shape.scene, shape.name))
            elif shape.name:
                shown[shape.name] = shape.texture
    chosen_families = {_variant_family(n) for n in shown} - {None}
    elements, override = [], {}
    for e in loaded.geo.doc.elements:
        if e.name in shown:
            if shown[e.name] is not None:
                override[e.name] = (shown[e.name].binary(), shown[e.name])
        elif e.name in hidden or not e.material.visible:
            continue
        elif _variant_family(e.name) in chosen_families:
            continue
        if not (e.material.texture or e.name in override):
            continue
        elements.append(e)
    # atlas : texture de peau des géosets du corps, patchs dessinés dans l'ordre sous-vêtements,
    # variations, puis objets portés
    skin_name = next((e.material.texture for e in elements if e.name.startswith(("torso_", "body_", "legs_"))
                      and e.material.texture), None)
    if skin_name:
        base = textures.image(loaded.geo.textures.get(skin_name), skin_name, 2048)
        if base is not None:
            atlas = base.copy()
            w, h = atlas.size
            order = [i for i in dress if any("Underwear" in (p[4].binary() or "") for ps in i.patches.values()
                                             for p in ps if p[4] is not None)]
            order = order + variations + [i for i in dress if i not in order]
            painted = 0
            for item in order:
                for key in ("unisex", sex):
                    for x1, x2, y1, y2, tex in item.patches.get(key, []):
                        if tex is None or x2 <= x1 or y2 <= y1:
                            continue
                        img = textures.image(tex, tex.binary() or "", 2048)
                        if img is None:
                            continue
                        box = (round(x1 * w), round((1 - y2) * h), round(x2 * w), round((1 - y1) * h))
                        patch = img.resize((box[2] - box[0], box[3] - box[1]), Image.LANCZOS)
                        atlas.alpha_composite(patch, (box[0], box[1]))
                        painted += 1
            name = f"actors/{actor_id}_skin.(Texture).bin"
            textures.put(name, atlas)
            for e in elements:
                if e.material.texture == skin_name and e.name not in override:
                    override[e.name] = (name, None)
            report.append(f"{actor_id} : {len(elements)} géosets, {painted} patchs de texture, {len(attachments)} objets accrochés")
    return elements, override, attachments


def build_actor(actor: dict, pack: Base, files: PakFiles, textures: TexturePool, report: list[str]) -> tuple[bytes, dict]:
    mob = find_mob(pack, actor)
    visual = mob_visual(mob)
    character = visual_character(visual) if visual is not None else None
    if character is None or character.visobject is None:
        raise ValueError(f"{actor['id']} : gabarit visuel introuvable")
    vis = read_visobject(character.visobject)
    loaded = load_geometry(files, vis.geometry) if vis.geometry is not None else None
    if loaded is None or loaded.skeleton is None:
        raise ValueError(f"{actor['id']} : géométrie ou squelette illisible")
    glb = Glb(textures, ACTOR_TEXTURE_MAX, "../textures/")
    override: dict[str, tuple[str, Ref | None]] = {}
    attachments: list[tuple[str, Ref, str | None]] = []
    default, variations, dress = dressed_items(visual)
    if default is not None:
        elements, override, attachments = dress_character(actor["id"], loaded, default, variations, dress,
                                                          actor.get("sex", "female"), textures, files, report)
    else:
        elements = [e for e in loaded.geo.doc.elements if e.material.visible]
    mesh = glb.mesh(actor["id"], loaded, elements, skinned_export=True, lit=True, texture_override=override)
    skeleton = loaded.skeleton
    joints = glb.skeleton_nodes(skeleton, actor["id"])
    for locator, vot, shape_name in attachments:
        if locator not in skeleton.names:
            report.append(f"{actor['id']} : locator absent du squelette {locator}")
            continue
        vis_att = read_visobject(vot)
        att = load_geometry(files, vis_att.geometry) if vis_att.geometry is not None else None
        chosen = None
        if att is not None and any(e.name == shape_name for e in att.geo.doc.elements):
            chosen = [e for e in att.geo.doc.elements if e.name == shape_name]
        index = glb.mesh(f"{actor['id']}:{locator}", att, chosen, lit=True) if att else None
        if index is not None:
            node = glb.gltf.add_node({"name": f"attach:{locator}", "mesh": index})
            glb.gltf.json["nodes"][joints[skeleton.names.index(locator)]].setdefault("children", []).append(node)
    static_node = glb.gltf.add_node({"name": f"{actor['id']}/Static"})
    mesh_node = {"name": f"{actor['id']}_mesh", "mesh": mesh, "skin": glb.skin(actor["id"], skeleton, joints, static_node)}
    roots = [joints[i] for i in range(len(skeleton)) if not (0 <= skeleton.parents[i] < len(skeleton))]
    span = float(np.max(np.abs(loaded.vertices["position"])) * 4.0)
    durations = {}
    for anim in actor.get("animations", ["Idle"]):
        file = animation_file(files, loaded.geo.binary, anim)
        animation = load_animation(files, file, skeleton, span)
        if animation is None:
            report.append(f"{actor['id']} : animation absente {anim}")
            continue
        durations[anim] = round(glb.clip(anim, skeleton, joints, animation), 4)
    scale = (vis.scale if vis.scale > 0 else 1.0)
    root = glb.gltf.add_node({"name": actor["id"], "children": roots + [static_node, glb.gltf.add_node(mesh_node)],
                              **({"scale": [scale] * 3} if abs(scale - 1) > 1e-6 else {})})
    report += [f"{actor['id']} : {n}" for n in glb.notes]
    height = float(loaded.vertices["position"][:, 2].max() * scale)
    meta = {"geometry": loaded.geo.binary, "template_scale": round(character.scale, 4), "visobject_scale": round(scale, 4),
            "height": round(height, 3), "animations": durations, "stats": glb.stats}
    return glb.finish([root]), meta


def find_mob(pack: Base, actor: dict) -> Ref:
    """`MobWorld` d'un acteur : identifiant de ressource (`mob`) du manifeste."""
    off = pack.pb.ids.get(int(actor["mob"]))
    if off is None:
        raise ValueError(f"{actor['id']} : MobWorld {actor['mob']} introuvable")
    return Ref(pack, off)


# --- voix --------------------------------------------------------------------------------------

def fsb_stream_names(vgmstream: Path, fsb: Path) -> list[str]:
    out = subprocess.run([str(vgmstream), "-m", str(fsb)], capture_output=True, text=True).stdout
    count = int(re.search(r"stream count: (\d+)", out).group(1))
    names = []
    for s in range(1, count + 1):
        info = subprocess.run([str(vgmstream), "-m", "-s", str(s), str(fsb)], capture_output=True, text=True).stdout
        m = re.search(r"stream name: (.+)", info)
        names.append(m.group(1).strip() if m else "")
    return names


def export_voices(events: list[str], bank: str, files: PakFiles, out_dir: Path, vgmstream: Path,
                  report: list[str]) -> list[dict | None]:
    data = files.get(bank)
    if data is None:
        report.append(f"banque vocale introuvable : {bank}")
        return [None] * len(events)
    if bank.endswith(".bsb"):
        data = zlib.decompress(data)
    fsb_at = data.find(b"FSB5")
    out_dir.mkdir(parents=True, exist_ok=True)
    result: list[dict | None] = []
    with tempfile.TemporaryDirectory(prefix="allodex-voice-") as tmp:
        fsb = Path(tmp) / "bank.fsb"
        fsb.write_bytes(data[fsb_at:])
        names = fsb_stream_names(vgmstream, fsb)
        for n, event in enumerate(events, 1):
            tail = event.split("/")[-1]
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
            result.append({"event": event, "ogg": f"voice/{n:02d}.ogg", "mp3": f"voice/{n:02d}.mp3",
                           "duration": round(duration, 3)})
    return result


# --- scène -------------------------------------------------------------------------------------

def camera_keys(track) -> dict:
    """Clés de caméra : la durée d'un point est le temps mis à rejoindre le point suivant (le
    dernier point tient jusqu'à la fin). Vérifié sur le pilote : les trois groupes de répliques
    tombent chacun dans un tronçon (39 s, 21 s, 15 s) de la trajectoire."""
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


def resolve_scene_lines(spec: dict, pack: Base, main: TextSet, fr: TextSet | None, report: list[str]) -> tuple[list[Line], list]:
    lines, raw = [], []
    delta = None
    for n, rid in enumerate(spec["lines"], 1):
        cd = pack.pb.ids.get(int(rid))
        if cd is None:
            raise ValueError(f"ClientData {rid} introuvable")
        cl = read_client_line(Ref(pack, cd))
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


def run(manifest: dict, out_root: Path, client: Path, only: list[str] | None, voices: bool, vgmstream: Path) -> list[str]:
    report: list[str] = []
    pack = open_pack(client)
    files = PakFiles(client / "data" / "Packs")
    main_spec, fr_spec = manifest["sources"]["main"], manifest["sources"]["fr"]
    main = load_textset(Path(main_spec["root"]), main_spec)
    try:
        fr = load_textset(Path(fr_spec["root"]), fr_spec)
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        report.append(f"textes FR illisibles : {exc}")
        fr = None
    anim_names = animation_names(pack)
    entries = []
    for spec in manifest["engine_scenes"]:
        if only and spec["id"] not in only:
            continue
        out = out_root / "engine" / spec["id"]
        out.mkdir(parents=True, exist_ok=True)
        buff = Ref(pack, pack.pb.ids[int(spec["buff"])])
        track = buff_camera_track(buff)
        camera = camera_keys(track)
        camera["fov"] = spec.get("fov", 45)
        lines, raw = resolve_scene_lines(spec, pack, main, fr, report)
        textures = TexturePool(files, out)
        map_base = open_map(pack, spec["map"])
        decor, decor_meta = build_decor(map_base, files, textures, report, tuple(spec.get("decor_center") or ()) or None,
                                        spec.get("decor_radius", 1e9))
        (out / "decor.glb").write_bytes(decor)
        actors_meta = []
        for actor in spec["actors"]:
            if actor.get("ground"):
                x, y = actor["position"][:2]
                z = ground_z(decor_meta["solids"], x, y, actor["position"][2] if len(actor["position"]) > 2 else 1e9)
                actor = {**actor, "position": [x, y, round(z, 3) if z is not None else actor["position"][2]]}
                report.append(f"{actor['id']} : posé à z = {z}")
            if actor.get("face"):
                fx, fy = actor["face"]
                actor = {**actor, "yaw": round(math.atan2(fy - actor["position"][1], fx - actor["position"][0]) - MODEL_FORWARD, 4)}
            data, meta = build_actor(actor, pack, files, textures, report)
            (out / "actors").mkdir(exist_ok=True)
            (out / "actors" / f"{actor['id']}.glb").write_bytes(data)
            name_idx = mob_name_index(find_mob(pack, actor))
            actors_meta.append({"id": actor["id"], "glb": f"actors/{actor['id']}.glb",
                                "name": {"ru": clean_text(main.texts["ru"][name_idx]), "en": clean_text(main.texts["en"][name_idx])},
                                "position": actor["position"], "yaw": actor.get("yaw", 0.0), "scale": actor.get("scale", 1.0),
                                "idle": actor.get("idle", "Idle"), "talk": actor.get("talk"),
                                "appear": actor.get("appear", 0.0), "light": local_light(decor_meta["samples"], actor["position"]),
                                **meta})
        voice_meta = [None] * len(lines)
        events = [cl.voice for cl in raw]
        if voices:
            voice_meta = export_voices(events, spec["voice_bank"], files, out / "voice", vgmstream, report)
        elif (out / "scene.json").is_file():
            old = json.loads((out / "scene.json").read_text(encoding="utf-8"))
            voice_meta = [l.get("voice") for l in old.get("lines", [])] or voice_meta
        starts = schedule_lines(spec, camera, voice_meta, lines)
        cues = build_cues(lines, starts, camera["duration"])
        tracks = []
        for lang in LANGS:
            vtt = to_vtt(cues, lang)
            if vtt:
                (out / f"{lang}.vtt").write_text(vtt, encoding="utf-8")
                tracks.append({"lang": lang, "label": LANG_LABELS[lang], "src": f"engine/{spec['id']}/{lang}.vtt",
                               "lines": sum(1 for c in cues if lang in c[2])})
        scene_lines = []
        for i, (line, cl) in enumerate(zip(lines, raw)):
            scene_lines.append({"n": i + 1, "start": starts[i], "duration": line.duration, "speaker": speaker_of(line, spec["actors"]),
                                "voice": voice_meta[i], "animations": [anim_names.get(a, str(a)) for a in cl.animations],
                                "text": line.text})
        scene = {"id": spec["id"], "map": spec["map"], "up": [0, 0, 1], "mirror": True, "duration": camera["duration"],
                 "camera": camera, "decor": "decor.glb", "actors": actors_meta, "lines": scene_lines,
                 "light": {**decor_meta["light"], **spec.get("light", {})}, "sources": spec.get("sources", {})}
        (out / "scene.json").write_text(json.dumps(scene, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        report.append(f"{spec['id']} : décor {len(decor) / 1e6:.1f} Mo, textures {textures.bytes_written / 1e6:.1f} Mo, "
                      f"{len(actors_meta)} acteurs, {len(lines)} répliques, {camera['duration']:.0f} s")
        entries.append({"spec": spec, "duration": camera["duration"], "tracks": tracks,
                        "lines": len(lines)})
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
    p.add_argument("--no-voices", action="store_true", help="garde les voix déjà extraites")
    p.add_argument("--vgmstream", type=Path, default=DEFAULT_VGMSTREAM)
    args = p.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = run(manifest, args.out, args.client, args.only, not args.no_voices, args.vgmstream)
    print("\n".join(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
