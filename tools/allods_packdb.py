"""Lecture de la base de ressources compilée du client Allods Online (`Bin/pack.bin`).

Le client récent (RU 17.x, paks mis à jour en 2026) ne livre plus aucun `.xdb` : toutes les
ressources décrites en XML dans l'arbre serveur (géométries, textures, gabarits d'objets
visuels, scripts d'effets, réglages des fatalités…) sont compilées dans un seul fichier,
`Bin/pack.bin` du pak `BaseLocall_x64.pak`, compressé en zlib (≈ 75 Mo → 703 Mo). Ce module
en relit la structure, établie sur les données (septembre 2026) :

* **entête** : `u32 magic, u32 version, u32 hash, u32 ?, u64 ?` puis cinq couples
  `(u32 pointeur auto-relatif, u32 nombre)` en 0x18, 0x20, 0x28, 0x30, 0x38 et un sixième en
  0x40 : table de hachage des objets (65521 seaux), table des chemins racines (4081 seaux),
  table des **types** (1498 noms `struct NDb::…`), deux index id ↔ décalage (65521 seaux) et
  le début des **blocs** ;
* **blocs** : `u32 genre, u64 taille, charge utile`. Genre 3 = image mémoire des objets
  (« données »), genre 4 = **table de relocation** (`u64 emplacement | genre, u64 cible` par
  entrée), genre 5 = table annexe (non utilisée ici) ;
* **relocations** : les champs pointeurs de l'image valent 0 (ou des restes de mémoire) ;
  seule la table dit où ils pointent. Les trois bits bas de l'emplacement donnent le genre :
  0 = pointeur vers un objet ou une sous-structure, 3 = premier élément d'un vecteur (ou d'une
  chaîne), 4 = table virtuelle d'une **ressource** (la cible est l'indice de son type),
  5 = table virtuelle d'une structure polymorphe imbriquée (même codage), 2 = rare, ignoré ;
* **vecteurs** (et chaînes, qui en sont) : trois mots de 8 octets `premier, dernier, fin` à la
  MSVC ; seul `premier` est relogé, `dernier` et `fin` portent la taille et la capacité **en
  octets** (poids faible). Les éléments d'un vecteur de structures commencent par 8 octets
  inutilisés ;
* **disposition des champs** : l'ordre des champs est celui des éléments des `.xdb` (champs
  non booléens, puis booléens), mais les décalages ne se déduisent pas mécaniquement du
  schéma : chaque décodeur de `tools/allods_visdb.py` nomme les siens, vérifiés sur les
  ressources communes à l'arbre serveur 7.0 ;
* **fichiers binaires** : une ressource qui a un `.bin` (géométrie, texture, animation…) porte
  `(u32 code de pak, u32 rang dans le pak)` ; le rang est l'ordre du répertoire central du
  zip. La table code → pak n'existe pas dans les données lues : `PakCatalog` la reconstitue
  par vote (le nom trouvé au rang indiqué doit finir par le type de la ressource), ce qui
  suffit à nommer toutes les ressources.

La base est décompressée une fois dans un cache (`~/.cache/allodex`, ou `ALLODEX_CACHE`) puis
projetée en mémoire.
"""
from __future__ import annotations

import collections
import hashlib
import json
import mmap
import os
import struct
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

PACK_PAK = "BaseLocall_x64.pak"
PACK_ENTRY = "Bin/pack.bin"

# Emplacements des couples (pointeur auto-relatif, nombre) de l'entête.
HEADER_OBJECT_HASH = 0x18
HEADER_PATHS = 0x20
HEADER_TYPES = 0x28
HEADER_ID_TO_OFFSET = 0x30
HEADER_OFFSET_TO_ID = 0x38
HEADER_BLOCKS = 0x40

BLOCK_DATA = 3
BLOCK_RELOCATIONS = 4

RELOC_POINTER = 0
RELOC_VECTOR = 3
RELOC_RESOURCE = 4
RELOC_STRUCT = 5

# Décalage de la référence de fichier binaire `(code de pak, rang)` par type de ressource :
# les deux mots sont à 8 octets d'écart.
BINARY_REF = {
    "Geometry": 0x88,
    "ParticleAnimation": 0x88,
    "SkeletalAnimation": 0x98,
    "Texture": 0x40,
}
# Deuxième fichier d'une texture : la version haute résolution (`.hi.bin`, pak `*.HiRes`).
TEXTURE_HIRES_REF = 0x68


def default_cache_dir() -> Path:
    return Path(os.environ.get("ALLODEX_CACHE") or Path.home() / ".cache" / "allodex")


class PackDB:
    """Image de `pack.bin` décompressé : entête, types, relocations, lecture typée."""

    def __init__(self, raw) -> None:
        self.raw = raw
        self.types = self._read_types()
        self.data, data_size = self._find_block(BLOCK_DATA)
        reloc_at, count = self._find_block(BLOCK_RELOCATIONS)
        rel = np.frombuffer(self.raw, dtype="<u8", count=2 * count, offset=reloc_at).reshape(count, 2)
        loc = rel[:, 0]
        order = np.argsort(loc & ~np.uint64(7), kind="stable")
        self.rloc = (loc[order] & ~np.uint64(7)).astype(np.int64)
        self.rkind = (loc[order] & np.uint64(7)).astype(np.int8)
        self.rtgt = rel[order, 1].astype(np.int64)
        vt = (self.rkind == RELOC_RESOURCE) | (self.rkind == RELOC_STRUCT)
        self.vt_loc = self.rloc[vt]
        self.vt_type = self.rtgt[vt]
        res = self.rkind == RELOC_RESOURCE
        self.res_loc = self.rloc[res]
        self.res_type = self.rtgt[res]
        self.data_size = data_size
        self._paths: dict[str, int] | None = None

    # -- structure du fichier

    def _u32(self, off: int) -> int:
        return struct.unpack_from("<I", self.raw, off)[0]

    def _selfptr(self, off: int) -> tuple[int, int]:
        value, count = struct.unpack_from("<II", self.raw, off)
        return off + value, count

    def _read_types(self) -> list[str]:
        base, count = self._selfptr(HEADER_TYPES)
        out = []
        for i in range(count):
            e = base + 16 * i
            p, n = self._selfptr(e)
            name = bytes(self.raw[p:p + n]).split(b"\0")[0].decode("ascii", "replace")
            out.append(name.replace("struct NDb::", ""))
        return out

    def _find_block(self, kind: int) -> tuple[int, int]:
        """(début de la charge utile, taille ou nombre) du premier bloc du genre demandé."""
        off, _ = self._selfptr(HEADER_BLOCKS)
        while off + 12 <= len(self.raw):
            k = self._u32(off)
            size, = struct.unpack_from("<Q", self.raw, off + 4)
            if k == kind:
                return off + 12, size
            if k == BLOCK_DATA:
                off += 12 + size
            elif k == BLOCK_RELOCATIONS:
                off += 12 + 16 * size
            else:
                break
        raise ValueError(f"bloc {kind} introuvable dans pack.bin")

    @property
    def paths(self) -> dict[str, int]:
        """Chemins `.xdb` des ressources racines (≈ 500) → décalage dans les données."""
        if self._paths is None:
            base, buckets = self._selfptr(HEADER_PATHS)
            out: dict[str, int] = {}
            for b in range(buckets):
                p, n = self._selfptr(base + 8 * b)
                for k in range(n):
                    e = p + 16 * k
                    rec, length = self._selfptr(e)
                    offset, = struct.unpack_from("<Q", self.raw, e + 8)
                    name = bytes(self.raw[rec + 8:rec + length]).split(b"\0")[0].decode("latin1")
                    out[name] = offset
            self._paths = out
        return self._paths

    # -- lecture des données (décalages relatifs au bloc de données)

    def u32(self, off: int) -> int:
        return struct.unpack_from("<I", self.raw, self.data + off)[0]

    def i32(self, off: int) -> int:
        return struct.unpack_from("<i", self.raw, self.data + off)[0]

    def f32(self, off: int) -> float:
        return struct.unpack_from("<f", self.raw, self.data + off)[0]

    def floats(self, off: int, n: int) -> tuple[float, ...]:
        return struct.unpack_from(f"<{n}f", self.raw, self.data + off)

    def u8(self, off: int) -> int:
        return self.raw[self.data + off]

    def bytes(self, off: int, n: int) -> bytes:
        return bytes(self.raw[self.data + off:self.data + off + n])

    def reloc(self, loc: int) -> tuple[int, int] | None:
        i = int(np.searchsorted(self.rloc, loc))
        if i < len(self.rloc) and self.rloc[i] == loc:
            return int(self.rkind[i]), int(self.rtgt[i])
        return None

    def relocs(self, start: int, end: int) -> list[tuple[int, int, int]]:
        i = int(np.searchsorted(self.rloc, start))
        j = int(np.searchsorted(self.rloc, end))
        return [(int(self.rloc[k]), int(self.rkind[k]), int(self.rtgt[k])) for k in range(i, j)]

    def ptr(self, loc: int) -> int | None:
        """Cible d'un champ pointeur (None si nul)."""
        r = self.reloc(loc)
        return r[1] if r is not None and r[0] == RELOC_POINTER else None

    def vec(self, loc: int) -> tuple[int, int] | None:
        """(premier élément, taille en octets) d'un vecteur, None s'il est vide."""
        r = self.reloc(loc)
        if r is None or r[0] != RELOC_VECTOR:
            return None
        return r[1], self.u32(loc + 8)

    def string(self, loc: int) -> str | None:
        v = self.vec(loc)
        if v is None:
            return None
        target, size = v
        return self.bytes(target, size).split(b"\0")[0].decode("latin1")

    def pointers(self, loc: int) -> list[int]:
        """Vecteur de pointeurs : cibles non nulles, dans l'ordre."""
        v = self.vec(loc)
        if v is None:
            return []
        target, size = v
        out = []
        for k in range(size // 8):
            p = self.ptr(target + 8 * k)
            if p is not None:
                out.append(p)
        return out

    def elements(self, loc: int, stride: int) -> list[int]:
        """Décalages des éléments d'un vecteur de structures de `stride` octets."""
        v = self.vec(loc)
        if v is None:
            return []
        target, size = v
        return [target + stride * k for k in range(size // stride)]

    def vtype(self, off: int) -> str | None:
        """Type d'une ressource ou structure polymorphe commençant en `off`."""
        i = int(np.searchsorted(self.vt_loc, off))
        if i < len(self.vt_loc) and self.vt_loc[i] == off:
            return self.types[int(self.vt_type[i])]
        return None

    def resources(self, type_name: str) -> list[int]:
        ti = self.types.index(type_name)
        return self.res_loc[self.res_type == ti].tolist()

    def structs(self, type_name: str) -> list[int]:
        ti = self.types.index(type_name)
        mask = (self.rkind == RELOC_STRUCT) & (self.rtgt == ti)
        return self.rloc[mask].tolist()

    def binary_ref(self, off: int) -> tuple[int, int] | None:
        """(code de pak, rang) du fichier binaire principal d'une ressource."""
        field = BINARY_REF.get(self.vtype(off) or "")
        if field is None:
            return None
        return self.u32(off + field), self.u32(off + field + 8)


def open_pack(client_root: Path, cache_dir: Path | None = None) -> PackDB:
    """Ouvre `pack.bin` du client, décompressé une fois dans le cache puis projeté en mémoire."""
    pak = Path(client_root) / "data" / "Packs" / PACK_PAK
    cache_dir = Path(cache_dir or default_cache_dir())
    stat = pak.stat()
    key = hashlib.sha1(f"{pak}:{stat.st_size}:{int(stat.st_mtime)}".encode()).hexdigest()[:12]
    raw_path = cache_dir / f"pack-{key}.raw"
    if not raw_path.is_file():
        cache_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(pak) as zf:
            packed = zf.read(PACK_ENTRY)
        tmp = raw_path.with_suffix(".tmp")
        tmp.write_bytes(zlib.decompress(packed))
        tmp.replace(raw_path)
    handle = open(raw_path, "rb")
    return PackDB(mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ))


# --- paks et noms des fichiers binaires ------------------------------------------------------

@dataclass
class PakCatalog:
    """Répertoires des paks d'un client et table code → pak des références binaires."""

    packs_dir: Path
    names: dict[str, list[str]]
    codes: dict[int, str]

    def name(self, ref: tuple[int, int] | None) -> str | None:
        if ref is None:
            return None
        code, rank = ref
        pak = self.codes.get(code)
        if pak is None:
            return None
        listing = self.names.get(pak, [])
        return listing[rank] if 0 <= rank < len(listing) else None

    def pak_of(self, ref: tuple[int, int] | None) -> str | None:
        return None if ref is None else self.codes.get(ref[0])


def list_paks(packs_dir: Path) -> dict[str, list[str]]:
    """Répertoire central (ordre du zip) de chaque pak hors cartes (`*_000_000_512_512`)."""
    out: dict[str, list[str]] = {}
    for path in sorted(Path(packs_dir).glob("*.pak")):
        if "_000_000_512_512" in path.name:
            continue
        try:
            with zipfile.ZipFile(path) as zf:
                out[path.name] = [n.replace("\\", "/") for n in zf.namelist()]
        except (OSError, zipfile.BadZipFile):
            continue
    return out


def vote_pak_codes(db: PackDB, names: dict[str, list[str]], sample: int = 400) -> dict[int, str]:
    """Code de pak → nom du pak, par vote : pour chaque ressource à fichier binaire, les paks
    dont l'entrée au rang indiqué finit par `(<Type>).bin` gagnent une voix pour son code."""
    votes: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    by_code: dict[int, list[tuple[str, int]]] = collections.defaultdict(list)
    for type_name, field in BINARY_REF.items():
        suffix = f"({type_name}).bin"
        for off in db.resources(type_name):
            code, rank = db.u32(off + field), db.u32(off + field + 8)
            if len(by_code[code]) < sample:
                by_code[code].append((suffix, rank))
    for code, refs in by_code.items():
        for pak, listing in names.items():
            hits = sum(1 for suffix, rank in refs if rank < len(listing) and listing[rank].endswith(suffix))
            if hits:
                votes[code][pak] = hits
    out: dict[int, str] = {}
    for code, counter in votes.items():
        (pak, hits), = counter.most_common(1)
        if hits * 2 >= len(by_code[code]):  # majorité stricte des références échantillonnées
            out[code] = pak
    return out


def open_catalog(db: PackDB, client_root: Path, cache_dir: Path | None = None) -> PakCatalog:
    packs_dir = Path(client_root) / "data" / "Packs"
    names = list_paks(packs_dir)
    cache_dir = Path(cache_dir or default_cache_dir())
    digest = hashlib.sha1(json.dumps({k: len(v) for k, v in sorted(names.items())}).encode()).hexdigest()[:12]
    cache = cache_dir / f"pakcodes-{digest}.json"
    if cache.is_file():
        codes = {int(k): v for k, v in json.loads(cache.read_text()).items()}
    else:
        codes = vote_pak_codes(db, names)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({str(k): v for k, v in sorted(codes.items())}, indent=0))
    return PakCatalog(packs_dir, names, codes)
