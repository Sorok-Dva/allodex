"""Tests de `tools/extract_talents.py` de bout en bout sur une base v1 synthétique."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.extract_talents import (
    TextSource, drop_untranslated, extract_version, is_ability_type, is_spell_type, is_talent_type, IconSink,
)
from tools.packbin import LocTable
from tools.tests.talents_fixture import build_loc_v2, warrior_fixture


@pytest.fixture()
def spec(tmp_path: Path) -> dict:
    pack, loc, icon = warrior_fixture()
    (tmp_path / "pack.bin").write_bytes(pack)
    (tmp_path / "pack.loc").write_bytes(loc)
    icon_dir = tmp_path / "client"
    (icon_dir / "Interface/Icons").mkdir(parents=True)
    (icon_dir / "Interface/Icons/Test.(UITexture).bin").write_bytes(icon)
    return {
        "id": "9.9", "label": "9.9", "client": "synthétique",
        "pack": [str(tmp_path / "pack.bin"), None],
        "texts": {"fr": [str(tmp_path / "pack.loc"), None]},
        "icon_dirs": [str(icon_dir)], "icon_paks": [],
    }


def test_extraction_bout_en_bout(spec: dict, tmp_path: Path):
    out = tmp_path / "out"
    entry = extract_version(spec, out, IconSink(out / "icons"), log=lambda *_: None)
    assert entry["languages"] == ["fr"]
    assert [c["code"] for c in entry["classes"]] == ["WARRIOR"]
    data = json.loads((out / "9.9" / "warrior.json").read_text())
    assert data["name"] == {"fr": "Guerrier"}

    layers = data["book"]["layers"]
    assert [l["points"] for l in layers] == [0, 5]
    first = layers[0]["cells"]
    assert first[1] is None                                   # NoTalent
    spell = data["talents"][first[0]["talent"]]
    assert spell["kind"] == "spell"
    assert spell["name"] == {"fr": "Frappe"}
    # inclusion <t href> développée, variable conservée
    assert spell["description"]["fr"] == "<html>Attaque de mêlée. Inflige <r name=\"var0\"/> dégâts.</html>"
    assert spell["ranks"] == [{"ref": "Mechanics/Spells/Strike/Spell01.xdb", "vars": {"var0": {"value": 12.5}}}]

    field = data["fields"][0]
    assert field["name"] == {"fr": "Combattant"}
    assert field["icon"] and (out / "icons" / field["icon"]).is_file()
    row = field["rows"][0]
    assert row[1] is None and row[0]["talent"] == row[2]["talent"]
    ability = data["talents"][row[0]["talent"]]
    assert ability["name"] == {"fr": "Rage"}
    assert ability["description"] == {"fr": "Augmente la rage."}      # rôle « _Desc »
    assert [r["ref"] for r in ability["ranks"]] == ["Mechanics/Abilities/Rage/Ability01.xdb", "Mechanics/Abilities/Rage/Ability02.xdb"]
    assert "missing" not in ability or "name" not in ability["missing"]


def test_expand_inclusion_v2_par_identifiant():
    src = TextSource("en", loc=LocTable(build_loc_v2(["Fire", 'Cast <t href="0000000000000000"/>!'])))
    assert src.expand(src.by_id(1)) == "Cast Fire!"


def test_drop_untranslated():
    vals = {"en": "Огонь", "ru": "Огонь"}
    drop_untranslated(vals)
    assert vals == {"ru": "Огонь"}
    vals = {"en": "Fire", "ru": "Огонь"}
    drop_untranslated(vals)
    assert vals == {"en": "Fire", "ru": "Огонь"}


def test_familles_de_types():
    assert is_spell_type("Spell") and is_spell_type("SpellSingleTarget") and is_spell_type("SpellArea")
    assert not is_spell_type("SpellVisScripts") and not is_spell_type("Spellbook")
    assert is_ability_type("AbilityResource") and not is_ability_type("AbilityGraphNode")
    assert is_talent_type("TalentSpell") and is_talent_type("NoTalent")
    assert not is_talent_type("TalentFieldResource") and not is_talent_type("TalentRefSpell")
