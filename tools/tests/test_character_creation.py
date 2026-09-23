"""Tests de la création de personnage : décodeurs (`allods_chargen`), interface (`chargen_ui`),
décors (`chargen_scene`) et extracteur (`extract_character_creation`).

Les tests synthétiques ne lisent aucun client ; ceux marqués `client` vérifient les décalages
sur les vraies données du client RU 17 (et le 7.0 pour les recoupements) et sont sautés quand
elles manquent.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tools import allods_chargen as ac
from tools.allods_packdb import packs_path
from tools.chargen_scene import _tokens, ambience_wave, chargen_sound_events
from tools.chargen_ui import UiExtractor
from tools.extract_character_creation import UI_CLASS_ORDER, UI_RACE_ORDER, class_key, with_fr

CLIENT = Path("/mnt/h/MyGames/AllodsRU")
client = pytest.mark.skipif(not packs_path(CLIENT / "data" / "Packs" / "BaseLocall_x64.pak").is_file(),
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


def test_ambience_tokens_and_loop_match():
    assert _tokens("SteppeWindy_AP") == ["steppe", "wind"]
    assert _tokens("DeathRealm") == ["death", "realm"]
    index = {"steppewindlp": [("SFX/Ambience/Ambience_Steppe.bsb", 1, "steppe_wind_lp")],
             "steppewind01": [("SFX/Ambience/Ambience_Steppe.bsb", 2, "steppe_wind_01")],
             "deathrealmambientlp": [("SFX/Music/Music_Zone.fsb", 23, "DeathRealmAmbient_lp")]}
    assert ambience_wave("Ambience/X/SteppeWindy_AP", index)[2] == "steppe_wind_lp"
    assert ambience_wave("Ambience/Zones/DeathRealm", index)[2] == "DeathRealmAmbient_lp"
    assert ambience_wave("Ambience/Zones/AI36", index) is None          # pas d'invention


def test_chargen_sound_keys():
    bank = "SFX/Interface/Chargen.bsb"
    index = {"a": [(bank, 1, "ClassSelectMage")], "b": [(bank, 2, "FactionSelect")],
             "c": [(bank, 3, "ChargenLigaElfMageMale")], "d": [(bank, 4, "ChargenImpOrcDruidMale")],
             "e": [("SFX/Other.bsb", 1, "ClassSelectBard")]}
    assert chargen_sound_events(index) == {"class:MAGE": "ClassSelectMage", "faction": "FactionSelect",
                                           "voice:Elf/MAGE": "ChargenLigaElfMageMale",
                                           "voice:Orc/DRUID": "ChargenImpOrcDruidMale"}


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
    ui = UiExtractor(db, packs_path(CLIENT / "data" / "Packs"), tmp_path)
    root = ui.widget(db.ptr(addon + 0x28))
    panels = {c["name"]: c for c in root["children"][0]["children"]}
    assert list(panels) == ["Progress", "Factions", "RaceClass", "Customization"]
    # Visibilité initiale : la progression et les panneaux montrés par les scripts partent cachés.
    assert panels["Progress"].get("hidden") and panels["Customization"].get("hidden")
    assert not panels["RaceClass"].get("hidden")
    # Variantes de bouton par place : la plaque de classe choisie (variante 1) a seule un calque normal.
    plate = next(c for c in panels["RaceClass"]["children"] if c["name"] == "Class")["children"][0]
    button = next(c for c in plate["children"] if c["name"] == "Button")
    assert "normal" not in button["variants"][0] and "highlight" in button["variants"][0]
    assert "normal" in button["variants"][1]
    # Libellé fixe « Пол » du panneau du sexe (identifiant de texte du `WidgetTextView`).
    gender = next(c for c in panels["RaceClass"]["children"] if c["name"] == "GenderPanel")
    assert next(c for c in gender["children"] if c["name"] == "Label").get("textId")
    bottom = ui.wrap_bottom_line()
    assert bottom["place"]["y"] == {"align": "high", "size": 67.0} and bottom["back"]["texture"] == "BottomLine"
    icons = ui.related_textures(ac.addon_texture_groups(db, addon)["ClassIcons"])
    assert {"Paladin", "Priest", "Druid"} <= set(icons)      # Paladin/Prêtre : pak localisé


@client
def test_elf_female_morph_presets_match_the_70_xdb(pack):
    db, _ = pack
    fem = next(e.template for e in ac.walk_root(db) if e.race == "Elf" and e.cls == "MAGE"
               and ac.read_template(db, e.template).name == "ElfFemale")
    morph = ac.read_morph(db, db.ptr(fem + ac.VCT_MORPH))
    assert len(morph["presets"]) == 9 and len(morph["controls"]) == 15
    # ElfFemaleMorphSettings.(ModelMorphSettings).xdb (7.0) : dernier préréglage, Height 0,88, Breast 0,85.
    assert morph["presets"][-1]["0"] == pytest.approx(0.88) and morph["presets"][-1]["6"] == pytest.approx(0.85)
    assert morph["controls"]["0"][0] == {"bone": "Global", "power": [1.0, 1.0, 1.0]}


@client
def test_menu_zone_light_and_ambience_grid(pack):
    from tools.allods_packdb import open_map
    from tools.chargen_scene import REGION_AMBIENCES, zone_light, zone_lights_at
    db, _ = pack
    mp = open_map(db, CLIENT, "MainMenu")
    place = {s.name: s for s in ac.character_scenes(db)}["CharacterSelectElf"].character
    light = zone_light(mp, zone_lights_at(mp, place))
    assert light["ambient"] & 0xFFFFFF == 0x312E47 and light["fogEnd"] == 220.0
    amb = zone_lights_at(mp, place, REGION_AMBIENCES, reach=2)
    assert mp.string(amb + 0x58) == "Ambience/OutdoorAmbience/Zones/AI36"
