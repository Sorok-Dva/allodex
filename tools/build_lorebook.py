#!/usr/bin/env python3
"""Données de la page Lorebook (`/lorebook`) à partir de l'extraction `public/game/lore/`.

Entrées : les fichiers de `tools/extract_lore.py` (catégories, tables `ru/` et `fr/`, glossaire,
séries, secrets, liens, atlas, corpus) et le matériel communautaire traduit par Allodex
(`tools/lorebook/community/*.md`, `tools/lorebook/atlas/*.json` : atlas et récits de Makar
Terentiev, repris avec son accord). Le russe original d'un texte communautaire est relu dans le
corpus (`refs/lorebook`, git-ignoré) quand il est présent.

Sorties dans `public/game/lorebook/` (chargées à la demande par la page) :

* `meta.json` — sections, groupes, volumes, crédit ;
* `list/<langue>/<section>.json` — groupes et lignes de la liste : `[id, groupe, bloc, drapeaux,
  titre, sous-titre]` (drapeaux : 1 communautaire, 2 anglais manquant, 4 russe révisé) ;
* `text/<langue>/<section>-<bloc>.json` — corps des entrées dans une langue : chaque texte est
  `[clé de champ, texte ou 0, drapeaux, extra?]` ; 0 = absent dans cette langue : la page lit le
  même champ dans le bloc de la langue de repli (mêmes entrées, même ordre dans les trois langues) ;
* `search/<langue>/<clé>.json` — index inversé fragmenté par les deux premiers caractères du mot
  (clé = leurs points de code en hexadécimal) : `mot → "ids|ids titre"` (ids globaux croissants,
  écarts en base 36) ; `dir/<langue>/<n>.json` — ids globaux → `[section, id, titre]` par
  blocs de 64 ;
* `names/<langue>.json` — nom propre → entrée (liens automatiques dans les textes).

Ordre de repli d'un texte : anglais → français → russe (page en anglais), français → anglais →
russe, russe → anglais → français. Un texte d'une autre langue que celle demandée porte cette
langue (badge « pas encore traduit ») ; un russe réécrit depuis l'anglais officiel porte le
drapeau 1 (badge discret).
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_LORE = ROOT / "public" / "game" / "lore"
DEFAULT_OUT = ROOT / "public" / "game" / "lorebook"
DEFAULT_SRC = HERE / "lorebook"


def default_corpus() -> Path:
    """Corpus communautaire : `$ALLODS_LORE_CORPUS`, sinon celui du manifeste de l'extraction."""
    import os
    if os.environ.get("ALLODS_LORE_CORPUS"):
        return Path(os.environ["ALLODS_LORE_CORPUS"])
    try:
        return Path(json.loads((HERE / "lore_manifest.json").read_text(encoding="utf-8"))["corpus"])
    except (OSError, KeyError, ValueError):
        return ROOT / "refs" / "lorebook"

LANGS = ("en", "fr", "ru")
FALLBACK = {"en": ("en", "fr", "ru"), "fr": ("fr", "en", "ru"), "ru": ("ru", "en", "fr")}
SECTIONS = ("timeline", "atlas", "library", "characters", "secrets", "quests")
MIN_LOC = 300            # sous ce seuil, les rattachements de pack.bin sont peu fiables (petits entiers)
CHUNK_BYTES = 90_000     # taille visée d'un bloc de corps (anglais, JSON compact)
DIR_BLOCK = 64
SCENE_MIN_CHARS = 100    # une réplique de scène plus courte est de la mécanique, pas de la narration
LETTER_MIN_CHARS = 150
TOKEN_MIN = 3
FLAG_COMMUNITY, FLAG_EN_MISSING, FLAG_REVISED = 1, 2, 4
TEXT_REVISED = 1

SEARCH_PRIORITY = {"character": 0, "secret": 0, "allod": 0, "region": 0, "series": 1, "story": 1, "chronology": 1,
                   "faction": 1, "place": 2, "event": 2, "quest": 3, "document": 3, "letter": 3, "atlasNote": 3,
                   "ambience": 4, "scene": 6, "dialogue": 7}
QUEST_FIELDS = ("goal", "startText", "checkText", "finishText", "kickText")
CREDIT_FALLBACK = {"line": "Allods atlas and community lore material compiled by Makar Terentiev (DarkyAndSparky), "
                           "https://github.com/DarkyAndSparky/atlas-ao",
                   "short": "Makar Terentiev (DarkyAndSparky)", "url": "https://github.com/DarkyAndSparky/atlas-ao"}
TRANSLATED_BY = "Community text, translated by Allodex"

STOPWORDS = set("""
the and for with that this from are was were you your our not but have has had his her its they them their
there what when where which who will would can could all any one out into than then also been being more
some such only very just about over like may must shall should upon these those each other every here
les des une est pas que qui pour dans avec sur par mais son ses aux ont vous nous leur leurs cette ces
elle ils elles lui être avoir tout tous plus bien comme sans sous chez dont été fait faire
это как что так там где его она они или ещё уже был была было были будет для при над под без все всё
тебя тебе меня мне нас вас вам нам ним ней них его её их чем тем том той кто если только может
""".split())


# --- textes --------------------------------------------------------------------------------------

def norm_text(s: str) -> str:
    """Forme de recherche : minuscules, diacritiques latins retirés, ё → е."""
    s = s.lower().replace("ё", "е")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if not ("̀" <= c <= "ͯ"))


TOKEN_RE = re.compile(r"[0-9a-zа-я]+")


def tokens(s: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(norm_text(s)) if len(t) >= TOKEN_MIN and t not in STOPWORDS]


def shard_key(token: str) -> str:
    return "".join(f"{ord(c):x}" for c in token[:2])


def resolve(texts: dict[str, str | None], lang: str) -> tuple[str, str]:
    """(texte, langue d'origine) selon l'ordre de repli ; langue vide = celle demandée."""
    for i, candidate in enumerate(FALLBACK[lang]):
        value = texts.get(candidate)
        if value and value.strip():
            return value, ("" if i == 0 else candidate)
    return "", ""


def excerpt(s: str, n: int = 72) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n - 1].rsplit(" ", 1)[0] + "…"


def b36(n: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while True:
        n, r = divmod(n, 36)
        out = digits[r] + out
        if not n:
            return out


def encode_postings(ids: list[int]) -> str:
    prev, out = 0, []
    for i in ids:
        out.append(b36(i - prev))
        prev = i
    return ",".join(out)


def slug(s: str) -> str:
    s = norm_text(s)
    return re.sub(r"[^0-9a-z]+", "-", s).strip("-") or "x"


# --- sources -------------------------------------------------------------------------------------

class Lore:
    """Extraction `public/game/lore/` : textes par `loc` dans les trois langues."""

    def __init__(self, root: Path):
        self.root = root
        self.cats: dict[str, list[dict]] = {}
        self.ru: dict[str, str] = {}
        self.fr: dict[str, str] = {}
        for p in sorted(root.glob("*.json")):
            name = p.stem
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, list) and data and isinstance(data[0], dict) and "fields" in data[0]:
                self.cats[name] = data
        for lang, table in (("ru", self.ru), ("fr", self.fr)):
            for p in sorted((root / lang).glob("*.json")) if (root / lang).exists() else []:
                table.update(json.loads(p.read_text(encoding="utf-8")))

        def opt(name, default):
            p = root / name
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default
        self.series = opt("series.json", [])
        self.atlas = opt("atlas.json", {})
        self.links = opt("links.json", {})
        self.community = opt("community.json", {})
        self.by_id = {e["id"]: (cat, e) for cat, es in self.cats.items() for e in es}

    def texts(self, f: dict) -> dict[str, str | None]:
        loc = str(f["loc"])
        en = f.get("en") if f.get("en_status") in ("official", "partial") else None
        return {"en": en, "fr": self.fr.get(loc), "ru": self.ru.get(loc)}


def read_markdown(path: Path) -> tuple[dict, str]:
    """Fichier `---` / en-tête `clé: valeur` / `---` puis Markdown."""
    raw = path.read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    body = raw
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", raw, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = m.group(2)
    return meta, body.strip()


def read_source(corpus: Path, rel: str) -> str | None:
    p = corpus / rel
    if not rel or not p.exists() or p.suffix.lower() != ".txt":
        return None
    b = p.read_bytes()
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return b.decode(enc).replace("\r\n", "\n").strip()
        except UnicodeDecodeError:
            continue
    return None


def split_eras(text: str, heading: str) -> list[tuple[str, str]]:
    """Découpe un texte en sections de titre `heading` (regex de ligne) ; `(titre, corps)`."""
    out: list[tuple[str, str]] = []
    title, buf = "", []
    for line in text.splitlines():
        if re.match(heading, line):
            if title or "".join(buf).strip():
                out.append((title, "\n".join(buf).strip()))
            title, buf = re.sub(heading, "", line).strip(), []
        else:
            buf.append(line)
    if title or "".join(buf).strip():
        out.append((title, "\n".join(buf).strip()))
    return out


# --- construction --------------------------------------------------------------------------------

def zone_of(path: str | None) -> str | None:
    """Clé de région d'une ressource : dossier de carte, de quêtes ou d'instance de PNJ."""
    if not path:
        return None
    s = path.split("/")
    if s[0] == "Maps" and len(s) > 2:
        return s[1]
    if s[:2] == ["World", "Quests"] and len(s) > 3:
        return s[2]
    if s[0] in ("Characters", "Creatures") and "Instances" in s:
        i = s.index("Instances")
        if i + 1 < len(s) - 1:
            return s[i + 1]
    return None


ATLAS_CATEGORIES = ["Story allod", "Mentioned island", "Confrontation island", "Unstable island", "Other",
                    "Allods Adventure", "Cloud Pirates"]
ATLAS_DOCS = {"1": "ATLAS ALLODS.docx", "2": "ATLAS ALLODS.docx",
              "ao1": "Астральные Острова(AO2.0+) ч1.docx", "ao2": "Астральные Острова(AO2.0+) ч2.docx",
              "ao3": "Астральные Острова(AO2.0+) Часть 3.docx", "beta": "Астральные Острова BETA(ОБТ и Классики).docx"}


def atlas_key(name: str) -> str:
    """Clé d'appariement d'un nom d'allod : sans la précision entre parenthèses, ni ponctuation."""
    base = re.sub(r"\(.*?\)", "", name)
    return re.sub(r"[^0-9a-zа-я]+", " ", norm_text(base)).strip()


def humanize(key: str) -> str:
    key = re.sub(r"([a-z])([A-Z0-9])", r"\1 \2", key.replace("_", " "))
    return re.sub(r"\s+", " ", key).strip()


class Builder:
    def __init__(self, lore: Lore, src: Path, corpus: Path, credit: dict | None = None):
        self.lore = lore
        self.src = src
        self.corpus = corpus
        cc = (lore.community or {}).get("credit") or {}
        self.credit = {**CREDIT_FALLBACK, **{k: v for k, v in cc.items() if k in ("line", "short", "url", "author")}, **(credit or {})}
        self.entries: dict[str, list[dict]] = {s: [] for s in SECTIONS}
        self.groups: dict[str, list[dict]] = {s: [] for s in SECTIONS}
        self.ref_of: dict[str, str] = {}        # id → « section/id »

    # -- enregistrements ---------------------------------------------------------------------
    def field(self, key: str, f: dict) -> dict | None:
        if f.get("loc", 0) < MIN_LOC:
            return None
        texts = self.lore.texts(f)
        if not any(v and v.strip() for v in texts.values()):
            return None
        return {"key": key, "texts": texts, "revised": bool(f.get("ru_revised"))}

    def fields(self, e: dict, order: tuple[str, ...] | None = None) -> list[dict]:
        keys = [k for k in (order or ()) if k in e["fields"]] + [k for k in e["fields"] if not order or k not in order]
        out = []
        for k in keys:
            rec = self.field(k, e["fields"][k])
            if rec:
                out.append(rec)
        return out

    def group(self, section: str, gid: str, label: dict[str, str] | None = None, key: str | None = None) -> int:
        """Index du groupe (créé au besoin) ; `key` = clé i18n de l'interface, sinon libellé par langue."""
        gs = self.groups[section]
        for i, g in enumerate(gs):
            if g["id"] == gid:
                return i
        g = {"id": gid}
        if key:
            g["key"] = key
        if label:
            g["label"] = label
        gs.append(g)
        return len(gs) - 1

    def add(self, section: str, group: int, entry: dict) -> dict:
        entry["section"], entry["group"] = section, group
        self.entries[section].append(entry)
        self.ref_of[entry["id"]] = f"{section}/{entry['id']}"
        return entry

    @staticmethod
    def title_texts(rec: dict | None, fallback: str = "") -> dict[str, str | None]:
        if rec:
            return {k: (excerpt(v, 90) if v else v) for k, v in rec["texts"].items()}
        return {"en": fallback, "fr": None, "ru": None}

    def official(self, e: dict, kind: str, title_keys: tuple[str, ...], body_order: tuple[str, ...] | None = None,
                 subtitle_key: str | None = None) -> dict | None:
        recs = self.fields(e, body_order)
        if not recs:
            return None
        title = next((r for k in title_keys for r in recs if r["key"] == k), None)
        sub = next((r for r in recs if subtitle_key and r["key"] == subtitle_key), None)
        body = [r for r in recs if r is not title]
        if title is None:
            title = {"key": "title", "texts": {k: excerpt(v) if v else v for k, v in recs[0]["texts"].items()}, "revised": False}
        entry = {"id": e["id"], "kind": kind, "title": self.title_texts(title), "fields": body,
                 "meta": {k: e[k] for k in ("era",) if k in e}}
        if sub and sub is not title:
            entry["subtitle"] = self.title_texts(sub)
            entry["fields"] = [r for r in body if r is not sub]
        return entry

    # -- sections ----------------------------------------------------------------------------
    def build(self) -> None:
        self.build_regions_index()
        self.build_timeline()
        self.build_atlas()
        self.build_library()
        self.build_characters()
        self.build_secrets()
        self.build_quests()
        self.resolve_links()

    def build_regions_index(self) -> None:
        """Régions = dossiers de cartes qui ont des lieux. Nom : la zone du même nom que le dossier,
        sinon le nom du dossier s'il est lisible (« Kania », « IllusionWorld »), sinon le préfixe le
        plus fréquent des noms de lieux (« Tenebra, Summer Manor » → « Tenebra »)."""
        self.region_places: dict[str, list[str]] = collections.defaultdict(list)
        self.region_title: dict[str, dict] = {}
        named: dict[str, list[dict]] = collections.defaultdict(list)
        for e in self.lore.cats.get("places", []):
            z = zone_of(e.get("path"))
            if not z:
                continue
            self.region_places[z].append(e["id"])
            rec = self.field("name", e["fields"]["name"]) if "name" in e["fields"] else None
            if not rec:
                continue
            if Path(e["path"]).name.split(".")[0].lower() == z.lower() and e.get("type") == "ZoneResource":
                self.region_title[z] = rec
            named[z].append(rec)
        for z, recs in named.items():
            if z in self.region_title:
                continue
            if re.fullmatch(r"[A-Za-z]+", z):
                self.region_title[z] = {"key": "name", "texts": {lang: humanize(z) for lang in LANGS}, "revised": False}
                continue
            title = {}
            for lang in LANGS:
                prefixes = collections.Counter(resolve(r["texts"], lang)[0].split(",")[0].strip() for r in recs)
                title[lang] = prefixes.most_common(1)[0][0] if prefixes else humanize(z)
            self.region_title[z] = {"key": "name", "texts": title, "revised": False}

    def zone_group(self, section: str, z: str | None, other_key: str) -> int:
        if not z:
            return self.group(section, "other", key=other_key)
        t = self.region_title.get(z)
        label = {lang: resolve(t["texts"], lang)[0] for lang in LANGS} if t else {lang: humanize(z) for lang in LANGS}
        return self.group(section, f"zone-{z}", label=label)

    def community_entry(self, meta: dict, body_en: str, body_ru: str | None, eid: str, kind: str,
                        title_ru: str | None = None) -> dict:
        return {"id": eid, "kind": kind, "community": True,
                "title": {"en": meta.get("title") or eid, "fr": None, "ru": title_ru or meta.get("title_ru")},
                "fields": [{"key": "communityText", "texts": {"en": body_en, "fr": None, "ru": body_ru},
                            "revised": False, "markdown": True}],
                "meta": {"source": meta.get("source", ""), "credit": self.credit.get("line"),
                         "translated": TRANSLATED_BY}}

    def build_timeline(self) -> None:
        cdir = self.src / "community"
        chrono = cdir / "chronology.md"
        if chrono.exists():
            meta, body = read_markdown(chrono)
            g = self.group("timeline", "chronology", key="lore.group.chronology")
            eras = split_eras(body, r"^##\s+")
            src_ru = read_source(self.corpus, meta.get("source", ""))
            # titres russes : lignes courtes qui ne sont ni des puces (-, —, •) ni des dates
            eras_ru = split_eras(src_ru, r"^(?![-—–•(\s])(?=.{1,80}$)") if src_ru else []
            # le russe : titres = lignes qui ne sont pas des puces ; on ne l'aligne que si le compte concorde
            eras_ru = [x for x in eras_ru if x[1]]
            aligned = len(eras_ru) == len([x for x in eras if x[1]])
            k = 0
            for i, (title, text) in enumerate(eras):
                if not text:
                    continue
                ru = eras_ru[k] if aligned else None
                k += 1
                ru_title = ru[0] if ru and ru[0] and ru[0] != meta.get("title_ru") else ("До Старой Эры" if ru else None)
                e = self.community_entry(meta, text, ru[1] if ru else None, f"c-chronology-{i}", "chronology", ru_title)
                e["title"]["en"] = title or meta.get("title", "Chronology")
                self.add("timeline", g, e)
        g = self.group("timeline", "events", key="lore.group.events")
        for e in self.lore.cats.get("events", []):
            en = self.official(e, "event", ("title", "name"), ("shortDescription", "description"))
            if en:
                self.add("timeline", g, en)
        for e in self.lore.cats.get("scenes", []):
            recs = self.fields(e)
            longest = max((len(r["texts"]["ru"] or "") for r in recs), default=0)
            if longest < SCENE_MIN_CHARS:
                continue
            entry = self.official(e, "scene", ())
            if entry:
                entry["fields"] = recs
                self.add("timeline", self.zone_group("timeline", zone_of(e.get("path")), "lore.group.narration"), entry)

    def atlas_rows(self) -> dict[str, dict]:
        """Nom russe (sans espaces) → ligne de `atlas.json` (lieu du client retrouvé)."""
        return {r["name"].strip(): r for r in (self.lore.atlas or {}).get("rows", [])}

    def build_atlas(self) -> None:
        allods_path = self.src / "atlas" / "allods.json"
        desc_path = self.src / "atlas" / "descriptions.json"
        allods = json.loads(allods_path.read_text(encoding="utf-8")) if allods_path.exists() else []
        descs = json.loads(desc_path.read_text(encoding="utf-8")) if desc_path.exists() else []
        for extra in sorted((self.src / "atlas").glob("astral-islands-*.json")):
            descs += json.loads(extra.read_text(encoding="utf-8"))
        by_ru = collections.defaultdict(list)
        for d in descs:
            if d.get("text"):
                by_ru[atlas_key(d["ru"])].append(d)
        used_descs = set()
        rows = self.atlas_rows()
        loc_owner = {}
        for cat, es in self.lore.cats.items():
            if cat in ("places", "characters", "factions", "quests", "secrets"):
                for e in es:
                    for f in e["fields"].values():
                        loc_owner.setdefault(f["loc"], e["id"])
        category_key = {}
        for a in sorted(allods, key=lambda x: (ATLAS_CATEGORIES.index(x.get("category")) if x.get("category") in ATLAS_CATEGORIES
                                                else len(ATLAS_CATEGORIES), norm_text(x.get("en") or x["ru"]))):
            cat = a.get("category") or "Other"
            gid = "allods-" + slug(cat)
            if gid not in category_key:
                key = f"lore.group.{gid}" if cat in ATLAS_CATEGORIES else None
                category_key[gid] = self.group("atlas", gid, label=None if key else {lang: cat for lang in LANGS}, key=key)
            row = rows.get(a["ru"].strip())
            texts = []
            if a.get("description"):
                texts.append({"key": "atlasSummary", "texts": {"en": a["description"], "fr": None, "ru": None},
                              "revised": False})
            for d in by_ru.get(atlas_key(a["ru"]), []):
                used_descs.add(id(d))
                texts.append({"key": "atlasDescription", "texts": {"en": d["text"], "fr": None, "ru": None},
                              "revised": False, "markdown": True})
                # sous-lieux de la même rubrique (1.1.1 Новоград…)
                for sub in descs:
                    if sub.get("part") == d.get("part") and sub.get("parent") == d["section"] and sub.get("text") \
                            and d.get("parent") != "0" and id(sub) not in used_descs:
                        used_descs.add(id(sub))
                        texts.append({"key": "atlasSubPlace", "heading": sub.get("en") or sub["ru"],
                                      "texts": {"en": sub["text"], "fr": None, "ru": None}, "revised": False,
                                      "markdown": True})
            facts = [[k, a[k]] for k in ("climate", "size", "faction", "category", "type", "archipelago", "holder",
                                          "expansion") if a.get(k)]
            entry = {"id": f"a-{a['id']}", "kind": "allod", "community": True,
                     "title": {"en": a.get("en") or a["ru"], "fr": None, "ru": a["ru"]},
                     "subtitle": {"en": a.get("category", ""), "fr": None, "ru": None},
                     "fields": texts, "facts": facts,
                     "meta": {"credit": self.credit.get("line"), "translated": TRANSLATED_BY,
                              "source": "atlas-ao server/seed-data.json" + (", ATLAS ALLODS.docx" if len(texts) > 1 or
                                                                          (texts and texts[0]["key"] != "atlasSummary") else ""),
                              "name_official": bool(a.get("en_official"))}}
            locs = row.get("loc") if row else None
            locs = locs if isinstance(locs, list) else [locs] if locs is not None else []
            owners = [loc_owner[x] for x in locs if x in loc_owner]
            if owners:
                entry["links"] = {"place": owners[:1]}
            self.add("atlas", category_key[gid], entry)
        # notes de l'atlas sans allod correspondant (îles des documents de travail, sections techniques)
        notes = [d for d in descs if d.get("text") and id(d) not in used_descs]
        if notes:
            gn = self.group("atlas", "atlas-notes", key="lore.group.atlasNotes")
            for n, d in enumerate(notes):
                self.add("atlas", gn, {
                    "id": f"n-{slug(str(d.get('part', '')))}-{n}", "kind": "atlasNote", "community": True,
                    "title": {"en": d.get("en") or d["ru"], "fr": None, "ru": d["ru"]},
                    "fields": [{"key": "atlasDescription", "texts": {"en": d["text"], "fr": None, "ru": None},
                                "revised": False, "markdown": True}],
                    "meta": {"credit": self.credit.get("line"), "translated": TRANSLATED_BY,
                             "source": ATLAS_DOCS.get(str(d.get("part")), "ATLAS ALLODS.docx")}})
        # régions et lieux du client
        gr = self.group("atlas", "regions", key="lore.group.regions")
        region_of_place = {}
        for z, ids in sorted(self.region_places.items(), key=lambda kv: -len(kv[1])):
            t = self.region_title.get(z)
            if not t:
                continue
            entry = {"id": f"z-{z}", "kind": "region", "title": dict(t["texts"]), "fields": [],
                     "meta": {"path": f"Maps/{z}"}, "links": {"places": ids}, "zone": z}
            for pid in ids:
                region_of_place[pid] = entry["id"]
            self.add("atlas", gr, entry)
        gp = self.group("atlas", "places", key="lore.group.places")
        for e in self.lore.cats.get("places", []):
            entry = self.official(e, "place", ("name",), ("description",))
            if entry:
                if e["id"] in region_of_place:
                    entry.setdefault("links", {})["region"] = [region_of_place[e["id"]]]
                self.add("atlas", gp, entry)

    def build_library(self) -> None:
        lib = {e["id"]: e for e in self.lore.cats.get("library", [])}
        in_series = set()
        gs = self.group("library", "series", key="lore.group.series")
        for i, s in enumerate(self.lore.series):
            pages = [lib[x] for x in s.get("ids", []) if x in lib]
            if not pages:
                continue
            items = []
            for p in pages:
                in_series.add(p["id"])
                recs = self.fields(p, ("name", "description"))
                head = next((r for r in recs if r["key"] == "name"), None)
                items.append({"id": p["id"], "heading": head, "fields": [r for r in recs if r is not head]})
            first = items[0]["heading"]
            title = {"en": s.get("example_en_title") and re.sub(r"^(Page \d+ of |Letter \d+ from )", "", s["example_en_title"]),
                     "fr": None, "ru": s["series"]}
            if first:
                title = {k: (title.get(k) or v) for k, v in first["texts"].items()} if not title["en"] else title
            self.add("library", gs, {"id": f"s-{i}", "kind": "series", "title": title, "fields": [], "items": items,
                                     "subtitle": {"en": f"{len(items)} pages", "fr": f"{len(items)} pages",
                                                  "ru": f"{len(items)} стр."}})
        gstories = self.group("library", "stories", key="lore.group.stories")
        for p in sorted((self.src / "community").glob("*.md")):
            meta, body = read_markdown(p)
            if meta.get("kind") == "chronology":
                continue
            ru = read_source(self.corpus, meta.get("source", ""))
            self.add("library", gstories, self.community_entry(meta, body, ru, meta.get("id") or f"c-{p.stem}", "story"))
        gd = self.group("library", "documents", key="lore.group.documents")
        ga = self.group("library", "ambience", key="lore.group.ambience")
        for e in self.lore.cats.get("library", []):
            if e["id"] in in_series:
                continue
            entry = self.official(e, "document" if e.get("kind") == "document" else "ambience", ("name",), ("description",))
            if entry:
                self.add("library", gd if e.get("kind") == "document" else ga, entry)
        gl = self.group("library", "letters", key="lore.group.letters")
        for e in self.lore.cats.get("mail", []):
            body = e["fields"].get("body")
            if not body or len(self.lore.ru.get(str(body["loc"]), "")) < LETTER_MIN_CHARS:
                continue
            entry = self.official(e, "letter", ("subject",), ("from", "body"))
            if entry:
                self.add("library", gl, entry)

    def build_characters(self) -> None:
        links = self.lore.links or {}
        by_char = collections.defaultdict(list)
        for d, c in (links.get("dialogue_character") or {}).items():
            by_char[c].append(d)
        self.dialogues_by_quest = collections.defaultdict(list)
        for d, q in (links.get("dialogue_quest") or {}).items():
            self.dialogues_by_quest[q].append(d)
        chars_by_quest = links.get("quest_characters") or {}
        self.quests_by_char = collections.defaultdict(list)
        for q, cs in chars_by_quest.items():
            for c in cs:
                self.quests_by_char[c].append(q)
        dialogues = {e["id"]: e for e in self.lore.cats.get("dialogues", [])}
        attached = set()
        g = self.group("characters", "npcs", key="lore.group.npcs")
        chars = []
        for e in self.lore.cats.get("characters", []):
            entry = self.official(e, "character", ("name", "title"), None, "title")
            if not entry:
                continue
            items = []
            for d in sorted(by_char.get(e["id"], []), key=lambda x: min(f["loc"] for f in dialogues[x]["fields"].values()) if x in dialogues else 0):
                if d in dialogues:
                    item = self.dialogue_item(dialogues[d])
                    if item:
                        items.append(item)
                        attached.add(d)
            if items:
                entry["items"] = items
            if self.quests_by_char.get(e["id"]):
                entry.setdefault("links", {})["quests"] = self.quests_by_char[e["id"]]
            z = zone_of(e.get("path"))
            if z and f"z-{z}" in self.ref_of:
                entry.setdefault("links", {})["region"] = [f"z-{z}"]
            chars.append(entry)
        # un même PNJ existe souvent en plusieurs ressources (une par quête ou par phase) : on les
        # fusionne quand nom et titre sont identiques dans les trois langues
        merged: dict[tuple, dict] = {}
        self.char_alias: dict[str, str] = {}
        for entry in chars:
            key = (tuple(entry["title"].get(l) or "" for l in LANGS),
                   tuple((entry.get("subtitle") or {}).get(l) or "" for l in LANGS))
            main = merged.get(key)
            if main is None:
                merged[key] = entry
                continue
            self.char_alias[entry["id"]] = main["id"]
            if entry.get("items"):
                main.setdefault("items", []).extend(entry["items"])
            for k, ids in (entry.get("links") or {}).items():
                cur = main.setdefault("links", {}).setdefault(k, [])
                cur.extend(x for x in ids if x not in cur)
            if not main["fields"] and entry["fields"]:
                main["fields"] = entry["fields"]
        chars = sorted(merged.values(), key=lambda x: norm_text(resolve(x["title"], "en")[0]))
        for entry in chars:
            self.add("characters", g, entry)
        gf = self.group("characters", "factions", key="lore.group.factions")
        for e in self.lore.cats.get("factions", []):
            entry = self.official(e, "faction", ("name", "Name", "greatName"))
            if entry:
                self.add("characters", gf, entry)
        self.attached_dialogues = attached
        gd = self.group("characters", "dialogues", key="lore.group.dialogues")
        for d in self.lore.cats.get("dialogues", []):
            if d["id"] in attached:
                continue
            q = (links.get("dialogue_quest") or {}).get(d["id"])
            entry = self.official(d, "dialogue", ("name",), ("text",))
            if entry:
                if q:
                    entry["links"] = {"quests": [q]}
                self.add("characters", gd, entry)

    def dialogue_item(self, d: dict) -> dict | None:
        recs = self.fields(d, ("name", "text"))
        if not recs:
            return None
        head = next((r for r in recs if r["key"] == "name"), None)
        return {"id": d["id"], "heading": head, "fields": [r for r in recs if r is not head]}

    def build_secrets(self) -> None:
        g = self.group("secrets", "secrets", key="lore.group.secrets")
        self.secret_of_quest = collections.defaultdict(list)
        for e in self.lore.cats.get("secrets", []):
            entry = self.official(e, "secret", ("name",), ("question", "description", "status", "solved_title"))
            if not entry:
                continue
            items = []
            for n, c in enumerate(e.get("components", []), 1):
                fields = []
                for k in ("text", "not_ready"):
                    if k in c:
                        rec = self.field("secretStep" if k == "text" else "secretStepHint", c[k])
                        if rec:
                            fields.append(rec)
                q = c.get("quests") or {}
                quests = [x for x in [q.get("start"), *q.get("path", []), q.get("final")] if x]
                seen = []
                for x in quests:
                    if x not in seen:
                        seen.append(x)
                        self.secret_of_quest[x].append(e["id"])
                items.append({"id": f"{e['id']}-{n}", "step": n, "fields": fields, "links": {"quests": seen}})
            entry["items"] = items
            self.add("secrets", g, entry)

    def build_quests(self) -> None:
        dialogues = {e["id"]: e for e in self.lore.cats.get("dialogues", [])}
        for e in self.lore.cats.get("quests", []):
            entry = self.official(e, "quest", ("name",), QUEST_FIELDS)
            if not entry:
                continue
            links = {}
            if self.secret_of_quest.get(e["id"]):
                links["secrets"] = sorted(set(self.secret_of_quest[e["id"]]))
            qc = (self.lore.links or {}).get("quest_characters", {}).get(e["id"])
            if qc:
                links["characters"] = qc
            z = zone_of(e.get("path"))
            if z and f"z-{z}" in self.ref_of:
                links["region"] = [f"z-{z}"]
            items = [it for d in self.dialogues_by_quest.get(e["id"], []) if d in dialogues and d not in self.attached_dialogues
                     for it in [self.dialogue_item(dialogues[d])] if it]
            if items:
                entry["items"] = items
            if links:
                entry["links"] = links
            self.add("quests", self.zone_group("quests", z, "lore.group.otherQuests"), entry)

    def resolve_links(self) -> None:
        """Liens réciproques région → quêtes / PNJ ; liens vers des entrées absentes retirés."""
        back = collections.defaultdict(lambda: collections.defaultdict(list))
        for s in ("quests", "characters"):
            for e in self.entries[s]:
                for r in (e.get("links") or {}).get("region", []):
                    back[r][s].append(e["id"])
        for e in self.entries["atlas"]:
            if e["id"] in back:
                for s, ids in back[e["id"]].items():
                    e.setdefault("links", {})[s] = ids
        alias = getattr(self, "char_alias", {})
        for s in SECTIONS:
            for e in self.entries[s]:
                for container in [e, *e.get("items", [])]:
                    links = container.get("links")
                    if links:
                        for k in list(links):
                            seen = []
                            for x in (alias.get(x, x) for x in links[k]):
                                if x in self.ref_of and x not in seen:
                                    seen.append(x)
                            links[k] = seen
                            if not links[k]:
                                del links[k]

    # -- écriture ------------------------------------------------------------------------------
    def title_in(self, e: dict, lang: str) -> tuple[str, str]:
        return resolve(e["title"], lang)

    def flags(self, e: dict) -> int:
        f = FLAG_COMMUNITY if e.get("community") else 0
        recs = list(self.all_fields(e))
        if not e.get("community") and any(not (r["texts"].get("en") or "").strip() for r in recs):
            f |= FLAG_EN_MISSING
        if any(r.get("revised") for r in recs):
            f |= FLAG_REVISED
        return f

    @staticmethod
    def all_fields(e: dict):
        yield from e.get("fields", [])
        for it in e.get("items", []):
            if it.get("heading"):
                yield it["heading"]
            yield from it.get("fields", [])

    def text_rec(self, r: dict, lang: str) -> list:
        """`[clé, texte ou 0, drapeaux, extra?]` : 0 = absent dans cette langue (la page lit alors le
        même champ dans le bloc de la langue de repli)."""
        text = r["texts"].get(lang)
        text = text if text and text.strip() else 0
        flags = TEXT_REVISED if r.get("revised") and lang == "en" and text else 0
        out = [r["key"], text, flags]
        if r.get("heading") or r.get("markdown"):
            out.append({k: v for k, v in (("heading", r.get("heading")), ("md", r.get("markdown"))) if v})
        return out

    def link_list(self, ids: list[str], lang: str) -> list[list[str]]:
        out = []
        for x in ids:
            ref = self.ref_of.get(x)
            if ref:
                out.append([ref, self.title_in(self.entry_by_id[x], lang)[0]])
        return out

    def body(self, e: dict, lang: str) -> dict:
        b: dict = {"t": [self.text_rec(r, lang) for r in e.get("fields", [])]}
        if e.get("subtitle"):
            b["s"] = resolve(e["subtitle"], lang)[0]
        if e.get("facts"):
            b["f"] = e["facts"]
        if e.get("items"):
            items = []
            for it in e["items"]:
                o: dict = {"t": [self.text_rec(r, lang) for r in it.get("fields", [])]}
                if it.get("heading"):
                    o["h"] = self.text_rec(it["heading"], lang)
                if it.get("step"):
                    o["n"] = it["step"]
                if it.get("links"):
                    o["l"] = {k: self.link_list(v, lang) for k, v in it["links"].items()}
                items.append(o)
            b["i"] = items
        if e.get("links"):
            b["l"] = {k: self.link_list(v, lang) for k, v in e["links"].items()}
        meta = {k: v for k, v in (e.get("meta") or {}).items() if v not in (None, "")}
        if meta:
            b["m"] = meta
        return b

    def write(self, out: Path) -> dict:
        # fichiers périmés retirés, dossiers gardés (un serveur de dev qui surveille `public/` suit)
        if out.exists():
            for p in out.rglob("*"):
                if p.is_file():
                    p.unlink()
        out.mkdir(parents=True, exist_ok=True)
        self.entry_by_id = {e["id"]: e for s in SECTIONS for e in self.entries[s]}
        sizes = collections.Counter()

        def dump(rel: str, data) -> int:
            p = out / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            p.write_text(text, encoding="utf-8")
            sizes[rel.split("/")[0]] += len(text.encode("utf-8"))
            return len(text.encode("utf-8"))

        global_ids: list[tuple[str, dict]] = []
        meta_sections = {}
        for s in SECTIONS:
            # groupes « autres » en fin de liste, puis entrées regroupées (tri stable)
            gs = self.groups[s]
            rank = sorted(range(len(gs)), key=lambda i: (gs[i]["id"] == "other", i))
            remap = {old: new for new, old in enumerate(rank)}
            self.groups[s] = [gs[i] for i in rank]
            for e in self.entries[s]:
                e["group"] = remap[e["group"]]
            es = self.entries[s] = sorted(self.entries[s], key=lambda e: e["group"])
            # blocs : l'ordre de la liste, coupé à ~CHUNK_BYTES d'anglais
            chunk, acc = 0, 0
            for e in es:
                n = len(json.dumps(self.body(e, "en"), ensure_ascii=False))
                if acc and acc + n > CHUNK_BYTES:
                    chunk, acc = chunk + 1, 0
                e["chunk"] = chunk
                acc += n
            for lang in LANGS:
                by_chunk = collections.defaultdict(dict)
                for e in es:
                    by_chunk[e["chunk"]][e["id"]] = self.body(e, lang)
                for c, data in by_chunk.items():
                    dump(f"text/{lang}/{s}-{c}.json", data)
            global_ids.extend((s, e) for e in es)
            groups = []
            for i, g in enumerate(self.groups[s]):
                g = dict(g)
                g["count"] = sum(1 for e in es if e["group"] == i)
                groups.append(g)
            for lang in LANGS:
                rows = [[e["id"], e["group"], e["chunk"], self.flags(e), self.title_in(e, lang)[0],
                         resolve(e["subtitle"], lang)[0] if e.get("subtitle") else ""] for e in es]
                lgroups = [{k: v for k, v in g.items() if k != "label"} | ({"label": g["label"][lang]} if "label" in g else {})
                           for g in groups]
                dump(f"list/{lang}/{s}.json", {"groups": lgroups, "rows": rows})
            meta_sections[s] = {"count": len(es), "chunks": (es[-1]["chunk"] + 1) if es else 0,
                                "groups": [{"id": g["id"], "count": g["count"]} for g in groups]}
        # recherche et répertoire : ids globaux numérotés par priorité de type (à score égal, la
        # page classe par id croissant) : entités nommées d'abord, répliques et scènes en dernier
        order = {s: i for i, s in enumerate(SECTIONS)}
        global_ids.sort(key=lambda se: (SEARCH_PRIORITY.get(se[1]["kind"], 5), order[se[0]]))
        for lang in LANGS:
            postings: dict[str, list[int]] = collections.defaultdict(list)
            title_post: dict[str, list[int]] = collections.defaultdict(list)
            for gid, (s, e) in enumerate(global_ids):
                title = self.title_in(e, lang)[0]
                words = set(tokens(title))
                for w in words:
                    title_post[w].append(gid)
                body = self.body(e, lang)
                texts = [t[1] for t in body["t"] if t[1]] + [t[1] for it in body.get("i", [])
                                                             for t in [*([it["h"]] if "h" in it else []), *it["t"]] if t[1]]
                if body.get("s"):
                    texts.append(body["s"])
                for w in words | set(tokens(" ".join(texts))):
                    postings[w].append(gid)
            shards = collections.defaultdict(dict)
            for w, ids in postings.items():
                shards[shard_key(w)][w] = encode_postings(ids) + ("|" + encode_postings(title_post[w]) if w in title_post else "")
            for k, d in shards.items():
                dump(f"search/{lang}/{k}.json", d)
            for b in range(0, len(global_ids), DIR_BLOCK):
                dump(f"dir/{lang}/{b // DIR_BLOCK}.json",
                     [[s, e["id"], self.title_in(e, lang)[0], self.flags(e)] for s, e in global_ids[b:b + DIR_BLOCK]])
            dump(f"names/{lang}.json", self.names(lang))
        meta = {"sections": meta_sections, "credit": self.credit, "translated_by": TRANSLATED_BY,
                "entries": len(global_ids), "dir_block": DIR_BLOCK, "token_min": TOKEN_MIN,
                "stopwords": sorted(STOPWORDS),
                "sources": {"client": "AllodsRU 17.0 (texts, official English), FR client 16.0 (French)",
                            "community": "Makar Terentiev (DarkyAndSparky), atlas-ao, used with permission"}}
        dump("meta.json", meta)
        return {"entries": len(global_ids), "bytes": dict(sizes), "total": sum(sizes.values()),
                "sections": {s: v["count"] for s, v in meta_sections.items()}}

    def names(self, lang: str) -> dict[str, str]:
        """Noms propres uniques → entrée : PNJ, lieux, régions, allods, secrets, factions."""
        cands: dict[str, list[dict]] = collections.defaultdict(list)
        for s in ("characters", "atlas", "secrets"):
            for e in self.entries[s]:
                if e["kind"] not in ("character", "place", "region", "allod", "secret", "faction"):
                    continue
                name, src = self.title_in(e, lang)
                if src:
                    continue
                name = name.strip()
                if len(name) < 4 or not name[:1].isupper() or norm_text(name) in STOPWORDS or len(name.split()) > 5:
                    continue
                cands[name].append(e)
        out = {}
        for name in sorted(cands):
            es = cands[name]
            if len(es) == 1:
                out[name] = self.ref_of[es[0]["id"]]
            elif all(e["kind"] in ("allod", "region", "place") for e in es):
                # même nom dans l'atlas : l'allod, sinon la région, sinon le lieu
                best = min(es, key=lambda e: ("allod", "region", "place").index(e["kind"]))
                if sum(1 for e in es if e["kind"] == best["kind"]) == 1:
                    out[name] = self.ref_of[best["id"]]
            elif all(e["kind"] == "character" for e in es):
                # homonymes (titres différents) : le PNJ le plus présent (dialogues, quêtes)
                best = max(es, key=lambda e: (len(e.get("items", [])), sum(len(v) for v in (e.get("links") or {}).values())))
                if len(best.get("items", [])) >= 3:
                    out[name] = self.ref_of[best["id"]]
        return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lore", type=Path, default=DEFAULT_LORE)
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--corpus", type=Path, default=None, help="corpus communautaire (défaut : manifeste ou $ALLODS_LORE_CORPUS)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    b = Builder(Lore(args.lore), args.src, args.corpus or default_corpus())
    b.build()
    report = b.write(args.out)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
