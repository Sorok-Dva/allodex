"""Tests des cinématiques moteur (sans client : données synthétiques)."""
import math
import struct

import numpy as np

from types import SimpleNamespace

from tools import cutscene_xdb70
from tools.allods_fx import fsb5_stream_names
from tools.allods_scenes import CameraTrack, PlacedObject, euler_zyx, parse_lightvrt, region_origin
from tools.extract_engine_cutscene import (
    MODEL_FORWARD, camera_keys, encode_light, face_yaw, find_wave, ground_z, light_at, schedule_lines, vertex_light,
)
from tools.extract_menu_scene import apply_vertex_offsets


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
    lines = [{"duration": 5}, {"duration": 7}, {"duration": 4}]
    assert schedule_lines(spec, camera, voices, lines) == [0.5, 3.1, 42.5]


def test_vertex_light_is_ambient_plus_sun_plus_baked_point_lights():
    light = {"ambient": 0xFF404040, "ambientFactor": 0.5, "diffuse": 0xFF800000, "pointLight": 0xFF008000,
             "sunYaw": 0, "sunPitch": 90}
    raw = np.array([[255, 255, 0, 0], [255, 255, 255, 0], [0, 128, 0, 0]], np.uint8)
    up = np.array([[0, 0, 1.0], [0, 0, -1.0], [0, 0, 1.0]])
    out = vertex_light(raw, light, up)
    assert np.allclose(out[0], [0.5 + 1.0, 0.5, 0.5])        # ciel dégagé + soleil au soleil
    assert np.allclose(out[1], [0.5, 0.5 + 1.0, 0.5])        # ciel dégagé + ponctuelles (octet 2 = 255)
    assert np.allclose(out[2], [0.25, 0.25, 0.25])           # ciel caché, à l'ombre : moitié de l'ambiante
    assert encode_light(np.array([[2.0, 1.0, 0.0]])).tolist() == [[255, 128, 0, 255]]


def test_light_at_adds_nearby_point_lights():
    light = {"ambient": 0xFF000000, "pointLight": 0xFF808080}
    lights = [{"p": [0, 0, 1], "intensity": 2.0, "radius": 10.0, "attenuation": 1.0}]
    assert light_at([0, 0, 0], lights, light) == [1.0, 1.0, 1.0]
    assert light_at([50, 0, 0], lights, light) == [0.0, 0.0, 0.0]
    dark = lights + [{"p": [0, 0, 1], "intensity": -100.0, "radius": 10.0, "attenuation": 0.0}]
    assert light_at([0, 0, 0], dark, light) == [0.0, 0.0, 0.0]     # lumière négative : bornée à 0


def test_apply_vertex_offsets_rebases_16_bit_indices_once_per_range():
    elements = [SimpleNamespace(ib0=0, ib1=3, vertex_offset=0), SimpleNamespace(ib0=3, ib1=6, vertex_offset=65536),
                SimpleNamespace(ib0=3, ib1=6, vertex_offset=65536)]
    indices = np.array([0, 1, 2, 0, 1, 2], np.uint32)
    assert apply_vertex_offsets(indices, elements) == 1
    assert indices.tolist() == [0, 1, 2, 65536, 65537, 65538]


def test_placed_object_rotation_is_yaw_pitch_roll_zyx():
    obj = PlacedObject("r", 0, (0, 0, 0), (0.0, math.pi / 2, 0.0, math.pi / 2), 1.0, None)
    assert obj.tilt == (0.0, math.pi / 2)
    # tangage 90° autour de Y (x → −z), puis lacet 90° autour de Z (y → −x)
    assert np.allclose(obj.matrix() @ [1, 0, 0], [0, 0, -1])
    assert np.allclose(obj.matrix() @ [0, 1, 0], [-1, 0, 0])
    assert np.allclose(euler_zyx(0, 0, 0.3), euler_zyx(0, 0, 0.3).T.T)
    assert np.allclose(euler_zyx(0.2, 0, 0) @ euler_zyx(-0.2, 0, 0), np.eye(3))


def test_xdb70_track_durations_are_weights_spread_over_the_buff():
    src = [(12, (0, 0, 0)), (10, (1, 0, 0)), (99, (2, 0, 0))]
    assert [k["t"] for k in cutscene_xdb70.track_keys(src, 3.0, 11.0)] == [3.0, 9.0, 14.0]
    assert [k["t"] for k in cutscene_xdb70.track_keys(src, 0.0, None)] == [0.0, 12.0, 22.0]


def test_xdb70_camera_keys_cut_to_the_next_shot():
    shots = [{"t": 0.0, "duration": 10.0, "points": [(1, (0, 0, 0)), (1, (10, 0, 0))], "targets": [(1, (0, 0, 0))]},
             {"t": 5.0, "duration": 5.0, "points": [(1, (50, 0, 0))], "targets": [(1, (9, 9, 9))]}]
    keys = cutscene_xdb70.camera_keys(shots)
    assert [k["t"] for k in keys["points"]] == [0.0, 4.999, 5.0, 9.999]   # dernier plan tenu jusqu’à sa fin
    assert keys["points"][1]["p"] == [5.0, 0, 0]              # position interpolée à l'instant de la coupe
    assert keys["targets"][-2:] == [{"t": 5.0, "p": [9, 9, 9]}, {"t": 9.999, "p": [9, 9, 9]}]


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


def test_grouped_wave_uses_the_bank_named_after_the_event_group():
    from tools.extract_engine_cutscene import grouped_wave
    index = {"rysina01": [("SFX/Voice/Voice_FerrisRaid602Portal_rus.bsb", 4, "Rysina01"),
                          ("SFX/Voice/Voice_FerrisRaid602Pre_rus.bsb", 3, "Rysina01")]}
    assert grouped_wave("FerrisRaid602/FR_PreRaidRysina01", index)[0].endswith("602Pre_rus.bsb")
    assert grouped_wave("FerrisRaid602/FR_PortalRysina01", index)[0].endswith("602Portal_rus.bsb")
    assert grouped_wave("Other/Rysina01", index) is None


def test_voice_speaker_matches_present_summons_and_aliases():
    from tools.extract_engine_cutscene import voice_speaker
    summoned = {"summon1": {"voice_key": "rysina", "presence": [[9, 29]]},
                "summon3": {"voice_key": "colossus", "presence": [[20, 37]]}}
    spec = {"speakers": {"Vayatel": "colossus"}}
    assert voice_speaker({"voice": "FerrisRaid602/FR_PreRaidRysina01", "t": 12}, summoned, spec) == "summon1"
    assert voice_speaker({"voice": "FerrisRaid602/FR_PreRaidVayatel01", "t": 28}, summoned, spec) == "summon3"
    assert voice_speaker({"voice": "FerrisRaid602/FR_PreRaidRysina03", "t": 40}, summoned, spec) is None


def test_xdb70_summons_walk_to_locators_and_vanish(tmp_path):
    (tmp_path / "Mobs").mkdir()
    (tmp_path / "Mobs" / "Rysina_CutScene.(MobWorld).xdb").write_text(
        "<MobWorld><walkSpeed>3</walkSpeed><visMob href=\"/Characters/Elf_female/V.(VisualMob).xdb\" /></MobWorld>")
    locator = lambda s: f"<locator><scriptID>{s}</scriptID><map href=\"/Maps/Ferris4/MapResource.xdb\" /></locator>"  # noqa: E731
    (tmp_path / "Start.(BuffResource).xdb").write_text(f"""<BuffResource><duration>10000</duration><effects>
      <Item type="gameMechanics.elements.effects.Switch"><impactsOn>
        <Item type="gameMechanics.elements.impacts.ImpactSummon">
          <destination type="x.DestinationLocator">{locator('A')}<yaw type="x.AngleDegrees"><value>90</value></yaw></destination>
          <impacts><Item type="gameMechanics.elements.impacts.ImpactsDeferred"><delay>2000</delay><impacts>
            <Item type="gameMechanics.elements.impacts.ImpactGoTo"><destination type="x.DestinationLocator">{locator('B')}</destination></Item>
          </impacts></Item></impacts>
          <object href="/Mobs/Rysina_CutScene.(MobWorld).xdb" />
        </Item></impactsOn></Item>
      <Item type="gameMechanics.elements.effects.EffectOnBuffTimeout"><impacts>
        <Item type="gameMechanics.elements.impacts.ImpactClientData"><data href="Line.(ClientData).xdb" /></Item>
      </impacts></Item>
    </effects></BuffResource>""")
    tl = cutscene_xdb70.simulate(tmp_path, "Start.(BuffResource).xdb")
    (summon,) = tl.summons
    assert summon["locator"] == "A" and math.isclose(summon["yaw"], math.pi / 2)
    assert summon["moves"] == [{"t": 2.0, "locator": "B"}] and summon["walkSpeed"] == 3
    assert summon["visual"] == "Characters/Elf_female/V.(VisualMob).xdb" and summon["until"] == 10.0
    assert tl.maps == {"Ferris4"} and {"A", "B"} <= tl.scripts


def test_xdb70_blank_shots_leave_the_previous_view():
    shots = [{"t": 0.0, "duration": 5.0, "points": [(1, (0, 0, 0))], "targets": [(1, (0, 0, 0))]},
             {"t": 5.0, "duration": 5.0, "points": [(1, (1, 2, 3))], "targets": [(1, (4, 5, 6))]}]
    keys = cutscene_xdb70.camera_keys(shots)
    assert keys["points"][0] == {"t": 0.0, "p": [1, 2, 3]} and keys["points"][1]["t"] == 5.0


def test_light_decor_keeps_the_scene_circle_and_lights_with_its_weather():
    from tools.extract_engine_cutscene import light_decor
    loaded = SimpleNamespace(vertices={"normal": np.array([[0, 0, 1.0], [0, 0, 1.0]])})
    decor = {"geometries": {7: loaded}, "instances": [
        {"vot": "A", "p": [0, 0, 0], "yaw": 0, "_geo": 7, "_m": np.eye(3), "_raw": np.array([[0, 0, 255, 0]] * 2, np.uint8)},
        {"vot": "B", "p": [500, 0, 0], "yaw": 0, "_geo": 7, "_m": np.eye(3)}]}
    light = {"ambient": 0xFF000000, "pointLight": 0xFF808080, "diffuse": 0xFF000000}
    instances, blob = light_decor(decor, light, [0, 0], 150)
    assert [i["vot"] for i in instances] == ["A"] and instances[0]["light"] == [0, 2]
    assert not any(k.startswith("_") for k in instances[0]) and len(blob) == 8


def test_rebase_objects_points_particle_files_to_the_map_folder():
    from tools.extract_engine_cutscene import map_prefix, rebase_objects
    objects = {"Fx": {"particles": {"file": "particles/Fx.bin"}}, "Mesh": {"scale": 1}}
    out = rebase_objects(objects, map_prefix("Ferris4"))
    assert out["Fx"]["particles"]["file"] == "../maps/Ferris4/particles/Fx.bin"
    assert objects["Fx"]["particles"]["file"] == "particles/Fx.bin"      # l'original n'est pas touché


def test_xdb70_spawn_tables_become_present_actors_walking_paths(tmp_path):
    (tmp_path / "Mobs").mkdir()
    (tmp_path / "Mobs" / "Fireman.(MobWorld).xdb").write_text("<MobWorld><walkSpeed>4</walkSpeed></MobWorld>")
    (tmp_path / "T.(SpawnTable).xdb").write_text(
        "<SpawnTable><singles><Item><object href=\"/Mobs/Fireman.(MobWorld).xdb\" /></Item></singles></SpawnTable>")
    (tmp_path / "S.(BuffResource).xdb").write_text("""<BuffResource><duration>5000</duration><effects>
      <Item type="gameMechanics.elements.effects.Switch"><impactsOn>
        <Item type="gameMechanics.elements.impacts.ImpactFindSpawnTable">
          <impacts><Item type="gameMechanics.elements.impacts.GoThroughPath"><path>
            <Item><scriptID>p1</scriptID><map href="/Maps/Ferris4/inst2_MapResource.(MapResource).xdb" /></Item>
            <Item><scriptID>p2</scriptID></Item></path></Item></impacts>
          <spawnResource href="T.(SpawnTable).xdb" />
        </Item></impactsOn></Item></effects></BuffResource>""")
    tl = cutscene_xdb70.simulate(tmp_path, "S.(BuffResource).xdb")
    (actor,) = tl.summons
    assert actor["id"] == "table:T.(SpawnTable).xdb" and actor["t"] == 0.0 and actor["walkSpeed"] == 4
    assert [m["locator"] for m in actor["moves"]] == ["p1", "p2"] and tl.maps == {"Ferris4"}


def test_packs_path_falls_back_to_the_real_packs_folder(tmp_path):
    from tools.allods_packdb import packs_path
    (tmp_path / "data" / "Packs.adc-real").mkdir(parents=True)
    (tmp_path / "data" / "Packs.adc-real" / "x.pak").write_bytes(b"")
    assert packs_path(tmp_path / "data" / "Packs" / "x.pak") == tmp_path / "data" / "Packs.adc-real" / "x.pak"


def test_gameview_placement_reads_double_xy_float_yaw_double_z():
    from tools.extract_engine_cutscene import _placement
    raw = struct.pack("<2dfxxxxd", 10967.005283, 11125.761637, 1.57, 49.066845)

    class Db:
        data = 0

        def __init__(self, raw):
            self.raw = raw

        def f32(self, off):
            return struct.unpack_from("<f", self.raw, off)[0]
    pos, yaw = _placement(Db(raw), 0)
    assert pos == [10967.0053, 11125.7616, 49.0668] and abs(yaw - 1.57) < 1e-6


def test_animation_file_falls_back_to_the_base_model():
    from tools.extract_engine_cutscene import animation_file
    bins = SimpleNamespace(_pak_index=lambda: {"Characters/Kania_male/Animations/KaniaMale.Special08.(SkeletalAnimation).bin": 0})
    name = animation_file(bins, "Characters/Kania_male/KaniaMale_CutScene.(Geometry).bin", "Special08")
    assert name == "Characters/Kania_male/Animations/KaniaMale.Special08.(SkeletalAnimation).bin"


def test_camera_moves_cut_each_group_at_the_next_one():
    from tools.extract_engine_cutscene import CAMMOVE_STRIDE, camera_moves

    class Db:
        """Deux groupes (délais 2 et 4 s), le premier de deux mouvements de 3 s."""
        data = 0

        def __init__(self):
            self.raw = bytearray(4096)
            self.groups = [100, 148]
            self.moves = {100: [1000, 1000 + CAMMOVE_STRIDE], 148: [2000]}
            for g, delay in zip(self.groups, (2.0, 4.0)):
                struct.pack_into("<f", self.raw, g + 4, delay)
            for i, m in enumerate([1000, 1000 + CAMMOVE_STRIDE, 2000]):
                struct.pack_into("<2d", self.raw, m + 0x18, 10.0 * i, 1.0)
                struct.pack_into("<d", self.raw, m + 0x30, 5.0)
                struct.pack_into("<f", self.raw, m + 0x6C, 3.0)

        def elements(self, loc, stride):
            return self.groups if loc == 0x48 else self.moves[loc - 8]

        def f32(self, off):
            return struct.unpack_from("<f", self.raw, off)[0]
    keys = camera_moves(Db(), 0)
    assert [k["t"] for k in keys] == [2.0, 3.999, 4.0]
    assert keys[1]["p"] == [10.0, 1.0, 5.0] and keys[2]["p"] == [20.0, 1.0, 5.0]


def test_lightmap_uv_skips_the_two_texel_border_and_flips_y():
    from tools.extract_engine_cutscene import lightmap_uv
    pts = np.array([[0.0, 0.0, 5.0], [256.0, 256.0, 5.0], [128.0, 128.0, 5.0]])
    uv = lightmap_uv(pts, (1, 0), 2) * 2 * 512          # en texels de l'atlas (deux cases de 512)
    # x = 0 au bord des texels 1-2 de la case (512 + 2), x = 256 à celui des texels 509-510 ; y retourné
    assert np.allclose(uv[0], [514, 510]) and np.allclose(uv[1], [1022, 2]) and np.allclose(uv[2], [768, 256])
