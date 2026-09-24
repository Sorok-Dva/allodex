"""Travellings de mise en scène des cinématiques moteur (données synthétiques)."""
import math

from tools.cutscene_travelling import smootherstep, splice, travelling_keys


def _actor(ident, x, y, appear=0.0):
    return {"id": ident, "path": [{"t": 0, "p": [x, y, 0.0]}], "height": 1.0, "scale": 1.0, "appear": appear}


def test_travelling_starts_and_ends_at_rest_and_arcs_around_the_group():
    actors = [_actor("a", 0, 0), _actor("b", 2, 0)]
    pts, tgts = travelling_keys(0.0, 20.0, [1.0, -5.0, 1.5], None, actors, [], {"arc": 20, "dolly": 0.0})
    assert pts[0]["t"] == 0.0 and pts[-1]["t"] == 20.0
    # vitesse nulle aux bornes (smootherstep), arc de 20° autour du centre (1, 0)
    step0 = math.dist(pts[0]["p"], pts[1]["p"])
    mid = len(pts) // 2
    assert step0 < 0.2 * math.dist(pts[mid]["p"], pts[mid + 1]["p"])
    a0 = math.atan2(pts[0]["p"][1], pts[0]["p"][0] - 1)
    a1 = math.atan2(pts[-1]["p"][1], pts[-1]["p"][0] - 1)
    assert abs(math.degrees(a1 - a0) - 20) < 0.5
    # le point du manifeste est au milieu de l'arc
    assert math.dist(pts[mid]["p"][:2], [1.0, -5.0]) < 0.3


def test_target_frames_the_speaker_during_his_line_and_is_smooth():
    actors = [_actor("a", 0, 0), _actor("b", 4, 0)]
    lines = [{"start": 5.0, "end": 9.0, "speaker": "b"}]
    _, tgts = travelling_keys(0.0, 14.0, [2.0, -6.0, 1.5], None, actors, lines, {"lean": 1.0, "smooth": 0.5})
    at = {k["t"]: k["p"] for k in tgts}
    assert abs(at[0.0][0] - 2.0) < 0.05          # groupe
    assert abs(at[7.0][0] - 4.0) < 0.05          # locuteur
    jumps = [abs(b["p"][0] - a["p"][0]) for a, b in zip(tgts, tgts[1:])]
    assert max(jumps) < 0.5                       # sans à-coup


def test_actor_joins_the_frame_when_he_appears_and_ground_lifts_the_eye():
    actors = [_actor("a", 0, 0), _actor("b", 4, 0, appear=10.0)]
    pts, tgts = travelling_keys(0.0, 20.0, [0.0, -5.0, 0.2], None, actors, [], {"smooth": 0.3},
                                ground=lambda x, y, z: 1.0)
    at = {k["t"]: k["p"] for k in tgts}
    assert abs(at[5.0][0]) < 0.05 and abs(at[15.0][0] - 2.0) < 0.05
    assert min(p["p"][2] for p in pts) >= 1.8 - 1e-6


def test_troop_member_offset_turns_with_the_model():
    # trio de gibberlings : décalage de `Slot_Defender` (repère du modèle, avant −Y) tourné au cap posé
    from tools.extract_engine_cutscene import troop_offset
    dx, dy = troop_offset([0.415, -0.044, 0.0], {"p": [0.0, 0.0, 0.0], "yaw": 0.0})
    assert (round(dx, 3), round(dy, 3)) == (0.415, -0.044)
    dx, dy = troop_offset([0.415, -0.044, 0.0], {"p": [0.0, 0.0, 0.0], "yaw": math.pi / 2})
    assert (round(dx, 3), round(dy, 3)) == (0.044, 0.415)


def test_long_dialogue_text_is_cut_into_balanced_subtitles_per_language():
    from tools.extract_engine_cutscene import split_line_text
    text = {"ru": "Первая фраза здесь. Вторая фраза тоже тут!\nТретья строка стиха\nЧетвёртая строка стиха",
            "fr": "Phrase une ici. Deux aussi ! Trois vers et quatre vers encore"}
    parts = split_line_text(text, 40)
    assert len(parts) == 3
    assert " ".join(p["ru"] for p in parts) == text["ru"].replace("\n", " ")
    assert all(p.get("fr") for p in parts)
    assert split_line_text({"ru": "Коротко"}, 40) == [{"ru": "Коротко"}]


def test_splice_replaces_the_window_and_holds_before_the_cut():
    track = [{"t": 0.0, "p": [0, 0, 0]}, {"t": 9.999, "p": [0, 0, 0]}, {"t": 10.0, "p": [5, 5, 5]}]
    keys = [{"t": 0.0, "p": [1, 1, 1]}, {"t": 5.0, "p": [2, 2, 2]}, {"t": 10.0, "p": [3, 3, 3]}]
    out = splice(track, keys, 0.0, 10.0)
    assert [k["t"] for k in out] == [0.0, 5.0, 9.999, 10.0]
    assert out[2]["p"] == [3, 3, 3] and out[3]["p"] == [5, 5, 5]
    assert smootherstep(0) == 0 and smootherstep(1) == 1
