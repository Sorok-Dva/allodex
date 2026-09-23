"""Tests des cinématiques moteur (sans client : données synthétiques)."""
import math
from types import SimpleNamespace

import numpy as np

from tools.allods_vis17 import CameraTrack, region_origin
from tools.extract_cinematics import Line
from tools.extract_engine_cutscene import (
    MODEL_FORWARD, _variant_family, camera_keys, ground_z, local_light, schedule_lines, vertex_light,
)


def test_region_origin_uses_256_m_regions_offset_by_block():
    assert region_origin("Maps/X/000_000/0_0_MapRegion.xdb") == (0.0, 0.0)
    assert region_origin("Maps/X/000_000/1_0_MapRegion.xdb") == (256.0, 0.0)
    assert region_origin("Maps/X/040_050/2_3_MapRegion.xdb") == (42 * 256.0, 53 * 256.0)


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


def test_vertex_light_adds_the_zone_glow_scaled_by_the_baked_byte():
    light = {"ambient": 0xFF101010, "selfIllum": 0xFF804000}
    raw = np.array([[0, 128, 0, 0], [255, 255, 255, 0]], np.uint8)
    out = vertex_light(raw, light)
    assert out[0].tolist() == [32, 32, 32, 255]            # ambiante × 2
    assert out[1].tolist() == [255, 160, 32, 255]          # + glow × 2, borné


def test_ground_z_finds_the_highest_surface_below_the_ceiling():
    floor = [[0, 0, 1], [10, 0, 1], [0, 10, 1]]
    roof = [[0, 0, 9], [10, 0, 9], [0, 10, 9]]
    solids = np.array([floor, roof], float)
    assert ground_z(solids, 2, 2, below=100) == 9
    assert ground_z(solids, 2, 2, below=5) == 1
    assert ground_z(solids, 20, 20, below=100) is None


def test_local_light_averages_nearby_decor_vertices():
    samples = np.array([[0, 0, 0, 1, 0, 0], [1, 0, 0, 0, 1, 0], [100, 0, 0, 0, 0, 1]], float)
    assert local_light(samples, [0, 0, 0]) == [0.5, 0.5, 0.0]
    assert local_light(samples, [50, 50, 0]) is None


def test_variant_families_and_forward_axis():
    assert _variant_family("hair_8") == "hair"
    assert _variant_family("hair_special") == "hair"
    assert _variant_family("torso") is None
    # un modèle tourné vers −Y regarde vers +X quand son lacet vaut atan2(0, 1) − MODEL_FORWARD
    assert math.isclose(math.atan2(0, 1) - MODEL_FORWARD, math.pi / 2)
