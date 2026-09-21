"""7.0 « New Order » : navires en bataille au-dessus de Dane."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from tools.scenes import SceneHooks

# Textures originales des AMM_Shot01/02 : chemins explicites, sans dépendre d'un
# matériau partagé ou d'un nom de primitive du GLB.
CANNON_TEXTURES = {
    "projectile": "Glow04White",
    "muzzle": "ManaFire01",
    "impact": "Rays23White",
    "shield": "Glow04Blue",
    "flame": "Fire07",
    "electric": "NoiseLight",
    "spark": "Spark06White",
    "smoke": "Smoke02White",
}


def material(mat, additive: bool) -> bool:
    # Le BlendEffect ne s'applique pas aux matériaux opaques.
    return additive and mat.transparent


def positions(name: str, obj, position: np.ndarray) -> np.ndarray:
    from tools.extract_menu_scene import attachment_bind_positions
    verts, skeleton = obj.vertices, obj.skeleton
    if skeleton is None:
        return position
    if name.startswith("AMM_Flag_") or name.startswith("AMM_7_0_Stones_"):
        return attachment_bind_positions(verts, skeleton)
    if name == "AMM_7_0_FrontShips":
        engine_indices = [obj.indices[e.ib0:e.ib1] for e in obj.doc.elements
                          if e.name.startswith("Engine_")]
        if engine_indices:
            return attachment_bind_positions(verts, skeleton, np.unique(np.concatenate(engine_indices)))
    if name == "AMM_7_0_Ships_Destroyed":
        # Engine03 est stocké dans le repère du troisième navire. Replacer son attache
        # relativement à la coque 02, sans appliquer la pose finale (chute) aux coques.
        hull = next((e for e in obj.doc.elements if e.name == "SmalShip_destr_02"), None)
        engines = [obj.indices[e.ib0:e.ib1] for e in obj.doc.elements
                   if e.name.startswith("Engine_") and e.name.endswith("03")]
        if hull is not None and engines:
            bound = attachment_bind_positions(verts, skeleton)
            hull_indices = np.unique(obj.indices[hull.ib0:hull.ib1])
            selected = np.unique(np.concatenate(engines))
            offset = position[hull_indices].mean(axis=0) - bound[hull_indices].mean(axis=0)
            position = position.copy()
            position[selected] = bound[selected] + offset
    return position


def extra_roots(emit_object) -> list[int]:
    # Bibliothèque native des tirs : maillages, UV, couleurs de sommets et matériaux
    # complets, masqués par le lecteur puis instanciés par salve.
    shot = emit_object("AMM_Shot01", (0, 0, 0), (0, 0, 0, 1), 1)
    return [shot] if shot is not None else []


def after_export(target: Path, meta: dict, source, server_root: Path) -> None:
    from tools.extract_menu_scene import TextureLibrary
    library = TextureLibrary(source, server_root, 512)
    effects = {}
    for key, texture in CANNON_TEXTURES.items():
        result = library.png(f"/Spells/FX/Textures/{texture}.(Texture).xdb")
        if result is not None:
            filename = f"cannon-{key}.png"
            (target / filename).write_bytes(result[0])
            effects[key] = filename
    meta["cannonTextures"] = effects


HOOKS = SceneHooks(material=material, positions=positions, extra_roots=extra_roots,
                   after_export=after_export)
