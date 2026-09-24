"""Décodeurs des données de création de personnage du dernier client (RU 17.x, `pack.bin`).

Lecture structurelle au-dessus de `tools/allods_packdb.py` (image mémoire + relocations). Chaque
décalage ci-dessous a été établi sur les données (septembre 2026) en confrontant les objets
compilés du client 17 aux `.xdb` de même rôle de l'arbre serveur 7.0 (`ElfFemale`,
`ElfMage01Female`, `Cloth_A_17ElfMageArmor`, `CharacterScenes`, `Hadagan_Chargen`…) : mêmes
listes (11 visages, 13 traits, 16 coiffures, 34 couleurs de cheveux, 18 teintes de peau de
l'elfe), mêmes couleurs ARGB, mêmes noms de géosets et de textures.

Chaîne de la création de personnage (addon `CharacterGenerator`, scripts
`Interface/Wrap/MainMenu/CharacterGenerator3/*.luac`) :

* `CharacterRoot` (le premier des deux : le second est un jeu d'essai à une seule race) →
  `factions[] = {faction, races[] = {race, classes[] = {raceClass, sexes[2]}}}`. Une entrée de
  sexe (48 o) porte le `Character` de la création, le gabarit du **familier** (`VisCharacterTemplate`
  du compagnon des Pacificateurs, seuls `DRUID` en ont un), un second `Character` et le
  `VisCharacterTemplate` du personnage ;
* `Character` → `growths[3]` : les trois tenues montrées à la création (« Экипировка начального /
  среднего / высшего уровня »), chacune avec ses animations (`chargen<Classe>Start` puis
  `chargen<Classe>` en boucle), ses objets portés (`VisualItem` + emplacement) et des effets
  accrochés à un locator ;
* `VisCharacterTemplate` → géométrie (via le `VisObjectTemplate`), texture « cuite »
  (`mainBakedTexture`), tenue par défaut, sous-vêtements, `CharacterVariations` ;
* `CharacterVariations` → visages, traits du visage (`facial`), coiffures, couleurs de cheveux,
  peaux (`IndexedTexture`, alpha = masque de teinte), teintes de peau, signe additionnel, pierres
  et couleurs de pierres (aèdes) ;
* `VisualItem` → formes (`shapeName` = géoset du corps, ou modèle accroché à un locator), géosets
  cachés, patchs de texture (`TexturePatch` : rectangles de la texture cuite, V = 0 en bas).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from tools.allods_packdb import PackDB, PakCatalog

# --- CharacterRoot et entrées -----------------------------------------------------------------

ROOT_FACTIONS = 0x28           # vecteur de {pad, Faction*, races[]} (48 o)
FACTION_ENTRY = 48
RACE_ENTRY = 48                # {pad, classes[] (+0x08), …, CharacterRace* (+0x28)}
CLASS_ENTRY = 48               # {pad, CharacterRaceClass* (+0x08), sexes[] (+0x10)}
SEX_ENTRY = 48                 # {pad, Character*, familier VCT*, ?, Character*, VCT*}
SEX_CHARACTER = 0x08
SEX_PET = 0x10
SEX_CHARACTER2 = 0x20
SEX_TEMPLATE = 0x28

FACTION_NAME = 0x68            # identifiant de texte
FACTION_SYSNAME = 0x70
RACE_NAME = 0x68
RACE_SEXES = 0x70              # vecteur de {…, nom (+0x20), indice de sexe (+0x28)} (48 o)
RACE_SYSNAME = 0x90
CLASS_NAME = 0x40
CLASS_SYSNAME = 0x68
RC_CLASS = 0x28
RC_RACE = 0x30
RC_DESC = 0x50                 # « Тип брони : … » (texte HTML)
RC_TITLE = 0x70                # titre de rang élevé (« Великий Чародей »)
RC_NAME = 0x90
RC_SYSNAME = 0xB8

# --- Character ---------------------------------------------------------------------------------

CH_RACECLASS = 0x28
CH_SEX = 0x30
CH_GROWTHS = 0x60              # 3 × 224 o
GROWTH_STRIDE = 224
GROWTH_LOOP = 0x08             # chaîne : animation en boucle
GROWTH_START = 0x38            # chaîne : animation d'entrée
GROWTH_ITEMS = 0x50            # {pad, VisualItem*, emplacement u32} (24 o)
GROWTH_FX = 0x70               # ChargenEffect (48 o) : locator (chaîne, +0x08), runType (+0x20),
                               # échelle f32 (+0x24), VisObjectTemplate* (+0x28)
FX_RUN_TYPE = 0x20             # champs par ordre alphabétique (types 7.0 : locator, runType, scale, visObj) ;
FX_SCALE = 0x24                # +0x24 vaut 0,6 à 1,2 selon la classe et la race, +0x20 vaut 0 ou 1

# Emplacements (`ItemSlot`) tels que stockés (vérifiés sur `ElfMage01Female` : BELT 7, BOOTS 3,
# PANTS 2, BRACERS 6, ARMOR 1, OFFHAND 15, MAINHAND 14, RANGED 16, HELM 0, MANTLE 4, GLOVES 5,
# CLOAK 12, ceinture de bijoux 13).
SLOTS = {0: "HELM", 1: "ARMOR", 2: "PANTS", 3: "BOOTS", 4: "MANTLE", 5: "GLOVES", 6: "BRACERS",
         7: "BELT", 8: "RING1", 9: "RING2", 10: "EARRING1", 11: "EARRING2", 12: "CLOAK", 13: "SHIRT",
         14: "MAINHAND", 15: "OFFHAND", 16: "RANGED", 17: "AMMO", 18: "TABARD", 19: "MISC", 20: "BAG"}

# --- VisCharacterTemplate ---------------------------------------------------------------------

VCT_VISOBJECT = 0x90
VCT_DEFAULT_DRESS = 0xA0
VCT_GENDER = 0xB8              # 1 homme, 2 femme
VCT_HAIR_COLORED = 0xC0        # vecteur de chaînes : géosets teints par la couleur de cheveux
VCT_NAME = 0xE8                # `helmGeoset`, identique au nom du modèle (« ElfFemale »)
VCT_BAKED = 0x120              # Texture cuite (peau + patchs)
VCT_MORPH = 0x148              # ModelMorphSettings* (corpulence : échelles d'os)
VCT_SPECIAL_HAIR_PATCH = 0x208  # {pad, rectangle x1 x2 y1 y2, Texture*} (32 o)
VCT_UI_SCENE = 0x234           # cameraAnchor xyz, bodyCoeff, additionalAway, faceAnchor xyz, scale
VCT_UI_SELECTION_SCALE = 0x258
VCT_UNDERWEAR = 0x260
VCT_VARIATIONS = 0x270

# --- CharacterVariations -----------------------------------------------------------------------

VAR_ADDITIONAL = 0x28
VAR_DEFAULT = {"additional": 0x50, "face": 0x58, "facial": 0x60, "hairColor": 0x68, "hair": 0x70,
               "shoulderStoneColor": 0xB8, "skin": 0xC0, "skinColor": 0xC8}
VAR_FACES = 0xD0
VAR_FACIALS = 0xF0
VAR_HAIRS = 0x110
VAR_HAIR_COLORS = 0x130        # u32 ARGB
VAR_SKINS = 0x150              # IndexedTexture*
VAR_SHOULDER_STONE_COLORS = 0x170
VAR_SHOULDER_STONES = 0x190
VAR_SKIN_COLORS = 0x1B0

# --- VisualItem --------------------------------------------------------------------------------

VI_SHAPES = {"female": 0x30, "male": 0x50, "unisex": 0x70}
VI_HIDDEN = {"female": 0x138, "male": 0x158, "unisex": 0x178}
VI_HIDDEN_LOCATORS = {"female": 0x1A0, "male": 0x1C0, "unisex": 0x1E0}
VI_DRESS_SLOT = 0xD8
VI_PATCHES = 0x258
VI_BRA_PATCHES = 0x90
VI_PANTS_PATCHES = 0x228
VI_UNDERWEAR = 0x260           # 0 SHOW_ALL … 3 HIDE_ALL
SHAPE_STRIDE = 96
SHAPE_VISOBJECT = 0x08
SHAPE_COLOR = 0x10
SHAPE_LOCATOR = 0x18
SHAPE_MASK_COLOR = 0x30
SHAPE_REPLACEMENT = 0x38
SHAPE_NAME = 0x40

TP_LISTS = {"female": 0x28, "male": 0x48, "unisex": 0x68}
TP_STRIDE = 32
TP_RECT = 0x08                 # x1, x2, y1, y2 (V = 0 en bas de l'image)
TP_TEXTURE = 0x18

INDEXED_BINARY = 0x40          # (code de pak, rang) comme une Texture
INDEXED_WIDTH = 0x88
INDEXED_HEIGHT = 0x78

# --- interface ---------------------------------------------------------------------------------

ADDON_NAME = 0x30
ADDON_TEXTS = 0xD8             # {pad, groupe (chaîne), UIRelatedTexts*} (40 o)
ADDON_TEXTURES = 0xF8          # {pad, groupe, UIRelatedTextures*} (40 o)
RELATED_ENTRY = 40
TEXTS_LIST = 0x28              # {pad, clé (chaîne, +0x08), identifiant de texte (+0x38)} (64 o)
TEXT_ENTRY = 64

# --- UICharacterScenes -------------------------------------------------------------------------

SCENES_LIST = 0x28
SCENE_STRIDE = 152
TILE = 32.0                    # côté d'une case de carte (m) : global = case·32 + local


def color_argb(value: int) -> str:
    """ARGB signé ou non → `#rrggbb` (l'alpha des palettes vaut toujours 0xff)."""
    value &= 0xFFFFFFFF
    return f"#{value & 0xFFFFFF:06x}"


@dataclass
class SexEntry:
    faction: str
    race: str
    cls: str
    race_class: int
    sex: int                   # 0 homme, 1 femme (ordre des entrées)
    character: int | None
    pet_template: int | None
    character2: int | None
    template: int | None


def character_root(db: PackDB) -> int:
    """Le vrai `CharacterRoot` : celui qui a le plus de factions."""
    roots = db.resources("CharacterRoot")
    return max(roots, key=lambda r: (db.vec(r + ROOT_FACTIONS) or (0, 0))[1])


def walk_root(db: PackDB) -> list[SexEntry]:
    out: list[SexEntry] = []
    for f in db.elements(character_root(db) + ROOT_FACTIONS, FACTION_ENTRY):
        faction = db.ptr(f + 0x08)
        fname = db.string(faction + FACTION_SYSNAME) if faction else "?"
        for r in db.elements(f + 0x10, RACE_ENTRY):
            race = db.ptr(r + 0x28)
            rname = db.string(race + RACE_SYSNAME) if race else "?"
            for c in db.elements(r + 0x08, CLASS_ENTRY):
                rc = db.ptr(c + 0x08)
                cls = db.ptr(rc + RC_CLASS) if rc else None
                cname = db.string(cls + CLASS_SYSNAME) if cls else "?"
                for k, s in enumerate(db.elements(c + 0x10, SEX_ENTRY)):
                    out.append(SexEntry(fname, rname, cname, rc, k, db.ptr(s + SEX_CHARACTER),
                                        db.ptr(s + SEX_PET), db.ptr(s + SEX_CHARACTER2),
                                        db.ptr(s + SEX_TEMPLATE)))
    return out


def root_order(db: PackDB) -> list[tuple[int, list[tuple[int, list[int]]]]]:
    """(faction, [(race, [classe…])…]) dans l'ordre du `CharacterRoot`."""
    out = []
    for f in db.elements(character_root(db) + ROOT_FACTIONS, FACTION_ENTRY):
        races = []
        for r in db.elements(f + 0x10, RACE_ENTRY):
            classes = [db.ptr(db.ptr(c + 0x08) + RC_CLASS) for c in db.elements(r + 0x08, CLASS_ENTRY)]
            races.append((db.ptr(r + 0x28), classes))
        out.append((db.ptr(f + 0x08), races))
    return out


# --- Character --------------------------------------------------------------------------------

@dataclass
class Growth:
    loop: str | None
    start: str | None
    items: list[tuple[str, int]]            # (emplacement, VisualItem)
    fx: list[dict]                          # {locator, scale, runType, visObject}


def read_growths(db: PackDB, character: int) -> list[Growth]:
    out = []
    for g in db.elements(character + CH_GROWTHS, GROWTH_STRIDE):
        items = []
        for it in db.elements(g + GROWTH_ITEMS, 24):
            vi = db.ptr(it + 8)
            if vi is not None:
                slot = db.u32(it + 16)
                items.append((SLOTS.get(slot, f"SLOT{slot}"), vi))
        fx = []
        for e in db.elements(g + GROWTH_FX, 48):
            vot = db.ptr(e + 0x28)
            if vot is not None:
                fx.append({"locator": db.string(e + 0x08) or "", "scale": round(db.f32(e + FX_SCALE), 4),
                           "runType": db.u32(e + FX_RUN_TYPE), "visObject": vot})
        out.append(Growth(db.string(g + GROWTH_LOOP), db.string(g + GROWTH_START), items, fx))
    return out


# --- VisualItem, TexturePatch --------------------------------------------------------------------

@dataclass
class Shape:
    geoset: str | None
    locator: str | None
    visobject: int | None
    color: int
    mask_color: int
    replacement: int | None                 # Texture


@dataclass
class Patch:
    rect: tuple[float, float, float, float]  # x1, x2, y1, y2
    texture: int | None


@dataclass
class VisualItem:
    offset: int
    shapes: dict[str, list[Shape]] = field(default_factory=dict)
    hidden: dict[str, list[str]] = field(default_factory=dict)
    hidden_locators: dict[str, list[str]] = field(default_factory=dict)
    patches: dict[str, list[Patch]] = field(default_factory=dict)
    underwear: int = 0
    dress_slot: int = 0


def _strings(db: PackDB, loc: int) -> list[str]:
    return [s for s in (db.string(e) for e in db.elements(loc, 24)) if s]


def read_patches(db: PackDB, tp: int | None) -> dict[str, list[Patch]]:
    out: dict[str, list[Patch]] = {}
    if tp is None:
        return out
    for key, off in TP_LISTS.items():
        lst = [Patch(tuple(round(float(v), 5) for v in db.floats(e + TP_RECT, 4)), db.ptr(e + TP_TEXTURE))
               for e in db.elements(tp + off, TP_STRIDE)]
        if lst:
            out[key] = lst
    return out


def read_visual_item(db: PackDB, off: int) -> VisualItem:
    vi = VisualItem(off)
    for key, rel in VI_SHAPES.items():
        shapes = []
        for e in db.elements(off + rel, SHAPE_STRIDE):
            shapes.append(Shape(db.string(e + SHAPE_NAME), db.string(e + SHAPE_LOCATOR),
                                db.ptr(e + SHAPE_VISOBJECT), db.u32(e + SHAPE_COLOR),
                                db.u32(e + SHAPE_MASK_COLOR), db.ptr(e + SHAPE_REPLACEMENT)))
        if shapes:
            vi.shapes[key] = shapes
    for key, rel in VI_HIDDEN.items():
        s = _strings(db, off + rel)
        if s:
            vi.hidden[key] = s
    for key, rel in VI_HIDDEN_LOCATORS.items():
        s = _strings(db, off + rel)
        if s:
            vi.hidden_locators[key] = s
    # Calques dans l'ordre du client : sous-vêtement du haut, du bas, puis calques propres
    # (`braTexturePatches`, `pantsTexturePatches`, `texturePatches` : décalages de
    # `tools/allods_characters.py`, module des fatalités).
    for rel in (VI_BRA_PATCHES, VI_PANTS_PATCHES, VI_PATCHES):
        for key, lst in read_patches(db, db.ptr(off + rel)).items():
            vi.patches.setdefault(key, []).extend(lst)
    vi.underwear = db.u32(off + VI_UNDERWEAR)
    vi.dress_slot = db.u32(off + VI_DRESS_SLOT)
    return vi


# --- VisCharacterTemplate, CharacterVariations ----------------------------------------------------

@dataclass
class Variations:
    offset: int
    faces: list[int]
    facials: list[int]
    hairs: list[int]
    hair_colors: list[int]
    skins: list[int]
    skin_colors: list[int]
    additionals: list[int]
    shoulder_stones: list[int]
    shoulder_stone_colors: list[int]
    default: dict


def _u32s(db: PackDB, loc: int) -> list[int]:
    v = db.vec(loc)
    if v is None:
        return []
    return [db.u32(v[0] + 4 * k) for k in range(v[1] // 4)]


def read_variations(db: PackDB, off: int) -> Variations:
    default = {}
    for key, rel in VAR_DEFAULT.items():
        if key in ("hairColor", "skinColor", "shoulderStoneColor"):
            default[key] = db.u32(off + rel)
        else:
            default[key] = db.ptr(off + rel)
    return Variations(off, db.pointers(off + VAR_FACES), db.pointers(off + VAR_FACIALS),
                      db.pointers(off + VAR_HAIRS), _u32s(db, off + VAR_HAIR_COLORS),
                      db.pointers(off + VAR_SKINS), _u32s(db, off + VAR_SKIN_COLORS),
                      db.pointers(off + VAR_ADDITIONAL), db.pointers(off + VAR_SHOULDER_STONES),
                      _u32s(db, off + VAR_SHOULDER_STONE_COLORS), default)


@dataclass
class Template:
    offset: int
    name: str
    visobject: int | None
    default_dress: int | None
    underwear: int | None
    baked: int | None
    gender: int
    hair_colored: list[str]
    special_hair_patch: list[Patch]
    ui_scene: dict
    variations: int | None


def read_template(db: PackDB, off: int) -> Template:
    ui = db.floats(off + VCT_UI_SCENE, 9)
    special = [Patch(tuple(round(float(v), 5) for v in db.floats(e + TP_RECT, 4)), db.ptr(e + TP_TEXTURE))
               for e in db.elements(off + VCT_SPECIAL_HAIR_PATCH, TP_STRIDE)]
    return Template(
        off, db.string(off + VCT_NAME) or f"vct_{off:x}", db.ptr(off + VCT_VISOBJECT),
        db.ptr(off + VCT_DEFAULT_DRESS), db.ptr(off + VCT_UNDERWEAR), db.ptr(off + VCT_BAKED),
        db.u32(off + VCT_GENDER), _strings(db, off + VCT_HAIR_COLORED), special,
        {"cameraAnchor": [round(float(v), 4) for v in ui[0:3]], "cameraBodyAnchorCoeff": round(float(ui[3]), 4),
         "preMissionAdditionalAway": round(float(ui[4]), 4),
         "preMissionFaceCameraAnchor": [round(float(v), 4) for v in ui[5:8]], "scale": round(float(ui[8]), 4)},
        db.ptr(off + VCT_VARIATIONS))


# --- corpulence (`ModelMorphSettings`) --------------------------------------------------------------
#
# Décodé sur `ElfFemaleMorphSettings` (le `.xdb` 7.0 du serveur donne les noms) : `controls` (+0x28,
# pas 0x38) — os touchés (+0x08, pas 0x30 : nom +0x08, puissance xyz +0x20), indice de la commande
# (+0x28 : Height, Head, NeckThickness, NeckLength, Shoulders, Torso, Breast, Waist, Basin, Hands,
# Forearms, Palm, Hips, Shins, Feet), maximum +0x2C ; `presets` (+0x68, pas 0x30) — valeurs
# (+0x10, pas 0x18 : indice de commande +0x0C, valeur +0x10 ; les commandes absentes valent 1).
# Le jeu met à l'échelle chaque os touché de `valeur ** puissance` sur chaque axe local : c'est la
# commande « Corpulence » (`morphPresets`) de l'écran d'apparence.

MORPH_CONTROLS = 0x28
MORPH_PRESETS = 0x68
MORPH_CONTROL_NAMES = ["Height", "Head", "NeckThickness", "NeckLength", "Shoulders", "Torso", "Breast", "Waist",
                       "Basin", "Hands", "Forearms", "Palm", "Hips", "Shins", "Feet"]


def read_morph(db: PackDB, settings: int | None) -> dict | None:
    """{controls: [[{bone, power}] par commande], presets: [{indice: valeur}]}, ou None."""
    if settings is None or db.vtype(settings) != "ModelMorphSettings":
        return None
    controls: dict[int, list[dict]] = {}
    for e in db.elements(settings + MORPH_CONTROLS, 0x38):
        bones = [{"bone": db.string(b + 0x08), "power": [round(float(v), 4) for v in db.floats(b + 0x20, 3)]}
                 for b in db.elements(e + 0x08, 0x30)]
        controls[db.u32(e + 0x28)] = [b for b in bones if b["bone"] and any(b["power"])]
    presets = []
    for e in db.elements(settings + MORPH_PRESETS, 0x30):
        presets.append({str(db.u32(v + 0x0C)): round(float(db.f32(v + 0x10)), 4) for v in db.elements(e + 0x10, 0x18)})
    if not presets:
        return None
    return {"controls": {str(k): v for k, v in sorted(controls.items()) if v}, "presets": presets}


def indexed_texture_binary(db: PackDB, cat: PakCatalog, off: int) -> str | None:
    return cat.name((db.u32(off + INDEXED_BINARY), db.u32(off + INDEXED_BINARY + 8)))


# --- textes et interface ----------------------------------------------------------------------

def find_addon(db: PackDB, name: str) -> int | None:
    for a in db.resources("UIAddon"):
        if db.string(a + ADDON_NAME) == name:
            return a
    return None


def addon_texts(db: PackDB, addon: int) -> dict[str, dict[str, int]]:
    """{groupe: {clé: identifiant de texte}}."""
    out: dict[str, dict[str, int]] = {}
    for e in db.elements(addon + ADDON_TEXTS, RELATED_ENTRY):
        group = db.string(e + 0x08) or ""
        rt = db.ptr(e + 0x20)
        if rt is None:
            continue
        out[group] = {db.string(t + 0x08): db.u32(t + 0x38) for t in db.elements(rt + TEXTS_LIST, TEXT_ENTRY)
                      if db.string(t + 0x08)}
    return out


def addon_texture_groups(db: PackDB, addon: int) -> dict[str, int]:
    return {db.string(e + 0x08) or "": db.ptr(e + 0x20) for e in db.elements(addon + ADDON_TEXTURES, RELATED_ENTRY)}


@dataclass
class ScenePlace:
    name: str
    map: str
    camera: tuple[float, float, float]
    camera_yaw: float
    camera_pitch: float
    character: tuple[float, float, float]
    character_yaw: float
    character_scale: float
    camera_height: float
    fov: float


def _place(db: PackDB, e: int) -> tuple[tuple[float, float, float], float]:
    lx, ly, lz = db.floats(e, 3)
    tx, ty, _ = struct.unpack("<3i", db.bytes(e + 12, 12))
    yaw = db.f32(e + 24)
    if tx < 0 or tx > 900:
        return (float(lx), float(ly), float(lz)), float(yaw)
    return (tx * TILE + float(lx), ty * TILE + float(ly), float(lz)), float(yaw)


def character_scenes(db: PackDB) -> list[ScenePlace]:
    """`UICharacterScenes.characterScenes` : caméra puis personnage, coordonnées en
    (case de 32 m, décalage local), lacet en degrés."""
    a = db.resources("UICharacterScenes")[0]
    out = []
    for e in db.elements(a + SCENES_LIST, SCENE_STRIDE):
        cam, cam_yaw = _place(db, e + 0x14)
        ch, ch_yaw = _place(db, e + 0x3C)
        out.append(ScenePlace(db.string(e + 0x78) or "", db.string(e + 0x60) or "", cam, cam_yaw, db.f32(e + 0x10),
                              ch, ch_yaw, db.f32(e + 0x58), db.f32(e + 0x08), db.f32(e + 0x04)))
    return out
