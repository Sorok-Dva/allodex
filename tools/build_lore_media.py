#!/usr/bin/env python3
"""Images du matériel communautaire pour la page Lorebook (`/lorebook`).

Source : le corpus de Makar Terentiev (`refs/lorebook`, git-ignoré ; voir `tools/lore_manifest.json`),
repris en entier avec son accord : fichiers image de tous les dossiers (captures, cartes, concepts,
logos, interface) et images incorporées aux documents de travail `.docx` de l'atlas, chacune
rattachée au dernier intertitre numéroté qui la précède (« 2.71 Фабрика Смерти »).

Sorties :

* `public/game/lorebook-media/<id>.webp` (1600 px au plus, 4096 px pour une source de 6000 px ou
  plus : cartes du monde) et `<id>-t.webp` (vignette, 480 px) ;
  `id` = 16 premiers caractères hexadécimaux du SHA-1 des octets source (une image présente à
  plusieurs endroits n'est écrite qu'une fois) ; une image déjà convertie n'est pas relue ;
* `public/game/lore/media.json`, lu par `tools/build_lorebook.py` (le corpus n'est pas requis pour
  reconstruire la page) :
  - `images` : `id → [largeur, hauteur]` de l'image pleine ; `hash` : `id → dhash` (voir `dhash`) ;
  - `files` : `[chemin relatif au corpus, id]` pour chaque fichier image du corpus ;
  - `docs` : `{doc, images: [[id, partie, numéro de section, intertitre russe], …]}` dans l'ordre du
    document (partie : « Раздел N » de `ATLAS ALLODS.docx`, sinon vide) ;
  - `failed` : sources illisibles (chemin, raison).

Formats lus : PNG, JPEG, WebP, GIF (première image), BMP, TIFF, DDS, PSD (image composée), ORA
(`mergedimage.png`, sinon les calques composés), Paint.NET (`.pdn` : la vignette de l'en-tête quand
elle a la taille de l'image).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import sys
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

from PIL import Image, ImageOps

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_OUT = ROOT / "public" / "game" / "lorebook-media"
DEFAULT_MANIFEST = ROOT / "public" / "game" / "lore" / "media.json"

FULL_PX, THUMB_PX = 1600, 480
BIG_PX, BIG_FROM = 4096, 6000    # cartes géantes (jusqu'à 22 000 px) : image pleine plus grande
HUGE_PIXELS = 60_000_000         # au-delà, conversion seule dans le processus principal (mémoire)
FULL_Q, THUMB_Q = 80, 70
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".dds", ".psd", ".ora", ".pdn"}
# intertitre numéroté d'un document de l'atlas : « 1.1.5 Астральная Академия Лиги », « 12 Даян »
HEADING = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,3}){0,4})\.?\s+(\S.{0,110})$")
Image.MAX_IMAGE_PIXELS = None   # cartes géantes du corpus : fichiers locaux de confiance


def default_corpus() -> Path:
    if os.environ.get("ALLODS_LORE_CORPUS"):
        return Path(os.environ["ALLODS_LORE_CORPUS"])
    try:
        return Path(json.loads((HERE / "lore_manifest.json").read_text(encoding="utf-8"))["corpus"])
    except (OSError, KeyError, ValueError):
        return ROOT / "refs" / "lorebook"


def image_id(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:16]


def dhash(im: Image.Image) -> str:
    """Empreinte perceptuelle (différence horizontale 8 × 8, 16 caractères hexadécimaux) : une même
    image recompressée ou redimensionnée (copie d'un .docx) garde presque la même."""
    g = im.convert("L").resize((9, 8), Image.LANCZOS)
    px = list(g.getdata())
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = bits << 1 | (px[y * 9 + x] > px[y * 9 + x + 1])
    return f"{bits:016x}"


def ora_image(data: bytes) -> Image.Image:
    """OpenRaster : `mergedimage.png` s'il existe, sinon les calques de `stack.xml` composés
    (le premier listé est au-dessus ; position, opacité et visibilité respectées)."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if "mergedimage.png" in z.namelist():
            return Image.open(io.BytesIO(z.read("mergedimage.png")))
        stack = z.read("stack.xml").decode("utf-8-sig")
        size = re.search(r'<image[^>]*\bw="(\d+)"[^>]*\bh="(\d+)"', stack)
        canvas = Image.new("RGBA", (int(size.group(1)), int(size.group(2))), (0, 0, 0, 0))
        for layer in reversed(re.findall(r"<layer\b[^>]*>", stack)):
            attr = dict(re.findall(r'([\w-]+)="([^"]*)"', layer))
            if attr.get("visibility") == "hidden" or "src" not in attr:
                continue
            im = Image.open(io.BytesIO(z.read(attr["src"]))).convert("RGBA")
            opacity = float(attr.get("opacity", "1"))
            if opacity < 1:
                im.putalpha(im.getchannel("A").point(lambda a: round(a * opacity)))
            canvas.alpha_composite(im, (int(float(attr.get("x", 0))), int(float(attr.get("y", 0)))))
        canvas.format = "PNG"
        return canvas


def pdn_image(data: bytes) -> Image.Image:
    """Paint.NET : pas de lecteur des calques, mais l'en-tête XML porte une vignette PNG ; elle n'est
    retenue que si elle a la taille de l'image (petites textures d'interface)."""
    if data[:4] != b"PDN3":
        raise ValueError("not a Paint.NET 3+ file")
    header = data[7:7 + int.from_bytes(data[4:7], "little")].decode("utf-8", "replace")
    size = re.search(r'<pdnImage[^>]*\bwidth="(\d+)"[^>]*\bheight="(\d+)"', header)
    thumb = re.search(r'<thumb png="([^"]+)"', header)
    if not (size and thumb):
        raise ValueError("Paint.NET file without thumbnail")
    im = Image.open(io.BytesIO(base64.b64decode(thumb.group(1))))
    if im.size != (int(size.group(1)), int(size.group(2))):
        raise ValueError(f"Paint.NET thumbnail {im.size} smaller than the image")
    return im


def open_image(data: bytes, ext: str) -> Image.Image:
    """Image PIL (non décodée) d'un fichier source."""
    if ext == ".ora":
        return ora_image(data)
    if ext == ".pdn":
        return pdn_image(data)
    return Image.open(io.BytesIO(data))


def target_px(size: tuple[int, int]) -> int:
    return BIG_PX if max(size) >= BIG_FROM else FULL_PX


def available_memory() -> int:
    """Octets de mémoire disponibles (`MemAvailable`), 0 si inconnu."""
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 0


def pixels(data: bytes, ext: str) -> int:
    """Nombre de pixels lu dans l'en-tête (0 si illisible : l'erreur viendra à la conversion)."""
    try:
        w, h = open_image(data, ext).size
        return w * h
    except Exception:  # noqa: BLE001
        return 0


def decode(data: bytes, ext: str) -> tuple[Image.Image, int]:
    """(image décodée, déjà réduite près de sa taille cible (JPEG : décodage réduit ; sinon `reduce`),
    taille cible)."""
    im = open_image(data, ext)
    target = target_px(im.size)
    if im.format == "JPEG":
        im.draft("RGB", (target * 2, target * 2))
    if getattr(im, "is_animated", False) and im.format != "PSD":   # GIF, APNG : première image ; PSD : image composée (les calques sont les images 1 à n)
        im.seek(0)
    im.load()
    factor = max(im.size) // (target * 2)
    if factor >= 2:
        fmt = im.format
        im = im.reduce(factor)
        im.format = fmt
    return im, target


def flatten(im: Image.Image) -> Image.Image:
    im = ImageOps.exif_transpose(im) if im.format == "JPEG" else im
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        if im.getextrema()[3][0] == 255:   # canal alpha plein : inutile
            im = im.convert("RGB")
        return im
    if im.mode in ("I;16", "I;16B", "I", "F"):
        im = ImageOps.autocontrast(im.convert("I").point(lambda v: v / 256).convert("L"))
    return im.convert("RGB")


def convert(job: tuple[bytes, str, str]) -> tuple[str, list[int] | None, str | None]:
    """(id, [l, h] de l'image pleine, erreur) ; écrit les deux WebP dans `out`."""
    data, ext, out = job
    iid = image_id(data)
    try:
        im, target = decode(data, ext)
        full = flatten(im)
        del im
        full.thumbnail((target, target), Image.LANCZOS)
        full.save(Path(out) / f"{iid}.webp", "WEBP", quality=FULL_Q, method=5)
        thumb = full.copy()
        thumb.thumbnail((THUMB_PX, THUMB_PX), Image.LANCZOS)
        thumb.save(Path(out) / f"{iid}-t.webp", "WEBP", quality=THUMB_Q, method=5)
        return iid, list(full.size), None
    except Exception as e:  # noqa: BLE001 — source corrompue ou format inconnu : signalée, pas bloquante
        return iid, None, f"{type(e).__name__}: {e}"


# --- documents .docx -----------------------------------------------------------------------------

def is_title(para: str) -> bool:
    """Intertitre non numéroté (documents des îles astrales) : gras, corps de 16 pt ou plus."""
    sizes = [int(x) for x in re.findall(r'<w:sz w:val="(\d+)"', para)]
    return bool(re.search(r'<w:b(?: w:val="(?:1|true|on)")?/>', para)) and bool(sizes) and min(sizes) >= 32

def docx_images(path: Path):
    """(octets, extension, partie, numéro, intertitre) des images d'un .docx, dans l'ordre du document ;
    partie = « Раздел N » de l'atlas (la numérotation des intertitres repart à 1 à chaque partie)."""
    with zipfile.ZipFile(path) as z:
        rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
        target = {m.group(1): m.group(2) for m in re.finditer(r'<Relationship [^>]*?Id="([^"]+)"[^>]*?Target="([^"]+)"', rels)}
        target.update({m.group(2): m.group(1) for m in re.finditer(r'<Relationship [^>]*?Target="([^"]+)"[^>]*?Id="([^"]+)"', rels)})
        xml = z.read("word/document.xml").decode("utf-8")
        part, number, heading = "", "", ""
        seen = set()
        for p in re.finditer(r"<w:p[ >].*?</w:p>", xml, re.S):
            para = p.group(0)
            text = "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", para))
            text = re.sub(r"\s+", " ", text.replace("&quot;", '"').replace("&amp;", "&")).strip()
            m = HEADING.match(text)
            section = re.fullmatch(r"Раздел\s+(\d+)", text)
            if section:
                part = section.group(1)
            elif m:
                number, heading = m.group(1), m.group(2).strip()
            elif text and len(text) <= 90 and is_title(para):
                number, heading = "", text
            for rid in re.findall(r'r:(?:embed|link|id)="([^"]+)"', para):
                t = target.get(rid, "")
                if not t.startswith("media/"):
                    continue
                name = "word/" + t
                if name in seen:
                    continue
                seen.add(name)
                yield z.read(name), Path(t).suffix.lower(), part, number, heading
        # images du paquet que le texte ne référence pas (en-têtes, illustrations orphelines)
        for info in z.infolist():
            if info.filename.startswith("word/media/") and info.filename not in seen:
                yield z.read(info.filename), Path(info.filename).suffix.lower(), "", "", ""


# --- construction --------------------------------------------------------------------------------

def build(corpus: Path, out: Path, manifest_path: Path, workers: int = 2) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    sizes: dict[str, list[int]] = dict(previous.get("images") or {})
    files: list[list[str]] = []
    docs: list[dict] = []
    failed: list[list[str]] = []
    pending: dict[str, tuple[bytes, str]] = {}   # id → (octets, extension) à convertir
    origin: dict[str, str] = {}

    def want(data: bytes, ext: str, where: str) -> str:
        iid = image_id(data)
        origin.setdefault(iid, where)
        full, thumb = out / f"{iid}.webp", out / f"{iid}-t.webp"
        if iid not in sizes and full.exists() and thumb.exists():   # conversion interrompue : reprise
            with Image.open(full) as im:
                sizes[iid] = list(im.size)
        if iid not in sizes and iid not in pending:
            pending[iid] = (data, ext)
        return iid

    def record(iid: str, size: list[int] | None, err: str | None) -> None:
        if size:
            sizes[iid] = size
        else:
            failed.append([origin.get(iid, iid), err or "?"])

    def run_pool(jobs: dict[str, tuple]) -> None:
        """Conversions en parallèle ; si un processus est tué (mémoire), le reste est repris un par un."""
        remaining = dict(jobs)
        try:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(convert, job): iid for iid, job in remaining.items()}
                for fut in as_completed(futures):
                    record(*fut.result())
                    remaining.pop(futures[fut])
        except BrokenProcessPool:
            for iid, job in list(remaining.items()):
                try:
                    with ProcessPoolExecutor(max_workers=1) as one:
                        record(*one.submit(convert, job).result())
                except BrokenProcessPool:
                    record(iid, None, "conversion process killed (memory)")
                remaining.pop(iid)

    def flush() -> None:
        if not pending:
            return
        small = {iid: (d, e, str(out)) for iid, (d, e) in pending.items() if pixels(d, e) <= HUGE_PIXELS}
        run_pool(small)
        for iid, (d, e) in pending.items():   # cartes géantes : une à la fois, sans processus parallèle
            if iid in small:
                continue
            need = pixels(d, e) * 9   # pic mesuré : ~9 octets par pixel (PNG RGBA de 470 Mpx → 4,2 Go)
            if available_memory() and available_memory() < need:
                record(iid, None, f"not enough free memory ({need >> 20} MiB needed): run again later")
            else:
                record(*convert((d, e, str(out))))
        print(f"  {len(pending)} converted", file=sys.stderr, flush=True)
        pending.clear()

    paths = sorted(p for p in corpus.rglob("*") if p.is_file())
    batch = 0
    for p in paths:
        rel = p.relative_to(corpus).as_posix()
        ext = p.suffix.lower()
        if ext in IMAGE_EXT:
            data = p.read_bytes()
            files.append([rel, want(data, ext, rel)])
            batch += len(data)
        elif ext == ".docx":
            items = []
            for data, iext, part, number, heading in docx_images(p):
                items.append([want(data, iext, f"{rel}#{number}"), part, number, heading])
                batch += len(data)
                if batch > 400_000_000:
                    flush()
                    batch = 0
            docs.append({"doc": rel, "images": items})
        if batch > 400_000_000:   # octets en attente bornés (mémoire de WSL)
            flush()
            batch = 0
    flush()
    ok = set(sizes)
    files = [f for f in files if f[1] in ok]
    for d in docs:
        d["images"] = [x for x in d["images"] if x[0] in ok]
    used = {f[1] for f in files} | {x[0] for d in docs for x in d["images"]}
    for stale in set(sizes) - used:
        del sizes[stale]
    # fichiers convertis qu'aucune source ne référence plus
    for p in out.glob("*.webp"):
        if p.stem.removesuffix("-t") not in used:
            p.unlink()
    hashes = dict(previous.get("hash") or {})
    for iid in sizes:
        if iid not in hashes:
            with Image.open(out / f"{iid}-t.webp") as im:
                hashes[iid] = dhash(im)
    manifest = {"note": "Images of the community material of Makar Terentiev (DarkyAndSparky), used with his "
                        "permission; built by tools/build_lore_media.py",
                "full_px": FULL_PX, "big_px": BIG_PX, "thumb_px": THUMB_PX,
                "images": dict(sorted(sizes.items())), "hash": {k: hashes[k] for k in sorted(sizes)}, "files": files, "docs": docs, "failed": sorted(failed)}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    total = sum(p.stat().st_size for p in out.glob("*.webp"))
    return {"images": len(sizes), "files": len(files), "doc_images": sum(len(d["images"]) for d in docs),
            "failed": len(failed), "bytes": total}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--corpus", type=Path, default=None, help="corpus communautaire (défaut : manifeste ou $ALLODS_LORE_CORPUS)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--workers", type=int, default=2, help="processus de conversion (mémoire : 2 par défaut)")
    args = ap.parse_args(argv)
    corpus = args.corpus or default_corpus()
    if not corpus.exists():
        print(f"corpus introuvable : {corpus}", file=sys.stderr)
        return 1
    print(json.dumps(build(corpus, args.out, args.manifest, args.workers), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
