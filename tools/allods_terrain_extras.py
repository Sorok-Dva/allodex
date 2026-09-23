"""Herbe et eau du sol des cartes (`terrainDump`), mises en glTF pour les lecteurs du site.

Commun aux cinématiques moteur (`extract_engine_cutscene.build_terrain`) et aux fatalités
(`extract_fatalities.terrain_ground`). Les données viennent de `tools/allods_terrain.py`
(`parse_terrain_extras`, `terrain_foliage`, `foliage_atlas`, `water_layers`).

**Herbe** : chaque carreau d'herbe de 32 m devient un nœud (`extras.grassCell`) dont le primitif
`POINTS` porte une touffe par point : `POSITION` = pied (hauteur du sol au mètre de la grille,
lue sur le maillage fin), `_GNORMAL` = normale du sol (octets), `_GRASS` = octets (sorte, lacet et
phase du vent en 256ᵉ de tour, échelle en 64ᵉ), `_LIGHTUV` = place dans l'atlas des `lightmap`
(`u16` normalisés, 65535 sans cuisson) — 24 octets par touffe. Le nœud `grass` donne l'atlas
d'herbe de la carte et la table des sortes (`extras.grass.kinds` : rectangle de l'élément dans
l'atlas, `numLeaves`, `top` et `bottom` = (hauteur, décalage, largeur)). Les jeux marqués du bit 7
(mêmes places que leur jumeau, toujours) ne sont pas doublés. Lacet, échelle (entre `minScale` et
`maxScale`) et phase du vent sont tirés au hasard (graine = place du carreau) : le client les tire
lui-même, son tirage n'est pas dans les données.

**Eau** : un maillage par type d'eau (`extras.water`) ; chaque élément de 8 m est une grille de
8 × 8 sommets à `i·8/7` m de son coin, à la hauteur de la surface, qui portent (`_WATER`) les texels
de son bloc du `SplatMap_N` (`N` = texture de son matériau) : B = 0,5 + profondeur/8, R, G = 0,5 +
normale du fond / 2 (corrélations 0,997 sur `Ferris4`) — ce que lit le shader `StaticWater` du
client (`hght`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from tools.allods_terrain import (Patch, foliage_atlas, grid_samples, region_extras, region_splats, terrain_foliage,
                                  water_layers)

GRASS_ATLAS_MAX = 1024
WATER_TEXTURE_MAX = 512
WATER_GRID = 8
WATER_DEFAULTS = {"defaultFresnel": "World/Generic/Water/Textures/WaterFresnel.(Texture).bin",
                  "defaultBump": "World/Generic/Water/Textures/WaterNoise.(Texture).bin"}


def quantize_normals(n: np.ndarray) -> np.ndarray:
    """Normales du sol en octets (`n · ½ + ½`), quatrième octet nul."""
    q = np.round((np.asarray(n, np.float64) * 0.5 + 0.5) * 255).clip(0, 255).astype(np.uint8)
    return np.column_stack([q, np.zeros(len(q), np.uint8)])


def quantize_tufts(g: np.ndarray) -> np.ndarray:
    """(sorte, lacet, échelle, phase) en octets : sorte, lacet et phase en 256ᵉ de tour, échelle en 64ᵉ."""
    g = np.asarray(g, np.float64)
    turn = 256.0 / (2 * math.pi)
    return np.column_stack([g[:, 0], np.round(g[:, 1] * turn) % 256, np.round(g[:, 2] * 64).clip(0, 255),
                            np.round(g[:, 3] * turn) % 256]).astype(np.uint8)


def quantize_uv(uv: np.ndarray) -> np.ndarray:
    """Place dans l'atlas de lumière cuite en `u16` normalisés ; sans cuisson (−1) : 65535."""
    uv = np.asarray(uv, np.float64)
    q = np.round(uv.clip(0, 1) * 65534).astype(np.uint16)
    q[uv[:, 0] < 0] = 65535
    return q


@dataclass
class ExtrasBuilder:
    """Accumule l'herbe et l'eau des régions d'une carte, puis les écrit dans un `Exporter`."""
    db: object
    cat: object
    textures: object
    uri: object                                   # (nom, taille max) → URI vue depuis le .glb
    cells: dict = field(default_factory=dict)     # (région, i, j) → listes de colonnes
    kinds: list = field(default_factory=list)
    kind_index: dict = field(default_factory=dict)
    water: dict = field(default_factory=dict)     # (terra, type) → [positions, texels, indices]
    water_meta: dict = field(default_factory=dict)
    atlas_name: str | None = None
    atlas_size: tuple[int, int] | None = None
    _cache: dict = field(default_factory=dict)

    def _terra(self, terra: int):
        if terra not in self._cache:
            name, rects = foliage_atlas(self.db, self.cat, terra)
            self._cache[terra] = (terrain_foliage(self.db, terra), name, rects, water_layers(self.db, self.cat, terra))
        return self._cache[terra]

    def _kind(self, terra: int, layer: int, index: int) -> int | None:
        key = (terra, layer, index)
        if key in self.kind_index:
            return self.kind_index[key]
        foliage, name, rects, _ = self._terra(terra)
        f = foliage[layer][index] if layer < len(foliage) and index < len(foliage[layer]) else None
        rect = rects.get(f.element) if f is not None and f.element is not None else None
        kind = None
        if f is not None and rect is not None and name and f.leaves > 0 and f.top[0] > f.bottom[0]:
            if self.atlas_name is None:
                self.atlas_name = name
                img = self.textures.image(name, 1 << 14)
                self.atlas_size = img.size if img is not None else None
            if name == self.atlas_name and self.atlas_size:
                w, h = self.atlas_size
                x, y, rw, rh = rect
                kind = len(self.kinds)
                self.kinds.append({"uv": [round(x / w, 6), round(y / h, 6), round((x + rw) / w, 6), round((y + rh) / h, 6)],
                                   "leaves": int(f.leaves), "top": list(f.top), "bottom": list(f.bottom),
                                   "scale": [round(min(f.min_scale, f.max_scale), 4), round(max(f.min_scale, f.max_scale), 4)],
                                   "layer": layer, "foliage": index})
        self.kind_index[key] = kind
        return kind

    def add_region(self, get, region_path: str, terra: int | None, origin: tuple[float, float], patches: list[Patch],
                   keep, shift=(0.0, 0.0, 0.0), light_slot=None, keep_water=None) -> None:
        """Herbe et eau d'une région : `keep(x, y)` (monde) choisit les carreaux, `shift` décale les
        sommets (repère du décor), `light_slot` = case de la région dans l'atlas de lumière cuite
        (résolue par `emit`), `keep_water` choisit l'eau (par défaut comme l'herbe)."""
        keep_water = keep_water or keep
        extras = region_extras(get, region_path)
        if extras is None or terra is None:
            return
        ox, oy = origin
        grids: dict[tuple[int, int], tuple[np.ndarray, np.ndarray]] = {}
        by_cell = {(p.sx, p.sy): p for p in patches if p.level == 0}

        def sample(x: int, y: int):
            sx, sy = min(x // 8, 31), min(y // 8, 31)
            patch = by_cell.get((sx, sy))
            if patch is None:
                return None
            if (sx, sy) not in grids:
                grids[(sx, sy)] = grid_samples(patch)
            z, n = grids[(sx, sy)]
            g = 9 * (x - 8 * sx) + (y - 8 * sy)
            return z[g], n[g]
        for cell in extras.grass:
            cx, cy = ox + 32 * cell.i + 16, oy + 32 * cell.j + 16
            if not keep(cx, cy):
                continue
            rng = np.random.default_rng([int(ox), int(oy), cell.i, cell.j])
            local, normals, params = [], [], []
            for s in cell.sets:
                if s.flag:
                    continue
                kind = self._kind(terra, s.layer, s.foliage)
                if kind is None:
                    continue
                lo, hi = self.kinds[kind]["scale"]
                for a, b in s.xy:
                    x, y = 32 * cell.i + int(a), 32 * cell.j + int(b)
                    hit = sample(x, y)
                    if hit is None:
                        continue
                    local.append((x, y, hit[0]))
                    normals.append(hit[1])
                    params.append((kind, rng.uniform(0, 2 * math.pi), rng.uniform(lo, hi), rng.uniform(0, 2 * math.pi)))
            if not local:
                continue
            pts = np.array(local, np.float64)
            self.cells[(region_path, cell.i, cell.j)] = {
                "p": (pts + np.array([ox, oy, 0.0]) + np.array(shift)).astype(np.float32), "local": pts,
                "slot": light_slot() if callable(light_slot) else light_slot, "n": np.array(normals, np.float32), "g": np.array(params, np.float32)}
        _, _, _, layers = self._terra(terra)
        if not extras.water:
            return
        splats = None
        for patch in extras.water:
            for x, y, i, j in patch.elements:
                ex0, ey0 = ox + patch.ox + i, oy + patch.oy + j
                if not keep_water(ex0 + 4, ey0 + 4):
                    continue
                if splats is None:
                    splats = region_splats(get, region_path)
                mat = extras.water_materials[patch.material] if patch.material < len(extras.water_materials) else (False, 0, 0)
                tile = splats[mat[1]] if mat[1] < len(splats) and splats[mat[1]] is not None else None
                key = (terra, patch.water)
                if key not in self.water:
                    self.water[key] = [[], [], []]
                    self.water_meta[key] = layers[patch.water] if patch.water < len(layers) else {}
                pos, tex, idx = self.water[key]
                base = sum(len(p) for p in pos)
                g = np.arange(WATER_GRID) * 8.0 / (WATER_GRID - 1)
                gx, gy = np.meshgrid(g, g, indexing="ij")
                # Hauteur : les quatre valeurs du carreau (égales dans toutes les régions lues),
                # mélangées en bilinéaire sur ses 32 m (ordre des coins supposé x puis y).
                h = patch.height
                u, v = np.clip((i + gx) / 32.0, 0, 1), np.clip((j + gy) / 32.0, 0, 1)
                z = (h[0] * (1 - u) + h[1] * u) * (1 - v) + (h[2] * (1 - u) + h[3] * u) * v
                p = np.stack([ex0 + gx, ey0 + gy, z], -1).reshape(-1, 3) + np.array(shift)
                pos.append(p.astype(np.float32))
                if tile is not None:
                    texels = tile[8 * x:8 * x + 8, 8 * y:8 * y + 8].reshape(-1, 3)
                else:
                    texels = np.tile([0.5, 0.5, 1.0], (WATER_GRID * WATER_GRID, 1))
                tex.append(np.round(np.column_stack([texels, np.ones(len(texels))]) * 255).astype(np.uint8))
                q = np.arange(WATER_GRID - 1)
                a0 = (q[:, None] * WATER_GRID + q[None, :]).reshape(-1)
                quads = np.stack([a0, a0 + WATER_GRID, a0 + 1, a0 + 1, a0 + WATER_GRID, a0 + WATER_GRID + 1], -1)
                idx.append((quads.reshape(-1) + base).astype(np.uint32))

    @property
    def tufts(self) -> int:
        return sum(len(c["p"]) for c in self.cells.values())

    @property
    def water_elements(self) -> int:
        return sum(len(p) for pos, _, _ in self.water.values() for p in pos)

    def emit(self, ex, lightuv=None) -> list[int]:
        """Nœuds glTF (`grass`, `water`) ajoutés à l'`Exporter` ; à passer à `finish`. `lightuv(points
        locaux, case)` place les pieds dans l'atlas de lumière cuite (−1 : sans cuisson)."""
        roots = []
        if self.cells and self.kinds:
            children = []
            for cell in self.cells.values():
                uv = (lightuv(cell["local"], cell["slot"]) if lightuv is not None and cell["slot"] is not None
                      else np.full((len(cell["p"]), 2), -1.0))
                prim = {"attributes": {
                    "POSITION": ex.gltf.add_accessor(cell["p"], "VEC3", "f32", target=34962, minmax=True),
                    "_GNORMAL": ex.gltf.add_accessor(quantize_normals(cell["n"]), "VEC4", "u8", normalized=True, target=34962),
                    "_GRASS": ex.gltf.add_accessor(quantize_tufts(cell["g"]), "VEC4", "u8", target=34962),
                    "_LIGHTUV": ex.gltf.add_accessor(quantize_uv(uv), "VEC2", "u16", normalized=True, target=34962)},
                    "mode": 0}
                ex.gltf.json["meshes"].append({"name": "grass", "primitives": [prim]})
                children.append(ex.gltf.add_node({"name": "grass_cell", "mesh": len(ex.gltf.json["meshes"]) - 1,
                                                  "extras": {"grassCell": True}}))
            roots.append(ex.gltf.add_node({"name": "grass", "children": children, "extras": {"grass": {
                "atlas": self.uri(self.atlas_name, GRASS_ATLAS_MAX), "kinds": self.kinds}}}))
        if self.water:
            children = []
            for key, (pos, tex, idx) in self.water.items():
                meta = dict(self.water_meta.get(key, {}))
                textures = meta.pop("textures", {}) or {}
                meta["textures"] = {k: self.uri(v, WATER_TEXTURE_MAX) if v else None for k, v in textures.items()}
                # Types d'eau sans texture de Fresnel ou de relief (`Kania_River`, `Ferris4`) : les
                # textures génériques du client, qu'aucune ressource ne cite (repli supposé du moteur).
                for k, v in WATER_DEFAULTS.items():
                    meta["textures"][k] = self.uri(v, WATER_TEXTURE_MAX)
                meta["sources"] = textures
                prim = {"attributes": {
                    "POSITION": ex.gltf.add_accessor(np.concatenate(pos), "VEC3", "f32", target=34962, minmax=True),
                    "_WATER": ex.gltf.add_accessor(np.concatenate(tex), "VEC4", "u8", normalized=True, target=34962)},
                    "indices": ex.gltf.add_accessor(np.concatenate(idx), "SCALAR", "u32", target=34963), "mode": 4}
                ex.gltf.json["meshes"].append({"name": f"water {meta.get('name') or key[1]}", "primitives": [prim]})
                children.append(ex.gltf.add_node({"name": "water_body", "mesh": len(ex.gltf.json["meshes"]) - 1,
                                                  "extras": {"water": meta}}))
            roots.append(ex.gltf.add_node({"name": "water", "children": children}))
        return roots
