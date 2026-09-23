"""Lecteur de bytecode LuaJIT (scripts d'addon du client 17.0)."""
from __future__ import annotations

import os
from pathlib import Path
import struct

import pytest

from tools import luajit
from tools.allods_packdb import packs_path
from tools.extract_talents import LUA_PAK, builder_layout


def uleb(v: int) -> bytes:
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        out.append(b | (0x80 if v else 0))
        if not v:
            return bytes(out)


def uleb33_num(x: float) -> bytes:
    lo, hi = struct.unpack("<II", struct.pack("<d", x))
    first = ((lo & 0x3F) << 1) | 1
    rest = lo >> 6
    head = bytes([first | (0x80 if rest else 0)]) + (uleb(rest) if rest else b"")
    return head + uleb(hi)


def uleb33_int(v: int) -> bytes:
    first = (v & 0x3F) << 1
    rest = v >> 6
    return bytes([first | (0x80 if rest else 0)]) + (uleb(rest) if rest else b"")


def kstr(s: str) -> bytes:
    b = s.encode()
    return uleb(5 + len(b)) + b


def ktab_num(x: float) -> bytes:
    lo, hi = struct.unpack("<II", struct.pack("<d", x))
    return uleb(4) + uleb(lo) + uleb(hi)


def ins(op: str, a: int = 0, b: int = 0, c: int = 0, d: int | None = None) -> bytes:
    o = luajit.OPS.index(op)
    word = o | a << 8 | ((d << 16) if d is not None else (c << 16 | b << 24))
    return struct.pack("<I", word)


def chunk() -> bytes:
    """`t.KEY = { SCALE = 0.5, N = 3 }` ; constantes numériques 0.5 et 7."""
    table = uleb(1) + uleb(0) + uleb(2) + kstr("SCALE") + ktab_num(0.5) + kstr("N") + uleb(3) + uleb(3)
    kgc = table + kstr("KEY")                     # ordre du fichier : gc(1) = table, gc(0) = "KEY"
    code = ins("TDUP", a=1, d=1) + ins("TSETS", a=1, b=0, c=0) + ins("RET0", d=1)
    kn = uleb33_num(0.5) + uleb33_int(7)
    body = bytes([0, 1, 2, 0]) + uleb(2) + uleb(2) + uleb(3) + code + kgc + kn
    return b"\x1bLJ\xa1" + uleb(luajit.FLAG_STRIP | 0x08) + uleb(len(body)) + body + b"\x00"


def test_parse_constantes_et_instructions():
    (pr,) = luajit.parse(chunk())
    assert pr.params == 1
    assert [i.op for i in pr.code] == ["TDUP", "TSETS", "RET0"]
    assert pr.kn == [0.5, 7]
    assert pr.gc(0) == "KEY"
    assert luajit.named_table([pr], "SCALE") == {"SCALE": 0.5, "N": 3}
    assert {k: v.hash for k, v in luajit.assigned_tables(pr).items()} == {"KEY": {"SCALE": 0.5, "N": 3}}


def test_refuse_autre_format():
    with pytest.raises(ValueError):
        luajit.parse(b"\x1bLua")


PACKS = str(packs_path(Path("/mnt/h/MyGames/AllodsRU/data/Packs")))


@pytest.mark.skipif(not os.path.exists(os.path.join(PACKS, LUA_PAK)), reason="client 17.0 absent")
def test_constantes_talentbuilder_du_client_17():
    lay = builder_layout(PACKS)
    assert lay["counts"] == {"BASE_TALENTS_ROW_COUNT": 10, "BASE_TALENTS_COL_COUNT": 4, "FIELD_TALENTS_FIELD_COUNT": 3,
                             "FIELD_TALENTS_ROW_COUNT": 9, "FIELD_TALENTS_COL_COUNT": 9}
    assert lay["rankCost"] == [1, 2, 3]
    assert lay["baseField"]["SCALE"] == pytest.approx(0.92437, abs=1e-5)
    assert lay["baseField"]["arrow"] == [14, 11, 24]
    assert lay["baseField"]["side"] == {"left": -9, "right": 56}
    assert lay["field"]["LEFT_BORDER"] == pytest.approx(36.25, abs=1e-3)
    assert lay["builder"]["fieldsInterval"] == 15
    assert lay["fieldTalentSize"] == {"main": 36, "done": 40}
    assert lay["fieldHighlight"]["TALENT_HIGHLIGHT_FULL"] == [0.07, 0.48, 0.48, 1.0]
    assert lay["classColors"]["DRUID"][:3] == [1.0, 0.4627, 0.2353]
    assert lay["classIcons"]["DRUID"] == "Druid"
