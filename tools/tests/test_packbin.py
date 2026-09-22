"""Tests de `tools/packbin.py` sur des bases synthétiques (aucun client requis)."""
from __future__ import annotations

import numpy as np

from tools.packbin import KIND_DATA, KIND_PTR, KIND_TYPE, LocTable, PackBin, _v1_relocs
from tools.tests.talents_fixture import Heap, build_loc_v1, build_loc_v2, build_pack, warrior_fixture


def test_v1_relocs_normalise_les_genres():
    x = np.array([2 * 0x40, 2 * 0x44 + 1, 2 * (0x80 + 1), 2 * (0x90 + 3) + 1, 2 * (0xA0 + 2) + 1], dtype=np.int64)
    t = np.array([0x100, 0x200, 7, 8, 0x300], dtype=np.int64)
    keys, targets = _v1_relocs(x, t)
    decoded = {(int(k) >> 2, int(k) & 3): int(v) for k, v in zip(keys, targets)}
    assert decoded[(0x40, KIND_PTR)] == 0x100
    assert decoded[(0x44, KIND_DATA)] == 0x200
    assert decoded[(0x80, KIND_TYPE)] == 7       # étiquette à +1
    assert decoded[(0x90, KIND_TYPE)] == 8       # étiquette à +3 (7.0 Revelation, 8.0, 11.0)
    assert decoded[(0xA0, KIND_DATA)] == 0x300   # données partagées à +2


def test_packbin_v1_chemins_types_et_relocalisations():
    pack, _, _ = warrior_fixture()
    pb = PackBin(pack)
    assert pb.fmt == "v1" and pb.ptr_size == 4
    assert pb.paths["Mechanics/Classes/Warrior.xdb"] == 0
    assert pb.types[:3] == ["CharacterClass", "BaseTalentsTable", "TalentFieldResource"]
    assert pb.text_paths["Mechanics/Classes/WarriorClassName.txt"] == 1
    assert pb.type_at(0x0) == "CharacterClass"
    assert pb.type_at(0x380) == "TalentAbility"
    assert pb.ptr(0x2C) == 0x100
    assert pb.string(0x20) == "WARRIOR"
    assert pb.vector(0x11C) == (0x170, 4)
    assert pb.objects_of("AbilityResource") == [0x800, 0x8C0]
    assert pb.objects_of("Inconnu") == []


def test_loc_v1_par_chemin_et_par_identifiant():
    loc = LocTable(build_loc_v1({"a/Name.txt": (0, "Épée"), "b/Desc.txt": (2, "Coupe <b>fort</b>")}))
    assert loc.by_path("a/Name.txt") == "Épée"
    assert loc.get(2) == "Coupe <b>fort</b>"
    assert loc.get(1) == ""
    assert loc.get(99) is None


def test_loc_v2_par_identifiant():
    loc = LocTable(build_loc_v2(["Mage", "", "Огненная стрела"]))
    assert not loc.paths
    assert loc.get(0) == "Mage"
    assert loc.get(2) == "Огненная стрела"
    assert loc.get(3) is None


def test_heap_minimal_sans_objet_indexe():
    h = Heap()
    h.obj(0, "NoTalent", nested=True)
    h.ensure(0x20)
    pb = PackBin(build_pack(h, {"x.txt": 0}))
    assert pb.paths == {}
    assert pb.type_at(0) == "NoTalent"
