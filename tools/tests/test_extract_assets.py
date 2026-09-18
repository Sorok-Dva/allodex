import io
import zipfile

from PIL import Image

from tools.extract_assets import select_entries, output_path_for, extract_textures
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
