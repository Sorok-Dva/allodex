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

* `characters/<id>.glb` — personnage (géométrie et matériaux RU, géosets de la tenue par
  défaut) avec les clips : `idle01` et toutes les animations que les chronologies demandent ;
* `fx/<id>.glb` — les gabarits d'objets d'une fatalité, un nœud `vot:<nom>` chacun, avec
  leur squelette, leur clip et leurs composants accrochés ; textures communes dans `textures/` ;
* `sfx/<nom>.ogg|.mp3` — les ondes des fatalités ;
* `fatalities.json` — index : personnages, fatalités, chronologies par personnage, gabarits.

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

from tools.allods_packdb import PackDB, PakCatalog, open_catalog, open_pack  # noqa: E402
from tools.allods_visdb import (  # noqa: E402
    GeometryInfo, VisObject, animation_names, read_fatalities, read_geometry, read_texture,
    read_visobject,
)
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


class TexturePool:
    """Textures du client décodées en PNG, une seule fois, dans `textures/` (partagées entre
    les `.glb` par URI relative)."""

    def __init__(self, db: PackDB, cat: PakCatalog, bins: BinSource, out_dir: Path) -> None:
        self.db, self.cat, self.bins = db, cat, bins
        self.dir = out_dir / "textures"
        self.done: dict[tuple[str, int], str | None] = {}
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

    def _export(self, name: str, max_size: int) -> str | None:
        off = self.by_name.get(name)
        if off is None:
            return None
        info = read_texture(self.db, self.cat, off)
        fmt = info.fmt
        if fmt not in FOURCC or not info.width or not info.height:
            return None
        mips: dict[int, bytes] = {}
        for binary in (info.binary, info.binary_hi):
            data = self.bins.get(binary) if binary else None
            if data:
                try:
                    mips.update(read_chunks(data))
                except zlib.error:
                    pass
        block = BLOCK_BYTES[fmt]
        for level in sorted(mips):
            w, h = max(1, info.width >> level), max(1, info.height >> level)
            if max(w, h) > max_size and level < max(mips):
                continue
            need = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * block
            payload = mips[level]
            if len(payload) < need:
                continue
            img = Image.open(io.BytesIO(build_dds(w, h, FOURCC[fmt], payload[:need])))
            img.load()
            img = img.convert("RGBA")
            file = f"{_slug(name)}{'' if max_size >= 1024 else f'@{max_size}'}.png"
            self.dir.mkdir(parents=True, exist_ok=True)
            path = self.dir / file
            if fmt == "DXT1" or img.getextrema()[3][0] == 255:
                img = img.convert("RGB")
            img.save(path, format="PNG", optimize=True)
            self.bytes_written += path.stat().st_size
            return file
        return None


# --- squelettes et animations -------------------------------------------------------------------

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

    def __post_init__(self) -> None:
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
        key = (tex, additive, mat.transparent, round(mat.alpha, 4), mat.blend)
        if key not in self.materials:
            alpha_mode = "BLEND" if mat.transparent else "OPAQUE"
            index = self.gltf.add_material(mat.name, tex, alpha_mode, True, additive, mat.alpha)
            extras = self.gltf.json["materials"][index].setdefault("extras", {})
            extras["gameBlend"] = mat.blend
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
        """Clip glTF d'une animation (pistes nettoyées) ; renvoie sa durée en secondes."""
        clean_animation(skeleton, animation)
        tracks = [t for t in animation.tracks if t.name in skeleton.names]
        frames = max(animation.frames, 1)
        duration = (frames - 1) / float(animation.fps) / max(speed, 1e-6) if frames > 1 else 0.0
        if not tracks:
            return duration
        times = np.arange(frames, dtype=np.float32) / float(animation.fps) / max(speed, 1e-6)
        if frames == 1:
            times = np.array([0.0], np.float32)
        acc_time = self.gltf.add_accessor(times, "SCALAR", "f32", minmax=True)
        samplers: list[dict] = []
        channels: list[dict] = []

        def channel(node: int, path: str, values: np.ndarray, kind: str) -> None:
            if len(values) != len(times):
                values = np.repeat(values[:1], len(times), axis=0)
            acc = self.gltf.add_accessor(values.astype(np.float32), kind, "f32")
            samplers.append({"input": acc_time, "output": acc, "interpolation": "LINEAR"})
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


def visual_item_shapes(path: Path) -> tuple[dict[str, str | None], set[str]]:
    root = _read_xml(path)
    shown: dict[str, str | None] = {}
    hidden: set[str] = set()
    if root is None:
        return shown, hidden
    for item in root.iter("Item"):
        shape = item.findtext("shapeName")
        if shape:
            shown[shape.strip()] = _href(item.find("replacement"))
    for node in root.findall("./hiddenGeosets//Item"):
        if node.text and node.text.strip():
            hidden.add(node.text.strip())
    return shown, hidden


def character_selection(server_root: Path, spec: dict) -> tuple[set[str], dict[str, str | None]]:
    """(géosets cachés par la tenue par défaut, géosets montrés par la variation par défaut →
    texture de remplacement). Tiré des `.xdb` 7.0 du gabarit — les noms de géosets du client
    RU sont les mêmes ; les `VisualItem` compilés du client restent à décoder."""
    folder = server_root / "Characters" / spec["dir"]
    template = _read_xml(folder / f"{spec['model']}.(VisCharacterTemplate).xdb")
    dress = _href(template.find("defaultDress")) if template is not None else None
    dress_path = server_root / dress.lstrip("/") if dress else folder / f"{spec['model']}Default.(VisualItem).xdb"
    _, hidden = visual_item_shapes(dress_path)
    shown: dict[str, str | None] = {}
    variations = _href(template.find("variations")) if template is not None else None
    root = _read_xml(server_root / variations.lstrip("/")) if variations else None
    default = root.find("defaultVariation") if root is not None else None
    for child in (list(default) if default is not None else []):
        path = _href(child)
        if path and path.endswith("(VisualItem).xdb"):
            add, _ = visual_item_shapes(server_root / path.lstrip("/"))
            shown.update(add)
    return hidden, shown


def xdb_texture_to_bin(href: str | None) -> str | None:
    if not href:
        return None
    return href.lstrip("/").replace("(Texture).xdb", "(Texture).bin")


def find_template(db: PackDB, cat: PakCatalog, spec: dict) -> int | None:
    """Gabarit du personnage joueur : le `VisCharacterTemplate` nommé comme le modèle dont la
    géométrie vit sous `Characters/<dossier>/`."""
    for off in sorted(db.resources("VisCharacterTemplate")):
        if db.string(off + 0xE8) != spec["model"]:
            continue
        vot = db.ptr(off + 0x90)
        geometry = db.ptr(vot + 0xC0) if vot is not None else None
        name = cat.name(db.binary_ref(geometry)) if geometry is not None else None
        if name and name.startswith(f"Characters/{spec['dir']}/"):
            return off
    return None


def animation_file(cat: PakCatalog, spec: dict, anim: str) -> str | None:
    """Fichier d'une animation du personnage : `<Modèle>.<Nom>` sans égard à la casse."""
    prefix = f"Characters/{spec['dir']}/Animations/{spec['model']}.".lower()
    target = f"{prefix}{anim.lower()}.(skeletalanimation).bin"
    for pak in ("Characters.Mini.pak",):
        for name in cat.names.get(pak, []):
            if name.lower() == target:
                return name
    return None


def build_character(spec: dict, db: PackDB, cat: PakCatalog, bins: BinSource, textures: TexturePool,
                    server_root: Path, wanted: set[str]) -> tuple[bytes, dict, list[str]]:
    exporter = Exporter(textures, CHARACTER_TEXTURE_MAX)
    template = find_template(db, cat, spec)
    if template is None:
        raise ValueError(f"gabarit introuvable : {spec['model']}")
    vot = read_visobject(db, cat, db.ptr(template + 0x90))
    loaded = load_geometry(db, cat, bins, vot.geometry) if vot.geometry is not None else None
    if loaded is None or loaded.skeleton is None:
        raise ValueError(f"géométrie ou squelette illisible : {spec['model']}")
    hidden, shown = character_selection(server_root, spec)
    elements = []
    override: dict[str, str] = {}
    for element in loaded.geo.doc.elements:
        name = element.name
        if name in shown:
            if shown[name]:
                override[name] = xdb_texture_to_bin(shown[name])
        elif name in hidden or not element.material.visible:
            continue
        elif _is_variant(name, shown):
            continue
        if not element.material.texture and name not in override:
            # Emplacement vide (jupes, capes des armures) : sans texture propre ni texture
            # apportée par un objet, le géoset n'est pas dessiné par le client.
            continue
        elements.append(element)
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
            "animations": sorted(durations), "durations": durations, "stats": exporter.stats}
    return glb, meta, exporter.notes


def _is_variant(name: str, shown: dict[str, str | None]) -> bool:
    """Géoset d'une famille à variantes (`hair_3`, `face_7`…) dont une autre variante est
    choisie par la variation par défaut : caché, comme le fait le client."""
    m = re.match(r"^([a-z]+)_(\d+|special|[0-9]+A)$", name)
    if not m:
        return False
    family = m.group(1)
    return any(other != name and other.startswith(family + "_") for other in shown)


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
            info["particles"] = self.cat.name(self.db.binary_ref(vot.particle))
        loaded = load_geometry(self.db, self.cat, self.bins, vot.geometry) if vot.geometry is not None else None
        if loaded is not None:
            geo = loaded.geo
            if geo.orientation != "COMMON":
                info["orientation"] = geo.orientation
            for loc in geo.doc.locators:
                locators[loc.name] = loc
            elements = [e for e in geo.doc.elements if e.material.visible]
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
            s = comp.scale
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
            attached.append({"vot": self.name_of(comp.visobject), "locator": comp.locator})
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


# --- sons --------------------------------------------------------------------------------------

SOUND_BANKS = ("SFX/Spells/Fatality.bsb", "SFX/Spells/Fatality2.bsb")


def export_sounds(names: set[str], bins: BinSource, out_dir: Path, vgmstream: Path, report: list[str]) -> dict[str, str]:
    """Événement FMOD → onde. Les événements des fatalités (`spells/FX/Spells/Fatality/X`)
    n'ont qu'une onde, `fx/spells/fatality/X.wav` dans `Sounds.bev`, rangée sous le nom `X`
    dans les banques `Fatality*.bsb` : on apparie par ce nom."""
    from tools.extract_audio import encode_outputs, fsb_payload_from_bytes, run_vgmstream
    import subprocess
    wanted = {n.split("/")[-1]: n for n in names}
    found: dict[str, str] = {}
    target = out_dir / "sfx"
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for bank in SOUND_BANKS:
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
                if stream not in wanted or stream in found:
                    continue
                base = target / stream
                if not (base.with_suffix(".ogg").exists() and base.with_suffix(".mp3").exists()):
                    wav = Path(tmp) / f"{stream}.wav"
                    run_vgmstream(vgmstream, fsb, sub, wav)
                    encode_outputs(wav, base, "sfx")
                found[stream] = f"sfx/{stream}"
    for short, full in wanted.items():
        if short not in found:
            report.append(f"AVERTISSEMENT : onde introuvable pour l'événement {full}")
    return {wanted[k]: v for k, v in found.items()}


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
        report: list[str] | None = None) -> dict:
    report = report if report is not None else []
    server_root = Path(manifest["server_root"])
    db = open_pack(client)
    cat = open_catalog(db, client)
    packs = client / "data" / "Packs"
    bins = BinSource([], [str(packs / p) for p in sorted(cat.names)])
    textures = TexturePool(db, cat, bins, out_dir)
    schema = {int(k): v for k, v in manifest.get("animation_enum", {}).items()}
    anim_names = animation_names(db, schema or None)
    fatalities = read_fatalities(db)
    by_type = {f["type"]: f for f in manifest["fatalities"]}

    # Animations demandées par les scripts (noms de fichiers : initiale en majuscule).
    wanted: set[str] = set()
    for fd in fatalities:
        collect_animations(fd.offender, anim_names, wanted)

    index_path = out_dir / "fatalities.json"
    previous = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else {}
    prev_chars = {c["id"]: c for c in previous.get("characters", [])}

    chars: list[dict] = []
    for spec in manifest["characters"]:
        if not characters or (only and spec["id"] not in only):
            if spec["id"] in prev_chars:
                chars.append(prev_chars[spec["id"]])
            continue
        try:
            glb, meta, notes = build_character(spec, db, cat, bins, textures, server_root, wanted)
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
        build = FxBuild(Exporter(textures, FX_TEXTURE_MAX), db, cat, bins)
        roots: set[int] = set()
        collect_vots(fd.offender, roots)
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
            timelines[char["id"]] = timeline_json(tl, build, anim_names)
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
    out_dir.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"textures : {textures.bytes_written / 1024:.0f} Kio écrits")
    return index


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export des fatalités (personnages, effets, chronologies, sons)")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--client", type=Path, default=None)
    parser.add_argument("--only", action="append")
    parser.add_argument("--only-fx", action="append")
    parser.add_argument("--no-characters", action="store_true")
    parser.add_argument("--no-sounds", action="store_true")
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    client = Path(args.client or os.environ.get("ALLODS_RU_CLIENT_DIR") or manifest["client_root"])
    report: list[str] = []
    run(manifest, args.out, client, args.only, args.only_fx, not args.no_characters, not args.no_sounds, report)
    for line in report:
        print(line, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
