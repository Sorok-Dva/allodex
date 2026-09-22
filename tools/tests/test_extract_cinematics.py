"""Tests de `tools/extract_cinematics.py` (cinématiques précalculées et leurs sous-titres).

Tout se joue sur des tampons synthétiques : les tests ne lisent pas les clients du jeu, qui
ne sont pas toujours montés. Un dernier groupe vérifie la cohérence du manifeste versionné.
"""
from __future__ import annotations

import io
import json
import struct
import zlib
from pathlib import Path

import pytest

from tools.extract_cinematics import (
    DEFAULT_MANIFEST,
    FACTIONS,
    Line,
    TextSet,
    align_starts,
    build_cues,
    merge_starts,
    clean_text,
    has_cyrillic,
    norm_key,
    resolve_lines,
    scan_subtitles,
    strip_speaker,
    to_vtt,
    unpack_loc,
    vtt_time,
)

# --- pack.loc ------------------------------------------------------------------------------


def make_loc(texts: list[str]) -> bytes:
    blob = io.BytesIO()
    entries = []
    for t in texts:
        entries.append((len(t), blob.tell()))
        blob.write(t.encode("utf-16-le"))
    raw = io.BytesIO()
    raw.write(struct.pack("<I", 1234))
    raw.write(struct.pack("<I", 0) + struct.pack("<Q", len(entries) * 2))
    for length, off in entries:
        raw.write(struct.pack("<QQ", length, off))
    data = blob.getvalue()
    raw.write(struct.pack("<I", 1) + struct.pack("<Q", len(data)) + data)
    return zlib.compress(raw.getvalue())


def test_unpack_loc_reads_utf16_texts_in_order():
    assert unpack_loc(make_loc(["Огонь!", "Fire!", ""])) == ["Огонь!", "Fire!", ""]


def test_unpack_loc_rejects_an_unexpected_layout():
    raw = struct.pack("<II", 1, 7)
    with pytest.raises(ValueError):
        unpack_loc(zlib.compress(raw))


# --- pack.bin ------------------------------------------------------------------------------

FLAG = b"\x01\x00\x00\x00\x00\x00\x00\x80"


def subtitle_block(idx: int, delay_ms: int, flag: bytes = FLAG) -> bytes:
    """Bloc tel que relevé dans les clients : (40, 40), délai à T-28, index à T, drapeau à T+16."""
    return (struct.pack("<QQ", 40, 40)            # T-56 .. T-40
            + b"\0" * 12                          # T-40 .. T-28
            + struct.pack("<I", delay_ms)         # T-28 .. T-24
            + b"\0" * 24                          # T-24 .. T
            + struct.pack("<Q", idx) + b"\0" * 8  # T .. T+16
            + flag)


def test_subtitle_block_layout_matches_the_documented_offsets():
    block = subtitle_block(7, 4500)
    t = 56
    assert struct.unpack_from("<QQ", block, t - 56) == (40, 40)
    assert struct.unpack_from("<I", block, t - 28)[0] == 4500
    assert struct.unpack_from("<Q", block, t)[0] == 7


def test_scan_subtitles_finds_every_block_with_its_duration():
    blob = b"\x55" * 100 + subtitle_block(3, 2500) + b"\x00" * 40 + subtitle_block(1, 13000, FLAG[:7] + b"\x00")
    assert scan_subtitles(blob, text_count=10) == {3: 2500, 1: 13000}


def test_scan_subtitles_ignores_indices_beyond_the_text_table_and_foreign_structures():
    fake = struct.pack("<QQ", 40, 0) + b"\0" * 12 + struct.pack("<I", 1000) + b"\0" * 24 + struct.pack("<Q", 2) + b"\0" * 8 + FLAG
    blob = subtitle_block(99, 1000) + fake
    assert scan_subtitles(blob, text_count=10) == {}


# --- textes --------------------------------------------------------------------------------


def test_clean_text_strips_client_markup_and_keeps_line_breaks():
    raw = "<html><CollectionColor><Size18>Il est aveugle...  <br/>\r\nmais il voit tout.</Size18></CollectionColor></html>"
    assert clean_text(raw) == "Il est aveugle...\nmais il voit tout."


def test_norm_key_ignores_case_accents_punctuation_and_yo():
    assert norm_key("Ну, вот и всё...") == "ну вот и все"
    assert norm_key("<html>Écoutez-vous, Kyros !</html>") == "ecoutez vous kyros"


def test_strip_speaker_removes_the_displayed_name_only():
    assert strip_speaker("Курган Печальных: Воины! Сегодня я сам обращусь к вам.") == "Воины! Сегодня я сам обращусь к вам."
    assert strip_speaker("Ну, вот и всё...") == "Ну, вот и всё..."


def test_has_cyrillic():
    assert has_cyrillic("О Тенсес… Они везде!")
    assert not has_cyrillic("Ô Tensess... ils sont partout !")


def textset(texts: dict[str, list[str]], subtitles: dict[int, int]) -> TextSet:
    return TextSet(texts, subtitles)


def test_textset_find_requires_a_unique_subtitle_match():
    ts = textset({"ru": ["Огонь!", "Огонь! Огонь, сонные тетери!", "Не сабтитр"]}, {0: 2000, 1: 5000})
    assert ts.find("ru", "огонь огонь") == 1
    with pytest.raises(LookupError):
        ts.find("ru", "огон")           # deux sous-titres commencent ainsi, aucun n'est égal
    with pytest.raises(LookupError):
        ts.find("ru", "не сабтитр")     # texte présent mais pas un élément de sous-titre


def test_textset_find_prefers_an_exact_text_over_longer_ones_starting_alike():
    ts = textset({"fr": ["Nom de... !", "Nom de Tensess, quelle horreur"]}, {0: 2000, 1: 3000})
    assert ts.find("fr", "nom de") == 0


def test_resolve_lines_takes_ru_en_from_main_and_fr_by_constant_index_offset():
    main = textset({"ru": ["x", "Ступайте на корабль!", "Живо, не медлите!"],
                    "en": ["x", "Go to the ship!", "Живо, не медлите!"]}, {1: 2500, 2: 4000})
    fr = textset({"fr": ["Allez sur le navire !", "Vite, ne vous attardez pas !"]}, {0: 2500, 1: 4000})
    spec = {"fr_anchor": "allez sur le", "lines": [{"ru": "ступайте на"}, {"ru": "живо не"}]}
    warnings: list[str] = []
    lines = resolve_lines(spec, main, fr, warnings.append)
    assert [ln.duration for ln in lines] == [2.5, 4.0]
    assert lines[0].text == {"ru": "Ступайте на корабль!", "en": "Go to the ship!", "fr": "Allez sur le navire !"}
    # anglais resté en russe dans le client : pas de ligne anglaise plutôt qu'un texte faux
    assert "en" not in lines[1].text and lines[1].text["fr"] == "Vite, ne vous attardez pas !"
    assert warnings == []


def test_resolve_lines_drops_french_when_durations_disagree():
    main = textset({"ru": ["Первая", "Вторая"], "en": ["First", "Second"]}, {0: 1000, 1: 2000})
    fr = textset({"fr": ["Première", "Deuxième"]}, {0: 1000, 1: 9999})
    warnings: list[str] = []
    lines = resolve_lines({"fr_anchor": "premiere", "lines": [{"ru": "первая"}, {"ru": "вторая"}]}, main, fr, warnings.append)
    assert "fr" in lines[0].text and "fr" not in lines[1].text
    assert len(warnings) == 1


# --- minutage et WebVTT --------------------------------------------------------------------


def L(duration: float, **text: str) -> Line:
    return Line(duration, text or {"fr": "x"})


def test_build_cues_chains_lines_from_zero_without_measured_starts():
    cues = build_cues([L(2.5), L(4.0)], None, 30)
    assert [(a, b) for a, b, _ in cues] == [(0.0, 2.5), (2.5, 6.5)]


def test_build_cues_uses_measured_starts_and_cuts_at_the_next_line():
    cues = build_cues([L(13.0), L(4.0), L(3.5)], [3.2, 16.0, None], 22)
    assert [(a, b) for a, b, _ in cues] == [(3.2, 16.0), (16.0, 20.0), (20.0, 22)]


def test_build_cues_never_goes_back_in_time():
    cues = build_cues([L(2.0), L(2.0)], [5.0, 1.0], 0)
    assert [(a, b) for a, b, _ in cues] == [(5.0, 7.0), (7.0, 9.0)]


def test_build_cues_places_unmeasured_leading_lines_just_before_the_first_measured_one():
    cues = build_cues([L(2.0), L(2.0), L(3.0)], [None, None, 19.0], 40)
    assert [(a, b) for a, b, _ in cues] == [(15.0, 17.0), (17.0, 19.0), (19.0, 22.0)]


def test_vtt_time_formats_hours_minutes_seconds_millis():
    assert vtt_time(0) == "00:00:00.000"
    assert vtt_time(3725.5) == "01:02:05.500"


def test_to_vtt_writes_only_the_lines_of_the_language_and_escapes_markup():
    cues = [(0.0, 2.0, {"fr": "A < B & C", "en": "A"}), (2.0, 3.0, {"en": "B"})]
    fr = to_vtt(cues, "fr")
    assert fr == "WEBVTT\n\n1\n00:00:00.000 --> 00:00:02.000\nA &lt; B &amp; C\n"
    assert to_vtt(cues, "ru") is None
    assert to_vtt(cues, "en").count("-->") == 2


def test_align_starts_follows_the_lines_in_order_and_skips_missing_ones():
    words = [(0.5, "что"), (0.8, "ж"), (1.0, "ты"), (1.2, "натворил"), (5.0, "о"), (5.3, "великий"), (5.6, "тенсис")]
    lines = [["что", "ж", "ты"], ["абракадабра", "нигде"], ["о", "великий", "тенсес"]]
    assert align_starts(lines, words) == [0.5, None, 5.0]


def test_merge_starts_takes_the_first_pass_that_found_each_line_in_increasing_order():
    passes = [[None, 4.0, 3.0, None], [0.4, 4.2, 6.0, None]]
    assert merge_starts(passes) == [0.4, 4.0, 6.0, None]


def test_align_starts_tolerates_a_swallowed_first_word():
    words = [(44.2, "бегите"), (49.4, "же"), (54.3, "подходите"), (55.1, "твари"), (55.9, "умираю")]
    assert align_starts([["ну", "подходите", "твари", "умираю"]], words) == [54.3]


# --- manifeste versionné -------------------------------------------------------------------


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(Path(DEFAULT_MANIFEST).read_text(encoding="utf-8"))


def test_manifest_ids_are_unique_and_factions_valid(manifest):
    ids = [c["id"] for c in manifest["cinematics"]]
    assert len(ids) == len(set(ids))
    assert {c["faction"] for c in manifest["cinematics"]} <= set(FACTIONS)
    assert all(c["arc"] in manifest["arcs"] and c["source"] in manifest["sources"] for c in manifest["cinematics"])


def test_manifest_gives_each_faction_its_own_prologue_first(manifest):
    for faction in ("league", "empire"):
        film = sorted((c for c in manifest["cinematics"] if c["faction"] in (faction, "common")), key=lambda c: c["order"])
        assert film[0]["faction"] == faction and film[0]["arc"] == "prologue"
        orders = [c["order"] for c in film]
        assert len(orders) == len(set(orders)), "deux cinématiques d'un même film à la même place"


def test_manifest_puts_the_boss_presentations_in_a_bonus_after_the_film(manifest):
    bonus = [c for c in manifest["cinematics"] if c.get("bonus")]
    main = [c for c in manifest["cinematics"] if not c.get("bonus")]
    assert len(bonus) == 12 and all(c["arc"] == "bosses" for c in bonus)
    assert min(c["order"] for c in bonus) > max(c["order"] for c in main)


def test_manifest_documents_every_placement(manifest):
    assert all(c["chronology"] for c in manifest["cinematics"])
    assert all(c["title"]["fr"] and c["title"]["en"] for c in manifest["cinematics"])
