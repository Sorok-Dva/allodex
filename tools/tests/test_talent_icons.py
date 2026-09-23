"""Icônes de talents : zone utile des `UITexture` (icônes sans fond de 39 × 39 dans 64 × 64)."""
from __future__ import annotations

import struct
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from tools import extract_talents as et

ICONS = Path(__file__).resolve().parents[2] / "public" / "game" / "talents" / "icons"


def fake_texture(words: list[int]):
    raw = b"".join(struct.pack("<I", w) for w in words)
    pb = SimpleNamespace(u32=lambda a: struct.unpack_from("<I", raw, a)[0])
    return SimpleNamespace(pb=pb, obj_end=lambda a: len(raw))


def test_zone_utile_v1_recente():
    # 9.0 : FFFFFFFF, dim, FFFFFFFF, 1, n, realH, realW, 2, dim
    ex = fake_texture([0] * 15 + [0xFFFFFFFF, 64, 0xFFFFFFFF, 1, 3, 39, 32, 2, 64, 257, 0])
    assert et.Extractor.texture_dims_v1(ex, 0) == {"realH": 39, "realW": 32}


def test_zone_utile_v1_ancienne():
    # 2.0 : dim, 2, empreinte, realW, realH, 1, FFFFFFFF, dim
    ex = fake_texture([0, 1, 0, 0, 1, 0, 0, 64, 2, 12345, 39, 32, 1, 0xFFFFFFFF, 64, 0, 0, 63, 113, 0])
    assert et.Extractor.texture_dims_v1(ex, 0) == {"realH": 32, "realW": 39}


def test_zone_utile_absente_ou_incoherente():
    assert et.Extractor.texture_dims_v1(fake_texture([0] * 20), 0) is None
    ex = fake_texture([0] * 15 + [0xFFFFFFFF, 64, 0xFFFFFFFF, 1, 3, 128, 128, 2, 64, 0, 0])
    assert et.Extractor.texture_dims_v1(ex, 0) is None


def test_icone_recadree_sur_la_zone_utile(tmp_path, monkeypatch):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    img.paste((200, 50, 50, 255), (0, 0, 39, 39))
    monkeypatch.setattr(et, "decode_uitexture", lambda data, hint=None: (img, None))
    sink = et.IconSink(tmp_path)
    name = sink.add("x", lambda: b"data", {"w": 64, "h": 64, "realW": 39, "realH": 39})
    out = Image.open(tmp_path / name)
    assert out.size == (39, 39)
    # sans dimensions : texture entière (comportement inchangé)
    assert Image.open(tmp_path / sink.add("y", lambda: b"data")).size == (64, 64)


@pytest.mark.skipif(not ICONS.exists(), reason="icônes non extraites")
def test_aucune_icone_tassee_en_haut_a_gauche():
    """Après recadrage, plus aucune icône n'a son dessin confiné dans le coin haut-gauche."""
    bad = []
    for f in sorted(ICONS.glob("*.png")):
        im = Image.open(f).convert("RGBA")
        bb = im.getchannel("A").point(lambda a: 255 if a > 16 else 0).getbbox()
        if bb and bb[2] <= 0.8 * im.width and bb[3] <= 0.8 * im.height:
            bad.append((f.name, im.size, bb))
    assert bad == []
