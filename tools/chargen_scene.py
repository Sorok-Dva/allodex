"""Décors de la création de personnage : la carte `MainMenu` du client 17.

Les objets de carte ne sont pas dans `pack.bin` mais dans une base par carte, `Bin/Maps_MainMenu.bin`
(pak `BaseLocall_x64.pak`, même format ; sa table « code de pak → pak » est votée à part). Elle
contient les huit décors de race (`World/MainMenu/Chargen_<Race>/…_Scene`), leurs objets accrochés,
leurs lumières (`ZoneLights`) et leurs ambiances. Relevés sur les données (septembre 2026) :

* `MapRegion` (256 m de côté, chemin `Maps/MainMenu/000_000/<x>_<y>_MapRegion.xdb`) : objets en
  `+0xA0`, 72 o chacun — position locale `+0x08` (x, y, z), angles `+0x18` (roulis ? tangage ?) et
  lacet `+0x20` (radians), échelle `+0x28`, `StaticObject*` `+0x30` (relocation de genre 0 dans la
  base de la carte, de genre 1 vers un objet de `pack.bin`) ; grille 16 × 16 de `ZoneLights` en
  `+0x160` ;
* `StaticObject` : `VisObjectTemplate*` en `+0x30` ;
* un décor est un `VisObjectTemplate` dont la géométrie a un squelette de « locators »
  (`Slot_SpecialNN`) où s'accrochent d'autres gabarits (`AttachedVisObjectComponent` : décalage,
  rotation, échelle), animés ou non ;
* `ZoneLights` : couleurs ARGB ambiante `+0x6C`, de contour `+0x74`, diffuse (soleil) `+0x78`, du
  brouillard `+0x84`, fin du brouillard `+0x88`, début `+0x8C`, lumière ponctuelle `+0x94`,
  spéculaire `+0x9C`, tangage et lacet du soleil `+0xA4`/`+0xA8` (degrés) — confrontés à
  `Maps/MainMenu/ZoneLights/Hadagan_Chargen.(ZoneLights).xdb` du 7.0 (mêmes couleurs) ;
  `SkyMesh*` en `+0x150`.

La place du personnage et de la caméra vient de `UICharacterScenes` (`CharacterSelect<Race>`),
en coordonnées de carte ; le personnage se tient à l'origine du décor de sa race.
"""
from __future__ import annotations

import hashlib
import json
import math
import mmap
import os
import struct
import zipfile
import zlib
from pathlib import Path

import numpy as np

from tools import allods_chargen as ac
from tools.allods_packdb import PackDB, PakCatalog, default_cache_dir, packs_path, vote_pak_codes
from tools.allods_visdb import read_visobject
from tools.chargen_gltf import Exporter, TexturePool, load_animation, load_geometry

MAP_ENTRY = "Bin/Maps_MainMenu.bin"
REGION = 256.0
REGION_OBJECTS = 0xA0
OBJECT_STRIDE = 72
REGION_ZONE_LIGHTS = 0x160
REGION_AMBIENCES = 0xE0
TASSEL_EVENT = 0x58        # Sound2DTassel : événement FMOD de l'ambiance
STATIC_VISOBJECT = 0x30
PEDESTAL_TOP = 0.28          # dessus de l'estrade de `Chargen_Aed` (sommets à moins de 3 m de l'axe)
SCENE_RADIUS = 40.0        # rayon (m) autour du personnage : le décor et ses voisins immédiats
SCENE_TEXTURE_MAX = 512

ZL_AMBIENT = 0x6C
ZL_DIFFUSE = 0x78
ZL_FOG_COLOR = 0x84
ZL_FOG_END = 0x88
ZL_FOG_START = 0x8C
ZL_POINT = 0x94
ZL_SPECULAR = 0x9C
ZL_SUN_PITCH = 0xA4
ZL_SUN_YAW = 0xA8
ZL_SKY = 0x150


def open_map(client: Path, cache_dir: Path | None = None) -> PackDB:
    pak = packs_path(Path(client) / "data" / "Packs" / "BaseLocall_x64.pak")
    cache_dir = Path(cache_dir or default_cache_dir())
    stat = pak.stat()
    key = hashlib.sha1(f"{pak}:{MAP_ENTRY}:{stat.st_size}:{int(stat.st_mtime)}".encode()).hexdigest()[:12]
    raw_path = cache_dir / f"map-mainmenu-{key}.raw"
    if not raw_path.is_file():
        cache_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(pak) as zf:
            packed = zf.read(MAP_ENTRY)
        try:
            data = zlib.decompress(packed)
        except zlib.error:
            data = packed
        raw_path.write_bytes(data)
    handle = open(raw_path, "rb")
    return PackDB(mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ))


def map_pak_codes(m: PackDB, names: dict[str, list[str]]) -> dict[int, str]:
    """Table « code → pak » propre à la base de la carte (ses codes ne sont pas ceux de
    `pack.bin`). Pour chaque code, le pak retenu est celui où le plus grand nombre de références
    tombent sur un fichier du bon type (`(<Type>).bin`) ; à égalité, le vote par paires de
    textures de `vote_pak_codes` départage (paks de textures, où tout rang tombe sur une texture)."""
    import collections
    from tools.allods_packdb import BINARY_REF
    strong = vote_pak_codes(m, names)
    score: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    for type_name, field in BINARY_REF.items():
        suffix = f"({type_name}).bin"
        for off in m.resources(type_name):
            code, rank = m.u32(off + field), m.u32(off + field + 8)
            for pak, listing in names.items():
                if rank < len(listing) and listing[rank].endswith(suffix):
                    score[code][pak] += 1
    out: dict[int, str] = {}
    for code in set(score) | set(strong):
        counter = score.get(code, collections.Counter())
        best = max(counter.values(), default=0)
        tied = [p for p, v in counter.items() if v == best]
        out[code] = strong[code] if code in strong and (strong[code] in tied or not tied) else (tied[0] if tied else strong[code])
    return out


def _rgb(value: int) -> str:
    return f"#{value & 0xFFFFFF:06x}"


def zone_light(m: PackDB, zl: int) -> dict:
    pitch, yaw = math.radians(m.f32(zl + ZL_SUN_PITCH)), math.radians(m.f32(zl + ZL_SUN_YAW))
    return {
        "ambient": _rgb(m.u32(zl + ZL_AMBIENT)), "sun": _rgb(m.u32(zl + ZL_DIFFUSE)),
        "point": _rgb(m.u32(zl + ZL_POINT)), "specular": _rgb(m.u32(zl + ZL_SPECULAR)),
        "sunPitch": round(m.f32(zl + ZL_SUN_PITCH), 3), "sunYaw": round(m.f32(zl + ZL_SUN_YAW), 3),
        "sunDirection": [round(math.cos(pitch) * math.cos(yaw), 4), round(math.cos(pitch) * math.sin(yaw), 4),
                         round(math.sin(pitch), 4)],
        "fog": {"color": _rgb(m.u32(zl + ZL_FOG_COLOR)), "near": round(m.f32(zl + ZL_FOG_START), 2),
                "far": round(m.f32(zl + ZL_FOG_END), 2)},
    }


def _quat_ypr(yaw: float, pitch: float, roll: float) -> list[float]:
    """Lacet (Z) puis tangage (X) puis roulis (Y), repère du jeu (Z en haut)."""
    def q(axis: int, a: float) -> np.ndarray:
        v = np.zeros(4)
        v[axis] = math.sin(a / 2)
        v[3] = math.cos(a / 2)
        return v

    def mul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        ax, ay, az, aw = a
        bx, by, bz, bw = b
        return np.array([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                         aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz])
    r = mul(mul(q(2, yaw), q(0, pitch)), q(1, roll))
    return [float(x) for x in r]


INDEX_PAGE = 32768


def fix_index_pages(loaded) -> int:
    """Géométries de plus de 32 768 sommets (décors de création) : les indices 16 bits sont
    relatifs à une « page » de 32 768 sommets. Les éléments sont rangés dans l'ordre des sommets ;
    quand la fin de leur plage de sommets (`vb1`) repart loin en arrière, on passe à la page suivante — la
    dernière page finit exactement au dernier sommet (`Interface_Scene` de Kania : 32 976 puis
    208…7 154 = 39 922 sommets). Renvoie le nombre de pages décalées."""
    n = len(loaded.vertices["position"])
    if n <= INDEX_PAGE or any(getattr(e, "vertex_offset", 0) for e in loaded.geo.doc.elements):
        return 0   # décalages exacts (`vertexBufferOffset`) déjà appliqués au chargement
    page, top = 0, 0
    for e in loaded.geo.doc.elements:
        if e.vb1 <= e.vb0:
            continue
        if e.vb1 < top - INDEX_PAGE // 2:
            page += 1
            top = 0
        top = max(top, e.vb1)
        if page and e.vb1 + page * INDEX_PAGE <= n:
            loaded.indices[e.ib0:e.ib1] += page * INDEX_PAGE
    return page


class SceneExporter:
    def __init__(self, dbs: dict[str, tuple[PackDB, PakCatalog]], pool: TexturePool, bins) -> None:
        self.dbs = dbs
        self.ex = Exporter(pool, SCENE_TEXTURE_MAX, cutout=True)
        self.bins = bins
        self.count = 0
        self.clips = 0
        self.notes: list[str] = []

    def emit_vot(self, which: str, vot_off: int | None, depth: int = 0) -> int | None:
        if vot_off is None or depth > 6:
            return None
        db, cat = self.dbs[which]
        if db.vtype(vot_off) != "VisObjectTemplate":
            return None
        vo = read_visobject(db, cat, vot_off)
        self.count += 1
        prefix = f"{vo.name}#{self.count}"
        group: dict = {"name": prefix, "children": []}
        joint_nodes: list[int] = []
        names: list[str] = []
        if vo.geometry is not None:
            try:
                loaded = load_geometry(db, cat, self.bins, vo.geometry)
            except (MemoryError, ValueError, IndexError) as error:
                loaded = None
                self.notes.append(f"géométrie illisible : {vo.name} ({cat.name(db.binary_ref(vo.geometry))}, {type(error).__name__})")
            if loaded is None:
                self.notes.append(f"géométrie illisible : {vo.name}")
            else:
                fix_index_pages(loaded)
                # Quelques sommets non définis (NaN) dans le décor des orques : ramenés à 0, sans
                # quoi le JSON du glTF (min/max des accesseurs) serait invalide.
                for key, arr in loaded.vertices.items():
                    if arr.dtype.kind == "f" and not np.isfinite(arr).all():
                        self.notes.append(f"sommets non finis ramenés à 0 : {vo.name} ({key})")
                        loaded.vertices[key] = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
                elements = [e for e in loaded.geo.doc.elements if e.material.visible and e.material.texture
                            and self.ex.texture(e.material.texture) is not None]
                skeleton = loaded.skeleton if loaded.skeleton is not None and len(loaded.skeleton) else None
                if skeleton is not None:
                    joint_nodes = self.ex.emit_skeleton(skeleton, prefix)
                    names = list(skeleton.names)
                    roots = [joint_nodes[i] for i in range(len(skeleton)) if not (0 <= skeleton.parents[i] < len(skeleton))]
                    group["children"].extend(roots)
                if elements:
                    try:
                        mesh, skinned = self.ex.emit_mesh(prefix, loaded.geo, loaded.vertices, loaded.indices,
                                                          elements, skeleton)
                    except (IndexError, ValueError) as error:
                        self.notes.append(f"géométrie non exportée : {vo.name} ({error})")
                        mesh, skinned = None, False
                    if mesh is not None:
                        node = {"name": f"{prefix}/mesh", "mesh": mesh}
                        if skinned and skeleton is not None:
                            static = self.ex.gltf.add_node({"name": f"{prefix}/Static"})
                            group["children"].append(static)
                            node["skin"] = self.ex.skin(prefix, skeleton, joint_nodes, static)
                        group["children"].append(self.ex.gltf.add_node(node))
                anim_off = vo.animation
                if skeleton is not None and anim_off is not None:
                    file = cat.name(db.binary_ref(anim_off))
                    span = float(np.max(np.abs(loaded.vertices["position"])) * 4.0)
                    anim = load_animation(self.bins, file, skeleton, span) if file else None
                    if anim is not None:
                        self.ex.emit_clip(prefix, skeleton, joint_nodes, anim)
                        self.clips += 1
        for comp in vo.components:
            child = self.emit_vot(which, comp.visobject, depth + 1)
            if child is None:
                continue
            holder = {"name": f"attach:{comp.locator}", "children": [child],
                      "translation": list(comp.offset), "rotation": list(comp.rotation)}
            if abs(comp.scale - 1) > 1e-6 and comp.scale > 0:
                holder["scale"] = [comp.scale] * 3
            h = self.ex.gltf.add_node(holder)
            if comp.locator in names:
                self.ex.gltf.json["nodes"][joint_nodes[names.index(comp.locator)]].setdefault("children", []).append(h)
            else:
                group["children"].append(h)
        if abs(vo.scale - 1) > 1e-6 and vo.scale > 0:
            group["scale"] = [vo.scale] * 3
        if not group["children"]:
            return None
        return self.ex.gltf.add_node(group)


def region_objects(m: PackDB) -> list[dict]:
    out = []
    for path, a in m.paths.items():
        if not path.endswith("MapRegion.xdb"):
            continue
        rx, ry = map(int, path.rsplit("/", 1)[-1].split("_")[:2])
        for e in m.elements(a + REGION_OBJECTS, OBJECT_STRIDE):
            x, y, z = m.floats(e + 0x08, 3)
            roll, pitch, yaw = m.floats(e + 0x18, 3)
            scale = m.f32(e + 0x28)
            rel = m.relocs(e + STATIC_VISOBJECT, e + STATIC_VISOBJECT + 8)
            if not rel:
                continue
            _, kind, so = rel[0]
            out.append({"pos": (rx * REGION + x, ry * REGION + y, z), "rot": (roll, pitch, yaw), "scale": scale,
                        "db": "map" if kind == 0 else "pack", "static": so})
    return out


def scene_origin(m: PackDB, db: PackDB, mcat: PakCatalog, cat: PakCatalog, objects: list[dict],
                 place: np.ndarray, radius: float = 10.0) -> tuple[float, float, float] | None:
    """Position de l'objet de décor de création le plus proche (horizontalement) de la place."""
    best = None
    for obj in objects:
        d = math.hypot(obj["pos"][0] - place[0], obj["pos"][1] - place[1])
        if d > radius or (best is not None and d >= best[0]):
            continue
        dbx, catx = (m, mcat) if obj["db"] == "map" else (db, cat)
        vot = dbx.ptr(obj["static"] + STATIC_VISOBJECT)
        geo = dbx.ptr(vot + 0xC0) if vot is not None else None
        name = catx.name(dbx.binary_ref(geo)) if geo is not None else None
        if name and name.startswith("World/MainMenu/Chargen_"):
            best = (d, obj["pos"])
    return best[1] if best else None


def zone_lights_at(m: PackDB, pos: tuple[float, float, float], grid: int = REGION_ZONE_LIGHTS) -> int | None:
    """Objet de la grille 16 × 16 d'une région (lumières en `+0x160`, ambiances sonores en
    `+0xE0`) sous une position de la carte."""
    rx, ry = int(pos[0] // REGION), int(pos[1] // REGION)
    a = m.paths.get(f"Maps/MainMenu/000_000/{rx}_{ry}_MapRegion.xdb")
    if a is None:
        return None
    cx, cy = int((pos[0] % REGION) // 16), int((pos[1] % REGION) // 16)
    rows = m.elements(a + grid, 32)
    if not rows:
        return None
    row = rows[min(cy, len(rows) - 1)]
    cells = m.pointers(row)
    if not cells:
        return None
    return cells[min(cx, len(cells) - 1)]


def export_scenes(ctx, races: list[str], race_scene: dict[str, str]) -> dict:
    client = Path(ctx.cat.packs_dir).parent.parent
    m = open_map(client)
    # Les codes de pak de la base de carte lui sont propres : aucune reprise de ceux de pack.bin.
    mcat = PakCatalog(ctx.cat.packs_dir, ctx.cat.names, map_pak_codes(m, ctx.cat.names))
    pool = TexturePool(m, mcat, ctx.bins, ctx.out)
    objects = region_objects(m)
    places = {s.name: s for s in ac.character_scenes(ctx.db)}
    out: dict[str, dict] = {}
    (ctx.out / "scenes").mkdir(parents=True, exist_ok=True)
    for race in races:
        place = places.get(race_scene.get(race, ""))
        if place is None:
            ctx.notes.append(f"décor : place absente pour {race}")
            continue
        # Origine : le décor de la race (objet de carte dont la géométrie est sous
        # `World/MainMenu/Chargen_*`), son estrade étant à l'origine de sa géométrie ; le
        # personnage s'y tient. La caméra garde son décalage par rapport à la place du
        # personnage. (Pour sept races la place et le décor coïncident à 0,3 m près ; celle des
        # aèdes est 32 m au-dessus de son décor, la place de sélection n'étant pas l'estrade.)
        P = np.array(place.character)
        decor = scene_origin(m, ctx.db, mcat, ctx.cat, objects, P)
        origin = np.array(decor) if decor is not None else P
        sx = SceneExporter({"map": (m, mcat), "pack": (ctx.db, ctx.cat)}, pool, ctx.bins)
        roots = []
        used = 0
        for obj in objects:
            d = math.hypot(obj["pos"][0] - origin[0], obj["pos"][1] - origin[1])
            if d > SCENE_RADIUS:
                continue
            db = m if obj["db"] == "map" else ctx.db
            vot = db.ptr(obj["static"] + STATIC_VISOBJECT)
            node = sx.emit_vot(obj["db"], vot)
            if node is None:
                continue
            used += 1
            roll, pitch, yaw = obj["rot"]
            holder = {"name": f"object#{used}", "children": [node],
                      "translation": [float(v) for v in (np.array(obj["pos"]) - origin)],
                      "rotation": _quat_ypr(yaw, pitch, roll)}
            if abs(obj["scale"] - 1) > 1e-6 and obj["scale"] > 0:
                holder["scale"] = [float(obj["scale"])] * 3
            roots.append(sx.ex.gltf.add_node(holder))
        offset = P - origin
        # Le personnage se tient sur l'estrade : à sa place quand elle est sur le décor (sept
        # races, 0,2 à 0,4 m au-dessus de l'origine = dessus de l'estrade), sinon au centre de
        # l'estrade (aèdes : dessus mesuré à 0,28 m dans `Chargen_Aed`).
        stand = offset if np.linalg.norm(offset) < 2.0 else np.array([0.0, 0.0, PEDESTAL_TOP])
        meta: dict = {"glb": f"scenes/{race}.glb", "objects": used, "clips": sx.clips,
                      "character": {"yaw": round(place.character_yaw, 3), "scale": round(place.character_scale, 3),
                                    "position": [round(float(v), 3) for v in stand]},
                      "camera": {"position": [round(float(v), 4) for v in (np.array(place.camera) - P)],
                                 "placeOffset": [round(float(v), 3) for v in (P - origin)],
                                 "yaw": round(place.camera_yaw, 3), "pitch": round(place.camera_pitch, 3),
                                 "height": round(place.camera_height, 3), "fov": round(place.fov, 4)},
                      "source": {"scene": place.name, "map": place.map, "position": [round(float(v), 3) for v in P]}}
        zl = zone_lights_at(m, place.character)
        if zl is not None and m.vtype(zl) == "ZoneLights":
            meta["light"] = zone_light(m, zl)
        amb = zone_lights_at(m, place.character, REGION_AMBIENCES)
        if amb is not None and m.vtype(amb) == "Sound2DTassel":
            meta["ambience"] = m.string(amb + TASSEL_EVENT)
        if roots:
            glb = sx.ex.finish(roots)
            (ctx.out / meta["glb"]).write_bytes(glb)
            meta["bytes"] = len(glb)
            meta["stats"] = sx.ex.stats
        ctx.notes.extend(f"décor {race} : {n}" for n in sx.notes + sx.ex.notes)
        (ctx.out / "scenes" / f"{race}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        out[race] = meta
        print(f"  décor {race:>10} : {used} objets, {sx.clips} animations, {meta.get('bytes', 0) / 1024:.0f} Kio")
    return out
