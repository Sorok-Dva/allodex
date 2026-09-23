"""Vérification des icônes de talents : arbre serveur 7.0 et accord d'une version à l'autre."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import extract_talents as et
from tools.talent_icons_check import DEFAULT_SERVER, ServerIcons, check_cross, check_server

DATA = Path(__file__).resolve().parents[2] / "public" / "game" / "talents"


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_suit_prototype_image_texture(tmp_path):
    write(tmp_path, "M/S/Spell01.xdb", '<x><Header><Prototype href="/M/S/Spell.xdb" /></Header></x>')
    write(tmp_path, "M/S/Spell.xdb", '<x><image href="/I/Fire.(UISingleTexture).xdb" /></x>')
    write(tmp_path, "I/Fire.(UISingleTexture).xdb", '<U><singleTexture href="/I/Fire.(UITexture).xdb#xpointer(/client.Widgets.UITexture)"/></U>')
    write(tmp_path, "I/Fire.(UITexture).xdb", '<U><binaryFile href="/I/Fire.(UITexture).bin"/></U>')
    assert ServerIcons(tmp_path).icon_bin("M/S/Spell01.xdb") == "I/Fire.(UITexture).bin"
    assert ServerIcons(tmp_path).icon_bin("M/absent.xdb") is None


def test_accord_entre_versions(tmp_path):
    def cls(version, talents):
        write(tmp_path, f"{version}/mage.json", json.dumps({"talents": talents}))
    cls("a", {"t1": {"ref": "#1", "name": {"fr": "Feu"}, "iconSrc": "I/Fire.(UITexture).bin"},
              "t2": {"ref": "#2", "name": {"fr": "Glace"}, "iconSrc": "I/Ice.(UITexture).bin"}})
    cls("b", {"t1": {"ref": "#9", "name": {"fr": "Feu"}, "iconSrc": "Other/fire.(UITexture).bin"},
              "t2": {"ref": "#8", "name": {"fr": "Glace"}, "iconSrc": "I/Shock.(UITexture).bin"}})
    ok, total, bad = check_cross(tmp_path, "a", "b", "fr")
    assert (ok, total) == (1, 2)
    assert bad[0][1] == "Glace"


def test_cle_d_icone_inclut_le_chemin_du_pak(tmp_path, monkeypatch):
    """Deux clients ont des paks de même nom (`Interface.Mini.pak`) au contenu différent : la même
    (nom de pak, rang) ne doit pas reprendre l'icône de l'autre client."""
    from PIL import Image
    images = {"/c15/Interface.Mini.pak": (255, 0, 0, 255), "/c17/Interface.Mini.pak": (0, 0, 255, 255)}
    monkeypatch.setattr(et, "decode_uitexture", lambda data, hint=None: (Image.new("RGBA", (8, 8), images[data.decode()]), None))
    sink = et.IconSink(tmp_path)
    a = sink.add("/c15/Interface.Mini.pak#12", lambda: b"/c15/Interface.Mini.pak")
    b = sink.add("/c17/Interface.Mini.pak#12", lambda: b"/c17/Interface.Mini.pak")
    assert a != b


SERVER = Path(DEFAULT_SERVER)


@pytest.mark.skipif(not (DATA / "7.0").exists() or not SERVER.exists(), reason="données 7.0 ou arbre serveur absents")
def test_icones_7_0_conformes_a_l_arbre_serveur():
    ok, total, bad = check_server(DATA, "7.0", ServerIcons(SERVER))
    assert total > 300
    assert ok / total >= 0.99, bad[:5]


@pytest.mark.skipif(not (DATA / "17.0").exists(), reason="données absentes")
@pytest.mark.parametrize("a,b,lang,floor", [("15.0", "16.0", "fr", 0.99), ("8.0", "9.0", "fr", 0.95), ("7.0", "17.0", "en", 0.75)])
def test_icones_stables_d_une_version_a_l_autre(a, b, lang, floor):
    ok, total, bad = check_cross(DATA, a, b, lang)
    if total == 0:
        pytest.skip("aucun talent de même nom")
    assert ok / total >= floor, bad[:5]
