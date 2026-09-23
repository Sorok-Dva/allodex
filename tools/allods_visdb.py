"""Décodeurs typés des ressources visuelles de `pack.bin` (voir `tools/allods_packdb.py`).

Chaque décalage ci-dessous a été établi sur les ressources présentes à la fois dans le client
RU récent et dans l'arbre serveur 7.0 (fatalités de classe : `FatalityWarrior`,
`Fatality_AuraWar`, `FatalityWarrior_Fire`…) en retrouvant dans l'image binaire les valeurs de
leurs `.xdb` : boîtes englobantes, tailles des tampons, vitesses de défilement UV, fondus,
échelles, noms de locators. L'ordre des champs est celui des éléments des `.xdb` (champs non
booléens puis booléens) ; les décalages absolus, eux, sont propres à chaque structure.

Énumérations telles que stockées par le client RU (elles diffèrent parfois du schéma 7.0) :

* `Geometry.orientationMode` : 0 COMMON, 1 WORLD_X, 3 WORLD_Z, 5 Y_AXIS, 6 Z_AXIS,
  7 BILLBOARD (vérifié sur `DummyWorldZed`, `StellaSmoke`, `Turret_All_Channel_Cast`,
  `EngineerGun_E_50_PowerNihaz_03Blue` et quatre géométries Z_AXIS des fatalités) ;
* `BlendEffect` : 0 ADD, 1 ALPHA… (schéma 7.0 inchangé) ;
* `Texture.type` : 0 DXT1, 1 DXT3, 2 DXT5, 3 RGBA ;
* `Animations` : indices du schéma 7.0 jusqu'à 1402 ; au-delà, relus dans les propriétés
  d'animation du client (1591 `deathFatality`, 1594 `deathFatalityPhoenix`,
  1609 `deathFatalityTree`…), voir `animation_names`.
"""
from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field

import numpy as np

from tools.allods_packdb import PackDB, PakCatalog, TEXTURE_HIRES_REF
from tools.extract_menu_scene import ElementSpec, GeometryDoc, Locator, MaterialSpec, VertexLayout

# --- Geometry ---------------------------------------------------------------------------------

GEO_SKELETAL_ANIMATION = 0x28
GEO_AABB = 0x30
GEO_GEOMETRY_BOX = 0xCC
GEO_INDEX_BUFFER_SIZE = 0x118
GEO_MODEL_ELEMENTS = 0x168
GEO_ORIENTATION = 0x1A8
GEO_SCENE_NODES = 0x200
GEO_SKELETON_ID = 0x22C
GEO_SKELETON_SIZE = 0x230
GEO_SORT_MODE = 0x238
GEO_VERTEX_BUFFER_SIZE = 0x248
GEO_VERTEX_DECLARATIONS = 0x250

ELEMENT_STRIDE = 192
EL_LODS = 0x28                 # vecteur de fragments (20 o : _, ib0, ib1, vb0, vb1)
EL_BLEND = 0x4C
EL_TEXTURE = 0x50
EL_TRANSPARENCY = 0x60
EL_U_SPEED = 0x64
EL_V_SPEED = 0x68
EL_BOOLS = 0x6C                # scrollAlpha, scrollRGB, ignoreDiffuseAlpha, transparent, useFog, useModifiers, visible
EL_MATERIAL_NAME = 0x78
EL_NAME = 0x90
EL_SKIN_INDEX = 0xA8
EL_PARAMS = 0x58               # MaterialParams (polymorphe)
PARAMS_ENV_TEXTURE = 0x48      # CommonMaterialParams.envReflectionTexture

NODE_STRIDE = 64
NODE_NAME = 0x08
NODE_POSITION = 0x20
NODE_ROTATION = 0x2C
NODE_SCALE = 0x3C

DECL_STRIDE = 116
# Attribut → décalage de son couple (offset, type) dans une déclaration de sommets.
DECL_ATTRIBUTES = {"bitangent": 0x08, "color": 0x14, "indices": 0x20, "normal": 0x2C,
                   "position": 0x38, "tangent": 0x48, "texcoord0": 0x54, "texcoord1": 0x60,
                   "weights": 0x6C}
DECL_STRIDE_FIELD = 0x40
DECL_UNUSED = 12

ORIENTATION = {0: "COMMON", 1: "WORLD_X", 2: "WORLD_Y", 3: "WORLD_Z", 4: "X_AXIS",
               5: "Y_AXIS", 6: "Z_AXIS", 7: "BILLBOARD"}
BLEND = {0: "BLEND_EFFECT_ADD", 1: "BLEND_EFFECT_ALPHA", 2: "BLEND_EFFECT_ALPHA_ADD",
         3: "BLEND_EFFECT_COLOR", 4: "BLEND_EFFECT_COLOR_ADD", 5: "BLEND_EFFECT_MUL",
         6: "BLEND_EFFECT_INVERSE"}
SORT_MODE = {0: "OFFSETS", 1: "FRONT_BACK", 2: "BACK_FRONT"}

# --- Texture ----------------------------------------------------------------------------------

TEX_HEIGHT = 0x78
TEX_MIPS = 0x80
TEX_TYPE = 0x90
TEX_WIDTH = 0x94
TEXTURE_TYPES = {0: "DXT1", 1: "DXT3", 2: "DXT5", 3: "RGBA"}

# --- VisObjectTemplate ------------------------------------------------------------------------

VOT_DEFAULT_STATE = 0x28
VOT_FADE_IN = 0xB8
VOT_FADE_OUT = 0xBC
VOT_GEOMETRY = 0xC0
VOT_PARTICLE = 0xC8
VOT_SCALE = 0xE8
VOT_SOUND_NAME = 0xF8
VOT_STATES = 0x118
VOT_COMPONENTS = 0x138
STATE_STRIDE = 144
STATE_ANIMATION = 0x80

COMPONENT_ID = 0x28            # VisualObjectComponentID
DELAY_CHILD = 0x48             # DelayComponent : composant retardé, puis timeMin, timeMax
DELAY_TIME_MIN = 0x50
STOP_IDS = 0x48                # StopVisObjectComponents : vecteur de chaînes (24 o chacune)
COMP_LOCATOR = 0x48
COMP_OFFSET = 0x60
COMP_ROTATION = 0x70
COMP_SCALE = 0x80
COMP_VISOBJECT = 0x88

# --- VisActions -------------------------------------------------------------------------------

ACTION_ID = 0x28
LIST_ELEMENTS = 0x48
LIST_PLAY = 0x68               # 0 InSequence, 1 Simultaneously
LIST_PLAY_WHILE = 0x70
LIST_PRECONDITIONAL = 0x78     # booléens : preconditional, restartOnVisualChange, stopOnDeath,
LIST_STOP_WHILE = 0x7B         # stopWhileWhenElementsEnded (vrai par défaut)
DELAY_TIME = 0x44              # ms
SCALE_VALUE = 0x44
TRANSP_FADE_MULT = 0x44
TRANSP_PRIORITY = 0x48
TRANSP_VALUE = 0x4C
FX_LIFETIME = 0x48
FX_OFFSET = 0x4C
FX_ROTATION = 0x58
FX_SCALE = 0x64
FX_VISOBJECT = 0x70
FX_IS_RELATIVE = 0x78
ANIM_SPEED = 0xC8              # AdvancedAnimationParams.speed (0 = vitesse normale)
ANIM_LIST = 0xE0               # vecteur d'u32 (indices de l'énumération Animations)
ANIM_CHANNEL = 0x100
ANIM_OVERRIDE = 0x108
ANIM_MODE = 0x118              # 0 DIE, 1 LOOP, 2 CLAMP
EFFECTS_LIST = 0x48
EFFECT_STRIDE = 176
EFFECT_FX = 0x40
EFFECT_FADE_IN = 0x48
EFFECT_FADE_OUT = 0x4C
EFFECT_SCALE = 0x50
EFFECT_LOCATOR = 0x60
EFFECT_LOCATOR_NAME = 0x68
EFFECT_MEMBER = 0x80
EFFECT_OFFSET = 0x88
PREDICATE_FLAG = 0x48
PREDICATE_TEMPLATES = 0x48
TEMPLATE_NAME = 0xE8
CHANNEL_FX = 0x58             # CreatureChannelDirectAction : channelingFx
CHANNEL_END = 0x60            # endPoint (VisPoint)
CHANNEL_FADE_IN = 0x68        # ms
CHANNEL_FADE_OUT = 0x6C       # ms
CHANNEL_LENGTH = 0x70         # fxLength : longueur modelée du rayon (m)
CHANNEL_VELOCITY = 0x98
CHANNEL_START = 0xB0          # startPoint (VisPoint)
POINT_SHIFT = 0x24            # VisPoint.shift (vec3), puis VisPointLocator : locator, nom
POINT_LOCATOR = 0x38
POINT_LOCATOR_NAME = 0x40
SHAKE_PARAMS = 0x48
SHAKE_FIELDS = 0x20            # 8 flottants bruts de CameraShakeParameters

FX_LOCATORS = ["Global", "Head", "Chest", "Slot_Hand_L", "Slot_Hand_R", "Slot_Shoulder_L",
               "Slot_Shoulder_R", "Slot_FX", "Slot_TopFX", "Slot_Mouth", "Slot_Global",
               "Slot_Head", "Slot_BodyFX", "Wand_Slot_FX", "UsedObject_Slot_FX", "Slot_Glove_L",
               "Slot_Glove_R", "Slot_Locket", "Slot_Belt", "FROM_LOCATOR_NAME"]

# --- SlonRoot ---------------------------------------------------------------------------------

SLON_PATH = "Interface/System/SlonSettings.(SlonRoot).xdb"
SLON_FATALITIES = 0xD0
FATALITY_STRIDE = 40
FAT_CASTER = 0x08
FAT_FADE_DURATION = 0x10
FAT_FADE_START = 0x14
FAT_OFFENDER = 0x18
FAT_SPARK_DELAY = 0x20
FAT_TYPE = 0x24


def _vec3(db: PackDB, off: int) -> tuple[float, float, float]:
    return tuple(float(v) for v in db.floats(off, 3))


@dataclass
class TextureInfo:
    offset: int
    binary: str | None
    binary_hi: str | None
    width: int
    height: int
    fmt: str
    mips: int


def read_texture(db: PackDB, cat: PakCatalog, off: int) -> TextureInfo:
    """Le second fichier (`.hi.bin`, niveaux de mipmap les plus fins) vit dans un pak `*.HiRes`
    dont le code n'est pas voté : on le retrouve par son nom, celui du `.bin` suffixé."""
    binary = cat.name(db.binary_ref(off))
    hi = cat.name(db.file_ref(off, TEXTURE_HIRES_REF))
    if hi is None and binary:
        hi = binary[:-4] + ".hi.bin"
    return TextureInfo(off, binary, hi, db.u32(off + TEX_WIDTH),
                       db.u32(off + TEX_HEIGHT), TEXTURE_TYPES.get(db.u32(off + TEX_TYPE), "?"),
                       db.u32(off + TEX_MIPS))


@dataclass
class GeometryInfo:
    offset: int
    binary: str | None
    doc: GeometryDoc
    orientation: str
    sort_mode: str
    textures: dict[str, int] = field(default_factory=dict)   # nom de binaire → décalage Texture


def read_vertex_layout(db: PackDB, off: int) -> VertexLayout:
    values = {}
    for name, rel in DECL_ATTRIBUTES.items():
        offset, kind = db.u32(off + rel), db.u32(off + rel + 4)
        values[name] = None if kind == DECL_UNUSED or offset >= 255 else offset
    return VertexLayout(stride=db.u32(off + DECL_STRIDE_FIELD), position=values["position"],
                        texcoord0=values["texcoord0"], color=values["color"], normal=values["normal"],
                        weights=values["weights"], indices=values["indices"])


def read_geometry(db: PackDB, cat: PakCatalog, off: int) -> GeometryInfo:
    doc = GeometryDoc()
    aabb = db.floats(off + GEO_AABB, 6)
    doc.aabb = (np.array(aabb[:3]), np.array(aabb[3:]))
    box = db.floats(off + GEO_GEOMETRY_BOX, 6)
    doc.geometry_box = (np.array(box[:3]), np.array(box[3:]))
    doc.index_buffer_size = db.u32(off + GEO_INDEX_BUFFER_SIZE)
    doc.vertex_buffer_size = db.u32(off + GEO_VERTEX_BUFFER_SIZE)
    if db.u32(off + GEO_SKELETON_SIZE):
        doc.skeleton_id = db.u32(off + GEO_SKELETON_ID)
    anim = db.ptr(off + GEO_SKELETAL_ANIMATION)
    doc.animation_href = cat.name(db.binary_ref(anim)) if anim is not None else None
    for decl in db.elements(off + GEO_VERTEX_DECLARATIONS, DECL_STRIDE):
        doc.layouts.append(read_vertex_layout(db, decl))
    for node in db.elements(off + GEO_SCENE_NODES, NODE_STRIDE):
        doc.locators.append(Locator(name=db.string(node + NODE_NAME) or "",
                                    position=_vec3(db, node + NODE_POSITION),
                                    rotation=tuple(float(v) for v in db.floats(node + NODE_ROTATION, 4)),
                                    scale=db.f32(node + NODE_SCALE)))
    textures: dict[str, int] = {}
    for el in db.elements(off + GEO_MODEL_ELEMENTS, ELEMENT_STRIDE):
        lods = db.elements(el + EL_LODS, 20)
        if not lods:
            continue
        ib0, ib1, vb0, vb1 = (db.u32(lods[0] + 4 * k) for k in range(1, 5))
        flags = db.bytes(el + EL_BOOLS, 7)
        tex = db.ptr(el + EL_TEXTURE)
        tex_name = cat.name(db.binary_ref(tex)) if tex is not None else None
        if tex_name:
            textures[tex_name] = tex
        mat = MaterialSpec(name=db.string(el + EL_MATERIAL_NAME) or "?", texture=tex_name,
                           blend=BLEND.get(db.u32(el + EL_BLEND), "BLEND_EFFECT_ALPHA"),
                           transparent=bool(flags[3]), visible=bool(flags[6]),
                           alpha=db.f32(el + EL_TRANSPARENCY),
                           uv_scroll=(db.f32(el + EL_U_SPEED), db.f32(el + EL_V_SPEED)))
        params = db.ptr(el + EL_PARAMS)
        if params is not None and db.vtype(params) == "CommonMaterialParams":
            env = db.ptr(params + PARAMS_ENV_TEXTURE)
            # Texture d'environnement : `SoftGeometryGrain*` sert de masque d'alpha indexé par la
            # normale vue de la caméra (disque blanc = bords estompés, « géométrie douce »).
            mat.env_texture = cat.name(db.binary_ref(env)) if env is not None else None
        doc.elements.append(ElementSpec(name=db.string(el + EL_NAME) or "?", ib0=ib0, ib1=ib1,
                                        vb0=vb0, vb1=vb1, material=mat,
                                        skin_index=db.i32(el + EL_SKIN_INDEX)))
    return GeometryInfo(off, cat.name(db.binary_ref(off)), doc,
                        ORIENTATION.get(db.u32(off + GEO_ORIENTATION), "COMMON"),
                        SORT_MODE.get(db.u32(off + GEO_SORT_MODE), "OFFSETS"), textures)


# --- objets visuels ---------------------------------------------------------------------------

@dataclass
class Component:
    locator: str
    offset: tuple[float, float, float]
    rotation: tuple[float, float, float, float]
    scale: float
    visobject: int | None
    ident: str = ""
    start: float = 0.0                 # `DelayComponent` : apparition retardée (s)
    stop: float | None = None          # `StopVisObjectComponents` retardé : disparition (s)
    random_delay: bool = False         # timeMin ≠ timeMax : délai tiré au hasard par le client


@dataclass
class VisObject:
    offset: int
    name: str
    geometry: int | None
    particle: int | None
    animation: int | None
    scale: float
    fade_in_ms: int
    fade_out_ms: int
    sound: str | None
    components: list[Component]


def vot_name(db: PackDB, cat: PakCatalog, off: int) -> str:
    """Nom lisible d'un gabarit : celui du binaire de sa géométrie (ou de ses particules)."""
    for rel in (VOT_GEOMETRY, VOT_PARTICLE):
        target = db.ptr(off + rel)
        name = cat.name(db.binary_ref(target)) if target is not None else None
        if name:
            return re.sub(r"\.\([A-Za-z]+\)\.bin$", "", name.split("/")[-1])
    return f"vot_{off:x}"


def read_visobject(db: PackDB, cat: PakCatalog, off: int) -> VisObject:
    states = db.elements(off + VOT_STATES, STATE_STRIDE)
    animation = db.ptr(states[0] + STATE_ANIMATION) if states else None
    if animation is None:
        animation = db.ptr(off + VOT_DEFAULT_STATE + STATE_ANIMATION)
    geometry = db.ptr(off + VOT_GEOMETRY)
    if animation is None and geometry is not None:
        animation = db.ptr(geometry + GEO_SKELETAL_ANIMATION)
    components = []
    stops: list[tuple[float, list[str]]] = []

    def visit(comp: int, delay: float, ident: str, random_delay: bool) -> None:
        kind = db.vtype(comp)
        ident = db.string(comp + COMPONENT_ID) or ident
        if kind == "DelayComponent":
            tmin, tmax = db.floats(comp + DELAY_TIME_MIN, 2)
            child = db.ptr(comp + DELAY_CHILD)
            if child is not None:
                visit(child, delay + float(tmin), ident, random_delay or abs(tmax - tmin) > 1e-6)
        elif kind == "StopVisObjectComponents":
            v = db.vec(comp + STOP_IDS)
            ids = [db.string(v[0] + 24 * k) or "" for k in range(v[1] // 24)] if v else []
            stops.append((delay, ids))
        elif kind == "AttachedVisObjectComponent":
            components.append(Component(locator=db.string(comp + COMP_LOCATOR) or "",
                                        offset=_vec3(db, comp + COMP_OFFSET),
                                        rotation=tuple(float(v) for v in db.floats(comp + COMP_ROTATION, 4)),
                                        scale=db.f32(comp + COMP_SCALE),
                                        visobject=db.ptr(comp + COMP_VISOBJECT),
                                        ident=ident, start=round(delay, 4), random_delay=random_delay))

    for comp in db.pointers(off + VOT_COMPONENTS):
        visit(comp, 0.0, "", False)
    # Un arrêt ne vaut que pour un composant déjà apparu (`MuseL` du Barde : arrêté à 7,85 s,
    # apparu à 7,87 s, il reste).
    for when, ids in stops:
        for c in components:
            if c.ident and c.ident in ids and when > c.start and (c.stop is None or when < c.stop):
                c.stop = round(when, 4)
    return VisObject(off, vot_name(db, cat, off), geometry, db.ptr(off + VOT_PARTICLE), animation,
                     db.f32(off + VOT_SCALE), db.i32(off + VOT_FADE_IN), db.i32(off + VOT_FADE_OUT),
                     db.string(off + VOT_SOUND_NAME), components)


# --- particules -------------------------------------------------------------------------------

PART_EMITTERS = 0x28
PART_END_FRAME = 0xC0
PART_LOOP_FRAME = 0xD4
PART_SPEED = 0x100
PART_TEXTURES = 0x138
PART_LOOPED = 0x158
EMITTER_STRIDE = 88
EM_BLEND = 0x04               # 0 ALPHA, 1 ADD (énumération propre aux particules)
EM_COLOR = 0x08               # ARGB, 0x80 = neutre
EM_RENDER = 0x0C              # 0 STD_MODE (face caméra), 1 Z_QUAD, 2 Z_BOX
EM_NAME = 0x28
EM_PIVOT = 0x40
EM_VIRTUAL_OFFSET = 0x48
EM_BOOLS = 0x4C               # UseLooping, WorldSpaceEmitter, decalEmitter, decalInheritRotation,
                              # distortionEmitter, texFlipX, texFlipY, useScaleForVirtualOffset
ELEMENT_ATLAS = 0x28
ATLAS_TEXTURE = 0x28
ATLAS_SOURCES = 0x30
SOURCE_STRIDE = 48
SOURCE_ELEMENT = 0x08
SOURCE_HEIGHT = 0x04
SOURCE_WIDTH = 0x10
SOURCE_X = 0x14
SOURCE_Y = 0x20


@dataclass
class ParticleEmitterInfo:
    name: str
    additive: bool
    color: tuple[int, int, int, int]      # R G B A (0x80 = neutre)
    render: int
    pivot: tuple[float, float]
    virtual_offset: float
    looping: bool
    world_space: bool
    flip: tuple[bool, bool]


@dataclass
class ParticleInfo:
    offset: int
    binary: str | None
    speed: float
    looped: bool
    end_frame: int
    loop_frame: int
    emitters: list[ParticleEmitterInfo]
    textures: list[int]                   # décalages des TextureSingleElement


def read_particle_animation(db: PackDB, cat: PakCatalog, off: int) -> ParticleInfo:
    emitters = []
    for e in db.elements(off + PART_EMITTERS, EMITTER_STRIDE):
        argb = db.u32(e + EM_COLOR)
        flags = db.bytes(e + EM_BOOLS, 8)
        emitters.append(ParticleEmitterInfo(
            name=db.string(e + EM_NAME) or "", additive=db.u32(e + EM_BLEND) == 1,
            color=((argb >> 16) & 255, (argb >> 8) & 255, argb & 255, (argb >> 24) & 255),
            render=db.u32(e + EM_RENDER), pivot=tuple(float(v) for v in db.floats(e + EM_PIVOT, 2)),
            virtual_offset=db.f32(e + EM_VIRTUAL_OFFSET), looping=bool(flags[0]), world_space=bool(flags[1]),
            flip=(bool(flags[5]), bool(flags[6]))))
    textures = []
    v = db.vec(off + PART_TEXTURES)
    if v is not None:
        for k in range(v[1] // 8):
            textures.append(db.ptr(v[0] + 8 * k))
    speed = db.f32(off + PART_SPEED)
    return ParticleInfo(off, cat.name(db.binary_ref(off)), speed if speed > 0 else 1.0,
                        bool(db.u8(off + PART_LOOPED)), db.i32(off + PART_END_FRAME),
                        db.i32(off + PART_LOOP_FRAME), emitters, textures)


def atlas_rect(db: PackDB, cat: PakCatalog, element: int | None) -> tuple[str, int, int, int, int] | None:
    """(texture de l'atlas, x, y, largeur, hauteur) d'un élément d'atlas (`TextureSingleElement`)."""
    if element is None:
        return None
    atlas = db.ptr(element + ELEMENT_ATLAS)
    if atlas is None:
        return None
    texture = db.ptr(atlas + ATLAS_TEXTURE)
    name = cat.name(db.binary_ref(texture)) if texture is not None else None
    for src in db.elements(atlas + ATLAS_SOURCES, SOURCE_STRIDE):
        if db.ptr(src + SOURCE_ELEMENT) == element:
            return (name, db.i32(src + SOURCE_X), db.i32(src + SOURCE_Y), db.i32(src + SOURCE_WIDTH),
                    db.i32(src + SOURCE_HEIGHT))
    return None


# --- scripts (VisActions) ---------------------------------------------------------------------

def read_action(db: PackDB, off: int | None, depth: int = 0) -> dict | None:
    """Arbre d'actions → dictionnaires simples (`type` + champs décodés). Les types inconnus
    gardent seulement leur nom : l'interpréteur les ignore et les signale."""
    if off is None or depth > 24:
        return None
    kind = db.vtype(off)
    node: dict = {"type": kind, "offset": off}
    ident = db.string(off + ACTION_ID)
    if ident:
        node["id"] = ident
    if kind == "VisActionList":
        node["play"] = "Simultaneously" if db.u32(off + LIST_PLAY) == 1 else "InSequence"
        node["elements"] = [a for a in (read_action(db, p, depth + 1) for p in db.pointers(off + LIST_ELEMENTS)) if a]
        node["playWhile"] = read_action(db, db.ptr(off + LIST_PLAY_WHILE), depth + 1)
        node["preconditional"] = bool(db.u8(off + LIST_PRECONDITIONAL))
        node["stopWhileWhenElementsEnded"] = bool(db.u8(off + LIST_STOP_WHILE))
    elif kind == "VisActionDelay":
        node["time"] = db.u32(off + DELAY_TIME) / 1000.0
    elif kind == "CreatureScaleAction":
        node["scale"] = db.f32(off + SCALE_VALUE)
    elif kind == "CreatureSetTransparencyAction":
        node["transparency"] = db.f32(off + TRANSP_VALUE)
        node["fadeMult"] = db.f32(off + TRANSP_FADE_MULT)
        node["priority"] = db.i32(off + TRANSP_PRIORITY)
    elif kind == "CreatureIndependentFxAction":
        node["visObject"] = db.ptr(off + FX_VISOBJECT)
        node["lifeTime"] = db.f32(off + FX_LIFETIME)
        node["offset"] = list(_vec3(db, off + FX_OFFSET))
        node["rotation"] = list(_vec3(db, off + FX_ROTATION))
        node["scale"] = db.f32(off + FX_SCALE)
        node["isRelative"] = bool(db.u8(off + FX_IS_RELATIVE))
    elif kind == "CreatureAnimationAction":
        v = db.vec(off + ANIM_LIST)
        node["animations"] = [db.u32(v[0] + 4 * k) for k in range(v[1] // 4)] if v else []
        speed = db.f32(off + ANIM_SPEED)
        node["speed"] = speed if speed > 0 else 1.0
        node["mode"] = {0: "DIE", 1: "LOOP", 2: "CLAMP"}.get(db.u32(off + ANIM_MODE), "?")
        node["channel"] = db.u32(off + ANIM_CHANNEL)
    elif kind == "CreatureEffectsAction":
        effects = []
        for e in db.elements(off + EFFECTS_LIST, EFFECT_STRIDE):
            loc = db.u32(e + EFFECT_LOCATOR)
            name = db.string(e + EFFECT_LOCATOR_NAME)
            locator = name if (loc == 19 or (name and loc >= len(FX_LOCATORS))) else (
                FX_LOCATORS[loc] if loc < len(FX_LOCATORS) else name)
            effects.append({"visObject": db.ptr(e + EFFECT_FX), "locator": locator or "",
                            "locatorName": name, "scale": db.f32(e + EFFECT_SCALE),
                            "fadeIn": db.i32(e + EFFECT_FADE_IN) / 1000.0,
                            "fadeOut": db.i32(e + EFFECT_FADE_OUT) / 1000.0,
                            "member": db.u32(e + EFFECT_MEMBER),
                            "offset": list(_vec3(db, e + EFFECT_OFFSET))})
        node["effects"] = effects
    elif kind == "PredicateCreatureFlagAction":
        node["flag"] = db.string(off + PREDICATE_FLAG)
    elif kind == "PredicateCreatureVisCharacterAction":
        node["templates"] = [db.string(t + TEMPLATE_NAME) for t in db.pointers(off + PREDICATE_TEMPLATES)]
    elif kind == "CreatureChannelDirectAction":
        node["visObject"] = db.ptr(off + CHANNEL_FX)
        node["fadeIn"] = db.i32(off + CHANNEL_FADE_IN) / 1000.0
        node["fadeOut"] = db.i32(off + CHANNEL_FADE_OUT) / 1000.0
        node["length"] = db.f32(off + CHANNEL_LENGTH)
        node["velocity"] = db.f32(off + CHANNEL_VELOCITY)
        node["start"] = read_point(db, db.ptr(off + CHANNEL_START))
        node["end"] = read_point(db, db.ptr(off + CHANNEL_END))
    elif kind == "ShakeAction":
        params = db.ptr(off + SHAKE_PARAMS)
        if params is not None:
            node["params"] = [round(float(v), 4) for v in db.floats(params + SHAKE_FIELDS, 8)]
    return node


def read_point(db: PackDB, off: int | None) -> dict:
    """`VisPoint` d'un rayon : décalage et, pour un `VisPointLocator`, le locator (défaut
    `Global`, la racine de la créature)."""
    if off is None:
        return {"locator": "Global", "shift": [0.0, 0.0, 0.0]}
    loc = db.u32(off + POINT_LOCATOR)
    name = db.string(off + POINT_LOCATOR_NAME)
    locator = name if (loc == 19 and name) else (FX_LOCATORS[loc] if loc < len(FX_LOCATORS) else "Global")
    return {"locator": locator, "shift": [round(float(v), 4) for v in db.floats(off + POINT_SHIFT, 3)]}


@dataclass
class FatalityDeath:
    type: int
    fade_start: float
    fade_duration: float
    spark_delay: float
    offender: dict | None
    caster: dict | None


def read_fatalities(db: PackDB) -> list[FatalityDeath]:
    slon = db.paths[SLON_PATH]
    out = []
    for e in db.elements(slon + SLON_FATALITIES, FATALITY_STRIDE):
        out.append(FatalityDeath(type=db.u32(e + FAT_TYPE), fade_start=db.f32(e + FAT_FADE_START),
                                 fade_duration=db.f32(e + FAT_FADE_DURATION),
                                 spark_delay=db.f32(e + FAT_SPARK_DELAY),
                                 offender=read_action(db, db.ptr(e + FAT_OFFENDER)),
                                 caster=read_action(db, db.ptr(e + FAT_CASTER))))
    return out


def animation_names(db: PackDB, schema_names: dict[int, str] | None = None) -> dict[int, str]:
    """Indice de l'énumération `Animations` → nom, relu dans les propriétés d'animation du client.

    Les enregistrements d'animation posent l'indice 8 octets avant la chaîne du nom
    (`u32 indice, pad, vecteur nom`) ; on ne garde un couple que s'il est majoritaire pour son
    indice, et conforme au schéma 7.0 quand celui-ci le connaît.
    """
    votes: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    mask = db.rkind == 3
    for loc, tgt in zip(db.rloc[mask].tolist(), db.rtgt[mask].tolist()):
        n = db.u32(loc + 8)
        if not 3 <= n < 48:
            continue
        s = db.bytes(tgt, n)
        if not re.fullmatch(rb"[a-z][A-Za-z0-9_]+", s):
            continue
        idx = db.u32(loc - 8)
        if idx < 4000:
            votes[idx][s.decode()] += 1
    out = {}
    for idx, counter in votes.items():
        (name, _), = counter.most_common(1)
        if schema_names and idx in schema_names and schema_names[idx] != name:
            continue
        out[idx] = name
    return out
