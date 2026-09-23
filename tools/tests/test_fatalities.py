"""Tests de la chaîne des fatalités : base compilée du client (`allods_packdb`), décodeurs
(`allods_visdb`), particules (`allods_particles`), interprète de scripts (`fatality_script`) et
règles de l'export (`extract_fatalities`).

Les tests synthétiques ne lisent aucun client ; ceux marqués `client` vérifient les décalages
sur les vraies données (client RU et arbre serveur 7.0) et sont sautés quand ils manquent.
"""
from __future__ import annotations

import math
import struct
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from tools import allods_visdb as vis
from tools.allods_packdb import PackDB, PakCatalog, vote_pak_codes
from tools.allods_particles import (Channel, Emitter, Particle, ParticleFile, encode_particles,
                                    parse_particles, sample, simplify, simplify_channel)
from tools.extract_fatalities import (_sound_key, bind_pose_positions, clean_animation,
                                      infer_texture_dims, reduce_keys, zone_light)
from tools.extract_menu_scene import JointTrack, Skeleton, SkeletalAnimation
from tools.fatality_script import flatten

CLIENT = Path("/mnt/h/MyGames/AllodsRU")
SERVER = Path("/mnt/f/ALLODS ONLINE SERVER/Allods 7.0/game/data")
client = pytest.mark.skipif(not (CLIENT / "data" / "Packs" / "BaseLocall_x64.pak").is_file()
                            or not SERVER.is_dir(), reason="client RU ou arbre serveur 7.0 absent")


# --- base compilée synthétique -----------------------------------------------------------------

def make_pack(types: list[str], data: bytes, relocs: list[tuple[int, int, int]],
              paths: dict[str, int] | None = None) -> bytes:
    """Fichier `pack.bin` décompressé minimal : entête, types, chemins, données, relocations."""
    out = bytearray(0x50)

    def put_selfptr(at: int, target: int, count: int) -> None:
        struct.pack_into("<II", out, at, target - at, count)

    # types : 16 octets par entrée (pointeur auto-relatif, longueur), noms ensuite
    table = len(out)
    out += bytes(16 * len(types))
    for i, name in enumerate(types):
        at = len(out)
        raw = f"struct NDb::{name}".encode() + b"\0"
        out += raw
        put_selfptr(table + 16 * i, at, len(raw))
    put_selfptr(0x28, table, len(types))
    # chemins : un seul seau
    paths = paths or {}
    bucket = len(out)
    out += bytes(8)
    entries = len(out)
    out += bytes(16 * len(paths))
    for k, (name, offset) in enumerate(paths.items()):
        rec = len(out)
        raw = name.encode() + b"\0"
        out += struct.pack("<II", 1, 0) + raw
        struct.pack_into("<IIQ", out, entries + 16 * k, rec - (entries + 16 * k), 8 + len(raw), offset)
    put_selfptr(bucket, entries, len(paths))
    put_selfptr(0x20, bucket, 1)
    # blocs
    while len(out) % 8:
        out.append(0)
    blocks = len(out)
    put_selfptr(0x40, blocks, 0)
    out += struct.pack("<IQ", 3, len(data)) + data
    out += struct.pack("<IQ", 4, len(relocs))
    for loc, kind, target in relocs:
        out += struct.pack("<QQ", loc | kind, target)
    return bytes(out)


def test_packdb_reads_types_paths_relocations():
    data = bytearray(256)
    struct.pack_into("<I", data, 0x20, 1234)
    data[0x80:0x86] = b"Hello\0"
    struct.pack_into("<I", data, 0x40 + 8, 5)            # taille du vecteur (poids faible de `dernier`)
    relocs = [(0x00, 4, 1), (0x10, 0, 0x60), (0x40, 3, 0x80), (0x60, 5, 0)]
    db = PackDB(make_pack(["Alpha", "Beta"], bytes(data), relocs, {"A/B.xdb": 0x00}))
    assert db.types == ["Alpha", "Beta"]
    assert db.paths == {"A/B.xdb": 0}
    assert db.vtype(0x00) == "Beta" and db.vtype(0x60) == "Alpha" and db.vtype(0x08) is None
    assert db.resources("Beta") == [0] and db.structs("Alpha") == [0x60]
    assert db.ptr(0x10) == 0x60 and db.ptr(0x18) is None
    assert db.vec(0x40) == (0x80, 5)
    assert db.string(0x40) == "Hello"
    assert db.u32(0x20) == 1234


def test_vote_pak_codes_matches_type_suffix():
    data = bytearray(0x200)
    # deux géométries codées (7, rang 1) et (7, rang 2)
    for base, rank in ((0x000, 1), (0x100, 2)):
        struct.pack_into("<I", data, base + 0x88, 7)
        struct.pack_into("<I", data, base + 0x90, rank)
    db = PackDB(make_pack(["Geometry", "ParticleAnimation", "SkeletalAnimation", "Texture"], bytes(data),
                          [(0x000, 4, 0), (0x100, 4, 0)]))
    names = {"A.pak": ["x.(Texture).bin", "a.(Geometry).bin", "b.(Geometry).bin"],
             "B.pak": ["y", "z.(Texture).bin", "w.(Texture).bin"]}
    codes = vote_pak_codes(db, names)
    assert codes == {7: "A.pak"}
    cat = PakCatalog(Path("."), names, codes)
    assert cat.name(db.binary_ref(0x100)) == "b.(Geometry).bin"


def test_orientation_enum_is_the_clients():
    # Valeurs relevées sur DummyWorldZed (WORLD_Z), StellaSmoke (BILLBOARD), Z_AXIS des fatalités.
    assert vis.ORIENTATION[3] == "WORLD_Z" and vis.ORIENTATION[6] == "Z_AXIS" and vis.ORIENTATION[7] == "BILLBOARD"


def test_read_action_decodes_lists_delays_and_fx():
    data = bytearray(0x400)
    lst, delay, fx, vot = 0x000, 0x100, 0x180, 0x300
    struct.pack_into("<I", data, lst + vis.LIST_PLAY, 0)               # en séquence
    struct.pack_into("<I", data, lst + vis.LIST_ELEMENTS + 8, 16)      # deux pointeurs
    data[lst + vis.LIST_STOP_WHILE] = 1
    struct.pack_into("<I", data, delay + vis.DELAY_TIME, 2500)
    struct.pack_into("<3f", data, fx + vis.FX_OFFSET, 0.0, 0.0, 0.3)
    struct.pack_into("<f", data, fx + vis.FX_SCALE, 3.12)
    struct.pack_into("<f", data, fx + vis.FX_LIFETIME, 11.6)
    relocs = [(lst, 5, 0), (lst + vis.LIST_ELEMENTS, 3, 0x200), (0x200, 0, delay), (0x208, 0, fx),
              (delay, 5, 1), (fx, 5, 2), (fx + vis.FX_VISOBJECT, 0, vot), (vot, 4, 3)]
    db = PackDB(make_pack(["VisActionList", "VisActionDelay", "CreatureIndependentFxAction", "VisObjectTemplate"],
                          bytes(data), sorted(relocs)))
    node = vis.read_action(db, lst)
    assert node["type"] == "VisActionList" and node["play"] == "InSequence"
    assert node["stopWhileWhenElementsEnded"] is True
    first, second = node["elements"]
    assert first == {"type": "VisActionDelay", "offset": delay, "time": 2.5}
    assert second["visObject"] == vot and math.isclose(second["scale"], 3.12, rel_tol=1e-6)
    assert np.allclose(second["offset"], [0, 0, 0.3]) and math.isclose(second["lifeTime"], 11.6, rel_tol=1e-6)


# --- particules ---------------------------------------------------------------------------------

def _particle_file(span: int) -> ParticleFile:
    grid = np.arange(span + 1, dtype=np.int32)
    ramp = np.linspace(0, 60000, span + 1)
    channels = {
        "position": Channel(grid, np.column_stack([ramp, ramp / 2, 65535 - ramp])),
        "size": Channel(grid, np.column_stack([ramp, ramp])),
        "rotation": Channel(grid, ramp[:, None] / 2),
        "color": Channel(grid, np.column_stack([np.full(span + 1, 255.0)] * 3 + [np.linspace(255, 0, span + 1)])),
        "frame": Channel(np.array([0, span // 2, span], np.int32), np.array([[0.0], [1.0], [2.0]])),
    }
    emitter = Emitter(np.array([-1.0, -2.0, 0.0]), np.array([1e-4, 2e-4, 3e-4]), np.array([0.1, 0.1]),
                      np.array([1e-5, 1e-5]), [Particle(5, span, channels)])
    return ParticleFile(3, 8, [emitter])


@pytest.mark.parametrize("span", [20, 300])      # grille 8 bits, puis 16 bits au-delà de 254
def test_particles_roundtrip_is_exact(span):
    original = _particle_file(span)
    blob = encode_particles(original)
    parsed = parse_particles(blob)
    assert parsed.textures == 3 and parsed.version == 8
    p0, p1 = original.emitters[0].particles[0], parsed.emitters[0].particles[0]
    assert (p1.birth, p1.span) == (p0.birth, p0.span)
    for name in p0.channels:
        assert np.array_equal(p0.channels[name].grid, p1.channels[name].grid)
        assert np.array_equal(np.round(p0.channels[name].values), p1.channels[name].values)
    assert np.allclose(parsed.emitters[0].pos_step, [1e-4, 2e-4, 3e-4])


def test_particle_simplification_keeps_ends_and_tolerance():
    grid = np.arange(0, 41, dtype=np.int32)
    values = np.column_stack([grid * 100.0 + 5 * np.sin(grid)])
    ch = simplify_channel(Channel(grid, values), 10.0)
    assert ch.grid[0] == 0 and ch.grid[-1] == 40 and len(ch.grid) < len(grid)
    for x in range(41):
        assert abs(sample(ch, x)[0] - values[x, 0]) <= 10.0 + 1e-9
    # image de texture : valeurs discrètes, aucune clé retirée
    pf = simplify(_particle_file(20))
    assert len(pf.emitters[0].particles[0].channels["frame"].grid) == 3


# --- interprète de scripts ------------------------------------------------------------------------

def _list(play, elements, play_while=None, stop_while=True):
    return {"type": "VisActionList", "play": play, "elements": elements, "playWhile": play_while,
            "stopWhileWhenElementsEnded": stop_while}


def test_flatten_sequences_delays_and_bounds():
    anim = {"type": "CreatureAnimationAction", "animations": [919], "speed": 0.5, "mode": "CLAMP"}
    fx = {"type": "CreatureIndependentFxAction", "visObject": 42, "lifeTime": 3.0, "scale": 1.3}
    script = _list("Simultaneously", [
        _list("InSequence", [_list("InSequence", [anim], {"type": "VisActionDelay", "time": 8.0}),
                             {"type": "CreatureAnimationAction", "animations": [1591], "speed": 1.0, "mode": "CLAMP"}]),
        _list("InSequence", [{"type": "VisActionDelay", "time": 7.5},
                             {"type": "CreatureSetTransparencyAction", "transparency": 0.0, "fadeMult": 1.0, "priority": 1}]),
        fx,
        {"type": "CreatureScaleAction", "scale": 1.3},
    ], {"type": "PredicateCreatureFlagAction", "flag": "FatalityVictim"})
    names = {919: "deathFatalityMage", 1591: "deathFatality"}
    tl = flatten(script, "KaniaMale", {"deathFatalityMage": 8.4, "deathFatality": 2.5}, names)
    # 8,4 s à vitesse 0,5 = 16,8 s, coupées à 8 s par le délai de la liste ; puis la pose finale
    assert [(s["anim"], s["t"], s["end"]) for s in tl.victim] == [("deathFatalityMage", 0.0, 8.0), ("deathFatality", 8.0, 10.5)]
    assert tl.alpha == [{"t": 7.5, "value": 0.0, "fadeMult": 1.0, "priority": 1}]
    assert tl.spawns[0]["vot"] == 42 and tl.spawns[0]["t"] == 0.0
    assert tl.scale == [{"t": 0.0, "scale": 1.3}]
    assert tl.end == 10.5


def test_flatten_stop_while_takes_the_shorter_of_bound_and_elements():
    short = {"type": "CreatureAnimationAction", "animations": [1], "speed": 1.0, "mode": "CLAMP"}
    after = {"type": "CreatureAnimationAction", "animations": [2], "speed": 1.0, "mode": "CLAMP"}
    bounded = _list("InSequence", [short], {"type": "VisActionDelay", "time": 8.0})
    tl = flatten(_list("InSequence", [bounded, after]), "X", {"a": 2.5, "b": 1.0}, {1: "a", 2: "b"})
    assert tl.victim[1]["t"] == 2.5                 # la liste s'arrête quand son élément finit
    loose = _list("InSequence", [short], {"type": "VisActionDelay", "time": 8.0}, stop_while=False)
    tl = flatten(_list("InSequence", [loose, after]), "X", {"a": 2.5, "b": 1.0}, {1: "a", 2: "b"})
    assert tl.victim[1]["t"] == 8.0


def test_flatten_character_predicates_select_race_variants():
    variant = lambda who, vot: _list("InSequence", [{"type": "CreatureIndependentFxAction", "visObject": vot}],
                                     {"type": "PredicateCreatureVisCharacterAction", "templates": [who]})
    script = _list("Simultaneously", [variant("AedFemale", 1), variant("KaniaMale", 2)])
    assert [s["vot"] for s in flatten(script, "KaniaMale", {}, {}).spawns] == [2]
    assert [s["vot"] for s in flatten(script, "AedFemale", {}, {}).spawns] == [1]


# --- règles de l'export -----------------------------------------------------------------------------

def test_reduce_keys_linear_and_constant():
    t = np.linspace(0, 1, 40)                  # moins que l'écart maximal entre deux clés
    assert list(reduce_keys(np.column_stack([t, 2 * t]), 1e-6)) == [0, 39]
    assert list(reduce_keys(np.ones((30, 3)), 1e-6)) == [0, 29]
    bumpy = np.column_stack([np.where(np.arange(50) == 25, 1.0, 0.0)])
    kept = reduce_keys(bumpy, 1e-3)
    assert 24 in kept and 25 in kept and 26 in kept


def test_sound_key_pairs_event_and_wave():
    assert _sound_key("FatalityUniversal") == _sound_key("fatality_universal")
    assert _sound_key("FatalityWarrior") != _sound_key("FatalityWarlock")


def test_infer_texture_dims_from_mip_chain():
    # DXT1 128 × 128, niveaux 2..5 (le .bin du client sans ses niveaux fins) : le dernier (4 × 4)
    # tient en un bloc de 8 octets, d'où le format ; le plus fin donne la taille
    mips = {k: bytes(max(1, (128 >> k) // 4) ** 2 * 8) for k in range(2, 6)}
    assert infer_texture_dims(mips) == [("DXT1", 128, 128)]


def _skeleton_one_joint(bind_t, inverse_identity: bool) -> Skeleton:
    local = np.zeros((1, 4, 3))
    local[0, :3] = np.eye(3)
    local[0, 3] = bind_t
    inverse = np.zeros((1, 4, 3))
    inverse[0, :3] = np.eye(3)
    inverse[0, 3] = 0 if inverse_identity else -np.asarray(bind_t)
    return Skeleton(["j"], [-1], local, inverse, [0])


def test_bind_pose_positions_places_joint_space_vertices():
    vertices = {"position": np.array([[0.0, 0.0, 1.0]], np.float32),
                "indices": np.array([[0, 255, 255, 255]], np.uint8), "weights": np.array([[255, 0, 0, 0]], np.uint8)}
    none = np.zeros(1, bool)
    # inverse de bind identité : le sommet est dans le repère de l'articulation (posée en z = 5)
    assert np.allclose(bind_pose_positions(vertices, _skeleton_one_joint([0, 0, 5], True), none), [[0, 0, 6]])
    # inverse réelle : le sommet est déjà dans le repère du modèle
    assert np.allclose(bind_pose_positions(vertices, _skeleton_one_joint([0, 0, 5], False), none), [[0, 0, 1]])
    # élément non skinné : inchangé
    assert np.allclose(bind_pose_positions(vertices, _skeleton_one_joint([0, 0, 5], True), np.ones(1, bool)), [[0, 0, 1]])


def test_clean_animation_drops_static_copies_of_the_bind():
    skeleton = _skeleton_one_joint([1, 2, 3], False)
    static = JointTrack("j", np.array([[1.0, 2.0, 3.0]]), np.array([[0.0, 0.0, 0.0, 1.0]]), False, np.array([1.0]))
    animation = SkeletalAnimation(30, 10, [static])
    assert clean_animation(skeleton, animation) == ["j"] and animation.tracks == []


def test_zone_light_reads_the_requested_hour(tmp_path):
    xml = """<ZoneLights><instantLights><Item><time>12</time><light><AmbientColor>5657187</AmbientColor>
    <DiffuseColor>8388608</DiffuseColor><FogColor>0</FogColor><FogStart>80</FogStart><FogEnd>700</FogEnd>
    <SunLightYaw>90</SunLightYaw><SunLightPitch>0</SunLightPitch></light></Item></instantLights></ZoneLights>"""
    (tmp_path / "z.xdb").write_text(xml)
    light = zone_light(tmp_path, "z.xdb", 12)
    assert light["ambient"] == [round(0x56 / 128, 4), round(0x52 / 128, 4), round(0x63 / 128, 4)]
    assert light["sun"] == [1.0, 0.0, 0.0]
    assert np.allclose(light["sunDirection"], [0, 1, 0], atol=1e-4)
    assert light["fog"] == {"color": [0.0, 0.0, 0.0], "near": 80.0, "far": 700.0}


# --- vraies données ----------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def real():
    from tools.allods_packdb import open_catalog, open_pack
    db = open_pack(CLIENT)
    return db, open_catalog(db, CLIENT)


def _geometry_by_name(db, cat, suffix):
    for off in db.resources("Geometry"):
        name = cat.name(db.binary_ref(off))
        if name and name.endswith(suffix):
            return off
    raise AssertionError(suffix)


@client
def test_real_geometry_matches_server_xdb(real):
    from tools.extract_menu_scene import parse_geometry_xdb
    db, cat = real
    for stem in ("FatalityWarrior", "Fatality_AuraWar"):
        geo = vis.read_geometry(db, cat, _geometry_by_name(db, cat, f"Fatality/{stem}.(Geometry).bin"))
        xdb = parse_geometry_xdb((SERVER / f"Spells/FX/Spells/Fatality/{stem}.(Geometry).xdb").read_text())
        assert geo.doc.layouts == xdb.layouts
        assert geo.doc.index_buffer_size == xdb.index_buffer_size
        assert len(geo.doc.elements) == len(xdb.elements)
        for a, b in zip(geo.doc.elements, xdb.elements):
            assert (a.name, a.ib0, a.ib1, a.vb0, a.vb1, a.skin_index) == (b.name, b.ib0, b.ib1, b.vb0, b.vb1, b.skin_index)
            assert (a.material.blend, a.material.transparent) == (b.material.blend, b.material.transparent)
            assert np.allclose(a.material.uv_scroll, b.material.uv_scroll)


@client
def test_real_fatalities_are_the_26_types(real):
    db, _ = real
    fatalities = vis.read_fatalities(db)
    assert [f.type for f in fatalities] == list(range(1, 27))
    bard = fatalities[0]
    assert math.isclose(bard.fade_start, 8.1, abs_tol=1e-5) and math.isclose(bard.spark_delay, 12.0)


@client
def test_real_particle_file_roundtrips_byte_for_byte(real):
    from tools.extract_menu_scene import BinSource, read_chunks
    db, cat = real
    bins = BinSource([], [str(CLIENT / "data" / "Packs" / "Spells_FX_Spells.Mini.pak")])
    raw = read_chunks(bins.get("Spells/FX/Spells/Fatality/FatalityWarrior_Fire.(ParticleAnimation).bin"))[0]
    pf = parse_particles(raw)
    assert len(pf.emitters) == 9 and pf.textures == 15
    again = parse_particles(encode_particles(pf))
    for e0, e1 in zip(pf.emitters, again.emitters):
        for p0, p1 in zip(e0.particles, e1.particles):
            for name in p0.channels:
                assert np.array_equal(p0.channels[name].values, p1.channels[name].values)


# --- personnages (tools/allods_characters.py) -------------------------------------------------

def _template(**kw):
    from tools.allods_characters import ArmorShape, CharacterTemplate, TextureRect, Variation, Variations, VisualItem
    dress = VisualItem(1, hidden={"unisex": ["face_0", "face_1", "hair_0", "hair_1", "torso_1"]})
    face = VisualItem(2, shapes={"unisex": [ArmorShape("face_0")]},
                      gendered={"patches": {"unisex": [TextureRect((0.0, 0.5, 0.0, 0.25), "face.bin")]}})
    hair = VisualItem(3, shapes={"unisex": [ArmorShape("hair_1", replacement="hair1.bin")]})
    under = VisualItem(4, gendered={"pants": {"female": [TextureRect((0.5, 1.0, 0.5, 0.625), "pants_f.bin")],
                                              "male": [TextureRect((0.5, 1.0, 0.5, 0.625), "pants_m.bin")]}})
    variation = Variation(additional=None, face=face, facial=None, hair=hair, hair_color=kw.get("hair_color", -1),
                          skin="mask.bin", skin_color=kw.get("skin_color", -1))
    return CharacterTemplate(offset=0, model="TestFemale", gender="female", visobject=0, geometry=0,
                             main_texture="skin.bin", default_dress=dress, underwear=under,
                             variations=Variations([], [], [], [], [], [], variation),
                             hair_colored=["hair_1"], special_hair_patch=[])


def test_resolve_appearance_hides_dress_geosets_and_shows_variation_shapes():
    from tools.allods_characters import resolve_appearance
    names = ["torso_0", "torso_1", "face_0", "face_1", "hair_0", "hair_1", "skirt_0"]
    textures = {n: "skin.bin" for n in names} | {"skirt_0": None}
    app = resolve_appearance(_template(hair_color=0xFF808080 - (1 << 32)), names, textures)
    # tenue par défaut : face_1, hair_0, torso_1 cachés ; la variation remontre face_0 et hair_1 ;
    # la jupe sans texture n'est pas dessinée
    assert app.visible == ["torso_0", "face_0", "hair_1"]
    assert app.replacements == {"hair_1": "hair1.bin"}
    assert app.tints["hair_1"] == pytest.approx((128 / 255,) * 3)
    # calques : visage, puis sous-vêtement du sexe du gabarit
    assert [p.texture for p in app.patches] == ["face.bin", "pants_f.bin"]


def test_bake_skin_counts_v_from_the_bottom_and_tints_under_the_mask():
    from PIL import Image
    from tools.allods_characters import Appearance, TextureRect, bake_skin
    base = Image.new("RGB", (8, 8), (200, 200, 200))
    patch = Image.new("RGBA", (4, 2), (255, 0, 0, 255))
    mask = Image.new("RGBA", (8, 8), (0, 0, 0, 255))
    mask.paste((0, 0, 0, 0), (0, 0, 8, 4))       # moitié haute hors masque
    app = Appearance(visible=[], replacements={}, tints={}, patches=[TextureRect((0.0, 0.5, 0.0, 0.25), "p")],
                     skin_texture="skin", skin_mask="mask", skin_color=0xFF808080 - (1 << 32), hair_color=-1)
    img = bake_skin(base, app, lambda name: patch, mask, 8)
    px = img.load()
    assert px[0, 7] == (255, 0, 0) and px[0, 6] == (255, 0, 0)   # y 0 → 0,25 = bas de l'image
    assert px[6, 6] == (100, 100, 100)                            # teinte ×128/255 sous le masque
    assert px[6, 1] == (200, 200, 200)                            # hors masque : intact


@client
def test_real_character_template_matches_server_xdb(real):
    from tools.allods_characters import find_character_template, read_character_template
    db, cat = real
    off = find_character_template(db, cat, "HadaganFemale", "Hadagan_female")
    tpl = read_character_template(db, cat, off)
    assert tpl.gender == "female" and tpl.main_texture.endswith("HadaganFemaleSkin00.(Texture).bin")
    assert tpl.hair_colored[:2] == ["hair_special", "hair_1"]
    hidden = tpl.default_dress.hidden_for("female")
    assert {"torso_1", "hair_0", "face_20", "skeleton", "skull"} <= set(hidden)
    default = tpl.variations.default
    assert [s.shape for s in default.face.shapes_for("female")] == ["face_0"]
    rects = [(p.rect, p.texture.split("/")[-1]) for p in tpl.underwear.patches_for("female")]
    # `Underwear_HadaganFemale.(VisualItem).xdb` : soutien-gorge puis culotte (deux rectangles)
    assert rects[0][1] == "Underwear_A_02HadaganRed_Bra_TU_F_D.(Texture).bin"
    assert rects[-1] == ((0.5, 1.0, 0.5, 0.625), "Underwear_A_02HadaganRed_LU_F_D.(Texture).bin")


def test_flatten_records_channel_rays():
    ray = {"type": "CreatureChannelDirectAction", "visObject": 7, "fadeIn": 0.2, "fadeOut": 0.1, "length": 10.0,
           "velocity": 2.0, "start": {"locator": "Global", "shift": [0, 0, 1]}, "end": {"locator": "Global", "shift": [0, 0, 1]}}
    script = _list("InSequence", [{"type": "VisActionDelay", "time": 1.2}, ray], {"type": "VisActionDelay", "time": 3.5})
    tl = flatten(script, "KaniaMale", {}, {})
    assert tl.channels == [{"t": 1.2, "until": 3.5, "vot": 7, "fadeIn": 0.2, "fadeOut": 0.1, "length": 10.0,
                            "velocity": 2.0, "start": ray["start"], "end": ray["end"]}]
