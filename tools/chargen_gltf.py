"""Briques glTF de l'écran de création de personnage : celles de `tools/allods_gltf.py`, communes
aux fatalités et aux cinématiques moteur (ce module en était une copie, réunie à la fusion des
branches). Seul le nom du générateur glTF change."""
from __future__ import annotations

from dataclasses import dataclass

from tools.allods_gltf import (  # noqa: F401
    BinSource, Loaded, TexturePool, _slug, bind_pose_positions, clean_animation, infer_texture_dims,
    load_animation, load_geometry, reduce_keys,
)
from tools.allods_gltf import Exporter as _Exporter


@dataclass
class Exporter(_Exporter):
    generator: str = "allodex/extract_character_creation"
