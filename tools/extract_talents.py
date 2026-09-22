#!/usr/bin/env python3
"""Extraction des talents de toutes les classes jouables, version par version.

Pour chaque version listée dans `tools/talents_manifest.json`, l'outil ouvre le `pack.bin` du client
(voir `tools/packbin.py` pour le format), suit `CharacterClass → BaseTalentsTable` et écrit :

* `public/game/talents/<version>/<classe>.json` — le « livre » (couches de 4 sorts débloquées par
  paliers de points de talent), les grilles de talents (`TalentFieldResource`, 9 × 9 en 3.0+), et,
  pour chaque sort ou capacité référencé : noms, descriptions localisées, icône, rangs et valeurs
  des variables `<r name="…"/>` citées par les descriptions ;
* `public/game/talents/index.json` — versions, classes, langues, systèmes et manques ;
* `public/game/talents/icons/<empreinte>.png` — icônes dédupliquées par contenu.

Rien n'est déduit hors des données : un champ absent reste absent (et `missing` le signale).
La découverte des champs est structurelle (relocalisations + type des cibles), ce qui la rend
indépendante des décalages propres à chaque version ; seuls les identifiants de texte des
clients 64 bits (sans chemins) sont repérés par un étalonnage statistique documenté plus bas.

Usage : python3 tools/extract_talents.py [--only 17.0 …] [--out public/game/talents]
"""
from __future__ import annotations

import argparse
import glob as globmod
import hashlib
import io
import json
import math
import os
import re
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.packbin import KIND_CLASS, KIND_DATA, KIND_PTR, KIND_TYPE, LocTable, PackBin, inflate  # noqa: E402
from tools.uitexture import decode_uitexture  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE / "talents_manifest.json"
DEFAULT_OUT = HERE.parent / "public" / "game" / "talents"

SPELL_TYPES_PREFIX = "Spell"
TALENT_REF_PREFIX = "TalentRef"
INCLUDE_RE = re.compile(r'<t\s+href="([^"]+)"\s*/>')
NO_TEXT = (1 << 64) - 1  # identifiant de texte absent (clients 64 bits)
VAR_RE = re.compile(r'<r\s+name="([^"]+)"\s*/>')


def is_spell_type(t: str | None) -> bool:
    return bool(t) and (t == "Spell" or (t.startswith("Spell") and t[5:6].isupper() and t not in NON_SPELL))


NON_SPELL = {"SpellVisScripts", "SpellSimpleCooldown", "SpellRankCalcer", "SpellRoot", "SpellModifier"}


def is_ability_type(t: str | None) -> bool:
    return t == "AbilityResource"


def is_talent_type(t: str | None) -> bool:
    return bool(t) and (t.startswith("Talent") or t == "NoTalent") and t not in (
        "TalentFieldResource", "TalentGraph") and not t.startswith(TALENT_REF_PREFIX)


CYRILLIC = re.compile(r"[Ѐ-ӿ]")


def drop_untranslated(vals: dict) -> None:
    """Le `.loc` anglais du client 17 contient des textes restés en russe (contenu non traduit) :
    une entrée « en » identique à « ru » et en cyrillique est retirée plutôt qu'affichée comme
    anglaise."""
    if not isinstance(vals, dict):
        return
    en, ru = vals.get("en"), vals.get("ru")
    if en and ru and en == ru and CYRILLIC.search(en):
        del vals["en"]


# --- sources ------------------------------------------------------------------------------

def read_source(spec: list | None) -> bytes | None:
    """`[chemin, entrée zip | None]` → octets décompressés (None si introuvable)."""
    if not spec:
        return None
    path, entry = os.path.expanduser(spec[0]), spec[1]
    if not os.path.exists(path):
        return None
    if entry is None:
        return inflate(Path(path).read_bytes())
    try:
        with zipfile.ZipFile(path) as z:
            return inflate(z.read(entry))
    except (KeyError, zipfile.BadZipFile, OSError):
        return None


class TextSource:
    """Textes d'une langue : par chemin (`.txt`) et/ou par identifiant."""

    def __init__(self, lang: str, loc: LocTable | None = None, tree: Path | None = None) -> None:
        self.lang = lang
        self.loc = loc
        self.tree = tree

    def by_path(self, path: str) -> str | None:
        path = path.lstrip("/")
        if self.loc is not None and self.loc.paths:
            return self.loc.by_path(path)
        if self.tree is not None:
            f = self.tree / path
            if f.is_file():
                data = f.read_bytes()
                for enc in ("utf-16", "utf-8-sig", "cp1251"):
                    try:
                        return data.decode(enc).lstrip("﻿")
                    except UnicodeDecodeError:
                        continue
        return None

    def by_id(self, tid: int) -> str | None:
        if self.loc is None:
            return None
        return self.loc.get(tid)

    def expand(self, text: str | None, depth: int = 0) -> str | None:
        """Remplace les inclusions `<t href="…"/>` (textes v1) par le texte inclus."""
        if text is None or depth > 4 or "<t " not in text:
            return text

        def sub(m: re.Match) -> str:
            href = m.group(1).split("#")[0]
            if re.fullmatch(r"[0-9a-f]{16}", href):
                # clients 64 bits : l'inclusion vise un identifiant de texte (u64 petit-boutiste en hexa)
                inner = self.by_id(int.from_bytes(bytes.fromhex(href), "little"))
            else:
                inner = self.by_path(href)
            if inner is None:
                return m.group(0)
            inner = self.expand(inner, depth + 1) or ""
            return re.sub(r"</?html>", "", inner)
        return INCLUDE_RE.sub(sub, text)


_ZIPS: dict[str, zipfile.ZipFile | None] = {}


def _zip(pak: str) -> zipfile.ZipFile | None:
    if pak not in _ZIPS:
        try:
            _ZIPS[pak] = zipfile.ZipFile(pak)
        except (OSError, zipfile.BadZipFile):
            _ZIPS[pak] = None
    return _ZIPS[pak]


def read_pak_entry(pak: str, entry: int) -> bytes | None:
    """Entrée n° `entry` (ordre du répertoire central) d'un pak zip."""
    z = _zip(pak)
    if z is None:
        return None
    infos = z.infolist()
    return z.read(infos[entry]) if 0 <= entry < len(infos) else None


def pak_entry_name(pak: str, entry: int) -> str | None:
    z = _zip(pak)
    if z is None:
        return None
    infos = z.infolist()
    return infos[entry].filename if 0 <= entry < len(infos) else None


class IconSink:
    """Décode les `(UITexture).bin`, déduplique par contenu et écrit les PNG."""

    def __init__(self, out_dir: Path, dry: bool = False) -> None:
        self.out_dir = out_dir
        self.dry = dry
        self.by_key: dict[str, str | None] = {}
        self.written: dict[str, int] = {}

    def add(self, key: str, loader) -> str | None:
        if key in self.by_key:
            return self.by_key[key]
        name = None
        data = loader()
        if data:
            try:
                img, _ = decode_uitexture(data)
                buf = io.BytesIO()
                img.save(buf, format="PNG", optimize=True)
                png = buf.getvalue()
                digest = hashlib.sha1(img.tobytes() + repr(img.size).encode()).hexdigest()[:12]
                name = f"{digest}.png"
                if name not in self.written:
                    self.written[name] = len(png)
                    if not self.dry:
                        self.out_dir.mkdir(parents=True, exist_ok=True)
                        (self.out_dir / name).write_bytes(png)
            except Exception as exc:  # pragma: no cover - dépend des données
                print(f"  icône illisible {key}: {exc}", file=sys.stderr)
        self.by_key[key] = name
        return name


class PakIndex:
    """Index `chemin → pak` sur une liste de globs (v1) ; accès par indice d'entrée (v2)."""

    def __init__(self, globs: list[str] | None = None, dirs: list[str] | None = None) -> None:
        self.index: dict[str, str] = {}
        self.dirs = [Path(os.path.expanduser(d)) for d in (dirs or [])]
        self._zips: dict[str, zipfile.ZipFile] = {}
        for pattern in globs or []:
            pattern = os.path.expanduser(pattern)
            base, pat = os.path.split(pattern)
            files = sorted(os.path.join(base, f) for f in os.listdir(base)) if os.path.isdir(base) else []
            import fnmatch
            for path in files:
                if not fnmatch.fnmatch(os.path.basename(path), pat):
                    continue
                try:
                    names = zipfile.ZipFile(path).namelist()
                except (OSError, zipfile.BadZipFile):
                    continue
                for n in names:
                    self.index.setdefault(n.replace("\\", "/").lower(), path)

    def zip(self, path: str) -> zipfile.ZipFile:
        z = self._zips.get(path)
        if z is None:
            z = self._zips[path] = zipfile.ZipFile(path)
        return z

    def get(self, rel: str) -> bytes | None:
        rel = rel.lstrip("/")
        for d in self.dirs:
            f = d / rel
            if f.is_file():
                return f.read_bytes()
        pak = self.index.get(rel.lower())
        if pak is None:
            return None
        z = self.zip(pak)
        for n in (rel, rel.replace("/", "\\")):
            try:
                return z.read(n)
            except KeyError:
                continue
        for info in z.infolist():
            if info.filename.replace("\\", "/").lower() == rel.lower():
                return z.read(info)
        return None


# --- décodage structurel ------------------------------------------------------------------

@dataclass
class Vec:
    field: int          # adresse du champ (pointeur de données)
    data: int | None    # adresse des éléments
    size: int           # octets


@dataclass
class Talent:
    key: str
    kind: str                     # "spell" | "ability"
    ref: str                      # chemin xdb (v1) ou identifiant d'objet (v2)
    name: dict = field(default_factory=dict)
    description: dict = field(default_factory=dict)
    icon: str | None = None
    ranks: list = field(default_factory=list)
    missing: list = field(default_factory=list)


class Extractor:
    def __init__(self, spec: dict, icons: IconSink, log=print) -> None:
        self.spec = spec
        self.icons = icons
        self.log = log
        raw = read_source(spec["pack"])
        if raw is None:
            raise FileNotFoundError(f"pack.bin introuvable : {spec['pack']}")
        self.pb = PackBin(raw)
        self.ps = self.pb.ptr_size
        self.bounds = self.pb.object_bounds()
        self.rev = self.pb.path_of()
        self.idrev = {v: k for k, v in self.pb.ids.items()}
        self.texts: list[TextSource] = []
        for lang, src in spec.get("texts", {}).items():
            if isinstance(src, dict) and "tree" in src:
                self.texts.append(TextSource(lang, tree=Path(src["tree"])))
            else:
                data = read_source(src)
                if data is None:
                    self.log(f"  textes {lang} introuvables : {src}")
                    continue
                self.texts.append(TextSource(lang, loc=LocTable(data)))
        if self.pb.fmt == "v1":
            self.paks = PakIndex(spec.get("icon_paks"), spec.get("icon_dirs"))
        else:
            self.paks = None
        self.talents: dict[int, Talent] = {}
        self._keys: dict[str, int] = {}
        self._text_slots: dict[str, dict[str, int]] = {}
        self._value_slots: dict[tuple[int, int], int] = {}

    # outils -------------------------------------------------------------------------------
    def type_at(self, a: int | None) -> str | None:
        return None if a is None else self.pb.type_at(a)

    def obj_end(self, a: int) -> int:
        i = int(np.searchsorted(self.bounds, a, side="right"))
        return int(self.bounds[i]) if i < len(self.bounds) else self.pb.size

    def head(self, a: int) -> tuple[int, int]:
        """Partie fixe de l'objet : jusqu'au prochain objet ou au premier bloc de données interne."""
        end = self.obj_end(a)
        stop = end
        for o in range(a, end, self.ps):
            rel = self.pb.reloc(o, KIND_DATA)
            if rel and a < rel.target < stop:
                stop = rel.target
            if o + self.ps >= stop:
                break
        return a, stop

    def ref_of(self, a: int) -> str:
        if a in self.rev:
            return self.rev[a]
        if a in self.idrev:
            return f"#{self.idrev[a]}"
        return f"@{a:x}"

    def ptrs(self, a: int, b: int) -> list[tuple[int, int]]:
        out = []
        for o in range(a, b, self.ps):
            t = self.pb.ptr(o)
            if t is not None:
                out.append((o, t))
        return out

    def vectors(self, a: int, b: int) -> list[Vec]:
        out = []
        for o in range(a, b - self.ps, self.ps):
            rel = self.pb.reloc(o, KIND_DATA)
            if rel is None:
                continue
            size = self.pb.word(o + self.ps)
            cap = self.pb.word(o + 2 * self.ps)
            if 0 < size <= cap < 1 << 24:
                out.append(Vec(o, rel.target, size))
        return out

    def vec_items(self, v: Vec) -> list[int]:
        if v.data is None:
            return []
        return [t for _, t in self.ptrs(v.data, v.data + v.size)]

    def inner_vectors(self, v: Vec) -> list[Vec]:
        if v.data is None:
            return []
        return self.vectors(v.data, v.data + v.size + self.ps * 2)

    def cstring(self, o: int) -> str | None:
        rel = self.pb.reloc(o, KIND_DATA)
        if rel is None:
            return None
        n = self.pb.word(o + self.ps)
        if not 0 < n < 512:
            return None
        return self.pb.bytes_at(rel.target, n).split(b"\0")[0].decode("utf-8", "replace")

    # textes -------------------------------------------------------------------------------
    def text_refs_v1(self, a: int, b: int) -> dict[str, tuple[str, int]]:
        """Références de texte v1 : `(ptr → "…/X.Name.txt", long., capacité, id)`."""
        out: dict[str, tuple[str, int]] = {}
        for o in range(a, b, self.ps):
            s = self.cstring(o)
            if not s or not s.lower().endswith(".txt"):
                continue
            base = s.rsplit("/", 1)[-1].lower()[:-4]
            if "template" in base:
                role = "template:" + base
            elif base.endswith("description") or base.endswith("desc"):
                role = "description"
            elif base.endswith("uiname"):
                role = "uiName"
            elif base.endswith("name"):
                role = "name"
            elif "tooltip" in base:
                role = "tooltip"
            else:
                role = "text:" + base
            out.setdefault(role, (s, self.pb.u32(o + 3 * self.ps)))
        return out

    def calibrate_v2(self, type_name: str) -> dict[str, int]:
        """Étalonnage des identifiants de texte (clients 64 bits, sans chemins).

        Pour chaque emplacement de 8 octets de la partie fixe, on regarde sur tous les objets du
        type si la valeur est un identifiant valide du `.loc` menant à un texte non vide, sans
        relocalisation posée dessus, et assez variée d'un objet à l'autre (un entier de réglage
        répété ne passe pas). Le texte majoritairement balisé `<html>`/long est la description,
        le plus court le nom.
        """
        if type_name in self._text_slots:
            return self._text_slots[type_name]
        slots: dict[str, int] = {}
        src = next((t for t in self.texts if t.loc is not None), None)
        objs = self.pb.objects_of(type_name)
        if src is None or not objs:
            self._text_slots[type_name] = slots
            return slots
        sample = objs[:: max(1, len(objs) // 300)]
        heads = [self.head(o) for o in sample]
        span = min(b - a for a, b in heads)
        cands = []
        for off in range(0x10, span, 8):
            vals, texts = [], []
            for a, _ in heads:
                if self.pb.reloc(a + off) is not None:
                    vals = None
                    break
                v = self.pb.u64(a + off)
                vals.append(v)
                if 0 < v < src.loc.count:
                    t = src.loc.get(v)
                    if t:
                        texts.append(t)
            if not vals:
                continue
            nz = [v for v in vals if v and v != NO_TEXT]
            # beaucoup d'objets (sorts de monstres…) n'ont aucun texte : on juge sur les non nuls
            if len(nz) < max(1, 0.15 * len(heads)) or len(texts) < 0.9 * len(nz):
                continue
            if len(nz) >= 8 and len(set(nz)) < 0.6 * len(nz):
                continue
            html = sum(1 for t in texts if "<html" in t or len(t) > 90) / len(texts)
            avg = sum(len(t) for t in texts) / len(texts)
            cands.append((off, html, avg))
        descs = sorted((c for c in cands if c[1] >= 0.4), key=lambda c: -c[1])
        names = sorted((c for c in cands if c[1] < 0.2), key=lambda c: (c[2] > 60, c[0]))
        if descs:
            slots["description"] = descs[0][0]
        if names:
            slots["name"] = names[0][0]
        self._text_slots[type_name] = slots
        return slots

    def localized(self, a: int, type_name: str | None = None) -> dict[str, dict]:
        """{rôle: {langue: texte}} pour l'objet en `a`."""
        type_name = type_name or self.type_at(a)
        out: dict[str, dict] = {}
        if self.pb.fmt == "v1":
            h = self.head(a)
            for role, (path, tid) in self.text_refs_v1(*h).items():
                vals = {}
                for src in self.texts:
                    t = src.by_path(path)
                    if t is None and src.loc is not None and not src.loc.paths:
                        t = src.by_id(tid)
                    t = src.expand(t)
                    if t is not None:
                        vals[src.lang] = t
                out[role] = vals
                out.setdefault("_paths", {})[role] = path
        else:
            for role, off in self.calibrate_v2(type_name).items():
                tid = self.pb.u64(a + off)
                vals = {}
                for src in self.texts:
                    t = src.expand(src.by_id(tid)) if tid != NO_TEXT else None
                    if t:
                        vals[src.lang] = t
                out[role] = vals
        for vals in out.values():
            drop_untranslated(vals)
        return out

    # icônes -------------------------------------------------------------------------------
    def icon_of(self, a: int, b: int) -> str | None:
        for _, t in self.ptrs(a, b):
            if self.type_at(t) == "UISingleTexture":
                return self.texture_icon(t)
        return None

    def texture_icon(self, single: int) -> str | None:
        h = self.head(single)
        tex = next((t for _, t in self.ptrs(*h) if self.type_at(t) == "UITexture"), None)
        if tex is None and self.pb.ids:
            # 17.x : la texture peut être désignée par identifiant (genre 2) ; retenue seulement
            # si l'objet désigné est bien une UITexture.
            for o in range(h[0], h[1], self.ps):
                rel = self.pb.reloc(o, KIND_CLASS)
                cand = self.pb.ids.get(rel.target) if rel else None
                if cand is not None and self.type_at(cand) == "UITexture":
                    tex = cand
                    break
        if tex is None:
            return None
        if self.pb.fmt == "v1":
            path = self.rev.get(tex)
            if not path:
                return None
            binpath = re.sub(r"\.xdb$", ".bin", path)
            return self.icons.add(f"{self.spec['id']}:{binpath}", lambda: self.paks.get(binpath))
        loc = self.texture_location(tex)
        if loc is None:
            return None
        pak, entry, _ = loc
        return self.icons.add(f"{os.path.basename(pak)}#{entry}", lambda: read_pak_entry(pak, entry))

    def texture_location(self, tex: int) -> tuple[str, int, dict] | None:
        """`UITexture` 64 bits → (pak, indice d'entrée, dimensions).

        Champs relevés sur le client 17 : u64 +0x40 = indice du pak dans le bloc 6 du pack.bin,
        u64 +0x48 = indice de l'entrée dans ce zip ; u32 +0x78 hauteur, +0x88 hauteur utile,
        +0x8c largeur utile, +0x94 largeur (puissances de deux pour hauteur/largeur).
        """
        pak_i, entry = self.pb.u64(tex + 0x40), self.pb.u64(tex + 0x48)
        names = self.pb.pak_names
        if pak_i >= len(names):
            return None
        dims = {"w": self.pb.u32(tex + 0x94), "h": self.pb.u32(tex + 0x78),
                "realW": self.pb.u32(tex + 0x8c), "realH": self.pb.u32(tex + 0x88)}
        pak = os.path.join(os.path.expanduser(self.spec["packs_dir"]), names[pak_i])
        return pak, entry, dims

    # sorts et capacités -----------------------------------------------------------------------
    def desc_vars(self, a: int, b: int) -> dict[str, dict]:
        """Variables de description `{nom: {"value": x, "scalers": [...]}}` de l'objet."""
        for v in self.vectors(a, b):
            if v.data is None:
                continue
            names = []
            for o in range(v.data, v.data + v.size, self.ps):
                s = self.cstring(o)
                if s and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", s):
                    names.append((o, s))
            if not names:
                continue
            name_off = names[0][0] - v.data
            stride = v.size // len(names)
            if (stride * len(names) != v.size or name_off >= stride
                    or any(o - v.data != name_off + i * stride for i, (o, _) in enumerate(names))):
                continue
            val_off = self.value_slot(v.data, stride, len(names), name_off)
            if val_off is None:
                continue
            out = {}
            for i, (_, name) in enumerate(names):
                item = v.data + i * stride
                val = self.pb.f32(item + val_off)
                entry: dict = {"value": round(val, 6) if math.isfinite(val) else None}
                sc = [self.scaler(t) for _, t in self.ptrs(item, item + stride)]
                if sc:
                    entry["scalers"] = sc
                out[name] = entry
            return out
        return {}

    def value_slot(self, data: int, stride: int, n: int, name_off: int) -> int | None:
        """Emplacement de la valeur (f32) d'une variable de description.

        Selon les versions il précède (2.0) ou suit (7.0+) le nom. On retient l'emplacement,
        hors chaîne du nom et hors pointeurs, où la valeur ressemble le plus souvent à un
        flottant plausible ; la disposition trouvée est mémorisée pour les tableaux dont
        toutes les valeurs sont nulles.
        """
        layout = (stride, name_off)
        skip = set(range(name_off, name_off + 3 * self.ps))
        best, best_score = None, 0
        for off in range(0, stride - 3, 4):
            if off in skip:
                continue
            score = 0
            for i in range(n):
                a = data + i * stride + off
                if self.pb.reloc(a - (a % self.ps)) is not None:
                    score = -1
                    break
                f = self.pb.f32(a)
                if math.isfinite(f) and 1e-4 < abs(f) < 1e7:
                    score += 1
            if score > 0 and score >= best_score:
                best, best_score = off, score
        if best is not None:
            self._value_slots[layout] = best
            return best
        return self._value_slots.get(layout)

    def scaler(self, a: int, depth: int = 0) -> dict:
        t = self.type_at(a) or "?"
        node: dict = {"type": t}
        if depth > 4:
            return node
        h = self.head(a)
        subs = []
        for v in self.vectors(*h):
            subs += [self.scaler(x, depth + 1) for x in self.vec_items(v)]
        if subs:
            node["of"] = subs
        if t == "LinearScaler":
            end = self.obj_end(a)
            f = self.pb.f32(end - (4 if self.ps == 4 else 8))
            if math.isfinite(f) and f != 0:
                node["multiplier"] = round(f, 6)
        return node

    def rank_objects(self, a: int, fam) -> list[int]:
        h = self.head(a)
        best: list[int] = []
        for v in self.vectors(*h):
            items = self.vec_items(v)
            if items and all(fam(self.type_at(x)) for x in items):
                if a in items:
                    return items
                if not best:
                    best = items
        return best or [a]

    def talent(self, a: int) -> str | None:
        """Enregistre le sort/la capacité en `a` et renvoie sa clé."""
        ty = self.type_at(a)
        fam = is_ability_type if is_ability_type(ty) else is_spell_type
        ranks = self.rank_objects(a, fam)
        base = ranks[0]
        if base in self.talents:
            return self.talents[base].key
        key = f"t{len(self.talents) + 1}"
        t = Talent(key=key, kind="ability" if fam is is_ability_type else "spell", ref=self.ref_of(base))
        self.talents[base] = t
        txt = self.localized(base, self.type_at(base))
        t.name = txt.get("name", {})
        t.description = txt.get("description", {})
        if "_paths" in txt:
            t.ref_texts = txt["_paths"]  # type: ignore[attr-defined]
        h = self.head(base)
        t.icon = self.icon_of(*h)
        for r in ranks:
            hr = self.head(r)
            rank: dict = {"ref": self.ref_of(r)}
            dv = self.desc_vars(*hr)
            if dv:
                rank["vars"] = dv
            if r != base:
                rt = self.localized(r, self.type_at(r))
                d = rt.get("description", {})
                if d and d != t.description:
                    rank["description"] = d
                ic = self.icon_of(*hr)
                if ic and ic != t.icon:
                    rank["icon"] = ic
            t.ranks.append(rank)
        if not t.name:
            t.missing.append("name")
        if not t.description:
            t.missing.append("description")
        if t.icon is None:
            t.missing.append("icon")
        return key

    def cell(self, a: int) -> dict | None:
        ty = self.type_at(a)
        if ty in (None, "NoTalent") or ty.endswith("NoTalent"):
            return None
        h = self.head(a)
        cell: dict = {"type": ty}
        for _, t in self.ptrs(*h):
            tt = self.type_at(t)
            if (is_spell_type(tt) or is_ability_type(tt)) and "talent" not in cell:
                cell["talent"] = self.talent(t)
            elif tt and tt.startswith(TALENT_REF_PREFIX):
                hh = self.head(t)
                for _, x in self.ptrs(*hh):
                    if is_spell_type(self.type_at(x)) or is_ability_type(self.type_at(x)):
                        cell["parent"] = self.talent(x)
                        break
            elif tt and "Unlock" in tt:
                cell["unlock"] = self.ref_of(t)
            elif is_spell_type(tt) or is_ability_type(tt):
                cell.setdefault("linked", []).append(self.talent(t))
        return cell if "talent" in cell else None

    # tables -------------------------------------------------------------------------------
    def grid_rows(self, v: Vec) -> list[tuple[Vec, int, int]]:
        """Vecteurs internes (un par ligne/couche) : (vecteur, début de l'élément, pas)."""
        inner = [x for x in self.inner_vectors(v) if v.data <= x.field < v.data + v.size]
        if not inner:
            return []
        stride = v.size // len(inner)
        return [(x, v.data + i * stride, stride) for i, x in enumerate(inner)]

    def points_slot(self, rows: list[tuple[Vec, int, int]]) -> int | None:
        """Emplacement du palier `talentPoints` dans une couche du livre.

        Sa position varie (après le tableau en 2.0, avant en 7.0+) : c'est l'entier 32 bits, hors
        tableau et pointeurs, qui vaut 0 sur la première couche et croît ensuite.
        """
        if len(rows) < 2:
            return None
        stride = rows[0][2]
        skip = set()
        r0, s0, _ = rows[0]
        vec_rel = r0.field - s0
        for k in range(3 * self.ps):
            skip.add(vec_rel + k)
        for off in range(0, stride - 3, 4):
            if off in skip or any(self.pb.reloc(s + off) for _, s, _ in rows):
                continue
            vals = [self.pb.i32(s + off) for _, s, _ in rows]
            if vals[0] == 0 and vals[-1] > 0 and all(0 <= a <= b < 1000 for a, b in zip(vals, vals[1:])):
                return off
        return None

    def field_start(self, a: int, b: int, rows: list[list]) -> list[int] | None:
        """Case de départ de la grille : couple d'entiers (ligne, colonne) de la partie fixe qui
        désigne une case occupée ; retenu seulement s'il est unique."""
        if not rows:
            return None
        ncols = max(len(r) for r in rows)
        found = []
        for o in range(a, b - 4, 4):
            if self.pb.reloc(o) or self.pb.reloc(o - (o % self.ps)):
                continue
            r, c = self.pb.u32(o), self.pb.u32(o + 4)
            if 0 < r < len(rows) and 0 < c < ncols and c < len(rows[r]) and rows[r][c]:
                found.append([r, c])
        return found[0] if len(found) == 1 else None

    def talents_table(self, a: int) -> dict:
        h = self.head(a)
        out: dict = {"ref": self.ref_of(a), "layers": [], "fields": []}
        for v in self.vectors(*h):
            items = self.vec_items(v)
            if items and all(self.type_at(x) == "TalentFieldResource" for x in items):
                out["fields"] = [self.field_(x) for x in items]
                continue
            rows = self.grid_rows(v)
            if rows and any(is_talent_type(self.type_at(t)) for r, _, _ in rows for t in self.vec_items(r)):
                pts_off = self.points_slot(rows)
                for r, start, stride in rows:
                    layer: dict = {"points": self.pb.i32(start + pts_off) if pts_off is not None else None}
                    layer["cells"] = [self.cell(t) for t in self.vec_items(r)]
                    for o, t in self.ptrs(start, start + stride):
                        if r.field <= o < r.field + 3 * self.ps:
                            continue
                        tt = self.type_at(t)
                        if tt and "Unlock" in tt:
                            layer["unlock"] = self.ref_of(t)
                    out["layers"].append(layer)
        return out

    def field_(self, a: int) -> dict:
        h = self.head(a)
        txt = self.localized(a, "TalentFieldResource")
        out: dict = {"ref": self.ref_of(a), "name": txt.get("name", {}), "icon": self.icon_of(*h), "rows": []}
        for v in self.vectors(*h):
            rows = self.grid_rows(v)
            if rows and any(is_talent_type(self.type_at(t)) for r, _, _ in rows for t in self.vec_items(r)):
                out["rows"] = [[self.cell(t) for t in self.vec_items(r)] for r, _, _ in rows]
                break
        start = self.field_start(h[0], h[1], out["rows"])
        if start:
            out["start"] = start
        return out

    def classes(self) -> list[dict]:
        out = []
        for c in self.pb.objects_of("CharacterClass"):
            h = self.head(c)
            code = None
            for o in range(h[0], h[1], self.ps):
                s = self.cstring(o)
                if s and re.fullmatch(r"[A-Z][A-Z_]{2,}", s):
                    code = s
                    break
            if code in (None, "CORK", "ANGEL"):
                continue
            table = next((t for _, t in self.ptrs(*h) if self.type_at(t) == "BaseTalentsTable"), None)
            txt = self.localized(c, "CharacterClass")
            out.append({"addr": c, "code": code, "ref": self.ref_of(c), "name": txt.get("name", {}),
                        "uiName": txt.get("uiName"), "table": table})
        return out


# --- interface 17.0 -----------------------------------------------------------------------

ALIGN = ["low", "high", "center", "both", "lowAbs"]

# Décalages des champs `client.Widgets.*` dans le pack.bin 64 bits, relevés en confrontant les
# objets du client 17 aux `.xdb` 7.0 de même nom (Interface/Ingame/ContextTalents) : mêmes noms,
# mêmes valeurs de placement (MainForm 15/508 × 120/749, BasePanel11 89/59 haut 279…).
W_BACK = 0x28          # WidgetLayer* BackLayer
W_CHILDREN = 0x30      # Widget*[] Children
W_NAME = 0x58          # ASCIIString Name
W_X = 0x78             # WidgetPlacement X : Align u32, HighPos f32 (+4), Pos f32 (+0x10), Size f32 (+0x14)
W_Y = 0x98             # WidgetPlacement Y
W_PRIORITY = 0xE8
B_TEXTTAG = 0x120      # WidgetButton.TextTag
B_VARIANTS = 0x1C0     # WidgetButton.Variants[] (pas 0x188, LayerHighlight en +8)
B_VARIANT_STRIDE = 0x188
L_COLOR = 0x28         # WidgetLayer.Color (ARGB)


class UiExtractor:
    """Arbre de widgets d'un addon d'interface (clients 64 bits) → JSON + textures PNG."""

    def __init__(self, ex: Extractor, out: Path, log=print) -> None:
        self.ex = ex
        self.pb = ex.pb
        self.out = out
        self.log = log
        self.textures: dict[str, dict] = {}

    def addon(self, name: str) -> int | None:
        for a in self.pb.objects_of("UIAddon"):
            h = self.ex.head(a)
            for o in range(h[0], h[1], 8):
                if self.ex.cstring(o) == name:
                    return a
        return None

    def placement(self, a: int, base: int) -> dict:
        p = {}
        for axis, off in (("x", W_X), ("y", W_Y)):
            o = a + off
            align = self.pb.u32(o)
            d = {"align": ALIGN[align] if align < len(ALIGN) else align}
            for key, k in (("high", 4), ("pos", 0x10), ("size", 0x14)):
                v = self.pb.f32(o + k)
                if v:
                    d[key] = round(v, 3)
            p[axis] = d
        return p

    def texture(self, single: int | None) -> str | None:
        if single is None or self.ex.type_at(single) != "UISingleTexture":
            return None
        tex = next((t for _, t in self.ex.ptrs(*self.ex.head(single)) if self.ex.type_at(t) == "UITexture"), None)
        if tex is None:
            return None
        loc = self.ex.texture_location(tex)
        if loc is None:
            return None
        pak, entry, dims = loc
        path = pak_entry_name(pak, entry) or f"{os.path.basename(pak)}#{entry}"
        key = re.sub(r"\.\(UITexture\)\.bin$", "", path.split("/")[-1])
        if key in self.textures:
            return key
        data = read_pak_entry(pak, entry)
        info = {"path": path, **dims}
        if data:
            try:
                hint = (dims["w"], dims["h"]) if dims["w"] and dims["h"] else None
                try:
                    img, _ = decode_uitexture(data, hint)
                except ValueError:
                    img, _ = decode_uitexture(data)
                if dims["realW"] and dims["realH"]:
                    img = img.crop((0, 0, min(dims["realW"], img.width), min(dims["realH"], img.height)))
                self.out.mkdir(parents=True, exist_ok=True)
                img.save(self.out / f"{key}.png", optimize=True)
                info["file"] = f"{key}.png"
                info["width"], info["height"] = img.size
            except Exception as exc:  # pragma: no cover
                self.log(f"  texture illisible {path}: {exc}")
        self.textures[key] = info
        return key

    def layer(self, a: int | None) -> dict | None:
        ty = self.ex.type_at(a)
        if not ty or not ty.startswith("WidgetLayer"):
            return None
        out: dict = {"type": ty, "color": f"{self.pb.u32(a + L_COLOR):08x}"}
        for _, t in self.ex.ptrs(*self.ex.head(a)):
            tex = self.texture(t)
            if tex:
                out["texture"] = tex
                break
        return out

    def widget(self, a: int, depth: int = 0) -> dict:
        ty = self.ex.type_at(a)
        w: dict = {"type": ty, "name": self.ex.cstring(a + W_NAME), "place": self.placement(a, a),
                   "priority": self.pb.i32(a + W_PRIORITY)}
        back = self.layer(self.pb.ptr(a + W_BACK))
        if back:
            w["back"] = back
        h = self.ex.head(a)
        for o, t in self.ex.ptrs(*h):
            if o - a != W_BACK and (self.ex.type_at(t) or "").startswith("WidgetLayer"):
                w["front"] = self.layer(t)
        if ty == "WidgetButton":
            tag = self.ex.cstring(a + B_TEXTTAG)
            if tag:
                w["textTag"] = tag
            d = self.pb.data_ptr(a + B_VARIANTS)
            n = self.pb.word(a + B_VARIANTS + 8)
            if d is not None and n:
                hl = []
                for k in range(n // B_VARIANT_STRIDE):
                    layer = self.layer(self.pb.ptr(d + k * B_VARIANT_STRIDE + 8))
                    hl.append(layer)
                if any(hl):
                    w["highlight"] = hl
        kids = []
        d = self.pb.data_ptr(a + W_CHILDREN)
        n = self.pb.word(a + W_CHILDREN + 8)
        if d is not None and 0 < n < 1 << 16 and depth < 12:
            for k in range(0, n, 8):
                t = self.pb.ptr(d + k)
                if t is not None and (self.ex.type_at(t) or "").startswith("Widget"):
                    kids.append(self.widget(t, depth + 1))
        if kids:
            w["children"] = kids
        return w

    def related(self, folder: str) -> list[str]:
        """Textures du dossier `RelatedTextures` de l'addon, commutées par script (mana/rage…)."""
        keys = []
        packs = os.path.expanduser(self.ex.spec["packs_dir"])
        for pak_name in self.pb.pak_names:
            if not pak_name.startswith("Interface"):
                continue
            z = _zip(os.path.join(packs, pak_name))
            if z is None:
                continue
            for i, info in enumerate(z.infolist()):
                if info.filename.startswith(folder) and info.filename.endswith("(UITexture).bin"):
                    key = re.sub(r"\.\(UITexture\)\.bin$", "", info.filename.split("/")[-1])
                    if key not in self.textures:
                        img, _ = decode_uitexture(z.read(info))
                        from tools.uitexture import trim_transparent_padding
                        img = trim_transparent_padding(img)
                        self.out.mkdir(parents=True, exist_ok=True)
                        img.save(self.out / f"{key}.png", optimize=True)
                        self.textures[key] = {"path": info.filename, "file": f"{key}.png",
                                              "width": img.width, "height": img.height, "trimmed": True}
                    keys.append(key)
        return keys

    def run(self, addon: str, related_folder: str) -> dict:
        a = self.addon(addon)
        if a is None:
            raise LookupError(f"addon {addon} introuvable")
        form = next((t for _, t in self.ex.ptrs(*self.ex.head(a)) if self.ex.type_at(t) == "WidgetForm"), None)
        root = self.widget(form)
        related = self.related(related_folder)
        return {"addon": addon, "version": self.ex.spec["id"], "root": root, "related": related,
                "textures": self.textures}


def extract_ui(spec: dict, out: Path, log=print) -> dict:
    ex = Extractor(spec, IconSink(out / "icons", dry=True), log)
    ui = UiExtractor(ex, out / "ui", log)
    data = ui.run("ContextTalents", "Interface/Ingame/ContextTalents/")
    (out / "ui").mkdir(parents=True, exist_ok=True)
    (out / "ui" / "context_talents.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    log(f"interface {spec['id']} : {len(data['textures'])} textures")
    return data


# --- orchestration ------------------------------------------------------------------------

def talent_json(t: Talent) -> dict:
    d: dict = {"kind": t.kind, "ref": t.ref, "name": t.name}
    if t.description:
        d["description"] = t.description
    if t.icon:
        d["icon"] = t.icon
    d["ranks"] = t.ranks
    if t.missing:
        d["missing"] = t.missing
    return d


def systems_of(tables: list[dict]) -> list[str]:
    s = set()
    for tb in tables:
        if any(l["cells"] for l in tb.get("layers", [])):
            s.add("book")
        for f in tb.get("fields", []):
            if f["rows"]:
                s.add(f"grid{len(f['rows'])}x{max(len(r) for r in f['rows'])}")
    return sorted(s)


def extract_version(spec: dict, out: Path, icons: IconSink, log=print) -> dict:
    log(f"== {spec['id']} ({spec['client']})")
    ex = Extractor(spec, icons, log)
    langs = [t.lang for t in ex.texts]
    vdir = out / spec["id"]
    vdir.mkdir(parents=True, exist_ok=True)
    entries = []
    for c in ex.classes():
        ex.talents = {}
        if c["table"] is None:
            log(f"  {c['code']}: pas de BaseTalentsTable")
            continue
        table = ex.talents_table(c["table"])
        n_talents = len(ex.talents)
        data = {
            "version": spec["id"], "code": c["code"], "ref": c["ref"], "name": c["name"],
            "languages": langs, "format": ex.pb.fmt,
            "book": {"ref": table["ref"], "layers": table["layers"]},
            "fields": table["fields"],
            "talents": {t.key: talent_json(t) for t in ex.talents.values()},
        }
        slug = c["code"].lower()
        (vdir / f"{slug}.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        missing_names = sum(1 for t in ex.talents.values() if "name" in t.missing)
        entries.append({
            "code": c["code"], "slug": slug, "name": c["name"], "talents": n_talents,
            "layers": len(table["layers"]), "fields": len(table["fields"]),
            "systems": systems_of([table]), "missingNames": missing_names,
        })
        log(f"  {c['code']:<12} {n_talents:4d} talents, {len(table['layers'])} couches, "
            f"{len(table['fields'])} grilles, noms manquants {missing_names}")
    return {"id": spec["id"], "label": spec["label"], "client": spec["client"], "languages": langs,
            "format": ex.pb.fmt, "classes": entries}


def run(manifest: dict, out: Path, only: list[str] | None = None, log=print) -> dict:
    icons = IconSink(out / "icons")
    index_path = out / "index.json"
    previous = {}
    if index_path.exists() and only:
        previous = {v["id"]: v for v in json.loads(index_path.read_text()).get("versions", [])}
    versions = []
    for spec in manifest["versions"]:
        if only and spec["id"] not in only:
            if spec["id"] in previous:
                versions.append(previous[spec["id"]])
            continue
        try:
            versions.append(extract_version(spec, out, icons, log))
        except FileNotFoundError as exc:
            log(f"  ignorée : {exc}")
    index = {"versions": versions, "unavailable": manifest.get("unavailable", [])}
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1))
    total = sum(icons.written.values())
    log(f"icônes écrites : {len(icons.written)} ({total / 1e6:.1f} Mo)")
    return index


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--ui", action="store_true", help="n'extraire que l'interface ContextTalents 17.0")
    args = ap.parse_args(argv)
    manifest = json.loads(args.manifest.read_text())
    if args.ui:
        spec = next(v for v in manifest["versions"] if v["id"] == manifest.get("ui_version", "17.0"))
        extract_ui(spec, args.out)
        return 0
    run(manifest, args.out, args.only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
