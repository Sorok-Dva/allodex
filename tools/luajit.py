"""Lecture des scripts d'addon compilés du client 17.0 (`LuaCompiledIngame_x64.pak`, `*.luac`).

Le client livre ses scripts d'interface en bytecode LuaJIT 2.1 dépouillé (en-tête `ESC 'L' 'J'`,
octet de version 0xA1 propre au client mais jeu d'instructions standard, drapeaux `STRIP|FR2`).
On n'en tire que ce qui est nécessaire pour reproduire une fenêtre : les constantes (tables
littérales `{ SCALE = 0.92, … }`, nombres, chaînes) et une lecture instruction par instruction
pour quelques motifs simples (`t.KEY = {…}`).

Format d'un prototype (dans l'ordre du fichier, les enfants avant leur parent) :
`uleb taille`, puis `u8 drapeaux, u8 nb_params, u8 taille_pile, u8 nb_upvalues`,
`uleb nb_kgc, uleb nb_kn, uleb nb_ins`, les instructions (u32), les upvalues (u16),
les constantes « objets » (`kgc` : chaînes, tables, prototypes enfants) puis numériques (`kn`).
Une instruction qui désigne une constante objet par `D` la prend à rebours : `kgc[nb_kgc-1-D]`.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

OPS = (
    "ISLT ISGE ISLE ISGT ISEQV ISNEV ISEQS ISNES ISEQN ISNEN ISEQP ISNEP ISTC ISFC IST ISF ISTYPE "
    "ISNUM MOV NOT UNM LEN ADDVN SUBVN MULVN DIVVN MODVN ADDNV SUBNV MULNV DIVNV MODNV ADDVV "
    "SUBVV MULVV DIVVV MODVV POW CAT KSTR KCDATA KSHORT KNUM KPRI KNIL UGET USETV USETS USETN "
    "USETP UCLO FNEW TNEW TDUP GGET GSET TGETV TGETS TGETB TGETR TSETV TSETS TSETB TSETM TSETR "
    "CALLM CALL CALLMT CALLT ITERC ITERN VARG ISNEXT RETM RET RET0 RET1 FORI JFORI FORL IFORL "
    "JFORL ITERL IITERL JITERL LOOP ILOOP JLOOP JMP FUNCF IFUNCF JFUNCF FUNCV IFUNCV JFUNCV "
    "FUNCC FUNCCW"
).split()

FLAG_STRIP = 0x02


class Proto:
    """Marqueur d'un prototype enfant dans les constantes."""

    def __repr__(self) -> str:  # pragma: no cover - aide au débogage
        return "<proto>"


@dataclass
class LuaTable:
    array: list = field(default_factory=list)
    hash: dict = field(default_factory=dict)


@dataclass
class Ins:
    op: str
    a: int
    b: int
    c: int
    d: int


@dataclass
class Prototype:
    params: int
    code: list[Ins]
    kgc: list          # dans l'ordre du fichier
    kn: list[float | int]

    def gc(self, d: int):
        """Constante objet désignée par l'opérande `D` d'une instruction."""
        return self.kgc[len(self.kgc) - 1 - d]

    def strings(self) -> list[str]:
        return [k for k in self.kgc if isinstance(k, str)]

    def tables(self) -> list[LuaTable]:
        return [k for k in self.kgc if isinstance(k, LuaTable)]


def _uleb(b: bytes, i: int) -> tuple[int, int]:
    r = s = 0
    while True:
        c = b[i]
        i += 1
        r |= (c & 0x7F) << s
        s += 7
        if c < 0x80:
            return r, i


def _uleb33(b: bytes, i: int) -> tuple[int, bool, int]:
    c = b[i]
    i += 1
    is_num = bool(c & 1)
    r = c >> 1
    if c >= 0x80:
        r &= 0x3F
        s = 6
        while True:
            c = b[i]
            i += 1
            r |= (c & 0x7F) << s
            s += 7
            if c < 0x80:
                break
    return r, is_num, i


def _double(lo: int, hi: int) -> float:
    return struct.unpack("<d", struct.pack("<II", lo & 0xFFFFFFFF, hi & 0xFFFFFFFF))[0]


def _signed(v: int) -> int:
    return v - (1 << 32) if v & 0x80000000 else v


def _ktab_value(p: bytes, j: int):
    t, j = _uleb(p, j)
    if t == 0:
        return None, j
    if t == 1:
        return False, j
    if t == 2:
        return True, j
    if t == 3:
        v, j = _uleb(p, j)
        return _signed(v), j
    if t == 4:
        lo, j = _uleb(p, j)
        hi, j = _uleb(p, j)
        return _double(lo, hi), j
    n = t - 5
    return p[j:j + n].decode("utf-8", "replace"), j + n


def _parse_proto(p: bytes, stripped: bool) -> Prototype:
    params = p[1]
    nuv = p[3]
    j = 4
    nkgc, j = _uleb(p, j)
    nkn, j = _uleb(p, j)
    nbc, j = _uleb(p, j)
    if not stripped:
        dbg, j = _uleb(p, j)
        if dbg:
            _, j = _uleb(p, j)
            _, j = _uleb(p, j)
    code = []
    for k in range(nbc):
        ins = struct.unpack_from("<I", p, j + 4 * k)[0]
        op = ins & 0xFF
        code.append(Ins(OPS[op] if op < len(OPS) else f"OP{op}", (ins >> 8) & 0xFF, ins >> 24, (ins >> 16) & 0xFF, ins >> 16))
    j += 4 * nbc + 2 * nuv
    kgc: list = []
    for _ in range(nkgc):
        tp, j = _uleb(p, j)
        if tp >= 5:
            kgc.append(p[j:j + tp - 5].decode("utf-8", "replace"))
            j += tp - 5
        elif tp == 0:
            kgc.append(Proto())
        elif tp == 1:
            na, j = _uleb(p, j)
            nh, j = _uleb(p, j)
            t = LuaTable()
            for _ in range(na):
                v, j = _ktab_value(p, j)
                t.array.append(v)
            for _ in range(nh):
                k, j = _ktab_value(p, j)
                v, j = _ktab_value(p, j)
                t.hash[k] = v
            kgc.append(t)
        elif tp in (2, 3):
            lo, j = _uleb(p, j)
            hi, j = _uleb(p, j)
            kgc.append(lo | hi << 32)
        else:  # nombre complexe (FFI) : sans usage ici
            for _ in range(4):
                _, j = _uleb(p, j)
            kgc.append(None)
    kn: list = []
    for _ in range(nkn):
        lo, is_num, j = _uleb33(p, j)
        if is_num:
            hi, j = _uleb(p, j)
            kn.append(_double(lo, hi))
        else:
            kn.append(_signed(lo))
    return Prototype(params, code, kgc, kn)


def parse(data: bytes) -> list[Prototype]:
    """Prototypes d'un chunk LuaJIT, dans l'ordre du fichier (le chunk principal en dernier)."""
    if data[:3] != b"\x1bLJ":
        raise ValueError("pas un bytecode LuaJIT")
    flags, i = _uleb(data, 4)
    stripped = bool(flags & FLAG_STRIP)
    if not stripped:
        n, i = _uleb(data, i)
        i += n
    protos = []
    while i < len(data):
        n, i = _uleb(data, i)
        if n == 0:
            break
        protos.append(_parse_proto(data[i:i + n], stripped))
        i += n
    return protos


def named_table(protos: list[Prototype], *keys: str) -> dict:
    """Première table littérale qui contient toutes les clés données (constantes de classe)."""
    for pr in protos:
        for t in pr.tables():
            if all(k in t.hash for k in keys):
                return dict(t.hash)
    raise LookupError(f"aucune table avec {keys}")


def assigned_tables(pr: Prototype) -> dict[str, LuaTable]:
    """Tables littérales rangées sous une clé : `t.CLÉ = {…}` (`TDUP` puis `TSETS`) ou
    `t[NOM_GLOBAL] = {…}` (`GGET`/`KSTR` de la clé, `TDUP`, puis `TSETV`).

    Suffit aux tables de couleurs des scripts (couleur par classe, par état de surbrillance).
    """
    out: dict[str, LuaTable] = {}
    tables: dict[int, LuaTable] = {}
    names: dict[int, str] = {}
    for ins in pr.code:
        if ins.op == "TDUP":
            k = pr.gc(ins.d)
            names.pop(ins.a, None)
            if isinstance(k, LuaTable):
                tables[ins.a] = k
            else:
                tables.pop(ins.a, None)
        elif ins.op in ("GGET", "KSTR"):
            k = pr.gc(ins.d)
            tables.pop(ins.a, None)
            if isinstance(k, str):
                names[ins.a] = k
        elif ins.op == "TSETS" and ins.a in tables:
            key = pr.gc(ins.c)
            if isinstance(key, str):
                out[key] = tables.pop(ins.a)
        elif ins.op == "TSETV" and ins.a in tables and ins.c in names:
            out[names[ins.c]] = tables.pop(ins.a)
        elif ins.op not in ("TSETS", "TSETV", "TGETS", "TGETV", "JMP"):
            tables.pop(ins.a, None)
            names.pop(ins.a, None)
    return out
