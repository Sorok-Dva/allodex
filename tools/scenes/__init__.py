"""Particularités par version des scènes de menu (4.0 → 8.0).

`tools/extract_menu_scene.py` reste générique : il lit les xdb, décode les binaires et
écrit le glTF. Ce qui n'est vrai que d'une version — un correctif de pose, une
bibliothèque d'effets à exporter en plus, des textures FX à déposer — vit dans
`tools/scenes/v<majeur>_0.py` et s'enregistre ici.

Chaque module expose une instance `HOOKS = SceneHooks(...)` dont les fonctions sont
toutes optionnelles :

* `material(mat, additive) -> bool` : ajuste le caractère additif d'un matériau ;
* `positions(name, obj, position) -> ndarray` : remplace les positions de sommets
  d'un objet (par exemple pour cuire une pose d'attache) ;
* `extra_roots(emit_object) -> list[int]` : émet des objets supplémentaires à la
  racine (bibliothèques d'effets masquées puis instanciées par le lecteur) ;
* `after_export(target, meta, source, server_root)` : dépose des fichiers à côté de
  `scene.glb` et complète `scene.json`.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Callable, Any


@dataclass
class SceneHooks:
    material: Callable[[Any, bool], bool] | None = None
    positions: Callable[[str, Any, Any], Any] | None = None
    extra_roots: Callable[[Callable[..., int | None]], list[int]] | None = None
    after_export: Callable[[Any, dict, Any, Any], None] | None = None


def hooks_for(version: str) -> SceneHooks:
    """`"7.0"` → `tools.scenes.v7_0.HOOKS` ; une version sans module n'a aucun crochet."""
    module_name = "v" + version.replace(".", "_")
    try:
        module = import_module(f"{__name__}.{module_name}")
    except ModuleNotFoundError as error:
        if error.name != f"{__name__}.{module_name}":
            raise
        return SceneHooks()
    return getattr(module, "HOOKS", SceneHooks())
