"""Objets des fatalités (`tools/fatality_items.py`) et leur fusion dans l'index
(`tools/extract_fatalities.apply_items`)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.allods_packdb import packs_path
from tools.extract_fatalities import apply_items
from tools.fatality_items import _bare, _is_text

CLIENT = Path("/mnt/h/MyGames/AllodsRU")
client = pytest.mark.skipif(not packs_path(CLIENT / "data" / "Packs" / "BaseLocall_x64.pak").is_file(),
                            reason="client 17.0 absent")


def test_bare_text_ignores_quotes_and_spaces():
    assert _bare("Compétence « Carnage »") == "CompétenceCarnage"
    assert _bare("Умение «Расправа»").endswith(_bare("Расправа"))


def test_untranslated_texts_are_not_official():
    assert _is_text("Lunar Speech of the Carnifex", "en")
    assert not _is_text("Абиссальные Речи Палача", "en")
    assert _is_text("Абиссальные Речи Палача", "ru")
    assert not _is_text("  ", "fr")


def test_apply_items_merges_names_icons_and_dates(tmp_path):
    items = tmp_path / "items.json"
    items.write_text(json.dumps({"fatalities": {"16": {
        "type": 16, "name": {"fr": "Rituel lunaire"}, "link": "icon",
        "items": [{"name": {"fr": "Discours lunaire du Carnifex"}, "icon": "Scroll_Fatality_Black_Hole",
                   "resourceIds": [740158371]}],
        "since": {"version": "15.0", "client": "15.0.03.23.2", "previous": "11.0"}}}}), encoding="utf-8")
    manifest = {"fatalities": [{"type": 16, "date": {"value": "2023-08-18", "kind": "attested", "source": "x"}}]}
    entries = [{"type": 16, "items": ["stale"]}, {"type": 1, "since": {"version": "0"}}]
    apply_items(entries, manifest, items)
    assert entries[0]["name"] == {"fr": "Rituel lunaire"}
    assert entries[0]["items"][0]["icon"] == "icons/Scroll_Fatality_Black_Hole.png"
    assert entries[0]["itemLink"] == "icon"
    assert entries[0]["since"]["version"] == "15.0" and entries[0]["since"]["date"]["value"] == "2023-08-18"
    assert "since" not in entries[1]  # données périmées retirées


@client
def test_real_items_teach_their_fatality():
    """Chaîne type → buff → icône → capacité → objet, sur le client 17.0."""
    from tools.fatality_items import Client
    c = Client({"root": str(CLIENT), "pak": "BaseLocall_x64.pak",
                "texts": {"ru": ["Texts_x64.pak", "Bin/pack.rus.loc"], "en": ["Texts_x64.pak", "Bin/pack.eng_eu.loc"]}})
    assert sorted(c.sources) == list(range(1, 27))
    lunar = c.sources[16]
    assert lunar.link == "icon"
    assert [c.text(i, "ItemResource", "en") for i in lunar.items] == ["Lunar Speech of the Carnifex"]
    assert c.text(lunar.buffs[0], "BuffResource", "en") == "Lunar Ritual"
    # Fatalités de classe : icône générique, aucun objet propre.
    assert not c.sources[1].items
    # La 11 (« Расправа ») n'est rattachée que par le nom de la capacité du « Кодекс Палача ».
    assert c.sources[11].link == "name"
    assert "Carnifex Code" in {c.text(i, "ItemResource", "en") for i in c.sources[11].items}
