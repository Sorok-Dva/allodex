#!/usr/bin/env python3
"""Extrait la musique du menu et les sons d'interface depuis le client Allods Online.

Les banques audio du client sont des FSB (FMOD Sample Bank, extension `.fsb`,
stockés tels quels dans les paks) ou des BSB (`.bsb`, un FSB compressé en zlib :
on décompresse puis on repère le magic `FSB5`/`FSB4`/... à l'intérieur). Chaque
banque contient plusieurs « subsongs » ; `tools/audio_manifest.json` désigne pour
chaque piste voulue le pak, l'entrée dans le pak et le numéro de subsong.

Ce script décode le subsong désigné avec vgmstream-cli vers un WAV temporaire,
puis encode ce WAV en OGG (qualité ~5 pour la musique, plus compressé pour les
sons courts) et en MP3 (repli Safari, qui ne lit pas l'OGG/Vorbis). Il écrit
`public/game/audio/<nom>.{ogg,mp3}` et l'index `public/game/audio.json`
(`{"<nom>": {"duration": float, "loop": bool}}`).

Idempotent : une piste dont les deux fichiers de sortie existent déjà est
ignorée (son entrée dans l'index est conservée telle quelle), sauf `--force`.
Une entrée introuvable (pak absent, chemin absent du pak, subsong hors plage,
décodage vgmstream en échec) déclenche un avertissement sur stderr et n'arrête
pas l'extraction des autres pistes.

Usage : python3 tools/extract_audio.py [--client DIR] [--out public/game/audio]
                                       [--manifest tools/audio_manifest.json]
                                       [--vgmstream PATH] [--force]
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
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_CLIENT = os.environ.get("ALLODS_CLIENT_DIR", "/mnt/h/MyGames/Allods Online FR (FR)")
DEFAULT_MANIFEST = HERE / "audio_manifest.json"
DEFAULT_VGMSTREAM = (
    HERE.parent.parent
    / "allods-texts-packer"
    / "voices"
    / "tools"
    / "vgmstream"
    / "vgmstream-cli"
)

FSB_MAGICS = (b"FSB5", b"FSB4", b"FSB3", b"FSB2", b"FSB1")
_DRIVE_LETTER_RE = re.compile(r"^[A-Za-z]:")

# Réglages d'encodage : musique en qualité confortable, sons d'interface en
# léger (ce sont des clips de moins de 3 secondes, le poids importe peu mais
# autant rester cohérent).
OGG_QUALITY = {"tracks": "5", "sfx": "2"}
MP3_BITRATE = {"tracks": "192k", "sfx": "96k"}


def is_safe_entry(name: str) -> bool:
    """Refuse une entrée de pak dont le nom pourrait faire sortir un chemin du dossier cible."""
    if ".." in name:
        return False
    if name.startswith("/") or name.startswith("\\"):
        return False
    if _DRIVE_LETTER_RE.match(name):
        return False
    return True


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_entries(manifest: dict):
    """Aplatit `tracks`/`sfx` du manifeste en tuples (categorie, nom, spec)."""
    for name, spec in manifest.get("tracks", {}).items():
        yield "tracks", name, spec
    for name, spec in manifest.get("sfx", {}).items():
        yield "sfx", name, spec


def resolve_pak_path(client: Path, manifest: dict, pak_ref: str) -> Path:
    """`pak_ref` est soit une clé de `manifest["packs"]`, soit un chemin relatif direct."""
    rel = manifest.get("packs", {}).get(pak_ref, pak_ref)
    return client / rel


def extract_pak_entry_bytes(pak_path: Path, entry: str) -> bytes | None:
    if not pak_path.exists() or not is_safe_entry(entry):
        return None
    try:
        with zipfile.ZipFile(pak_path) as zf:
            if entry not in zf.namelist():
                return None
            return zf.read(entry)
    except (zipfile.BadZipFile, OSError):
        return None


def fsb_payload_from_bytes(data: bytes, entry_name: str) -> bytes | None:
    """Renvoie les octets FSB bruts : directs pour `.fsb`, décompressés (zlib) pour `.bsb`/`.bev`."""
    ext = Path(entry_name).suffix.lower()
    if ext == ".fsb":
        return data if data[:4] in FSB_MAGICS else None
    if ext in (".bsb", ".bev"):
        try:
            dec = zlib.decompress(data)
        except zlib.error:
            return None
        for magic in FSB_MAGICS:
            idx = dec.find(magic)
            if idx != -1:
                return dec[idx:]
        return None
    return None


def fsb_subsong_count(payload: bytes) -> int | None:
    if len(payload) < 12 or payload[:4] not in FSB_MAGICS:
        return None
    return int.from_bytes(payload[8:12], "little")


def run_vgmstream(vgmstream: Path, fsb_path: Path, subsong: int, out_wav: Path) -> None:
    cmd = [str(vgmstream), "-i", "-s", str(subsong), "-o", str(out_wav), str(fsb_path)]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode != 0 or not out_wav.exists():
        stderr = result.stderr.decode(errors="replace").strip()[:400]
        raise RuntimeError(f"vgmstream a échoué (code {result.returncode}) : {stderr}")


def _run_ffmpeg(args: list[str]) -> None:
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()[:400]
        raise RuntimeError(f"ffmpeg a échoué (code {result.returncode}) : {stderr}")


def encode_outputs(wav_path: Path, out_base: Path, category: str) -> None:
    ogg_q = OGG_QUALITY[category]
    mp3_b = MP3_BITRATE[category]
    _run_ffmpeg(["-i", str(wav_path), "-c:a", "libvorbis", "-q:a", ogg_q, str(out_base.with_suffix(".ogg"))])
    _run_ffmpeg(["-i", str(wav_path), "-c:a", "libmp3lame", "-b:a", mp3_b, str(out_base.with_suffix(".mp3"))])


def probe_duration(path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return round(float(result.stdout.strip()), 3)
    except ValueError:
        return 0.0


def process_entry(
    category: str,
    name: str,
    spec: dict,
    client: Path,
    manifest: dict,
    out_dir: Path,
    vgmstream: Path,
    force: bool,
    existing_index: dict,
    report: list[str],
) -> dict | None:
    """Traite une piste. Renvoie l'entrée d'index à conserver, ou None si rien à faire."""
    out_base = out_dir / name
    ogg_path = out_base.with_suffix(".ogg")
    mp3_path = out_base.with_suffix(".mp3")

    if ogg_path.exists() and mp3_path.exists() and not force:
        if name in existing_index:
            return existing_index[name]
        # Fichiers présents mais pas d'entrée d'index (première exécution avec un
        # index perdu/manuel) : on retrouve juste la durée, sans redécoder.
        return {"duration": probe_duration(ogg_path), "loop": category == "tracks"}

    pak_ref = spec.get("pak")
    entry = spec.get("entry")
    if not pak_ref or not entry:
        report.append(f"AVERTISSEMENT : entrée de manifeste incomplète pour '{name}' (pak/entry manquant)")
        return None

    pak_path = resolve_pak_path(client, manifest, pak_ref)
    data = extract_pak_entry_bytes(pak_path, entry)
    if data is None:
        report.append(f"AVERTISSEMENT : introuvable pour '{name}' : {entry} dans {pak_path}")
        return None

    payload = fsb_payload_from_bytes(data, entry)
    if payload is None:
        report.append(f"AVERTISSEMENT : format FSB non reconnu pour '{name}' ({entry})")
        return None

    subsong = int(spec.get("subsong", 1))
    count = fsb_subsong_count(payload)
    if count is not None and not (1 <= subsong <= count):
        report.append(f"AVERTISSEMENT : subsong {subsong} hors plage (1..{count}) pour '{name}' ({entry})")
        return None

    with tempfile.TemporaryDirectory(prefix="allodex-audio-") as tmp_dir:
        tmp_fsb = Path(tmp_dir) / "input.fsb"
        tmp_fsb.write_bytes(payload)
        tmp_wav = Path(tmp_dir) / "decoded.wav"
        try:
            run_vgmstream(vgmstream, tmp_fsb, subsong, tmp_wav)
        except RuntimeError as exc:
            report.append(f"AVERTISSEMENT : décodage échoué pour '{name}' : {exc}")
            return None

        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            encode_outputs(tmp_wav, out_base, category)
        except RuntimeError as exc:
            report.append(f"AVERTISSEMENT : encodage échoué pour '{name}' : {exc}")
            return None

        duration = probe_duration(tmp_wav)

    loop = bool(spec.get("loop", category == "tracks"))
    return {"duration": duration, "loop": loop}


def run(client: Path, manifest: dict, out_dir: Path, vgmstream: Path, force: bool) -> tuple[dict, list[str]]:
    index_path = out_dir.parent / f"{out_dir.name}.json"
    existing_index: dict = {}
    if index_path.exists():
        try:
            existing_index = json.loads(index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing_index = {}

    report: list[str] = []
    index: dict = {}
    for category, name, spec in iter_entries(manifest):
        entry = process_entry(
            category, name, spec, client, manifest, out_dir, vgmstream, force, existing_index, report
        )
        if entry is not None:
            index[name] = entry
        elif name in existing_index:
            # Échec sur cette exécution mais une sortie précédente existe déjà : on la garde.
            index[name] = existing_index[name]

    return index, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--client", default=DEFAULT_CLIENT, help="Dossier racine du client Allods Online")
    parser.add_argument("--out", default="public/game/audio", help="Dossier de sortie des pistes audio")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Chemin du manifeste JSON")
    parser.add_argument("--vgmstream", default=str(DEFAULT_VGMSTREAM), help="Chemin de vgmstream-cli")
    parser.add_argument("--force", action="store_true", help="Réencoder même si les fichiers existent déjà")
    args = parser.parse_args(argv)

    vgmstream = Path(args.vgmstream)
    if not vgmstream.exists():
        print(f"ERREUR : vgmstream-cli introuvable à {vgmstream} (voir --vgmstream)", file=sys.stderr)
        return 2
    if not os.access(vgmstream, os.X_OK):
        print(f"ERREUR : vgmstream-cli non exécutable à {vgmstream} (chmod +x)", file=sys.stderr)
        return 2
    if shutil.which("ffmpeg") is None:
        print("ERREUR : ffmpeg introuvable dans le PATH", file=sys.stderr)
        return 2
    if shutil.which("ffprobe") is None:
        print("ERREUR : ffprobe introuvable dans le PATH", file=sys.stderr)
        return 2

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"ERREUR : manifeste introuvable à {manifest_path}", file=sys.stderr)
        return 2
    manifest = load_manifest(manifest_path)

    out_dir = Path(args.out)
    index, report = run(Path(args.client), manifest, out_dir, vgmstream, args.force)

    for line in report:
        print(line, file=sys.stderr)

    out_dir.mkdir(parents=True, exist_ok=True)
    index_path = out_dir.parent / f"{out_dir.name}.json"
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"OK : {len(index)} piste(s) indexée(s) dans {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
