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


def test_xdb70_trigger_zone_takes_the_if_branch_and_records_states_fx_and_exit(tmp_path):
    (tmp_path / "Boom.(ClientData).xdb").write_text("""<ClientData><customData type="CreatureVisActionData">
      <action type="CreatureFixedPointProjectileAction"><projectileFx href="/P.(VisObjectTemplate).xdb" />
      <explosionFx href="/E.(VisObjectTemplate).xdb" /><theGe>5</theGe>
      <lines><Item><throwDuration>3000</throwDuration><endPointIndex>1</endPointIndex></Item></lines></action>
    </customData></ClientData>""")
    (tmp_path / "Snd.(ClientData).xdb").write_text("""<ClientData><customData type="CreatureVisActionData">
      <action type="Sound2DAction"><sound><project href="/SFX/World/World.(FMODProject).xdb" />
      <name>World/Zones/IE1/IE1_ShipDestroy</name></sound></action></customData></ClientData>""")

    def spawn(script: str, inner: str) -> str:
        return (f"<Item type=\"gameMechanics.elements.impacts.ImpactsToSingleSpawn\"><spawn><scriptID>{script}</scriptID>"
                f"</spawn><impacts>{inner}</impacts></Item>")
    state = '<Item type="gameMechanics.elements.impacts.ImpactSetVisualState"><visualState>{}</visualState></Item>'
    (tmp_path / "Z.(ScriptZone).xdb").write_text(f"""<ScriptZone><impactsIn>
      <Item type="gameMechanics.elements.impacts.ImpactIfTarget"><impactsIf>
        <Item type="gameMechanics.elements.impacts.ImpactsDeferred"><delay>2000</delay><impacts>
          <Item type="gameMechanics.elements.impacts.ImpactClientData"><data href="Boom.(ClientData).xdb" />
            <locators><Item><scriptID>A</scriptID></Item><Item><scriptID>B</scriptID></Item></locators></Item>
          <Item type="gameMechanics.elements.impacts.ImpactClientDataParams"><data href="Snd.(ClientData).xdb" /></Item>
          {spawn('Ship', state.format(2))}
        </impacts></Item></impactsIf>
        <impactsElse>{spawn('No', state.format(9))}</impactsElse></Item>
      {spawn('Squid', '<Item type="gameMechanics.elements.impacts.GoThroughPath"><path><Item><scriptID>P1</scriptID></Item></path></Item>'
             '<Item type="gameMechanics.elements.impacts.ImpactsDeferred"><delay>4000</delay><impacts>'
             '<Item type="gameMechanics.elements.impacts.Disintegrate" /></impacts></Item>')}
      <Item type="gameMechanics.elements.impacts.ImpactsDeferred"><delay>6000</delay><impacts>
        <Item type="gameMechanics.elements.impacts.ImpactTeleport" /></impacts></Item>
    </impactsIn></ScriptZone>""")
    tl = cutscene_xdb70.simulate(tmp_path, trigger="Z.(ScriptZone).xdb")
    assert tl.states == [{"t": 2.0, "spawn": "Ship", "state": 2}]
    (fx,) = tl.fx
    assert fx["locators"] == ["A", "B"] and fx["throw"] == 3.0 and fx["end"] == 1
    assert fx["explosion"] == "E.(VisObjectTemplate).xdb"
    assert tl.sfx[0]["name"] == "World/Zones/IE1/IE1_ShipDestroy" and not tl.lines
    assert tl.spawn_moves == {"Squid": [{"t": 0.0, "locator": "P1"}]} and tl.spawn_until == {"Squid": 4.0}
    assert tl.exit == 6.0 and tl.duration == 6.0


def test_xdb70_ability_trigger_reads_only_the_named_effect():
    import xml.etree.ElementTree as ET
    doc = ET.fromstring("""<AbilityResource><effects>
      <Item type="gameMechanics.elements.effects.HealthTrigger"><impactsOn><Item type="a.X" /></impactsOn></Item>
      <Item type="gameMechanics.elements.effects.CombatStateTrigger"><impactsOn><Item type="a.Y" /></impactsOn></Item>
    </effects></AbilityResource>""")
    assert [i.get("type") for i in cutscene_xdb70.trigger_impacts(doc, "HealthTrigger")] == ["a.X"]


def test_state_windows_start_from_the_manifest_state():
    from tools.extract_engine_cutscene import state_windows
    w = state_windows(1, [{"t": 0.0, "state": 2}, {"t": 11.0, "state": 3}], 14.0)
    assert w == [(-1e6, 0.0, 1), (0.0, 11.0, 2), (11.0, 14.0, 3)]


def test_read_zone_light_reads_point_light_after_the_constant_field():
    """Élément `Ferris4_Base` : `+0x48` vaut −1, `PointLightColor` 12362130 en `+0x4C` (7.0)."""
    from tools.allods_scenes import ZONE_LIGHTS, read_zone_light
    raw = bytearray(0x200)
    e = 0x100
    for off, value in ((0x24, 0xFF655045), (0x48, 0xFFFFFFFF), (0x4C, 12362130), (0x50, 2024878104), (0x54, 9259293)):
        struct.pack_into("<I", raw, e + off, value)

    class Db:
        def resources(self, kind):
            return [0]

        def elements(self, loc, stride):
            return [e] if loc == ZONE_LIGHTS else []

        def ptr(self, loc):
            return None

        def u32(self, off):
            return struct.unpack_from("<I", raw, off)[0]

        def f32(self, off):
            return struct.unpack_from("<f", raw, off)[0]
    light = read_zone_light(Db())
    assert light["pointLight"] == 12362130 and light["selfIllum"] == 2024878104 and light["specular"] == 9259293


def test_find_wave_takes_the_first_recorded_variant():
    index = {"15amanda04v2patch403": [("SFX/Voice/Voice_IL1_3D_rus.bsb", 40, "15_amanda_04_v2_patch403")],
             "15amanda04v1patch403": [("SFX/Voice/Voice_IL1_3D_rus.bsb", 39, "15_amanda_04_v1_patch403")],
             "18amanda07patch403": [("SFX/Voice/Voice_IL1_3D_rus.bsb", 48, "18_Amanda_07_patch403")]}
    assert find_wave("IL1/15_Amanda_04", index, "SFX/Voice/")[2] == "15_amanda_04_v1_patch403"
    assert find_wave("IL1/18_Amanda_07", index, "SFX/Voice/")[1] == 48
    assert find_wave("IL1/15_Amanda_0", index) is None


def _league_tree(tmp_path):
    """Quête qui pose l'état 1 d'une stèle (1 s) puis 2 (61 s), fait courir son donneur et lui donne une
    bulle, tue un PNJ, et n'emprunte que la branche `impactsIf` d'un `ImpactIfTarget`."""
    (tmp_path / "Maps" / "M" / "000_000").mkdir(parents=True)
    (tmp_path / "Maps" / "M" / "000_000" / "0_0_ServerObjects.xdb").write_text("""<PatchObjects><objects>
      <Item type="gameMechanics.map.Locator"><scriptID>Far</scriptID><position x="10" y="0" z="0" /><yaw>0</yaw></Item>
    </objects></PatchObjects>""")
    (tmp_path / "Maps" / "M" / "Fight.xdb").write_text(
        "<GameViewScene><place><x>10</x><y>20</y><z>3</z></place><mobs><Item><scriptID>A</scriptID></Item></mobs></GameViewScene>")
    (tmp_path / "Line.(ClientData).xdb").write_text(
        '<ClientData><customData type="InterfaceAction"><sysId>ENUM_SHOW_BUBBLE</sysId><text href="Line.txt" /></customData></ClientData>')
    (tmp_path / "Line.txt").write_bytes("Портал открыт!".encode("utf-16"))
    (tmp_path / "M.(TextMessage).xdb").write_text('<TextMessage><Text href="Line.txt" /></TextMessage>')
    (tmp_path / "China.(TextMessage).xdb").write_text('<TextMessage><Text href="Line.txt" /></TextMessage>')

    def spawn(s, body):
        return (f'<Item type="x.ImpactsToSingleSpawn"><spawn><scriptID>{s}</scriptID><map href="/Maps/M/MapResource.xdb" />'
                f'</spawn><impacts>{body}</impacts></Item>')
    state = '<Item type="x.ImpactSetVisualState"><visualState>{}</visualState></Item>'
    (tmp_path / "Q.xdb").write_text(f"""<QuestResource><startImpacts>
      <Item type="x.ImpactsDeferred"><delay>1000</delay><impacts>{spawn('Dev1', state.format(1) +
        '<Item type="x.DeviceImpactsDeferred"><delay>60000</delay><impacts>' + state.format(2) + '</impacts></Item>')}</impacts></Item>
      <Item type="x.ImpactsToInterlocutor"><impacts>
        <Item type="x.GoThroughPath"><runningMode>true</runningMode><path><Item><scriptID>Far</scriptID></Item></path></Item>
        <Item type="x.ImpactsDeferred"><delay>2000</delay><impacts>
          <Item type="x.ImpactClientDataParams"><data href="Line.(ClientData).xdb" /></Item></impacts></Item></impacts></Item>
      <Item type="x.ImpactIfTarget"><impactsIf><Item type="x.ImpactMobChat"><msg href="M.(TextMessage).xdb" /></Item></impactsIf>
        <impactsElse><Item type="x.ImpactMobChat"><msg href="China.(TextMessage).xdb" /></Item></impactsElse></Item>
      <Item type="x.ImpactsDeferred"><delay>3000</delay><impacts>{spawn('Mage', '<Item type="x.ImpactKill" />')}</impacts></Item>
    </startImpacts></QuestResource>""")


def test_xdb70_quest_start_impacts_set_states_moves_kills_and_bubbles(tmp_path):
    _league_tree(tmp_path)
    tl = cutscene_xdb70.simulate(tmp_path, trigger="Q.xdb", trigger_tag="startImpacts", until_last=True)
    assert tl.states == [{"t": 1.0, "spawn": "Dev1", "state": 1}, {"t": 61.0, "spawn": "Dev1", "state": 2}]
    assert tl.spawn_moves == {"interlocutor": [{"t": 0.0, "locator": "Far", "run": True}]}
    assert tl.kills == {"Mage": 3.0} and tl.duration == 600.0          # borné par l'extraction
    (line,) = tl.lines
    assert line["bubble"] == "Портал открыт!" and line["t"] == 2.0 and line["speaker"] == "interlocutor"
    assert [c["message"] for c in tl.chats] == ["M.(TextMessage).xdb"]       # `impactsIf` seulement
    assert cutscene_xdb70.read_game_scene(tmp_path, "Maps/M/Fight.xdb") == {"place": [10.0, 20.0, 3.0], "mobs": ["A"]}


def test_merge_bubbles_gives_a_voice_its_bubble_and_drops_twin_chats():
    from tools.extract_engine_cutscene import merge_bubbles
    base = {"ru": "", "animations": [], "delay_ms": 0}
    lines = [{**base, "t": 12.0, "speaker": "elf", "voice": "IL1/15_Amanda_04", "clientdata": "15_Elf01"},
             {**base, "t": 12.0, "speaker": "elf", "voice": None, "bubble": "Портал открыт!", "clientdata": "15_Elf01_Bubble"}]
    chats = [{"t": 12.0, "speaker": "elf", "ru": "Портал открыт!", "message": "Elf.(TextMessage)"},
             {"t": 20.0, "speaker": "elf", "ru": "Прыгай!", "message": "Jump.(TextMessage)"}]
    out = merge_bubbles(lines, chats)
    assert [(l["t"], l["voice"], l.get("bubble")) for l in out] == [
        (12.0, "IL1/15_Amanda_04", "Портал открыт!"), (20.0, None, "Прыгай!")]
