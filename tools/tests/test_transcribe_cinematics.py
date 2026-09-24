"""Tests des sous-titres transcrits (sans Whisper : segments synthétiques)."""
import json

from tools.transcribe_cinematics import apply, candidates, cues_of, draft_lines, merge_review, reject_reason


def seg(text, logprob=-0.2, silence=0.1, ratio=1.3, start=0.0, end=1.0):
    return {"start": start, "end": end, "text": text, "avg_logprob": logprob, "no_speech_prob": silence,
            "compression_ratio": ratio, "word_min": 0.5}


def test_reject_reason_drops_whisper_hallucinations_and_keeps_confident_speech():
    assert reject_reason(seg("Редактор субтитров Н.Закомолдина")).startswith("formule")
    assert reject_reason(seg("Продолжение следует...")).startswith("formule")
    assert reject_reason(seg("СПОКОЙНАЯ МУЗЫКА")).startswith("description sonore")
    assert reject_reason(seg("Thank you.")) == "sans cyrillique"
    assert reject_reason(seg("да да да да да", ratio=3.1)).startswith("texte répétitif")
    assert reject_reason(seg("Двигатели остановлены.", logprob=-1.4)).startswith("confiance faible")
    assert reject_reason(seg("Ага.", logprob=-0.7, silence=0.9)).startswith("probablement pas de parole")
    # un narrateur sur la musique a une probabilité de silence élevée mais une forte confiance : gardé
    assert reject_reason(seg("Город Вышеград на краю мира.", logprob=-0.13, silence=0.86)) is None


def test_draft_lines_keeps_raw_text_and_lists_rejected_segments():
    kept, rejected = draft_lines([seg("Активирован.", start=13.8, end=14.4), seg("Субтитры сделал DimaTorzok")])
    assert kept[0]["ru"] == kept[0]["whisper"] == "Активирован." and kept[0]["en"] == ""
    assert kept[0]["confidence"] == 0.82 and rejected[0]["why"].startswith("formule")


def test_merge_review_never_overwrites_a_reviewed_chapter_unless_asked():
    review = {"chapters": {"x": {"reviewed": True, "prompt": "Вышеград", "lines": [{"ru": "corrigé"}]}}}
    merge_review(review, "x", "x", "small", [{"ru": "brut"}], [], replace=False)
    assert review["chapters"]["x"]["lines"] == [{"ru": "corrigé"}]
    assert review["chapters"]["x"]["draft"]["lines"] == [{"ru": "brut"}]
    merge_review(review, "x", "x", "small", [{"ru": "brut"}], [], replace=True)
    chapter = review["chapters"]["x"]
    assert chapter["lines"] == [{"ru": "brut"}] and not chapter["reviewed"] and chapter["prompt"] == "Вышеград"


def test_cues_of_pads_short_lines_and_stops_at_the_next_line():
    chapter = {"lines": [{"start": 1.0, "end": 1.3, "ru": "Да.", "en": "Yes.", "fr": ""},
                         {"start": 1.9, "end": 3.0, "ru": "Нет.", "en": "No.", "fr": "Non."}]}
    cues = cues_of(chapter, 3.2)
    assert cues[0] == (1.0, 1.9, {"en": "Yes.", "ru": "Да."})
    assert cues[1] == (1.9, 3.2, {"fr": "Non.", "en": "No.", "ru": "Нет."})


def test_candidates_are_dubbed_film_chapters_without_official_lines():
    manifest = {"cinematics": [{"id": "a", "audio": {"language": "ru"}}, {"id": "b", "audio": {"language": None}},
                               {"id": "c", "audio": {"language": "ru"}}, {"id": "d", "audio": {"language": "ru"}}]}
    index = {"cinematics": [{"id": "a", "subtitles": {"status": "none", "lines": 0}},
                            {"id": "b", "subtitles": {"status": "none", "lines": 0}},
                            {"id": "c", "subtitles": {"status": "official", "lines": 4}},
                            {"id": "d", "subtitles": {"status": "official", "lines": 0}}]}
    assert candidates(manifest, index) == ["a", "d"]


def test_apply_marks_tracks_transcribed_and_leaves_official_subtitles_alone(tmp_path):
    index = {"arcs": {}, "cinematics": [
        {"id": "a", "duration": 5.0, "files": {"webm": "a/video.webm"}, "tracks": [],
         "subtitles": {"status": "none", "lines": 0, "timing": None}},
        {"id": "b", "duration": 5.0, "tracks": [{"lang": "ru"}], "subtitles": {"status": "official", "lines": 2}}]}
    (tmp_path / "cinematics.json").write_text(json.dumps(index), encoding="utf-8")
    line = {"start": 0.5, "end": 2.0, "ru": "Это не по плану!", "en": "This wasn't part of the plan!", "fr": ""}
    review = {"chapters": {"a": {"reviewed": True, "model": "m", "lines": [line]}, "b": {"lines": [line]}}}
    apply(review, tmp_path)
    out = {c["id"]: c for c in json.loads((tmp_path / "cinematics.json").read_text(encoding="utf-8"))["cinematics"]}
    assert out["a"]["subtitles"]["status"] == "transcribed" and out["a"]["subtitles"]["reviewed"]
    assert [t["lang"] for t in out["a"]["tracks"]] == ["en", "ru"] and out["a"]["tracks"][0]["label"] == "English (auto)"
    assert (tmp_path / "a" / "ru.vtt").read_text(encoding="utf-8").endswith("Это не по плану!\n")
    assert out["b"]["subtitles"]["status"] == "official" and not (tmp_path / "b").exists()
