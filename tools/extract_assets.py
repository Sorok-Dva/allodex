#!/usr/bin/env python3
"""Extrait les assets nécessaires au site depuis le client Allods Online.

Usage : python3 tools/extract_assets.py [--client DIR] [--out public/game] [--force] [--skip-video]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.uitexture import decode_uitexture  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_CLIENT = os.environ.get("ALLODS_CLIENT_DIR", "/mnt/h/MyGames/Allods Online FR (FR)")
TEXTURE_SUFFIX = ".(UITexture).bin"


def select_entries(names: list[str], manifest: dict) -> list[str]:
    prefixes = tuple(manifest.get("texture_prefixes", []))
    explicit = set(manifest.get("texture_files", []))
    return [n for n in names if n.endswith(TEXTURE_SUFFIX) and (n.startswith(prefixes) or n in explicit)]


def output_path_for(entry: str) -> str:
    return entry[: -len(TEXTURE_SUFFIX)] if entry.endswith(TEXTURE_SUFFIX) else entry


def extract_textures(pak: zipfile.ZipFile, manifest: dict, out: Path, force: bool) -> dict:
    index: dict[str, dict] = {}
    names = pak.namelist()
    entries = select_entries(names, manifest)
    missing = set(manifest.get("texture_files", [])) - set(names)
    for m in sorted(missing):
        print(f"AVERTISSEMENT : introuvable dans le pak : {m}", file=sys.stderr)
    overrides = {k: tuple(v) for k, v in manifest.get("dims_overrides", {}).items()}
    for entry in entries:
        rel = output_path_for(entry)
        target = out / "textures" / f"{rel}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not force:
            from PIL import Image
            with Image.open(target) as im:
                index[rel] = {"w": im.width, "h": im.height}
            continue
        img, info = decode_uitexture(pak.read(entry), overrides.get(entry))
        img.save(target)
        index[rel] = {"w": info.width, "h": info.height}
        print(f"texture  {rel}  {info.width}x{info.height} {info.fourcc}")
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
    args = p.parse_args(argv)

    client, out = Path(args.client), Path(args.out)
    if not client.is_dir():
        print(f"Client introuvable : {client}", file=sys.stderr)
        return 2
    manifest = json.loads((HERE / "assets_manifest.json").read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(client / manifest["packs"]["interface"]) as pak:
        textures = extract_textures(pak, manifest, out, args.force)
        extract_cursors(pak, manifest, out, args.force)
    if not args.skip_video:
        with zipfile.ZipFile(client / manifest["packs"]["video"]) as pak:
            transcode_videos(pak, manifest, out, args.force)

    (out / "manifest.json").write_text(json.dumps({"textures": textures}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"OK : {len(textures)} textures → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
