#!/usr/bin/env python3
"""Textes de lore officiels d'Allods Online (préparation de la page « Lorebook », cible : anglais).

Sources (voir `tools/lore_manifest.json`) :

* **dernier client officiel** (`AllodsRU`, 17.0) — `Texts_x64.pak` contient `pack.rus.loc` et
  `pack.eng_eu.loc` : deux tables **alignées index par index** (même empreinte de build). L'anglais
  est celui de l'édition européenne (il se retrouve à l'identique dans les packs officiels EU 16.0) ;
  une entrée restée en cyrillique n'a pas de traduction officielle.
* **`Bin/pack.bin`** (dans `BaseLocall_x64.pak`) — base de ressources compilée. Elle ne contient pas
  les chemins, mais chaque ressource y pointe ses textes par leur index dans les `.loc` : on sait ainsi
  quelle ressource porte quel texte, à quel décalage, et on regroupe les textes (une quête = nom,
  objectif, textes de début/fin ; une page de livre = titre + texte).
* **arbre serveur** (xdb + .txt, étiqueté 7.0, contenus jusqu'à ZC14) — donne, pour les contenus qui
  y figurent, le chemin de ressource, le type (balise racine du xdb) et le champ de chaque texte. Le
  `resourceId` des xdb est la clé de la table S3 de `pack.bin` : c'est le pont exact serveur ↔ client.
  Pour les ressources plus récentes, le type est **déduit** de la disposition binaire (classifieur
  bayésien naïf appris sur les ressources connues ; précision mesurée avec `--evaluate`).
* **packs EU officiels** (en + fr, alignés) — pont anglais → français : le français n'est retenu que
  si l'anglais du client 17.0 est identique à celui du pack EU.
* **corpus communautaire** (`refs/lorebook`, git-ignoré) — jamais recopié : chaque texte russe est
  découpé en phrases normalisées, apparié aux textes du client, puis classé (`in-game (official EN
  available)`, `in-game (RU/FR only)`, `official out-of-game (announcement/FAQ)`, `community`).

Formats décodés :

* `.loc` (zlib) : `u32 empreinte, u32 0, u64 2×N`, puis N × `(u64 longueur, u64 décalage)`, puis
  `u32 1, u64 taille` et le bloc de chaînes UTF-16LE (décalages relatifs au bloc). Dans le texte,
  `<t href="HEX"/>` insère le texte d'index `int.from_bytes(bytes.fromhex(HEX), "little")`.
* `pack.bin` (zlib) : `u32 ?, u32 ?, u32 empreinte (= celle des .loc), u32 2, u64 taille de l'index`
  (= début du corps), puis six sections `(u32 pointeur auto-relatif, u32 nombre)` : S0 table de
  hachage (65521 seaux) `clé 9 o (u32 1, u32 rid, u8 0) → u64 décalage dans le corps`, S1 chemins
  (519 ressources racines), S2 noms des 1498 structures, S3 `resourceId → décalage`, S4 l'inverse,
  S5 le corps. Un seau = `(u32 pointeur, u32 nombre)` vers des éléments de 16 o. Une référence de
  texte dans une ressource = `u32 index` aligné sur 4 suivi d'un `u32 0`.

Sorties dans `public/game/lore/` : `index.json` (sources, méthode, couverture, poids), un fichier
par catégorie (`quests`, `dialogues`, `library`, `scenes`, `events`, `places`, `characters`,
`factions`, `mail`, `secrets`) qui porte l'anglais et les métadonnées (ressource, type, ère, statut de
l'anglais), les tables `loc → texte` russe (`ru/<catégorie>.json`) et française (`fr/<catégorie>.json`),
`series.json` (documents en plusieurs pages), `glossary.json` (russe → anglais officiel),
`community.json` (classement du corpus, par chemin) et `atlas.json` (allods de l'atlas ↔ client).
"""
from __future__ import annotations

import argparse
import bisect
import collections
import html
import json
import re
import struct
import subprocess
import sys
import threading
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path
# Données de jeu locales et de confiance (xdb de l'arbre serveur) : pas d'entrées externes.
from xml.etree import ElementTree as ET

import numpy as np

if __package__ in (None, ""):  # exécution directe : `python3 tools/extract_lore.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.extract_menu_scene import BinSource  # noqa: E402  (lecture des membres de pak)

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE / "lore_manifest.json"
DEFAULT_OUT = HERE.parent / "public" / "game" / "lore"

CYRILLIC = re.compile(r"[А-Яа-яЁё]")
HREF = re.compile(r'<t\s+href="([0-9A-Fa-f]*)"\s*/>')
HREF_ANY = re.compile(r'<t\s+href="[^"]*"\s*/>')
TAG = re.compile(r"<[^>]*>")
RVAR = re.compile(r'<r\s+name="([^"]*)"\s*/>')

MIN_REF = 300            # sous ce seuil, un u32 est trop souvent un petit entier : second passage typé
MAX_REGION = 1_000_000   # régions de plus d'1 Mo = tables globales (index de textes…), pas des ressources
SUPPORT_WINDOW = 6       # deux textes d'une même ressource sont voisins dans l'ordre des chemins


# --- .loc ------------------------------------------------------------------------------------

def parse_loc(data: bytes) -> tuple[int, list[str]]:
    """`.loc` (compressé ou non) → (empreinte de build, textes)."""
    try:
        raw = zlib.decompress(data)
    except zlib.error:
        raw = data
    fingerprint, _, doubled = struct.unpack_from("<IIQ", raw, 0)
    count = doubled // 2
    table = 16
    end = table + count * 16
    one, size = struct.unpack_from("<IQ", raw, end)
    base = end + 12
    if one != 1 or base + size != len(raw):
        raise ValueError("format .loc inattendu")
    texts = []
    for i in range(count):
        length, offset = struct.unpack_from("<QQ", raw, table + i * 16)
        texts.append(raw[base + offset: base + offset + length * 2].decode("utf-16le"))
    return fingerprint, texts


def build_loc(texts: list[str], fingerprint: int = 0x5E102AA3) -> bytes:
    """Inverse de `parse_loc` (tests) : chaînes alignées sur 8 octets, terminées par un NUL."""
    blob = bytearray()
    table = bytearray()
    for s in texts:
        off = len(blob)
        enc = s.encode("utf-16le") + b"\0\0"
        blob += enc + b"\0" * (-len(enc) % 8)
        table += struct.pack("<QQ", len(s), off)
    return zlib.compress(struct.pack("<IIQ", fingerprint, 0, 2 * len(texts)) + bytes(table)
                         + struct.pack("<IQ", 1, len(blob)) + bytes(blob))


def href_index(hexstr: str) -> int:
    return int.from_bytes(bytes.fromhex(hexstr), "little") if hexstr else -1


def render(index: int, texts: list[str], depth: int = 0, seen: frozenset = frozenset()) -> str:
    """Texte lisible : références `<t href>` résolues, HTML du jeu → texte brut, variables → `{nom}`."""
    s = texts[index] if 0 <= index < len(texts) else ""

    def sub(m: re.Match) -> str:
        j = href_index(m.group(1)) if len(m.group(1)) % 2 == 0 else -1
        if depth >= 6 or j in seen or not 0 <= j < len(texts):
            return ""
        return render(j, texts, depth + 1, seen | {index})

    s = HREF.sub(sub, s)
    if depth:
        return s
    return to_plain(s)


def to_plain(s: str) -> str:
    s = RVAR.sub(lambda m: "{" + m.group(1) + "}", s)
    s = re.sub(r"<br\s*/?>|</p>|</?li>", "\n", s, flags=re.I)
    s = TAG.sub("", s)
    s = html.unescape(s).replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def en_status(raw_en: str, rendered_en: str) -> str:
    """`official` : traduction officielle complète ; `partial` : un fragment inséré reste en russe ;
    `missing` : pas de traduction (vide ou cyrillique)."""
    if not rendered_en or CYRILLIC.search(HREF_ANY.sub("", raw_en or "")) or not (raw_en or "").strip():
        return "missing"
    return "partial" if CYRILLIC.search(rendered_en) else "official"


def norm_key(s: str) -> str:
    """Clé d'égalité de contenu entre builds : les `href` changent d'un build à l'autre."""
    return HREF_ANY.sub("<t/>", s).replace("\r\n", "\n").strip()


# --- pack.bin --------------------------------------------------------------------------------

@dataclass
class PackIndex:
    fingerprint: int
    body: int                        # début du corps (octets)
    rid_offset: dict[int, int]       # rid (S0) → décalage dans le corps
    key_offset: dict[int, int]       # resourceId (S3) → décalage
    offsets: np.ndarray = field(default=None)   # décalages triés
    rids: np.ndarray = field(default=None)      # rid correspondant
    sizes: np.ndarray = field(default=None)     # taille de région (jusqu'à la ressource suivante)
    offset_key: dict[int, int] = field(default_factory=dict)   # décalage → resourceId

    def finalize(self, body_len: int) -> None:
        pairs = sorted((o, r) for r, o in self.rid_offset.items())
        self.offsets = np.array([o for o, _ in pairs], dtype=np.int64)
        self.rids = np.array([r for _, r in pairs], dtype=np.int64)
        nxt = np.append(self.offsets[1:], body_len)
        self.sizes = nxt - self.offsets
        self.offset_key = {o: k for k, o in self.key_offset.items()}


def _section(raw: bytes, hdr: int) -> tuple[int, int]:
    rel, count = struct.unpack_from("<II", raw, hdr)
    return hdr + rel, count


def _buckets(raw: bytes, base: int, count: int):
    for b in range(count):
        o = base + b * 8
        rel, n = struct.unpack_from("<II", raw, o)
        items = o + rel
        for k in range(n):
            yield items + k * 16


def parse_pack(raw: bytes) -> PackIndex:
    """En-tête et tables S0/S3 de `pack.bin` décompressé (voir la docstring du module)."""
    _, _, fingerprint, _, body = struct.unpack_from("<IIIIQ", raw, 0)
    rid_offset: dict[int, int] = {}
    base, count = _section(raw, 0x18)
    for io in _buckets(raw, base, count):
        krel, klen, value = struct.unpack_from("<IIQ", raw, io)
        key = raw[io + krel: io + krel + klen]
        if klen == 9 and key[:4] == b"\x01\0\0\0":
            rid_offset[struct.unpack_from("<I", key, 4)[0]] = value
    key_offset: dict[int, int] = {}
    base, count = _section(raw, 0x30)
    for io in _buckets(raw, base, count):
        key, value = struct.unpack_from("<QQ", raw, io)
        key_offset[key] = value
    index = PackIndex(fingerprint, body, rid_offset, key_offset)
    index.finalize(len(raw) - body)
    return index


def scan_refs(raw: bytes, index: PackIndex, n_texts: int, min_ref: int = MIN_REF,
              max_region: int = MAX_REGION) -> dict[str, np.ndarray]:
    """Toutes les références de texte candidates : `u32 v < N` aligné sur 4, suivi d'un `u32 0`,
    dans une ressource de taille raisonnable. Renvoie des tableaux parallèles triés par (rid, v)."""
    words = np.frombuffer(raw, dtype="<u4", offset=index.body, count=(len(raw) - index.body) // 4)
    pos = np.nonzero((words[:-1] < n_texts) & (words[:-1] >= min_ref) & (words[1:] == 0))[0]
    vals = words[pos].astype(np.int64)
    byte = pos.astype(np.int64) * 4
    j = np.searchsorted(index.offsets, byte, side="right") - 1
    keep = j >= 0
    byte, vals, j = byte[keep], vals[keep], j[keep]
    rel = byte - index.offsets[j]
    keep = (index.sizes[j] <= max_region) & (rel < index.sizes[j])
    rid, vals, rel = index.rids[j][keep], vals[keep], rel[keep]
    order = np.lexsort((vals, rid))
    return {"rid": rid[order], "val": vals[order], "rel": rel[order]}


def support(refs: dict[str, np.ndarray], window: int = SUPPORT_WINDOW, span: int = 12) -> np.ndarray:
    """Nombre de voisins proches (|Δindex| ≤ window) dans la même ressource : les textes d'une
    ressource se suivent dans les .loc (triés par chemin), les faux positifs sont isolés."""
    rid, val = refs["rid"], refs["val"]
    out = np.zeros(len(rid), dtype=np.int32)
    for k in range(1, span):
        same = (rid[k:] == rid[:-k]) & ((val[k:] - val[:-k]) <= window)
        out[k:] += same
        out[:-k] += same
    return out


def pick_owners(refs: dict[str, np.ndarray], sup: np.ndarray, sizes: dict[int, int] | None = None
                ) -> dict[int, tuple[int, int, int]]:
    """Pour chaque texte : la ressource qui le porte = meilleur soutien, puis région la plus petite,
    puis décalage le plus faible. → {index: (rid, soutien, décalage)}."""
    rid, val, rel = refs["rid"], refs["val"], refs["rel"]
    size = np.array([sizes.get(int(r), 0) for r in rid], dtype=np.int64) if sizes else np.zeros(len(rid), np.int64)
    order = np.lexsort((rel, size, -sup, val))
    v2 = val[order]
    first = np.ones(len(v2), dtype=bool)
    first[1:] = v2[1:] != v2[:-1]
    sel = order[first]
    return {int(val[i]): (int(rid[i]), int(sup[i]), int(rel[i])) for i in sel}


def word_shape(raw: bytes, start: int, size: int, n: int = 48) -> tuple[int, ...]:
    """Silhouette des premiers mots d'une ressource (0, 1.0f, petit entier, -1, autre)."""
    count = min(size, n * 4) // 4
    out = []
    for w in struct.unpack_from("<%dI" % count, raw, start):
        out.append(0 if w == 0 else 1 if w == 0x3F800000 else 2 if w < 256 else 3 if w == 0xFFFFFFFF else 4)
    return tuple(out)


class LayoutClassifier:
    """Bayésien naïf : type de ressource ← décalages de ses textes + silhouette binaire.

    Tous les types connus sont évalués (matrice log-probabilités types × traits, en numpy)."""

    def __init__(self, alpha: float = 0.1) -> None:
        self.alpha = alpha
        self.labels: list[str] = []
        self.vocab: dict[str, int] = {}

    @staticmethod
    def features(rels: list[int], shape: tuple[int, ...]) -> list[str]:
        fs = ["o%d" % r for r in sorted(set(rels)) if r < 4096]
        fs += ["w%d=%d" % (i, v) for i, v in enumerate(shape)]
        fs.append("n%d" % min(len(rels), 6))
        return fs

    def fit(self, samples: list[tuple[list[str], str]]) -> "LayoutClassifier":
        prior: collections.Counter = collections.Counter(label for _, label in samples)
        self.labels = sorted(prior)
        lab = {l: k for k, l in enumerate(self.labels)}
        for feats, _ in samples:
            for f in feats:
                self.vocab.setdefault(f, len(self.vocab))
        counts = np.zeros((len(self.labels), len(self.vocab)), dtype=np.float64)
        for feats, label in samples:
            counts[lab[label], [self.vocab[f] for f in feats]] += 1
        n = np.array([prior[l] for l in self.labels], dtype=np.float64)[:, None]
        self.logp = np.log((counts + self.alpha) / (n + 1))
        self.logprior = np.log(n[:, 0] / n.sum())
        # un trait « décalage de texte » jamais vu pour un type le pénalise fortement (disposition fixe)
        self.offset_cols = np.array([f.startswith("o") for f in self.vocab], dtype=bool)
        return self

    def predict_many(self, samples: list[list[str]]) -> list[tuple[str | None, float]]:
        out = []
        for feats in samples:
            cols = [self.vocab[f] for f in feats if f in self.vocab]
            ocols = [c for c in cols if self.offset_cols[c]]
            if not ocols:
                out.append((None, 0.0))
                continue
            scores = self.logprior + self.logp[:, cols].sum(axis=1)
            k = int(np.argmax(scores))
            z = np.exp(scores - scores[k]).sum()
            out.append((self.labels[k], float(1.0 / z)))
        return out

    def predict(self, feats: list[str]) -> tuple[str | None, float]:
        return self.predict_many([feats])[0]


# --- arbre serveur ---------------------------------------------------------------------------

def decode_text_file(b: bytes) -> str:
    if b.startswith(b"\xff\xfe"):
        return b[2:].decode("utf-16le", "replace")
    if b.startswith(b"\xfe\xff"):
        return b[2:].decode("utf-16be", "replace")
    if b.startswith(b"\xef\xbb\xbf"):
        return b[3:].decode("utf-8", "replace")
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp1251", "replace")


RESOURCE_ID = re.compile(rb"<resourceId>(\d+)</resourceId>")
ROOT_TAG = re.compile(rb"<([A-Za-z_][\w.]*)[\s/>]")


def xdb_text_refs(xdb: str, data: bytes) -> tuple[str | None, int | None, list[tuple[str, str]]]:
    """Balise racine, resourceId et `(chemin .txt, chemin d'élément)` de chaque texte d'un xdb."""
    head = data[:800].split(b"?>", 1)[-1]
    m = ROOT_TAG.search(head)
    root = m.group(1).decode() if m else None
    m = RESOURCE_ID.search(data[:800])
    rid = int(m.group(1)) if m else None
    refs: list[tuple[str, str]] = []
    if b".txt" not in data:
        return root, rid, refs
    try:
        tree = ET.fromstring(data)
    except ET.ParseError:
        return root, rid, refs
    folder = xdb.rsplit("/", 1)[0] if "/" in xdb else ""

    def walk(el, chain):
        for ch in el:
            c2 = chain + (ch.tag,)
            href = ch.get("href")
            if href and ".txt" in href:
                target = href.split("#")[0]
                target = target.lstrip("/") if target.startswith("/") else (folder + "/" + target if folder else target)
                refs.append((target, "/".join(c2)))
            walk(ch, c2)

    walk(tree, ())
    return root, rid, refs


class ServerTree:
    """Arbre serveur : textes (.txt) par chemin et métadonnées des xdb. Lecture par `git cat-file`
    quand l'arbre est un dépôt (≈ 10 s pour 700 000 fichiers), sinon parcours du disque."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.texts: dict[str, str] = {}
        self.resources: dict[int, tuple[str, str]] = {}          # resourceId → (xdb, type court)
        self.text_owners: dict[str, list[tuple[str, str, str]]] = collections.defaultdict(list)
        self.xdb_fields: dict[str, dict[str, str]] = collections.defaultdict(dict)   # xdb → champ → .txt

    def _git_blobs(self, pattern: str):
        listing = subprocess.run(["git", "-C", str(self.root), "ls-files", "-s", "--", pattern],
                                 check=True, capture_output=True).stdout.decode("utf-8", "surrogateescape")
        entries = []
        for line in listing.splitlines():
            meta, path = line.split("\t", 1)
            entries.append((path, meta.split()[1]))
        proc = subprocess.Popen(["git", "-C", str(self.root), "cat-file", "--batch"],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=1 << 20)

        def feed():
            for _, sha in entries:
                proc.stdin.write((sha + "\n").encode())
            proc.stdin.close()

        threading.Thread(target=feed, daemon=True).start()
        for path, _ in entries:
            header = proc.stdout.readline().split()
            if len(header) < 3 or header[1] == b"missing":
                continue
            data = proc.stdout.read(int(header[2]))
            proc.stdout.read(1)
            yield path, data
        proc.wait()

    def _disk_blobs(self, suffix: str):
        for p in self.root.rglob("*" + suffix):
            yield p.relative_to(self.root).as_posix(), p.read_bytes()

    def load(self) -> "ServerTree":
        use_git = (self.root / ".git").exists()
        blobs = (lambda pat, suf: self._git_blobs(pat)) if use_git else (lambda pat, suf: self._disk_blobs(suf))
        for path, data in blobs("*.txt", ".txt"):
            self.texts[path] = decode_text_file(data)
        for path, data in blobs("*.xdb", ".xdb"):
            root, rid, refs = xdb_text_refs(path, data)
            short = root.split(".")[-1] if root else "?"
            if rid is not None:
                self.resources[rid] = (path, short)
            for target, el in refs:
                self.text_owners[target].append((path, short, el))
                self.xdb_fields[path].setdefault(el, target)
        return self


# --- lien texte ↔ ressource ↔ type ↔ champ ---------------------------------------------------

@dataclass
class Linked:
    owner: dict[int, tuple[int, int, int]]         # index → (rid, soutien, décalage)
    rid_type: dict[int, tuple[str, str]]           # rid → (type, "server" | "inferred")
    rid_key: dict[int, int]                         # rid → resourceId
    rid_path: dict[int, str]                        # rid → xdb (serveur)
    text_path: dict[int, str]                       # index → chemin .txt (serveur)
    field_map: dict[tuple[str, int], str]           # (type, décalage) → champ
    legacy_text: set                                # index dont le contenu figure dans l'arbre serveur
    revised: set = field(default_factory=set)       # index dont le russe a été réécrit depuis l'arbre serveur
    evaluation: dict = field(default_factory=dict)


def learn_fields(owner, rid_type_server, rid_path, text_path, server: ServerTree) -> dict[tuple[str, int], str]:
    votes: dict[tuple[str, int], collections.Counter] = collections.defaultdict(collections.Counter)
    for t, (rid, _, rel) in owner.items():
        p = text_path.get(t)
        if p is None or rid not in rid_path:
            continue
        for xdb, _, el in server.text_owners.get(p, []):
            if xdb == rid_path[rid]:
                votes[(rid_type_server[rid], rel)][el] += 1
                break
    out = {}
    for key, c in votes.items():
        el, n = c.most_common(1)[0]
        if n >= 0.6 * sum(c.values()):
            out[key] = el
    return out


def link(ru: list[str], raw: bytes, index: PackIndex, server: ServerTree | None,
         evaluate: bool = False, log=print) -> Linked:
    n = len(ru)
    refs = scan_refs(raw, index, n)
    sup = support(refs)
    sizes = {int(r): int(s) for r, s in zip(index.rids, index.sizes)}
    owner = pick_owners(refs, sup, sizes)
    log(f"  références candidates : {len(refs['rid'])}, textes rattachés : {len(owner)}/{n}")

    rid_key = {}
    for rid, off in index.rid_offset.items():
        k = index.offset_key.get(off)
        if k is not None:
            rid_key[rid] = k
    rid_path: dict[int, str] = {}
    rid_type_server: dict[int, str] = {}
    text_path: dict[int, str] = {}
    legacy: set = set()
    if server is not None:
        for rid, k in rid_key.items():
            if k in server.resources:
                rid_path[rid], rid_type_server[rid] = server.resources[k]
        by_key: dict[str, list[str]] = collections.defaultdict(list)
        for p, s in server.texts.items():
            by_key[norm_key(s)].append(p)
        for t, s in enumerate(ru):
            cands = by_key.get(norm_key(s))
            if not cands or not s.strip():
                continue
            legacy.add(t)
            rid = owner.get(t, (None,))[0]
            xdb = rid_path.get(rid)
            chosen = None
            if xdb:
                chosen = next((p for p in cands if any(o[0] == xdb for o in server.text_owners.get(p, []))), None)
            if chosen is None and len(cands) == 1:
                chosen = cands[0]
            if chosen:
                text_path[t] = chosen
        log(f"  ressources reliées à l'arbre serveur : {len(rid_path)} ; textes à chemin : {len(text_path)}")

    field_map = learn_fields(owner, rid_type_server, rid_path, text_path, server) if server else {}

    # types : serveur, sinon classifieur de disposition
    owned: dict[int, list[int]] = collections.defaultdict(list)
    for t, (rid, _, rel) in owner.items():
        owned[rid].append(rel)

    def feats(rid):
        start = index.body + index.rid_offset[rid]
        return LayoutClassifier.features(owned[rid], word_shape(raw, start, sizes[rid]))

    known = [r for r in owned if r in rid_type_server]
    evaluation = {}
    if evaluate and known:
        import random
        rnd = random.Random(0)
        sample = known[:]
        rnd.shuffle(sample)
        cut = int(len(sample) * 0.8)
        clf = LayoutClassifier().fit([(feats(r), rid_type_server[r]) for r in sample[:cut]])
        ok = 0
        per = collections.Counter()
        test = sample[cut:]
        for r, (p, _) in zip(test, clf.predict_many([feats(r) for r in test])):
            per[(rid_type_server[r], p == rid_type_server[r])] += 1
            ok += p == rid_type_server[r]
        evaluation = {"held_out": len(sample) - cut, "accuracy": round(ok / max(1, len(sample) - cut), 4),
                      "per_type": {t: {"ok": per[(t, True)], "wrong": per[(t, False)]}
                                   for t in sorted({t for t, _ in per})
                                   if per[(t, True)] + per[(t, False)] >= 20}}
        log(f"  classifieur (validation 80/20) : {evaluation['accuracy']:.1%} sur {evaluation['held_out']}")
    rid_type: dict[int, tuple[str, str]] = {r: (rid_type_server[r], "server") for r in known}
    if known:   # sans arbre serveur, aucun type n'est connu : rien à apprendre
        clf = LayoutClassifier().fit([(feats(r), rid_type_server[r]) for r in known])
        unknown = [r for r in owned if r not in rid_type]
        for r, (label, conf) in zip(unknown, clf.predict_many([feats(r) for r in unknown])):
            if label and conf >= 0.6:
                rid_type[r] = (label, "inferred")

    # second passage : petits index (1 ≤ v < MIN_REF), gardés seulement quand ils tombent sur un
    # champ texte connu du type de la ressource (0 = champ vide, ignoré)
    small = scan_refs(raw, index, MIN_REF, min_ref=1)
    type_ids = {t: k for k, t in enumerate(sorted({t for t, _ in field_map}))}
    rid_tid = np.full(int(index.rids.max()) + 1, -1, dtype=np.int64)
    for r, (t, _) in rid_type.items():
        if t in type_ids:
            rid_tid[r] = type_ids[t]
    allowed = np.array(sorted(type_ids[t] << 24 | rel for t, rel in field_map if rel < 1 << 24), dtype=np.int64)
    tid = rid_tid[small["rid"]]
    keys = (tid << 24) | small["rel"]
    hit = (tid >= 0) & np.isin(keys, allowed)
    for rid, val, rel in zip(small["rid"][hit], small["val"][hit], small["rel"][hit]):
        owner.setdefault(int(val), (int(rid), 0, int(rel)))
    # russe réécrit depuis l'arbre serveur : l'anglais officiel peut traduire l'ancienne version
    revised = set()
    if server is not None:
        for t, (rid, _, rel) in owner.items():
            if rid not in rid_path or t in legacy:
                continue
            el = field_map.get((rid_type_server[rid], rel))
            old = server.xdb_fields.get(rid_path[rid], {}).get(el) if el else None
            if old in server.texts and norm_key(server.texts[old]) != norm_key(ru[t]):
                revised.add(t)
    return Linked(owner, rid_type, rid_key, rid_path, text_path, field_map, legacy,
                  revised=revised, evaluation=evaluation)


# --- catégories --------------------------------------------------------------------------------

LORE_TYPES = {
    "QuestResource": ("quests", ("name", "goal", "startText", "checkText", "finishText", "kickText")),
    "Cue": ("dialogues", ("name", "text")),
    "MailTemplate": ("mail", ("from", "subject", "body")),
    "WorldSecrets": ("secrets", None),
    "ZoneResource": ("places", ("name", "description")),
    "MapResource": ("places", ("name", "description")),
    "InterfaceMap": ("places", ("name", "description")),
    "TeleportMasterLocation": ("places", ("name",)),
    "AstralSectorResource": ("places", ("name",)),
    "AstralMapPOI": ("places", ("name", "description")),
    "AstralHubObjectPoi": ("places", ("name", "description")),
    "MobWorld": ("characters", ("name", "title")),
    "AstralMobWorld": ("characters", ("name", "title")),
    "Faction": ("factions", ("name",)),
    "CharacterRace": ("factions", None),
    "CharacterRaceClass": ("factions", ("name", "greatName", "description")),
    "CharacterClass": ("factions", ("Name",)),
    "ItemResource": ("library", ("name", "description")),
    # textes de scènes (répliques scriptées, résumés d'intrigue) et messages au monde
    "ClientData": ("scenes", None),
    "TextMessage": ("scenes", ("Text",)),
    # objectifs et événements : décrivent souvent un allod ou une situation
    "GoalResource": ("events", ("title", "description", "shortDescription")),
    "MarkedGroupInstancedEvent": ("events", ("name", "description")),
    "DungeonEventType": ("events", ("name", "description")),
    "RaidEventType": ("events", ("name", "description")),
    "IslandEventType": ("events", ("name", "description")),
}
NARRATIVE_MIN = 60   # scènes et événements : au moins un texte de cette longueur, sans vocabulaire de mécanique

DOC_WORDS = re.compile(r"(страниц|записк|письм|дневник|летопис|книг|\bтом\b|свит(ок|к)|записи|табличк|послани|"
                       r"доклад|отч[её]т|рапорт|фолиант|газет|листовк|приказ|донесени|сказ\b|сказани|легенд|"
                       r"хроник|трактат|завещани|стих|песн|молитв|заметк|журнал|воспоминани|исповед)", re.I)
# vocabulaire des objets de mécanique (bonus, coffres, parchemins d'expérience…) : pas du lore
MECHANICS = re.compile(r"(<r name|получите|получит|позволяет|позволит|Открыв|откро|используйте|Используется|"
                       r"сундук|ларец|ларц|Лавк|\d+\s*%|урон|экипиров|Внимание!|премиум|активир|Содержит|содержит:|"
                       r"бонус|опыта|репутаци|характеристик|единиц|Эффект|стиля|скидк|Прочтя этот|очк(о|и|ов) умени|"
                       r"дней\)|часов\)|обменять|перезаряд|кулдаун)", re.I)
HINT = re.compile(r"<tip_\w+>.*?</tip_\w+>", re.S)   # indications en fin de page (« Загляните в… »)
NAME_LIKE = re.compile(r"^[А-ЯЁ][а-яё'-]+(\s+(ди|де|дель|ван|фон|аль|эль|из|де ла)?\s*[А-ЯЁ][а-яё'-]+)+$")
ORDINAL = re.compile(r"^(перв|втор|трет|четв[её]рт|пят|шест|седьм|восьм|девят|десят|одиннадцат|двенадцат|"
                     r"тринадцат|четырнадцат|пятнадцат|шестнадцат|семнадцат|восемнадцат|девятнадцат|двадцат)"
                     r"(ая|ой|ый|ий|ое|ья|ье|ого)\s+", re.I)


def is_document(name_ru: str, desc_ru: str) -> str | None:
    """`document` = texte lisible (page, lettre, journal…) ; `flavor` = description d'ambiance ;
    None = objet de mécanique. Les indications en `<tip_…>` (« Загляните в… ») sont ignorées."""
    body = HINT.sub("", HREF_ANY.sub("", desc_ru))
    plain = to_plain(body)
    if len(plain) < 120 or MECHANICS.search(body) or MECHANICS.search(name_ru):
        return None
    if DOC_WORDS.search(name_ru) and len(plain) >= 150:
        return "document"
    if len(plain) >= 400:
        return "document"
    return "flavor" if len(plain) >= 200 else None


def book_key(name_ru: str) -> str | None:
    """Série d'un document : titre entre guillemets, « X, страница … » ou « Восьмая записка X »."""
    name = to_plain(name_ru)
    m = re.search(r"«([^»]+)»", name)
    if m:
        return m.group(1).strip()
    m = re.match(r"^(.+?),\s*(страниц|запись|глава)", name, re.I)
    if m:
        return m.group(1).strip()
    m = ORDINAL.match(name)
    if m:
        rest = name[m.end():].strip()
        return rest[:1].upper() + rest[1:] if rest else None
    return None


# --- corpus communautaire ------------------------------------------------------------------------

SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")
PATH_PREFIX = re.compile(r"\[[^\]\n]{3,200}\]:?")      # « [/Maps/…/X.txt]: » des extraits de dumps
DATED_TITLE = re.compile(r"\d{2}\.\d{2}\.20\d{2}")       # « Titre01.11.2025 » : article daté du site officiel

CLASSES = ("in-game (official EN available)", "in-game (RU/FR only)",
           "official out-of-game (announcement/FAQ)", "community", "excluded (raw dump / other game)")


def norm_sentence(s: str) -> str:
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[^0-9a-zа-я]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def sentences(text: str, min_chars: int = 25) -> list[str]:
    out = []
    for part in SENT_SPLIT.split(text):
        k = norm_sentence(part)
        if len(k) >= min_chars and k.count(" ") >= 3:
            out.append(k)
    return out


def short_lines(text: str) -> list[str]:
    """Lignes courtes d'au moins deux mots (listes de noms, extraits de dumps « [chemin]: texte »)."""
    out = []
    for line in text.split("\n"):
        k = norm_sentence(line)
        if 8 <= len(k) <= 120 and " " in k:
            out.append(k)
    return out


def coverage_of(units: list[str], index: dict[str, list[int]], official) -> tuple[float, float, collections.Counter]:
    """Part (en caractères) des unités retrouvées dans le client, part de celles-ci qui ont un anglais
    officiel, et index des textes retrouvés."""
    total = sum(len(u) for u in units)
    matched = en_ok = 0
    locs: collections.Counter = collections.Counter()
    for u in units:
        ts = index.get(u)
        if not ts:
            continue
        matched += len(u)
        locs[ts[0]] += 1
        if official(ts[0]):
            en_ok += len(u)
    return (matched / total if total else 0.0), (en_ok / matched if matched else 0.0), locs


def read_corpus_text(path: Path) -> str:
    b = path.read_bytes()
    if b.startswith(b"\xef\xbb\xbf"):
        return b[3:].decode("utf-8", "replace")
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp1251", "replace")


def clean_corpus_text(text: str) -> str:
    """Retire préfixes de chemins et balises HTML des extraits copiés depuis le client."""
    return to_plain(PATH_PREFIX.sub("\n", text))


def classify_community(rel: str, coverage: float, en_share: float, provenance: dict,
                       head: str = "") -> tuple[str, str | None]:
    """→ (classe, note). L'appariement au client prime ; sinon règles de provenance du manifeste."""
    files = provenance.get("files", {})
    if rel in files and files[rel].get("force"):
        return files[rel]["class"], files[rel].get("note")
    for pat in provenance.get("excluded", {}).get("patterns", []):
        if pat.lower() in rel.lower():
            return CLASSES[4], provenance["excluded"].get("note")
    if coverage >= 0.5:
        return ("in-game (official EN available)" if en_share >= 0.8 else "in-game (RU/FR only)"), None
    if rel in files:
        return files[rel]["class"], files[rel].get("note")
    low = rel.lower()
    for kind, cls in (("official", CLASSES[2]), ("community", CLASSES[3])):
        for pat in provenance.get(kind, {}).get("patterns", []):
            if pat.lower() in low:
                return cls, provenance[kind].get("note")
    if DATED_TITLE.search(head[:200]):
        return CLASSES[2], "dated post (official site format)"
    return CLASSES[3], None


# --- glossaire / atlas ------------------------------------------------------------------------

def norm_name(s: str) -> str:
    s = to_plain(s).lower().replace("ё", "е")
    s = re.sub(r"[«»\"'.,:;!?()\[\]]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def atlas_base_name(name: str) -> tuple[str, str | None]:
    """`Айрин (Умойр)` → (`Айрин`, `Умойр`)."""
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", name.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return name.strip(), None


# --- pipeline -------------------------------------------------------------------------------

def load_pak_member(pak: Path, member: str) -> bytes:
    data = BinSource([], [str(pak)]).get(member)
    if data is None:
        raise FileNotFoundError(f"{member} absent de {pak}")
    return data


def words(s: str) -> int:
    return len(re.findall(r"\w+", s))


GLOSSARY_KINDS = {"places": "place", "characters": "character", "factions": "faction"}
NAME_FIELDS = ("name", "Name", "greatName")


class Extractor:
    def __init__(self, manifest: dict, out: Path, log=print) -> None:
        self.m = manifest
        self.out = Path(out)
        self.log = log
        self.report: list[str] = []
        self.fr: dict[int, str] = {}
        self.fr_verified = 0

    # sources -------------------------------------------------------------------------------
    def load_client(self) -> None:
        c = self.m["client"]
        root = Path(c["root"])
        texts = root / c["texts_pak"]
        fp_ru, self.ru = parse_loc(load_pak_member(texts, c["ru"]))
        fp_en, self.en = parse_loc(load_pak_member(texts, c["en"]))
        if fp_ru != fp_en or len(self.ru) != len(self.en):
            raise ValueError("pack.rus.loc et pack.eng_eu.loc ne sont pas alignés")
        self.fingerprint = fp_ru
        raw = zlib.decompress(load_pak_member(root / c["base_pak"], c["pack"]))
        self.pack_raw = raw
        self.pack = parse_pack(raw)
        if self.pack.fingerprint != fp_ru:
            self.report.append("empreinte pack.bin ≠ .loc : rattachement ressource ↔ texte non garanti")
        version = root / "Profiles" / "game.version"
        m = re.search(rb"\d+\.\d+\.\d+\.\d+(\.\d+)?", version.read_bytes()[:200]) if version.exists() else None
        self.client_version = m.group().decode() if m else "?"
        self.log(f"client {self.client_version} : {len(self.ru)} textes, {len(self.pack.rid_offset)} ressources")

    def load_server(self) -> ServerTree | None:
        root = self.m.get("server_root")
        if not root or not Path(root).exists():
            self.report.append(f"arbre serveur absent : {root}")
            return None
        t = time.time()
        tree = ServerTree(Path(root)).load()
        self.log(f"arbre serveur : {len(tree.texts)} textes, {len(tree.resources)} ressources ({time.time() - t:.0f} s)")
        return tree

    def load_fr(self) -> dict[int, str]:
        """Pont officiel en → fr par les packs EU alignés ; vérification dans le client FR."""
        eu = self.m.get("eu_packs") or {}
        try:
            _, eu_en = parse_loc(load_pak_member(Path(eu["en"]), eu.get("member", "Bin/pack.loc")))
            _, eu_fr = parse_loc(load_pak_member(Path(eu["fr"]), eu.get("member", "Bin/pack.loc")))
        except (KeyError, FileNotFoundError, OSError) as exc:
            self.report.append(f"packs EU absents, pas de français : {exc}")
            return {}
        fr_set = None
        fc = self.m.get("fr_client")
        if fc:
            try:
                _, frc = parse_loc(load_pak_member(Path(fc["root"]) / fc["texts_pak"], fc.get("member", "Bin/pack.loc")))
                fr_set = {norm_key(s) for s in frc}
                self.fr_client_count = len(frc)
            except (FileNotFoundError, OSError) as exc:
                self.report.append(f"client FR absent : {exc}")
        self.eu_count = len(eu_en)
        self.en_in_eu = 0
        match = bridge(self.en, eu_en)
        fr: dict[int, str] = {}
        for i, j in match.items():
            self.en_in_eu += 1
            f = eu_fr[j]
            if not f.strip() or CYRILLIC.search(f):
                continue
            # un texte identique en/fr n'est gardé que s'il est court (nom propre) : sinon non traduit
            if f == eu_en[j] and (len(f) > 40 or "\n" in f):
                continue
            fr[i] = to_plain(HREF.sub(lambda m: render(href_index(m.group(1)), eu_fr, 1), f))
            if fr_set is not None and norm_key(f) in fr_set:
                self.fr_verified += 1
        self.log(f"français (pont EU) : {len(fr)} textes, dont {self.fr_verified} présents dans le client FR")
        return fr

    # entrées -------------------------------------------------------------------------------
    def field_name(self, typ: str, rel: int) -> str:
        return self.linked.field_map.get((typ, rel), f"@{rel}")

    def text_record(self, t: int) -> dict:
        ru = render(t, self.ru)
        raw_en = self.en[t]
        en = render(t, self.en)
        rec = {"loc": t, "ru": ru, "en_status": en_status(raw_en, en)}
        if rec["en_status"] != "missing":
            rec["en"] = en
        if t in self.linked.revised:
            rec["ru_revised"] = True
        if t in self.fr:
            rec["fr"] = self.fr[t]
        return rec

    def build_entries(self) -> dict[str, list[dict]]:
        L = self.linked
        by_rid: dict[int, list[tuple[int, int]]] = collections.defaultdict(list)
        for t, (rid, _, rel) in L.owner.items():
            by_rid[rid].append((rel, t))
        cats: dict[str, list[dict]] = collections.defaultdict(list)
        for rid, items in by_rid.items():
            typ, source = L.rid_type.get(rid, (None, None))
            if typ not in LORE_TYPES:
                continue
            cat, wanted = LORE_TYPES[typ]
            fields: dict[str, int] = {}
            for rel, t in sorted(items):
                name = self.field_name(typ, rel)
                if wanted is not None and name not in wanted:
                    continue
                if not self.ru[t].strip():
                    continue
                fields.setdefault(name, t)
            if not fields:
                continue
            extra = {}
            if cat == "library":
                name_ru = self.ru[fields["name"]] if "name" in fields else ""
                kind = is_document(name_ru, self.ru[fields["description"]] if "description" in fields else "")
                if kind is None:
                    continue
                extra["kind"] = kind
                b = book_key(name_ru) if name_ru else None
                if b:
                    extra["series"] = b
            if cat == "characters":
                name_ru = to_plain(self.ru[fields["name"]]) if "name" in fields else ""
                if "title" not in fields and not NAME_LIKE.match(name_ru):
                    continue
            if cat in ("scenes", "events"):
                plain = {k: to_plain(HREF_ANY.sub("", self.ru[t])) for k, t in fields.items()}
                keep = {k for k, v in plain.items() if not MECHANICS.search(self.ru[fields[k]])}
                if not any(len(plain[k]) >= NARRATIVE_MIN for k in keep):
                    continue
                fields = {k: t for k, t in fields.items() if k in keep}
            if cat == "dialogues" and "text" not in fields:
                continue
            if cat == "quests" and len(fields) < 2:
                continue
            legacy = [t in L.legacy_text for t in fields.values()]
            era = "legacy" if all(legacy) else ("legacy-revised" if rid in L.rid_path else "recent")
            entry = {"id": f"r{rid}", "type": typ, "type_source": source}
            if rid in L.rid_key:
                entry["resource_id"] = L.rid_key[rid]
            if rid in L.rid_path:
                entry["path"] = L.rid_path[rid]
            entry["era"] = era
            entry.update(extra)
            entry["fields"] = {k: self.text_record(t) for k, t in fields.items()}
            cats[cat].append(entry)
        for cat in cats:
            cats[cat].sort(key=lambda e: min(f["loc"] for f in e["fields"].values()))
        self.series_summary(cats.get("library", []))
        return cats

    def series_summary(self, library: list[dict]) -> None:
        """Séries de documents (livres en pages, carnets…) : au moins deux documents."""
        groups: dict[str, list[dict]] = collections.defaultdict(list)
        for e in library:
            if e.get("series") and e["kind"] == "document":
                groups[e["series"]].append(e)
        self.series = []
        for name, items in groups.items():
            if len(items) < 2:
                continue
            en_names = [e["fields"]["name"].get("en") for e in items if "name" in e["fields"]]
            self.series.append({
                "series": name, "documents": len(items),
                "en_official": sum(1 for e in items if e["fields"].get("description", {}).get("en_status") == "official"),
                "example_en_title": next((n for n in en_names if n), None),
                "ids": [e["id"] for e in items],
            })
        self.series.sort(key=lambda s: -s["documents"])

    # glossaire -------------------------------------------------------------------------------
    def casing(self) -> dict[str, list[int]]:
        """Mot (minuscule) → [occurrences capitalisées, occurrences en minuscule] hors début de
        phrase, sur tous les textes russes : un nom propre reste capitalisé en cours de phrase."""
        counts: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
        for t, s in enumerate(self.ru):
            if len(s) < 20:
                continue
            for sent in re.split(r"[.!?…\n:«»\"—–-]+", to_plain(HREF_ANY.sub("", s))):
                toks = re.findall(r"[А-Яа-яЁё]+", sent)
                for tok in toks[1:]:
                    counts[tok.lower().replace("ё", "е")][0 if tok[0].isupper() else 1] += 1
        return counts

    def build_glossary(self, cats: dict[str, list[dict]], corpus_text: str = "") -> list[dict]:
        acc: dict[str, dict] = {}
        for cat, kind in GLOSSARY_KINDS.items():
            for e in cats.get(cat, []):
                for fname in NAME_FIELDS:
                    f = e["fields"].get(fname)
                    if not f or f["en_status"] != "official":
                        continue
                    ru, en = f["ru"], f["en"]
                    if not ru or len(ru) > 60 or "\n" in ru or not en:
                        continue
                    k = norm_name(ru)
                    g = acc.setdefault(k, {"ru": ru, "kind": kind, "en": collections.Counter(), "refs": [], "types": set()})
                    g["en"][en] += 1
                    g["types"].add(e["type"])
                    if len(g["refs"]) < 5:
                        g["refs"].append(f["loc"])
        out = []
        padded = f" {corpus_text} " if corpus_text else ""
        casing = self.casing()
        for k, g in acc.items():
            (best, _), *rest = g["en"].most_common()
            kind = g["kind"]
            if " " not in k:
                cap, low = casing.get(k, [0, 0])
                if low >= 3 and low >= cap:
                    # nom commun : gardé comme terme s'il a un équivalent anglais d'un seul mot
                    if " " in best.strip():
                        continue
                    kind = "term"
            item = {"ru": g["ru"], "en": best, "kind": kind, "types": sorted(g["types"]), "loc": g["refs"]}
            if rest:
                item["variants"] = [v for v, _ in rest[:4]]
            if padded and len(k) >= 3:
                n = padded.count(f" {k} ")
                if n:
                    item["corpus_hits"] = n
            out.append(item)
        out.sort(key=lambda x: (x["kind"], x["ru"].casefold()))
        return out

    # corpus ------------------------------------------------------------------------------------
    def build_sentence_index(self) -> dict[str, list[int]]:
        """Phrases normalisées de tous les textes russes du client, plus les textes courts entiers."""
        idx: dict[str, list[int]] = collections.defaultdict(list)
        for t, s in enumerate(self.ru):
            if not s.strip():
                continue
            plain = render(t, self.ru)
            keys = sentences(plain) if len(s) >= 25 else []
            whole = norm_sentence(plain)
            if 8 <= len(whole) <= 120 and " " in whole:
                keys.append(whole)
            for k in keys:
                lst = idx[k]
                if len(lst) < 8:
                    lst.append(t)
        return idx

    def match_corpus(self, cats: dict[str, list[dict]]) -> tuple[list[dict], str]:
        """→ (index du corpus, texte normalisé concaténé pour les fréquences du glossaire)."""
        root = Path(self.m.get("corpus", ""))
        if not root.exists():
            self.report.append(f"corpus communautaire absent : {root}")
            return [], ""
        sidx = self.build_sentence_index()
        owner_entry = {}
        for cat, entries in cats.items():
            for e in entries:
                for f in e["fields"].values():
                    owner_entry[f["loc"]] = (cat, e["id"])
        prov = self.m.get("provenance", {})
        out = []
        normalized: list[str] = []
        cache: dict[int, bool] = {}

        def official(t: int) -> bool:
            if t not in cache:
                cache[t] = en_status(self.en[t], render(t, self.en)) == "official"
            return cache[t]

        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            suffix = path.suffix.lower()
            item = {"path": rel, "bytes": path.stat().st_size}
            if suffix == ".txt":
                raw_text = read_corpus_text(path)
                text = clean_corpus_text(raw_text)
                item["words"] = words(text)
                sents = sentences(text)
                cov, share, locs = coverage_of(sents, sidx, official)
                # listes et extraits de dumps : la ligne est l'unité (on garde la meilleure lecture)
                cov_l, share_l, locs_l = coverage_of(short_lines(text), sidx, official)
                coverage, en_share = (cov_l, share_l) if cov_l > cov else (cov, share)
                locs.update(locs_l)
                item.update({"sentences": len(sents), "coverage": round(coverage, 3), "en_share": round(en_share, 3)})
                cls, note = classify_community(rel, coverage, en_share, prov, raw_text.lstrip()[:300])
                if cls != CLASSES[4]:
                    normalized.append(norm_sentence(text))
                if locs:
                    item["loc_count"] = len(locs)
                    item["loc"] = sorted(locs)[:300]
                    ents = collections.Counter(owner_entry[t] for t in locs if t in owner_entry)
                    item["entries"] = [f"{c}:{i}" for (c, i), _ in ents.most_common(60)]
            elif suffix in (".docx", ".pdf", ".doc", ".xlsx", ".pak"):
                cls, note = classify_community(rel, 0.0, 0.0, prov)
                if suffix == ".docx" and item["bytes"] < 600_000_000:
                    item["words"] = docx_words(path)
            else:
                continue
            item["class"] = cls
            if note:
                item["note"] = note
            out.append(item)
        return out, " ".join(normalized)

    def match_atlas(self, cats: dict[str, list[dict]]) -> dict:
        root = Path(self.m.get("corpus", ""))
        xlsx = next(iter(root.glob("*табл.xlsx")), None) if root.exists() else None
        if xlsx is None:
            return {}
        import openpyxl
        ws = openpyxl.load_workbook(xlsx, read_only=True).worksheets[0]
        places: dict[str, list[tuple[str, dict]]] = collections.defaultdict(list)
        for e in cats.get("places", []):
            f = e["fields"].get("name")
            if f:
                places[norm_name(f["ru"])].append((e["id"], f))
        short: dict[str, int] = {}
        for t, s in enumerate(self.ru):
            if 0 < len(s) <= 80:
                short.setdefault(norm_name(render(t, self.ru)), t)
        haystack = [(t, " " + norm_name(render(t, self.ru)) + " ") for t, s in enumerate(self.ru) if len(s) > 80]
        rows = []
        stats = collections.Counter()
        by_cat: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        header = None
        for r, row in enumerate(ws.iter_rows(values_only=True), start=1):
            if row and row[0] == "Назание":
                header = row
                continue
            if not header or not row or not row[0] or not str(row[0]).strip():
                continue
            name = str(row[0]).strip()
            category = str(row[7]).strip() if len(row) > 7 and row[7] else "?"
            base, _ = atlas_base_name(name)
            k = norm_name(base)
            item = {"row": r, "name": name}
            if k in places:
                hit = places[k]
                item["match"] = "place"
                item["entries"] = sorted({h[0] for h in hit})[:10]
                ens = collections.Counter(h[1].get("en") for h in hit if h[1].get("en"))
                if ens:
                    item["en"] = ens.most_common(1)[0][0]
            elif k in short:
                t = short[k]
                item["match"] = "name"
                item["loc"] = t
                en = render(t, self.en)
                if en_status(self.en[t], en) == "official":
                    item["en"] = en
            else:
                needle = f" {k} "
                found = [t for t, h in haystack if needle in h] if len(k) >= 4 else []
                if found:
                    item["match"] = "mentioned"
                    item["mentions"] = len(found)
                    item["loc"] = found[:10]
                else:
                    item["match"] = None
            stats[item["match"] or "none"] += 1
            stats["with_official_en"] += "en" in item
            by_cat[category][item["match"] or "none"] += 1
            rows.append(item)
        return {"source": xlsx.relative_to(root).as_posix(), "total": len(rows), "stats": dict(stats),
                "by_atlas_category": {c: dict(v) for c, v in sorted(by_cat.items())}, "rows": rows}

    # statistiques ---------------------------------------------------------------------------
    def stats(self, cats: dict[str, list[dict]]) -> dict:
        out = {}
        for cat, entries in cats.items():
            c = collections.Counter()
            for e in entries:
                c["entries"] += 1
                c[f"entries_{e['era']}"] += 1
                for f in e["fields"].values():
                    w = words(f["ru"])
                    c["texts"] += 1
                    c["ru_chars"] += len(f["ru"])
                    c["ru_words"] += w
                    if f["en_status"] == "official":
                        c["en_texts"] += 1
                        c["en_words"] += words(f.get("en", ""))
                        c["en_ru_words"] += w
                        if f.get("ru_revised"):
                            c["en_maybe_outdated_texts"] += 1
                            c["en_maybe_outdated_ru_words"] += w
                        c[f"en_texts_{e['era']}"] += 1
                    else:
                        c["todo_texts"] += 1
                        c["todo_ru_words"] += w
                    c[f"texts_{e['era']}"] += 1
                    if "fr" in f:
                        c["fr_texts"] += 1
            out[cat] = dict(c)
        return out

    def run(self, evaluate: bool = False) -> dict:
        self.load_client()
        server = self.load_server()
        self.linked = link(self.ru, self.pack_raw, self.pack, server, evaluate=evaluate, log=self.log)
        self.fr = self.load_fr()
        cats = self.build_entries()
        community, corpus_text = self.match_corpus(cats)
        glossary = self.build_glossary(cats, corpus_text)
        atlas = self.match_atlas(cats)
        self.out.mkdir(parents=True, exist_ok=True)
        files = {}
        for cat, entries in sorted(cats.items()):
            main_entries, ru_map, fr_map = split_languages(entries)
            files[cat] = self.write(f"{cat}.json", main_entries)
            files[f"ru/{cat}"] = self.write(f"ru/{cat}.json", ru_map)
            if fr_map:
                files[f"fr/{cat}"] = self.write(f"fr/{cat}.json", fr_map)
        files["series"] = self.write("series.json", self.series)
        files["glossary"] = self.write("glossary.json", glossary)
        files["community"] = self.write("community.json", community)
        files["atlas"] = self.write("atlas.json", atlas)
        n = len(self.ru)
        nonempty = [t for t in range(n) if self.ru[t].strip()]
        en_ok = sum(1 for t in nonempty if en_status(self.en[t], self.en[t]) != "missing")
        index = {
            "generated": time.strftime("%Y-%m-%d"),
            "client": {"version": self.client_version, "fingerprint": f"{self.fingerprint:08x}",
                       "texts": n, "texts_nonempty": len(nonempty), "texts_with_official_en": en_ok,
                       "resources": len(self.pack.rid_offset),
                       "texts_linked_to_a_resource": len(self.linked.owner)},
            "sources": {
                "texts": "official client AllodsRU 17.0: Texts_x64.pak (pack.rus.loc + pack.eng_eu.loc, index-aligned)",
                "resources": "official client: BaseLocall_x64.pak Bin/pack.bin (which resource owns which text)",
                "paths_types": "server data tree (xdb + txt, content up to ~ZC14); newer resources typed from their binary layout",
                "fr": "official EU text packs 16.0 (en/fr aligned) used as an en→fr bridge, checked against the FR client 16.0",
            },
            "provenance": {"in-game": "shipped in the official client; en_status tells whether an official English exists",
                           "official": "official out-of-game text (announcements, dev posts, story FAQ)",
                           "community": "fan work (atlas, encyclopedia, chronologies): referenced by path, never copied"},
            "en_status": {"official": "official English (EU edition) shipped in the 17.0 client",
                          "partial": "official English, but an inserted fragment is still Russian",
                          "missing": "no official English: to translate"},
            "eras": {"legacy": "resource and text present in the server tree (content up to ~ZC14)",
                     "legacy-revised": "resource present in the server tree, at least one text rewritten since",
                     "recent": "resource added after the server tree (Eden, Jigran, Kadagan, Kvator, Isa, Suslanger, Airin…)"},
            "flags": {"ru_revised": "Russian rewritten after the server tree: the official English may translate the old version"},
            "classifier": self.linked.evaluation,
            "fr": {"texts": len(self.fr), "verified_in_fr_client": self.fr_verified,
                   "client_en_texts_found_in_eu_pack": getattr(self, "en_in_eu", 0)},
            "stats": self.stats(cats),
            "community": dict(collections.Counter(x["class"] for x in community)),
            "atlas": {k: atlas.get(k) for k in ("total", "stats")} if atlas else {},
            "files": files,
            "notes": self.report,
        }
        self.write("index.json", index)
        return index

    def write(self, name: str, data) -> dict:
        path = self.out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        path.write_text(text, encoding="utf-8")
        return {"file": name, "bytes": path.stat().st_size, "gzip": len(zlib.compress(text.encode("utf-8"), 9))}


def bridge(client_en: list[str], eu_en: list[str]) -> dict[int, int]:
    """Index client → index du pack EU, par égalité du texte anglais ; en cas d'homonymes, l'index
    EU le plus proche de celui qu'annonce l'ancre unique précédente (les deux tables suivent l'ordre
    des chemins)."""
    by_en: dict[str, list[int]] = collections.defaultdict(list)
    for j, s in enumerate(eu_en):
        if s.strip():
            by_en[norm_key(s)].append(j)
    match: dict[int, int] = {}
    amb: dict[int, list[int]] = {}
    for i, s in enumerate(client_en):
        if not s.strip() or CYRILLIC.search(s):
            continue
        js = by_en.get(norm_key(s))
        if not js:
            continue
        if len(js) == 1:
            match[i] = js[0]
        else:
            amb[i] = js
    anchors = sorted(match.items())
    keys = [a for a, _ in anchors]
    for i, js in amb.items():
        k = bisect.bisect_left(keys, i) - 1
        expect = anchors[k][1] + (i - anchors[k][0]) if k >= 0 else i
        match[i] = min(js, key=lambda j: abs(j - expect))
    return match


def split_languages(entries: list[dict]) -> tuple[list[dict], dict[str, str], dict[str, str]]:
    """Fichier principal (anglais + métadonnées) et tables `loc → texte` russe et française."""
    main, ru, fr = [], {}, {}
    for e in entries:
        e2 = dict(e)
        e2["fields"] = {}
        for k, f in e["fields"].items():
            f2 = {x: v for x, v in f.items() if x not in ("ru", "fr")}
            if "fr" in f:
                f2["fr"] = True
                fr[str(f["loc"])] = f["fr"]
            ru[str(f["loc"])] = f["ru"]
            e2["fields"][k] = f2
        main.append(e2)
    return main, ru, fr


def docx_words(path: Path) -> int | None:
    """Nombre de mots d'un .docx sans charger les images (lecture directe de word/document.xml)."""
    import zipfile
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
    except (KeyError, OSError, zipfile.BadZipFile):
        return None
    return words(" ".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml)))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--evaluate", action="store_true", help="mesure la précision du classifieur de types (80/20)")
    args = ap.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    ex = Extractor(manifest, args.out)
    index = ex.run(evaluate=args.evaluate)
    for cat, st in index["stats"].items():
        print(f"  {cat:11s} {st.get('entries', 0):6d} entrées, {st.get('texts', 0):6d} textes, "
              f"EN officiel {st.get('en_texts', 0)}/{st.get('texts', 0)}")
    total = 0
    for name, f in index["files"].items():
        total += f["bytes"]
        print(f"  {f['file']:22s} {f['bytes'] / 1e6:7.2f} Mo (gzip {f['gzip'] / 1e6:.2f} Mo)")
    print(f"  total {total / 1e6:.1f} Mo")
    for note in index["notes"]:
        print("  !", note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
