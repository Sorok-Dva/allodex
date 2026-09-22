"""Tests de `tools/inventory_engine_cutscenes.py` (logique pure, sans client ni arbre serveur)."""
from tools.inventory_engine_cutscenes import faction_of, has_content, summarize, voice_scene_key


def test_voice_scene_key_groups_the_lines_of_one_scene():
    assert voice_scene_key("Cutscenes/Isa/Isa_Arrival_2_Urun_Replika_03") == "Cutscenes/Isa/Isa_Arrival_2_Urun"
    assert voice_scene_key("Cutscenes/Isa/Isa_Arrival_2_Urun_Replika_F") == "Cutscenes/Isa/Isa_Arrival_2_Urun"
    assert voice_scene_key("Cutscenes/Edem/Allmother_12") == "Cutscenes/Edem/Allmother"


def test_faction_comes_from_the_map_name_only():
    assert faction_of({"map": "Inst_EmpireStart"}) == "empire"
    assert faction_of({"map": "Inst_LeagueStart"}) == "league"
    assert faction_of({"map": "Ferris4"}) == "common"
    assert faction_of({"map": None}) == "common"


def test_empty_scenes_are_dropped():
    assert not has_content({"camera_tracks": 0, "game_scenes": 0, "lines": []})
    assert has_content({"camera_tracks": 1, "game_scenes": 0, "lines": []})
    assert has_content({"lines": [{"ru": "x"}]})


def test_summary_counts():
    scenes = [
        {"source": "7.0 xdb", "faction": "common", "camera_tracks": 2, "game_scenes": 0, "voiced_lines": 1,
         "subtitled_lines": 1, "lines": [{"in_17": True}]},
        {"source": "17.0 pack.bin", "faction": "common", "voiced_lines": 2, "subtitled_lines": 0,
         "lines": [{"in_17": True}, {"in_17": True}]},
    ]
    s = summarize(scenes)
    assert (s["scenes"], s["from_7_0_xdb"], s["only_17_0"], s["with_camera_track"]) == (2, 1, 1, 1)
    assert (s["lines"], s["voiced_lines"], s["lines_still_in_17_0"]) == (3, 3, 3)
