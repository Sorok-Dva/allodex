import struct
import zlib

from tools.allods_fev import FevResolver, parse_bev


def _cstr(s: str) -> bytes:
    b = s.encode() + b"\0"
    return struct.pack("<I", len(b)) + b


def _chunk(tag: bytes, body: bytes) -> bytes:
    return tag + struct.pack("<I", len(body)) + body + (b"\0" if len(body) & 1 else b"")


def _bev(strings: list[str], event: int, sounddef_name: int, param: int = -1) -> bytes:
    """Projet FMOD minimal comme ceux du client : banque `Music_StartZones`, une définition de
    son (`adaptivemusic/Conquer_high.wav`, sous-piste 1), un événement complexe à un calque."""
    lg = struct.pack("<II", 0, 0) + _cstr("Music") + struct.pack("<II", 1, 1)
    lg += struct.pack("<II", 0x80, 8) + b"\x11" * 8 + struct.pack("<I", 0) + _cstr("Music_StartZones")
    head = struct.pack("<II", 8, event) + bytes(range(1, 17)) + struct.pack("<f", 0.25)
    head += b"\0" * (0xA8 - len(head))
    instance = struct.pack("<H", 0) + struct.pack("<ffIHHiIIIIf", 0, 1, 0, 0, 0, -1, 0, 0, 0, 0, 1)
    instance += struct.pack("<ffII", -1, -1, 2, 2)
    lg += head + struct.pack("<I", 1) + struct.pack("<HhhHH", 2, -1, param, 1, 0) + instance + b"\0" * 8
    lg += struct.pack("<I", 1) + struct.pack("<III", sounddef_name, 0, 1)
    lg += struct.pack("<II", 0, 100) + _cstr("adaptivemusic/Conquer_high.wav") + struct.pack("<III", 0, 1, 321000)
    offs, blob = [], b""
    for s in strings:
        offs.append(len(blob))
        blob += s.encode() + b"\0"
    strr = struct.pack(f"<I{len(offs)}I", len(offs), *offs) + blob
    proj = b"PROJ" + _chunk(b"LGCY", lg) + _chunk(b"STRR", strr)
    riff = b"FEV " + _chunk(b"FMT ", struct.pack("<I", 0x00450000)) + _chunk(b"LIST", proj)
    return zlib.compress(b"\0" * 68 + _chunk(b"RIFF", riff))


def test_parse_bev_links_event_to_its_sound_definition_wave():
    strings = ["", "Music", "ZonesMusic", "IE1_main", "/Music/Conquer_high"]
    project = parse_bev(_bev(strings, 3, 4))
    assert project.name == "Music" and project.banks == ["Music_StartZones"]
    assert [e.name for e in project.events] == ["IE1_main"]
    assert project.events[0].layers == [(-1, [0])]
    wave = project.sounddefs[0].waves[0]
    assert (wave.bank, wave.index, wave.stream, wave.ms) == ("Music_StartZones", 1, "Conquer_high", 321000)


def test_resolver_checks_the_stream_name_in_the_bank():
    strings = ["", "Music", "ZonesMusic", "IE1_main", "/Music/Conquer_high"]
    files = {"SFX/Music/Music.bev": _bev(strings, 3, 4, param=0)}
    names = [*files, "SFX/Music/Music_StartZones.fsb"]
    ok = FevResolver(names, files.get, lambda bank: ["Conquer_adaptive", "Conquer_high"])
    waves, why = ok.waves("Music/ZonesMusic/IE1_main")
    assert why is None
    assert [(w["bank"], w["sub"], w["stream"], w["param"]) for w in waves] == \
        [("SFX/Music/Music_StartZones.fsb", 2, "Conquer_high", 0)]
    stale = FevResolver(names, files.get, lambda bank: ["Conquer_adaptive", "AstralBattle"])
    waves, why = stale.waves("Music/ZonesMusic/IE1_main")
    assert waves == [] and "absente" in why
