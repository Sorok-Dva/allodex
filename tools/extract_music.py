#!/usr/bin/env python3
"""Extrait toutes les musiques FR puis RU, sans doublons de noms internes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.extract_audio import DEFAULT_VGMSTREAM, encode_outputs, extract_pak_entry_bytes, fsb_payload_from_bytes, probe_duration
from tools.extract_archive import DEFAULT_VGMSTREAM_WASM, _stem, decode_subsong, fold_to_stereo, list_subsongs

HERE = Path(__file__).resolve().parent


def slug(name: str) -> str:
    # Le hash du nom exact évite les collisions casse/ponctuation et reste stable.
    readable = re.sub(r"[^a-z0-9]+", "-", _stem(name).lower()).strip("-") or "track"
    return f"{readable}-{hashlib.sha256(name.encode()).hexdigest()[:10]}"


def build_index(entries: list[dict], banks: dict) -> list[dict]:
    groups = list(dict.fromkeys(banks.values()))
    return sorted(entries, key=lambda e: (groups.index(e["group"]) if e["group"] in groups else len(groups), e["name"].casefold(), e["id"]))


def run(manifest: dict, titles: dict, out: Path, vgmstream: Path = DEFAULT_VGMSTREAM,
        *, force: bool = False, only: str | None = None, wasm: Path = DEFAULT_VGMSTREAM_WASM) -> tuple[list[dict], list[str]]:
    out.mkdir(parents=True, exist_ok=True)
    index_path = out.parent / "music.json"
    previous = json.loads(index_path.read_text()) if index_path.exists() else []
    entries = {e["name"]: e for e in previous}
    seen: set[str] = set()
    report: list[str] = []
    banks = manifest["banks"]
    if only and only not in banks:
        raise ValueError(f"Banque inconnue : {only}")
    for client in manifest["clients"]:
        pak = Path(client["root"]) / client["pak"]
        if not pak.is_file():
            report.append(f"Client {client['id']} absent : {pak}")
            # Préserve aussi sa priorité si le client avait déjà été extrait.
            seen.update(e["name"] for e in previous if e["client"] == client["id"])
            continue
        with zipfile.ZipFile(pak) as archive:
            available = {Path(n).stem: n for n in archive.namelist()
                         if n.startswith("SFX/Music/") and n.lower().endswith((".fsb", ".bsb"))}
        for bank, group in banks.items():
            if (only and bank != only) or bank not in available:
                continue
            try:
                data = extract_pak_entry_bytes(pak, available[bank])
                payload = fsb_payload_from_bytes(data, available[bank]) if data else None
                if not payload:
                    raise ValueError("banque FSB absente")
                with tempfile.TemporaryDirectory(prefix="allodex-music-") as tmp:
                    fsb = Path(tmp) / "bank.fsb"
                    fsb.write_bytes(payload)
                    for stream in list_subsongs(vgmstream, fsb, payload):
                        name = _stem(stream["name"]) or f"{bank}_{stream['index']}"
                        if name in seen:
                            continue
                        seen.add(name)
                        ident = slug(name)
                        base = out / ident
                        old = entries.get(name)
                        cached = old and old["client"] == client["id"] and old["bank"] == bank
                        try:
                            if force or not cached or not all(base.with_suffix(ext).is_file() for ext in (".ogg", ".mp3")):
                                wav = Path(tmp) / "track.wav"
                                decode_subsong(vgmstream, wasm, fsb, stream["index"], wav)
                                stereo = fold_to_stereo(wav)
                                # N'expose jamais une paire partiellement encodée.
                                encoded = Path(tmp) / ident
                                encode_outputs(stereo, encoded, "tracks")
                                duration = probe_duration(stereo)
                                for ext in (".ogg", ".mp3"):
                                    encoded.with_suffix(ext).replace(base.with_suffix(ext))
                            else:
                                duration = old["duration"]
                            entries[name] = dict(id=ident, name=name, title=titles.get(name), bank=bank,
                                                 group=group, duration=duration, ogg=f"/game/music/{ident}.ogg",
                                                 mp3=f"/game/music/{ident}.mp3", client=client["id"])
                            print(f"music {client['id']} {bank} / {name}", flush=True)
                        except (OSError, RuntimeError, ValueError) as exc:
                            report.append(f"{client['id']} / {bank} / {name} : {exc}")
            except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
                report.append(f"{client['id']} / {bank} : {exc}")
            # Point de reprise après chaque banque.
            index_path.write_text(json.dumps(build_index(list(entries.values()), banks), indent=2, ensure_ascii=False) + "\n")
    index = build_index(list(entries.values()), banks)
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n")
    return index, report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, default=HERE / "music_manifest.json")
    p.add_argument("--titles", type=Path, default=HERE / "music_titles.json")
    p.add_argument("--client", default=os.environ.get("ALLODS_CLIENT_DIR"))
    p.add_argument("--out", type=Path, default=HERE.parent / "public/game/music")
    p.add_argument("--vgmstream", type=Path, default=DEFAULT_VGMSTREAM)
    p.add_argument("--vgmstream-wasm", type=Path, default=DEFAULT_VGMSTREAM_WASM)
    p.add_argument("--only")
    p.add_argument("--force", action="store_true")
    args = p.parse_args(argv)
    manifest = json.loads(args.manifest.read_text())
    if args.client:
        manifest["clients"][0]["root"] = args.client
    index, report = run(manifest, json.loads(args.titles.read_text()), args.out, args.vgmstream,
                        force=args.force, only=args.only, wasm=args.vgmstream_wasm)
    for warning in report:
        print(f"AVERTISSEMENT : {warning}", file=sys.stderr)
    print(f"OK : {len(index)} pistes → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
