from PIL import Image

from tools.compare_refs import compare


def _checker(path, offset=0):
    img = Image.new("RGB", (60, 40), (20, 30, 40))
    for x in range(60):
        for y in range(40):
            if ((x + offset) // 10 + y // 10) % 2 == 0:
                img.putpixel((x, y), (200, 180, 90))
    img.save(path)
    return path


def test_identical_images_score_zero_and_write_files(tmp_path):
    a = _checker(tmp_path / "site.png")
    b = _checker(tmp_path / "ref.png")
    prefix = tmp_path / "cmp"
    score = compare(a, b, [0, 0, 60, 40], [0, 0, 60, 40], str(prefix))
    assert score == 0.0
    assert (tmp_path / "cmp-montage.png").exists()
    assert (tmp_path / "cmp-diff.png").exists()
    with Image.open(tmp_path / "cmp-montage.png") as m:
        assert m.size == (60 * 2 + 10, 40)


def test_shifted_image_scores_above_zero(tmp_path):
    a = _checker(tmp_path / "site.png", offset=5)
    b = _checker(tmp_path / "ref.png", offset=0)
    score = compare(a, b, [0, 0, 60, 40], [0, 0, 60, 40], str(tmp_path / "cmp"))
    assert score > 0


def test_mismatched_crop_sizes_are_resized(tmp_path):
    a = _checker(tmp_path / "site.png")
    b = _checker(tmp_path / "ref.png")
    score = compare(a, b, [0, 0, 30, 20], [0, 0, 60, 40], str(tmp_path / "cmp"))
    assert score >= 0
    with Image.open(tmp_path / "cmp-diff.png") as d:
        assert d.size == (60, 40)
