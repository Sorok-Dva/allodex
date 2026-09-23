"""Tests des cinématiques moteur (sans client : données synthétiques)."""
import math
import struct

import numpy as np

from tools.allods_fx import fsb5_stream_names
from tools.allods_scenes import CameraTrack, parse_lightvrt, region_origin
from tools.extract_cinematics import Line
from tools.extract_engine_cutscene import (
    MODEL_FORWARD, camera_keys, encode_light, face_yaw, find_wave, ground_z, light_at, schedule_lines, vertex_light,
)


def test_region_origin_uses_256_m_regions_offset_by_block():
    assert region_origin("Maps/X/000_000/0_0_MapRegion.xdb") == (0.0, 0.0)
    assert region_origin("Maps/X/000_000/1_0_MapRegion.xdb") == (256.0, 0.0)
    assert region_origin("Maps/X/040_050/2_3_MapRegion.xdb") == (42 * 256.0, 53 * 256.0)


def test_parse_lightvrt_maps_block_k_plus_2_to_object_k():
    body = bytes([1, 2, 3, 0] * 2)
    raw = struct.pack("<II", 0, 4) + b"\0" * 4 + struct.pack("<II", 1, 4) + b"\0" * 4 + struct.pack("<II", 3, len(body)) + body
    out = parse_lightvrt(raw)
    assert list(out) == [1] and out[1].shape == (2, 4)


def test_camera_keys_accumulate_durations_to_reach_the_next_point():
    track = CameraTrack(points=[(39, (1, 2, 3)), (3, (4, 5, 6)), (2, (7, 8, 9))], targets=[(39, (0, 0, 0)), (5, (1, 1, 1))])
    keys = camera_keys(track)
    assert [k["t"] for k in keys["points"]] == [0, 39, 42]
    assert keys["duration"] == 44
    assert keys["targets"][1] == {"t": 39, "p": [1, 1, 1]}


def test_schedule_lines_opens_each_group_on_its_camera_segment():
    camera = {"points": [{"t": 0}, {"t": 39}, {"t": 42}]}
    spec = {"timing": {"groups": [{"segment": 0, "lines": [1, 2]}, {"segment": 2, "lines": [3]}], "lead": 0.5, "gap": 0.6}}
    voices = [{"duration": 2.0}, None, {"duration": 1.0}]
    lines = [Line(5, {}), Line(7, {}), Line(4, {})]
    assert schedule_lines(spec, camera, voices, lines) == [0.5, 3.1, 42.5]


def test_vertex_light_is_ambient_plus_sun_plus_baked_point_lights():
    light = {"ambient": 0xFF404040, "diffuse": 0xFF800000, "pointLight": 0xFF008000, "sunYaw": 0, "sunPitch": 90}
    raw = np.array([[0, 128, 0, 0], [0, 128, 255, 0]], np.uint8)
    up = np.array([[0, 0, 1.0], [0, 0, -1.0]])
    out = vertex_light(raw, light, up)
    assert np.allclose(out[0], [0.5 + 1.0, 0.5, 0.5])        # ambiante + soleil (normale vers le haut)
    assert np.allclose(out[1], [0.5, 0.5 + 1.0, 0.5])        # ambiante + ponctuelles (octet 2 = 255)
    assert encode_light(np.array([[2.0, 1.0, 0.0]])).tolist() == [[255, 128, 0, 255]]


def test_light_at_adds_nearby_point_lights():
    light = {"ambient": 0xFF000000, "pointLight": 0xFF808080}
    lights = [{"p": [0, 0, 1], "intensity": 2.0, "radius": 10.0, "attenuation": 1.0}]
    assert light_at([0, 0, 0], lights, light) == [1.0, 1.0, 1.0]
    assert light_at([50, 0, 0], lights, light) == [0.0, 0.0, 0.0]


def test_ground_z_finds_the_highest_surface_below_the_ceiling():
    floor = [[0, 0, 1], [10, 0, 1], [0, 10, 1]]
    roof = [[0, 0, 9], [10, 0, 9], [0, 10, 9]]
    solids = np.array([floor, roof], float)
    assert ground_z(solids, 2, 2, below=100) == 9
    assert ground_z(solids, 2, 2, below=5) == 1
    assert ground_z(solids, 20, 20, below=100) is None


def test_find_wave_matches_names_loops_and_ambience_presets():
    index = {"ac7lightninglp": [("SFX/World/World_AC7.bsb", 2, "AC7_Lightning_lp")],
             "demonicdronelp": [("SFX/Ambience/Ambience_Outdoor.bsb", 5, "demonic_drone_lp")],
             "ac9mainnm": [("SFX/Music/Music_Zone.fsb", 3, "AC9_Main_NM")]}
    assert find_wave("World/Zones/AC7/AC7_Lightning", index)[2] == "AC7_Lightning_lp"
    assert find_wave("Music/ZonesMusic/AC9_main", index)[2] == "AC9_Main_NM"
    assert find_wave("Ambience/OutdoorAmbience/AmbiencePresets/Demonic_AP", index)[2] == "demonic_drone_lp"
    assert find_wave("Nothing/Here", index) is None


def test_fsb5_stream_names_reads_the_name_table():
    names = [b"first\0", b"second\0"]
    table = struct.pack("<2I", 8, 8 + len(names[0])) + b"".join(names)
    header = b"FSB5" + struct.pack("<6I", 1, 2, 0, len(table), 0, 0) + b"\0" * (0x3C - 28)
    assert fsb5_stream_names(header + table) == ["first", "second"]


def test_face_yaw_turns_the_minus_y_forward_axis_to_the_target():
    assert math.isclose(face_yaw([0, 0, 0], [1, 0]), math.pi / 2, abs_tol=1e-4)
    assert MODEL_FORWARD == -math.pi / 2
