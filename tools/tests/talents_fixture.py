"""Construction de `pack.bin` / `pack.loc` synthétiques (format v1, 32 bits) pour les tests.

Rien ici ne lit un vrai client : on fabrique une base minimale qui suit la disposition
documentée dans `tools/packbin.py` (blocs 0-4, tables de hachage, relocalisations).
"""
from __future__ import annotations

import struct
import zlib

TYPES = ["CharacterClass", "BaseTalentsTable", "TalentFieldResource", "TalentAbility", "NoTalent",
         "AbilityResource", "TalentSpell", "Spell", "UISingleTexture", "UITexture"]


class Heap:
    """Bloc 3 : objets + relocalisations (adresse, genre, cible)."""

    def __init__(self) -> None:
        self.buf = bytearray()
        self.relocs: list[tuple[int, int]] = []   # (X, T) déjà codés
        self.paths: dict[str, int] = {}

    def ensure(self, end: int) -> None:
        if len(self.buf) < end:
            self.buf.extend(b"\0" * (end - len(self.buf)))

    def u32(self, a: int, v: int) -> None:
        self.ensure(a + 4)
        struct.pack_into("<I", self.buf, a, v)

    def f32(self, a: int, v: float) -> None:
        self.ensure(a + 4)
        struct.pack_into("<f", self.buf, a, v)

    def raw(self, a: int, data: bytes) -> None:
        self.ensure(a + len(data))
        self.buf[a:a + len(data)] = data

    def obj(self, a: int, type_name: str, path: str | None = None, nested: bool = False) -> None:
        self.ensure(a + 16)
        self.relocs.append((2 * (a + 1) + (1 if nested else 0), TYPES.index(type_name)))
        if path:
            self.paths[path] = a

    def ptr(self, a: int, target: int) -> None:
        self.u32(a, 0)
        self.relocs.append((2 * a, target))

    def data(self, a: int, target: int) -> None:
        self.u32(a, 0)
        self.relocs.append((2 * a + 1, target))

    def string(self, field: int, where: int, text: str) -> None:
        raw = text.encode() + b"\0"
        self.raw(where, raw)
        self.data(field, where)
        self.u32(field + 4, len(raw) - 1)
        self.u32(field + 8, len(raw))

    def text_ref(self, field: int, where: int, path: str, tid: int) -> None:
        self.string(field, where, path)
        self.u32(field + 12, tid)

    def vector(self, field: int, where: int, items: list[int] | None = None, size: int | None = None) -> None:
        self.data(field, where)
        n = size if size is not None else 4 * len(items or [])
        self.u32(field + 4, n)
        self.u32(field + 8, n)
        for i, t in enumerate(items or []):
            self.ptr(where + 4 * i, t)


def _strings_table(entries: list[tuple[str, int]]) -> bytes:
    """`(u32 8, u32 n)` + n × (ptr auto-relatif, u32 long., u32 id) + chaînes."""
    head = struct.pack("<II", 8, len(entries))
    table = bytearray(12 * len(entries))
    blob = bytearray()
    base_str = 8 + len(table)
    for i, (s, tid) in enumerate(entries):
        raw = s.encode() + b"\0"
        pad = raw + b"\0" * ((-len(raw)) % 4)
        target = base_str + len(blob)
        e = 8 + 12 * i
        struct.pack_into("<III", table, 12 * i, target - e, len(raw), tid)
        blob += pad
    return head + bytes(table) + bytes(blob)


def build_pack(heap: Heap, text_paths: dict[str, int]) -> bytes:
    """Assemble un pack.bin v1 (non compressé) autour du tas `heap`."""
    out = bytearray()

    def chunk(cid: int, payload: bytes, size: int | None = None) -> None:
        out.extend(struct.pack("<II", cid, len(payload) if size is None else size))
        out.extend(payload)

    chunk(0, b"TESTHASH")
    chunk(1, _strings_table(sorted(text_paths.items(), key=lambda kv: kv[1])))
    # bloc 2 : 4 tables (ptr, n) ; table 0 = 1 alvéole de chemins, table 1 = types
    hdr_size = 32
    paths = list(heap.paths.items())
    bucket_off = hdr_size
    entries_off = bucket_off + 8
    recs_off = entries_off + 12 * len(paths)
    recs = bytearray()
    entries = bytearray()
    for i, (p, addr) in enumerate(paths):
        rec_at = recs_off + len(recs)
        raw = p.encode() + b"\0"
        rec = struct.pack("<II", 1, 0) + raw + b"\0" * ((-len(raw)) % 4)
        entries += struct.pack("<III", rec_at - (entries_off + 12 * i), len(raw), addr)
        recs += rec
    types_off = recs_off + len(recs)
    ttable = bytearray()
    tstr = bytearray()
    tstr_off = types_off + 12 * len(TYPES)
    for i, t in enumerate(TYPES):
        raw = f"struct NDb::{t}".encode() + b"\0"
        at = tstr_off + len(tstr)
        ttable += struct.pack("<III", at - (types_off + 12 * i), len(raw), 0)
        tstr += raw + b"\0" * ((-len(raw)) % 4)
    end = tstr_off + len(tstr)
    c2 = bytearray(end)
    struct.pack_into("<II", c2, 0, bucket_off, 1)
    struct.pack_into("<II", c2, 8, types_off - 8, len(TYPES))
    struct.pack_into("<II", c2, 16, end - 16, 0)
    struct.pack_into("<II", c2, 24, end - 24, 0)
    struct.pack_into("<II", c2, bucket_off, entries_off - bucket_off, len(paths))
    c2[entries_off:entries_off + len(entries)] = entries
    c2[recs_off:recs_off + len(recs)] = recs
    c2[types_off:types_off + len(ttable)] = ttable
    c2[tstr_off:tstr_off + len(tstr)] = tstr
    chunk(2, bytes(c2))
    chunk(3, bytes(heap.buf))
    pairs = b"".join(struct.pack("<II", x, t) for x, t in heap.relocs)
    chunk(4, pairs, size=len(heap.relocs))
    return bytes(out)


def build_loc_v1(texts: dict[str, tuple[int, str]]) -> bytes:
    """pack.loc v1 : bloc 0 (chemins → id), bloc 1 (long., décalage), bloc 2 (UTF-16)."""
    by_id = sorted(texts.items(), key=lambda kv: kv[1][0])
    c0 = _strings_table([(p, tid) for p, (tid, _) in by_id])
    n = max(tid for tid, _ in texts.values()) + 1
    words = bytearray(8 * n)
    blob = bytearray()
    for _, (tid, s) in by_id:
        struct.pack_into("<II", words, 8 * tid, len(s), len(blob))
        blob += s.encode("utf-16-le") + b"\0\0"
    out = struct.pack("<II", 0, len(c0)) + c0
    out += struct.pack("<II", 1, 2 * n) + bytes(words)
    out += struct.pack("<II", 2, len(blob)) + bytes(blob)
    return out


def build_loc_v2(strings: list[str], magic: bytes = b"HASH") -> bytes:
    n = len(strings)
    words = bytearray(16 * n)
    blob = bytearray()
    for i, s in enumerate(strings):
        struct.pack_into("<QQ", words, 16 * i, len(s), len(blob))
        blob += s.encode("utf-16-le") + b"\0\0"
    return magic + b"\0\0\0\0" + struct.pack("<Q", 2 * n) + bytes(words) + struct.pack("<IQ", 2, len(blob)) + bytes(blob)


def dxt1_uitexture(w: int = 8, h: int = 8) -> bytes:
    """`(UITexture).bin` DXT1 uni : zlib(u32 0, u32 taille, blocs)."""
    block = struct.pack("<HHI", 0xF800, 0xF800, 0)  # rouge plein
    payload = block * ((w // 4) * (h // 4))
    return zlib.compress(struct.pack("<II", 0, len(payload)) + payload)


def warrior_fixture() -> tuple[bytes, bytes, bytes]:
    """(pack.bin, pack.loc, icône) : un guerrier, un livre de 2 couches et une grille 1 × 3."""
    H = Heap()
    T = {
        "Mechanics/Classes/WarriorClassName.txt": 1,
        "Mechanics/Talents/Field.Name.txt": 2,
        "Mechanics/Spells/Strike/Strike.Name.txt": 3,
        "Mechanics/Spells/Strike/Strike.Description.txt": 4,
        "Mechanics/Abilities/Rage/Ability_Name.txt": 5,
        "Mechanics/Abilities/Rage/Ability_Desc.txt": 6,
        "Mechanics/Texts/Include.txt": 7,
    }
    # classe
    H.obj(0x0, "CharacterClass", "Mechanics/Classes/Warrior.xdb")
    H.text_ref(0x10, 0x40, "Mechanics/Classes/WarriorClassName.txt", 1)
    H.string(0x20, 0x70, "WARRIOR")
    H.ptr(0x2C, 0x100)
    H.ensure(0x80)
    # table : couches (2 × 32 o) puis grilles
    H.obj(0x100, "BaseTalentsTable", "Mechanics/Talents/Table.xdb")
    H.vector(0x110, 0x130, size=64)
    H.vector(0x11C, 0x170, [0x400])
    # couche 0 : points en +4, tableau en +8
    H.u32(0x130 + 4, 0)
    H.vector(0x130 + 8, 0x180, [0x300, 0x340])
    H.u32(0x150 + 4, 5)
    H.vector(0x150 + 8, 0x190, [0x380])
    H.ensure(0x1A0)
    H.obj(0x300, "TalentSpell", nested=True)
    H.ptr(0x310, 0x500)
    H.ensure(0x340)
    H.obj(0x340, "NoTalent", nested=True)
    H.ensure(0x380)
    H.obj(0x380, "TalentAbility", nested=True)
    H.ptr(0x390, 0x800)
    H.ensure(0x3C0)
    # grille : nom, icône, lignes (1 ligne de 20 o)
    H.obj(0x400, "TalentFieldResource", "Mechanics/Talents/Field.xdb")
    H.text_ref(0x410, 0x480, "Mechanics/Talents/Field.Name.txt", 2)
    H.ptr(0x420, 0x900)
    H.vector(0x424, 0x440, size=20)
    H.vector(0x440, 0x460, [0x380, 0x340, 0x380])
    H.ensure(0x4C0)
    # sort : nom, description, rangs [lui-même], variables (1 × 0x28, nom en +4, valeur en +0x24)
    H.obj(0x500, "Spell", "Mechanics/Spells/Strike/Spell01.xdb")
    H.text_ref(0x510, 0x560, "Mechanics/Spells/Strike/Strike.Name.txt", 3)
    H.text_ref(0x520, 0x5A0, "Mechanics/Spells/Strike/Strike.Description.txt", 4)
    H.vector(0x530, 0x5E0, [0x500])
    H.vector(0x53C, 0x5F0, size=0x28)
    H.string(0x5F0 + 4, 0x620, "var0")
    H.f32(0x5F0 + 0x24, 12.5)
    H.ensure(0x630)
    # capacité à 2 rangs
    H.obj(0x800, "AbilityResource", "Mechanics/Abilities/Rage/Ability01.xdb")
    H.text_ref(0x810, 0x840, "Mechanics/Abilities/Rage/Ability_Name.txt", 5)
    H.text_ref(0x820, 0x870, "Mechanics/Abilities/Rage/Ability_Desc.txt", 6)
    H.vector(0x830, 0x8A0, [0x800, 0x8C0])
    H.ensure(0x8C0)
    H.obj(0x8C0, "AbilityResource", "Mechanics/Abilities/Rage/Ability02.xdb")
    H.ensure(0x8F0)
    # icône
    H.obj(0x900, "UISingleTexture", "Interface/Icons/Test.(UISingleTexture).xdb")
    H.ptr(0x910, 0x940)
    H.ensure(0x940)
    H.obj(0x940, "UITexture", "Interface/Icons/Test.(UITexture).xdb")
    H.ensure(0x980)
    pack = build_pack(H, T)
    loc = build_loc_v1({
        "Mechanics/Classes/WarriorClassName.txt": (1, "Guerrier"),
        "Mechanics/Talents/Field.Name.txt": (2, "Combattant"),
        "Mechanics/Spells/Strike/Strike.Name.txt": (3, "Frappe"),
        "Mechanics/Spells/Strike/Strike.Description.txt": (4, '<html><t href="/Mechanics/Texts/Include.txt"/> Inflige <r name="var0"/> dégâts.</html>'),
        "Mechanics/Abilities/Rage/Ability_Name.txt": (5, "Rage"),
        "Mechanics/Abilities/Rage/Ability_Desc.txt": (6, "Augmente la rage."),
        "Mechanics/Texts/Include.txt": (7, "<html>Attaque de mêlée.</html>"),
    })
    return pack, loc, dxt1_uitexture()
