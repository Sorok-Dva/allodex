import json

import pytest
from PIL import Image

from tools.cut_sprites import build_sheet, cut_sprite, run, validate_box


def test_validate_box_rejects_outside_medals_window():
    with pytest.raises(ValueError):
        validate_box([100, 200, 300, 250])
    with pytest.raises(ValueError):
        validate_box([600, 100, 700, 200])
    validate_box([600, 300, 700, 330])  # ok, ne lève pas


def test_cut_sprite_crops_and_applies_alpha_key():
    img = Image.new("RGB", (40, 40), (10, 200, 10))
    for x in range(10, 30):
        for y in range(10, 30):
            img.putpixel((x, y), (120, 80, 30))
    out = cut_sprite(img, [5, 5, 35, 35], alpha_key={"rgb": [10, 200, 10], "tol": 20})
    assert out.size == (30, 30) and out.mode == "RGBA"
    assert out.getpixel((0, 0))[3] == 0 and out.getpixel((15, 15))[3] == 255


def test_cut_sprite_clear_center_uses_slice():
    img = Image.new("RGB", (40, 40), (120, 80, 30))
    out = cut_sprite(img, [0, 0, 40, 40], clear_center=True, slice_=[6, 6, 6, 6])
    assert out.mode == "RGBA"
    assert out.getpixel((2, 2))[3] == 255  # bord conservé
    assert out.getpixel((20, 20))[3] == 0  # centre vidé
    assert out.getpixel((5, 20))[3] == 255  # dernière colonne du bord gauche
    assert out.getpixel((6, 20))[3] == 0  # première colonne du centre


def test_cut_sprite_repeat_x_erases_a_column_range():
    img = Image.new("RGB", (10, 4), (10, 20, 30))
    for y in range(4):
        img.putpixel((5, y), (200, 0, 0))  # « texte » à effacer
        img.putpixel((9, y), (0, 0, 200))  # colonne source propre
    out = cut_sprite(img, [0, 0, 10, 4], repeat_x=[{"src": 9, "x0": 2, "x1": 8}])
    assert out.getpixel((5, 1))[:3] == (0, 0, 200)
    assert out.getpixel((1, 1))[:3] == (10, 20, 30)


def test_cut_sprite_repeat_y_erases_a_row_range():
    img = Image.new("RGB", (4, 10), (10, 20, 30))
    for x in range(4):
        img.putpixel((x, 2), (200, 0, 0))
        img.putpixel((x, 9), (0, 0, 200))
    out = cut_sprite(img, [0, 0, 4, 10], repeat_y=[{"src": 9, "y0": 0, "y1": 5}])
    assert out.getpixel((1, 2))[:3] == (0, 0, 200)
    assert out.getpixel((1, 7))[:3] == (10, 20, 30)


def test_cut_sprite_alpha_poly_keeps_only_the_polygon():
    img = Image.new("RGB", (10, 10), (200, 100, 50))
    out = cut_sprite(img, [0, 0, 10, 10], alpha_poly=[[[0, 0], [10, 0], [0, 10]]])
    assert out.getpixel((1, 1))[3] == 255  # dans le triangle
    assert out.getpixel((9, 9))[3] == 0  # hors du triangle
    assert out.getpixel((1, 1))[:3] == (200, 100, 50)


def test_run_accepts_a_texture_source_without_window_check(tmp_path):
    tex_dir = tmp_path / "textures" / "Sub"
    tex_dir.mkdir(parents=True)
    Image.new("RGBA", (20, 20), (1, 2, 3, 255)).save(tex_dir / "Box.png")
    ref = tmp_path / "astral.png"
    Image.new("RGB", (1920, 1009), (0, 0, 0)).save(ref)
    manifest = {
        "captures": {"astral": str(ref)},
        "textures_dir": str(tmp_path / "textures"),
        "sprites": {"checkbox-off": {"texture": "Sub/Box.png", "slice": None}},
    }
    mpath = tmp_path / "m.json"
    mpath.write_text(json.dumps(manifest))
    out = tmp_path / "sprites"
    index = run(mpath, out)
    assert index["checkbox-off"] == {"w": 20, "h": 20, "slice": None}
    assert (out / "checkbox-off.png").exists()


def test_run_writes_sprites_and_index(tmp_path):
    ref = tmp_path / "astral.png"
    Image.new("RGB", (1920, 1009), (0, 0, 0)).save(ref)
    manifest = {
        "captures": {"astral": str(ref)},
        "sprites": {"pill-mid": {"capture": "astral", "box": [600, 300, 640, 328], "slice": None}},
    }
    mpath = tmp_path / "m.json"
    mpath.write_text(json.dumps(manifest))
    out = tmp_path / "sprites"
    run(mpath, out)
    assert (out / "pill-mid.png").exists()
    assert json.loads((out.parent / "sprites.json").read_text())["pill-mid"] == {
        "w": 40,
        "h": 28,
        "slice": None,
    }


def test_run_rejects_a_box_outside_the_window(tmp_path):
    ref = tmp_path / "astral.png"
    Image.new("RGB", (1920, 1009), (0, 0, 0)).save(ref)
    manifest = {
        "captures": {"astral": str(ref)},
        "sprites": {"hud": {"capture": "astral", "box": [10, 20, 60, 48], "slice": None}},
    }
    mpath = tmp_path / "m.json"
    mpath.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        run(mpath, tmp_path / "sprites")


def test_build_sheet_writes_a_labelled_contact_sheet(tmp_path):
    ref = tmp_path / "astral.png"
    Image.new("RGB", (1920, 1009), (0, 0, 0)).save(ref)
    manifest = {
        "captures": {"astral": str(ref)},
        "sprites": {
            "pill-mid": {"capture": "astral", "box": [600, 300, 640, 328], "slice": None},
            "rail-top": {"capture": "astral", "box": [600, 300, 608, 311], "slice": None},
        },
    }
    mpath = tmp_path / "m.json"
    mpath.write_text(json.dumps(manifest))
    out = tmp_path / "sprites"
    index = run(mpath, out)
    sheet = build_sheet(index, out, tmp_path / "planche.png")
    assert sheet.exists()
    with Image.open(sheet) as im:
        assert im.width > 40 * 3 and im.height > 28 * 3
