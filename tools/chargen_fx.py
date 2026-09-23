"""Effets des personnages de la création : lueurs et particules des objets tenus (boule de feu du
mage, `Chargen_MageHandFX`) et effets des tenues de création (`growths[].fx` : plantes du
Pacificateur, lame du Paladin, aspects du Prêtre…).

Construits par `FxBuild` (`tools/allods_fx.py`, commun aux fatalités et aux cinématiques) : un
`.glb` par gabarit dans `fx/`, ses métadonnées (clips, particules, fondus) dans `chargen.json`
(`fx.objects`), particules allégées dans `particles/` et leur atlas.

Ajout propre à ces gabarits, relevé sur `Chargen_MageHandFX` : leurs effets ne sont pas des
composants (`VisObjectTemplate.components`, +0x138) mais des **objets accrochés de l'état par
défaut** (`defaultState.attached`, +0x28 de l'état en +0x28 du gabarit, soit +0x50 ; éléments de
40 octets : `locator` +0x08, `VisObjectTemplate*` +0x20) — ici un système de particules (la boule
de feu) et son son, sur le locator `Slot_Special01` d'une géométrie sans élément visible.
`FxBuild` les reçoit comme des composants.
"""
from __future__ import annotations

import contextlib
from dataclasses import replace
from pathlib import Path

from tools import allods_fx
from tools.allods_fx import FxBuild, ParticlePool
from tools.allods_gltf import Exporter
from tools.allods_packdb import PackDB
from tools.allods_visdb import Component, read_visobject

STATE_ATTACHED = 0x50          # VisObjectTemplate : defaultState (+0x28) → attached (+0x28)
STATE_ATTACHED_STRIDE = 40
FX_TEXTURE_MAX = 4096


def state_attachments(db: PackDB, vot: int) -> list[Component]:
    """Objets accrochés de l'état par défaut d'un gabarit, en composants."""
    out = []
    for e in db.elements(vot + STATE_ATTACHED, STATE_ATTACHED_STRIDE):
        child = db.ptr(e + 0x20)
        if child is not None and db.vtype(child) == "VisObjectTemplate":
            out.append(Component(locator=db.string(e + 0x08) or "", offset=(0.0, 0.0, 0.0),
                                 rotation=(0.0, 0.0, 0.0, 1.0), scale=1.0, visobject=child))
    return out


@contextlib.contextmanager
def with_state_attachments(db: PackDB):
    """`FxBuild` lit les gabarits par `allods_fx.read_visobject` : on y ajoute, le temps de
    l'export, les objets accrochés de l'état par défaut (sans rien changer pour les autres outils)."""
    base = allods_fx.read_visobject

    def read(db_, cat, off):
        vo = base(db_, cat, off)
        extra = state_attachments(db_, off) if db_ is db else []
        return replace(vo, components=list(vo.components) + extra) if extra else vo
    allods_fx.read_visobject = read
    try:
        yield
    finally:
        allods_fx.read_visobject = base


def has_effect(db: PackDB, cat, vot: int) -> bool:
    """Le gabarit porte-t-il autre chose qu'un maillage statique (particules, composants, objets
    accrochés de son état) ?"""
    vo = read_visobject(db, cat, vot)
    return vo.particle is not None or bool(vo.components) or bool(state_attachments(db, vot))


class CharacterFx:
    """Gabarits d'effets exportés à la demande : `fx/<nom>.glb` + métadonnées communes."""

    def __init__(self, db: PackDB, cat, bins, textures, out: Path) -> None:
        self.db, self.cat, self.bins, self.textures, self.out = db, cat, bins, textures, out
        self.particles = ParticlePool(db, cat, bins, out)
        self.objects: dict[str, dict] = {}
        self.names: dict[int, str] = {}      # noms uniques communs à tous les `.glb`
        self.files: dict[int, str | None] = {}
        self.report: list[str] = []

    def export(self, vot: int) -> str | None:
        """`fx/<nom>.glb` du gabarit (nom de son nœud racine `vot:<nom>`), ou None."""
        if vot in self.files:
            return self.files[vot]
        fx = FxBuild(Exporter(self.textures, FX_TEXTURE_MAX, generator="allodex/extract_character_creation",
                              texture_prefix="../textures/"), self.db, self.cat, self.bins,
                     names=self.names, particles=self.particles, report=self.report)
        with with_state_attachments(self.db):
            node = fx.emit(vot)
        name = fx.name_of(vot)
        if node is None:
            self.files[vot] = None
            return None
        glb = fx.exporter.finish([node])
        (self.out / "fx").mkdir(parents=True, exist_ok=True)
        file = f"fx/{_file(name)}.glb"
        (self.out / file).write_bytes(glb)
        for key, info in fx.meta.items():
            self.objects.setdefault(key, info)
        self.files[vot] = file
        return file

    def finish(self) -> dict:
        atlas = self.particles.write_atlas(self.textures)
        return {"objects": self.objects, "particleAtlas": atlas}


def _file(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
