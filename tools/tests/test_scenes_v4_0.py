"""Tests des crochets 4.0 (`tools/scenes/v4_0.py`) : relevé du `sortMode` du Geometry xdb.

Sur des fichiers synthétiques : ni l'arbre serveur ni les clients ne sont lus.
"""
from __future__ import annotations

from pathlib import Path

from tools.scenes import hooks_for
from tools.scenes import v4_0

XDB = """<?xml version="1.0" encoding="UTF-8" ?>
<Geometry>
    <fogFactor>1</fogFactor>
    <sortMode>OFFSETS</sortMode>
    <modelElements/>
</Geometry>
"""


def test_hooks_for_4_0_exposes_after_export_only():
    hooks = hooks_for("4.0")
    assert hooks.after_export is v4_0.after_export
    assert hooks.material is None and hooks.positions is None and hooks.extra_roots is None


def test_read_sort_mode_from_xdb():
    assert v4_0.read_sort_mode(XDB) == "OFFSETS"
    assert v4_0.read_sort_mode("<Geometry><sortMode>  DEPTH </sortMode></Geometry>") == "DEPTH"
    assert v4_0.read_sort_mode("<Geometry/>") is None
    assert v4_0.read_sort_mode("<Geometry><sortMode/></Geometry>") is None
    assert v4_0.read_sort_mode("pas du xml") is None


def test_after_export_records_sort_mode_in_meta(tmp_path: Path):
    xdb = tmp_path / v4_0.GEOMETRY
    xdb.parent.mkdir(parents=True)
    xdb.write_text(XDB, encoding="utf-8")
    meta = {"version": "4.0"}
    v4_0.after_export(tmp_path / "out", meta, None, tmp_path)
    assert meta["sortMode"] == "OFFSETS"


def test_after_export_without_xdb_leaves_meta_untouched(tmp_path: Path):
    meta = {"version": "4.0"}
    v4_0.after_export(tmp_path / "out", meta, None, tmp_path)
    assert meta == {"version": "4.0"}
