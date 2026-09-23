"""Accès typé aux bases compilées du dernier client (17.x) : `Bin/pack.bin` et `Bin/Maps_<carte>.bin`.

Couche mince au-dessus de `tools/packbin.py` (lecteur générique repris tel quel de la branche des
talents, `worktree-agent-a98cc40ece7f9649d`, commit 1ad668d). Elle ajoute ce que les cartes
demandent :

* **deux bases liées** : chaque carte a sa propre base (`BaseLocall_x64.pak` → `Bin/Maps_<carte>.bin`,
  même format v2 que `pack.bin`) qui contient ses régions (`MapRegion`), ses objets propres et leurs
  géométries ; les objets communs (rochers, bâtiments, textures partagées) restent dans `pack.bin`.
  La table de relocation d'une carte a un genre de plus que celle de `pack.bin` : **genre 1 =
  pointeur vers un objet de `pack.bin`** (la cible est un décalage dans les données de `pack.bin`) ;
* **références `Ref`** (base, décalage) qui suivent ces pointeurs d'une base à l'autre ;
* **noms des fichiers binaires** (`.bin` de géométrie, texture, animation) : une ressource porte
  `(u32 code de pak, u32 rang dans le pak)` ; la table code → pak est le **bloc 6** de chaque base
  (liste des noms de paks, `PackBin.pak_names`), propre à chaque base. Le rang est l'ordre du
  répertoire central du zip.

Décalages de champs établis sur les données (septembre 2026), recoupés avec l'arbre serveur 7.0 :
voir `tools/extract_engine_cutscene.py`.
"""
from __future__ import annotations

import hashlib
import mmap
import os
import struct
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from tools.packbin import KIND_CLASS, KIND_DATA, KIND_PTR, PackBin, inflate

PACK_PAK = "BaseLocall_x64.pak"
# Décalage de la référence de fichier binaire `(code de pak, rang)` par type de ressource (les deux
# mots sont à 8 octets d'écart) ; relevés par la branche des fatalités (`tools/allods_packdb.py`).
BINARY_REF = {"Geometry": 0x88, "ParticleAnimation": 0x88, "SkeletalAnimation": 0x98, "Texture": 0x40}
TEXTURE_HIRES_REF = 0x68


def cache_dir() -> Path:
    return Path(os.environ.get("ALLODEX_CACHE") or Path.home() / ".cache" / "allodex")


class Base:
    """Une base compilée (`pack.bin` ou `Maps_<carte>.bin`) et, pour une carte, la base commune."""

    def __init__(self, pb: PackBin, name: str, packs_dir: Path, parent: "Base | None" = None) -> None:
        self.pb = pb
        self.name = name
        self.packs_dir = Path(packs_dir)
        self.parent = parent
        self.extern: dict[int, int] = self._extern_relocs() if parent is not None else {}
        self._listings: dict[str, list[str]] = {}

    def _extern_relocs(self) -> dict[int, int]:
        """Relocations de genre 1 (pointeurs vers `pack.bin`), ignorées par `PackBin` en mode 17.x."""
        raw, pb = self.pb.raw, self.pb
        rhdr = pb.base + pb.size
        _, count = struct.unpack_from("<IQ", raw, rhdr)
        rel = np.frombuffer(raw, dtype="<u8", count=2 * count, offset=rhdr + 12).astype(np.int64)
        loc, tgt = rel[0::2], rel[1::2]
        mask = (loc & 7) == 1
        return {int(a): int(t) for a, t in zip(loc[mask] & ~7, tgt[mask])}

    def ref(self, off: int | None) -> "Ref | None":
        return None if off is None else Ref(self, off)

    def paths(self) -> dict[str, "Ref"]:
        return {p: Ref(self, a) for p, a in self.pb.paths.items()}

    def objects(self, type_name: str) -> list["Ref"]:
        return [Ref(self, a) for a in self.pb.objects_of(type_name)]

    def listing(self, pak: str) -> list[str]:
        if pak not in self._listings:
            try:
                with zipfile.ZipFile(self.packs_dir / pak) as zf:
                    self._listings[pak] = [n.replace("\\", "/") for n in zf.namelist()]
            except (OSError, zipfile.BadZipFile):
                self._listings[pak] = []
        return self._listings[pak]

    def file_name(self, code: int, rank: int) -> str | None:
        if not 0 <= code < len(self.pb.pak_names):
            return None
        names = self.listing(self.pb.pak_names[code])
        return names[rank] if 0 <= rank < len(names) else None


@dataclass(frozen=True)
class Ref:
    """Objet ou champ d'une base : (base, décalage dans ses données)."""

    base: Base
    off: int

    def __add__(self, delta: int) -> "Ref":
        return Ref(self.base, self.off + delta)

    @property
    def type(self) -> str | None:
        return self.base.pb.type_at(self.off)

    def u32(self, rel: int = 0) -> int:
        return self.base.pb.u32(self.off + rel)

    def i32(self, rel: int = 0) -> int:
        return self.base.pb.i32(self.off + rel)

    def f32(self, rel: int = 0) -> float:
        return self.base.pb.f32(self.off + rel)

    def f64(self, rel: int = 0) -> float:
        pb = self.base.pb
        return struct.unpack_from("<d", pb.raw, pb.base + self.off + rel)[0]

    def floats(self, rel: int, n: int) -> tuple[float, ...]:
        pb = self.base.pb
        return struct.unpack_from(f"<{n}f", pb.raw, pb.base + self.off + rel)

    def bytes(self, rel: int, n: int) -> bytes:
        return bytes(self.base.pb.bytes_at(self.off + rel, n))

    def ptr(self, rel: int = 0) -> "Ref | None":
        """Pointeur d'objet : dans la même base, ou (genre 1) vers `pack.bin`, ou par identifiant."""
        at = self.off + rel
        pb = self.base.pb
        r = pb.reloc(at, KIND_PTR)
        if r is not None:
            return Ref(self.base, r.target)
        if at in self.base.extern and self.base.parent is not None:
            return Ref(self.base.parent, self.base.extern[at])
        r = pb.reloc(at, KIND_CLASS)
        if r is not None and r.target in pb.ids:
            return Ref(self.base, pb.ids[r.target])
        return None

    def vector(self, rel: int = 0) -> tuple["Ref | None", int]:
        """Vecteur `(premier, dernier, fin)` : (données, taille en octets)."""
        at = self.off + rel
        pb = self.base.pb
        r = pb.reloc(at, KIND_DATA)
        if r is None:
            return None, 0
        return Ref(self.base, r.target), pb.u32(at + 8)

    def elements(self, rel: int, stride: int) -> list["Ref"]:
        data, size = self.vector(rel)
        if data is None:
            return []
        return [data + stride * k for k in range(size // stride)]

    def pointers(self, rel: int) -> list["Ref"]:
        data, size = self.vector(rel)
        if data is None:
            return []
        out = []
        for k in range(size // 8):
            p = data.ptr(8 * k)
            if p is not None:
                out.append(p)
        return out

    def string(self, rel: int = 0) -> str | None:
        data, size = self.vector(rel)
        if data is None or size <= 0 or size > 1 << 20:
            return None
        return data.bytes(0, size).split(b"\0")[0].decode("utf-8", "replace")

    def binary(self, field: int | None = None) -> str | None:
        """Nom du fichier binaire (`X.(Geometry).bin`…) d'une ressource."""
        field = BINARY_REF.get(self.type or "") if field is None else field
        if field is None:
            return None
        return self.base.file_name(self.u32(field), self.u32(field + 8))

    def resource_id(self) -> int | None:
        for k, v in self.base.pb.ids.items():
            if v == self.off:
                return k
        return None


def _open_raw(path: Path):
    handle = open(path, "rb")
    return mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)


def open_pack(client: Path) -> Base:
    """`pack.bin` du client, décompressé une fois dans le cache (≈ 700 Mo) puis projeté en mémoire.
    Même clé de cache que la branche des fatalités (`pack-<empreinte>.raw`)."""
    packs = Path(client) / "data" / "Packs"
    pak = packs / PACK_PAK
    stat = pak.stat()
    key = hashlib.sha1(f"{pak}:{stat.st_size}:{int(stat.st_mtime)}".encode()).hexdigest()[:12]
    raw_path = cache_dir() / f"pack-{key}.raw"
    if not raw_path.is_file():
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(pak) as zf:
            data = zlib.decompress(zf.read("Bin/pack.bin"))
        tmp = raw_path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(raw_path)
    return Base(PackBin(_open_raw(raw_path)), "pack.bin", packs)


def open_map(pack: Base, map_name: str) -> Base:
    with zipfile.ZipFile(pack.packs_dir / PACK_PAK) as zf:
        raw = inflate(zf.read(f"Bin/Maps_{map_name}.bin"))
    return Base(PackBin(raw), f"Maps_{map_name}.bin", pack.packs_dir, parent=pack)


class PakFiles:
    """Lecture des fichiers des paks par nom (index construit à la demande, pak par pak)."""

    def __init__(self, packs_dir: Path) -> None:
        self.packs_dir = Path(packs_dir)
        self._zips: dict[str, zipfile.ZipFile] = {}
        self._index: dict[str, str] | None = None

    def _zip(self, pak: str) -> zipfile.ZipFile:
        if pak not in self._zips:
            self._zips[pak] = zipfile.ZipFile(self.packs_dir / pak)
        return self._zips[pak]

    def index(self) -> dict[str, str]:
        if self._index is None:
            out: dict[str, str] = {}
            for path in sorted(self.packs_dir.glob("*.pak")):
                try:
                    names = self._zip(path.name).namelist()
                except (OSError, zipfile.BadZipFile):
                    continue
                for n in names:
                    out.setdefault(n.replace("\\", "/"), path.name)
            self._index = out
        return self._index

    def get(self, name: str | None, pak: str | None = None) -> bytes | None:
        if not name:
            return None
        pak = pak or self.index().get(name)
        if pak is None:
            return None
        try:
            return self._zip(pak).read(name)
        except KeyError:
            return None
