"""Export glTF des scènes de menu animées d'Allods Online (4.0 → 8.0).

Chaque version du jeu possède un décor de menu en 3D (`World/MainMenu/Animated_Background*`) :
des calques de géométrie peinte, des navires, des drapeaux, des pierres flottantes. Cet outil
lit l'arbre serveur décompressé (les `.xdb`, du XML) et les binaires `.bin` (dans les paks des
clients) puis écrit, par version :

* `public/game/archive/<v>/scene.glb` — glTF 2.0 binaire écrit à la main (aucune dépendance
  nouvelle) : maillages `POSITION`/`TEXCOORD_0`/`COLOR_0` (+ `JOINTS_0`/`WEIGHTS_0` quand la
  géométrie est skinnée), matériaux `KHR_materials_unlit`, textures PNG intégrées, animations
  squelettiques décodées ;
* `public/game/archive/<v>/scene.json` — ce que le glTF ne porte pas : caméra (inconnue dans
  les données, elle vient du manifeste), axe « haut », couleur de fond, liste des animations.

Formats décodés (voir aussi `.superpowers/amm-spike/README-textured.md`) :

* `.bin` = `zlib(` suite de `(u32 localID, u32 size, payload)` `)`. Pour une géométrie :
  localID 0 = vertex buffer, 1 = index buffer u16, 2 = squelette, 3 = blob de collision.
  Le `vertexDeclarations` du xdb donne le stride et l'offset de chaque attribut.
* Squelette (localID 2) : entête de 4 pointeurs *auto-relatifs* `(offset, count)` — un pointeur
  de valeur V à l'adresse P désigne P+V. Tables : matrices inverses de bind (52 o = 12 f32 +
  u32 parent), noms `(ptr, len)`, ordre d'évaluation (u16), transformations locales de bind
  (48 o = 12 f32).
* `(SkeletalAnimation).bin` : même principe de pointeurs auto-relatifs. Entête
  `u16 fps, u16 nb_images, ptr fin, (count, ptr) × 3`. Chaque nœud = nom (aligné sur 4 octets),
  puis la translation (par axe : 1 f32 si fixe, sinon 2 f32 `base`/`échelle`), puis la rotation
  (1 f32 par composante fixe, rien pour les composantes animées), puis, par image, un entier
  16 bits par composante animée — `u16` pour la translation (`base + v × échelle`), `i16 / 32767`
  pour la rotation (quaternion renormalisé ensuite). Le nombre de composantes animées se déduit
  de la taille : `nb_flottants = 7 + nTA - nRA` et `nb_canaux = nTA + nRA`.
"""
from __future__ import annotations

import argparse
import glob as globmod
import io
import json
import math
import re
import struct
import sys
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image

if __package__ in (None, ""):  # exécution directe : `python3 tools/extract_menu_scene.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.uitexture import build_dds  # noqa: E402
from tools.scenes import hooks_for  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE / "scenes_manifest.json"
DEFAULT_OUT = HERE.parent / "public" / "game" / "archive"

FOURCC = {"DXT1": b"DXT1", "DXT3": b"DXT3", "DXT5": b"DXT5"}
BLOCK_BYTES = {"DXT1": 8, "DXT3": 16, "DXT5": 16}

# Les composantes du quaternion sont rangées (w, x, y, z) dans les binaires ; glTF attend
# (x, y, z, w).


# --- conteneur binaire ---------------------------------------------------------------------

def read_chunks(data: bytes) -> dict[int, bytes]:
    """`zlib(` suite de `(u32 localID, u32 size, payload)` `)` → {localID: payload}.

    Les données non compressées sont acceptées telles quelles (certains `.bin` le sont).
    En cas de doublon de `localID`, la première occurrence gagne.
    """
    try:
        raw = zlib.decompress(data)
    except zlib.error:
        raw = data
    out: dict[int, bytes] = {}
    off = 0
    while off + 8 <= len(raw):
        local_id, size = struct.unpack_from("<II", raw, off)
        off += 8
        if size < 0 or off + size > len(raw):
            break
        out.setdefault(local_id, raw[off:off + size])
        off += size
    return out


def self_pointer(buf: bytes, offset: int) -> int:
    """Pointeur auto-relatif : la valeur lue en `offset` est un delta depuis `offset`."""
    value, = struct.unpack_from("<I", buf, offset)
    return offset + value


# --- sources de binaires -------------------------------------------------------------------

class BinSource:
    """Résout `World/MainMenu/.../X.(Geometry).bin` dans des dossiers puis dans des paks (zip)."""

    def __init__(self, dirs: list[Path], pak_globs: list[str]) -> None:
        self.dirs = [Path(d) for d in dirs]
        self.pak_globs = pak_globs
        self._index: dict[str, Path] | None = None
        self._zips: dict[Path, zipfile.ZipFile] = {}
        self.missing: list[str] = []

    def _pak_index(self) -> dict[str, Path]:
        if self._index is None:
            index: dict[str, Path] = {}
            for pattern in self.pak_globs:
                for path in sorted(globmod.glob(pattern)):
                    try:
                        names = zipfile.ZipFile(path).namelist()
                    except (OSError, zipfile.BadZipFile):
                        continue
                    for name in names:
                        index.setdefault(name.replace("\\", "/"), Path(path))
            self._index = index
        return self._index

    def get(self, rel: str) -> bytes | None:
        rel = rel.lstrip("/").replace("\\", "/")
        for base in self.dirs:
            candidate = base / rel
            if candidate.is_file():
                return candidate.read_bytes()
        pak = self._pak_index().get(rel)
        if pak is None:
            self.missing.append(rel)
            return None
        zf = self._zips.get(pak)
        if zf is None:
            zf = self._zips[pak] = zipfile.ZipFile(pak)
        try:
            return zf.read(rel)
        except KeyError:
            self.missing.append(rel)
            return None


# --- déclaration de sommets ----------------------------------------------------------------

@dataclass(frozen=True)
class VertexLayout:
    stride: int
    position: int | None = None
    texcoord0: int | None = None
    color: int | None = None
    normal: int | None = None
    weights: int | None = None
    indices: int | None = None

    @property
    def skinned(self) -> bool:
        return self.weights is not None and self.indices is not None


def _decl_offset(item: ET.Element, tag: str) -> int | None:
    node = item.find(tag)
    if node is None:
        return None
    type_node = node.find("type")
    offset_node = node.find("offset")
    if type_node is None or offset_node is None:
        return None
    if (type_node.text or "").strip() == "UNUSED":
        return None
    offset = int(float(offset_node.text or "255"))
    return None if offset >= 255 else offset


def parse_vertex_declaration(item: ET.Element) -> VertexLayout:
    stride = int(float((item.findtext("stride") or "0")))
    return VertexLayout(
        stride=stride,
        position=_decl_offset(item, "position"),
        texcoord0=_decl_offset(item, "texcoord0"),
        color=_decl_offset(item, "color"),
        normal=_decl_offset(item, "normal"),
        weights=_decl_offset(item, "weights"),
        indices=_decl_offset(item, "indices"),
    )


def decode_vertex_buffer(buf: bytes, layout: VertexLayout, count: int) -> dict[str, np.ndarray]:
    """Découpe le vertex buffer selon la déclaration. Renvoie des tableaux numpy par attribut."""
    if layout.stride <= 0 or count <= 0:
        raise ValueError("stride et nombre de sommets doivent être positifs")
    if len(buf) < count * layout.stride:
        raise ValueError(f"vertex buffer trop court : {len(buf)} < {count} × {layout.stride}")
    rows = np.frombuffer(buf[:count * layout.stride], np.uint8).reshape(count, layout.stride)
    out: dict[str, np.ndarray] = {}
    if layout.position is not None:
        out["position"] = rows[:, layout.position:layout.position + 12].copy().view("<f4").reshape(count, 3)
    if layout.texcoord0 is not None:
        out["texcoord0"] = rows[:, layout.texcoord0:layout.texcoord0 + 8].copy().view("<f4").reshape(count, 2)
    if layout.color is not None:
        out["color"] = rows[:, layout.color:layout.color + 4].copy()
    if layout.normal is not None:
        raw = rows[:, layout.normal:layout.normal + 3].astype(np.float32)
        out["normal"] = (raw - 128.0) / 127.0
    if layout.weights is not None:
        out["weights"] = rows[:, layout.weights:layout.weights + 4].copy()
    if layout.indices is not None:
        out["indices"] = rows[:, layout.indices:layout.indices + 4].copy()
    return out


# --- géométrie (xdb) -----------------------------------------------------------------------

@dataclass
class MaterialSpec:
    name: str = "?"
    texture: str | None = None
    blend: str = "BLEND_EFFECT_ALPHA"
    transparent: bool = False
    visible: bool = True
    alpha: float = 1.0
    uv_scroll: tuple[float, float] = (0.0, 0.0)


@dataclass
class ElementSpec:
    name: str
    ib0: int
    ib1: int
    vb0: int
    vb1: int
    material: MaterialSpec


@dataclass
class Locator:
    name: str
    position: tuple[float, float, float]
    rotation: tuple[float, float, float, float]  # x, y, z, w
    scale: float


@dataclass
class GeometryDoc:
    elements: list[ElementSpec] = field(default_factory=list)
    layouts: list[VertexLayout] = field(default_factory=list)
    vertex_buffer_size: int = 0
    index_buffer_size: int = 0
    skeleton_id: int | None = None
    locators: list[Locator] = field(default_factory=list)
    animation_href: str | None = None
    aabb: tuple[np.ndarray, np.ndarray] | None = None
    geometry_box: tuple[np.ndarray, np.ndarray] | None = None

    @property
    def vertex_count(self) -> int:
        return max([e.vb1 for e in self.elements] + [0])


def _box(node: ET.Element | None) -> tuple[np.ndarray, np.ndarray] | None:
    if node is None:
        return None
    center, extents = node.find("center"), node.find("extents")
    if center is None or extents is None:
        return None
    c = np.array([float(center.get(a, 0)) for a in "xyz"])
    e = np.array([float(extents.get(a, 0)) for a in "xyz"])
    return c, e


def _bool(text: str | None, default: bool = False) -> bool:
    if text is None:
        return default
    return text.strip().lower() == "true"


def parse_geometry_xdb(text: str) -> GeometryDoc:
    root = ET.fromstring(text)
    doc = GeometryDoc()
    doc.aabb = _box(root.find("aabb"))
    doc.geometry_box = _box(root.find("geometryBox"))
    anim = root.find("SkeletalAnimation")
    if anim is not None and anim.get("href"):
        doc.animation_href = anim.get("href")
    for tag, attr in (("vertexBuffer", "vertex_buffer_size"), ("indexBuffer", "index_buffer_size")):
        node = root.find(tag)
        if node is not None:
            setattr(doc, attr, int(float(node.findtext("size") or "0")))
    skel = root.find("skeleton")
    if skel is not None and (skel.findtext("size") or "0") != "0":
        doc.skeleton_id = int(float(skel.findtext("localID") or "2"))
    for item in root.findall("./vertexDeclarations/Item"):
        doc.layouts.append(parse_vertex_declaration(item))
    for item in root.findall("./sceneNodes/Item"):
        rot = item.find("rotation")
        pos = item.find("position")
        if pos is None:
            continue
        doc.locators.append(Locator(
            name=(item.findtext("name") or "").strip(),
            position=tuple(float(pos.get(a, 0)) for a in "xyz"),
            rotation=tuple(float(rot.get(a, 0)) for a in "xyzw") if rot is not None else (0.0, 0.0, 0.0, 1.0),
            scale=float(item.findtext("scale") or "1"),
        ))
    for item in root.findall("./modelElements/Item"):
        lod = item.find("./lods/Item")
        if lod is None:
            continue
        mat_node = item.find("material")
        mat = MaterialSpec(name=(item.findtext("materialName") or "?").strip())
        if mat_node is not None:
            tex = mat_node.find("diffuseTexture")
            if tex is not None and tex.get("href"):
                mat.texture = tex.get("href")
            mat.blend = (mat_node.findtext("BlendEffect") or "BLEND_EFFECT_ALPHA").strip()
            mat.transparent = _bool(mat_node.findtext("transparent"))
            if _bool(mat_node.findtext("scrollRGB")) or _bool(mat_node.findtext("scrollAlpha")):
                mat.uv_scroll = (float(mat_node.findtext("uTranslateSpeed") or "0"),
                                 float(mat_node.findtext("vTranslateSpeed") or "0"))
            mat.visible = _bool(mat_node.findtext("visible"), True)
            mat.alpha = float(mat_node.findtext("transparencyModifier") or "1")
        doc.elements.append(ElementSpec(
            name=(item.findtext("name") or "?").strip(),
            ib0=int(float(lod.findtext("indexBufferBegin") or "0")),
            ib1=int(float(lod.findtext("indexBufferEnd") or "0")),
            vb0=int(float(lod.findtext("vertexBufferBegin") or "0")),
            vb1=int(float(lod.findtext("vertexBufferEnd") or "0")),
            material=mat,
        ))
    return doc


# --- squelette -----------------------------------------------------------------------------

@dataclass
class Skeleton:
    names: list[str]
    parents: list[int]
    local: np.ndarray       # (n, 4, 3) : 3 lignes de base + translation
    inverse: np.ndarray     # (n, 4, 3) : matrice inverse de bind (monde → os)
    order: list[int]

    def __len__(self) -> int:
        return len(self.names)

    def topological_order(self) -> list[int]:
        out: list[int] = []
        seen: set[int] = set()

        def visit(i: int) -> None:
            if i in seen:
                return
            seen.add(i)
            p = self.parents[i]
            if 0 <= p < len(self) and p != i:
                visit(p)
            out.append(i)

        for i in range(len(self)):
            visit(i)
        return out


def parse_skeleton(blob: bytes) -> Skeleton:
    header = struct.unpack_from("<8I", blob, 0)
    count = header[1]
    p_inverse = self_pointer(blob, 0)
    p_names = self_pointer(blob, 8)
    p_order = self_pointer(blob, 16)
    p_local = self_pointer(blob, 24)
    names: list[str] = []
    parents: list[int] = []
    inverse = np.zeros((count, 4, 3), np.float64)
    local = np.zeros((count, 4, 3), np.float64)
    for i in range(count):
        off = p_names + 8 * i
        value, length = struct.unpack_from("<II", blob, off)
        names.append(blob[off + value:off + value + max(0, length - 1)].decode("ascii", "replace"))
        inverse[i] = np.array(struct.unpack_from("<12f", blob, p_inverse + 52 * i)).reshape(4, 3)
        parent, = struct.unpack_from("<I", blob, p_inverse + 52 * i + 48)
        parents.append(parent)
        local[i] = np.array(struct.unpack_from("<12f", blob, p_local + 48 * i)).reshape(4, 3)
    order = list(struct.unpack_from(f"<{count}H", blob, p_order))
    return Skeleton(names=names, parents=parents, local=local, inverse=inverse, order=order)


# --- animation squelettique ------------------------------------------------------------------

@dataclass
class JointTrack:
    name: str
    translation: np.ndarray   # (frames, 3)
    rotation: np.ndarray      # (frames, 4) en (x, y, z, w), normalisé
    animated: bool


@dataclass
class SkeletalAnimation:
    fps: int
    frames: int
    tracks: list[JointTrack]
    undecoded: list[str] = field(default_factory=list)


def _combinations(items: list[int], k: int) -> list[tuple[int, ...]]:
    if k == 0:
        return [()]
    if k > len(items):
        return []
    out: list[tuple[int, ...]] = []
    for i, value in enumerate(items):
        for rest in _combinations(items[i + 1:], k - 1):
            out.append((value,) + rest)
    return out


def _choose_translation(floats: list[float], n_animated: int, bind: np.ndarray | None,
                        max_span: float = 0.0) -> tuple[list[int], list[tuple[float, float]]] | None:
    """Répartit les flottants sur les 3 axes : 1 par axe fixe, 2 (base, échelle) par axe animé.

    `max_span` (amplitude plausible, tirée de la boîte de la géométrie) écarte les découpages
    où un flottant de coordonnée serait pris pour une échelle : l'amplitude obtenue
    (`échelle × 65535`) serait alors absurde.
    """
    best = None
    for animated in _combinations([0, 1, 2], n_animated):
        slots: list[tuple[float, float] | float] = []
        cursor = 0
        ok = True
        for axis in range(3):
            if axis in animated:
                base, scale = floats[cursor], floats[cursor + 1]
                cursor += 2
                if not (0.0 < scale < 1.0) or (max_span > 0 and scale * 65535.0 > max_span):
                    ok = False
                    break
                slots.append((base, scale))
            else:
                slots.append(floats[cursor])
                cursor += 1
        if not ok:
            continue
        cost = 0.0
        for axis in range(3):
            slot = slots[axis]
            target = float(bind[axis]) if bind is not None else None
            if isinstance(slot, tuple):
                base, scale = slot
                span = scale * 65535.0
                cost += 0.05 * span
                if target is not None and not (base - 1e-3 <= target <= base + span + 1e-3):
                    cost += min(abs(target - base), abs(target - base - span))
            elif target is not None:
                cost += abs(slot - target)
        if best is None or cost < best[0]:
            best = (cost, list(animated), slots)
    if best is None:
        return None
    return best[1], best[2]


def _choose_rotation(floats: list[float], n_animated: int,
                     bind: np.ndarray | None) -> tuple[list[int], list[float]] | None:
    """Les composantes animées ne portent aucun flottant : les flottants restants sont les fixes."""
    best = None
    for animated in _combinations([0, 1, 2, 3], n_animated):
        statics = [c for c in range(4) if c not in animated]
        values = [0.0, 0.0, 0.0, 0.0]
        for slot, comp in enumerate(statics):
            values[comp] = floats[slot]
        if any(abs(v) > 1.0001 for v in values):
            continue
        # À égalité, on anime plutôt (x, y, z) en gardant `w` fixe : c'est le cas courant
        # (rotations modérées autour d'une pose de repos).
        cost = -1e-3 * sum(animated)
        if bind is not None:
            for comp in statics:
                cost += abs(values[comp] - float(bind[comp]))
        if best is None or cost < best[0]:
            best = (cost, list(animated), values)
    if best is None:
        return None
    return best[1], best[2]


def _quat_from_rows(rows: np.ndarray) -> np.ndarray:
    """Matrice 3×3 (lignes = vecteurs de base) → quaternion (w, x, y, z)."""
    m = np.asarray(rows[:3]).T
    trace = m[0, 0] + m[1, 1] + m[2, 2]
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        q = (0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s)
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = ((m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s)
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = ((m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s)
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = ((m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s)
    return np.array(q)


def parse_skeletal_animation(blob: bytes, skeleton: Skeleton | None = None,
                             max_span: float = 0.0) -> SkeletalAnimation:
    fps, frames = struct.unpack_from("<HH", blob, 0)
    count, = struct.unpack_from("<I", blob, 8)
    p_names = self_pointer(blob, 12)
    p_order = self_pointer(blob, 20)
    records = []
    for i in range(count):
        off = p_names + 8 * i
        value, length = struct.unpack_from("<II", blob, off)
        records.append((off + value, length))
    bounds = sorted({addr for addr, _ in records} | {p_order})
    bind_by_name: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    if skeleton is not None:
        for i, name in enumerate(skeleton.names):
            bind_by_name[name] = (skeleton.local[i][3], _quat_from_rows(skeleton.local[i]))

    tracks: list[JointTrack] = []
    undecoded: list[str] = []
    for addr, length in sorted(records):
        name = blob[addr:addr + max(0, length - 1)].decode("ascii", "replace")
        end = bounds[bounds.index(addr) + 1]
        start = addr + (length + 3) // 4 * 4
        body = end - start
        bind_t, bind_q = bind_by_name.get(name, (None, None))
        track = _decode_track(blob, name, start, body, frames, bind_t, bind_q, max_span)
        if track is None:
            undecoded.append(name)
            track = JointTrack(
                name=name,
                translation=np.zeros((1, 3)) if bind_t is None else np.array([bind_t]),
                rotation=np.array([[0.0, 0.0, 0.0, 1.0]]) if bind_q is None
                else np.array([[bind_q[1], bind_q[2], bind_q[3], bind_q[0]]]),
                animated=False,
            )
        tracks.append(track)
    return SkeletalAnimation(fps=fps or 30, frames=frames, tracks=tracks, undecoded=undecoded)


def _decode_track(blob: bytes, name: str, start: int, body: int, frames: int,
                  bind_t: np.ndarray | None, bind_q: np.ndarray | None,
                  max_span: float = 0.0) -> JointTrack | None:
    if body < 28 or frames <= 0:
        return None
    # Le découpage se déduit de la taille : `nb_flottants = 7 + nTA - nRA` (3 pour la
    # translation, +1 par axe animé, et une valeur par composante fixe du quaternion) et
    # `nb_canaux = nTA + nRA`. Sur les vraies animations (≥ 161 images) une seule solution
    # existe ; on retient sinon celle qui anime le plus de composantes.
    solution = None
    for channels in range(0, 8):
        rest = body - frames * channels * 2
        if rest < 12:
            break
        if rest % 4 not in (0, 2) or rest > 42:
            continue
        n_floats = rest // 4
        n_ta, n_ra = n_floats - 7 + channels, 7 - n_floats + channels
        if n_ta < 0 or n_ra < 0 or n_ta % 2 or n_ra % 2:
            continue
        n_ta, n_ra = n_ta // 2, n_ra // 2
        if n_ta > 3 or n_ra > 4 or n_ta + n_ra != channels:
            continue
        solution = (channels, n_floats, n_ta, n_ra)
    if solution is None:
        return None
    channels, n_floats, n_ta, n_ra = solution
    floats = list(struct.unpack_from(f"<{n_floats}f", blob, start))
    translation = _choose_translation(floats[:3 + n_ta], n_ta, bind_t, max_span)
    rotation = _choose_rotation(floats[3 + n_ta:], n_ra, bind_q)
    if translation is None or rotation is None:
        return None
    t_animated, t_slots = translation
    r_animated, r_values = rotation

    curve_start = start + n_floats * 4
    n = frames if channels else 1
    if channels:
        raw = np.frombuffer(blob[curve_start:curve_start + frames * channels * 2], "<u2")
        if raw.size != frames * channels:
            return None
        raw = raw.reshape(frames, channels)
    else:
        raw = np.zeros((1, 0), np.uint16)

    out_t = np.zeros((n, 3))
    cursor = 0
    for axis in range(3):
        slot = t_slots[axis]
        if isinstance(slot, tuple):
            base, scale = slot
            out_t[:, axis] = base + raw[:, cursor].astype(np.float64) * scale
            cursor += 1
        else:
            out_t[:, axis] = slot
    out_q = np.zeros((n, 4))  # (w, x, y, z)
    for comp in range(4):
        if comp in r_animated:
            signed = raw[:, cursor].astype(np.int16).astype(np.float64)
            out_q[:, comp] = signed / 32767.0
            cursor += 1
        else:
            out_q[:, comp] = r_values[comp]
    norm = np.linalg.norm(out_q, axis=1, keepdims=True)
    out_q = np.where(norm > 1e-6, out_q / np.maximum(norm, 1e-9), np.array([1.0, 0.0, 0.0, 0.0]))
    xyzw = out_q[:, [1, 2, 3, 0]]
    return JointTrack(name=name, translation=out_t, rotation=xyzw, animated=bool(channels))


# --- pose de repos et peau ---------------------------------------------------------------------

def quat_matrix(q: np.ndarray) -> np.ndarray:
    """Quaternion (x, y, z, w) → matrice 3×3 (colonnes)."""
    x, y, z, w = (float(v) for v in q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def rest_local(skeleton: Skeleton, animation: SkeletalAnimation | None,
               index: int) -> tuple[np.ndarray, np.ndarray]:
    """Transformation locale de repos d'une articulation : (translation, quaternion xyzw).

    L'image 0 de l'animation fait foi quand elle existe ; sinon la pose de bind du squelette.
    Les matrices inverses de bind du jeu ne sont pas reprises telles quelles : on les recalcule
    depuis cette pose (`rest_world_matrices`), ce qui garantit qu'à l'image 0 le maillage
    skinné redonne exactement la géométrie au repos.
    """
    tracks = {t.name: t for t in animation.tracks} if animation else {}
    track = tracks.get(skeleton.names[index])
    if track is not None:
        return np.asarray(track.translation[0], float), np.asarray(track.rotation[0], float)
    wxyz = _quat_from_rows(skeleton.local[index])
    return np.asarray(skeleton.local[index][3], float), np.array([wxyz[1], wxyz[2], wxyz[3], wxyz[0]])


def rest_world_matrices(skeleton: Skeleton, animation: SkeletalAnimation | None) -> np.ndarray:
    """Matrices monde 4×4 de la pose de repos, parents avant enfants."""
    world = np.tile(np.eye(4), (len(skeleton), 1, 1))
    for i in skeleton.topological_order():
        t, q = rest_local(skeleton, animation, i)
        m = np.eye(4)
        m[:3, :3] = quat_matrix(q)
        m[:3, 3] = t
        p = skeleton.parents[i]
        world[i] = world[p] @ m if 0 <= p < len(skeleton) else m
    return world


def skin_attributes(vertices: dict[str, np.ndarray], joint_count: int) -> tuple[np.ndarray, np.ndarray]:
    """`JOINTS_0`/`WEIGHTS_0` glTF depuis les attributs bruts.

    Les indices stockés sont des **décalages dans la palette de matrices** (3 vecteurs par
    articulation) : l'indice réel vaut `valeur / 3`. `255` marque un emplacement inutilisé.
    """
    raw = vertices["indices"].astype(np.int32)
    unused = raw >= 255
    joints = np.clip(raw // 3, 0, max(0, joint_count - 1)).astype(np.uint8)
    joints[unused] = 0
    weights = vertices["weights"].astype(np.float64)
    weights[unused] = 0.0
    total = weights.sum(axis=1)
    weights[total == 0, 0] = 1.0
    total = weights.sum(axis=1)
    weights = weights / total[:, None]
    scaled = np.floor(weights * 255.0).astype(np.int32)
    scaled[np.arange(len(scaled)), np.argmax(weights, axis=1)] += 255 - scaled.sum(axis=1)
    return joints, np.clip(scaled, 0, 255).astype(np.uint8)


# --- textures --------------------------------------------------------------------------------

class TextureLibrary:
    """Décode les `(Texture).bin` DXT référencés par les matériaux, en PNG."""

    def __init__(self, source: BinSource, server_root: Path, max_size: int = 512) -> None:
        self.source = source
        self.server_root = Path(server_root)
        self.max_size = max_size
        self.cache: dict[str, tuple[bytes, int, int] | None] = {}

    def _mips(self, data: bytes) -> dict[int, bytes]:
        return read_chunks(data)

    def png(self, href: str) -> tuple[bytes, int, int] | None:
        key = href.split("#")[0]
        if key in self.cache:
            return self.cache[key]
        self.cache[key] = result = self._decode(key)
        return result

    def _decode(self, key: str) -> tuple[bytes, int, int] | None:
        xdb = self.server_root / key.lstrip("/")
        width = height = 0
        fmt = "DXT5"
        if xdb.is_file():
            try:
                root = ET.fromstring(xdb.read_text(errors="replace"))
            except ET.ParseError:
                root = None
            if root is not None:
                width = int(float(root.findtext("width") or "0"))
                height = int(float(root.findtext("height") or "0"))
                fmt = (root.findtext("type") or "DXT5").strip()
        base = key[:-4] if key.endswith(".xdb") else key
        mips: dict[int, bytes] = {}
        for suffix in (".hi.bin", ".bin"):
            data = self.source.get(base + suffix)
            if data:
                try:
                    mips.update(self._mips(data))
                except zlib.error:
                    pass
        if not mips or not width or fmt not in FOURCC:
            return None
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
                continue
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            return buf.getvalue(), w, h
        return None


# --- écriture glTF binaire ---------------------------------------------------------------------

COMPONENT = {"f32": 5126, "u8": 5121, "u16": 5123, "u32": 5125}
TYPE_COUNT = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
COMPONENT_BYTES = {5126: 4, 5121: 1, 5123: 2, 5125: 4}


class GltfBuilder:
    """Assemble un glTF 2.0 binaire (`.glb`) : chunk JSON + chunk BIN."""

    def __init__(self) -> None:
        self.json: dict = {
            "asset": {"version": "2.0", "generator": "allodex/extract_menu_scene"},
            "extensionsUsed": ["KHR_materials_unlit"],
            "scene": 0,
            "scenes": [{"nodes": []}],
            "nodes": [],
            "meshes": [],
            "materials": [],
            "textures": [],
            "images": [],
            "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}],
            "accessors": [],
            "bufferViews": [],
            "buffers": [],
            "skins": [],
            "animations": [],
        }
        self.blob = bytearray()

    # -- tampon

    def _align(self, alignment: int = 4) -> None:
        while len(self.blob) % alignment:
            self.blob.append(0)

    def add_buffer_view(self, data: bytes, target: int | None = None, stride: int | None = None) -> int:
        self._align(4)
        offset = len(self.blob)
        self.blob.extend(data)
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
        if target is not None:
            view["target"] = target
        if stride is not None:
            view["byteStride"] = stride
        self.json["bufferViews"].append(view)
        return len(self.json["bufferViews"]) - 1

    def add_accessor(self, array: np.ndarray, kind: str, component: str,
                     normalized: bool = False, target: int | None = None,
                     minmax: bool = False) -> int:
        data = np.ascontiguousarray(array).tobytes()
        view = self.add_buffer_view(data, target=target)
        accessor = {
            "bufferView": view,
            "byteOffset": 0,
            "componentType": COMPONENT[component],
            "count": int(array.shape[0]),
            "type": kind,
        }
        if normalized:
            accessor["normalized"] = True
        if minmax:
            flat = array.reshape(array.shape[0], -1).astype(float)
            accessor["min"] = [float(v) for v in flat.min(axis=0)]
            accessor["max"] = [float(v) for v in flat.max(axis=0)]
        self.json["accessors"].append(accessor)
        return len(self.json["accessors"]) - 1

    # -- ressources

    def add_image(self, png: bytes, name: str) -> int:
        view = self.add_buffer_view(png)
        self.json["images"].append({"bufferView": view, "mimeType": "image/png", "name": name})
        self.json["textures"].append({"sampler": 0, "source": len(self.json["images"]) - 1})
        return len(self.json["textures"]) - 1

    def add_material(self, name: str, texture: int | None, alpha_mode: str,
                     double_sided: bool, additive: bool, alpha: float = 1.0) -> int:
        pbr: dict = {"baseColorFactor": [1.0, 1.0, 1.0, alpha], "metallicFactor": 0.0, "roughnessFactor": 1.0}
        if texture is not None:
            pbr["baseColorTexture"] = {"index": texture}
        material: dict = {
            "name": name,
            "pbrMetallicRoughness": pbr,
            "alphaMode": alpha_mode,
            "doubleSided": double_sided,
            "extensions": {"KHR_materials_unlit": {}},
        }
        if additive:
            material["extras"] = {"blend": "add"}
        self.json["materials"].append(material)
        return len(self.json["materials"]) - 1

    def add_node(self, node: dict) -> int:
        self.json["nodes"].append(node)
        return len(self.json["nodes"]) - 1

    def to_glb(self) -> bytes:
        self.json["buffers"] = [{"byteLength": len(self.blob)}]
        for key in ("skins", "animations", "textures", "images", "materials", "meshes"):
            if not self.json[key]:
                del self.json[key]
        if "textures" not in self.json:
            self.json.pop("samplers", None)
        payload = json.dumps(self.json, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        payload += b" " * ((4 - len(payload) % 4) % 4)
        blob = bytes(self.blob)
        blob += b"\0" * ((4 - len(blob) % 4) % 4)
        total = 12 + 8 + len(payload) + (8 + len(blob) if blob else 0)
        out = bytearray()
        out += struct.pack("<III", 0x46546C67, 2, total)
        out += struct.pack("<II", len(payload), 0x4E4F534A) + payload
        if blob:
            out += struct.pack("<II", len(blob), 0x004E4942) + blob
        return bytes(out)


def validate_glb(data: bytes) -> dict:
    """Contrôle structurel : entêtes, alignements, accesseurs dans leurs vues, vues dans le tampon."""
    if len(data) < 20:
        raise ValueError("glb trop court")
    magic, version, total = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67:
        raise ValueError("magic glTF absent")
    if version != 2:
        raise ValueError(f"version glTF inattendue : {version}")
    if total != len(data):
        raise ValueError(f"longueur déclarée {total} ≠ {len(data)}")
    offset = 12
    chunks: dict[int, bytes] = {}
    while offset + 8 <= len(data):
        length, kind = struct.unpack_from("<II", data, offset)
        if length % 4:
            raise ValueError("chunk non aligné sur 4 octets")
        offset += 8
        chunks[kind] = data[offset:offset + length]
        offset += length
    if 0x4E4F534A not in chunks:
        raise ValueError("chunk JSON absent")
    doc = json.loads(chunks[0x4E4F534A].decode("utf-8"))
    blob = chunks.get(0x004E4942, b"")
    buffers = doc.get("buffers", [])
    views = doc.get("bufferViews", [])
    for i, view in enumerate(views):
        if view.get("buffer", 0) >= max(1, len(buffers)):
            raise ValueError(f"bufferView {i} : tampon inconnu")
        end = view.get("byteOffset", 0) + view["byteLength"]
        if end > buffers[view.get("buffer", 0)]["byteLength"] or end > len(blob):
            raise ValueError(f"bufferView {i} déborde du tampon")
    for i, acc in enumerate(doc.get("accessors", [])):
        if "bufferView" not in acc:
            continue
        view = views[acc["bufferView"]]
        size = COMPONENT_BYTES[acc["componentType"]] * TYPE_COUNT[acc["type"]]
        stride = view.get("byteStride", size)
        end = acc.get("byteOffset", 0) + (acc["count"] - 1) * stride + size
        if end > view["byteLength"]:
            raise ValueError(f"accesseur {i} déborde de sa bufferView")
    for i, node in enumerate(doc.get("nodes", [])):
        for child in node.get("children", []):
            if child >= len(doc.get("nodes", [])):
                raise ValueError(f"nœud {i} : enfant inconnu {child}")
    return doc


# --- construction de la scène -----------------------------------------------------------------

@dataclass
class LoadedObject:
    name: str
    doc: GeometryDoc
    vertices: dict[str, np.ndarray]
    indices: np.ndarray
    skeleton: Skeleton | None
    animation: SkeletalAnimation | None


class SceneBuilder:
    def __init__(self, server_root: Path, directory: str, source: BinSource,
                 max_texture: int = 512) -> None:
        self.server_root = Path(server_root)
        self.directory = directory
        self.source = source
        self.textures = TextureLibrary(source, server_root, max_texture)
        self.objects: dict[str, LoadedObject | None] = {}
        self.notes: list[str] = []

    # -- chargement

    def xdb_path(self, name: str, kind: str) -> Path:
        return self.server_root / "World" / "MainMenu" / self.directory / f"{name}.({kind}).xdb"

    def rel_bin(self, name: str, kind: str) -> str:
        return f"World/MainMenu/{self.directory}/{name}.({kind}).bin"

    def load(self, name: str) -> LoadedObject | None:
        if name in self.objects:
            return self.objects[name]
        self.objects[name] = None
        path = self.xdb_path(name, "Geometry")
        if not path.is_file():
            self.notes.append(f"géométrie absente : {name}")
            return None
        doc = parse_geometry_xdb(path.read_text(errors="replace"))
        data = self.source.get(self.rel_bin(name, "Geometry"))
        if data is None or not doc.elements:
            self.notes.append(f"binaire de géométrie absent : {name}")
            return None
        chunks = read_chunks(data)
        vb, ib = chunks.get(0), chunks.get(1)
        if vb is None or ib is None:
            self.notes.append(f"tampons absents : {name}")
            return None
        layout = doc.layouts[0] if doc.layouts else VertexLayout(stride=len(vb) // max(1, doc.vertex_count))
        count = doc.vertex_count
        if layout.stride <= 0 or count <= 0:
            self.notes.append(f"déclaration de sommets illisible : {name}")
            return None
        vertices = decode_vertex_buffer(vb, layout, count)
        indices = np.frombuffer(ib[:doc.index_buffer_size or len(ib)], "<u2").astype(np.uint32)
        skeleton = None
        if doc.skeleton_id is not None and doc.skeleton_id in chunks:
            try:
                skeleton = parse_skeleton(chunks[doc.skeleton_id])
            except (struct.error, ValueError):
                self.notes.append(f"squelette illisible : {name}")
        animation = None
        if doc.animation_href:
            anim_bin = self.rel_bin(name, "SkeletalAnimation")
            blob = self.source.get(anim_bin)
            if blob is not None:
                payload = read_chunks(blob).get(0)
                if payload:
                    span = 0.0
                    if doc.aabb is not None:
                        span = float(np.max(doc.aabb[1]) * 4.0) or 0.0
                    try:
                        animation = parse_skeletal_animation(payload, skeleton, span)
                    except (struct.error, ValueError, IndexError):
                        self.notes.append(f"animation illisible : {name}")
        obj = LoadedObject(name=name, doc=doc, vertices=vertices, indices=indices,
                           skeleton=skeleton, animation=animation)
        self.objects[name] = obj
        return obj

    def attachments(self, name: str) -> list[tuple[str, Locator | None, dict]]:
        """`AttachedVisObjectComponent` du VisObjectTemplate, résolus sur les locators."""
        path = self.xdb_path(name, "VisObjectTemplate")
        if not path.is_file():
            return []
        try:
            root = ET.fromstring(path.read_text(errors="replace"))
        except ET.ParseError:
            return []
        parent = self.objects.get(name)
        locators = {loc.name: loc for loc in parent.doc.locators} if parent else {}
        out = []
        for item in root.findall("./visObjComponents/Item"):
            if item.get("type") != "AttachedVisObjectComponent":
                continue  # DelayComponent = apparitions aléatoires (hors périmètre v1)
            href = item.find("visObject")
            if href is None or not href.get("href"):
                continue
            path_in_game = href.get("href").split("#")[0]
            if Path(path_in_game).parent.name != self.directory:
                continue  # effets de particules d'autres dossiers (/Spells/FX/...) : hors périmètre v1
            child = Path(path_in_game).name.replace(".(VisObjectTemplate).xdb", "")
            locator_name = (item.findtext("locatorName") or "").strip()
            offset = item.find("offset")
            rotation = item.find("rotation")
            extra = {
                "offset": tuple(float(offset.get(a, 0)) for a in "xyz") if offset is not None else (0, 0, 0),
                "rotation": tuple(float(rotation.get(a, 0)) for a in "xyzw") if rotation is not None else (0, 0, 0, 1),
                "scale": float(item.findtext("scale") or "1"),
            }
            out.append((child, locators.get(locator_name), extra))
        return out


def _quat_mul(a: tuple, b: tuple) -> tuple:
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _quat_rotate(q: tuple, v: tuple) -> tuple:
    x, y, z, w = q
    vx, vy, vz = v
    tx, ty, tz = 2 * (y * vz - z * vy), 2 * (z * vx - x * vz), 2 * (x * vy - y * vx)
    return (vx + w * tx + (y * tz - z * ty), vy + w * ty + (z * tx - x * tz), vz + w * tz + (x * ty - y * tx))


def attachment_bind_positions(vertices: dict[str, np.ndarray], skeleton: Skeleton,
                              selected: np.ndarray | None = None) -> np.ndarray:
    """Applique le repère natif avant d'attacher un objet à son locator.

    Les drapeaux/pierres V7 ne sont pas centrés à l'origine dans le vertex buffer.
    La hiérarchie native contient leur recentrage. Employer des inverses recalculées
    sur l'image 0 l'annule et applique le décalage d'attache une deuxième fois.
    Conserver ici les matrices complètes préserve aussi échelles et cisaillements.
    """
    world = np.tile(np.eye(4), (len(skeleton), 1, 1))
    inverse = np.tile(np.eye(4), (len(skeleton), 1, 1))
    inverse[:, :3, :] = skeleton.inverse.transpose(0, 2, 1)
    for i in skeleton.topological_order():
        local = np.eye(4)
        local[:3, :] = skeleton.local[i].T
        parent = skeleton.parents[i]
        world[i] = world[parent] @ local if 0 <= parent < len(skeleton) else local
    palette = world @ inverse
    joints, weights = skin_attributes(vertices, len(skeleton))
    points = np.column_stack((vertices["position"], np.ones(len(vertices["position"]))))
    result = np.zeros_like(points)
    for slot in range(4):
        result += np.einsum("nij,nj->ni", palette[joints[:, slot]], points) * (weights[:, slot] / 255)[:, None]
    bound = result[:, :3].astype(np.float32)
    if selected is not None:
        # Certains effets restent dans leur pose de création alors que la coque est
        # déjà posée : ne pas appliquer à celle-ci la correction réservée aux effets.
        position = vertices["position"].astype(np.float32).copy()
        position[selected] = bound[selected]
        return position
    return bound


def build_scene(version: str, spec: dict, server_root: Path, source: BinSource,
                max_texture: int = 512) -> tuple[bytes, dict, list[str]]:
    builder = SceneBuilder(server_root, spec["dir"], source, max_texture)
    hooks = hooks_for(version)
    gltf = GltfBuilder()
    texture_index: dict[str, int | None] = {}
    material_index: dict[tuple, int] = {}
    animation_names: list[str] = []
    stats = {"triangles": 0, "textures": 0, "animations": 0, "objects": 0}

    def texture_for(href: str | None) -> int | None:
        if not href:
            return None
        if href not in texture_index:
            png = builder.textures.png(href)
            if png is None:
                texture_index[href] = None
                builder.notes.append(f"texture illisible : {href.split('#')[0]}")
            else:
                data, w, h = png
                texture_index[href] = gltf.add_image(data, Path(href.split("#")[0]).name)
                stats["textures"] += 1
        return texture_index[href]

    def material_for(mat: MaterialSpec) -> int:
        additive = mat.blend == "BLEND_EFFECT_ADD"
        if hooks.material is not None:
            additive = hooks.material(mat, additive)
        tex = texture_for(mat.texture)
        key = (mat.name, tex, additive, mat.transparent, round(mat.alpha, 4))
        if key not in material_index:
            alpha_mode = "BLEND" if (additive or mat.transparent) else "OPAQUE"
            material_index[key] = gltf.add_material(
                mat.name, tex, alpha_mode, True, additive, mat.alpha)
        return material_index[key]

    def emit_object(name: str, translation: tuple, rotation: tuple, scale: float) -> int | None:
        obj = builder.load(name)
        if obj is None:
            return None
        stats["objects"] += 1
        verts = obj.vertices
        position = verts["position"].astype(np.float32)
        if hooks.positions is not None:
            position = hooks.positions(name, obj, position)
        uv = verts.get("texcoord0", np.zeros((len(position), 2), np.float32)).astype(np.float32)
        color = verts.get("color")
        if color is None:
            rgba = np.full((len(position), 4), 255, np.uint8)
        else:
            rgb = np.minimum(color[:, :3].astype(np.uint16) * 2, 255).astype(np.uint8)
            flat = color[:, :3].max(axis=1) == 0
            rgb[flat] = 255  # couleur de sommet nulle = matériau sans teinte
            rgba = np.concatenate([rgb, color[:, 3:4]], axis=1)
        acc_pos = gltf.add_accessor(position, "VEC3", "f32", target=34962, minmax=True)
        acc_uv = gltf.add_accessor(uv, "VEC2", "f32", target=34962)
        acc_col = gltf.add_accessor(rgba, "VEC4", "u8", normalized=True, target=34962)
        attributes = {"POSITION": acc_pos, "TEXCOORD_0": acc_uv, "COLOR_0": acc_col}

        skin_index = None
        skeleton = obj.skeleton
        if skeleton is not None and "indices" in verts and "weights" in verts:
            joints, weights = skin_attributes(verts, len(skeleton))
            attributes["JOINTS_0"] = gltf.add_accessor(joints, "VEC4", "u8", target=34962)
            attributes["WEIGHTS_0"] = gltf.add_accessor(weights, "VEC4", "u8", normalized=True, target=34962)

        primitives = []
        for element in obj.doc.elements:
            if not element.material.visible:
                continue
            tri = obj.indices[element.ib0:element.ib1]
            if tri.size < 3:
                continue
            stats["triangles"] += tri.size // 3
            acc_idx = gltf.add_accessor(tri.astype(np.uint32), "SCALAR", "u32", target=34963)
            primitives.append({"attributes": attributes, "indices": acc_idx,
                               "material": material_for(element.material), "mode": 4,
                               "extras": {"element": element.name,
                                          "uvScroll": list(element.material.uv_scroll)}})
        if not primitives:
            return None
        gltf.json["meshes"].append({"name": name, "primitives": primitives})
        mesh_index = len(gltf.json["meshes"]) - 1

        children: list[int] = []
        mesh_node = {"name": f"{name}_mesh", "mesh": mesh_index}
        joint_nodes: list[int] = []
        if skeleton is not None and "JOINTS_0" in attributes:
            joint_nodes = _emit_skeleton(gltf, skeleton, obj.animation, name, animation_names)
            world = rest_world_matrices(skeleton, obj.animation)
            inverse = np.zeros((len(skeleton), 16), np.float32)
            for i in range(len(skeleton)):
                inverse[i] = np.linalg.inv(world[i]).T.reshape(-1)  # glTF : colonnes d'abord
            acc_ibm = gltf.add_accessor(inverse, "MAT4", "f32")
            gltf.json["skins"].append({
                "name": f"{name}_skin",
                "inverseBindMatrices": acc_ibm,
                "joints": joint_nodes,
                "skeleton": joint_nodes[skeleton.topological_order()[0]],
            })
            skin_index = len(gltf.json["skins"]) - 1
            mesh_node["skin"] = skin_index
            roots = [joint_nodes[i] for i in range(len(skeleton))
                     if not (0 <= skeleton.parents[i] < len(skeleton))]
            children.extend(roots)
        children.append(gltf.add_node(mesh_node))

        for child_name, locator, extra in builder.attachments(name):
            t = np.array(locator.position if locator else (0.0, 0.0, 0.0), float)
            r = locator.rotation if locator else (0.0, 0.0, 0.0, 1.0)
            s = (locator.scale if locator else 1.0) * extra["scale"]
            offset = _quat_rotate(r, extra["offset"])
            child = emit_object(child_name, tuple(t + np.array(offset) * (locator.scale if locator else 1.0)),
                                _quat_mul(r, extra["rotation"]), s)
            if child is not None:
                children.append(child)

        node = {"name": name, "children": children}
        if any(abs(v) > 1e-9 for v in translation):
            node["translation"] = [float(v) for v in translation]
        if any(abs(v) > 1e-9 for v in (rotation[0], rotation[1], rotation[2])) or abs(rotation[3] - 1) > 1e-9:
            node["rotation"] = [float(v) for v in rotation]
        if abs(scale - 1.0) > 1e-9:
            node["scale"] = [float(scale)] * 3
        return gltf.add_node(node)

    roots: list[int] = []
    for root_spec in spec["roots"]:
        if isinstance(root_spec, str):
            root_spec = {"name": root_spec}
        index = emit_object(root_spec["name"], tuple(root_spec.get("offset", (0.0, 0.0, 0.0))),
                            tuple(root_spec.get("rotation", (0.0, 0.0, 0.0, 1.0))),
                            float(root_spec.get("scale", 1.0)))
        if index is not None:
            roots.append(index)
    if hooks.extra_roots is not None:
        roots.extend(hooks.extra_roots(emit_object))
    # Le moteur du jeu est en main gauche (Direct3D) ; glTF est en main droite. On enveloppe la
    # scène dans un nœud miroir pour que le rendu ne soit pas inversé gauche/droite.
    mirror = gltf.add_node({"name": "scene", "scale": [-1.0, 1.0, 1.0], "children": roots})
    gltf.json["scenes"][0]["nodes"].append(mirror)

    stats["animations"] = len(gltf.json.get("animations", []))
    glb = gltf.to_glb()
    meta = {
        "version": version,
        "up": spec.get("up", [0, 0, 1]),
        "camera": spec["camera"],
        "background": spec.get("background", "#05060d"),
        "animations": animation_names,
        "stats": stats,
    }
    return glb, meta, builder.notes


def _emit_skeleton(gltf: GltfBuilder, skeleton: Skeleton, animation: SkeletalAnimation | None,
                   object_name: str, animation_names: list[str]) -> list[int]:
    """Crée un nœud par articulation (hiérarchie + pose de repos) et l'animation associée."""
    nodes: list[int] = []
    for i, name in enumerate(skeleton.names):
        t, q = rest_local(skeleton, animation, i)
        node = {"name": f"{object_name}/{name}",
                "translation": [float(v) for v in t],
                "rotation": [float(v) for v in q]}
        nodes.append(gltf.add_node(node))
    for i in range(len(skeleton)):
        parent = skeleton.parents[i]
        if 0 <= parent < len(skeleton) and parent != i:
            gltf.json["nodes"][nodes[parent]].setdefault("children", []).append(nodes[i])

    if animation is None or animation.frames <= 1:
        return nodes
    moving = [t for t in animation.tracks if t.animated and t.name in skeleton.names]
    if not moving:
        return nodes
    times = (np.arange(animation.frames, dtype=np.float32) / float(animation.fps))
    acc_time = gltf.add_accessor(times, "SCALAR", "f32", minmax=True)
    samplers: list[dict] = []
    channels: list[dict] = []
    for track in moving:
        node = nodes[skeleton.names.index(track.name)]
        acc_t = gltf.add_accessor(track.translation.astype(np.float32), "VEC3", "f32")
        samplers.append({"input": acc_time, "output": acc_t, "interpolation": "LINEAR"})
        channels.append({"sampler": len(samplers) - 1, "target": {"node": node, "path": "translation"}})
        acc_r = gltf.add_accessor(track.rotation.astype(np.float32), "VEC4", "f32")
        samplers.append({"input": acc_time, "output": acc_r, "interpolation": "LINEAR"})
        channels.append({"sampler": len(samplers) - 1, "target": {"node": node, "path": "rotation"}})
    gltf.json["animations"].append({"name": object_name, "samplers": samplers, "channels": channels})
    animation_names.append(object_name)
    return nodes


# --- validation des animations -----------------------------------------------------------------

def animated_bounds(obj: LoadedObject, frame: int) -> tuple[np.ndarray, np.ndarray] | None:
    """Boîte englobante des sommets skinnés à une image donnée (contrôle du décodage)."""
    skeleton, animation = obj.skeleton, obj.animation
    if skeleton is None or animation is None or "indices" not in obj.vertices:
        return None
    tracks = {t.name: t for t in animation.tracks}
    world = np.tile(np.eye(4), (len(skeleton), 1, 1))
    for i in skeleton.topological_order():
        track = tracks.get(skeleton.names[i])
        if track is not None:
            t = track.translation[min(frame, len(track.translation) - 1)]
            q = track.rotation[min(frame, len(track.rotation) - 1)]
        else:
            t, q = rest_local(skeleton, animation, i)
        m = np.eye(4)
        m[:3, :3] = quat_matrix(q)
        m[:3, 3] = t
        p = skeleton.parents[i]
        world[i] = world[p] @ m if 0 <= p < len(skeleton) else m
    rest = rest_world_matrices(skeleton, animation)
    joint = world @ np.linalg.inv(rest)
    pos = obj.vertices["position"].astype(np.float64)
    joints, weights = skin_attributes(obj.vertices, len(skeleton))
    wts = weights.astype(np.float64) / 255.0
    homogeneous = np.concatenate([pos, np.ones((len(pos), 1))], axis=1)
    out = np.zeros((len(pos), 3))
    for k in range(4):
        m = joint[joints[:, k].astype(np.int32)]
        out += wts[:, k, None] * np.einsum("nij,nj->ni", m, homogeneous)[:, :3]
    return out.min(axis=0), out.max(axis=0)


# --- rendu de contrôle -------------------------------------------------------------------------

def render_glb(glb: bytes, meta: dict, width: int = 960, height: int = 540,
               supersample: int = 2, time: float = 0.0) -> Image.Image:
    """Rasteriseur logiciel (peintre, UV corrigées par la profondeur) pour vérifier un `.glb`.

    Sert de planche de contrôle : ce n'est pas le moteur de rendu du site, seulement de quoi
    regarder à l'œil ce que contient le fichier exporté.
    """
    doc = validate_glb(glb)
    blob = _glb_bin(glb)

    def read(acc_index: int) -> np.ndarray:
        acc = doc["accessors"][acc_index]
        view = doc["bufferViews"][acc["bufferView"]]
        start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        n = acc["count"] * TYPE_COUNT[acc["type"]]
        dtype = {5126: "<f4", 5121: "u1", 5123: "<u2", 5125: "<u4"}[acc["componentType"]]
        arr = np.frombuffer(blob, dtype, count=n, offset=start)
        return arr.reshape(acc["count"], TYPE_COUNT[acc["type"]])

    textures: dict[int, np.ndarray] = {}

    def texture(index: int | None) -> np.ndarray:
        if index is None:
            return np.ones((1, 1, 4), np.float32)
        if index not in textures:
            source = doc["textures"][index]["source"]
            view = doc["bufferViews"][doc["images"][source]["bufferView"]]
            raw = blob[view.get("byteOffset", 0):view.get("byteOffset", 0) + view["byteLength"]]
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
            textures[index] = np.asarray(img, np.float32) / 255.0
        return textures[index]

    # Animations : on échantillonne chaque échantillonneur à `time` et on remplace la
    # transformation locale du nœud visé, ce qui permet de contrôler une image quelconque.
    posed: dict[int, dict] = {}
    for animation in doc.get("animations", []) if time else []:
        for channel in animation["channels"]:
            sampler = animation["samplers"][channel["sampler"]]
            times = read(sampler["input"]).reshape(-1)
            values = read(sampler["output"])
            index = int(np.searchsorted(times, time % max(times[-1], 1e-6)))
            index = min(max(index, 0), len(values) - 1)
            node = channel["target"]["node"]
            posed.setdefault(node, {})[channel["target"]["path"]] = [
                float(v) for v in values[index]]

    batches: list[tuple] = []

    def walk(node_index: int, matrix: np.ndarray) -> None:
        node = doc["nodes"][node_index]
        if node_index in posed:
            node = {**node, **posed[node_index]}
        m = matrix @ _node_matrix(node)
        if "mesh" in node:
            for prim in doc["meshes"][node["mesh"]]["primitives"]:
                attrs = prim["attributes"]
                pos = read(attrs["POSITION"]).astype(np.float64)
                uv = read(attrs["TEXCOORD_0"]).astype(np.float64)
                col = read(attrs["COLOR_0"]).astype(np.float64) / 255.0
                idx = read(prim["indices"]).reshape(-1, 3).astype(np.int64)
                mat = doc["materials"][prim["material"]]
                tex = (mat["pbrMetallicRoughness"].get("baseColorTexture") or {}).get("index")
                additive = (mat.get("extras") or {}).get("blend") == "add"
                alpha = mat["pbrMetallicRoughness"]["baseColorFactor"][3]
                world = (m[:3, :3] @ pos.T).T + m[:3, 3]
                batches.append((world, uv, col, idx, tex, additive, alpha))
        for child in node.get("children", []):
            walk(child, m)

    for root in doc["scenes"][0]["nodes"]:
        walk(root, np.eye(4))

    w, h = width * supersample, height * supersample
    background = meta.get("background", "#05060d").lstrip("#")
    fb = np.zeros((h, w, 3), np.float32)
    fb[:] = np.array([int(background[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)
    if not batches:
        return Image.fromarray((np.clip(fb, 0, 1) * 255).astype(np.uint8)).resize((width, height))

    cam = meta["camera"]
    eye = np.array(cam["position"], float)
    forward = np.array(cam["target"], float) - eye
    forward /= max(np.linalg.norm(forward), 1e-9)
    up = np.array(meta.get("up", [0, 0, 1]), float)
    right = np.cross(forward, up)
    right /= max(np.linalg.norm(right), 1e-9)
    true_up = np.cross(right, forward)
    orthographic = cam.get("orthographicHeight", 0)
    ty = orthographic / 2 if orthographic else math.tan(math.radians(cam.get("fov", 45)) / 2)
    tx = ty * width / height

    drawn = []
    for world, uv, col, idx, tex, additive, alpha in batches:
        rel = world - eye
        cz = rel @ forward
        zs = np.ones_like(cz) if orthographic else np.where(np.abs(cz) < 1e-6, 1e-6, cz)
        sx = w / 2 + ((rel @ right) / zs) / tx * (w / 2)
        sy = h / 2 - ((rel @ true_up) / zs) / ty * (h / 2)
        screen = np.stack([sx, sy, cz], 1)
        depth = screen[idx.reshape(-1), 2].reshape(-1, 3).mean(1)
        drawn.append((float(depth.mean()), screen, uv, col, idx[np.argsort(-depth)], tex, additive, alpha))
    drawn.sort(key=lambda b: -b[0])
    for _, screen, uv, col, idx, tex, additive, alpha in drawn:
        image = texture(tex)
        for tri in idx:
            _fill_triangle(fb, screen[tri], uv[tri], col[tri], image, additive, alpha)
    out = Image.fromarray((np.clip(fb, 0, 1) * 255).astype(np.uint8))
    return out.resize((width, height), Image.LANCZOS) if supersample > 1 else out


def _glb_bin(glb: bytes) -> bytes:
    offset = 12
    while offset + 8 <= len(glb):
        length, kind = struct.unpack_from("<II", glb, offset)
        offset += 8
        if kind == 0x004E4942:
            return glb[offset:offset + length]
        offset += length
    return b""


def _node_matrix(node: dict) -> np.ndarray:
    m = np.eye(4)
    if "matrix" in node:
        return np.array(node["matrix"]).reshape(4, 4).T
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    m[:3, :3] = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])
    m[:3, :3] *= np.array(node.get("scale", [1, 1, 1]))
    m[:3, 3] = node.get("translation", [0, 0, 0])
    return m


def _fill_triangle(fb: np.ndarray, p: np.ndarray, uv: np.ndarray, col: np.ndarray,
                   texture: np.ndarray, additive: bool, alpha_factor: float) -> None:
    if (p[:, 2] <= 0.2).any():
        return
    h, w = fb.shape[:2]
    minx, maxx = int(max(0, math.floor(p[:, 0].min()))), int(min(w - 1, math.ceil(p[:, 0].max())))
    miny, maxy = int(max(0, math.floor(p[:, 1].min()))), int(min(h - 1, math.ceil(p[:, 1].max())))
    if minx > maxx or miny > maxy:
        return
    area = (p[1, 0] - p[0, 0]) * (p[2, 1] - p[0, 1]) - (p[2, 0] - p[0, 0]) * (p[1, 1] - p[0, 1])
    if abs(area) < 1e-9:
        return
    gx, gy = np.meshgrid(np.arange(minx, maxx + 1) + 0.5, np.arange(miny, maxy + 1) + 0.5)
    l2 = ((p[1, 0] - p[0, 0]) * (gy - p[0, 1]) - (gx - p[0, 0]) * (p[1, 1] - p[0, 1])) / area
    l1 = ((gx - p[0, 0]) * (p[2, 1] - p[0, 1]) - (p[2, 0] - p[0, 0]) * (gy - p[0, 1])) / area
    l0 = 1.0 - l1 - l2
    mask = (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
    if not mask.any():
        return
    inv = 1.0 / p[:, 2]
    weights = np.stack([l0[mask] * inv[0], l1[mask] * inv[1], l2[mask] * inv[2]], 1)
    weights /= np.maximum(weights.sum(axis=1, keepdims=True), 1e-12)
    th, tw = texture.shape[:2]
    u = (weights @ uv[:, 0] * tw).astype(np.int64) % tw
    v = (weights @ uv[:, 1] * th).astype(np.int64) % th
    texel = texture[v, u]
    tint = weights @ col
    src = np.clip(texel[:, :3] * tint[:, :3], 0, 4)
    a = np.clip(texel[:, 3] * tint[:, 3] * alpha_factor, 0, 1)[:, None]
    dst = fb[miny:maxy + 1, minx:maxx + 1]
    dst[mask] = dst[mask] + src * a if additive else dst[mask] * (1 - a) + src * a


# --- CLI -----------------------------------------------------------------------------------------

def run(manifest: dict, out_dir: Path, only: list[str] | None = None,
        check_dir: Path | None = None, report: list[str] | None = None) -> dict[str, dict]:
    report = report if report is not None else []
    server_root = Path(manifest["server_root"])
    results: dict[str, dict] = {}
    for version, spec in manifest["versions"].items():
        if only and version not in only:
            continue
        if spec.get("publish") is False:
            # Scène jugée non présentable (brume sans le brouillard du moteur…) : on ne
            # dépose rien, et on retire un dépôt antérieur pour que l'index retombe sur
            # l'illustration de repli. `--only <version>` force quand même l'export.
            if not only:
                for name in ("scene.glb", "scene.json"):
                    (out_dir / version / name).unlink(missing_ok=True)
                report.append(f"NOTE : {version} — scène non publiée (publish: false), illustration de repli conservée")
                continue
        source = BinSource(
            [Path(d) for d in manifest.get("bin_dirs", [])] + [Path(d) for d in spec.get("bin_dirs", [])],
            list(manifest.get("pak_globs", [])) + list(spec.get("pak_globs", [])),
        )
        if not (server_root / "World" / "MainMenu" / spec["dir"]).is_dir():
            report.append(f"AVERTISSEMENT : {version} — arbre serveur absent : {server_root}")
            continue
        glb, meta, notes = build_scene(version, spec, server_root, source,
                                       int(spec.get("max_texture", manifest.get("max_texture", 512))))
        validate_glb(glb)
        target = out_dir / version
        target.mkdir(parents=True, exist_ok=True)
        hooks = hooks_for(version)
        if hooks.after_export is not None:
            hooks.after_export(target, meta, source, server_root)
        (target / "scene.glb").write_bytes(glb)
        (target / "scene.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
                                           encoding="utf-8")
        for note in notes:
            report.append(f"AVERTISSEMENT : {version} — {note}")
        stats = meta["stats"]
        print(f"{version:>5}  scene.glb  {len(glb) / 1024:.0f} Kio  "
              f"{stats['triangles']} triangles, {stats['textures']} textures, "
              f"{stats['animations']} animations")
        if check_dir is not None:
            check_dir.mkdir(parents=True, exist_ok=True)
            # Deux images : la pose de repos et la scène 3 s plus tard, pour voir bouger
            # ce que les courbes d'animation décodées produisent.
            rest = render_glb(glb, meta)
            later = render_glb(glb, meta, time=3.0)
            sheet = Image.new("RGB", (rest.width, rest.height * 2))
            sheet.paste(rest, (0, 0))
            sheet.paste(later, (0, rest.height))
            sheet.save(check_dir / f"glb-check-{version}.png")
            print(f"{version:>5}  contrôle → {check_dir / f'glb-check-{version}.png'}")
        results[version] = meta
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export glTF des scènes de menu animées")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--only", action="append", help="limiter à une version (répétable)")
    parser.add_argument("--check-dir", type=Path, default=None,
                        help="dossier où écrire un rendu logiciel de contrôle par version")
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    report: list[str] = []
    run(manifest, args.out, args.only, args.check_dir, report)
    for line in report:
        print(line, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
