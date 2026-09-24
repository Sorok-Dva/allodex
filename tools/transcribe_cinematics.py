#!/usr/bin/env python3
"""Sous-titres **transcrits** des chapitres doublés que le jeu ne sous-titre pas (page « Cinématiques »).

Certaines cinématiques ont des voix russes sans aucune ressource de sous-titres dans le client
(vidéos retirées du 10.0, « Pas prévu au plan » du 11.0…). Ce script en fait une transcription
**automatique**, jamais présentée comme officielle :

1. **Transcription** (`faster-whisper`, local, CPU `int8`, modèle `small` par défaut) de la voix
   russe : piste audio de la vidéo (`<id>/video.webm`), ou, pour une scène moteur, mixage de ses
   voix (`engine/<id>/voice/*.ogg`) à leurs instants. Filtre de voix (VAD), pas de reprise du
   texte précédent, et rejet des segments douteux (hallucinations de Whisper sur la musique ou le
   silence) : probabilité de silence élevée, confiance faible, texte répétitif, formules connues
   (« Субтитры сделал… », « Продолжение следует… »), texte sans cyrillique. Les segments écartés
   restent listés (`rejected`) pour la relecture.
2. **Relecture** : `tools/cinematics_transcripts.json` (versionné) garde, par chapitre, les
   répliques (`start`, `end`, `ru` corrigé, traductions `en` et `fr`, sortie brute `whisper`,
   `confidence`). Un chapitre relu (`"reviewed": true`) n'est plus réécrit par une relance :
   la nouvelle sortie va dans `draft`, pour comparaison ; `--replace` force le remplacement.
3. **Pistes** (`--apply`, et à chaque relance) : `ru.vtt`, `en.vtt`, `fr.vtt` du chapitre et son
   entrée de `cinematics.json` (`subtitles.status: "transcribed"`, libellés « (auto) ») ; le
   lecteur affiche « transcription automatique ». `tools/extract_cinematics.py` et
   `tools/extract_engine_cutscene.py` réécrivent ces pistes depuis le même fichier.

Usage :
    python3 tools/transcribe_cinematics.py --list                   # chapitres concernés
    python3 tools/transcribe_cinematics.py --only warp-prologue     # transcrit un chapitre (un à la fois)
    python3 tools/transcribe_cinematics.py --only X --model medium  # si `small` ne suffit pas
    python3 tools/transcribe_cinematics.py --probe --only X         # y a-t-il de la parole ?
    python3 tools/transcribe_cinematics.py --apply                  # pistes et index depuis la relecture

Candidats : chapitres du film (pas `held_back`), voix russes (`audio.language`), sans ligne
officielle. Les traductions EN/FR sont écrites à la main dans le fichier de relecture, avec les noms
officiels des textes du client et du lorebook.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

DEFAULT_MANIFEST = HERE / "cinematics_manifest.json"
DEFAULT_REVIEW = HERE / "cinematics_transcripts.json"
DEFAULT_OUT = HERE.parent / "public" / "game" / "cinematics"
LANGS = ("fr", "en", "ru")
LABELS = {"fr": "Français (auto)", "en": "English (auto)", "ru": "Русский (авто)"}

REVIEW_NOTE = ("Transcriptions automatiques (faster-whisper, local) des chapitres doublés sans sous-titres dans "
               "le jeu, relues à la main : `ru` = texte russe corrigé (noms propres compris), `en`/`fr` = "
               "traductions de relecture, avec les noms officiels des textes du client et du lorebook ; "
               "`whisper` = sortie brute ; `rejected` = segments écartés (hallucinations, musique). Ce ne sont "
               "pas des données du jeu : le site les marque « transcription automatique ». Un chapitre "
               "`reviewed` n'est pas réécrit par tools/transcribe_cinematics.py (sa nouvelle sortie va dans "
               "`draft`).")

# Formules que Whisper invente sur la musique ou le silence (génériques de sous-titreurs, fin de vidéo).
HALLUCINATIONS = re.compile(
    r"субтитр|продолжение следует|спасибо за (просмотр|внимание)|подпис(ывайтесь|аться)|редактор|корректор|"
    r"dimatorzok|игорь негода|amara\.org|до новых встреч|ставьте лайк", re.I)

# Seuils de rejet (sur les segments de faster-whisper).
NO_SPEECH_MAX = 0.6       # probabilité de silence au-delà de laquelle un segment peu sûr est écarté
LOGPROB_MIN = -1.0        # confiance moyenne minimale (log-probabilité par jeton)
COMPRESSION_MAX = 2.4     # texte trop répétitif (boucle de Whisper)


# --- sélection ------------------------------------------------------------------------------------

def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def candidates(manifest: dict, index: dict) -> list[str]:
    """Chapitres du film doublés en russe sans ligne officielle (entrée de l'index sans réplique)."""
    by_id = {c["id"]: c for c in index.get("cinematics", [])}
    out = []
    for spec in manifest["cinematics"]:
        entry = by_id.get(spec["id"])
        if entry is None or (spec.get("audio") or {}).get("language") != "ru":
            continue
        subs = entry.get("subtitles") or {}
        if subs.get("status") == "official" and subs.get("lines"):
            continue
        out.append(spec["id"])
    return out


def chapter_dir(entry: dict) -> str:
    """Dossier du chapitre relatif à `public/game/cinematics/` (`<id>` ou `engine/<id>`)."""
    return f"engine/{entry['id']}" if entry.get("engine") else entry["id"]


# --- audio ----------------------------------------------------------------------------------------

def chapter_audio(entry: dict, out_root: Path, tmp: Path) -> Path | None:
    """WAV mono 16 kHz de la voix du chapitre : piste de la vidéo, ou voix d'une scène moteur posées à
    leurs instants (sans musique ni effets : rien d'autre à reconnaître)."""
    wav = tmp / f"{entry['id']}.wav"
    if entry.get("engine"):
        scene = load_json(out_root / entry["engine"]["scene"])
        base = out_root / chapter_dir(entry)
        voices = [(line["start"], base / line["voice"]["ogg"]) for line in scene.get("lines", [])
                  if (line.get("voice") or {}).get("ogg") and (base / line["voice"]["ogg"]).is_file()]
        if not voices:
            return None
        args = ["ffmpeg", "-y", "-loglevel", "error"]
        for _, path in voices:
            args += ["-i", str(path)]
        chains = [f"[{i}:a]aresample=16000,aformat=channel_layouts=mono,adelay={int(t * 1000)}[a{i}]"
                  for i, (t, _) in enumerate(voices)]
        mix = "".join(f"[a{i}]" for i in range(len(voices)))
        args += ["-filter_complex", ";".join(chains) + f";{mix}amix=inputs={len(voices)}:normalize=0[out]",
                 "-map", "[out]", "-t", f"{float(scene.get('duration') or entry['duration']):.2f}", str(wav)]
        subprocess.run(args, check=True)
        return wav
    files = entry.get("files") or {}
    src = out_root / (files.get("webm") or files.get("mp4") or "")
    if not src.is_file():
        return None
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", str(wav)],
                   check=True)
    return wav


# --- transcription --------------------------------------------------------------------------------

def reject_reason(seg: dict) -> str | None:
    """Pourquoi un segment de Whisper est écarté (`None` : gardé)."""
    text = seg["text"].strip()
    if not re.search(r"[а-яё]", text, re.I):
        return "sans cyrillique"
    if HALLUCINATIONS.search(text):
        return "formule de fin de vidéo (hallucination connue)"
    if text.upper() == text and len(re.findall(r"[А-ЯЁ]", text)) > 3:
        return "description sonore en capitales (« СПОКОЙНАЯ МУЗЫКА »)"
    if seg["compression_ratio"] > COMPRESSION_MAX:
        return f"texte répétitif (compression {seg['compression_ratio']:.2f})"
    if seg["avg_logprob"] < LOGPROB_MIN:
        return f"confiance faible ({math.exp(seg['avg_logprob']):.2f})"
    if seg["no_speech_prob"] > NO_SPEECH_MAX and seg["avg_logprob"] < -0.5:
        return f"probablement pas de parole (silence {seg['no_speech_prob']:.2f})"
    return None


def transcribe(wav: Path, model_name: str, prompt: str | None) -> list[dict]:
    """Segments de faster-whisper (russe, VAD, mots horodatés) : début et fin pris sur les mots."""
    from faster_whisper import WhisperModel  # dépendance facultative (pip install faster-whisper)
    model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=4)
    segments, _ = model.transcribe(
        str(wav), language="ru", beam_size=5, vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 400, "speech_pad_ms": 200},
        condition_on_previous_text=False, word_timestamps=True, initial_prompt=prompt or None,
        temperature=(0.0, 0.2, 0.4))
    out = []
    for seg in segments:
        words = [w for w in (seg.words or []) if w.word.strip()]
        start = float(words[0].start) if words else float(seg.start)
        end = float(words[-1].end) if words else float(seg.end)
        out.append({"start": round(start, 2), "end": round(end, 2), "text": seg.text.strip(),
                    "avg_logprob": float(seg.avg_logprob), "no_speech_prob": float(seg.no_speech_prob),
                    "compression_ratio": float(seg.compression_ratio),
                    "word_min": round(min((float(w.probability) for w in words), default=0.0), 2)})
    return out


def draft_lines(segments: list[dict]) -> tuple[list[dict], list[dict]]:
    """Répliques gardées (texte brut à relire) et segments écartés, avec la raison."""
    kept, rejected = [], []
    for seg in segments:
        why = reject_reason(seg)
        if why:
            rejected.append({"start": seg["start"], "end": seg["end"], "whisper": seg["text"], "why": why})
            continue
        kept.append({"start": seg["start"], "end": seg["end"], "ru": seg["text"], "en": "", "fr": "",
                     "whisper": seg["text"], "confidence": round(math.exp(seg["avg_logprob"]), 2),
                     "word_min": seg["word_min"]})
    return kept, rejected


def merge_review(review: dict, cid: str, audio: str, model: str, kept: list[dict], rejected: list[dict],
                 replace: bool) -> str:
    """Range la transcription dans le fichier de relecture ; un chapitre relu garde ses répliques."""
    chapters = review.setdefault("chapters", {})
    entry = chapters.get(cid)
    fresh = {"audio": audio, "model": f"faster-whisper {model}, int8, VAD", "lines": kept, "rejected": rejected}
    if entry and entry.get("reviewed") and not replace:
        entry["draft"] = {"model": fresh["model"], "lines": kept, "rejected": rejected}
        return "relu : nouvelle sortie rangée dans `draft`"
    keep = {k: entry[k] for k in ("prompt", "note") if entry and k in entry}
    chapters[cid] = {**fresh, **keep, "reviewed": False}
    return f"{len(kept)} répliques, {len(rejected)} segments écartés (à relire)"


# --- pistes ---------------------------------------------------------------------------------------

def cues_of(chapter: dict, duration: float) -> list[tuple[float, float, dict[str, str]]]:
    """Répliques relues → repères : fin du dernier mot + 0,4 s, au moins 1,2 s d'affichage (lecture),
    coupée au départ suivant et à la durée du chapitre."""
    lines = sorted((l for l in chapter.get("lines", []) if l.get("ru")), key=lambda l: l["start"])
    cues = []
    for i, line in enumerate(lines):
        start = float(line["start"])
        end = max(float(line["end"]) + 0.4, start + 1.2)
        if i + 1 < len(lines):
            end = min(end, float(lines[i + 1]["start"]))
        if duration:
            end = min(end, duration)
        text = {lang: line[lang].strip() for lang in LANGS if (line.get(lang) or "").strip()}
        if end > start and text:
            cues.append((round(start, 3), round(end, 3), text))
    return cues


def write_tracks(cid: str, folder: Path, rel: str, chapter: dict, duration: float) -> tuple[list[dict], dict]:
    """Pistes WebVTT transcrites d'un chapitre ; rend `tracks` et `subtitles` de l'index."""
    from tools.extract_cinematics import to_vtt
    cues = cues_of(chapter, duration)
    tracks = []
    for lang in LANGS:
        vtt = to_vtt(cues, lang)
        path = folder / f"{lang}.vtt"
        if vtt:
            folder.mkdir(parents=True, exist_ok=True)
            path.write_text(vtt, encoding="utf-8")
            tracks.append({"lang": lang, "label": LABELS[lang], "src": f"{rel}/{lang}.vtt",
                           "lines": sum(1 for c in cues if lang in c[2])})
        elif path.exists():
            path.unlink()
    meta = {"status": "transcribed", "lines": len(cues), "timing": "transcribed",
            "reviewed": bool(chapter.get("reviewed")), "model": chapter.get("model")}
    return tracks, meta


def transcribed_tracks(cid: str, out_root: Path, rel: str, duration: float,
                       review_path: Path = DEFAULT_REVIEW) -> tuple[list[dict], dict] | None:
    """Pistes transcrites d'un chapitre sans sous-titres officiels, s'il est dans le fichier de relecture
    (appelé par les extracteurs, pour qu'une relance les garde)."""
    chapter = load_json(review_path).get("chapters", {}).get(cid)
    if not chapter or not chapter.get("lines"):
        return None
    return write_tracks(cid, out_root / rel, rel, chapter, duration)


def apply(review: dict, out_root: Path, only: list[str] | None = None) -> list[str]:
    """Pistes et entrées de l'index de tous les chapitres du fichier de relecture."""
    index_path = out_root / "cinematics.json"
    index = load_json(index_path)
    done = []
    for entry in index.get("cinematics", []):
        cid = entry["id"]
        chapter = review.get("chapters", {}).get(cid)
        if not chapter or (only and cid not in only):
            continue
        subs = entry.get("subtitles") or {}
        if subs.get("status") == "official" and subs.get("lines"):
            continue   # jamais par-dessus des sous-titres du jeu
        rel = chapter_dir(entry)
        tracks, meta = write_tracks(cid, out_root / rel, rel, chapter, float(entry.get("duration") or 0))
        entry["tracks"] = tracks
        entry["subtitles"] = {**{k: v for k, v in subs.items() if k == "audio"}, **meta}
        done.append(f"{cid} : {meta['lines']} répliques, pistes {', '.join(t['lang'] for t in tracks)}"
                    f"{'' if meta['reviewed'] else ' (non relu)'}")
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return done


def save_review(review: dict, path: Path) -> None:
    doc = {"_note": REVIEW_NOTE, "chapters": {k: review["chapters"][k] for k in sorted(review.get("chapters", {}))}}
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    p.add_argument("--review", default=str(DEFAULT_REVIEW))
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p.add_argument("--only", action="append", help="chapitre (répétable) ; sans : les candidats absents de la relecture")
    p.add_argument("--model", default="small", help="modèle faster-whisper (small, medium…), CPU int8")
    p.add_argument("--replace", action="store_true", help="remplace aussi les répliques d'un chapitre relu")
    p.add_argument("--list", action="store_true", help="liste les chapitres candidats")
    p.add_argument("--probe", action="store_true", help="n'écrit rien : montre les segments et leur verdict")
    p.add_argument("--apply", action="store_true", help="pistes et index depuis le fichier de relecture, sans Whisper")
    args = p.parse_args(argv)

    manifest = load_json(Path(args.manifest))
    out_root = Path(args.out)
    index = load_json(out_root / "cinematics.json")
    review_path = Path(args.review)
    review = load_json(review_path)
    review.setdefault("chapters", {})
    todo = candidates(manifest, index)
    if args.list:
        for cid in todo:
            state = review["chapters"].get(cid)
            print(f"{cid}\t{'relu' if state and state.get('reviewed') else 'à relire' if state else 'à transcrire'}")
        return 0
    if args.apply:
        for line in apply(review, out_root, args.only):
            print(line)
        return 0
    by_id = {c["id"]: c for c in index.get("cinematics", [])}
    chosen = args.only or [cid for cid in todo if cid not in review["chapters"]]
    for cid in chosen:   # un chapitre à la fois (mémoire)
        entry = by_id.get(cid)
        if entry is None:
            print(f"{cid} : absent de l'index", file=sys.stderr)
            continue
        with tempfile.TemporaryDirectory(prefix="allodex-whisper-") as tmp:
            wav = chapter_audio(entry, out_root, Path(tmp))
            if wav is None:
                print(f"{cid} : pas de voix à transcrire", file=sys.stderr)
                continue
            prompt = (review["chapters"].get(cid) or {}).get("prompt")
            segments = transcribe(wav, args.model, prompt)
        kept, rejected = draft_lines(segments)
        if args.probe:
            for seg in segments:
                print(f"{seg['start']:7.2f}–{seg['end']:7.2f}  p={math.exp(seg['avg_logprob']):.2f} "
                      f"silence={seg['no_speech_prob']:.2f}  {reject_reason(seg) or 'gardé'}  {seg['text']}")
            continue
        rel = chapter_dir(entry)
        print(f"{cid} : {merge_review(review, cid, rel, args.model, kept, rejected, args.replace)}")
        save_review(review, review_path)
    if not args.probe:
        save_review(review, review_path)
        for line in apply(review, out_root, chosen):
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
