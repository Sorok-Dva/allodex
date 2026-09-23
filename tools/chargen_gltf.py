"""Briques glTF des personnages (textures, squelettes, clips, maillages skinnés).

Reprises telles quelles de `tools/extract_fatalities.py` de la branche des fatalités (agent
a3b3f11f, non fusionnée au moment de l'écriture) : `TexturePool`, `Exporter`, `reduce_keys`,
`clean_animation`, `bind_pose_positions`, `load_geometry`, `load_animation`. Seul le nom du
générateur glTF change. Quand les deux branches seront fusionnées, ce module pourra être
remplacé par un import depuis l'extracteur des fatalités (ou l'inverse).
"""
from __future__ import annotations

import io
import re
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

from tools import extract_menu_scene as _ems
from tools.allods_packdb import PackDB, PakCatalog
from tools.allods_visdb import GeometryInfo, read_geometry, read_texture
from tools.extract_menu_scene import (  # noqa: F401
    BLOCK_BYTES, FOURCC, BinSource, GltfBuilder, Skeleton, SkeletalAnimation, decode_vertex_buffer,
    parse_skeletal_animation, parse_skeleton, read_chunks, rest_local, rest_world_matrices,
    skin_attributes, validate_glb,
)
from tools.scenes.v5_0 import restore_fixed_rotations
from tools.scenes.v8_0 import restore_static_binds
from tools.uitexture import build_dds

def _slug(name: str) -> str:
    stem = re.sub(r"\.\(Texture\)\.(hi\.)?bin$", "", name)
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", stem.replace("/", "__"))


def infer_texture_dims(mips: dict[int, bytes]) -> list[tuple[str, int, int]]:
    """Candidats `(format, largeur, hauteur)` d'une texture DXT à partir de ses mipmaps.

    Chaque niveau `k` a pour dimensions `(w >> k, h >> k)` et la chaîne s'arrête quand la plus
    petite dimension atteint 4 pixels (un bloc) : `min(w, h) = 4 << max(k)`. Le nombre de blocs
    du niveau le plus fin donne l'autre dimension, pour chacun des deux formats possibles ; le
    format est certain si le dernier niveau ne fait qu'un bloc (8 ou 16 octets).
    """
    if not mips:
        return []
    last = max(mips)
    smallest = len(mips[last])
    formats = ["DXT5"] if smallest == 16 else ["DXT1"] if smallest == 8 else ["DXT5", "DXT1"]
    out: list[tuple[str, int, int]] = []
    finest = min(mips)
    for fmt in formats:
        block = BLOCK_BYTES[fmt]
        if len(mips[finest]) % block:
            continue
        blocks0 = len(mips[finest]) // block * (4 ** finest)
        short = 4 << last
        long_side = blocks0 * 16 // short
        if long_side * short != blocks0 * 16 or long_side < short:
            continue
        for w, h in ((long_side, short), (short, long_side)):
            if (w, h) not in [(c[1], c[2]) for c in out]:
                out.append((fmt, w, h))
    return out


class TexturePool:
    """Textures du client décodées en PNG, une seule fois, dans `textures/` (partagées entre
    les `.glb` par URI relative)."""

    def __init__(self, db: PackDB, cat: PakCatalog, bins: BinSource, out_dir: Path) -> None:
        self.db, self.cat, self.bins = db, cat, bins
        self.dir = out_dir / "textures"
        self.done: dict[tuple[str, int], str | None] = {}
        self.has_alpha: dict[str, bool] = {}
        self.by_name: dict[str, int] = {}
        for off in db.resources("Texture"):
            name = cat.name(db.binary_ref(off))
            if name:
                self.by_name.setdefault(name, off)
        self.bytes_written = 0

    def uri(self, name: str | None, max_size: int, prefix: str = "../textures/") -> str | None:
        if not name:
            return None
        key = (name, max_size)
        if key not in self.done:
            self.done[key] = self._export(name, max_size)
        file = self.done[key]
        return None if file is None else prefix + file

    def image(self, name: str, max_size: int) -> Image.Image | None:
        """Texture décodée (RGBA), au plus grand niveau de mipmap qui tient dans `max_size`.

        Sans ressource `Texture` (textures de terrain, lues par les calques de carte), format et
        dimensions se déduisent de la chaîne de mipmaps (`infer_texture_dims`)."""
        off = self.by_name.get(name)
        if off is not None:
            info = read_texture(self.db, self.cat, off)
        else:
            info = SimpleNamespace(binary=name, binary_hi=name[:-4] + ".hi.bin", fmt=None, width=0, height=0)
        mips: dict[int, bytes] = {}
        for binary in (info.binary, info.binary_hi):
            data = self.bins.get(binary) if binary else None
            if data:
                try:
                    mips.update(read_chunks(data))
                except zlib.error:
                    pass
        if info.fmt is None:
            candidates = infer_texture_dims(mips)
            if not candidates:
                return None
            fmt, width, height = next((c for c in candidates if c[1] == c[2]), candidates[0])
            info = SimpleNamespace(binary=info.binary, binary_hi=info.binary_hi, fmt=fmt, width=width, height=height)
        fmt = info.fmt
        if (fmt not in FOURCC and fmt != "RGBA") or not info.width or not info.height:
            return None
        for level in sorted(mips):
            w, h = max(1, info.width >> level), max(1, info.height >> level)
            if max(w, h) > max_size and level < max(mips):
                continue
            payload = mips[level]
            if fmt == "RGBA":
                # Non compressée : 4 octets par pixel, ordre B G R A (A8R8G8B8 de Direct3D).
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

    def _export(self, name: str, max_size: int) -> str | None:
        img = self.image(name, max_size)
        if img is None:
            return None
        file = f"{_slug(name)}{'' if max_size >= 1024 else f'@{max_size}'}.png"
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / file
        self.has_alpha[name] = img.getextrema()[3][0] < 255
        if not self.has_alpha[name]:
            img = img.convert("RGB")
        img.save(path, format="PNG", optimize=True)
        self.bytes_written += path.stat().st_size
        return file


# --- squelettes et animations -------------------------------------------------------------------

# Écart toléré en retirant une clé d'animation (interpolation linéaire des voisines) :
# 1 mm pour les translations (unités du jeu ≈ mètres), 2·10⁻⁴ par composante de quaternion
# (≈ 0,02°). Invisible, et divise le poids des personnages par ~4.
TRANSLATION_TOLERANCE = 1e-3
ROTATION_TOLERANCE = 2e-4
# Écart maximal entre deux clés gardées (images) : borne le coût du glouton.
MAX_KEY_GAP = 48

# glTF : composantes entières signées 16 bits (rotations quantifiées). Le constructeur glTF
# des scènes de menu ne s'en sert pas ; on étend ses tables sans rien changer à ses sorties.
_ems.COMPONENT.setdefault("i16", 5122)
_ems.COMPONENT_BYTES.setdefault(5122, 2)


def reduce_keys(values: np.ndarray, tolerance: float) -> np.ndarray:
    """Indices des clés à garder pour que l'interpolation linéaire des clés gardées reste à
    moins de `tolerance` (par composante) de chaque clé d'origine. Glouton, première et
    dernière clés toujours gardées ; une piste constante se réduit à deux clés."""
    n = len(values)
    if n <= 2:
        return np.arange(n)
    if np.max(np.ptp(values, axis=0)) <= tolerance:
        return np.array([0, n - 1])
    keep = [0]
    anchor = 0
    i = 2
    while i < n:
        # Peut-on relier `anchor` à `i` sans trahir les clés intermédiaires ?
        span = np.arange(anchor + 1, i)
        w = ((span - anchor) / (i - anchor))[:, None]
        interp = values[anchor] * (1 - w) + values[i] * w
        if i - anchor > MAX_KEY_GAP or np.max(np.abs(interp - values[span])) > tolerance:
            keep.append(i - 1)
            anchor = i - 1
        i += 1
    keep.append(n - 1)
    return np.array(keep)

def clean_animation(skeleton: Skeleton, animation: SkeletalAnimation) -> list[str]:
    """Règles établies sur les données (README, § « Scènes de menu ») appliquées à un clip :
    une piste sans canal animé qui recopie le bind est écartée (le squelette fait foi, échelle
    non uniforme comprise), puis les angles d'Euler fixes (écrits à 0) reprennent ceux du bind."""
    obj = SimpleNamespace(skeleton=skeleton, animation=animation)
    dropped = restore_static_binds(obj)
    restore_fixed_rotations(obj)
    return dropped


def bind_pose_positions(vertices: dict[str, np.ndarray], skeleton: Skeleton,
                        static: np.ndarray) -> np.ndarray:
    """Sommets skinnés ramenés dans le repère du modèle à la pose de bind :
    `Σ w · monde_bind · inverse_native · v`. Identique à `v` quand l'inverse native est celle
    du bind (cas des personnages) ; place correctement les sommets exprimés dans le repère de
    leur articulation (inverse native identité, cas de nombreux effets). Les sommets des
    éléments non skinnés (`static`) restent tels quels."""
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


# --- assemblage glTF ---------------------------------------------------------------------------

@dataclass
class Exporter:
    textures: TexturePool
    texture_max: int
    notes: list[str] = field(default_factory=list)
    # Décor : les matériaux opaques dont la texture a de l'alpha sont des feuillages découpés.
    cutout: bool = False

    def __post_init__(self) -> None:
        self.gltf = GltfBuilder()
        self.gltf.json["asset"]["generator"] = "allodex/extract_character_creation"
        self.images: dict[str, int | None] = {}
        self.materials: dict[tuple, int] = {}
        self.stats = {"triangles": 0, "animations": 0, "objects": 0}

    def texture(self, name: str | None) -> int | None:
        if not name:
            return None
        if name not in self.images:
            uri = self.textures.uri(name, self.texture_max)
            if uri is None:
                self.images[name] = None
                self.notes.append(f"texture illisible : {name}")
            else:
                self.gltf.json["images"].append({"uri": uri, "name": Path(name).name})
                self.gltf.json["textures"].append({"sampler": 0, "source": len(self.gltf.json["images"]) - 1})
                self.images[name] = len(self.gltf.json["textures"]) - 1
        return self.images[name]

    def material(self, element, orientation: str) -> int:
        mat = element.material
        # `BLEND_EFFECT_ADD` n'est additif que sur un matériau transparent (règle des scènes de
        # menu, vérifiée ici sur les peaux des personnages, ADD mais opaques).
        additive = mat.blend in ("BLEND_EFFECT_ADD", "BLEND_EFFECT_ALPHA_ADD", "BLEND_EFFECT_COLOR_ADD") and mat.transparent
        tex = self.texture(mat.texture)
        key = (tex, additive, mat.transparent, round(mat.alpha, 4), mat.blend)
        if key not in self.materials:
            alpha_mode = "BLEND" if mat.transparent else "OPAQUE"
            index = self.gltf.add_material(mat.name, tex, alpha_mode, True, additive, mat.alpha)
            extras = self.gltf.json["materials"][index].setdefault("extras", {})
            extras["gameBlend"] = mat.blend
            if self.cutout and not mat.transparent and self.textures.has_alpha.get(mat.texture or ""):
                extras["cutout"] = True
            self.materials[key] = index
        return self.materials[key]

    # -- squelette

    def emit_skeleton(self, skeleton: Skeleton, prefix: str) -> list[int]:
        nodes: list[int] = []
        for i, name in enumerate(skeleton.names):
            t, q, s = rest_local(skeleton, None, i)
            node = {"name": f"{prefix}/{name}", "translation": [float(v) for v in t],
                    "rotation": [float(v) for v in q]}
            if np.any(np.abs(s - 1.0) > 1e-7):
                node["scale"] = [float(v) for v in s]
            nodes.append(self.gltf.add_node(node))
        for i in range(len(skeleton)):
            parent = skeleton.parents[i]
            if 0 <= parent < len(skeleton) and parent != i:
                self.gltf.json["nodes"][nodes[parent]].setdefault("children", []).append(nodes[i])
        return nodes

    def emit_clip(self, name: str, skeleton: Skeleton, nodes: list[int], animation: SkeletalAnimation,
                  speed: float = 1.0) -> float:
        """Clip glTF d'une animation (pistes nettoyées) ; renvoie sa durée en secondes.

        Pour le poids : clés redondantes retirées (`reduce_keys`) et rotations en entiers 16 bits
        normalisés (`KHR_mesh_quantization`, lu par `GLTFLoader`)."""
        clean_animation(skeleton, animation)
        tracks = [t for t in animation.tracks if t.name in skeleton.names]
        frames = max(animation.frames, 1)
        duration = (frames - 1) / float(animation.fps) / max(speed, 1e-6) if frames > 1 else 0.0
        if not tracks:
            return duration
        times = np.arange(frames, dtype=np.float32) / float(animation.fps) / max(speed, 1e-6)
        if frames == 1:
            times = np.array([0.0], np.float32)
        time_cache: dict[bytes, int] = {}
        samplers: list[dict] = []
        channels: list[dict] = []

        def channel(node: int, path: str, values: np.ndarray, kind: str) -> None:
            values = np.asarray(values, np.float64)
            if len(values) != len(times):
                values = np.repeat(values[:1], len(times), axis=0)
            keep = reduce_keys(values, ROTATION_TOLERANCE if path == "rotation" else TRANSLATION_TOLERANCE)
            key_times = times[keep]
            token = keep.tobytes()
            if token not in time_cache:
                time_cache[token] = self.gltf.add_accessor(key_times.astype(np.float32), "SCALAR", "f32", minmax=True)
            if path == "rotation":
                quant = np.round(np.clip(values[keep], -1, 1) * 32767).astype(np.int16)
                acc = self.gltf.add_accessor(quant, kind, "i16", normalized=True)
                self.quantized = True
            else:
                acc = self.gltf.add_accessor(values[keep].astype(np.float32), kind, "f32")
            samplers.append({"input": time_cache[token], "output": acc, "interpolation": "LINEAR"})
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

    # -- maillage

    def emit_mesh(self, name: str, geo: GeometryInfo, vertices: dict[str, np.ndarray], indices: np.ndarray,
                  elements: list, skeleton: Skeleton | None, texture_override: dict[str, str] | None = None
                  ) -> tuple[int | None, bool]:
        doc = geo.doc
        position = vertices["position"].astype(np.float32)
        skinned = skeleton is not None and "indices" in vertices and "weights" in vertices
        static = np.zeros(len(position), bool)
        for e in doc.elements:
            if e.skin_index < 0:
                static[np.unique(indices[e.ib0:e.ib1])] = True
        if skinned:
            position = bind_pose_positions(vertices, skeleton, static)
        uv = vertices.get("texcoord0", np.zeros((len(position), 2), np.float32)).astype(np.float32).copy()
        uv[:, 1] = 1.0 - uv[:, 1]  # V = 0 en bas dans le jeu, en haut en glTF
        color = vertices.get("color")
        if color is None:
            rgba = np.full((len(position), 4), 255, np.uint8)
        else:
            rgb = np.minimum(color[:, :3].astype(np.uint16) * 2, 255).astype(np.uint8)
            rgb[color[:, :3].max(axis=1) == 0] = 255
            rgba = np.concatenate([rgb, color[:, 3:4]], axis=1)
        attributes = {
            "POSITION": self.gltf.add_accessor(position, "VEC3", "f32", target=34962, minmax=True),
            "TEXCOORD_0": self.gltf.add_accessor(uv, "VEC2", "f32", target=34962),
            "COLOR_0": self.gltf.add_accessor(rgba, "VEC4", "u8", normalized=True, target=34962),
        }
        if "normal" in vertices:
            normal = vertices["normal"].astype(np.float32)
            norm = np.linalg.norm(normal, axis=1, keepdims=True)
            normal = np.where(norm > 1e-6, normal / np.maximum(norm, 1e-9), np.array([0, 0, 1], np.float32))
            attributes["NORMAL"] = self.gltf.add_accessor(normal.astype(np.float32), "VEC3", "f32", target=34962)
        if skinned:
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
            self.stats["triangles"] += tri.size // 3
            if texture_override and element.name in texture_override:
                element.material.texture = texture_override[element.name]
            prim = {"attributes": attributes, "mode": 4,
                    "indices": self.gltf.add_accessor(tri.astype(np.uint32), "SCALAR", "u32", target=34963),
                    "material": self.material(element, geo.orientation),
                    "extras": {"element": element.name}}
            su, sv = element.material.uv_scroll
            if su or sv:
                prim["extras"]["uvScroll"] = [su, sv]
            primitives.append(prim)
        if not primitives:
            return None, skinned
        self.gltf.json["meshes"].append({"name": name, "primitives": primitives})
        return len(self.gltf.json["meshes"]) - 1, skinned

    def skin(self, name: str, skeleton: Skeleton, joint_nodes: list[int], static_node: int) -> int:
        world = rest_world_matrices(skeleton, None)
        inverse = np.zeros((len(skeleton) + 1, 16), np.float32)
        for i in range(len(skeleton)):
            inverse[i] = np.linalg.inv(world[i]).T.reshape(-1)
        inverse[len(skeleton)] = np.eye(4, dtype=np.float32).reshape(-1)
        self.gltf.json["skins"].append({
            "name": f"{name}_skin",
            "inverseBindMatrices": self.gltf.add_accessor(inverse, "MAT4", "f32"),
            "joints": joint_nodes + [static_node],
        })
        return len(self.gltf.json["skins"]) - 1

    def finish(self, roots: list[int]) -> bytes:
        self.gltf.json["scenes"][0]["nodes"].extend(roots)
        if getattr(self, "quantized", False):
            for key in ("extensionsUsed", "extensionsRequired"):
                used = self.gltf.json.setdefault(key, [])
                if "KHR_mesh_quantization" not in used:
                    used.append("KHR_mesh_quantization")
        glb = self.gltf.to_glb()
        validate_glb(glb)
        return glb


# --- chargement --------------------------------------------------------------------------------

@dataclass
class Loaded:
    geo: GeometryInfo
    vertices: dict[str, np.ndarray]
    indices: np.ndarray
    skeleton: Skeleton | None


def load_geometry(db: PackDB, cat: PakCatalog, bins: BinSource, off: int) -> Loaded | None:
    geo = read_geometry(db, cat, off)
    data = bins.get(geo.binary) if geo.binary else None
    if data is None or not geo.doc.layouts:
        return None
    chunks = read_chunks(data)
    vb, ib = chunks.get(0), chunks.get(1)
    if vb is None or ib is None:
        return None
    layout = geo.doc.layouts[0]
    if layout.stride <= 0 or len(vb) < layout.stride:
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


def load_animation(bins: BinSource, name: str | None, skeleton: Skeleton, span: float) -> SkeletalAnimation | None:
    data = bins.get(name) if name else None
    if not data:
        return None
    payload = read_chunks(data).get(0)
    if not payload:
        return None
    try:
        return parse_skeletal_animation(payload, skeleton, span)
    except (struct.error, ValueError, IndexError):
        return None


