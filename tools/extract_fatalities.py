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

* `characters/<id>.glb` — personnage sans équipement tel que le client le montre (apparence
  par défaut et peau cuite : `tools/allods_characters.py`) avec les clips : `Idle01` et toutes les
  animations que les scripts de la victime et du tueur demandent ;
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

from tools.allods_characters import (  # noqa: E402
    bake_skin, find_character_template, read_character_template, resolve_appearance,
)
from tools.allods_packdb import PackDB, PakCatalog, open_catalog, open_pack  # noqa: E402
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


# --- textures ----------------------------------------------------------------------------------

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
        self.by_name: dict[str, list[int]] = {}
        for kind in ("Texture", "IndexedTexture"):
            for off in db.resources(kind):
                name = cat.name(db.binary_ref(off))
                if name:
                    self.by_name.setdefault(name, []).append(off)
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

        Plusieurs ressources `Texture` peuvent nommer le même `.bin` avec des dimensions
        différentes (`Rays12White` : 256² et 128²) : on essaie chacune, puis les dimensions
        déduites de la chaîne de mipmaps (`infer_texture_dims`, seule source pour les textures
        de terrain), et l'on garde la première dont les niveaux ont la taille attendue."""
        infos = [read_texture(self.db, self.cat, off) for off in self.by_name.get(name, [])]
        binary = infos[0].binary if infos else name
        binary_hi = infos[0].binary_hi if infos else name[:-4] + ".hi.bin"
        mips: dict[int, bytes] = {}
        for file in (binary, binary_hi):
            data = self.bins.get(file) if file else None
            if data:
                try:
                    mips.update(read_chunks(data))
                except zlib.error:
                    pass
        candidates = [(i.fmt, i.width, i.height) for i in infos]
        inferred = infer_texture_dims(mips)
        candidates += sorted(inferred, key=lambda c: c[1] != c[2])
        for fmt, width, height in dict.fromkeys(candidates):
            img = self._decode(mips, fmt, width, height, max_size)
            if img is not None:
                return img
        return None

    @staticmethod
    def _decode(mips: dict[int, bytes], fmt: str, width: int, height: int, max_size: int) -> Image.Image | None:
        if (fmt not in FOURCC and fmt != "RGBA") or not width or not height:
            return None
        for level in sorted(mips):
            w, h = max(1, width >> level), max(1, height >> level)
            if max(w, h) > max_size and level < max(mips):
                continue
            payload = mips[level]
            if fmt == "RGBA":
                # Non compressée : 4 octets par pixel, ordre B G R A (A8R8G8B8 de Direct3D).
                if len(payload) != w * h * 4:
                    return None
                bgra = np.frombuffer(payload, np.uint8).reshape(h, w, 4)
                return Image.fromarray(bgra[:, :, [2, 1, 0, 3]].copy(), "RGBA")
            need = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * BLOCK_BYTES[fmt]
            if len(payload) != need:
                return None
            img = Image.open(io.BytesIO(build_dds(w, h, FOURCC[fmt], payload)))
            img.load()
            return img.convert("RGBA")
        return None

    def add_image(self, name: str, img: Image.Image, max_size: int) -> None:
        """Image calculée (peau cuite d'un personnage) servie sous `name` comme une texture."""
        self.done[(name, max_size)] = self._write(name, img, max_size)

    def _export(self, name: str, max_size: int) -> str | None:
        img = self.image(name, max_size)
        return None if img is None else self._write(name, img, max_size)

    def _write(self, name: str, img: Image.Image, max_size: int) -> str:
        if max(img.size) > max_size:
            img = img.resize((min(img.width, max_size), min(img.height, max_size)), Image.LANCZOS)
        file = f"{_slug(name)}{'' if max_size >= 1024 else f'@{max_size}'}.png"
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / file
        self.has_alpha[name] = img.mode == "RGBA" and img.getextrema()[3][0] < 255
        if not self.has_alpha[name]:
            img = img.convert("RGB")
        img.save(path, format="PNG", optimize=True)
        self.bytes_written += path.stat().st_size
        return file


def is_soft_geometry(env: str) -> bool:
    """Textures d'environnement qui sont en fait des masques de « géométrie douce » (disque
    d'alpha lu par la normale vue de la caméra) — pas des cartes de reflets (`Refmap*`)."""
    return Path(env).name.startswith("SoftGeometryGrain")


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
        # Teinte multiplicative par géoset (couleur des cheveux, couleur d'armure).
        self.tints: dict[str, tuple[float, float, float]] = {}
        self.gltf = GltfBuilder()
        self.gltf.json["asset"]["generator"] = "allodex/extract_fatalities"
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
        tint = self.tints.get(element.name)
        env = getattr(mat, "env_texture", None)
        soft = self.textures.uri(env, FX_TEXTURE_MAX) if env and mat.transparent and is_soft_geometry(env) else None
        key = (tex, additive, mat.transparent, round(mat.alpha, 4), mat.blend, tint, soft)
        if key not in self.materials:
            alpha_mode = "BLEND" if mat.transparent else "OPAQUE"
            index = self.gltf.add_material(mat.name, tex, alpha_mode, True, additive, mat.alpha)
            extras = self.gltf.json["materials"][index].setdefault("extras", {})
            extras["gameBlend"] = mat.blend
            if tint:
                self.gltf.json["materials"][index]["pbrMetallicRoughness"]["baseColorFactor"][:3] = [round(c, 4) for c in tint]
                extras["tint"] = True
            if soft:
                extras["soft"] = soft
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


# --- personnages -------------------------------------------------------------------------------

def _read_xml(path: Path) -> ET.Element | None:
    try:
        return ET.fromstring(path.read_text(errors="replace"))
    except (OSError, ET.ParseError):
        return None


def _href(node: ET.Element | None) -> str | None:
    href = node.get("href") if node is not None else None
    return href.split("#")[0] if href else None


def bake_size(base: Image.Image, patches, image_of) -> int:
    """Côté de la peau cuite : celui de la peau de base, relevé si un calque est plus fin que
    son rectangle ne le permet (sans dépasser `CHARACTER_TEXTURE_MAX`)."""
    size = max(base.size)
    for patch in patches:
        img = image_of(patch.texture) if patch.texture else None
        if img is None:
            continue
        x1, x2, y1, y2 = patch.rect
        if x2 > x1:
            size = max(size, round(img.width / (x2 - x1)))
        if y2 > y1:
            size = max(size, round(img.height / (y2 - y1)))
    return min(1 << max(size - 1, 1).bit_length(), CHARACTER_TEXTURE_MAX)


def build_character(spec: dict, db: PackDB, cat: PakCatalog, bins: BinSource, textures: TexturePool,
                    wanted: set[str]) -> tuple[bytes, dict, list[str]]:
    """Personnage jouable tel que le client le montre sans équipement : apparence par défaut
    (`tools/allods_characters.py` : tenue par défaut, sous-vêtements, variation par défaut du
    client), peau cuite avec ses calques, squelette et clips demandés."""
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
    geo_elements = loaded.geo.doc.elements
    appearance = resolve_appearance(template, [e.name for e in geo_elements],
                                    {e.name: e.material.texture for e in geo_elements if e.material.visible})
    # Peau cuite : remplace la peau de base sur tous les géosets qui la portent.
    override = dict(appearance.replacements)
    skin = template.main_texture
    base = textures.image(skin, 4096) if skin else None
    baked_name = None
    if base is not None:
        image_of = lambda name: textures.image(name, 4096)  # noqa: E731
        mask = textures.image(appearance.skin_mask, 4096) if appearance.skin_mask else None
        baked = bake_skin(base, appearance, image_of, mask, bake_size(base, appearance.patches, image_of))
        baked_name = f"characters/{spec['id']}-skin"
        textures.add_image(baked_name, baked, CHARACTER_TEXTURE_MAX)
    visible = set(appearance.visible)
    elements = []
    for element in geo_elements:
        if element.name not in visible:
            continue
        if baked_name and element.name not in override and element.material.texture == skin:
            override[element.name] = baked_name
        elements.append(element)
    exporter.tints = appearance.tints
    mesh, skinned = exporter.emit_mesh(spec["model"], loaded.geo, loaded.vertices, loaded.indices,
                                       elements, loaded.skeleton, override)
    if mesh is None:
        raise ValueError(f"aucun géoset visible : {spec['model']}")
    skeleton = loaded.skeleton
    joint_nodes = exporter.emit_skeleton(skeleton, spec["model"])
    static_node = exporter.gltf.add_node({"name": f"{spec['model']}/Static"})
    mesh_node = {"name": f"{spec['model']}_mesh", "mesh": mesh}
    if skinned:
        mesh_node["skin"] = exporter.skin(spec["model"], skeleton, joint_nodes, static_node)
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
    root = exporter.gltf.add_node({"name": spec["model"], "children": roots + [static_node, exporter.gltf.add_node(mesh_node)],
                                   **({"scale": [vot.scale] * 3} if abs(vot.scale - 1) > 1e-6 else {})})
    glb = exporter.finish([root])
    height = float(loaded.vertices["position"][:, 2].max() * vot.scale)
    meta = {"id": spec["id"], "race": spec["race"], "sex": spec["sex"], "model": spec["model"],
            "glb": f"characters/{spec['id']}.glb", "scale": vot.scale, "height": round(height, 3),
            "geosets": [e.name for e in elements],
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


# --- effets ------------------------------------------------------------------------------------

@dataclass
class FxBuild:
    exporter: Exporter
    db: PackDB
    cat: PakCatalog
    bins: BinSource
    names: dict[int, str] = field(default_factory=dict)       # décalage VOT → nom unique
    meta: dict[str, dict] = field(default_factory=dict)
    roots: list[int] = field(default_factory=list)
    sounds: set[str] = field(default_factory=set)
    particles: "ParticlePool | None" = None
    report: list[str] = field(default_factory=list)

    def name_of(self, off: int) -> str:
        if off not in self.names:
            base = read_visobject(self.db, self.cat, off).name
            name, k = base, 2
            while name in self.names.values():
                name, k = f"{base}#{k}", k + 1
            self.names[off] = name
        return self.names[off]

    def emit(self, off: int, depth: int = 0) -> int | None:
        """Nœud d'un gabarit : géométrie skinnée animée, composants accrochés."""
        if depth > 8:
            return None
        vot = read_visobject(self.db, self.cat, off)
        name = self.name_of(off)
        ex = self.exporter
        children: list[int] = []
        joint_nodes: list[int] = []
        joint_names: list[str] = []
        locators: dict[str, tuple] = {}
        duration = 0.0
        loop = False
        info: dict = {"fadeIn": vot.fade_in_ms / 1000.0, "fadeOut": vot.fade_out_ms / 1000.0,
                      "scale": vot.scale}
        if vot.sound:
            info["sound"] = vot.sound
            self.sounds.add(vot.sound)
        if vot.particle is not None:
            system = self.particles.system(vot.particle, self.report) if self.particles else None
            if system is not None:
                info["particles"] = system
        loaded = load_geometry(self.db, self.cat, self.bins, vot.geometry) if vot.geometry is not None else None
        if loaded is not None:
            geo = loaded.geo
            if geo.orientation != "COMMON":
                info["orientation"] = geo.orientation
            for loc in geo.doc.locators:
                locators[loc.name] = loc
            # Un élément sans texture n'est pas dessiné (mêmes emplacements vides que les
            # armures des personnages ; ici les formes d'émission Maya — anneaux gris opaques
            # de `FatalityWarlock` — qui boucheraient la vue).
            elements = [e for e in geo.doc.elements if e.material.visible and e.material.texture]
            mesh, skinned = ex.emit_mesh(name, geo, loaded.vertices, loaded.indices, elements, loaded.skeleton)
            if mesh is not None:
                ex.stats["objects"] += 1
                mesh_node = {"name": f"{name}_mesh", "mesh": mesh}
                skeleton = loaded.skeleton
                if skeleton is not None and skinned:
                    joint_nodes = ex.emit_skeleton(skeleton, name)
                    joint_names = list(skeleton.names)
                    static_node = ex.gltf.add_node({"name": f"{name}/Static"})
                    mesh_node["skin"] = ex.skin(name, skeleton, joint_nodes, static_node)
                    children.extend(joint_nodes[i] for i in range(len(skeleton))
                                    if not (0 <= skeleton.parents[i] < len(skeleton)))
                    children.append(static_node)
                    anim_name = self.cat.name(self.db.binary_ref(vot.animation)) if vot.animation is not None else None
                    span = float(np.max(np.abs(loaded.vertices["position"])) * 8.0) if len(loaded.vertices["position"]) else 0.0
                    animation = load_animation(self.bins, anim_name, skeleton, span)
                    if animation is not None:
                        speed = self.db.f32(vot.animation + 0x100) or 1.0
                        loop = bool(self.db.u8(vot.animation + 0x108))
                        duration = ex.emit_clip(name, skeleton, joint_nodes, animation, speed)
                children.append(ex.gltf.add_node(mesh_node))
        info["duration"] = round(duration, 4)
        info["loop"] = loop
        attached = []
        for comp in vot.components:
            if comp.visobject is None:
                continue
            child = self.emit(comp.visobject, depth + 1)
            if child is None:
                continue
            node = ex.gltf.json["nodes"][child]
            t = np.array(comp.offset, float)
            r = comp.rotation
            # Échelle du composant × échelle propre du gabarit accroché (les racines, elles,
            # reçoivent la leur dans le lecteur).
            s = comp.scale * (read_visobject(self.db, self.cat, comp.visobject).scale or 1.0)
            if comp.locator in joint_names:
                ex.gltf.json["nodes"][joint_nodes[joint_names.index(comp.locator)]].setdefault("children", []).append(child)
            elif comp.locator in locators:
                loc = locators[comp.locator]
                t = np.array(loc.position) + _rotate(loc.rotation, t) * loc.scale
                r = _qmul(loc.rotation, r)
                s = s * loc.scale
                children.append(child)
            else:
                if comp.locator:
                    self.exporter.notes.append(f"{name} : locator {comp.locator} introuvable (composant à l'origine)")
                children.append(child)
            if np.any(np.abs(t) > 1e-9):
                node["translation"] = [float(v) for v in t]
            if abs(r[3] - 1) > 1e-9 or any(abs(v) > 1e-9 for v in r[:3]):
                node["rotation"] = [float(v) for v in r]
            if abs(s - 1) > 1e-9:
                node["scale"] = [float(s)] * 3
            if comp.start > 0 or comp.stop is not None:
                node.setdefault("extras", {})["window"] = [comp.start, comp.stop]
            item = {"vot": self.name_of(comp.visobject), "locator": comp.locator}
            if comp.start > 0:
                item["start"] = comp.start
            if comp.stop is not None:
                item["stop"] = comp.stop
            if comp.random_delay:
                self.exporter.notes.append(f"{name} : délai aléatoire de {item['vot']} pris à sa borne basse")
            attached.append(item)
        if attached:
            info["components"] = attached
        self.meta[name] = info
        return ex.gltf.add_node({"name": f"vot:{name}", "children": children, "extras": {"vot": name}})


def _qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def _rotate(q, v):
    x, y, z, w = q
    vx, vy, vz = v
    tx, ty, tz = 2 * (y * vz - z * vy), 2 * (z * vx - x * vz), 2 * (x * vy - y * vx)
    return np.array((vx + w * tx + (y * tz - z * ty), vy + w * ty + (z * tx - x * tz), vz + w * tz + (x * ty - y * tx)))


# --- particules --------------------------------------------------------------------------------

class ParticlePool:
    """Systèmes de particules exportés : binaire du client allégé (`allods_particles.simplify`,
    même format) compressé en zlib dans `particles/`, et un atlas réduit aux seules images
    utilisées (découpées dans `Client/Render/ParticleAtlas`)."""

    def __init__(self, db: PackDB, cat: PakCatalog, bins: BinSource, out_dir: Path) -> None:
        self.db, self.cat, self.bins = db, cat, bins
        self.dir = out_dir / "particles"
        self.systems: dict[str, dict] = {}
        self.rects: list[tuple[str, int, int, int, int]] = []
        self.rect_index: dict[tuple, int] = {}
        self.bytes_written = 0

    def system(self, off: int, report: list[str]) -> dict | None:
        from tools.allods_particles import encode_particles, parse_particles, simplify
        from tools.allods_visdb import atlas_rect, read_particle_animation
        info = read_particle_animation(self.db, self.cat, off)
        if not info.binary:
            return None
        if info.binary in self.systems:
            return self.systems[info.binary]
        data = self.bins.get(info.binary)
        payload = read_chunks(data).get(0) if data else None
        if not payload:
            report.append(f"AVERTISSEMENT : particules absentes {info.binary}")
            self.systems[info.binary] = None
            return None
        pf = parse_particles(payload)
        if len(pf.emitters) != len(info.emitters):
            report.append(f"AVERTISSEMENT : {info.binary} : {len(pf.emitters)} émetteurs dans le binaire, "
                          f"{len(info.emitters)} dans la ressource")
        packed = zlib.compress(encode_particles(simplify(pf)), 9)
        file = re.sub(r"\.\(ParticleAnimation\)\.bin$", "", info.binary.split("/")[-1]) + ".bin"
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / file).write_bytes(packed)
        self.bytes_written += len(packed)
        frames = []
        for element in info.textures:
            rect = atlas_rect(self.db, self.cat, element)
            if rect is None:
                frames.append(-1)
                continue
            if rect not in self.rect_index:
                self.rect_index[rect] = len(self.rects)
                self.rects.append(rect)
            frames.append(self.rect_index[rect])
        entry = {
            "file": f"particles/{file}", "speed": info.speed, "loop": info.looped,
            "endFrame": info.end_frame, "loopFrame": info.loop_frame, "frames": frames,
            "emitters": [{"additive": e.additive, "tint": [round(c / 128.0, 4) for c in e.color[:3]],
                          "render": e.render, "pivot": [round(v, 4) for v in e.pivot],
                          "virtualOffset": round(e.virtual_offset, 4), "looping": e.looping,
                          "worldSpace": e.world_space, "flip": list(e.flip)} for e in info.emitters],
        }
        self.systems[info.binary] = entry
        return entry

    def write_atlas(self, textures: "TexturePool") -> dict | None:
        """Assemble les images utilisées en rangées (plus haute d'abord) dans un atlas carré."""
        if not self.rects:
            return None
        sources: dict[str, Image.Image] = {}
        for name, *_ in self.rects:
            if name and name not in sources:
                img = textures.image(name, 4096)
                if img is not None:
                    sources[name] = img
        order = sorted(range(len(self.rects)), key=lambda i: -self.rects[i][4])
        width = PARTICLE_ATLAS_WIDTH
        x = y = row = 0
        placed: dict[int, tuple[int, int]] = {}
        for i in order:
            _, _, _, w, h = self.rects[i]
            if x + w > width:
                x, y, row = 0, y + row, 0
            placed[i] = (x, y)
            x += w
            row = max(row, h)
        height = 1
        while height < y + row:
            height *= 2
        atlas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        out_rects = []
        for i, (name, sx, sy, w, h) in enumerate(self.rects):
            src = sources.get(name)
            px, py = placed[i]
            if src is not None:
                atlas.paste(src.crop((sx, sy, sx + w, sy + h)), (px, py))
            out_rects.append([px, py, w, h])
        self.dir.mkdir(parents=True, exist_ok=True)
        atlas.save(self.dir / "atlas.png", format="PNG", optimize=True)
        self.bytes_written += (self.dir / "atlas.png").stat().st_size
        return {"file": "particles/atlas.png", "width": width, "height": height, "rects": out_rects,
                "sources": [list(r) for r in self.rects]}

    def seed(self, previous: dict | None) -> None:
        """Reprend les images de l'atlas précédent, dans le même ordre : un export partiel
        (`--only-fx`) garde valables les indices des fatalités qu'il ne réécrit pas."""
        for rect in (previous or {}).get("sources", []):
            key = tuple(rect)
            if key not in self.rect_index:
                self.rect_index[key] = len(self.rects)
                self.rects.append(key)


# Largeur de l'atlas réduit (les images de l'atlas du client font 32 à 256 px).
PARTICLE_ATLAS_WIDTH = 1024


# --- sons --------------------------------------------------------------------------------------

# Banques des fatalités, puis celles des deux effets empruntés à d'autres sorts (gel du Mage :
# `Mobs/WormGracial/FrozenStatue`, dans `WormGracialSpells` ; lance de Smeyana :
# `SmeyanaFX/spearFireHit`, dans `Spells_FX2`), fouillées seulement pour les ondes manquantes.
SOUND_BANKS = ("SFX/Spells/Fatality.bsb", "SFX/Spells/Fatality2.bsb", "SFX/Spells/WormGracialSpells.bsb",
               "SFX/Spells/Spells_FX2.bsb")


def _sound_key(name: str) -> str:
    """Clé d'appariement événement ↔ onde : casse et soulignés ignorés (l'événement
    `FatalityUniversal` joue l'onde `fatality_universal.wav`, seul écart de nommage des banques
    de fatalités)."""
    return name.lower().replace("_", "")


def export_sounds(names: set[str], bins: BinSource, out_dir: Path, vgmstream: Path, report: list[str]) -> dict[str, str]:
    """Événement FMOD → onde. Les événements des fatalités (`spells/FX/Spells/Fatality/X`)
    n'ont qu'une onde, `fx/spells/fatality/X.wav` dans `Sounds.bev`, rangée sous le nom `X`
    dans les banques `Fatality*.bsb` : on apparie par ce nom."""
    from tools.extract_audio import encode_outputs, fsb_payload_from_bytes, run_vgmstream
    import subprocess
    wanted = {_sound_key(n.split("/")[-1]): n for n in names}
    found: dict[str, str] = {}
    target = out_dir / "sfx"
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for bank in SOUND_BANKS:
            if len(found) == len(wanted):
                break
            data = bins.get(bank)
            payload = fsb_payload_from_bytes(data, bank) if data else None
            if payload is None:
                report.append(f"AVERTISSEMENT : banque absente {bank}")
                continue
            fsb = Path(tmp) / (Path(bank).stem + ".fsb")
            fsb.write_bytes(payload)
            listing = subprocess.run([str(vgmstream), "-m", str(fsb)], capture_output=True, text=True).stdout
            m = re.search(r"stream count: (\d+)", listing)
            count = int(m.group(1)) if m else 1
            for sub in range(1, count + 1):
                info = subprocess.run([str(vgmstream), "-m", "-s", str(sub), str(fsb)], capture_output=True, text=True).stdout
                sm = re.search(r"stream name: (.*)", info)
                stream = sm.group(1).strip() if sm else ""
                key = _sound_key(stream)
                if key not in wanted or key in found:
                    continue
                stream_file = stream
                base = target / stream_file
                if not (base.with_suffix(".ogg").exists() and base.with_suffix(".mp3").exists()):
                    wav = Path(tmp) / f"{stream_file}.wav"
                    run_vgmstream(vgmstream, fsb, sub, wav)
                    encode_outputs(wav, base, "sfx")
                found[key] = f"sfx/{stream_file}"
    for short, full in wanted.items():
        if short not in found:
            report.append(f"AVERTISSEMENT : onde introuvable pour l'événement {full}")
    return {wanted[k]: v for k, v in found.items()}


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


def build_scene(spec: dict, db: PackDB, cat: PakCatalog, bins: BinSource, textures: TexturePool,
                server_root: Path) -> tuple[bytes, dict, list[str]]:
    """Petit décor : sol texturé (textures de terrain de la zone), ornements (arbres, rochers,
    buissons de la zone, à leur pose de bind), dôme de ciel du client. Tout vient du client ;
    seule la disposition (manifeste, `scene.props`) est une mise en scène."""
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

    node = disc(ground["radius"], ground["tile"], ground["texture"], None, 0.0, "ground")
    roots.append(node)
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
                  "translation": [float(x), float(y), 0.0],
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
    packs = client / "data" / "Packs"
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
        glb, meta, notes = build_scene(manifest["scene"], db, cat, bins, textures, server_root)
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
