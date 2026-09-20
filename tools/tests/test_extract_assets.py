import io
import zipfile

from PIL import Image

from tools.extract_assets import apply_color_offset, select_entries, output_path_for, extract_textures
from tools.uitexture import DecodeInfo

MANIFEST = {
    "texture_prefixes": ["Interface/Ingame/Medals/Textures/"],
    "texture_files": ["Interface/Icons/Misc/Event/GoldMedal.(UITexture).bin"],
}


def test_select_entries_keeps_prefix_matches_and_explicit_files():
    names = [
        "Interface/Ingame/Medals/Textures/MedalFrame.(UITexture).bin",
        "Interface/Ingame/Medals/Scripts/ClassMain.luac",
        "Interface/Icons/Misc/Event/GoldMedal.(UITexture).bin",
        "Interface/Icons/Misc/Event/SilverMedal.(UITexture).bin",
    ]
    assert select_entries(names, MANIFEST) == [
        "Interface/Ingame/Medals/Textures/MedalFrame.(UITexture).bin",
        "Interface/Icons/Misc/Event/GoldMedal.(UITexture).bin",
    ]


def test_output_path_strips_type_suffix():
    assert output_path_for("Interface/Ingame/Medals/Textures/Numbers/Num1.(UITexture).bin") == \
        "Interface/Ingame/Medals/Textures/Numbers/Num1"


def test_select_entries_rejects_path_traversal():
    # Même explicitement listée, une entrée à chemin dangereux doit être rejetée :
    # `output_path_for` la transformerait en chemin de sortie hors du dossier cible.
    manifest = {
        "texture_prefixes": [],
        "texture_files": ["../x.(UITexture).bin"],
    }
    assert select_entries(["../x.(UITexture).bin"], manifest) == []


def _make_pak() -> zipfile.ZipFile:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Interface/Ingame/Medals/Textures/X.(UITexture).bin", b"\0")
    buf.seek(0)
    return zipfile.ZipFile(buf)


def _make_pak_two_entries() -> zipfile.ZipFile:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Interface/Ingame/Medals/Textures/Bad.(UITexture).bin", b"\0")
        zf.writestr("Interface/Ingame/Medals/Textures/Good.(UITexture).bin", b"\0")
    buf.seek(0)
    return zipfile.ZipFile(buf)


def _img_with_padding() -> Image.Image:
    img = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    for y in range(2):
        for x in range(3):
            img.putpixel((x, y), (255, 0, 0, 255))
    return img


TRIM_MANIFEST = {
    "texture_prefixes": ["Interface/Ingame/Medals/Textures/"],
    "texture_files": [],
    "no_trim": [],
}


def test_extract_textures_trims_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "tools.extract_assets.decode_uitexture",
        lambda data, hint=None: (_img_with_padding(), DecodeInfo(8, 8, "DXT5")),
    )
    with _make_pak() as pak:
        index = extract_textures(pak, TRIM_MANIFEST, tmp_path, force=True)
    assert index["Interface/Ingame/Medals/Textures/X"] == {"w": 3, "h": 2}
    with Image.open(tmp_path / "textures" / "Interface/Ingame/Medals/Textures/X.png") as im:
        assert im.size == (3, 2)


def test_extract_textures_trim_false_keeps_full_size(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "tools.extract_assets.decode_uitexture",
        lambda data, hint=None: (_img_with_padding(), DecodeInfo(8, 8, "DXT5")),
    )
    with _make_pak() as pak:
        index = extract_textures(pak, TRIM_MANIFEST, tmp_path, force=True, trim=False)
    assert index["Interface/Ingame/Medals/Textures/X"] == {"w": 8, "h": 8}


def test_extract_textures_respects_no_trim_list(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "tools.extract_assets.decode_uitexture",
        lambda data, hint=None: (_img_with_padding(), DecodeInfo(8, 8, "DXT5")),
    )
    manifest = dict(TRIM_MANIFEST, no_trim=["Interface/Ingame/Medals/Textures/X.(UITexture).bin"])
    with _make_pak() as pak:
        index = extract_textures(pak, manifest, tmp_path, force=True)
    assert index["Interface/Ingame/Medals/Textures/X"] == {"w": 8, "h": 8}


def test_extract_textures_skips_bad_entry_and_keeps_going(monkeypatch, tmp_path):
    # L'ordre des entrées suit celui d'écriture dans le pak (Bad puis Good) :
    # le premier appel à decode_uitexture échoue, le second réussit.
    calls = {"n": 0}

    def fake_decode(data, hint=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("texture corrompue")
        return _img_with_padding(), DecodeInfo(8, 8, "DXT5")

    monkeypatch.setattr("tools.extract_assets.decode_uitexture", fake_decode)
    with _make_pak_two_entries() as pak:
        index = extract_textures(pak, TRIM_MANIFEST, tmp_path, force=True)
    assert list(index.keys()) == ["Interface/Ingame/Medals/Textures/Good"]
    assert not (tmp_path / "textures" / "Interface/Ingame/Medals/Textures/Bad.png").exists()


def test_apply_color_offset_adds_and_clamps_without_touching_alpha():
    # Les décalages de couleur du jeu (ex. FrameNavigation +15/+14/+9) sont cuits dans le
    # PNG : plus aucun filtre côté navigateur (spec § 7.1).
    img = Image.new("RGBA", (3, 1))
    img.putpixel((0, 0), (10, 20, 250, 128))
    img.putpixel((1, 0), (0, 0, 0, 0))
    img.putpixel((2, 0), (255, 255, 255, 255))
    out = apply_color_offset(img, (15, 14, 9))
    assert out.getpixel((0, 0)) == (25, 34, 255, 128)  # bleu saturé à 255
    assert out.getpixel((1, 0)) == (15, 14, 9, 0)  # alpha intact
    assert out.getpixel((2, 0)) == (255, 255, 255, 255)


def test_apply_color_offset_clamps_at_zero():
    img = Image.new("RGBA", (1, 1), (10, 5, 200, 255))
    out = apply_color_offset(img, (-30, -4, -9))
    assert out.getpixel((0, 0)) == (0, 1, 191, 255)


def test_extract_textures_applies_color_offset_after_trim(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "tools.extract_assets.decode_uitexture",
        lambda data, hint=None: (_img_with_padding(), DecodeInfo(8, 8, "DXT5")),
    )
    manifest = dict(
        TRIM_MANIFEST,
        color_offsets={"Interface/Ingame/Medals/Textures/X.(UITexture).bin": [8, 12, 18]},
    )
    with _make_pak() as pak:
        index = extract_textures(pak, manifest, tmp_path, force=True)
    assert index["Interface/Ingame/Medals/Textures/X"] == {"w": 3, "h": 2}  # rognage conservé
    with Image.open(tmp_path / "textures" / "Interface/Ingame/Medals/Textures/X.png") as im:
        assert im.convert("RGBA").getpixel((0, 0)) == (255, 12, 18, 255)
def test_remote_texture_is_cached_without_changing_original_bytes(tmp_path, monkeypatch):
    from io import BytesIO
    from PIL import Image
    from tools import extract_assets as assets
    buffer = BytesIO()
    Image.new("RGBA", (64, 64), (50, 60, 70, 120)).save(buffer, format="PNG")
    data = buffer.getvalue()
    calls = []
    def fetch(url, timeout):
        calls.append(url)
        return BytesIO(data)
    monkeypatch.setattr(assets, "urlopen", fetch)
    manifest = {"remote_textures": {"Official/media_player": "https://allods.ru/images/articles/media_player.png"}}
    assert assets.extract_remote_textures(manifest, tmp_path) == {"Official/media_player": {"w": 64, "h": 64}}
    assert (tmp_path / "textures/Official/media_player.png").read_bytes() == data
    assets.extract_remote_textures(manifest, tmp_path)
    assert len(calls) == 1
    assets.extract_remote_textures(manifest, tmp_path, force=True)
    assert len(calls) == 2
