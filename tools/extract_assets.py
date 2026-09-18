#!/usr/bin/env python3
"""Extrait les assets nécessaires au site depuis le client Allods Online.

Les textures UI sont stockées en puissances de deux avec un padding
entièrement transparent en bas et à droite ; par défaut, ce padding est
rogné (voir `tools.uitexture.trim_transparent_padding`) et la taille
enregistrée dans le manifest est la taille utile, rognée. `--no-trim`
désactive ce rognage globalement ; la clé `no_trim` du manifest liste les
entrées (chemin de pak complet) à ne jamais rogner.

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
from pathlib import Path

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


def extract_textures(pak: zipfile.ZipFile, manifest: dict, out: Path, force: bool, trim: bool = True) -> dict:
    index: dict[str, dict] = {}
    names = pak.namelist()
    entries = select_entries(names, manifest)
    missing = set(manifest.get("texture_files", [])) - set(names)
    for m in sorted(missing):
        print(f"AVERTISSEMENT : introuvable dans le pak : {m}", file=sys.stderr)
    overrides = {k: tuple(v) for k, v in manifest.get("dims_overrides", {}).items()}
    no_trim = set(manifest.get("no_trim", []))
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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--client", default=DEFAULT_CLIENT)
    p.add_argument("--out", default=str(HERE.parent / "public" / "game"))
    p.add_argument("--force", action="store_true")
    p.add_argument("--skip-video", action="store_true")
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

    (out / "manifest.json").write_text(json.dumps({"textures": textures}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"OK : {len(textures)} textures → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
