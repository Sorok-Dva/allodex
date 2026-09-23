"""Personnages jouables d'Allods Online, lus dans le dernier client (`Bin/pack.bin`).

Module réutilisable (page Fatalités, future page de création de personnage) : il décode le
« constructeur visuel » du client et dit **quoi dessiner** pour un personnage — sans rien
exporter lui-même :

* `read_character_template` : le `VisCharacterTemplate` d'un modèle (`KaniaMale`…) — gabarit
  visuel (géométrie skinnée, squelette), texture de peau cuite, tenue par défaut, sous-vêtements,
  variations (visages, pilosité, coiffures, couleurs), géosets teints par la couleur des cheveux ;
* `read_visual_item` : un `VisualItem` (tenue, sous-vêtement, visage, coiffure…) — formes
  d'armure montrées (`armorShapes`, par sexe), géosets cachés, calques de texture
  (`texturePatches`, `braTexturePatches`, `pantsTexturePatches`) ;
* `resolve_appearance` : géosets visibles, textures de remplacement, teintes et calques à cuire
  pour une variation (par défaut celle du client) et des objets portés ;
* `bake_skin` : la texture de peau cuite — peau de base, teinte de peau sous le masque de
  l'`IndexedTexture`, puis calques dans l'ordre du client (visage, pilosité, tatouages,
  cuir chevelu, sous-vêtements, objets).

Règles établies sur les données (septembre 2026, client RU 17.0.01.64), chaque décalage retrouvé
sur les `.xdb` 7.0 des mêmes ressources (`HadaganFemale`, `Underwear_HadaganFemale`,
`HadaganFemaleFace03`…) :

* visibilité : tous les géosets de la géométrie, moins ceux que cache la tenue par défaut, plus
  ceux que montrent les `armorShapes` des objets (la variation par défaut montre `face_0`,
  `hair_0`, `facial_0`…), moins ceux que cachent les objets portés (`hiddenGeosets`, listes par
  sexe + unisexe) — ce dernier cache l'emporte (cheveux sous un casque) ; un géoset sans texture
  n'est pas dessiné (emplacements vides de jupes et capes) ;
* calques : rectangles en fraction de la texture de peau, **V compté depuis le bas** (le visage,
  `y 0 → 0,375`, occupe le bas de l'image) ; ordre des coordonnées `x1, x2, y1, y2` ;
* couleurs ARGB (`-1` = blanc, sans effet) ; teinte de peau multipliée sous le masque (alpha de
  l'`IndexedTexture`, basse résolution, qui exclut yeux et dents) ; couleur des cheveux
  multipliée sur les géosets `hairColoredGeosets`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

import numpy as np
from PIL import Image

from tools.allods_packdb import PackDB, PakCatalog

# --- VisCharacterTemplate -----------------------------------------------------------------------

TPL_VISOBJECT = 0x90           # characterVisObject (VisObjectTemplate)
TPL_DEFAULT_DRESS = 0xA0       # defaultDress (VisualItem)
TPL_GENDER = 0xB8              # 1 Male, 2 Female
TPL_HAIR_COLORED = 0xC0        # hairColoredGeosets (chaînes de 24 o)
TPL_NAME = 0xE8                # helmGeoset : nom du modèle (`HadaganFemale`)
TPL_MAIN_TEXTURE = 0x120       # mainBakedTexture
TPL_SPECIAL_HAIR_PATCH = 0x208 # specialHairTexPatch (TextureRect[])
TPL_UNDERWEAR = 0x260          # underwear (VisualItem)
TPL_VARIATIONS = 0x270         # variations (CharacterVariations)
VOT_GEOMETRY = 0xC0

GENDERS = {1: "male", 2: "female"}

# --- CharacterVariations ------------------------------------------------------------------------

VAR_ADDITIONAL = 0x28
VAR_DEFAULT = 0x48             # CharacterVariation en ligne (8 o d'entête)
VAR_FACES = 0xD0
VAR_FACIAL = 0xF0
VAR_HAIR = 0x110
VAR_HAIR_COLORS = 0x130
VAR_MAIN_TEXTURES = 0x150
# 0x170 = couleurs de pierres d'épaule (Aoidoi) ; les couleurs de peau sont en 0x1B0 (relevé par
# l'écran de création de personnage, `tools/allods_chargen.py`).
VAR_SHOULDER_STONE_COLORS = 0x170
VAR_SKIN_COLORS = 0x1B0
# CharacterVariation (relatif à son début)
CV_ADDITIONAL = 0x08
CV_FACE = 0x10
CV_FACIAL = 0x18
CV_HAIR_COLOR = 0x20
CV_HAIR = 0x28
CV_SKIN = 0x78                 # IndexedTexture
CV_SKIN_COLOR = 0x80

# --- VisualItem ---------------------------------------------------------------------------------

VI_SHAPES = {"female": 0x30, "male": 0x50, "unisex": 0x70}      # armorShapes (ArmorShape[])
VI_BRA_PATCHES = 0x90
VI_HIDDEN = {"female": 0x138, "male": 0x158, "unisex": 0x178}   # hiddenGeosets (chaînes)
VI_PANTS_PATCHES = 0x228
VI_PATCHES = 0x258
SHAPE_STRIDE = 96
SHAPE_SCENE = 0x08             # armorScene (VisObjectTemplate)
SHAPE_COLOR = 0x10
SHAPE_LOCATOR = 0x18
SHAPE_MASK_COLOR = 0x30
SHAPE_REPLACEMENT = 0x38       # replacement (Texture)
SHAPE_NAME = 0x40
STRING_STRIDE = 24

# --- TexturePatch / IndexedTexture ------------------------------------------------------------

PATCH_LISTS = {"female": 0x28, "male": 0x48, "unisex": 0x68}   # TextureRect[]
RECT_STRIDE = 32
RECT_COORDS = 0x08             # x1, x2, y1, y2
RECT_TEXTURE = 0x18
INDEXED_BINARY = 0x40          # (code de pak, rang) du `.bin`, comme une Texture

WHITE = -1


def argb(value: int) -> tuple[float, float, float]:
    """Couleur ARGB signée du client → (r, g, b) dans [0, 1]."""
    v = value & 0xFFFFFFFF
    return ((v >> 16) & 255) / 255.0, ((v >> 8) & 255) / 255.0, (v & 255) / 255.0


@dataclass
class ArmorShape:
    shape: str
    color: int = WHITE
    mask_color: int = WHITE
    replacement: str | None = None      # nom du `.bin` de la texture de remplacement
    locator: str | None = None
    scene: int | None = None            # VisObjectTemplate accroché (décalage)


@dataclass
class TextureRect:
    rect: tuple[float, float, float, float]   # x1, x2, y1, y2 (V depuis le bas)
    texture: str | None


@dataclass
class VisualItem:
    offset: int
    shapes: dict[str, list[ArmorShape]] = field(default_factory=dict)
    hidden: dict[str, list[str]] = field(default_factory=dict)
    patches: list[TextureRect] = field(default_factory=list)        # texturePatches
    bra: list[TextureRect] = field(default_factory=list)
    pants: list[TextureRect] = field(default_factory=list)
    gendered: dict[str, dict[str, list[TextureRect]]] = field(default_factory=dict)

    def shapes_for(self, gender: str) -> list[ArmorShape]:
        return self.shapes.get(gender, []) + self.shapes.get("unisex", [])

    def hidden_for(self, gender: str) -> list[str]:
        return self.hidden.get(gender, []) + self.hidden.get("unisex", [])

    def patches_for(self, gender: str) -> list[TextureRect]:
        """Calques de l'objet pour un sexe : sous-vêtement du haut, du bas, puis calques propres."""
        out: list[TextureRect] = []
        for kind in ("bra", "pants", "patches"):
            lists = self.gendered.get(kind, {})
            out += lists.get(gender, []) + lists.get("unisex", [])
        return out


@dataclass
class Variation:
    additional: VisualItem | None
    face: VisualItem | None
    facial: VisualItem | None
    hair: VisualItem | None
    hair_color: int
    skin: str | None                    # `.bin` de l'IndexedTexture (masque de teinte)
    skin_color: int

    def items(self) -> list[VisualItem]:
        """Objets de la variation dans l'ordre de cuisson du client."""
        return [i for i in (self.face, self.facial, self.additional, self.hair) if i is not None]


@dataclass
class Variations:
    faces: list[int]
    facials: list[int]
    hairs: list[int]
    additionals: list[int]
    hair_colors: list[int]
    skin_colors: list[int]
    default: Variation
    # `mainTextures` : peaux de base au choix ; la première sert quand le gabarit n'a pas de
    # `mainBakedTexture` (PNJ uniques : `Creatures/Mirianna`, peau `ElfFemaleSkin00`).
    main_textures: list[str] = field(default_factory=list)


@dataclass
class CharacterTemplate:
    offset: int
    model: str
    gender: str
    visobject: int
    geometry: int
    main_texture: str | None
    default_dress: VisualItem | None
    underwear: VisualItem | None
    variations: Variations | None
    hair_colored: list[str]
    special_hair_patch: list[TextureRect]


# --- lecture ------------------------------------------------------------------------------------

def _strings(db: PackDB, loc: int) -> list[str]:
    v = db.vec(loc)
    if v is None:
        return []
    return [db.string(v[0] + STRING_STRIDE * k) or "" for k in range(v[1] // STRING_STRIDE)]


def _texture_name(db: PackDB, cat: PakCatalog, off: int | None) -> str | None:
    return cat.name(db.binary_ref(off)) if off is not None else None


def read_texture_rects(db: PackDB, cat: PakCatalog, loc: int) -> list[TextureRect]:
    out = []
    for e in db.elements(loc, RECT_STRIDE):
        x1, x2, y1, y2 = (float(v) for v in db.floats(e + RECT_COORDS, 4))
        out.append(TextureRect((x1, x2, y1, y2), _texture_name(db, cat, db.ptr(e + RECT_TEXTURE))))
    return out


def read_texture_patch(db: PackDB, cat: PakCatalog, off: int | None) -> dict[str, list[TextureRect]]:
    if off is None:
        return {}
    return {g: read_texture_rects(db, cat, off + rel) for g, rel in PATCH_LISTS.items()}


def read_visual_item(db: PackDB, cat: PakCatalog, off: int) -> VisualItem:
    item = VisualItem(off)
    for gender, rel in VI_SHAPES.items():
        shapes = []
        for e in db.elements(off + rel, SHAPE_STRIDE):
            shapes.append(ArmorShape(shape=db.string(e + SHAPE_NAME) or "", color=db.i32(e + SHAPE_COLOR),
                                     mask_color=db.i32(e + SHAPE_MASK_COLOR),
                                     replacement=_texture_name(db, cat, db.ptr(e + SHAPE_REPLACEMENT)),
                                     locator=db.string(e + SHAPE_LOCATOR), scene=db.ptr(e + SHAPE_SCENE)))
        item.shapes[gender] = shapes
    for gender, rel in VI_HIDDEN.items():
        item.hidden[gender] = _strings(db, off + rel)
    item.gendered = {"bra": read_texture_patch(db, cat, db.ptr(off + VI_BRA_PATCHES)),
                     "pants": read_texture_patch(db, cat, db.ptr(off + VI_PANTS_PATCHES)),
                     "patches": read_texture_patch(db, cat, db.ptr(off + VI_PATCHES))}
    return item


def _item(db: PackDB, cat: PakCatalog, off: int | None) -> VisualItem | None:
    return read_visual_item(db, cat, off) if off is not None else None


def _ints(db: PackDB, loc: int) -> list[int]:
    v = db.vec(loc)
    return [db.i32(v[0] + 4 * k) for k in range(v[1] // 4)] if v else []


def read_variation(db: PackDB, cat: PakCatalog, off: int) -> Variation:
    skin = db.ptr(off + CV_SKIN)
    skin_bin = cat.name(db.file_ref(skin, INDEXED_BINARY)) if skin is not None else None
    return Variation(additional=_item(db, cat, db.ptr(off + CV_ADDITIONAL)), face=_item(db, cat, db.ptr(off + CV_FACE)),
                     facial=_item(db, cat, db.ptr(off + CV_FACIAL)), hair=_item(db, cat, db.ptr(off + CV_HAIR)),
                     hair_color=db.i32(off + CV_HAIR_COLOR), skin=skin_bin, skin_color=db.i32(off + CV_SKIN_COLOR))


def read_variations(db: PackDB, cat: PakCatalog, off: int) -> Variations:
    return Variations(faces=db.pointers(off + VAR_FACES), facials=db.pointers(off + VAR_FACIAL),
                      hairs=db.pointers(off + VAR_HAIR), additionals=db.pointers(off + VAR_ADDITIONAL),
                      hair_colors=_ints(db, off + VAR_HAIR_COLORS), skin_colors=_ints(db, off + VAR_SKIN_COLORS),
                      default=read_variation(db, cat, off + VAR_DEFAULT),
                      main_textures=[n for n in (_texture_name(db, cat, t) for t in db.pointers(off + VAR_MAIN_TEXTURES)) if n])


def find_character_template(db: PackDB, cat: PakCatalog, model: str, folder: str) -> int | None:
    """Gabarit du personnage joueur : le `VisCharacterTemplate` nommé comme le modèle dont la
    géométrie est `Characters/<dossier>/<modèle>.(Geometry).bin` (les variantes `_CutScene`,
    `_lowpoly` et les PNJ portent le même nom de modèle)."""
    wanted = f"Characters/{folder}/{model}.(Geometry).bin"
    for off in sorted(db.resources("VisCharacterTemplate")):
        if db.string(off + TPL_NAME) != model:
            continue
        vot = db.ptr(off + TPL_VISOBJECT)
        geometry = db.ptr(vot + VOT_GEOMETRY) if vot is not None else None
        if geometry is not None and cat.name(db.binary_ref(geometry)) == wanted:
            return off
    return None


def read_character_template(db: PackDB, cat: PakCatalog, off: int) -> CharacterTemplate:
    vot = db.ptr(off + TPL_VISOBJECT)
    variations = db.ptr(off + TPL_VARIATIONS)
    return CharacterTemplate(
        offset=off, model=db.string(off + TPL_NAME) or "", gender=GENDERS.get(db.u32(off + TPL_GENDER), "male"),
        visobject=vot, geometry=db.ptr(vot + VOT_GEOMETRY),
        main_texture=_texture_name(db, cat, db.ptr(off + TPL_MAIN_TEXTURE)),
        default_dress=_item(db, cat, db.ptr(off + TPL_DEFAULT_DRESS)),
        underwear=_item(db, cat, db.ptr(off + TPL_UNDERWEAR)),
        variations=read_variations(db, cat, variations) if variations is not None else None,
        hair_colored=_strings(db, off + TPL_HAIR_COLORED),
        special_hair_patch=read_texture_rects(db, cat, off + TPL_SPECIAL_HAIR_PATCH))


# --- apparence ----------------------------------------------------------------------------------

@dataclass
class Appearance:
    """Ce qu'il faut dessiner : géosets visibles (ordre de la géométrie), texture de chaque géoset
    qui change (remplacement d'armure, ou peau cuite pour ceux qui portent la peau de base),
    teintes multiplicatives, calques à cuire et teinte de peau."""
    visible: list[str]
    replacements: dict[str, str]
    tints: dict[str, tuple[float, float, float]]
    patches: list[TextureRect]
    skin_texture: str | None
    skin_mask: str | None
    skin_color: int
    hair_color: int


def resolve_appearance(template: CharacterTemplate, element_names: Iterable[str],
                       element_textures: dict[str, str | None], variation: Variation | None = None,
                       items: Iterable[VisualItem] = ()) -> Appearance:
    """Apparence d'un personnage pour une variation (celle du client par défaut) et des objets
    portés par-dessus la tenue par défaut, dans l'ordre (le dernier l'emporte)."""
    gender = template.gender
    variation = variation or (template.variations.default if template.variations else None)
    worn: list[VisualItem] = []
    if template.default_dress:
        worn.append(template.default_dress)
    if variation:
        worn += variation.items()
    worn += list(items)
    # La tenue par défaut cache les variantes (visages, coiffures…) que les objets remontrent ;
    # un géoset caché par un objet porté (variation ou objet) l'emporte, lui, sur un géoset
    # montré : les cheveux disparaissent sous un casque (règle de l'écran de création).
    default_hidden: set[str] = set(template.default_dress.hidden_for(gender)) if template.default_dress else set()
    hidden: set[str] = set()
    shown: dict[str, ArmorShape] = {}
    for item in worn:
        if item is not template.default_dress:
            hidden.update(item.hidden_for(gender))
    for item in worn:
        for shape in item.shapes_for(gender):
            shown[shape.shape] = shape
    replacements: dict[str, str] = {}
    tints: dict[str, tuple[float, float, float]] = {}
    visible: list[str] = []
    hair_color = variation.hair_color if variation else WHITE
    for name in element_names:
        if name in hidden or (name in default_hidden and name not in shown):
            continue
        shape = shown.get(name)
        texture = (shape.replacement if shape and shape.replacement else None) or element_textures.get(name)
        if not texture:
            continue  # emplacement vide : rien à dessiner
        visible.append(name)
        if shape and shape.replacement:
            replacements[name] = shape.replacement
        tint = shape.color if shape and shape.color != WHITE else WHITE
        if name in template.hair_colored and hair_color != WHITE:
            tint = hair_color
        if tint != WHITE:
            tints[name] = argb(tint)
    patches: list[TextureRect] = []
    for item in (variation.items() if variation else []):
        patches += item.patches_for(gender)
    if template.underwear:
        patches += template.underwear.patches_for(gender)
    for item in items:
        patches += item.patches_for(gender)
    return Appearance(visible=visible, replacements=replacements, tints=tints, patches=patches,
                      skin_texture=template.main_texture, skin_mask=variation.skin if variation else None,
                      skin_color=variation.skin_color if variation else WHITE, hair_color=hair_color)


def bake_skin(base: Image.Image, appearance: Appearance, image_of: Callable[[str], Image.Image | None],
              mask: Image.Image | None = None, size: int | None = None) -> Image.Image:
    """Texture de peau cuite (RGB) : peau de base à `size` (sa taille par défaut), teinte de peau
    sous le masque, puis chaque calque collé dans son rectangle (V depuis le bas) avec son alpha."""
    size = size or max(base.size)
    img = base.convert("RGBA").resize((size, size), Image.LANCZOS) if base.size != (size, size) else base.convert("RGBA")
    if appearance.skin_color != WHITE:
        rgb = np.asarray(img, np.float32)
        tint = np.array(argb(appearance.skin_color), np.float32)
        weight = np.ones(rgb.shape[:2], np.float32)
        if mask is not None:
            weight = np.asarray(mask.convert("RGBA").resize((size, size), Image.BILINEAR), np.float32)[:, :, 3] / 255.0
        factor = 1.0 + (tint[None, None, :] - 1.0) * weight[:, :, None]
        rgb[:, :, :3] *= factor
        img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGBA")
    for patch in appearance.patches:
        if not patch.texture:
            continue
        piece = image_of(patch.texture)
        if piece is None:
            continue
        x1, x2, y1, y2 = patch.rect
        box = (round(x1 * size), round((1.0 - y2) * size), round(x2 * size), round((1.0 - y1) * size))
        w, h = box[2] - box[0], box[3] - box[1]
        if w <= 0 or h <= 0:
            continue
        piece = piece.convert("RGBA")
        if piece.size != (w, h):
            piece = piece.resize((w, h), Image.LANCZOS)
        img.alpha_composite(piece, box[:2])
    return img.convert("RGB")
