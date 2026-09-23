"""Lecture des bases de ressources compilées d'Allods Online (`Bin/pack.bin`, `Bin/pack*.loc`).

Le client ne livre pas ses `.xdb` : le constructeur (`AOgame.exe -buildBinaries`) les sérialise
dans un unique `pack.bin` (zlib), image mémoire des structures C++ `NDb::*` dont les pointeurs
ont été remis à zéro et listés dans une table de relocalisation. Deux familles coexistent :

**v1 (clients 32 bits, 1.x → 11.x)** — suite de blocs `(u32 id, u32 taille)` :

* bloc 0 : 8 octets (empreinte de version, identique à l'en-tête du `pack.loc` apparié) ;
* bloc 1 : table des fichiers texte `(u32 8, u32 n)` puis `n × (ptr auto-relatif, u32 long., u32 id)`
  — `id` est l'indice du texte dans le `pack.loc` ;
* bloc 2 : quatre tables `(ptr, n)` : 65 521 alvéoles de hachage `chemin xdb → décalage` (entrées
  `(ptr, long., décalage)` vers `(u32 1, u32 empreinte, chemin\\0)`), la table des noms de types
  (`struct NDb::X`, dans l'ordre des indices de type), puis deux tables internes ;
* bloc 3 : les objets (décalages relatifs au début du bloc) ;
* bloc 4 : `n` couples `(u32 X, u32 T)` de relocalisation, `X = 2·adresse + drapeau` ; selon les deux
  bits bas de l'adresse : `…00`+0 = pointeur vers un objet, `…00`+1 = pointeur vers des données
  (chaîne, tableau), `…01` = type de l'objet commençant à `adresse-1` (T = indice de type ; drapeau
  0 pour un objet indexé par chemin, 1 pour un objet imbriqué), `…10`+1 = pointeur vers des données
  partagées, à `adresse-2` ;
* bloc 5 : liste des décalages d'objets.

**v2 (clients 64 bits, 15.x → 17.x)** — en-tête `u64, u32 empreinte, u32 2, u64 ptr(données)`, puis
5 (15/16) ou 6 (17) tables `(ptr, n)` et un compteur ; table 0 = identifiant d'objet → décalage
(les chemins ont disparu, sauf ~500 racines de la table 1), table 2 = noms de types. Le bloc de
données (`u32 3, u64 taille`) est suivi du bloc 4 (`u32 4, u64 n`, `n × (u64 X, u64 T)`) avec
`X = adresse + genre` : 0 = pointeur vers un objet, 3 = vers des données, 4 = type d'un objet
indexé, 5 = type d'un objet imbriqué, 2 = référence par identifiant d'objet (clé de la table 0 ;
la cible n'a pas toujours le type attendu, ces références sont traitées comme indices faibles).

`pack.loc` (v1 : blocs 0 = table `chemin → id`, 1 = `(u32 long., u32 décalage)` UTF-16, 2 = chaînes ;
v2 : `u32 empreinte, u32 0, u64 nb_mots`, `(u64 long., u64 décalage)`, puis `(u32 2, u64 taille)` et
les chaînes) donne le texte localisé d'un identifiant.
"""
from __future__ import annotations

import bisect
import struct
import zlib
from dataclasses import dataclass

import numpy as np

KIND_PTR = 0      # pointeur vers un objet (indexé ou imbriqué)
KIND_DATA = 1     # pointeur vers des données internes (chaîne, tableau)
KIND_TYPE = 2     # l'objet commençant à cette adresse a pour type T
KIND_CLASS = 3    # v2 (17.x) : référence par identifiant d'objet (clé de la table 0)


def inflate(data: bytes) -> bytes:
    try:
        return zlib.decompress(data)
    except zlib.error:
        return data


def _v1_relocs(x: np.ndarray, t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Codage `X = 2·adresse + drapeau` (v1, 15.x, 16.x) → clés normalisées `(adresse<<2)|genre`."""
    addr, flag = x >> 1, x & 1
    low = addr & 3
    kind = np.full(len(x), -1, dtype=np.int64)
    norm = addr.copy()
    kind[(low == 0) & (flag == 0)] = KIND_PTR
    kind[(low == 0) & (flag == 1)] = KIND_DATA
    m = (low == 1) | (low == 3)  # l'étiquette de type est à +1 ou +3 selon les versions
    kind[m] = KIND_TYPE
    norm[m] = addr[m] - low[m]
    m = (low == 2) & (flag == 1)
    kind[m] = KIND_DATA
    norm[m] = addr[m] - 2
    keep = kind >= 0
    return (norm[keep] << 2) | kind[keep], t[keep]


@dataclass
class Reloc:
    kind: int
    target: int


class PackBin:
    """Base compilée d'un client (`pack.bin` décompressé)."""

    def __init__(self, raw: bytes) -> None:
        self.raw = raw
        if raw[:8] == b"\0\0\0\0\x08\0\0\0":
            self.fmt = "v1"
            self.ptr_size = 4
            self._parse_v1()
        elif struct.unpack_from("<I", raw, 12)[0] == 2:
            self.fmt = "v2"
            self.ptr_size = 8
            self._parse_v2()
        else:  # pragma: no cover - format inconnu
            raise ValueError("format de pack.bin inconnu")
        order = np.argsort(self._rkeys, kind="stable")
        self._rkeys = self._rkeys[order]
        self._rtarget = self._rtarget[order]
        types = self._rkeys[(self._rkeys & 3) == KIND_TYPE]
        tt = self._rtarget[(self._rkeys & 3) == KIND_TYPE]
        self._obj_addr = (types >> 2).astype(np.int64)
        self._obj_type = tt.astype(np.int64)

    # --- v1 -------------------------------------------------------------------------------
    def _chunks_v1(self) -> dict[int, tuple[int, int]]:
        raw = self.raw
        out: dict[int, tuple[int, int]] = {}
        off = 0
        while off + 8 <= len(raw):
            cid, size = struct.unpack_from("<II", raw, off)
            if cid in out or cid > 16:
                break
            if cid == 4 or cid == 5:
                out[cid] = (off + 8, size)
                off += 8 + size * (8 if cid == 4 else 4)
                continue
            out[cid] = (off + 8, size)
            off += 8 + size
        return out

    def _parse_v1(self) -> None:
        raw = self.raw
        ch = self._chunks_v1()
        self.chunks = ch
        self.hash = raw[8:16]
        self.pak_names: list[str] = []
        U = lambda o: struct.unpack_from("<I", raw, o)[0]  # noqa: E731
        # textes
        st, _ = ch[1]
        _, cnt = struct.unpack_from("<II", raw, st)
        base = st + 8
        self.text_paths: dict[str, int] = {}
        for i in range(cnt):
            e = base + 12 * i
            o, ln, tid = struct.unpack_from("<III", raw, e)
            self.text_paths[raw[e + o:e + o + ln].split(b"\0")[0].decode("utf-8", "replace")] = tid
        # chemins + types
        st2, _ = ch[2]
        tbl = st2 + U(st2)
        nb = U(st2 + 4)
        self.paths: dict[str, int] = {}
        for b in range(nb):
            e = tbl + 8 * b
            bp, bc = e + U(e), U(e + 4)
            for j in range(bc):
                x = bp + 12 * j
                rec = x + U(x)
                ln, val = U(x + 4), U(x + 8)
                path = raw[rec + 8:rec + 8 + ln].split(b"\0")[0].decode("utf-8", "replace")
                self.paths[path] = val
        p = st2 + 8
        tt, tn = p + U(p), U(p + 4)
        self.types = []
        for i in range(tn):
            e = tt + 12 * i
            o, ln, _ = struct.unpack_from("<III", raw, e)
            self.types.append(raw[e + o:e + o + ln].split(b"\0")[0].decode().replace("struct NDb::", ""))
        self.base, self.size = ch[3]
        rst, rn = ch[4]
        a = np.frombuffer(raw, dtype=np.uint32, count=rn * 2, offset=rst).astype(np.int64)
        self._rkeys, self._rtarget = _v1_relocs(a[0::2], a[1::2])
        self.ids: dict[int, int] = {}

    # --- v2 -------------------------------------------------------------------------------
    def _parse_v2(self) -> None:
        raw = self.raw
        U = lambda o: struct.unpack_from("<I", raw, o)[0]  # noqa: E731
        self.hash = raw[8:12]
        data_hdr = 0x10 + struct.unpack_from("<Q", raw, 0x10)[0]
        tabs = []
        k = 0
        while 0x18 + 8 * k < data_hdr:
            p = 0x18 + 8 * k
            ptr, cnt = U(p), U(p + 4)
            if ptr == 0 or p + ptr >= data_hdr + 8:
                break
            tabs.append((p + ptr, cnt))
            k += 1
            if len(tabs) >= 5 and cnt == 0:
                break
        self.tables = tabs
        # table 0 : identifiant → décalage
        tbl, cnt = tabs[0]
        self.ids = {}
        for b in range(cnt):
            e = tbl + 8 * b
            bp, bc = e + U(e), U(e + 4)
            for j in range(bc):
                x = bp + 16 * j
                rec = x + U(x)
                val = struct.unpack_from("<Q", raw, x + 8)[0]
                self.ids[U(rec + 4)] = val
        # table 1 : quelques chemins racines
        tbl, cnt = tabs[1]
        self.paths = {}
        for b in range(cnt):
            e = tbl + 8 * b
            bp, bc = e + U(e), U(e + 4)
            for j in range(bc):
                x = bp + 16 * j
                rec = x + U(x)
                ln = U(x + 4)
                val = struct.unpack_from("<Q", raw, x + 8)[0]
                path = raw[rec + 8:rec + 8 + ln].split(b"\0")[0].decode("utf-8", "replace")
                self.paths[path] = val
        tbl, cnt = tabs[2]
        self.types = []
        for i in range(cnt):
            e = tbl + 16 * i
            o, ln = U(e), U(e + 4)
            self.types.append(raw[e + o:e + o + ln].split(b"\0")[0].decode().replace("struct NDb::", ""))
        cid, size = struct.unpack_from("<IQ", raw, data_hdr + 8)
        assert cid == 3, cid
        self.base = data_hdr + 0x14
        self.size = size
        rhdr = self.base + size
        cid, rn = struct.unpack_from("<IQ", raw, rhdr)
        assert cid == 4, cid
        a = np.frombuffer(raw, dtype=np.uint64, count=rn * 2, offset=rhdr + 12).astype(np.int64)
        self.pak_names = self._pak_names_v2(rhdr + 12 + rn * 16)
        x, t = a[0::2], a[1::2]
        genre = x & 7
        self.text_paths = {}
        kind = np.full(len(x), -1, dtype=np.int64)
        if not np.any(genre == 4):
            # 15.x / 16.x : X = 8·adresse + genre (0 objet, 1 données, 2 type indexé, 3 type imbriqué).
            addr = x >> 3
            kind[genre == 0] = KIND_PTR
            kind[genre == 1] = KIND_DATA
            kind[(genre == 2) | (genre == 3)] = KIND_TYPE
        else:
            # 17.x : X = adresse + genre (0 objet, 3 données, 4/5 type, 2 référence par identifiant).
            addr = x & ~7
            kind[genre == 0] = KIND_PTR
            kind[genre == 3] = KIND_DATA
            kind[(genre == 4) | (genre == 5)] = KIND_TYPE
            kind[genre == 2] = KIND_CLASS
        keep = kind >= 0
        self._rkeys = (addr[keep] << 2) | kind[keep]
        self._rtarget = t[keep]

    def _pak_names_v2(self, off: int) -> list[str]:
        """Blocs 5 (décalages) puis 6 : noms des paks (UTF-16) indexés par les `UITexture`."""
        raw = self.raw
        names: list[str] = []
        while off + 12 <= len(raw):
            cid, n = struct.unpack_from("<IQ", raw, off)
            off += 12
            if cid == 5:
                off += 8 * n
                continue
            if cid == 6:
                for _ in range(n):
                    ln = struct.unpack_from("<Q", raw, off)[0]
                    names.append(raw[off + 8:off + 8 + ln].decode("utf-16-le", "replace"))
                    off += 8 + ln
            break
        return names

    # --- accès ----------------------------------------------------------------------------
    def reloc(self, addr: int, kind: int | None = None) -> Reloc | None:
        """Relocalisation posée sur le champ à `addr` (décalage dans le bloc de données)."""
        kinds = (KIND_PTR, KIND_DATA, KIND_CLASS) if kind is None else (kind,)
        for k in kinds:
            key = (addr << 2) | k
            i = int(np.searchsorted(self._rkeys, key))
            if i < len(self._rkeys) and int(self._rkeys[i]) == key:
                return Reloc(k, int(self._rtarget[i]))
        return None

    def type_at(self, addr: int) -> str | None:
        rel = self.reloc(addr, KIND_TYPE)
        if rel is None or rel.target >= len(self.types):
            return None
        return self.types[rel.target]

    def objects_of(self, type_name: str) -> list[int]:
        """Adresses de tous les objets (indexés ou imbriqués) du type donné."""
        try:
            ti = self.types.index(type_name)
        except ValueError:
            return []
        return sorted(int(a) for a in self._obj_addr[self._obj_type == ti])

    def object_bounds(self) -> np.ndarray:
        return np.sort(self._obj_addr)

    def u8(self, a: int) -> int:
        return self.raw[self.base + a]

    def u32(self, a: int) -> int:
        return struct.unpack_from("<I", self.raw, self.base + a)[0]

    def i32(self, a: int) -> int:
        return struct.unpack_from("<i", self.raw, self.base + a)[0]

    def u64(self, a: int) -> int:
        return struct.unpack_from("<Q", self.raw, self.base + a)[0]

    def f32(self, a: int) -> float:
        return struct.unpack_from("<f", self.raw, self.base + a)[0]

    def word(self, a: int) -> int:
        return self.u64(a) if self.ptr_size == 8 else self.u32(a)

    def bytes_at(self, a: int, n: int) -> bytes:
        return self.raw[self.base + a:self.base + a + n]

    def ptr(self, a: int) -> int | None:
        """Cible d'un pointeur d'objet posé en `a` (None si nul)."""
        rel = self.reloc(a, KIND_PTR)
        return rel.target if rel else None

    def data_ptr(self, a: int) -> int | None:
        rel = self.reloc(a, KIND_DATA)
        return rel.target if rel else None

    def vector(self, a: int) -> tuple[int | None, int]:
        """Tableau `(ptr, taille_octets, capacité)` posé en `a` → (adresse des données, octets)."""
        size = self.word(a + self.ptr_size)
        return self.data_ptr(a), size

    def string(self, a: int) -> str | None:
        """Chaîne `(ptr, longueur, capacité)` posée en `a`."""
        target = self.data_ptr(a)
        n = self.word(a + self.ptr_size)
        if target is None or n <= 0 or n > 1 << 20:
            return None if target is None else ""
        return self.bytes_at(target, n).split(b"\0")[0].decode("utf-8", "replace")

    def path_of(self) -> dict[int, str]:
        return {v: k for k, v in self.paths.items()}


class LocTable:
    """Textes localisés (`pack.loc`, `pack.<langue>.loc`) : identifiant → chaîne."""

    def __init__(self, raw: bytes) -> None:
        self.raw = raw
        self.paths: dict[str, int] = {}
        if raw[:8] == b"\0\0\0\0" + raw[4:8] and struct.unpack_from("<I", raw, 8)[0] == 8:
            self._parse_v1()
        else:
            self._parse_v2()

    def _parse_v1(self) -> None:
        raw = self.raw
        _, size0 = struct.unpack_from("<II", raw, 0)
        _, cnt = struct.unpack_from("<II", raw, 8)
        base = 16
        for i in range(cnt):
            e = base + 12 * i
            o, ln, tid = struct.unpack_from("<III", raw, e)
            self.paths[raw[e + o:e + o + ln].split(b"\0")[0].decode("utf-8", "replace")] = tid
        c1 = 8 + size0
        cid, nwords = struct.unpack_from("<II", raw, c1)
        self.table = c1 + 8
        self.entry = 8
        self.count = nwords // 2
        self.fmt = "<II"
        self.strings = self.table + nwords * 4 + 8

    def _parse_v2(self) -> None:
        raw = self.raw
        nwords = struct.unpack_from("<Q", raw, 8)[0]
        self.table = 16
        self.entry = 16
        self.count = nwords // 2
        self.fmt = "<QQ"
        self.strings = self.table + nwords * 8 + 12

    def get(self, tid: int) -> str | None:
        if tid is None or tid < 0 or tid >= self.count:
            return None
        ln, off = struct.unpack_from(self.fmt, self.raw, self.table + self.entry * tid)
        if ln == 0:
            return ""
        s = self.raw[self.strings + off:self.strings + off + 2 * ln]
        return s.decode("utf-16-le", "replace")

    def by_path(self, path: str) -> str | None:
        tid = self.paths.get(path)
        return None if tid is None else self.get(tid)
