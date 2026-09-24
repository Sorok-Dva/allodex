"""Tests de l'extraction des auras (`tools/extract_auras.py`) : textes et références en ligne,
obtention, choix du buff, version d'apparition, chronologie ; et, sur les vrais clients (sautés
s'ils manquent), la garde-robe du 17.0 et l'exemple de l'infobulle du client FR."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import extract_auras as ea
from tools.allods_packdb import packs_path

MANIFEST = Path(__file__).resolve().parents[1] / "auras_manifest.json"
EXPORT = Path(__file__).resolve().parents[2] / "public" / "game" / "auras" / "auras.json"


def test_href_index_is_little_endian_hex():
    assert ea.href_index("2689010000000000") == 0x018926
    assert ea.href_index("5dc1000000000000") == 0xC15D


def test_resolve_refs_replaces_texts_and_objects():
    texts = {0x018926: "Larmes du <t href=\"0200000000000000\"/>", 2: "jarl"}
    out = ea.resolve_refs('<html><t href="2689010000000000"/> — <o id="740212447"/></html>',
                          texts.get, {740212447: "Emblèmes"}.get)
    assert out == "<html>Larmes du jarl — Emblèmes</html>"


def test_plain_turns_tooltip_markup_into_lines():
    html = "<html>Vous confère l'effet Rune.<br/>\r\n<tip_grey>Utilisez à nouveau‎ pour annuler.</tip_grey></html>"
    assert ea.plain(html) == "Vous confère l'effet Rune.\nUtilisez à nouveau pour annuler."


def test_obtain_prefers_the_sources_lines():
    unlock = ("<html>Une aura guidée.<br/>\r\n<tip_grey>Sources :</tip_grey><br/>\r\n"
              "<html>- s'achète avec des devises Emblèmes auprès de Gerasim Rivin dans la capitale de faction.</html></html>")
    text, origin = ea.obtain_text(unlock, [])
    assert origin == "unlock"
    assert text == "s'achète avec des devises Emblèmes auprès de Gerasim Rivin dans la capitale de faction."


def test_obtain_skips_generic_unlock_and_repeated_name():
    item = "<html>Vous confère l'effet Aura.<br/>\r\nReçu en récompense durant l'événement Trésors de Marquis.</html>"
    assert ea.obtain_text("<html>Accordé par l'Aura de Marquis.</html>", [item]) == \
        ("Reçu en récompense durant l'événement Trésors de Marquis.", "item")
    assert ea.obtain_text("Rune du Seigneur des abysses.", [], ("Rune du Seigneur des abysses",)) == (None, None)
    # Un renvoi à l'objet qui dit où l'acheter est gardé.
    text, _ = ea.obtain_text("Conféré par l'Aura qui s'achète avec des larmes auprès de Reine-des-prés sur Éden.", [])
    assert text.startswith("Conféré par")


def test_obtain_ignores_effect_lines_of_the_item():
    item = "Сторонники Детей получают дополнительные эффекты, если аура активна:\n+50% длительность эффектов, полученных после"
    assert ea.obtain_text(None, [item]) == (None, None)


def test_pick_buff_keeps_the_same_name_even_without_script():
    buffs = [(1, "Аура Покровителя", False), (2, "Уро-Борос слышит", True)]
    assert ea.pick_buff("Аура Покровителя", buffs) == 1
    assert ea.pick_buff("Аура Воителя", [(3, "Клич Воителя", True)]) == 3
    assert ea.pick_buff("X", [(4, None, False), (5, None, True)]) == 5
    assert ea.pick_buff("X", []) is None


def test_first_version_reports_previous_and_skips_unreadable_clients():
    rows = [("3.0", "3.0.02.19", False), ("4.0", None, None), ("7.0", "7.0.00.00", False), ("8.0", "8.0.02.61.1", True)]
    assert ea.first_version(rows) == {"version": "8.0", "client": "8.0.02.61.1", "previous": "7.0"}
    assert ea.first_version([("3.0", None, True)]) == {"version": "3.0"}
    assert ea.first_version([("3.0", None, False)]) is None


def test_aura_timeline_keeps_attached_effects_without_end():
    script = {"type": "CreatureEffectsAction", "effects": [
        {"visObject": 10, "locator": "Global", "scale": 1.0, "fadeIn": 0.15, "fadeOut": 0.0, "offset": [0.0, 0.0, 0.0]},
        {"visObject": 99, "locator": "Slot_Global", "scale": 1.25, "fadeIn": 0.0, "fadeOut": 0.0, "offset": [0.0, 0.0, 0.0]}]}
    tl = ea.aura_timeline(script, {10: "Aura_Provider_2024_01"}, {})
    assert tl["attached"] == [{"t": 0.0, "vot": "Aura_Provider_2024_01", "locator": "Global", "scale": 1.0, "fadeIn": 0.15}]
    assert tl["spawns"] == []


def test_is_official_rejects_cyrillic_translations():
    assert ea.is_official("Rune", "fr")
    assert not ea.is_official("Руна", "fr")
    assert ea.is_official("Руна", "ru")
    assert not ea.is_official("  ", "ru")


# --- vrais clients -------------------------------------------------------------------------------

def _clients_present() -> bool:
    if not MANIFEST.is_file():
        return False
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return all(packs_path(Path(m[k]["root"]) / "data" / "Packs" / m[k]["pak"]).is_file() for k in ("latest", "fr"))


clients = pytest.mark.skipif(not _clients_present(), reason="client RU 17 ou FR 16 absent")


@clients
def test_wardrobe_auras_of_the_latest_client():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    latest = ea.Client(m["latest"])
    spells = ea.aura_spells(latest)
    assert len(spells) == 55
    names = [latest.text_ref(s, ea.SPELL_NAME, "ru") for s in spells]
    assert names[0] == "Аура Покровителя" and "Пурпурная руна Чемпиона" in names


@pytest.mark.skipif(not EXPORT.is_file(), reason="auras.json non extrait")
def test_export_has_the_tooltip_example_of_the_fr_client():
    data = json.loads(EXPORT.read_text(encoding="utf-8"))
    rune = next(a for a in data["auras"] if a["name"].get("fr") == "Rune de l'esclavagiste")
    assert rune["description"]["fr"] == "Vous confère l'effet Rune de l'Esclavagiste.\nUtilisez à nouveau pour annuler l'effet."
    assert rune["obtain"]["fr"] == "Obtenu pour avoir participé aux épreuves de l'Arène des héros."
    assert rune["visual"] and rune["timeline"]["attached"][0]["locator"] == "Global"
    hickut = next(a for a in data["auras"] if a["id"] == "a740215542")
    assert "Gerasim Rivin" in hickut["obtain"]["fr"]
