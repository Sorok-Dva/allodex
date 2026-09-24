#!/usr/bin/env python3
"""Écran de création de personnage d'Allods Online (client RU 17.x) : données, modèles, décors.

Source : le **dernier client** (`/mnt/h/MyGames/AllodsRU`), qui compile tout dans
`Bin/pack.bin` (lu par `tools/allods_packdb.py`) et, pour les objets de carte, dans
`Bin/Maps_<carte>.bin` (même format). Les chaînes de données sont décrites dans
`tools/allods_chargen.py` ; l'interface (addon `CharacterGenerator`) dans `tools/chargen_ui.py`.

Sorties (`public/game/character/`) :

* `chargen.json` — index : textes (ru/en/fr), factions, races, classes, combinaisons race × classe
  × sexe (tenues des trois niveaux, animations, familier), gabarits (variations de visage,
  coiffure, couleurs…), objets (géosets, patchs de texture, modèles accrochés), décors ;
* `ui/` — l'arbre de widgets de l'addon (`layout.json`) et ses textures ;
* `models/<Gabarit>.glb` — personnage et familiers : tous les géosets (un primitif par géoset,
  `extras.element`), squelette, `Idle01` et les animations de création de ses classes ;
* `attach/<nom>.glb` — modèles accrochés (casques, épaulières, armes) ;
* `textures/` — peaux, patchs, cheveux, pelages (PNG) ;
* `scenes/<Race>.glb` + `scenes/<Race>.json` — le décor de la race (carte `MainMenu`), centré
  sur la place du personnage, avec lumière, brouillard et caméra.

Usage : python3 tools/extract_character_creation.py [--only Elf] [--no-models] [--no-scenes]
        [--no-ui] [--client /mnt/h/MyGames/AllodsRU]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import allods_chargen as ac  # noqa: E402
from tools.allods_packdb import PackDB, PakCatalog, open_catalog, open_pack, packs_path, vote_pak_codes  # noqa: E402
from tools.allods_visdb import read_geometry, read_visobject  # noqa: E402
from tools.chargen_gltf import (  # noqa: E402
    BinSource, Exporter, TexturePool, load_animation, load_geometry,
)
from tools.chargen_ui import UiExtractor  # noqa: E402
from tools.packbin import LocTable, inflate  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE / "character_creation_manifest.json"
DEFAULT_OUT = HERE.parent / "public" / "game" / "character"
SCHEMA_VERSION = 1

# Textures exportées à leur taille d'origine, en WebP (décision de l'utilisateur : pas de
# réduction ; voir `chargen_scene.WebpTexturePool`) — la peau cuite fait 512, les patchs et
# coiffures 64 à 256, les pelages des familiers 512, les décors jusqu'à 2048.
CHARACTER_TEXTURE_MAX = 4096
IDLE = "Idle01"


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text)


# --- contexte ------------------------------------------------------------------------------------

@dataclass
class Ctx:
    db: PackDB
    cat: PakCatalog
    bins: BinSource
    textures: TexturePool
    out: Path
    locs: dict[str, LocTable]
    notes: list[str] = field(default_factory=list)
    items: dict[int, dict] = field(default_factory=dict)
    attach: dict[int, str] = field(default_factory=dict)
    fx: object = None          # tools.chargen_fx.CharacterFx
    _pak_listing: dict[str, list[str]] = field(default_factory=dict)

    def text(self, tid: int | None) -> dict[str, str] | None:
        if tid is None or tid in (0, 0xFFFFFFFF):
            return None
        out = {}
        for lang, loc in self.locs.items():
            t = loc.get(tid)
            if t:
                out[lang] = t
        # Le .loc anglais garde des textes non traduits (identiques au russe, en cyrillique).
        if out.get("en") and out.get("en") == out.get("ru") and re.search(r"[Ѐ-ӿ]", out["en"]):
            del out["en"]
        return out or None

    def texture(self, off: int | None, max_size: int = CHARACTER_TEXTURE_MAX) -> str | None:
        if off is None:
            return None
        name = self.cat.name(self.db.binary_ref(off))
        return self.texture_name(name, max_size)

    def texture_name(self, name: str | None, max_size: int = CHARACTER_TEXTURE_MAX) -> str | None:
        uri = self.textures.uri(name, max_size, prefix="textures/")
        if uri is None and name:
            self.notes.append(f"texture illisible : {name}")
        return uri


FR_CLIENT = Path("/mnt/h/MyGames/Allods Online FR (FR)")


def french_texts(fr_client: Path) -> dict | None:
    """Textes français, relus dans le client FR (MY.GAMES Europe) par clé et non par identifiant :
    son `pack.bin` est d'une autre construction (format 15/16, `tools/packbin.py`), mêmes
    structures. Clés : textes de l'addon, noms système des races, classes, combinaisons et factions."""
    pak = packs_path(fr_client / "data" / "Packs" / "BaseLocfra_x64.pak")
    texts = packs_path(fr_client / "data" / "Packs" / "Texts_x64.pak")
    if not pak.is_file() or not texts.is_file():
        return None
    from tools.allods_packdb import default_cache_dir
    from tools.packbin import PackBin
    stat = pak.stat()
    raw_path = default_cache_dir() / f"pack-fr-{stat.st_size}-{int(stat.st_mtime)}.raw"
    if not raw_path.is_file():
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(zlib.decompress(zipfile.ZipFile(pak).read("Bin/pack.bin")))
    pb = PackBin(raw_path.read_bytes())
    loc = LocTable(inflate(zipfile.ZipFile(texts).read("Bin/pack.loc")))
    get = lambda tid: loc.get(tid) if 0 < tid < loc.count else None  # noqa: E731
    out: dict = {"ui": {}, "races": {}, "sexes": {}, "classes": {}, "combos": {}, "factions": {}, "widgets": {}}
    for a in pb.objects_of("UIAddon"):
        if pb.string(a + ac.ADDON_NAME) != "CharacterGenerator":
            continue

        # Textes fixes des widgets (« Sexe »…) : même arbre, identifiant à +0x1B0 dans ce format.
        def walk(w: int | None, path: str, depth: int = 0) -> None:
            if w is None or depth > 16:
                return
            path = f"{path}/{pb.string(w + 0x58) or ''}"
            if pb.type_at(w) == "WidgetTextView":
                txt = get(pb.u64(w + 0x1B0))
                if txt:
                    out["widgets"][path] = txt
            d, n = pb.vector(w + 0x30)
            for k in range(0, n if d is not None else 0, 8):
                walk(pb.ptr(d + k), path, depth + 1)
        walk(pb.ptr(a + 0x28), "")
        # vecteur des groupes de textes : premier vecteur dont les entrées (40 o) pointent un UIRelatedTexts
        for o in range(a + 0x80, a + 0x140, 8):
            d, n = pb.data_ptr(o), pb.word(o + 8)
            if d is None or not n or n % 40:
                continue
            if pb.type_at(pb.ptr(d + 0x20) or -1) != "UIRelatedTexts":
                continue
            for k in range(n // 40):
                e = d + 40 * k
                group, rt = pb.string(e + 8), pb.ptr(e + 0x20)
                td, tn = pb.data_ptr(rt + ac.TEXTS_LIST), pb.word(rt + ac.TEXTS_LIST + 8)
                for j in range(tn // ac.TEXT_ENTRY if td is not None else 0):
                    t = td + ac.TEXT_ENTRY * j
                    key, txt = pb.string(t + 8), get(pb.u64(t + 0x38))
                    if key and txt:
                        out["ui"].setdefault(f"{group}:{key}", txt)
            break
    for r in pb.objects_of("CharacterRace"):
        name = pb.string(r + ac.RACE_SYSNAME)
        if name:
            out["races"][name] = get(pb.u64(r + ac.RACE_NAME))
            sx, sn = pb.data_ptr(r + ac.RACE_SEXES), pb.word(r + ac.RACE_SEXES + 8)
            for k in range(sn // 48 if sx is not None else 0):
                e = sx + 48 * k
                out["sexes"][(name, pb.u32(e + 0x28))] = get(pb.u64(e + 0x20))
    for c in pb.objects_of("CharacterClass"):
        name = pb.string(c + ac.CLASS_SYSNAME)
        if name:
            out["classes"][name] = get(pb.u64(c + ac.CLASS_NAME))
    for rc in pb.objects_of("CharacterRaceClass"):
        name = pb.string(rc + ac.RC_SYSNAME)
        if name:
            out["combos"][name] = {"name": get(pb.u64(rc + ac.RC_NAME)), "title": get(pb.u64(rc + ac.RC_TITLE)),
                                   "desc": get(pb.u64(rc + ac.RC_DESC))}
    for f in pb.objects_of("Faction"):
        name = pb.string(f + ac.FACTION_SYSNAME)
        if name and name not in out["factions"]:
            out["factions"][name] = get(pb.u64(f + ac.FACTION_NAME))
    return out


def with_fr(value: dict | None, fr: str | None) -> dict | None:
    if not fr:
        return value
    out = dict(value or {})
    out["fr"] = fr
    return out


def open_locs(client: Path) -> dict[str, LocTable]:
    z = zipfile.ZipFile(packs_path(client / "data" / "Packs" / "Texts_x64.pak"))
    out = {}
    for lang, entry in (("ru", "Bin/pack.rus.loc"), ("en", "Bin/pack.eng_eu.loc")):
        out[lang] = LocTable(inflate(z.read(entry)))
    return out


# --- objets (VisualItem) -------------------------------------------------------------------------

def item_id(off: int) -> str:
    return f"i{off:x}"


def export_item(ctx: Ctx, off: int | None) -> str | None:
    """`VisualItem` → entrée de `chargen.json["items"]` (identifiant stable pour une extraction)."""
    if off is None:
        return None
    if off in ctx.items:
        return item_id(off)
    vi = ac.read_visual_item(ctx.db, off)
    entry: dict = {}
    shapes = {}
    for sex, lst in vi.shapes.items():
        out = []
        for s in lst:
            d: dict = {}
            if s.geoset:
                d["geoset"] = s.geoset
            if s.visobject is not None:
                model = export_attachment(ctx, s.visobject)
                if model:
                    d["model"] = model
                    d["locator"] = s.locator or ""
                # Effets de l'objet (boule de feu du mage) : gabarit complet, particules comprises.
                from tools.chargen_fx import has_effect
                if ctx.fx is not None and has_effect(ctx.db, ctx.cat, s.visobject):
                    fx = ctx.fx.export(s.visobject)
                    if fx:
                        d["fx"] = fx
                        d["locator"] = s.locator or ""
            if s.replacement is not None:
                tex = ctx.texture(s.replacement)
                if tex:
                    d["texture"] = tex
            if s.color not in (0xFFFFFFFF, 0):
                d["color"] = ac.color_argb(s.color)
            if d:
                out.append(d)
        if out:
            shapes[sex] = out
    if shapes:
        entry["shapes"] = shapes
    if vi.hidden:
        entry["hidden"] = vi.hidden
    patches = {}
    for sex, lst in vi.patches.items():
        out = []
        for p in lst:
            tex = ctx.texture(p.texture)
            if tex:
                out.append({"rect": list(p.rect), "texture": tex})
        if out:
            patches[sex] = out
    if patches:
        entry["patches"] = patches
    if vi.underwear:
        entry["underwear"] = vi.underwear
    ctx.items[off] = entry
    return item_id(off)


# --- modèles -------------------------------------------------------------------------------------

def pak_listing(ctx: Ctx, pak: str) -> list[str]:
    if pak not in ctx._pak_listing:
        ctx._pak_listing[pak] = ctx.cat.names.get(pak, [])
    return ctx._pak_listing[pak]


def animation_files(ctx: Ctx, geometry_binary: str, wanted: list[str]) -> dict[str, str]:
    """Fichiers `<dossier>/Animations/<Modèle>.<Nom>.(SkeletalAnimation).bin`, casse ignorée."""
    folder, stem = geometry_binary.rsplit("/", 1)
    stem = stem.split(".")[0]
    prefix = f"{folder}/Animations/{stem}.".lower()
    want = {w.lower(): w for w in wanted}
    out: dict[str, str] = {}
    for pak in ("Characters.Mini.pak", "Creatures.Mini.pak"):
        for name in pak_listing(ctx, pak):
            low = name.lower()
            if low.startswith(prefix) and low.endswith(".(skeletalanimation).bin"):
                clip = low[len(prefix):-len(".(skeletalanimation).bin")]
                if clip in want and want[clip] not in out:
                    out[want[clip]] = name
    return out


def find_idle(ctx: Ctx, geometry_binary: str) -> str | None:
    folder, stem = geometry_binary.rsplit("/", 1)
    stem = stem.split(".")[0]
    prefix = f"{folder}/Animations/{stem}.".lower()
    cands = []
    for pak in ("Characters.Mini.pak", "Creatures.Mini.pak"):
        for name in pak_listing(ctx, pak):
            low = name.lower()
            if low.startswith(prefix) and ".idle" in low and low.endswith(".(skeletalanimation).bin"):
                cands.append(name)
    cands.sort(key=lambda n: (0 if ".idle01." in n.lower() else 1 if ".idle." in n.lower() else 2, n))
    return cands[0] if cands else None


def build_model(ctx: Ctx, name: str, vot_off: int, clips: list[str], baked: int | None = None
                ) -> tuple[bytes, dict] | None:
    db, cat = ctx.db, ctx.cat
    vot = read_visobject(db, cat, vot_off)
    if vot.geometry is None:
        ctx.notes.append(f"{name} : gabarit sans géométrie")
        return None
    loaded = load_geometry(db, cat, ctx.bins, vot.geometry)
    if loaded is None or loaded.skeleton is None:
        ctx.notes.append(f"{name} : géométrie ou squelette illisible")
        return None
    exporter = Exporter(ctx.textures, CHARACTER_TEXTURE_MAX)
    elements = list(loaded.geo.doc.elements)
    mesh, skinned = exporter.emit_mesh(name, loaded.geo, loaded.vertices, loaded.indices, elements, loaded.skeleton)
    if mesh is None:
        ctx.notes.append(f"{name} : aucun géoset")
        return None
    skeleton = loaded.skeleton
    joints = exporter.emit_skeleton(skeleton, name)
    static_node = exporter.gltf.add_node({"name": f"{name}/Static"})
    mesh_node = {"name": f"{name}_mesh", "mesh": mesh}
    if skinned:
        mesh_node["skin"] = exporter.skin(name, skeleton, joints, static_node)
    roots = [joints[i] for i in range(len(skeleton)) if not (0 <= skeleton.parents[i] < len(skeleton))]
    span = float(np.max(np.abs(loaded.vertices["position"])) * 4.0)
    binary = loaded.geo.binary or ""
    files = animation_files(ctx, binary, clips)
    idle = find_idle(ctx, binary)
    if idle:
        files.setdefault("idle", idle)
    durations = {}
    for clip, file in sorted(files.items()):
        anim = load_animation(ctx.bins, file, skeleton, span)
        if anim is None:
            ctx.notes.append(f"{name} : animation illisible {file}")
            continue
        durations[clip] = round(exporter.emit_clip(clip, skeleton, joints, anim), 4)
    for clip in clips:
        if clip not in durations:
            ctx.notes.append(f"{name} : animation absente {clip}")
    root = exporter.gltf.add_node({"name": name, "children": roots + [static_node, exporter.gltf.add_node(mesh_node)],
                                   **({"scale": [vot.scale] * 3} if abs(vot.scale - 1) > 1e-6 else {})})
    # Matériaux de la peau cuite : repérés pour que le lecteur y pose la texture composée.
    baked_name = cat.name(db.binary_ref(baked)) if baked is not None else None
    baked_uri = ctx.textures.uri(baked_name, CHARACTER_TEXTURE_MAX, prefix="../textures/") if baked_name else None
    gl = exporter.gltf.json
    for m in gl.get("materials", []):
        tex = m.get("pbrMetallicRoughness", {}).get("baseColorTexture")
        if tex is not None and baked_uri and gl["images"][gl["textures"][tex["index"]]["source"]]["uri"] == baked_uri:
            m.setdefault("extras", {})["baked"] = True
    glb = exporter.finish([root])
    ctx.notes.extend(f"{name} : {n}" for n in exporter.notes)
    pos = loaded.vertices["position"]
    meta = {
        "glb": f"models/{name}.glb",
        "binary": binary,
        "scale": round(float(vot.scale), 4),
        "height": round(float(pos[:, 2].max() * vot.scale), 3),
        "elements": [e.name for e in elements],
        "joints": list(skeleton.names),
        "clips": durations,
        "bytes": len(glb),
    }
    return glb, meta


def export_attachment(ctx: Ctx, vot_off: int) -> str | None:
    """Modèle accroché (casque, épaulière, arme) : maillage statique à sa pose de bind."""
    if vot_off in ctx.attach:
        return ctx.attach[vot_off]
    db, cat = ctx.db, ctx.cat
    vot = read_visobject(db, cat, vot_off)
    ctx.attach[vot_off] = None
    if vot.geometry is None:
        return None
    loaded = load_geometry(db, cat, ctx.bins, vot.geometry)
    if loaded is None:
        return None
    name = slug(vot.name)
    exporter = Exporter(ctx.textures, CHARACTER_TEXTURE_MAX)
    elements = [e for e in loaded.geo.doc.elements if e.material.texture]
    mesh, _ = exporter.emit_mesh(name, loaded.geo, loaded.vertices, loaded.indices, elements, None)
    if mesh is None:
        return None
    node = exporter.gltf.add_node({"name": name, "mesh": mesh,
                                   **({"scale": [vot.scale] * 3} if abs(vot.scale - 1) > 1e-6 else {})})
    glb = exporter.finish([node])
    (ctx.out / "attach").mkdir(parents=True, exist_ok=True)
    file = f"attach/{name}.glb"
    k = 2
    while (ctx.out / file).exists() and file in ctx.attach.values():
        file = f"attach/{name}_{k}.glb"
        k += 1
    (ctx.out / file).write_bytes(glb)
    ctx.attach[vot_off] = file
    return file


# --- gabarits et variations ------------------------------------------------------------------------

def export_template(ctx: Ctx, off: int, clips: list[str], build: bool) -> tuple[str, dict]:
    db = ctx.db
    t = ac.read_template(db, off)
    vot = read_visobject(db, ctx.cat, t.visobject) if t.visobject else None
    geo = read_geometry(db, ctx.cat, vot.geometry) if vot and vot.geometry else None
    name = t.name if not t.name.startswith("vct_") else slug(Path(geo.binary or t.name).name.split(".")[0])
    entry: dict = {"gender": {1: "male", 2: "female"}.get(t.gender, "none")}
    if build and t.visobject is not None:
        res = build_model(ctx, name, t.visobject, clips, t.baked)
        if res:
            glb, meta = res
            (ctx.out / "models").mkdir(parents=True, exist_ok=True)
            (ctx.out / meta["glb"]).write_bytes(glb)
            entry.update(meta)
            print(f"  {name:>18}  {len(glb) / 1024:.0f} Kio  {len(meta['clips'])} clips")
    if t.baked is not None:
        baked = ctx.texture(t.baked)
        if baked:
            entry["baked"] = baked
    entry["hairColored"] = t.hair_colored
    sp = [{"rect": list(p.rect), "texture": ctx.texture(p.texture)} for p in t.special_hair_patch]
    if sp:
        entry["specialHairPatch"] = sp
    entry["ui"] = t.ui_scene
    entry["defaultDress"] = export_item(ctx, t.default_dress)
    entry["underwear"] = export_item(ctx, t.underwear)
    if t.variations is not None:
        v = ac.read_variations(db, t.variations)
        skins = []
        for s in v.skins:
            binary = ac.indexed_texture_binary(db, ctx.cat, s)
            skins.append(ctx.texture_name(binary))
        var = {
            "faces": [export_item(ctx, x) for x in v.faces],
            "facials": [export_item(ctx, x) for x in v.facials],
            "hairs": [export_item(ctx, x) for x in v.hairs],
            "hairColors": [ac.color_argb(c) for c in v.hair_colors],
            "skins": skins,
            "skinColors": [ac.color_argb(c) for c in v.skin_colors],
            "additionals": [export_item(ctx, x) for x in v.additionals],
            "shoulderStones": [export_item(ctx, x) for x in v.shoulder_stones],
            "shoulderStoneColors": [ac.color_argb(c) for c in v.shoulder_stone_colors],
        }
        default = {}
        for key, lst_key, lst in (("face", "faces", v.faces), ("facial", "facials", v.facials),
                                  ("hair", "hairs", v.hairs), ("additional", "additionals", v.additionals),
                                  ("skin", "skins", v.skins)):
            p = v.default.get(key)
            if p is not None and p in lst:
                default[lst_key] = lst.index(p)
        for key, lst_key, lst in (("hairColor", "hairColors", v.hair_colors), ("skinColor", "skinColors", v.skin_colors),
                                  ("shoulderStoneColor", "shoulderStoneColors", v.shoulder_stone_colors)):
            c = v.default.get(key)
            if c in lst:
                default[lst_key] = lst.index(c)
        morph = ac.read_morph(db, db.ptr(off + ac.VCT_MORPH))
        if morph:
            entry["morph"] = morph["controls"]
            var["morphPresets"] = morph["presets"]
            # Préréglage par défaut : le plus proche de l'échelle 1 (le client n'en désigne pas).
            default["morphPresets"] = min(range(len(morph["presets"])),
                                          key=lambda i: sum(abs(v - 1) for v in morph["presets"][i].values()))
        var["default"] = default
        entry["variations"] = {k: val for k, val in var.items() if val not in ([], {})}
    return name, entry


# --- index ---------------------------------------------------------------------------------------

UI_RACE_ORDER = ["Kania", "Elf", "Gibberling", "Hadagan", "Orc", "Undead", "Praiden", "Aed"]
RACE_SCENE = {"Kania": "CharacterSelectKania", "Elf": "CharacterSelectElf", "Gibberling": "CharacterSelectGibberling",
              "Hadagan": "CharacterSelectHadagan", "Orc": "CharacterSelectOrc", "Undead": "CharacterSelectUndead",
              "Praiden": "CharacterSelectPraiden", "Aed": "CharacterSelectAed"}
# Classes des plaques ClassPlate01…11 : ordre des icônes `ClassIcons` de l'addon (celui du script
# `ScriptRaceClass`, dont les constantes LuaJIT sont rangées à rebours).
UI_CLASS_ORDER = ["DRUID", "MAGE", "NECROMANCER", "PALADIN", "PRIEST", "PSIONIC", "STALKER", "WARRIOR", "BARD",
                  "ENGINEER", "WARLOCK"]


def class_key(sysname: str) -> str:
    return sysname.capitalize()


def run(out: Path, client: Path, only: list[str] | None, models: bool, scenes: bool, ui: bool) -> dict:
    db = open_pack(client)
    cat = open_catalog(db, client)
    packs = packs_path(client / "data" / "Packs")
    bins = BinSource([], [str(packs / p) for p in sorted(cat.names)])
    from tools.chargen_scene import WebpTexturePool
    for old in (out / "textures").glob("*.png"):   # PNG réduits des extractions précédentes
        old.unlink()
    textures = WebpTexturePool(db, cat, bins, out)
    ctx = Ctx(db, cat, bins, textures, out, open_locs(client))
    if models:
        from tools.chargen_fx import CharacterFx
        ctx.fx = CharacterFx(db, cat, bins, textures, out)
    out.mkdir(parents=True, exist_ok=True)

    addon = ac.find_addon(db, "CharacterGenerator")
    raw_texts = ac.addon_texts(db, addon)
    fr = french_texts(FR_CLIENT) or {"ui": {}, "races": {}, "sexes": {}, "classes": {}, "combos": {}, "factions": {}}
    texts = {k: with_fr(ctx.text(v), fr["ui"].get(f"Common:{k}")) for k, v in raw_texts.get("Common", {}).items()}
    progress = {k: with_fr(ctx.text(v), fr["ui"].get(f"CharacterGenerationProgressTooltip:{k}"))
                for k, v in raw_texts.get("CharacterGenerationProgressTooltip", {}).items()}

    index: dict = {"schema": SCHEMA_VERSION, "client": "RU 17.x (Bin/pack.bin)", "texts": texts,
                   "progress": progress, "raceOrder": UI_RACE_ORDER, "classOrder": UI_CLASS_ORDER}

    # interface
    if ui:
        uix = UiExtractor(db, packs, out / "ui")
        layout = uix.widget(db.ptr(addon + 0x28))
        related = {k: uix.related_textures(v) for k, v in ac.addon_texture_groups(db, addon).items()}
        (out / "ui").mkdir(parents=True, exist_ok=True)
        bottom = uix.wrap_bottom_line()

        def resolve(w: dict, path: str) -> None:
            path = f"{path}/{w.get('name') or ''}"
            tid = w.pop("textId", None)
            if tid is not None:
                t = with_fr(ctx.text(tid), fr.get("widgets", {}).get(path))
                if t:
                    w["text"] = t
            for c in w.get("children", []):
                resolve(c, path)
        resolve(layout, "")
        (out / "ui" / "layout.json").write_text(json.dumps({"root": layout, "related": related, "bottomLine": bottom,
                                                           "textures": uix.textures}, ensure_ascii=False,
                                                          separators=(",", ":")), encoding="utf-8")
        index["ui"] = {"layout": "ui/layout.json", "related": related}
        print(f"interface : {len(uix.textures)} textures")

    # Règles de nommage (`NameRules`) : alphabet (expression régulière, texte localisé), longueurs
    # maximale (+0x88) et minimale (+0x8C) ; une règle cyrillique (serveurs russes), des latines.
    rules = []
    for r in db.resources("NameRules"):
        pattern = (ctx.text(db.u32(r + 0x40)) or {}).get("ru")
        if pattern and pattern.startswith("["):
            rule = {"pattern": pattern, "max": db.u32(r + 0x88), "min": db.u32(r + 0x8C)}
            if rule not in rules:
                rules.append(rule)
    index["nameRules"] = rules

    # factions, races, classes
    order = ac.root_order(db)
    factions, races, classes = [], {}, {}
    for fac, rlist in order:
        fname = db.string(fac + ac.FACTION_SYSNAME)
        factions.append({"id": fname, "name": with_fr(ctx.text(db.u32(fac + ac.FACTION_NAME)), fr["factions"].get(fname)),
                         "races": [db.string(r + ac.RACE_SYSNAME) for r, _ in rlist]})
        for r, clist in rlist:
            rname = db.string(r + ac.RACE_SYSNAME)
            sexes = {}
            for e in db.elements(r + ac.RACE_SEXES, 48):
                idx = db.u32(e + 0x28)
                sexes[{1: "male", 2: "female"}.get(idx, str(idx))] = with_fr(ctx.text(db.u32(e + 0x20)),
                                                                             fr["sexes"].get((rname, idx)))
            races[rname] = {"faction": fname, "name": with_fr(ctx.text(db.u32(r + ac.RACE_NAME)), fr["races"].get(rname)),
                            "sexNames": sexes,
                            "motto": texts.get(rname), "desc": texts.get(rname + "Desc"),
                            "classes": [db.string(c + ac.CLASS_SYSNAME) for c in clist], "scene": rname}
            for c in clist:
                cname = db.string(c + ac.CLASS_SYSNAME)
                classes.setdefault(cname, {"name": with_fr(ctx.text(db.u32(c + ac.CLASS_NAME)), fr["classes"].get(cname)),
                                           "label": texts.get(class_key(cname))})
    index["factions"] = factions
    index["races"] = races
    index["classes"] = classes

    # combinaisons
    combos: dict[str, dict] = {}
    template_clips: dict[int, set[str]] = {}
    template_of: dict[int, str] = {}
    pet_templates: dict[int, set[str]] = {}
    entries = ac.walk_root(db)
    for e in entries:
        if only and e.race not in only:
            continue
        if e.template is None or e.character is None:
            continue
        rc = e.race_class
        key = f"{e.race}/{e.cls}"
        rc_fr = fr["combos"].get(db.string(rc + ac.RC_SYSNAME) or "", {})
        rc_entry = combos.setdefault(key, {"race": e.race, "class": e.cls,
                                           "name": with_fr(ctx.text(db.u32(rc + ac.RC_NAME)), rc_fr.get("name")),
                                           "title": with_fr(ctx.text(db.u32(rc + ac.RC_TITLE)), rc_fr.get("title")),
                                           "desc": with_fr(ctx.text(db.u32(rc + ac.RC_DESC)), rc_fr.get("desc")),
                                           "sexes": {}})
        t = ac.read_template(db, e.template)
        gender = {1: "male", 2: "female"}.get(t.gender, str(e.sex))
        growths = []
        for g in ac.read_growths(db, e.character):
            growths.append({"start": g.start, "loop": g.loop,
                            "items": [{"slot": s, "item": export_item(ctx, i)} for s, i in g.items],
                            "fx": [{"locator": f["locator"], "scale": f["scale"], "runType": f["runType"],
                                    "fx": ctx.fx.export(f["visObject"]) if ctx.fx is not None else None}
                                   for f in g.fx if f["visObject"] is not None]})
            for clip in (g.start, g.loop):
                if clip:
                    template_clips.setdefault(e.template, set()).add(clip[0].upper() + clip[1:])
        sex_entry = {"template": None, "growths": growths}
        template_of.setdefault(e.template, "")
        sex_entry["_template"] = e.template
        if e.pet_template is not None:
            pet_templates.setdefault(e.pet_template, set()).add(e.race)
            sex_entry["_pet"] = e.pet_template
        rc_entry["sexes"][gender] = sex_entry

    templates: dict[str, dict] = {}
    names: dict[int, str] = {}
    print("gabarits :")
    for off in sorted(template_of):
        name, entry = export_template(ctx, off, sorted(template_clips.get(off, [])), models)
        names[off] = name
        templates[name] = entry
    pets: dict[str, dict] = {}
    pet_names: dict[int, str] = {}
    for off in sorted(pet_templates):
        name, entry = export_template(ctx, off, [], models)
        pet_names[off] = name
        entry["races"] = sorted(pet_templates[off])
        pets[name] = entry
    for c in combos.values():
        for s in c["sexes"].values():
            s["template"] = names[s.pop("_template")]
            if "_pet" in s:
                s["pet"] = pet_names[s.pop("_pet")]
    # Familiers proposés par race : l'« Облик » du script choisit parmi eux, l'« Окрас » (faces)
    # parmi les pelages du familier choisi.
    for rname, race in races.items():
        race_pets = sorted({s["pet"] for k, c in combos.items() if c["race"] == rname for s in c["sexes"].values()
                            if "pet" in s})
        if race_pets:
            race["pets"] = race_pets
    index["combos"] = combos
    index["templates"] = templates
    index["pets"] = pets
    index["items"] = {item_id(k): v for k, v in sorted(ctx.items.items())}
    if ctx.fx is not None:
        index["fx"] = ctx.fx.finish()
        ctx.notes.extend(ctx.fx.report)
    index["slots"] = sorted({s["slot"] for c in combos.values() for x in c["sexes"].values()
                             for g in x["growths"] for s in g["items"]})

    if scenes:
        from tools.chargen_scene import export_scenes
        index["scenes"] = export_scenes(ctx, [r for r in UI_RACE_ORDER if not only or r in only], RACE_SCENE)
        index["sounds"] = getattr(ctx, "sounds", {})

    index["notes"] = sorted(set(ctx.notes))
    path = out / "chargen.json"
    prev = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    # Sans --models / --scenes, les métadonnées des fichiers déjà extraits sont reprises.
    model_keys = ("glb", "binary", "scale", "height", "elements", "joints", "clips", "bytes")
    for key in ("templates", "pets"):
        for name, entry in index.get(key, {}).items():
            old = prev.get(key, {}).get(name, {})
            if "glb" not in entry and "glb" in old:
                entry.update({k: old[k] for k in model_keys if k in old})
    if not scenes and "scenes" in prev:
        index["scenes"] = prev["scenes"]
        index["sounds"] = prev.get("sounds", {})
    if "fx" not in index and "fx" in prev:
        index["fx"] = prev["fx"]
    if only and path.is_file():
        # extraction partielle : fusion avec l'index existant
        prev = json.loads(path.read_text(encoding="utf-8"))
        for key in ("combos", "templates", "pets", "items", "scenes"):
            merged = dict(prev.get(key, {}))
            merged.update(index.get(key, {}))
            index[key] = merged
    path.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"index : {len(combos)} combinaisons, {len(templates)} gabarits, {len(pets)} familiers, "
          f"{len(index['items'])} objets, {len(ctx.notes)} remarques")
    return index


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--client", type=Path, default=Path("/mnt/h/MyGames/AllodsRU"))
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--only", nargs="*", help="races à extraire (Elf, Kania…)")
    ap.add_argument("--no-models", action="store_true")
    ap.add_argument("--no-scenes", action="store_true")
    ap.add_argument("--no-ui", action="store_true")
    args = ap.parse_args(argv)
    run(args.out, args.client, args.only, not args.no_models, not args.no_scenes, not args.no_ui)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
