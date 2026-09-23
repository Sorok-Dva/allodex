"""Mise en scène des cinématiques moteur dans les bases compilées 17.x (`tools/allods_packdb.py`).

Complète `tools/allods_visdb.py` (géométries, textures, gabarits, actions visuelles) et
`tools/allods_characters.py` (habillage des personnages) avec ce que les cinématiques demandent.
Décalages établis sur les données (septembre 2026) en retrouvant dans l'image binaire les valeurs
des `.xdb` de l'arbre serveur 7.0 :

* `CameraTrackAction` (`BuffResource +0x148` → `BuffVisScripts +0x48`) : deux vecteurs d'éléments
  de 20 octets `(8 inutilisés, f32 durée en s, f32 x, y, z)` — points de caméra en `+0x48`, visées
  en `+0x78` ; identiques, valeur pour valeur, au `.xdb` 7.0 de `AO12_Prologue04_Cutscene` ;
* `ClientData` → `+0x28` `CustomClientDataList` → `+0x30` éléments : `CreatureVisActionData`
  (`+0x30` → action : `CreatureAnimationAction`, `Sound2DAction`, `Sound3DAction`…) et
  `UISubtitleShow` (`+0x30`, éléments de 40 o : `+0x04` durée d'affichage en ms, `+0x20` indice
  du texte dans `pack.*.loc`) ; `Sound2DAction`/`Sound3DAction` : `+0x78` événement FMOD ;
* `MobWorld` : `+0x68` indice du nom, `+0xF8` `VisualMob` ; `VisualMob` : `+0x28` gabarit
  (`VisCharacterTemplate`), `+0x60` objets portés (24 o : `+0x08` `VisualItem`), `+0xD8`
  variation en ligne (`CharacterVariation` : visage, pilosité, couleur et coiffure, peau) ;
* `MapRegion` (`Maps/<carte>/<bloc>/<i>_<j>_MapRegion.xdb` de la base de carte) : `+0xA0` objets
  de 72 o `(8 inutilisés, f32 x, y, z, f32[4] rotation — lacet en +0x20 —, f32 échelle en +0x28,
  StaticObject en +0x30)`, coordonnées locales à la région (256 m : région `i_j` du bloc
  `bx_by` à `(256·(bx+i), 256·(by+j))`) ; `StaticObject` : `+0x30` `VisObjectTemplate` ;
* `ZoneLights` : `+0x168` éclairages (280 o), champs rangés par ordre alphabétique de leur nom
  (recoupé sur `AC5_base` 7.0 ↔ 17.0) ; `+0x2C0` `SkyMesh` (`+0x100` géométrie) ;
* `GameViewScene` : `+0xA0` mobs (192 o : `+0x70` décalage x, y, z, `+0x80` scriptID, `+0xB0`
  VisualMob, `+0xB8` lacet), `+0xE8` MapResource, `+0xF0/+0xF8/+0x100` place x, y, z (doubles) ;
  `ShowSceneAction` : `+0x50` scène, `+0x58` script.
"""
from __future__ import annotations

import re
import struct
import zlib
from dataclasses import dataclass

import numpy as np

from tools.allods_packdb import PackDB

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
ANIM_LIST = 0xE0
MOB_NAME = 0x68
MOB_VISUAL = 0xF8
VM_CHARACTER = 0x28
VM_DRESS = 0x60
VM_DRESS_STRIDE = 24
VM_VARIATION = 0xD8
REGION_OBJECTS = 0xA0
REGION_OBJECT_STRIDE = 72
STATIC_VISOBJECT = 0x30
REGION_SIZE = 256.0
ZONE_LIGHTS = 0x168
ZONE_LIGHT_STRIDE = 280
ZONE_SKY = 0x2C0
SKY_GEOMETRY = 0x100


def _vec3(db: PackDB, off: int) -> tuple[float, float, float]:
    return tuple(float(v) for v in db.floats(off, 3))


# --- caméra et répliques ------------------------------------------------------------------------

@dataclass
class CameraTrack:
    points: list[tuple[float, tuple[float, float, float]]]
    targets: list[tuple[float, tuple[float, float, float]]]

    @property
    def duration(self) -> float:
        return sum(d for d, _ in self.points)


def read_camera_track(db: PackDB, off: int) -> CameraTrack:
    def pts(rel: int):
        return [(round(db.f32(e + 4), 4), tuple(round(v, 4) for v in _vec3(db, e + 8)))
                for e in db.elements(off + rel, CAM_POINT_STRIDE)]
    return CameraTrack(pts(CAM_POINTS), pts(CAM_TARGETS))


def buff_scripts(db: PackDB, buff: int) -> int | None:
    return db.ptr(buff + BUFF_VIS_SCRIPTS)


def buff_camera_track(db: PackDB, buff: int) -> CameraTrack | None:
    scripts = buff_scripts(db, buff)
    action = db.ptr(scripts + VIS_SCRIPTS_ACTION) if scripts is not None else None
    if action is None or db.vtype(action) != "CameraTrackAction":
        return None
    return read_camera_track(db, action)


@dataclass
class ClientLine:
    text_index: int | None
    delay_ms: int
    voice: str | None
    animations: list[int]


def read_client_line(db: PackDB, off: int) -> ClientLine:
    """Réplique d'un `ClientData` : sous-titre (texte + durée), voix, animations du locuteur."""
    lst = db.ptr(off + CLIENT_DATA_LIST)
    line = ClientLine(None, 0, None, [])
    for element in (db.pointers(lst + LIST_ELEMENTS) if lst is not None else []):
        kind = db.vtype(element)
        if kind == "UISubtitleShow":
            items = db.elements(element + SUBTITLE_ITEMS, SUBTITLE_STRIDE)
            if items:
                line.delay_ms = db.u32(items[0] + SUBTITLE_DELAY)
                line.text_index = db.u32(items[0] + SUBTITLE_TEXT)
        elif kind == "CreatureVisActionData":
            action = db.ptr(element + VIS_ACTION_DATA_ACTION)
            akind = db.vtype(action) if action is not None else None
            if akind == "CreatureAnimationAction":
                v = db.vec(action + ANIM_LIST)
                line.animations += [db.u32(v[0] + 4 * k) for k in range(v[1] // 4)] if v else []
            elif akind in ("Sound2DAction", "Sound3DAction"):
                line.voice = db.string(action + SOUND_NAME)
    return line


# --- acteurs ------------------------------------------------------------------------------------

def mob_name_index(db: PackDB, mob: int) -> int:
    return db.u32(mob + MOB_NAME)


def mob_visual(db: PackDB, mob: int) -> int | None:
    return db.ptr(mob + MOB_VISUAL)


def visual_template(db: PackDB, visual_mob: int) -> int | None:
    tpl = db.ptr(visual_mob + VM_CHARACTER)
    return tpl if tpl is not None and db.vtype(tpl) == "VisCharacterTemplate" else None


def visual_dress(db: PackDB, visual_mob: int) -> list[int]:
    out = []
    for e in db.elements(visual_mob + VM_DRESS, VM_DRESS_STRIDE):
        item = db.ptr(e + 8)
        if item is not None and db.vtype(item) == "VisualItem":
            out.append(item)
    return out


# --- décor de carte -----------------------------------------------------------------------------

@dataclass
class PlacedObject:
    region: str
    index: int
    position: tuple[float, float, float]
    rotation: tuple[float, float, float, float]
    scale: float
    static_object: int | None

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


def read_regions(db: PackDB) -> list[PlacedObject]:
    out: list[PlacedObject] = []
    for path, region in sorted(db.paths.items()):
        if not path.endswith("_MapRegion.xdb"):
            continue
        ox, oy = region_origin(path)
        for k, e in enumerate(db.elements(region + REGION_OBJECTS, REGION_OBJECT_STRIDE)):
            x, y, z = _vec3(db, e + 8)
            out.append(PlacedObject(path, k, (x + ox, y + oy, z), tuple(float(v) for v in db.floats(e + 20, 4)),
                                    db.f32(e + 0x28), db.ptr(e + 0x30)))
    return out


def static_visobject(db: PackDB, static_object: int | None) -> int | None:
    if static_object is None or db.vtype(static_object) != "StaticObject":
        return None
    return db.ptr(static_object + STATIC_VISOBJECT)


def parse_lightvrt(raw: bytes) -> dict[int, np.ndarray]:
    """`<région>_lightvrt.bin` décompressé : blocs `(u32 id, u32 taille)` ; bloc 0 = nombre
    d'entrées, bloc 1 = taille par objet, bloc `k + 2` = sommets de l'objet `k` de la région
    (4 octets par sommet, autant que de sommets dans sa géométrie)."""
    out: dict[int, np.ndarray] = {}
    off = 0
    while off + 8 <= len(raw):
        cid, size = struct.unpack_from("<II", raw, off)
        if cid >= 2:
            out[cid - 2] = np.frombuffer(raw[off + 8:off + 8 + size], np.uint8).reshape(-1, 4)
        off += 8 + size
    return out


def read_lightvrt(db: PackDB, map_name: str, get) -> dict[tuple[str, int], np.ndarray]:
    """Éclairage précalculé des objets posés, lu dans `<carte>_000_000_512_512.Client.pak`
    (`get(nom, pak)` rend les octets d'un fichier)."""
    pak = f"{map_name}_000_000_512_512.Client.pak"
    out: dict[tuple[str, int], np.ndarray] = {}
    for path in db.paths:
        if not path.endswith("_MapRegion.xdb"):
            continue
        data = get(path.replace("_MapRegion.xdb", "_lightvrt.bin"), pak)
        if data:
            for k, v in parse_lightvrt(zlib.decompress(data)).items():
                out[(path, k)] = v
    return out


def read_zone_light(db: PackDB) -> dict:
    """Premier éclairage de la zone de la carte (+ le ciel)."""
    zones = [z for z in db.resources("ZoneLights") if not z & (1 << 40)]
    if not zones:
        return {}
    items = db.elements(zones[0] + ZONE_LIGHTS, ZONE_LIGHT_STRIDE)
    if not items:
        return {}
    e = items[0]
    sky = db.ptr(zones[0] + ZONE_SKY)
    return {"ambient": db.u32(e + 0x24), "ambientFactor": round(db.f32(e + 0x28), 4),
            "diffuse": db.u32(e + 0x30), "fog": db.u32(e + 0x3C), "fogEnd": round(db.f32(e + 0x40), 3),
            "fogStart": round(db.f32(e + 0x44), 3), "pointLight": db.u32(e + 0x48),
            "selfIllum": db.u32(e + 0x4C), "specular": db.u32(e + 0x54),
            "sunPitch": round(db.f32(e + 0x5C), 3), "sunYaw": round(db.f32(e + 0x60), 3),
            "sky": sky, "skyGeometry": db.ptr(sky + SKY_GEOMETRY) if sky is not None else None}
