#!/usr/bin/env python3
"""Export glTF des fatalités d'Allods Online (écran « Fatality Showcases »).

Une fatalité, dans le jeu, c'est d'abord l'animation de mort **de la cible**
(`Characters/<race>/Animations/<Modèle>.DeathFatality<Classe>.(SkeletalAnimation).bin`)
et un décor d'effet posé à ses pieds (`Spells/FX/Spells/Fatality/Fatality<Classe>…`,
géométries skinnées animées). Cet outil lit le client RU (`.bin` dans les paks) et
l'arbre serveur 7.0 (`.xdb` : déclarations de sommets, géosets, matériaux) puis écrit,
dans `public/game/fatalities/` (non versionné, comme le reste de `public/game/`) :

* `characters/<id>.glb` — le personnage de chaque race/sexe en tenue par défaut (peau,
  visage, coiffure et ornements de la variation par défaut du jeu), avec **toutes** ses
  animations `DeathFatality*` comme clips glTF (nom du clip = nom de l'animation) ;
* `fx/<id>.glb` — les objets 3D de l'effet de chaque fatalité, chacun avec son squelette
  et son animation propre ;
* `fatalities.json` — l'index : personnages, fatalités (libellés bilingues, animation
  de la cible, fichiers d'effets, approximations connues).

Formats : voir l'en-tête de `tools/extract_menu_scene.py`, dont ce module réutilise le
décodage. Deux écarts avec les scènes de menu :

* la géométrie des personnages du client RU (17.x) a été réexportée depuis la 7.0 : le
  vertex buffer a changé mais **le découpage de l'index buffer en géosets est conservé**
  (vérifié : chaque plage d'indices pointe toujours vers une plage de sommets contiguë
  de la même taille). On lit donc les plages d'indices du xdb 7.0 et on laisse les
  indices désigner les sommets RU ; le nombre de sommets vient de la taille du tampon ;
* les effets ajoutés après la 7.0 n'ont pas de xdb : stride déduit de la taille du tampon
  (36 = position, uv, normale, couleur, poids, indices ; 32 = sans couleur), une seule
  primitive, texture homonyme (ou forcée par le manifeste). Les dimensions d'une texture
  sans xdb se déduisent de sa chaîne de mipmaps (la plus petite dimension vaut
  `4 << dernier niveau`).

Usage : python3 tools/extract_fatalities.py [--only aed-female] [--only-fx warrior]
                                            [--check-dir DIR] [--client /mnt/h/…/AllodsRU]
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import struct
import sys
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.extract_menu_scene import (  # noqa: E402
    BLOCK_BYTES,
    FOURCC,
    BinSource,
    GeometryDoc,
    GltfBuilder,
    MaterialSpec,
    Skeleton,
    SkeletalAnimation,
    TextureLibrary,
    VertexLayout,
    decode_vertex_buffer,
    parse_geometry_xdb,
    parse_skeletal_animation,
    parse_skeleton,
    read_chunks,
    render_glb,
    rest_local,
    rest_world_matrices,
    skin_attributes,
    validate_glb,
)
from tools.uitexture import build_dds, smoothness_score  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE / "fatalities_manifest.json"
DEFAULT_OUT = HERE.parent / "public" / "game" / "fatalities"

# Dispositions de sommets connues des effets sans xdb, par stride.
KNOWN_LAYOUTS = {
    36: VertexLayout(stride=36, position=0, texcoord0=12, normal=20, color=24, weights=28, indices=32),
    32: VertexLayout(stride=32, position=0, texcoord0=12, normal=20, weights=24, indices=28),
    28: VertexLayout(stride=28, position=0, texcoord0=12, normal=20, color=24),
    24: VertexLayout(stride=24, position=0, texcoord0=12, normal=20),
    20: VertexLayout(stride=20, position=0, texcoord0=12),
}


# --- textures sans xdb -----------------------------------------------------------------------

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
        blocks_finest = len(mips[finest]) // block
        blocks0 = blocks_finest * (4 ** finest)
        short = 4 << last
        long_side = blocks0 * 16 // short
        if long_side * short != blocks0 * 16 or long_side < short:
            continue
        for w, h in ((long_side, short), (short, long_side)):
            if (w, h) not in [(c[1], c[2]) for c in out]:
                out.append((fmt, w, h))
    return out


class RuTextureLibrary(TextureLibrary):
    """`TextureLibrary` qui se passe du xdb quand le client seul connaît la texture."""

    def _decode(self, key: str) -> tuple[bytes, int, int] | None:
        # Le xdb 7.0 fait foi tant qu'il décrit encore les octets du client RU ; sinon
        # (format changé entre-temps, p. ex. la peau du Kanien passée de DXT5 à DXT1) on
        # se rabat sur la chaîne de mipmaps, qui suffit à retrouver dimensions et format.
        xdb = self.server_root / key.lstrip("/")
        if xdb.is_file():
            result = super()._decode(key)
            if result is not None:
                return result
        base = key[:-4] if key.endswith(".xdb") else key
        mips: dict[int, bytes] = {}
        for suffix in (".hi.bin", ".bin"):
            data = self.source.get(base + suffix)
            if data:
                try:
                    mips.update(read_chunks(data))
                except zlib.error:
                    pass
        best: tuple[float, bytes, int, int] | None = None
        for fmt, width, height in infer_texture_dims(mips):
            block = BLOCK_BYTES[fmt]
            for level in sorted(mips):
                w, h = max(1, width >> level), max(1, height >> level)
                if max(w, h) > self.max_size and level < max(mips):
                    continue
                need = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * block
                payload = mips[level]
                if len(payload) < need:
                    continue
                try:
                    img = Image.open(io.BytesIO(build_dds(w, h, FOURCC[fmt], payload[:need])))
                    img.load()
                    img = img.convert("RGBA")
                except Exception:  # pragma: no cover - dépend de Pillow/DDS
                    break
                score = smoothness_score(img) + (0.0 if w >= h else 1e-3)
                if best is None or score < best[0]:
                    buf = io.BytesIO()
                    img.save(buf, format="PNG", optimize=True)
                    best = (score, buf.getvalue(), w, h)
                break
        return None if best is None else (best[1], best[2], best[3])


# --- déclarations de sommets sans xdb ----------------------------------------------------------

def guess_layout(vb_size: int, index_max: int) -> VertexLayout | None:
    """Stride d'un vertex buffer sans xdb : le plus grand stride connu qui tombe juste et couvre
    tous les indices référencés (`index_max + 1` sommets au moins)."""
    for stride in sorted(KNOWN_LAYOUTS, reverse=True):
        if vb_size % stride == 0 and vb_size // stride > index_max:
            return KNOWN_LAYOUTS[stride]
    return None


# --- personnages ------------------------------------------------------------------------------

@dataclass
class Geoset:
    """Un géoset visible : l'élément du xdb et, le cas échéant, sa texture de remplacement."""
    name: str
    texture: str | None
    ib0: int
    ib1: int
    blend: str = "BLEND_EFFECT_ALPHA"
    transparent: bool = False
    alpha: float = 1.0


def _href_path(node: ET.Element | None) -> str | None:
    if node is None:
        return None
    href = node.get("href")
    return href.split("#")[0] if href else None


def _read_xml(path: Path) -> ET.Element | None:
    try:
        return ET.fromstring(path.read_text(errors="replace"))
    except (OSError, ET.ParseError):
        return None


def default_variation_items(server_root: Path, character_dir: str,
                            template_root: ET.Element | None) -> list[Path]:
    """Chemins des `VisualItem` de la variation par défaut (coiffure, visage, ornements)."""
    if template_root is None:
        return []
    variations = _href_path(template_root.find("variations"))
    if not variations:
        return []
    root = _read_xml(server_root / variations.lstrip("/"))
    if root is None:
        return []
    default = root.find("defaultVariation")
    if default is None:
        return []
    out: list[Path] = []
    for child in default:
        path = _href_path(child)
        if path and path.endswith("(VisualItem).xdb"):
            out.append(server_root / path.lstrip("/"))
    return out


def visual_item_shapes(path: Path) -> tuple[dict[str, str | None], set[str]]:
    """`{géoset: texture de remplacement}` affichés par un VisualItem, et ses géosets cachés."""
    root = _read_xml(path)
    shown: dict[str, str | None] = {}
    hidden: set[str] = set()
    if root is None:
        return shown, hidden
    for item in root.iter("Item"):
        shape = item.findtext("shapeName")
        if shape:
            shown[shape.strip()] = _href_path(item.find("replacement"))
    for node in root.findall("./hiddenGeosets//Item"):
        if node.text and node.text.strip():
            hidden.add(node.text.strip())
    return shown, hidden


def character_geosets(server_root: Path, spec: dict, doc: GeometryDoc) -> list[Geoset]:
    """Géosets à afficher pour la tenue par défaut : ceux que `<Modèle>Default.(VisualItem)`
    ne cache pas, plus ceux qu'ajoute la variation par défaut (avec leurs textures)."""
    folder = server_root / "Characters" / spec["dir"]
    template = _read_xml(folder / f"{spec['model']}.(VisCharacterTemplate).xdb")
    hidden: set[str] = set()
    shown: dict[str, str | None] = {}
    default_dress = _href_path(template.find("defaultDress")) if template is not None else None
    dress_path = server_root / default_dress.lstrip("/") if default_dress else folder / f"{spec['model']}Default.(VisualItem).xdb"
    _, hidden = visual_item_shapes(dress_path)
    for item in default_variation_items(server_root, spec["dir"], template):
        add, _ = visual_item_shapes(item)
        shown.update(add)
    out: list[Geoset] = []
    for element in doc.elements:
        name = element.name
        if name in shown:
            texture = shown[name] or element.material.texture
        elif name in hidden or not element.material.visible:
            continue
        else:
            texture = element.material.texture
        out.append(Geoset(name, texture, element.ib0, element.ib1, element.material.blend,
                          element.material.transparent, element.material.alpha))
    return out


def character_scale(server_root: Path, spec: dict) -> float:
    root = _read_xml(server_root / "Characters" / spec["dir"] / f"{spec['model']}.(VisObjectTemplate).xdb")
    if root is None:
        return 1.0
    try:
        return float(root.findtext("scale") or "1")
    except ValueError:
        return 1.0


# --- assemblage glTF --------------------------------------------------------------------------

@dataclass
class Exporter:
    server_root: Path
    source: BinSource
    max_texture: int = 1024
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.gltf = GltfBuilder()
        self.gltf.json["asset"]["generator"] = "allodex/extract_fatalities"
        self.textures = RuTextureLibrary(self.source, self.server_root, self.max_texture)
        self.texture_index: dict[str, int | None] = {}
        self.material_index: dict[tuple, int] = {}
        self.stats = {"triangles": 0, "textures": 0, "animations": 0, "objects": 0}

    # -- ressources

    def texture(self, href: str | None) -> int | None:
        if not href:
            return None
        key = href.split("#")[0]
        if key not in self.texture_index:
            png = self.textures.png(key)
            if png is None:
                self.texture_index[key] = None
                self.notes.append(f"texture illisible : {key}")
            else:
                data, _, _ = png
                self.texture_index[key] = self.gltf.add_image(data, Path(key).name)
                self.stats["textures"] += 1
        return self.texture_index[key]

    def material(self, name: str, texture_href: str | None, blend: str, transparent: bool,
                 alpha: float = 1.0) -> int:
        # Le canal alpha des textures de peau est un masque (spéculaire, sous-vêtements),
        # pas une transparence : un matériau non `transparent` est opaque, jamais découpé.
        additive = blend == "BLEND_EFFECT_ADD" and transparent
        tex = self.texture(texture_href)
        key = (name, tex, additive, transparent, round(alpha, 4))
        if key not in self.material_index:
            alpha_mode = "BLEND" if (additive or transparent) else "OPAQUE"
            self.material_index[key] = self.gltf.add_material(name, tex, alpha_mode, True, additive, alpha)
        return self.material_index[key]

    # -- squelette et animations

    def emit_skeleton(self, skeleton: Skeleton, prefix: str) -> list[int]:
        """Un nœud par articulation, à la pose de bind du squelette (aucune animation ne fait
        foi : plusieurs clips se partagent le squelette)."""
        nodes: list[int] = []
        for i, name in enumerate(skeleton.names):
            t, q = rest_local(skeleton, None, i)
            nodes.append(self.gltf.add_node({"name": f"{prefix}/{name}",
                                             "translation": [float(v) for v in t],
                                             "rotation": [float(v) for v in q]}))
        for i in range(len(skeleton)):
            parent = skeleton.parents[i]
            if 0 <= parent < len(skeleton) and parent != i:
                self.gltf.json["nodes"][nodes[parent]].setdefault("children", []).append(nodes[i])
        return nodes

    def emit_animation(self, name: str, skeleton: Skeleton, nodes: list[int],
                       animation: SkeletalAnimation) -> bool:
        known = [t for t in animation.tracks if t.name in skeleton.names]
        moving = [t for t in known if t.animated]
        if animation.frames <= 0 or not known:
            return False
        if moving:
            times = np.arange(animation.frames, dtype=np.float32) / float(animation.fps)
            tracks = moving
        else:
            # Pose figée (aucune articulation animée) : deux clés identiques sur toute la
            # durée, pour chaque articulation — c'est le cas de `DeathFatality`, la pose que
            # les fatalités de la boutique imposent à leur cible.
            times = np.array([0.0, max(animation.frames - 1, 1) / float(animation.fps)], np.float32)
            tracks = known
        acc_time = self.gltf.add_accessor(times, "SCALAR", "f32", minmax=True)
        samplers: list[dict] = []
        channels: list[dict] = []
        for track in tracks:
            node = nodes[skeleton.names.index(track.name)]
            translation = track.translation.astype(np.float32)
            rotation = track.rotation.astype(np.float32)
            if len(translation) != len(times):
                translation = np.repeat(translation[:1], len(times), axis=0)
                rotation = np.repeat(rotation[:1], len(times), axis=0)
            acc_t = self.gltf.add_accessor(translation, "VEC3", "f32")
            samplers.append({"input": acc_time, "output": acc_t, "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": node, "path": "translation"}})
            acc_r = self.gltf.add_accessor(rotation, "VEC4", "f32")
            samplers.append({"input": acc_time, "output": acc_r, "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": node, "path": "rotation"}})
        self.gltf.json["animations"].append({"name": name, "samplers": samplers, "channels": channels})
        self.stats["animations"] += 1
        if animation.undecoded:
            self.notes.append(f"{name} : {len(animation.undecoded)} articulation(s) figée(s) ({', '.join(animation.undecoded[:4])}…)")
        return True

    def load_animation(self, rel: str, skeleton: Skeleton, span: float) -> SkeletalAnimation | None:
        blob = self.source.get(rel)
        if blob is None:
            return None
        payload = read_chunks(blob).get(0)
        if not payload:
            return None
        try:
            return parse_skeletal_animation(payload, skeleton, span)
        except (struct.error, ValueError, IndexError):
            self.notes.append(f"animation illisible : {rel}")
            return None

    # -- maillage

    def emit_mesh(self, name: str, vertices: dict[str, np.ndarray], indices: np.ndarray,
                  geosets: list[Geoset], skeleton: Skeleton | None,
                  vertex_colors: bool) -> tuple[int | None, dict]:
        position = vertices["position"].astype(np.float32)
        uv = vertices.get("texcoord0", np.zeros((len(position), 2), np.float32)).astype(np.float32)
        color = vertices.get("color") if vertex_colors else None
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
        if skeleton is not None and "indices" in vertices and "weights" in vertices:
            joints, weights = skin_attributes(vertices, len(skeleton))
            attributes["JOINTS_0"] = self.gltf.add_accessor(joints, "VEC4", "u8", target=34962)
            attributes["WEIGHTS_0"] = self.gltf.add_accessor(weights, "VEC4", "u8", normalized=True, target=34962)
        primitives = []
        for geoset in geosets:
            tri = indices[geoset.ib0:geoset.ib1]
            if tri.size < 3:
                continue
            self.stats["triangles"] += tri.size // 3
            acc_idx = self.gltf.add_accessor(tri.astype(np.uint32), "SCALAR", "u32", target=34963)
            primitives.append({"attributes": attributes, "indices": acc_idx, "mode": 4,
                               "material": self.material(geoset.name, geoset.texture, geoset.blend,
                                                         geoset.transparent, geoset.alpha),
                               "extras": {"element": geoset.name}})
        if not primitives:
            return None, attributes
        self.gltf.json["meshes"].append({"name": name, "primitives": primitives})
        return len(self.gltf.json["meshes"]) - 1, attributes

    def emit_skinned_object(self, name: str, vertices: dict[str, np.ndarray], indices: np.ndarray,
                            geosets: list[Geoset], skeleton: Skeleton | None,
                            animations: dict[str, SkeletalAnimation], scale: float = 1.0,
                            vertex_colors: bool = False) -> int | None:
        mesh_index, attributes = self.emit_mesh(name, vertices, indices, geosets, skeleton, vertex_colors)
        if mesh_index is None:
            return None
        self.stats["objects"] += 1
        children: list[int] = []
        mesh_node: dict = {"name": f"{name}_mesh", "mesh": mesh_index}
        if skeleton is not None and "JOINTS_0" in attributes:
            joint_nodes = self.emit_skeleton(skeleton, name)
            world = rest_world_matrices(skeleton, None)
            inverse = np.zeros((len(skeleton), 16), np.float32)
            for i in range(len(skeleton)):
                inverse[i] = np.linalg.inv(world[i]).T.reshape(-1)
            self.gltf.json["skins"].append({
                "name": f"{name}_skin",
                "inverseBindMatrices": self.gltf.add_accessor(inverse, "MAT4", "f32"),
                "joints": joint_nodes,
                "skeleton": joint_nodes[skeleton.topological_order()[0]],
            })
            mesh_node["skin"] = len(self.gltf.json["skins"]) - 1
            children.extend(joint_nodes[i] for i in range(len(skeleton))
                            if not (0 <= skeleton.parents[i] < len(skeleton)))
            for clip_name, animation in animations.items():
                self.emit_animation(clip_name, skeleton, joint_nodes, animation)
        children.append(self.gltf.add_node(mesh_node))
        node: dict = {"name": name, "children": children}
        if abs(scale - 1.0) > 1e-9:
            node["scale"] = [float(scale)] * 3
        return self.gltf.add_node(node)

    def finish(self, roots: list[int]) -> bytes:
        # Repère main gauche du jeu → main droite de glTF : nœud miroir, comme les scènes de menu.
        mirror = self.gltf.add_node({"name": "scene", "scale": [-1.0, 1.0, 1.0], "children": roots})
        self.gltf.json["scenes"][0]["nodes"].append(mirror)
        glb = self.gltf.to_glb()
        validate_glb(glb)
        return glb


# --- personnages ------------------------------------------------------------------------------

def build_character(spec: dict, server_root: Path, source: BinSource, max_texture: int,
                    only_animations: re.Pattern[str] | None = None) -> tuple[bytes, dict, list[str]]:
    exporter = Exporter(server_root, source, max_texture)
    folder = f"Characters/{spec['dir']}"
    xdb = server_root / folder / f"{spec['model']}.(Geometry).xdb"
    if not xdb.is_file():
        raise FileNotFoundError(f"xdb absent : {xdb}")
    doc = parse_geometry_xdb(xdb.read_text(errors="replace"))
    data = source.get(f"{folder}/{spec['model']}.(Geometry).bin")
    if data is None:
        raise FileNotFoundError(f"géométrie absente du client : {folder}/{spec['model']}.(Geometry).bin")
    chunks = read_chunks(data)
    vb, ib = chunks.get(0), chunks.get(1)
    if vb is None or ib is None or not doc.layouts:
        raise ValueError(f"tampons ou déclaration absents : {spec['model']}")
    layout = doc.layouts[0]
    count = len(vb) // layout.stride
    if len(vb) % layout.stride:
        raise ValueError(f"vertex buffer de {len(vb)} octets non multiple du stride {layout.stride}")
    vertices = decode_vertex_buffer(vb, layout, count)
    indices = np.frombuffer(ib, "<u2").astype(np.uint32)
    if doc.skeleton_id is None or doc.skeleton_id not in chunks:
        raise ValueError(f"squelette absent : {spec['model']}")
    skeleton = parse_skeleton(chunks[doc.skeleton_id])
    geosets = character_geosets(server_root, spec, doc)
    last = len(indices)
    for geoset in geosets:
        if geoset.ib1 > last or geoset.ib0 >= geoset.ib1:
            raise ValueError(f"géoset {geoset.name} hors de l'index buffer RU")
        tri = indices[geoset.ib0:geoset.ib1]
        if tri.max() >= count:
            raise ValueError(f"géoset {geoset.name} référence un sommet inexistant")
    span = float(np.max(doc.aabb[1]) * 4.0) if doc.aabb is not None else 0.0
    prefix = f"{folder}/Animations/{spec['model']}.DeathFatality"
    names = sorted(n for n in source.names() if n.startswith(prefix) and n.endswith(".(SkeletalAnimation).bin"))
    animations: dict[str, SkeletalAnimation] = {}
    for rel in names:
        clip = rel[len(f"{folder}/Animations/{spec['model']}."):-len(".(SkeletalAnimation).bin")]
        if only_animations and not only_animations.search(clip):
            continue
        animation = exporter.load_animation(rel, skeleton, span)
        if animation is not None:
            animations[clip] = animation
    if not animations:
        exporter.notes.append(f"{spec['id']} : aucune animation DeathFatality* trouvée")
    scale = character_scale(server_root, spec)
    root = exporter.emit_skinned_object(spec["model"], vertices, indices, geosets, skeleton, animations, scale)
    if root is None:
        raise ValueError(f"aucun géoset visible : {spec['model']}")
    glb = exporter.finish([root])
    clips = [name for name in animations if any(a["name"] == name for a in exporter.gltf.json.get("animations", []))]
    durations = {name: round(animations[name].frames / float(animations[name].fps), 3) for name in clips}
    meta = {"id": spec["id"], "model": spec["model"], "scale": scale, "geosets": [g.name for g in geosets],
            "animations": clips, "durations": durations, "height": float(vertices["position"][:, 2].max() * scale),
            "stats": exporter.stats}
    return glb, meta, exporter.notes


# --- effets -----------------------------------------------------------------------------------

FX_DIRS = ("Spells/FX/Spells/Fatality", "Spells/FX/Spells", "Spells/FX/Mobs", "Spells/FX/Armors",
           "Items/ObjectComponents/Wings")


def find_fx(source: BinSource, name: str) -> str | None:
    """Dossier du client où vit `<name>.(Geometry).bin`."""
    for folder in FX_DIRS:
        if source.get(f"{folder}/{name}.(Geometry).bin") is not None:
            return folder
    return None


def build_fx(fatality: dict, server_root: Path, source: BinSource,
             max_texture: int) -> tuple[bytes | None, dict, list[str]]:
    exporter = Exporter(server_root, source, max_texture)
    roots: list[int] = []
    objects: list[dict] = []
    for entry in fatality.get("fx", []):
        spec = {"name": entry} if isinstance(entry, str) else dict(entry)
        name = spec["name"]
        folder = find_fx(source, name)
        if folder is None:
            exporter.notes.append(f"{fatality['id']} : géométrie absente du client : {name}")
            continue
        chunks = read_chunks(source.get(f"{folder}/{name}.(Geometry).bin") or b"")
        vb, ib = chunks.get(0), chunks.get(1)
        if vb is None or ib is None:
            exporter.notes.append(f"{fatality['id']} : tampons absents : {name}")
            continue
        indices = np.frombuffer(ib, "<u2").astype(np.uint32)
        xdb = server_root / folder / f"{name}.(Geometry).xdb"
        approx = not xdb.is_file()
        doc = None if approx else parse_geometry_xdb(xdb.read_text(errors="replace"))
        if doc is not None and doc.layouts and doc.vertex_buffer_size == len(vb) and doc.index_buffer_size == len(ib):
            layout = doc.layouts[0]
            geosets = [Geoset(e.name, e.material.texture, e.ib0, e.ib1, e.material.blend,
                              e.material.transparent, e.material.alpha)
                       for e in doc.elements if e.material.visible]
            skeleton_id = doc.skeleton_id
        else:
            if doc is not None:
                exporter.notes.append(f"{fatality['id']} : xdb 7.0 de {name} périmé (tailles différentes), décodage heuristique")
                approx = True
            layout = guess_layout(len(vb), int(indices.max()) if indices.size else 0)
            if layout is None:
                exporter.notes.append(f"{fatality['id']} : stride indéterminable : {name}")
                continue
            texture = spec.get("texture")
            if texture is None and source.get(f"{folder}/{name}.(Texture).bin") is not None:
                texture = f"/{folder}/{name}"
            geosets = [Geoset(name, f"{texture}.(Texture).xdb" if texture else None, 0, len(indices),
                              "BLEND_EFFECT_ALPHA", True)]
            skeleton_id = 2 if 2 in chunks else None
        count = len(vb) // layout.stride
        vertices = decode_vertex_buffer(vb, layout, count)
        skeleton = None
        if skeleton_id is not None and skeleton_id in chunks:
            try:
                skeleton = parse_skeleton(chunks[skeleton_id])
            except (struct.error, ValueError):
                exporter.notes.append(f"{fatality['id']} : squelette illisible : {name}")
        animations: dict[str, SkeletalAnimation] = {}
        if skeleton is not None:
            stems = [name] + list(spec.get("animations", []))
            span = float(np.max(np.abs(vertices["position"])) * 8.0) if len(vertices["position"]) else 0.0
            for stem in stems:
                animation = exporter.load_animation(f"{folder}/{stem}.(SkeletalAnimation).bin", skeleton, span)
                if animation is not None:
                    animations[stem] = animation
        root = exporter.emit_skinned_object(name, vertices, indices, geosets, skeleton, animations,
                                            float(spec.get("scale", 1.0)), vertex_colors=layout.color is not None)
        if root is None:
            exporter.notes.append(f"{fatality['id']} : rien à afficher : {name}")
            continue
        roots.append(root)
        objects.append({"name": name, "approx": approx, "animations": list(animations),
                        "duration": max([a.frames / float(a.fps) for a in animations.values()] + [0.0])})
    if not roots:
        return None, {"objects": []}, exporter.notes
    glb = exporter.finish(roots)
    return glb, {"objects": objects, "stats": exporter.stats}, exporter.notes


# --- index et CLI ------------------------------------------------------------------------------

def check_meta(height: float) -> dict:
    """Caméra de la planche de contrôle : de face, à hauteur de poitrine."""
    h = max(height, 1.0)
    return {"up": [0, 0, 1], "background": "#1a1d26",
            "camera": {"position": [0.0, -h * 2.6, h * 0.55], "target": [0.0, 0.0, h * 0.45], "fov": 40}}


def _node_local(node: dict) -> np.ndarray:
    m = np.eye(4)
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    m[:3, :3] = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]) * np.array(node.get("scale", [1, 1, 1]))
    m[:3, 3] = node.get("translation", [0, 0, 0])
    return m


def bake_pose(glb: bytes, time: float, clip: str | None = None) -> bytes:
    """Recopie le `.glb` avec les sommets skinnés à l'instant `time` du clip demandé (le
    premier sinon) et sans skin : le rasteriseur de contrôle, qui ignore les skins, montre
    alors la pose. Réservé aux planches de contrôle."""
    length, = struct.unpack_from("<I", glb, 12)
    doc = json.loads(glb[20:20 + length])
    blob = bytearray(glb[28 + length:])
    views = doc["bufferViews"]

    def read(index: int) -> np.ndarray:
        acc = doc["accessors"][index]
        view = views[acc["bufferView"]]
        start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[acc["type"]]
        dtype = {5126: "<f4", 5121: "u1", 5123: "<u2", 5125: "<u4"}[acc["componentType"]]
        return np.frombuffer(bytes(blob), dtype, count=acc["count"] * n, offset=start).reshape(acc["count"], n)

    posed: dict[int, dict] = {}
    animations = doc.get("animations", [])
    chosen = [a for a in animations if clip is None or a["name"] == clip][:1] if animations else []
    for animation in chosen:
        for channel in animation["channels"]:
            sampler = animation["samplers"][channel["sampler"]]
            times = read(sampler["input"]).reshape(-1)
            values = read(sampler["output"])
            t = time % max(float(times[-1]), 1e-6) if times[-1] > 0 else 0.0
            i = min(int(np.searchsorted(times, t)), len(values) - 1)
            posed.setdefault(channel["target"]["node"], {})[channel["target"]["path"]] = [float(v) for v in values[i]]
    world: dict[int, np.ndarray] = {}

    def walk(index: int, parent: np.ndarray) -> None:
        node = {**doc["nodes"][index], **posed.get(index, {})}
        world[index] = parent @ _node_local(node)
        for child in node.get("children", []):
            walk(child, world[index])

    for root in doc["scenes"][0]["nodes"]:
        walk(root, np.eye(4))
    for index, node in enumerate(doc["nodes"]):
        if "skin" not in node or "mesh" not in node:
            continue
        skin = doc["skins"][node["skin"]]
        ibm = read(skin["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1)
        palette = np.array([world[j] for j in skin["joints"]]) @ ibm
        back = np.linalg.inv(world[index])
        done: set[int] = set()
        for prim in doc["meshes"][node["mesh"]]["primitives"]:
            attrs = prim["attributes"]
            if attrs["POSITION"] in done or "JOINTS_0" not in attrs:
                continue
            done.add(attrs["POSITION"])
            pos = read(attrs["POSITION"]).astype(np.float64)
            joints = read(attrs["JOINTS_0"]).astype(np.int64)
            weights = read(attrs["WEIGHTS_0"]).astype(np.float64)
            if doc["accessors"][attrs["WEIGHTS_0"]]["componentType"] == 5121:
                weights /= 255.0
            homogeneous = np.concatenate([pos, np.ones((len(pos), 1))], axis=1)
            out = np.zeros((len(pos), 4))
            for k in range(4):
                out += weights[:, k, None] * np.einsum("nij,nj->ni", palette[joints[:, k]], homogeneous)
            local = (back @ out.T).T[:, :3].astype("<f4")
            acc = doc["accessors"][attrs["POSITION"]]
            view = views[acc["bufferView"]]
            start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
            blob[start:start + local.nbytes] = local.tobytes()
        del node["skin"]
    doc.pop("skins", None)
    doc.pop("animations", None)
    payload = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    payload += b" " * ((4 - len(payload) % 4) % 4)
    out = bytearray(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(payload) + 8 + len(blob)))
    out += struct.pack("<II", len(payload), 0x4E4F534A) + payload
    out += struct.pack("<II", len(blob), 0x004E4942) + bytes(blob)
    return bytes(out)


def write_check(glb: bytes, meta: dict, path: Path, times: tuple[float, ...] = (0.0, 2.0, 5.0),
                clip: str | None = None) -> None:
    frames = [render_glb(bake_pose(glb, t, clip), meta, width=480, height=540) for t in times]
    sheet = Image.new("RGB", (frames[0].width * len(frames), frames[0].height))
    for i, frame in enumerate(frames):
        sheet.paste(frame, (i * frame.width, 0))
    sheet.save(path)


def run(manifest: dict, out_dir: Path, only: list[str] | None = None, only_fx: list[str] | None = None,
        check_dir: Path | None = None, report: list[str] | None = None,
        client_root: Path | None = None, animations: str | None = None) -> dict:
    report = report if report is not None else []
    server_root = Path(manifest["server_root"])
    client = Path(client_root or os.environ.get("ALLODS_RU_CLIENT_DIR") or manifest["client_root"])
    source = BinSource([], [str(client / pattern) for pattern in manifest["pak_globs"]])
    if not (client / "data" / "Packs").is_dir():
        report.append(f"AVERTISSEMENT : client absent : {client}")
    if not server_root.is_dir():
        report.append(f"AVERTISSEMENT : arbre serveur absent : {server_root}")
    previous = {}
    index_path = out_dir / "fatalities.json"
    if index_path.is_file():
        try:
            previous = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = {}
    prev_chars = {c["id"]: c for c in previous.get("characters", [])}
    prev_fx = {f["id"]: f for f in previous.get("fatalities", [])}
    pattern = re.compile(animations) if animations else None

    characters: list[dict] = []
    for spec in manifest["characters"]:
        if (only and spec["id"] not in only) or only_fx:
            if spec["id"] in prev_chars:
                characters.append(prev_chars[spec["id"]])
            continue
        try:
            glb, meta, notes = build_character(spec, server_root, source, int(manifest.get("max_texture", 1024)), pattern)
        except (FileNotFoundError, ValueError, struct.error) as error:
            report.append(f"AVERTISSEMENT : {spec['id']} — {error}")
            if spec["id"] in prev_chars:
                characters.append(prev_chars[spec["id"]])
            continue
        target = out_dir / "characters"
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{spec['id']}.glb").write_bytes(glb)
        for note in notes:
            report.append(f"AVERTISSEMENT : {spec['id']} — {note}")
        stats = meta["stats"]
        print(f"{spec['id']:>18}  characters/{spec['id']}.glb  {len(glb) / 1024:.0f} Kio  "
              f"{stats['triangles']} triangles, {stats['textures']} textures, {stats['animations']} animations")
        if check_dir is not None:
            check_dir.mkdir(parents=True, exist_ok=True)
            clip = next((c for c in meta["animations"] if c.endswith("Warrior")), None)
            write_check(glb, check_meta(meta["height"]), check_dir / f"fatality-{spec['id']}.png", clip=clip)
        characters.append({"id": spec["id"], "race": spec["race"], "sex": spec["sex"],
                           "glb": f"characters/{spec['id']}.glb", "scale": meta["scale"], "height": round(meta["height"], 3),
                           "animations": meta["animations"], "durations": meta["durations"]})

    fatalities: list[dict] = []
    for fatality in manifest["fatalities"]:
        entry = {"id": fatality["id"], "kind": fatality["kind"], "label": fatality["label"],
                 "victim": fatality["victim"]}
        if "note" in fatality:
            entry["note"] = fatality["note"]
        if (only_fx and fatality["id"] not in only_fx) or (only and not only_fx):
            if fatality["id"] in prev_fx:
                entry.update({k: v for k, v in prev_fx[fatality["id"]].items() if k in ("fx", "fxObjects", "approx")})
            fatalities.append(entry)
            continue
        glb, meta, notes = build_fx(fatality, server_root, source, int(manifest.get("max_texture", 1024)))
        for note in notes:
            report.append(f"AVERTISSEMENT : {note}")
        if glb is not None:
            target = out_dir / "fx"
            target.mkdir(parents=True, exist_ok=True)
            (target / f"{fatality['id']}.glb").write_bytes(glb)
            entry["fx"] = f"fx/{fatality['id']}.glb"
            entry["fxObjects"] = meta["objects"]
            entry["approx"] = any(o["approx"] for o in meta["objects"])
            stats = meta["stats"]
            print(f"{fatality['id']:>18}  fx/{fatality['id']}.glb  {len(glb) / 1024:.0f} Kio  "
                  f"{stats['triangles']} triangles, {stats['textures']} textures, {stats['animations']} animations"
                  f"{'  (approx.)' if entry['approx'] else ''}")
            if check_dir is not None:
                check_dir.mkdir(parents=True, exist_ok=True)
                write_check(glb, check_meta(2.0), check_dir / f"fatality-fx-{fatality['id']}.png", (0.0, 1.5, 4.0))
        fatalities.append(entry)

    index = {"races": manifest["races"], "characters": characters, "fatalities": fatalities}
    out_dir.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export glTF des fatalités (personnages + effets)")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--client", type=Path, default=None, help="racine du client RU (sinon ALLODS_RU_CLIENT_DIR ou le manifeste)")
    parser.add_argument("--only", action="append", help="limiter à un personnage (répétable)")
    parser.add_argument("--only-fx", action="append", help="limiter aux effets d'une fatalité (répétable)")
    parser.add_argument("--animations", default=None, help="regex : n'exporter que les animations qui la vérifient")
    parser.add_argument("--check-dir", type=Path, default=None, help="planches de contrôle (rendu logiciel)")
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    report: list[str] = []
    run(manifest, args.out, args.only, args.only_fx, args.check_dir, report, args.client, args.animations)
    for line in report:
        print(line, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
