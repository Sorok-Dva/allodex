#!/usr/bin/env python3
"""Extrait les assets nécessaires au site depuis le client Allods Online.

Les textures UI sont stockées en puissances de deux avec un padding
entièrement transparent en bas et à droite ; par défaut, ce padding est
rogné (voir `tools.uitexture.trim_transparent_padding`) et la taille
enregistrée dans le manifest est la taille utile, rognée. `--no-trim`
désactive ce rognage globalement ; la clé `no_trim` du manifest liste les
entrées (chemin de pak complet) à ne jamais rogner.

La clé `color_offsets` du manifest (`{"<entrée de pak>": [dr, dg, db]}`) ajoute
après rognage un décalage constant aux canaux RVB : c'est la correction de
couleur que le jeu applique au rendu, cuite dans le PNG pour que le site n'ait
aucun filtre à appliquer dans le navigateur (spec § 7.1).

Usage : python3 tools/extract_assets.py [--client DIR] [--out public/game] [--force] [--skip-video] [--no-trim]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from urllib.request import urlopen

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.uitexture import decode_uitexture, trim_transparent_padding  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_CLIENT = os.environ.get("ALLODS_CLIENT_DIR", "/mnt/h/MyGames/Allods Online FR (FR)")
TEXTURE_SUFFIX = ".(UITexture).bin"
_DRIVE_LETTER_RE = re.compile(r"^[A-Za-z]:")


def is_safe_entry(name: str) -> bool:
    """Refuse une entrée de pak dont le nom pourrait faire sortir la sortie du dossier cible."""
    if ".." in name:
        return False
    if name.startswith("/") or name.startswith("\\"):
        return False
    if _DRIVE_LETTER_RE.match(name):
        return False
    return True


def select_entries(names: list[str], manifest: dict) -> list[str]:
    prefixes = tuple(manifest.get("texture_prefixes", []))
    explicit = set(manifest.get("texture_files", []))
    selected = []
    for n in names:
        if not (n.endswith(TEXTURE_SUFFIX) and (n.startswith(prefixes) or n in explicit)):
            continue
        if not is_safe_entry(n):
            print(f"AVERTISSEMENT : entrée de pak rejetée (chemin dangereux) : {n}", file=sys.stderr)
            continue
        selected.append(n)
    return selected


def output_path_for(entry: str) -> str:
    return entry[: -len(TEXTURE_SUFFIX)] if entry.endswith(TEXTURE_SUFFIX) else entry


def apply_color_offset(img: Image.Image, offset) -> Image.Image:
    """Ajoute un décalage constant (dr, dg, db) aux canaux RVB, alpha inchangé.

    Le jeu affiche plusieurs textures plus claires que ce que contient le pak (le moteur
    les éclaircit au rendu). Le décalage mesuré sur les captures est **cuit dans le PNG**
    à l'extraction : le site n'applique plus aucun filtre côté navigateur, dont le rendu
    varie entre Chrome logiciel et Chrome GPU (spec § 7.1).
    """
    a = np.asarray(img.convert("RGBA")).astype(np.int16)
    a[:, :, 0:3] = np.clip(a[:, :, 0:3] + np.array(offset, dtype=np.int16), 0, 255)
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def extract_textures(pak: zipfile.ZipFile, manifest: dict, out: Path, force: bool, trim: bool = True) -> dict:
    index: dict[str, dict] = {}
    names = pak.namelist()
    entries = select_entries(names, manifest)
    missing = set(manifest.get("texture_files", [])) - set(names)
    for m in sorted(missing):
        print(f"AVERTISSEMENT : introuvable dans le pak : {m}", file=sys.stderr)
    overrides = {k: tuple(v) for k, v in manifest.get("dims_overrides", {}).items()}
    no_trim = set(manifest.get("no_trim", []))
    color_offsets = {k: tuple(v) for k, v in manifest.get("color_offsets", {}).items()}
    for entry in entries:
        rel = output_path_for(entry)
        target = out / "textures" / f"{rel}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not force:
            with Image.open(target) as im:
                index[rel] = {"w": im.width, "h": im.height}
            continue
        try:
            img, info = decode_uitexture(pak.read(entry), overrides.get(entry))
            if trim and entry not in no_trim:
                img = trim_transparent_padding(img)
            if entry in color_offsets:
                img = apply_color_offset(img, color_offsets[entry])
            img.save(target)
        except Exception as exc:
            print(f"AVERTISSEMENT : décodage impossible pour {entry} : {exc}", file=sys.stderr)
            continue
        index[rel] = {"w": img.width, "h": img.height}
        print(f"texture  {rel}  {img.width}x{img.height} (src {info.width}x{info.height} {info.fourcc})")
    return index


def extract_cursors(pak: zipfile.ZipFile, manifest: dict, out: Path, force: bool) -> None:
    prefix = manifest["cursor_prefix"]
    for entry in pak.namelist():
        if entry.startswith(prefix) and entry.endswith(".cur"):
            target = out / "cursors" / Path(entry).name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and not force:
                continue
            target.write_bytes(pak.read(entry))
            print(f"cursor   {target.name}")


def transcode_videos(pak: zipfile.ZipFile, manifest: dict, out: Path, force: bool) -> None:
    if shutil.which("ffmpeg") is None:
        print("AVERTISSEMENT : ffmpeg absent, vidéos ignorées", file=sys.stderr)
        return
    (out / "video").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for name, entry in manifest["videos"].items():
            webm, mp4 = out / "video" / f"{name}.webm", out / "video" / f"{name}.mp4"
            if webm.exists() and mp4.exists() and not force:
                continue
            src = Path(tmp) / f"{name}.ogv"
            src.write_bytes(pak.read(entry))
            base = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-an"]
            subprocess.run(base + ["-c:v", "libvpx-vp9", "-b:v", "2500k", "-row-mt", "1", str(webm)], check=True)
            subprocess.run(base + ["-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)], check=True)
            print(f"video    {name}.webm / {name}.mp4")


def extract_remote_textures(manifest: dict, out: Path, force: bool = False) -> dict:
    index = {}
    for name, url in manifest.get("remote_textures", {}).items():
        if not is_safe_entry(name):
            raise ValueError(f"Chemin de texture distant invalide : {name}")
        target = out / "textures" / f"{name}.png"
        try:
            if force or not target.is_file():
                with urlopen(url, timeout=30) as response:
                    data = response.read()
                with Image.open(BytesIO(data)) as img:
                    if img.format != "PNG":
                        raise ValueError("l'image distante doit être un PNG")
                    img.verify()
                target.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
                    downloaded = Path(tmp) / "image.png"
                    downloaded.write_bytes(data)
                    downloaded.replace(target)
            with Image.open(target) as img:
                index[name] = {"w": img.width, "h": img.height}
        except (OSError, ValueError) as exc:
            print(f"AVERTISSEMENT : texture distante {name} : {exc}", file=sys.stderr)
    return index


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--client", default=DEFAULT_CLIENT)
    p.add_argument("--out", default=str(HERE.parent / "public" / "game"))
    p.add_argument("--force", action="store_true")
    p.add_argument("--skip-video", action="store_true")
    p.add_argument("--music", action="store_true", help="extrait aussi le catalogue musical FR/RU")
    p.add_argument("--no-trim", action="store_true", help="désactive le rognage du padding transparent")
    args = p.parse_args(argv)

    client, out = Path(args.client), Path(args.out)
    if not client.is_dir():
        print(f"Client introuvable : {client}", file=sys.stderr)
        return 2
    manifest = json.loads((HERE / "assets_manifest.json").read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(client / manifest["packs"]["interface"]) as pak:
        textures = extract_textures(pak, manifest, out, args.force, trim=not args.no_trim)
        extract_cursors(pak, manifest, out, args.force)
    if not args.skip_video:
        with zipfile.ZipFile(client / manifest["packs"]["video"]) as pak:
            transcode_videos(pak, manifest, out, args.force)

    textures.update(extract_remote_textures(manifest, out, args.force))
    (out / "manifest.json").write_text(json.dumps({"textures": textures}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"OK : {len(textures)} textures → {out}")
    if args.music:
        from tools.extract_music import main as extract_music
        return extract_music(["--client", str(client), "--out", str(out / "music")]
                             + (["--force"] if args.force else []))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
