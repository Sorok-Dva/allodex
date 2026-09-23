"""Décodeurs des ressources des cinématiques moteur dans les bases compilées 17.x (`tools/allods_bins17.py`).

Les décalages des ressources visuelles (`Geometry`, `Texture`, `VisObjectTemplate`,
`CreatureAnimationAction`) sont ceux relevés par la branche des fatalités
(`worktree-agent-a3b3f11f3ec5aecf4`, `tools/allods_visdb.py`, commit 5615126), repris ici sur la
couche `Ref` (qui suit les pointeurs d'une carte vers `pack.bin`). Les autres ont été établis pour
les cinématiques en retrouvant dans l'image binaire les valeurs des `.xdb` de l'arbre serveur 7.0
(septembre 2026) :

* `CameraTrackAction` (`BuffVisScripts` → `+0x48`) : deux vecteurs d'éléments de 20 octets
  `(8 octets inutilisés, f32 durée en secondes, f32 x, y, z)` — `cameraPoints` en `+0x48`,
  `targetPoints` en `+0x78` ; identiques, valeur pour valeur, au `.xdb` 7.0 de
  `AO12_Prologue04_Cutscene` ;
* `ClientData` → `+0x28` `CustomClientDataList` → `+0x30` vecteur de pointeurs vers les éléments :
  `CreatureVisActionData` (`+0x30` → action : `CreatureAnimationAction`, `Sound2DAction`,
  `Sound3DAction`…) et `UISubtitleShow` (`+0x30` vecteur d'éléments de 40 octets :
  `+0x04` `delayMs` = durée d'affichage, `+0x20` indice du texte dans `pack.*.loc`) ;
  `Sound3DAction` / `Sound2DAction` : `+0x78` nom de l'événement FMOD (`Cutscenes/…`) ;
* `MobWorld` : `+0x68` indice du nom, `+0xF8` `VisualMob` ; `VisualMob` : `+0x28`
  `VisCharacterTemplate` ; `VisCharacterTemplate` : `+0x90` `VisObjectTemplate` (corps),
  `+0xE8` nom du modèle (personnages joueurs), `+0xE0` échelle ;
* `MapRegion` (`Maps/<carte>/<bloc>/<i>_<j>_MapRegion.xdb` de la base de carte) : `+0xA0`
  vecteur d'objets de 72 octets `(8 inutilisés, f32 x, y, z, f32[4] rotation — le lacet en
  +0x20 —, f32 échelle en +0x28, pointeur StaticObject en +0x30)`, coordonnées locales à la
  région (256 m de côté : région `i_j` décalée de `(256·i, 256·j)`) ; `StaticObject` :
  `+0x30` `VisObjectTemplate` ;
* `GameViewScene` : `+0xA0` mobs (192 o : `+0x70` décalage x, y, z, `+0x80` scriptID,
  `+0xB0` VisualMob, `+0xB8` lacet), `+0xE8` MapResource, `+0xF0/+0xF8/+0x100` place x, y, z
  (doubles) ; `GameViewScript` : `+0x48` actions ; `ShowSceneAction` : `+0x50` scène,
  `+0x58` script.
"""
from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field

import numpy as np

from tools.allods_bins17 import TEXTURE_HIRES_REF, Base, Ref
from tools.extract_menu_scene import ElementSpec, GeometryDoc, Locator, MaterialSpec, VertexLayout

# --- Geometry (branche des fatalités) ---------------------------------------------------------

GEO_SKELETAL_ANIMATION = 0x28
GEO_AABB = 0x30
GEO_INDEX_BUFFER_SIZE = 0x118
GEO_MODEL_ELEMENTS = 0x168
GEO_ORIENTATION = 0x1A8
GEO_SCENE_NODES = 0x200
GEO_SKELETON_ID = 0x22C
GEO_SKELETON_SIZE = 0x230
GEO_VERTEX_BUFFER_SIZE = 0x248
GEO_VERTEX_DECLARATIONS = 0x250
ELEMENT_STRIDE = 192
EL_LODS = 0x28
EL_BLEND = 0x4C
EL_TEXTURE = 0x50
EL_TRANSPARENCY = 0x60
EL_U_SPEED = 0x64
EL_V_SPEED = 0x68
EL_BOOLS = 0x6C
EL_MATERIAL_NAME = 0x78
EL_NAME = 0x90
EL_SKIN_INDEX = 0xA8
NODE_STRIDE = 64
DECL_STRIDE = 116
DECL_ATTRIBUTES = {"color": 0x14, "indices": 0x20, "normal": 0x2C, "position": 0x38,
                   "texcoord0": 0x54, "weights": 0x6C}
DECL_STRIDE_FIELD = 0x40
DECL_UNUSED = 12
ORIENTATION = {0: "COMMON", 1: "WORLD_X", 2: "WORLD_Y", 3: "WORLD_Z", 4: "X_AXIS", 5: "Y_AXIS",
               6: "Z_AXIS", 7: "BILLBOARD"}
BLEND = {0: "BLEND_EFFECT_ADD", 1: "BLEND_EFFECT_ALPHA", 2: "BLEND_EFFECT_ALPHA_ADD",
         3: "BLEND_EFFECT_COLOR", 4: "BLEND_EFFECT_COLOR_ADD", 5: "BLEND_EFFECT_MUL",
         6: "BLEND_EFFECT_INVERSE"}
TEX_HEIGHT = 0x78
TEX_MIPS = 0x80
TEX_TYPE = 0x90
TEX_WIDTH = 0x94
TEXTURE_TYPES = {0: "DXT1", 1: "DXT3", 2: "DXT5", 3: "RGBA"}
VOT_DEFAULT_STATE = 0x28
VOT_GEOMETRY = 0xC0
VOT_PARTICLE = 0xC8
VOT_SCALE = 0xE8
VOT_STATES = 0x118
VOT_COMPONENTS = 0x138
STATE_STRIDE = 144
STATE_ANIMATION = 0x80
COMP_LOCATOR = 0x48
COMP_OFFSET = 0x60
COMP_ROTATION = 0x70
COMP_SCALE = 0x80
COMP_VISOBJECT = 0x88
ANIM_SPEED = 0xC8
ANIM_LIST = 0xE0
ANIM_MODE = 0x118

# --- cinématiques (ce module) -----------------------------------------------------------------

BUFF_VIS_SCRIPTS = 0x148
VIS_SCRIPTS_ACTION = 0x48
CAM_POINTS = 0x48
CAM_TARGETS = 0x78
CAM_POINT_STRIDE = 20
CLIENT_DATA_LIST = 0x28
LIST_ELEMENTS = 0x30
VIS_ACTION_DATA_ACTION = 0x30
SUBTITLE_ITEMS = 0x30
SUBTITLE_STRIDE = 40
SUBTITLE_DELAY = 0x04
SUBTITLE_TEXT = 0x20
SOUND_NAME = 0x78
MOB_NAME = 0x68
MOB_VISUAL = 0xF8
VISUAL_MOB_CHARACTER = 0x28
CHAR_VISOBJECT = 0x90
CHAR_SCALE = 0xE0
CHAR_MODEL = 0xE8
REGION_OBJECTS = 0xA0
REGION_OBJECT_STRIDE = 72
STATIC_VISOBJECT = 0x30
REGION_SIZE = 256.0


def _vec3(ref: Ref, rel: int) -> tuple[float, float, float]:
    return tuple(float(v) for v in ref.floats(rel, 3))


# --- ressources visuelles ---------------------------------------------------------------------

@dataclass
class TextureInfo:
    binary: str | None
    binary_hi: str | None
    width: int
    height: int
    fmt: str


def read_texture(ref: Ref) -> TextureInfo:
    binary = ref.binary()
    hi = ref.binary(TEXTURE_HIRES_REF)
    if hi is None and binary:
        hi = binary[:-4] + ".hi.bin"
    return TextureInfo(binary, hi, ref.u32(TEX_WIDTH), ref.u32(TEX_HEIGHT),
                       TEXTURE_TYPES.get(ref.u32(TEX_TYPE), "?"))


@dataclass
class GeometryInfo:
    ref: Ref
    binary: str | None
    doc: GeometryDoc
    orientation: str
    textures: dict[str, Ref] = field(default_factory=dict)


def read_vertex_layout(ref: Ref) -> VertexLayout:
    values = {}
    for name, rel in DECL_ATTRIBUTES.items():
        offset, kind = ref.u32(rel), ref.u32(rel + 4)
        values[name] = None if kind == DECL_UNUSED or offset >= 255 else offset
    return VertexLayout(stride=ref.u32(DECL_STRIDE_FIELD), **values)


def read_geometry(ref: Ref) -> GeometryInfo:
    doc = GeometryDoc()
    aabb = ref.floats(GEO_AABB, 6)
    doc.aabb = (np.array(aabb[:3]), np.array(aabb[3:]))
    doc.index_buffer_size = ref.u32(GEO_INDEX_BUFFER_SIZE)
    doc.vertex_buffer_size = ref.u32(GEO_VERTEX_BUFFER_SIZE)
    if ref.u32(GEO_SKELETON_SIZE):
        doc.skeleton_id = ref.u32(GEO_SKELETON_ID)
    anim = ref.ptr(GEO_SKELETAL_ANIMATION)
    doc.animation_href = anim.binary() if anim is not None else None
    for decl in ref.elements(GEO_VERTEX_DECLARATIONS, DECL_STRIDE):
        doc.layouts.append(read_vertex_layout(decl))
    for node in ref.elements(GEO_SCENE_NODES, NODE_STRIDE):
        doc.locators.append(Locator(name=node.string(0x08) or "", position=_vec3(node, 0x20),
                                    rotation=tuple(float(v) for v in node.floats(0x2C, 4)),
                                    scale=node.f32(0x3C)))
    textures: dict[str, Ref] = {}
    for el in ref.elements(GEO_MODEL_ELEMENTS, ELEMENT_STRIDE):
        lods = el.elements(EL_LODS, 20)
        if not lods:
            continue
        ib0, ib1, vb0, vb1 = (lods[0].u32(4 * k) for k in range(1, 5))
        flags = el.bytes(EL_BOOLS, 7)
        tex = el.ptr(EL_TEXTURE)
        tex_name = tex.binary() if tex is not None else None
        if tex_name:
            textures[tex_name] = tex
        mat = MaterialSpec(name=el.string(EL_MATERIAL_NAME) or "?", texture=tex_name,
                           blend=BLEND.get(el.u32(EL_BLEND), "BLEND_EFFECT_ALPHA"),
                           transparent=bool(flags[3]), visible=bool(flags[6]),
                           alpha=el.f32(EL_TRANSPARENCY),
                           uv_scroll=(el.f32(EL_U_SPEED), el.f32(EL_V_SPEED)))
        doc.elements.append(ElementSpec(name=el.string(EL_NAME) or "?", ib0=ib0, ib1=ib1, vb0=vb0,
                                        vb1=vb1, material=mat, skin_index=el.i32(EL_SKIN_INDEX)))
    return GeometryInfo(ref, ref.binary(), doc, ORIENTATION.get(ref.u32(GEO_ORIENTATION), "COMMON"), textures)


@dataclass
class Component:
    locator: str
    offset: tuple[float, float, float]
    rotation: tuple[float, float, float, float]
    scale: float
    visobject: Ref | None


@dataclass
class VisObject:
    ref: Ref
    geometry: Ref | None
    particle: Ref | None
    animation: Ref | None
    scale: float
    components: list[Component]


def read_visobject(ref: Ref) -> VisObject:
    states = ref.elements(VOT_STATES, STATE_STRIDE)
    animation = states[0].ptr(STATE_ANIMATION) if states else None
    if animation is None:
        animation = ref.ptr(VOT_DEFAULT_STATE + STATE_ANIMATION)
    geometry = ref.ptr(VOT_GEOMETRY)
    if animation is None and geometry is not None:
        animation = geometry.ptr(GEO_SKELETAL_ANIMATION)
    components = []
    for comp in ref.pointers(VOT_COMPONENTS):
        if comp.type != "AttachedVisObjectComponent":
            continue
        components.append(Component(comp.string(COMP_LOCATOR) or "", _vec3(comp, COMP_OFFSET),
                                    tuple(float(v) for v in comp.floats(COMP_ROTATION, 4)),
                                    comp.f32(COMP_SCALE), comp.ptr(COMP_VISOBJECT)))
    return VisObject(ref, geometry, ref.ptr(VOT_PARTICLE), animation, ref.f32(VOT_SCALE), components)


# --- noms d'animations ------------------------------------------------------------------------

def animation_names(pack: Base) -> dict[int, str]:
    """Indice de l'énumération `Animations` → nom, relu dans les propriétés d'animation du client
    (`u32 indice, pad, chaîne`), vote majoritaire par indice (méthode de la branche des fatalités)."""
    pb = pack.pb
    keys, targets = pb._rkeys, pb._rtarget
    mask = (keys & 3) == 1
    votes: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    for k, t in zip(keys[mask].tolist(), targets[mask].tolist()):
        loc = k >> 2
        n = pb.u32(loc + 8)
        if not 3 <= n < 48:
            continue
        s = bytes(pb.bytes_at(t, n))
        if not re.fullmatch(rb"[a-z][A-Za-z0-9_]+", s):
            continue
        idx = pb.u32(loc - 8)
        if idx < 4000:
            votes[idx][s.decode()] += 1
    return {i: c.most_common(1)[0][0] for i, c in votes.items()}


# --- cinématiques -----------------------------------------------------------------------------

@dataclass
class CameraTrack:
    points: list[tuple[float, tuple[float, float, float]]]
    targets: list[tuple[float, tuple[float, float, float]]]

    @property
    def duration(self) -> float:
        return sum(d for d, _ in self.points)


def read_camera_track(action: Ref) -> CameraTrack:
    def pts(rel: int):
        return [(round(e.f32(4), 4), tuple(round(v, 4) for v in _vec3(e, 8)))
                for e in action.elements(rel, CAM_POINT_STRIDE)]
    return CameraTrack(pts(CAM_POINTS), pts(CAM_TARGETS))


def buff_camera_track(buff: Ref) -> CameraTrack | None:
    scripts = buff.ptr(BUFF_VIS_SCRIPTS)
    action = scripts.ptr(VIS_SCRIPTS_ACTION) if scripts is not None else None
    if action is None or action.type != "CameraTrackAction":
        return None
    return read_camera_track(action)


@dataclass
class ClientLine:
    text_index: int | None
    delay_ms: int
    voice: str | None
    animations: list[int]


def read_client_line(client_data: Ref) -> ClientLine:
    """Réplique d'un `ClientData` : sous-titre (texte + durée), voix, animations du locuteur."""
    lst = client_data.ptr(CLIENT_DATA_LIST)
    line = ClientLine(None, 0, None, [])
    for element in (lst.pointers(LIST_ELEMENTS) if lst is not None else []):
        kind = element.type
        if kind == "UISubtitleShow":
            items = element.elements(SUBTITLE_ITEMS, SUBTITLE_STRIDE)
            if items:
                line.delay_ms = items[0].u32(SUBTITLE_DELAY)
                line.text_index = items[0].u32(SUBTITLE_TEXT)
        elif kind == "CreatureVisActionData":
            action = element.ptr(VIS_ACTION_DATA_ACTION)
            akind = action.type if action is not None else None
            if akind == "CreatureAnimationAction":
                data, size = action.vector(ANIM_LIST)
                line.animations += [data.u32(4 * k) for k in range(size // 4)] if data else []
            elif akind in ("Sound2DAction", "Sound3DAction"):
                line.voice = action.string(SOUND_NAME)
    return line


def mob_name_index(mob: Ref) -> int:
    return mob.u32(MOB_NAME)


def mob_visual(mob: Ref) -> Ref | None:
    return mob.ptr(MOB_VISUAL)


@dataclass
class CharacterTemplate:
    ref: Ref
    visobject: Ref | None
    model: str | None
    scale: float


def visual_character(visual_mob: Ref) -> CharacterTemplate | None:
    tpl = visual_mob.ptr(VISUAL_MOB_CHARACTER)
    if tpl is None or tpl.type != "VisCharacterTemplate":
        return None
    return CharacterTemplate(tpl, tpl.ptr(CHAR_VISOBJECT), tpl.string(CHAR_MODEL), tpl.f32(CHAR_SCALE))


@dataclass
class PlacedObject:
    region: str
    index: int
    position: tuple[float, float, float]
    rotation: tuple[float, float, float, float]
    scale: float
    static_object: Ref | None

    @property
    def yaw(self) -> float:
        return self.rotation[3]


def region_origin(path: str) -> tuple[float, float]:
    """`Maps/X/000_000/1_0_MapRegion.xdb` → origine (x, y) de la région en mètres."""
    m = re.search(r"/(\d+)_(\d+)/(\d+)_(\d+)_MapRegion", path)
    if not m:
        return 0.0, 0.0
    bx, by, i, j = (int(g) for g in m.groups())
    return (bx + i) * REGION_SIZE, (by + j) * REGION_SIZE


def read_regions(map_base: Base) -> list[PlacedObject]:
    out: list[PlacedObject] = []
    for path, region in sorted(map_base.paths().items()):
        if not path.endswith("_MapRegion.xdb"):
            continue
        ox, oy = region_origin(path)
        for k, e in enumerate(region.elements(REGION_OBJECTS, REGION_OBJECT_STRIDE)):
            x, y, z = _vec3(e, 8)
            out.append(PlacedObject(path, k, (x + ox, y + oy, z), tuple(float(v) for v in e.floats(20, 4)),
                                    e.f32(0x28), e.ptr(0x30)))
    return out


def static_visobject(static_object: Ref | None) -> Ref | None:
    if static_object is None or static_object.type != "StaticObject":
        return None
    return static_object.ptr(STATIC_VISOBJECT)


# --- personnages : objets visuels (`VisualItem`) et patchs de texture -------------------------
# Établi sur `Plate_E_17DemonhunterPaladinArmor` (armure, 7.0 et 17.0) : trois `armorShapes`
# (robe_0 ; hipguards L/R aux locators Slot_Hip_BL/BR), neuf géosets cachés, deux locators cachés,
# patchs de texture femme/homme aux rectangles du `.xdb`.

VM_DRESS = 0x60                # vecteur (24 o : +0x08 VisualItem, +0x10 emplacement)
VM_DRESS_STRIDE = 24
VM_VARIATIONS = (0xE0, 0xE8, 0xF0, 0xF8, 0x100)   # visage, pilosité, coiffure… (VisualItem)
CHAR_DEFAULT_DRESS = 0xA0      # VisCharacterTemplate → VisualItem « tenue par défaut »
VI_SHAPES = 0x70               # armorShapes (96 o)
VI_SHAPE_STRIDE = 96
SHAPE_SCENE = 0x08             # VisObjectTemplate accroché
SHAPE_LOCATOR = 0x18
SHAPE_TEXTURE = 0x38           # texture de remplacement du géoset
SHAPE_NAME = 0x40
VI_SLOT = 0xD8
VI_HIDDEN_GEOSETS = 0x178      # vecteur de chaînes (24 o)
VI_HIDDEN_LOCATORS = 0x1E0
VI_TEXTURE_PATCHES = (0x90, 0x228, 0x258)
TP_LISTS = {"female": 0x28, "male": 0x48, "unisex": 0x68}
PATCH_STRIDE = 32              # +0x08 x1, x2, y1, y2 (f32), +0x18 Texture


@dataclass
class Shape:
    name: str | None
    locator: str | None
    scene: Ref | None
    texture: Ref | None


@dataclass
class VisualItem:
    ref: Ref
    slot: int
    shapes: list[Shape]
    hidden: list[str]
    hidden_locators: list[str]
    patches: dict[str, list[tuple[float, float, float, float, Ref | None]]]


def _strings(ref: Ref, rel: int) -> list[str]:
    return [s for s in (e.string(0) for e in ref.elements(rel, 24)) if s]


def read_visual_item(ref: Ref) -> VisualItem:
    shapes = [Shape(e.string(SHAPE_NAME), e.string(SHAPE_LOCATOR), e.ptr(SHAPE_SCENE), e.ptr(SHAPE_TEXTURE))
              for e in ref.elements(VI_SHAPES, VI_SHAPE_STRIDE)]
    patches: dict[str, list] = {"female": [], "male": [], "unisex": []}
    for rel in VI_TEXTURE_PATCHES:
        tp = ref.ptr(rel)
        if tp is None or tp.type != "TexturePatch":
            continue
        for key, lrel in TP_LISTS.items():
            for e in tp.elements(lrel, PATCH_STRIDE):
                patches[key].append((*(round(v, 5) for v in e.floats(8, 4)), e.ptr(0x18)))
    return VisualItem(ref, ref.u32(VI_SLOT), shapes, _strings(ref, VI_HIDDEN_GEOSETS),
                      _strings(ref, VI_HIDDEN_LOCATORS), patches)


def dressed_items(visual_mob: Ref) -> tuple[VisualItem | None, list[VisualItem], list[VisualItem]]:
    """(tenue par défaut du gabarit, variations du visage et des cheveux, objets portés)."""
    tpl = visual_mob.ptr(VISUAL_MOB_CHARACTER)
    default = tpl.ptr(CHAR_DEFAULT_DRESS) if tpl is not None else None
    variations = [read_visual_item(v) for v in (visual_mob.ptr(o) for o in VM_VARIATIONS)
                  if v is not None and v.type == "VisualItem"]
    dress = [read_visual_item(v) for v in (e.ptr(8) for e in visual_mob.elements(VM_DRESS, VM_DRESS_STRIDE))
             if v is not None and v.type == "VisualItem"]
    return (read_visual_item(default) if default is not None and default.type == "VisualItem" else None), variations, dress
