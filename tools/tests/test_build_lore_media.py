import io
import json
import zipfile

from PIL import Image

from tools import build_lore_media as media


def png(color, size=(40, 30), mode="RGB"):
    b = io.BytesIO()
    Image.new(mode, size, color).save(b, "PNG")
    return b.getvalue()


def para(text="", embed=None, big=False):
    rpr = '<w:rPr><w:b w:val="1"/><w:sz w:val="36"/></w:rPr>' if big else ""
    run = f"<w:r>{rpr}<w:t>{text}</w:t></w:r>" if text else ""
    pic = f'<w:r><w:drawing><a:blip r:embed="{embed}"/></w:drawing></w:r>' if embed else ""
    return f"<w:p>{run}{pic}</w:p>"


def make_docx(path, body, media_files):
    rels = "".join(f'<Relationship Id="{rid}" Type="image" Target="media/{name}"/>' for rid, name in media_files)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/_rels/document.xml.rels", f"<Relationships>{rels}</Relationships>")
        z.writestr("word/document.xml", f"<w:document><w:body>{body}</w:body></w:document>")
        for i, (_, name) in enumerate(media_files):
            z.writestr(f"word/media/{name}", png((i * 60, 0, 0)))


def test_docx_images_follow_parts_numbered_and_bold_headings(tmp_path):
    doc = tmp_path / "a.docx"
    body = (para("Раздел 2") + para("1.1 Кания") + para(embed="r1") + para("Астральный Шип", big=True)
            + para(embed="r2") + para(embed="r1"))
    make_docx(doc, body, [("r1", "image1.png"), ("r2", "image2.png"), ("r3", "orphan.png")])
    got = [(ext, part, num, h) for _, ext, part, num, h in media.docx_images(doc)]
    assert got == [(".png", "2", "1.1", "Кания"), (".png", "2", "", "Астральный Шип"), (".png", "", "", "")]


def test_build_converts_dedupes_and_resumes(tmp_path):
    corpus, out, manifest = tmp_path / "corpus", tmp_path / "media", tmp_path / "media.json"
    (corpus / "Кания").mkdir(parents=True)
    red = png((255, 0, 0), (3000, 1000))
    (corpus / "Кания" / "1.png").write_bytes(red)
    (corpus / "Кания" / "copy.png").write_bytes(red)
    (corpus / "alpha.png").write_bytes(png((0, 0, 255, 128), mode="RGBA"))
    (corpus / "broken.jpg").write_bytes(b"not an image")
    (corpus / "notes.txt").write_text("texte")
    report = media.build(corpus, out, manifest, workers=1)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    rid = media.image_id(red)
    assert report["images"] == 2 and report["failed"] == 1 and data["failed"][0][0] == "broken.jpg"
    assert data["images"][rid] == [1600, 533]
    assert [f for f in data["files"] if f[1] == rid] == [["Кания/1.png", rid], ["Кания/copy.png", rid]]
    with Image.open(out / f"{rid}-t.webp") as im:
        assert im.size == (480, 160)
    alpha = next(f[1] for f in data["files"] if f[0] == "alpha.png")
    with Image.open(out / f"{alpha}.webp") as im:
        assert im.mode == "RGBA"
    # reprise : fichiers présents, manifeste perdu → pas de reconversion, tailles relues
    manifest.unlink()
    (out / f"{rid}.webp").touch()
    stamp = (out / f"{rid}.webp").stat().st_mtime_ns
    media.build(corpus, out, manifest, workers=1)
    assert json.loads(manifest.read_text(encoding="utf-8"))["images"][rid] == [1600, 533]
    assert (out / f"{rid}.webp").stat().st_mtime_ns == stamp
    # source retirée : ses fichiers convertis aussi
    (corpus / "alpha.png").unlink()
    media.build(corpus, out, manifest, workers=1)
    assert not (out / f"{alpha}.webp").exists()


def test_giant_sources_get_a_larger_full_image():
    assert media.target_px((22429, 20997)) == media.BIG_PX and media.target_px((1920, 1080)) == media.FULL_PX
