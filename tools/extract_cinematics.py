#!/usr/bin/env python3
"""Extrait les cinématiques précalculées du client Allods Online pour la page « Cinématiques ».

Source par défaut : le **dernier client** (17.0, `/mnt/h/MyGames/AllodsRU`). Le manifeste
`tools/cinematics_manifest.json` décrit chaque vidéo (entrée de `Video.pak`, événement du
registre vidéo du client, faction, clé de chronologie et sa justification, titre éditorial)
et, quand le jeu en a, ses sous-titres.

* **Vidéo** — l'`.ogv` (Theora + Vorbis, voix russe incrustée) est transcodé en
  `video.webm` (VP9 + Opus) et `video.mp4` (H.264 + AAC), 720p au plus, avec une affiche
  `poster.jpg`. Les vidéos retirées du jeu viennent d'un client plus ancien (`source`).
* **Sous-titres** — ils ne sont pas dans la vidéo : le client les affiche par l'add-on
  `Subtitles` à partir de ressources `UISubtitleShow` (un texte localisé + `delayMs`, sa
  durée d'affichage). Ces ressources sont compilées dans `Bin/pack.bin` ; chaque élément y
  occupe un bloc reconnaissable (voir `scan_subtitles`) qui donne l'**index du texte** dans
  les `pack.<langue>.loc` et la **durée**. Le manifeste désigne chaque ligne par le début de
  son texte russe (langue source) ; le russe et l'anglais sortent du client 17.0 (même
  index), le français du client FR 16.0 (décalage d'index constant au sein d'une ressource,
  vérifié par l'égalité des durées). Aucun texte n'est écrit à la main.
* **Minutage** — les données décodées donnent l'ordre et la durée de chaque ligne, pas
  l'instant où le script de la scène la déclenche. Ces instants sont **mesurés** une fois sur
  la piste audio (`--measure-sync`, reconnaissance vocale : début de la réplique officielle
  dans la voix) et rangés dans `tools/cinematics_sync.json`. Une vidéo à ligne unique qui
  couvre toute la vidéo (présentations de boss) commence à 0 sans mesure.

Sorties : `public/game/cinematics/<id>/{video.webm, video.mp4, poster.jpg, fr.vtt, en.vtt,
ru.vtt}` et l'index `public/game/cinematics/cinematics.json`. Idempotent : une vidéo déjà
transcodée est gardée sauf `--force` ; sous-titres et index sont toujours régénérés. Un
client absent (disque non monté) ou une entrée introuvable avertit sur stderr et l'entrée
garde `files: null`.

Usage : python3 tools/extract_cinematics.py [--only league-intro ...] [--force]
                                            [--skip-video] [--measure-sync]
                                            [--source-root main=/mnt/x/...]
"""
from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.extract_audio import probe_duration  # noqa: E402
from tools.extract_menu_scene import BinSource  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE / "cinematics_manifest.json"
DEFAULT_SYNC = HERE / "cinematics_sync.json"
DEFAULT_OUT = HERE.parent / "public" / "game" / "cinematics"
LANGS = ("fr", "en", "ru")
LANG_LABELS = {"fr": "Français", "en": "English", "ru": "Русский"}
FACTIONS = ("league", "empire", "common")

# Réglages d'encodage : 720p, VP9 au CRF 40 (≈ 1,1 Mb/s sur ces clips) et H.264 au CRF 29
# (≈ 1,2 Mb/s) ; à CRF 34/26 les fichiers pesaient 50 % de plus sans différence visible.
MAX_HEIGHT = 720
VP9_ARGS = ["-c:v", "libvpx-vp9", "-crf", "40", "-b:v", "0", "-row-mt", "1", "-deadline", "good",
            "-cpu-used", "4", "-c:a", "libopus", "-b:a", "96k"]
H264_ARGS = ["-c:v", "libx264", "-preset", "slow", "-crf", "29", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart"]


# --- textes localisés (Bin/pack.<langue>.loc) ------------------------------------------------

def unpack_loc(data: bytes, is_64bit: bool = True) -> list[str]:
    """Décode un `pack.loc` : zlib → en-tête u32, bloc 0 (paires longueur/offset), bloc 1
    (textes UTF-16). Même format que les outils de traduction du projet `allods-texts-packer`."""
    raw = zlib.decompress(data)
    s = io.BytesIO(raw)
    word = "<Q" if is_64bit else "<I"
    size = 8 if is_64bit else 4

    def u32() -> int:
        return struct.unpack("<I", s.read(4))[0]

    def uword() -> int:
        return struct.unpack(word, s.read(size))[0]

    u32()  # en-tête (identifiant de construction)
    if u32() != 0:
        raise ValueError("pack.loc : bloc 0 attendu")
    entries = [(uword(), uword()) for _ in range(uword() // 2)]
    if u32() != 1:
        raise ValueError("pack.loc : bloc 1 attendu")
    blob = s.read(uword())
    return [blob[off:off + length * 2].decode("utf-16-le") for length, off in entries]


# --- éléments UISubtitleShow dans Bin/pack.bin -----------------------------------------------

# Bloc d'un élément de sous-titre (relevé sur les clients 16.0 FR et 17.0 RU) : à T-56 et
# T-48 deux u64 valant 40 (en-tête de tableau), u32 `delayMs` à T-28, 24 octets nuls, u64
# index du texte à T, 8 octets nuls, puis le drapeau 01 00 00 00 00 00 00 (00|80).
_FLAG_RE = re.compile(rb"\x01\x00\x00\x00\x00\x00\x00[\x00\x80]")


def scan_subtitles(blob: bytes, text_count: int) -> dict[int, int]:
    """Renvoie {index de texte → delayMs} pour chaque élément de sous-titre du pack.bin."""
    found: dict[int, int] = {}
    for m in _FLAG_RE.finditer(blob):
        t = m.start() - 16
        if t < 56:
            continue
        idx = struct.unpack_from("<Q", blob, t)[0]
        if idx >= text_count or blob[t + 8:t + 16] != b"\0" * 8 or blob[t - 24:t] != b"\0" * 24:
            continue
        if struct.unpack_from("<QQ", blob, t - 56) != (40, 40):
            continue
        found.setdefault(idx, struct.unpack_from("<I", blob, t - 28)[0])
    return found


def clean_text(text: str) -> str:
    """Texte affichable : balises du client retirées, `<br/>` → saut de ligne."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def norm_key(text: str) -> str:
    """Forme de comparaison : minuscules, ё→е, sans accents ni ponctuation."""
    text = clean_text(text).lower().replace("ё", "е")
    text = "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")
    return " ".join(re.findall(r"\w+", text))


def strip_speaker(text: str) -> str:
    """Retire le nom du personnage (« Курган Печальных: … ») : il s'affiche, il ne se dit pas."""
    return re.sub(r"^[^:\n]{1,40}:\s+", "", text)


def has_cyrillic(text: str) -> bool:
    return bool(re.search(r"[Ѐ-ӿ]", text))


@dataclass
class TextSet:
    """Textes d'un client (une liste par langue, mêmes index) et ses éléments de sous-titres."""
    texts: dict[str, list[str]]
    subtitles: dict[int, int]
    _keys: dict[str, dict[int, str]] = field(default_factory=dict)

    def find(self, lang: str, prefix: str) -> int:
        """Index de l'élément de sous-titre dont le texte (`lang`) commence par `prefix`."""
        keys = self._keys.setdefault(lang, {i: norm_key(self.texts[lang][i]) for i in self.subtitles})
        want = norm_key(prefix)
        hits = [i for i, k in keys.items() if k.startswith(want)]
        if len(hits) > 1:
            # un texte court peut être le début d'un autre (« Nom de… ! ») : l'égalité tranche
            hits = [i for i in hits if keys[i] == want] or hits
        if len(hits) != 1:
            raise LookupError(f"« {prefix} » ({lang}) : {len(hits)} sous-titres correspondent")
        return hits[0]


def load_textset(root: Path, spec: dict) -> TextSet:
    with zipfile.ZipFile(root / spec["texts_pak"]) as z:
        texts = {lang: unpack_loc(z.read(entry)) for lang, entry in spec["locs"].items()}
    with zipfile.ZipFile(root / spec["bin_pak"]) as z:
        blob = zlib.decompress(z.read("Bin/pack.bin"))
    count = min(len(v) for v in texts.values())
    return TextSet(texts, scan_subtitles(blob, count))


# --- sous-titres d'une cinématique -----------------------------------------------------------

@dataclass
class Line:
    duration: float
    text: dict[str, str]


def resolve_lines(spec: dict, main: TextSet, fr: TextSet | None, warn) -> list[Line]:
    """Lignes officielles d'une cinématique : russe/anglais du client principal, français du
    client FR par décalage d'index (ancré sur la première ligne, vérifié par les durées)."""
    lines: list[Line] = []
    delta = None
    if fr is not None and spec.get("fr_anchor"):
        try:
            first = main.find("ru", spec["lines"][0]["ru"])
            delta = first - fr.find("fr", spec["fr_anchor"])
        except LookupError as exc:
            warn(f"ancre française : {exc}")
    for item in spec["lines"]:
        idx = main.find("ru", item["ru"])
        dur = main.subtitles[idx] / 1000
        text = {"ru": clean_text(main.texts["ru"][idx])}
        en = clean_text(main.texts["en"][idx]) if "en" in main.texts else ""
        if en and not has_cyrillic(en):
            text["en"] = en
        if delta is not None:
            j = idx - delta
            if j in fr.subtitles and fr.subtitles[j] == main.subtitles[idx]:
                text["fr"] = clean_text(fr.texts["fr"][j])
            else:
                warn(f"pas de français pour « {item['ru']} » (index {j}, durées différentes ou absent)")
        lines.append(Line(dur, text))
    return lines


def build_cues(lines: list[Line], starts: list[float | None] | None, video_duration: float) -> list[tuple[float, float, dict[str, str]]]:
    """Place les lignes : départ mesuré (`starts`) ou, à défaut, fin de la précédente (les
    lignes de tête non mesurées sont calées juste avant la première mesurée, 0 s'il n'y en a
    aucune) ; fin = départ + durée du client, coupée au départ suivant et à la vidéo."""
    starts = list(starts or [])
    # Lignes de tête non mesurées : calées juste avant la première ligne mesurée.
    first = next((i for i, v in enumerate(starts) if v is not None), None)
    if first:
        t = starts[first]
        for i in range(first - 1, -1, -1):
            t = max(0.0, t - lines[i].duration)
            starts[i] = t
    begins: list[float] = []
    for i, line in enumerate(lines):
        at = starts[i] if i < len(starts) else None
        if at is None or (begins and at <= begins[-1]):
            # pas de mesure, ou mesure antérieure à la ligne précédente : à la suite
            at = begins[-1] + lines[i - 1].duration if begins else 0.0
        begins.append(round(at, 3))
    cues = []
    for i, line in enumerate(lines):
        end = begins[i] + line.duration
        if i + 1 < len(lines):
            end = min(end, begins[i + 1])
        if video_duration:
            end = min(end, video_duration)
        if end > begins[i]:
            cues.append((begins[i], round(end, 3), line.text))
    return cues


def vtt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def to_vtt(cues: list[tuple[float, float, dict[str, str]]], lang: str) -> str | None:
    """Piste WebVTT d'une langue ; `None` si aucune ligne n'existe dans cette langue."""
    body = []
    for n, (start, end, text) in enumerate(cues, 1):
        if lang not in text:
            continue
        escaped = text[lang].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        body.append(f"{n}\n{vtt_time(start)} --> {vtt_time(end)}\n{escaped}\n")
    return "WEBVTT\n\n" + "\n".join(body) if body else None


# --- vidéo -----------------------------------------------------------------------------------

def _ffmpeg(args: list[str]) -> None:
    result = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg a échoué : {result.stderr.decode(errors='replace')[:300]}")


def transcode(src: Path, out_dir: Path, duration: float) -> None:
    scale = ["-vf", f"scale=-2:'min({MAX_HEIGHT},ih)'"]
    _ffmpeg(["-i", str(src), *scale, *VP9_ARGS, str(out_dir / "video.webm")])
    _ffmpeg(["-i", str(src), *scale, *H264_ARGS, str(out_dir / "video.mp4")])
    _ffmpeg(["-ss", f"{duration * 0.4:.2f}", "-i", str(src), "-frames:v", "1", "-vf", "scale=480:-2",
             "-q:v", "4", str(out_dir / "poster.jpg")])


# --- mesure du minutage (optionnelle, reconnaissance vocale) ----------------------------------

_WHISPER = None


def measure_starts(ogv: Path, lines: list[Line]) -> list[float | None]:
    """Début de chaque réplique officielle dans la voix (faster-whisper, mots horodatés).

    Le texte officiel sert d'amorce et de cible : on ne garde de la transcription que les
    instants. Deux passes (sans puis avec détection de voix : la première rate parfois les
    répliques couvertes par la musique, la seconde écrase le début des segments) ; pour
    chaque ligne on garde la première passe qui la retrouve. Une réplique introuvable renvoie
    `None` (placée à la suite de la précédente)."""
    global _WHISPER
    if _WHISPER is None:
        from faster_whisper import WhisperModel  # dépendance facultative
        _WHISPER = WhisperModel("large-v3", device="auto", compute_type="auto")
    spoken = [strip_speaker(line.text["ru"]) for line in lines]
    prompt = " ".join(spoken)[:600]
    targets = [norm_key(text).split() for text in spoken]
    passes = []
    for vad in (False, True):
        segments, _ = _WHISPER.transcribe(str(ogv), language="ru", vad_filter=vad, beam_size=5,
                                          word_timestamps=True, initial_prompt=prompt)
        words = [(float(w.start), norm_key(w.word)) for seg in segments for w in (seg.words or []) if norm_key(w.word)]
        passes.append(align_starts(targets, words))
    return merge_starts(passes)


def merge_starts(passes: list[list[float | None]]) -> list[float | None]:
    """Première valeur mesurée de chaque ligne parmi les passes, en gardant l'ordre croissant."""
    out: list[float | None] = []
    last = -1.0
    for values in zip(*passes):
        pick = next((v for v in values if v is not None and v > last), None)
        out.append(pick)
        if pick is not None:
            last = pick
    return out


def _similar(a: str, b: str) -> float:
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()


def align_starts(lines_words: list[list[str]], words: list[tuple[float, str]], window: int = 40) -> list[float | None]:
    """Pour chaque ligne (dans l'ordre), premier mot de la transcription, après la ligne
    précédente, à partir duquel ses premiers mots se retrouvent (similarité moyenne ≥ 0,7).
    La transcription avale parfois un premier mot bref (« Ну, подходите… ») : on essaie
    aussi la tête de la ligne privée de son premier mot."""
    starts: list[float | None] = []
    cursor = 0
    for lw in lines_words:
        heads = [lw[:3]] + ([lw[1:4]] if len(lw) > 3 else [])
        found = None
        for p in range(cursor, min(len(words), cursor + window)):
            for head in heads:
                span = words[p:p + len(head)]
                if len(span) == len(head) and sum(_similar(a, b[1]) for a, b in zip(head, span)) / len(head) >= 0.7:
                    found = (p, len(head))
                    break
            if found:
                break
        if found is None:
            starts.append(None)
        else:
            starts.append(round(words[found[0]][0], 2))
            cursor = found[0] + found[1]
    return starts


# --- orchestration ---------------------------------------------------------------------------

def output_entry(spec: dict, manifest: dict, files: dict | None, duration: float,
                 tracks: list[dict], sub_meta: dict) -> dict:
    src = manifest["sources"][spec["source"]]
    entry = {
        "id": spec["id"],
        "title": spec["title"],
        "faction": spec["faction"],
        "order": spec["order"],
        "arc": spec["arc"],
        "version": spec["version"],
        "duration": duration,
        "files": files,
        "tracks": tracks,
        "audio": sub_meta.pop("audio"),
        "subtitles": sub_meta,
        "source": {"client": src["client"], "pak": src["video_pak"], "entry": spec["entry"], "event": spec["event"]},
        "chronology": spec.get("chronology", ""),
    }
    if spec.get("note"):
        entry["note"] = spec["note"]
    return entry


def run(manifest: dict, out_dir: Path, sync: dict, only: list[str] | None = None, force: bool = False,
        skip_video: bool = False, measure: bool = False, roots: dict[str, str] | None = None,
        textsets: dict[str, TextSet | None] | None = None) -> tuple[list[dict], dict, list[str]]:
    report: list[str] = []
    roots = roots or {}

    def root_of(name: str) -> Path:
        return Path(roots.get(name, manifest["sources"][name]["root"]))

    if textsets is None:
        textsets = {}
        for name in ("main", "fr"):
            spec = manifest["sources"][name]
            try:
                textsets[name] = load_textset(root_of(name), spec)
            except (OSError, KeyError, zipfile.BadZipFile) as exc:
                report.append(f"textes {name} ({spec['client']}) illisibles : {exc}")
                textsets[name] = None

    previous: dict[str, dict] = {}
    index_path = out_dir / "cinematics.json"
    if index_path.is_file():
        try:
            previous = {e["id"]: e for e in json.loads(index_path.read_text(encoding="utf-8"))["cinematics"]}
        except (ValueError, KeyError):
            previous = {}

    entries = []
    for spec in manifest["cinematics"]:
        cid = spec["id"]
        if only and cid not in only:
            if cid in previous:
                entries.append(previous[cid])
            continue
        warn = lambda msg, cid=cid: report.append(f"{cid} : {msg}")  # noqa: E731
        target = out_dir / cid
        target.mkdir(parents=True, exist_ok=True)
        src = manifest["sources"][spec["source"]]
        source = BinSource([], [str(root_of(spec["source"]) / src["video_pak"])])
        files, duration = None, 0.0
        have = (target / "video.webm").is_file() and (target / "video.mp4").is_file() and (target / "poster.jpg").is_file()
        data = None
        if not have or force or measure:
            data = source.get(spec["entry"])
        with tempfile.TemporaryDirectory(prefix="allodex-cine-") as tmp:
            ogv = Path(tmp) / "source.ogv"
            if data is not None:
                ogv.write_bytes(data)
                duration = probe_duration(ogv)
                if not skip_video and (force or not have):
                    try:
                        transcode(ogv, target, duration)
                        print(f"vidéo    {cid}  {duration:.1f} s")
                    except RuntimeError as exc:
                        warn(str(exc))
            elif not have:
                warn(f"introuvable : {spec['entry']} ({src['client']})")
            if (target / "video.webm").is_file() and (target / "video.mp4").is_file():
                files = {"webm": f"{cid}/video.webm", "mp4": f"{cid}/video.mp4", "poster": f"{cid}/poster.jpg"}
                if not duration:
                    duration = probe_duration(target / "video.mp4")

            tracks: list[dict] = []
            sub_meta: dict = {"status": "none", "lines": 0, "timing": None, "audio": audio_meta(spec)}
            subs = spec.get("subtitles")
            if subs and textsets.get("main") is not None:
                try:
                    lines = resolve_lines(subs, textsets["main"], textsets.get("fr"), warn)
                except LookupError as exc:
                    warn(str(exc))
                    lines = []
                if lines:
                    starts = None
                    if len(lines) > 1:
                        if measure and ogv.is_file():
                            starts = measure_starts(ogv, lines)
                            sync[cid] = starts
                            print(f"minutage {cid}  {starts}")
                        starts = sync.get(cid)
                        if starts is None:
                            warn("minutage non mesuré : lignes enchaînées depuis 0 (lancer --measure-sync)")
                    cues = build_cues(lines, starts, duration)
                    for lang in LANGS:
                        vtt = to_vtt(cues, lang)
                        path = target / f"{lang}.vtt"
                        if vtt:
                            path.write_text(vtt, encoding="utf-8")
                            tracks.append({"lang": lang, "label": LANG_LABELS[lang], "src": f"{cid}/{lang}.vtt",
                                           "lines": sum(1 for c in cues if lang in c[2])})
                        elif path.exists():
                            path.unlink()
                    sub_meta.update({
                        "status": "official",
                        "lines": len(lines),
                        "timing": "client" if len(lines) == 1 else ("measured" if starts else "sequential"),
                    })
        entries.append(output_entry(spec, manifest, files, duration, tracks, sub_meta))
    return entries, sync, report


def audio_meta(spec: dict) -> dict:
    """Piste audio incrustée dans l'.ogv (identique dans tous les clients, quelle que soit
    leur langue) : `language` = langue des voix, `null` = musique et effets seulement."""
    return dict(spec.get("audio") or {"language": None})


def write_index(entries: list[dict], manifest: dict, out_dir: Path) -> None:
    entries = sorted(entries, key=lambda e: (e["order"], e["id"]))
    index = {
        "arcs": manifest["arcs"],
        "cinematics": entries,
    }
    (out_dir / "cinematics.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def parse_roots(values: list[str] | None) -> dict[str, str]:
    roots = {}
    for value in values or []:
        name, _, path = value.partition("=")
        if not path:
            raise SystemExit(f"--source-root attend nom=chemin : {value}")
        roots[name] = path
    return roots


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    p.add_argument("--sync", default=str(DEFAULT_SYNC))
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p.add_argument("--only", action="append")
    p.add_argument("--force", action="store_true")
    p.add_argument("--skip-video", action="store_true")
    p.add_argument("--measure-sync", action="store_true", help="mesure les instants des répliques (faster-whisper)")
    p.add_argument("--source-root", action="append", help="remplace la racine d'une source : main=/chemin")
    args = p.parse_args(argv)

    if shutil.which("ffmpeg") is None:
        print("ffmpeg introuvable", file=sys.stderr)
        return 2
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    sync_path = Path(args.sync)
    sync = json.loads(sync_path.read_text(encoding="utf-8")) if sync_path.is_file() else {}
    sync.pop("_note", None)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    entries, sync, report = run(manifest, out, sync, args.only, args.force, args.skip_video,
                                args.measure_sync, parse_roots(args.source_root))
    write_index(entries, manifest, out)
    if args.measure_sync:
        doc = {"_note": SYNC_NOTE, **{k: sync[k] for k in sorted(sync)}}
        sync_path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for line in report:
        print(f"AVERTISSEMENT : {line}", file=sys.stderr)
    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"OK : {len(entries)} cinématiques → {out} ({total / 2**20:.0f} Mo)")
    return 0


SYNC_NOTE = ("Instants d'apparition (secondes) des répliques officielles, mesurés sur la voix russe de "
             "chaque vidéo par reconnaissance vocale (tools/extract_cinematics.py --measure-sync) : ce ne "
             "sont pas des données du jeu, qui ne donnent que l'ordre et la durée des lignes. null = "
             "réplique introuvable dans la voix, placée à la suite de la précédente.")


if __name__ == "__main__":
    raise SystemExit(main())
