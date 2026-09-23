"""Tests de la création de personnage : décodeurs (`allods_chargen`), interface (`chargen_ui`),
décors (`chargen_scene`) et extracteur (`extract_character_creation`).

Les tests synthétiques ne lisent aucun client ; ceux marqués `client` vérifient les décalages
sur les vraies données du client RU 17 (et le 7.0 pour les recoupements) et sont sautés quand
elles manquent.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from tools import allods_chargen as ac
from tools.chargen_scene import INDEX_PAGE, _quat_ypr, fix_index_pages
from tools.chargen_ui import UiExtractor
from tools.extract_character_creation import UI_CLASS_ORDER, UI_RACE_ORDER, class_key, with_fr

CLIENT = Path("/mnt/h/MyGames/AllodsRU")
client = pytest.mark.skipif(not (CLIENT / "data" / "Packs" / "BaseLocall_x64.pak").is_file(),
                            reason="client RU absent")


# --- synthétique --------------------------------------------------------------------------------

def test_color_argb_signed_and_unsigned():
    assert ac.color_argb(-1) == "#ffffff"
    assert ac.color_argb(-10864996) == "#5a369c"          # 2e couleur de cheveux de l'elfe (xdb 7.0)
    assert ac.color_argb(0xFF123456) == "#123456"


def test_state_of_texture_names():
    assert UiExtractor.state_of("ButtonAcceptPressedHighlighted") == "pressedHighlighted"
    assert UiExtractor.state_of("ButtonAcceptHighlighted") == "highlighted"
    assert UiExtractor.state_of("FactionCurrent") == "current"
    assert UiExtractor.state_of("RacePanel") == "normal"


def _loaded(n_vertices: int, elements: list[tuple[int, int, int, int]], indices: np.ndarray):
    els = [SimpleNamespace(vb0=vb0, vb1=vb1, ib0=ib0, ib1=ib1) for vb0, vb1, ib0, ib1 in elements]
    return SimpleNamespace(vertices={"position": np.zeros((n_vertices, 3), np.float32)},
                           geo=SimpleNamespace(doc=SimpleNamespace(elements=els)), indices=indices)


def test_fix_index_pages_shifts_second_page():
    # Modèle réduit de `Interface_Scene` (Kania) : 32 976 sommets en page 0, puis 208…7 154.
    idx = np.array([0, 1, 32975, 208, 7153, 300], np.uint32)
    loaded = _loaded(39922, [(0, 32976, 0, 3), (208, 7154, 3, 5), (208, 400, 5, 6)], idx)
    assert fix_index_pages(loaded) == 1
    assert loaded.indices.tolist() == [0, 1, 32975, 208 + INDEX_PAGE, 7153 + INDEX_PAGE, 300 + INDEX_PAGE]


def test_fix_index_pages_ignores_small_overlaps_and_small_meshes():
    idx = np.array([10, 20, 2818, 2900], np.uint32)
    loaded = _loaded(40000, [(2917, 4942, 0, 2), (2818, 6550, 2, 4)], idx.copy())
    assert fix_index_pages(loaded) == 0
    assert loaded.indices.tolist() == idx.tolist()
    small = _loaded(1000, [(500, 900, 0, 2), (0, 400, 2, 4)], idx.copy())
    assert fix_index_pages(small) == 0


def test_quat_ypr_is_a_z_rotation_for_yaw_only():
    q = _quat_ypr(np.pi / 2, 0.0, 0.0)
    assert q == pytest.approx([0.0, 0.0, np.sin(np.pi / 4), np.cos(np.pi / 4)])


def test_with_fr_and_class_key():
    assert with_fr({"ru": "Воин"}, "Guerrier") == {"ru": "Воин", "fr": "Guerrier"}
    assert with_fr(None, None) is None
    assert class_key("NECROMANCER") == "Necromancer"
    assert len(UI_CLASS_ORDER) == 11 and len(UI_RACE_ORDER) == 8


# --- vraies données ------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pack():
    from tools.allods_packdb import open_catalog, open_pack
    db = open_pack(CLIENT)
    return db, open_catalog(db, CLIENT)


@client
def test_character_root_lists_the_62_race_class_combinations(pack):
    db, _ = pack
    entries = ac.walk_root(db)
    combos = {(e.race, e.cls) for e in entries}
    assert len(combos) == 62
    assert len(entries) == 124                              # deux sexes par combinaison
    assert {e.faction for e in entries} == {"League", "Empire", "Pridens", "Aed"}
    races = {e.race for e in entries}
    assert races == set(UI_RACE_ORDER)
    # Seuls les Pacificateurs (DRUID) ont un familier à la création.
    assert {e.cls for e in entries if e.pet_template} == {"DRUID"}


@client
def test_elf_female_variations_match_the_70_xdb(pack):
    db, cat = pack
    tpl = next(e.template for e in ac.walk_root(db) if e.race == "Elf" and e.cls == "MAGE" and e.sex == 0)
    t = ac.read_template(db, tpl)
    assert t.name in ("ElfFemale", "ElfMale")
    fem = next(e.template for e in ac.walk_root(db) if e.race == "Elf" and e.cls == "MAGE"
               and ac.read_template(db, e.template).name == "ElfFemale")
    v = ac.read_variations(db, ac.read_template(db, fem).variations)
    # ElfFemaleVariations.(CharacterVariations).xdb (7.0) : 11 visages, 13 traits, 18 teintes ;
    # le 17 a ajouté des coiffures et des couleurs (16 → 17, 34 → 36).
    assert len(v.faces) == 11 and len(v.facials) == 13 and len(v.skin_colors) == 18
    assert ac.color_argb(v.hair_colors[1]) == "#5a369c"
    hair = ac.read_visual_item(db, v.hairs[4])
    assert [s.geoset for s in hair.shapes["unisex"]][0] == "hair_5"
    assert hair.patches["unisex"][0].rect == (0.0, 0.5, 0.0, 0.25)


@client
def test_mage_growths_dress_three_outfits(pack):
    db, _ = pack
    e = next(e for e in ac.walk_root(db) if e.race == "Elf" and e.cls == "MAGE")
    growths = ac.read_growths(db, e.character)
    assert len(growths) == 3
    assert growths[0].loop == "chargenMage" and growths[0].start == "chargenMageStart"
    slots = {s for s, _ in growths[1].items}
    assert {"HELM", "ARMOR", "OFFHAND", "MAINHAND", "RANGED"} <= slots


@client
def test_character_scenes_places(pack):
    db, _ = pack
    places = {s.name: s for s in ac.character_scenes(db)}
    kania = places["CharacterSelectKania"]
    assert kania.map == "Maps/MainMenu/"
    assert kania.character_scale == pytest.approx(1.3)
    assert kania.character == pytest.approx((903.449, 800.95, 23.912), abs=1e-2)


@client
def test_addon_texts_and_ui_tree(pack, tmp_path):
    db, _ = pack
    addon = ac.find_addon(db, "CharacterGenerator")
    texts = ac.addon_texts(db, addon)
    assert set(texts) == {"Common", "RedefineRaceProgressTooltip", "CharacterGenerationProgressTooltip"}
    assert "ControlHairColors" in texts["Common"]
    ui = UiExtractor(db, CLIENT / "data" / "Packs", tmp_path)
    root = ui.widget(db.ptr(addon + 0x28))
    names = [c["name"] for c in root["children"][0]["children"]]
    assert names == ["Progress", "Factions", "RaceClass", "Customization"]
    icons = ui.related_textures(ac.addon_texture_groups(db, addon)["ClassIcons"])
    assert {"Paladin", "Priest", "Druid"} <= set(icons)      # Paladin/Prêtre : pak localisé
