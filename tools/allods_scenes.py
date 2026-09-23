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
  de 72 o `(8 inutilisés, f32 x, y, z, f32[4] rotation, f32 échelle en +0x28, StaticObject en
  +0x30)` ; rotation `(0, tangage autour de Y, roulis autour de X, lacet autour de Z)` composée
  `Rz(lacet)·Ry(tangage)·Rx(roulis)` (établi sur l'éclairage précalculé des rochers inclinés de
  `Ferris4` : corrélation 1,000 contre ≤ 0,5 pour le lacet seul), coordonnées locales à la région (256 m : région `i_j` du bloc
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
ZONE_SINGLE_ITEM = 0x48           # éclairage unique en ligne (cartes d'intérieur)
ZONE_SINGLE_POST = 0xF0
SKY_GEOMETRY = 0x100
SKY_PARTS = 0x28               # SkyMesh.parts (208 o : +0x08 animation, +0xB0 géométrie, +0xB8 shift)
SKY_PART_STRIDE = 208


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


def find_camera_action(db: PackDB, off: int | None, depth: int = 0) -> int | None:
    """Première `CameraTrackAction` d'une action, en descendant dans les listes (`VisActionList`)."""
    if off is None or depth > 6:
        return None
    if db.vtype(off) == "CameraTrackAction":
        return off
    for loc, kind, target in db.relocs(off, off + 0x100):
        children = [db.ptr(loc)] if kind == 0 else db.pointers(loc) if kind == 3 else []
        for child in children:
            if child is not None and db.vtype(child):
                found = find_camera_action(db, child, depth + 1)
                if found is not None:
                    return found
    return None


def buff_camera_track(db: PackDB, buff: int) -> CameraTrack | None:
    scripts = buff_scripts(db, buff)
    action = find_camera_action(db, db.ptr(scripts + VIS_SCRIPTS_ACTION) if scripts is not None else None)
    return read_camera_track(db, action) if action is not None else None


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
    # `customData` : une liste (`CustomClientDataList`), ou un seul élément posé directement (un
    # `ClientData` sur quatre : voix seule `IL1/15_Amanda_04`, sous-titre seul…).
    if lst is None:
        elements = []
    elif db.vtype(lst) in ("CreatureVisActionData", "UISubtitleShow"):
        elements = [lst]
    else:
        elements = db.pointers(lst + LIST_ELEMENTS)
    for element in elements:
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

    @property
    def tilt(self) -> tuple[float, float]:
        """(roulis autour de X, tangage autour de Y), nuls pour un objet seulement tourné."""
        return self.rotation[2], self.rotation[1]

    def matrix(self) -> np.ndarray:
        """Rotation 3×3 locale → carte, `Rz(lacet)·Ry(tangage)·Rx(roulis)`."""
        return euler_zyx(self.rotation[2], self.rotation[1], self.rotation[3])


def euler_zyx(rx: float, ry: float, rz: float) -> np.ndarray:
    """`Rz(rz)·Ry(ry)·Rx(rx)` (ordre `ZYX` d'un `THREE.Euler`)."""
    cx, sx, cy, sy, cz, sz = np.cos(rx), np.sin(rx), np.cos(ry), np.sin(ry), np.cos(rz), np.sin(rz)
    x = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    y = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    z = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return z @ y @ x


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
    local = [z for z in db.resources("ZoneLights") if not z & (1 << 40)]
    zones = [z for z in local if db.elements(z + ZONE_LIGHTS, ZONE_LIGHT_STRIDE)]
    if zones:
        e = db.elements(zones[0] + ZONE_LIGHTS, ZONE_LIGHT_STRIDE)[0]
        sky = db.ptr(zones[0] + ZONE_SKY)
    else:
        # Variante à un seul éclairage (`Ferris_indoor`) : l'élément est en ligne en `+0x48`
        # (reconnu à ses `PostEffectParams` en `+0xF0`), sans ciel.
        single = [z for z in local if (t := db.ptr(z + ZONE_SINGLE_POST)) is not None and db.vtype(t) == "PostEffectParams"]
        if not single:
            return {}
        e, sky = single[0] + ZONE_SINGLE_ITEM, None
    return {"ambient": db.u32(e + 0x24), "ambientFactor": round(db.f32(e + 0x28), 4),
            "diffuse": db.u32(e + 0x30), "fog": db.u32(e + 0x3C), "fogEnd": round(db.f32(e + 0x40), 3),
            "fogStart": round(db.f32(e + 0x44), 3), "pointLight": db.u32(e + 0x48),
            "selfIllum": db.u32(e + 0x4C), "specular": db.u32(e + 0x54),
            "sunPitch": round(db.f32(e + 0x5C), 3), "sunYaw": round(db.f32(e + 0x60), 3),
            "sky": sky, "skyGeometry": db.ptr(sky + SKY_GEOMETRY) if sky is not None else None}


def sky_parts(db: PackDB, sky: int | None) -> list[tuple[int, int | None, float]]:
    """Calques d'un `SkyMesh` : (géométrie, animation, décalage vertical `shift`). Recoupé sur
    `AI52_BossFight` (7.0 : `shift` −55 sur l'horizon animé)."""
    if sky is None:
        return []
    out = []
    for e in db.elements(sky + SKY_PARTS, SKY_PART_STRIDE):
        geo = db.ptr(e + 0xB0)
        if geo is not None:
            out.append((geo, db.ptr(e + 0x08), db.f32(e + 0xB8)))
    if not out and db.ptr(sky + SKY_GEOMETRY) is not None:
        out.append((db.ptr(sky + SKY_GEOMETRY), None, 0.0))
    return out


class PackBinView:
    """Vue `PackDB` minimale (lecture des répliques) sur une base lue par `tools/packbin.py` : le client
    FR 16.0 a un `pack.bin` de format 15/16 que `PackDB` ne lit pas, mêmes structures et **mêmes
    identifiants de ressources** que le 17.0 (constat de `tools/extract_lore.py`)."""

    def __init__(self, pb) -> None:
        self.pb = pb
        self.ids = pb.ids

    def u32(self, off: int) -> int:
        return self.pb.u32(off)

    def ptr(self, off: int) -> int | None:
        return self.pb.ptr(off)

    def vtype(self, off: int) -> str | None:
        return self.pb.type_at(off)

    def vec(self, off: int) -> tuple[int, int] | None:
        target, size = self.pb.vector(off)
        return None if target is None else (target, size)

    def elements(self, off: int, stride: int) -> list[int]:
        v = self.vec(off)
        return [] if v is None else [v[0] + stride * k for k in range(v[1] // stride)]

    def pointers(self, off: int) -> list[int]:
        v = self.vec(off)
        if v is None:
            return []
        return [p for p in (self.pb.ptr(v[0] + 8 * k) for k in range(v[1] // 8)) if p is not None]

    def string(self, off: int) -> str | None:
        return self.pb.string(off)
