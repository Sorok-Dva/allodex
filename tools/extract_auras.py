"""Auras de la garde-robe (« Дары » → « Ауры » ; FR « Cadeaux » → « Auras ») et apparences à aura.

Chaîne établie sur le client 17.0 (septembre 2026), par pointeurs du `pack.bin`, sans nom deviné :

1. la garde-robe est un arbre de `LifestyleCategory` → `LifestyleCollection` (nom en `+0x80`) ;
   la collection « Ауры » (FR « Auras ») de la catégorie « Дары » (FR « Cadeaux ») est un vecteur
   (`+0x88`) d'entrées de 56 octets dont `+0x08` pointe un **`Spell`** : l'aptitude qui pose l'aura,
   celle que montre l'infobulle de la garde-robe (nom `+0x108`, description `+0xE8`, icône
   `UISingleTexture` `+0x150`, conditions d'emploi `+0x168` : `PredicateUnlock` → `UnlockResource`,
   ou clé de contenu `PredicateHasContentKey` pour les auras Premium) ;
2. le sort pose un **buff** ; le lien sort → buff est côté serveur (absent du client), mais le buff
   porte **la même icône** (`+0xD8`) — et, pour 41 auras sur 55, le même nom (`+0x68`). Le buff de
   l'aura est celui qui a l'icône du sort et son nom, sinon celui des buffs de cette icône qui a un
   script visuel (`+0x148` → `BuffVisScripts`, arbre de `VisAction` en `+0x48`) ; dix auras
   (Premium, auras de guilde de la Vallée d'ambroisie) n'ont aucun buff scripté : **aucun effet
   visuel dans le client** (signalé tel quel, rien n'est inventé) ;
3. le script pose les effets : `CreatureEffectsAction` (gabarits `VisObjectTemplate` accrochés à un
   locator, `Global`/`Slot_Global` = aux pieds), interprété par `tools/fatality_script.py`, exporté
   par `tools/allods_fx.FxBuild` comme les fatalités ;
4. la capacité débloquée (`UnlockResource` de même icône, `+0x70` nom, `+0x48` description) dit
   **comment l'obtenir** : c'est le texte « Sources » de la garde-robe (« s'achète avec des devises …
   auprès de Gerasim Rivin dans la capitale de faction ») ; à défaut, la phrase de source de
   l'objet (`ItemResource` de même icône, `+0x150`), sinon « Source inconnue » ;
5. **apparences à aura** : objets du client (`ItemResource`) qui donnent à la fois un objet d'aura
   et une apparence (peau d'exosquelette ou de monture `MountSkin`, pièces de costume) : leur aura
   est celle du lot (« Цветовая схема мистической брони «Пожиратель» » → deux auras) ;
6. **couleurs de robe de carapace à aura au sol** (`exo_skin_auras`, 31 peaux) : l'aura n'est ni
   dans la peau ni dans son modèle de vitrine, mais dans les **objets visuels que la carapace fait
   porter à l'avatar** — branche du script des carapaces gardée par un `PredicateVisualMountAction`
   sur le `VisualMount` de la peau → `CreatureChangeVisItemsAction` → `VisualItem` → pièce
   accrochée à `Slot_Global` (`MEV16Hunter_Dec` pour Néphalion, `MEV13_Com_Dec` pour Destructeur
   des mondes, `MEV15Base_Dec` pour Div ; aucune pour « Жнец », la couleur de base du Faucheur) ;
7. **auras sans buff scripté de même icône** : le visuel est le buff sans nom créé juste après le
   sort (`link_visual_buffs`) — empreintes des auras premium (`CreatureVisObjectComponentsAction`
   pendant `run`/`walk`, `EmitterVisObjComponent`), décors de la Vallée d'ambroisie.

Textes : russe et anglais du client 17.0 (`pack.rus.loc`, `pack.eng_eu.loc`, langue vérifiée),
français du client FR 16.0, même objet par son `resourceId` (tables 0x30/0x38 de l'entête). Les
références en ligne sont résolues : `<t href="…"/>` (indice de texte, petit-boutiste) et
`<o id="…"/>` (nom de l'objet de ce `resourceId`).

Version d'apparition : premier client archivé qui contient l'aura — par son `resourceId` dans les
clients 64 bits (15.0 à 17.0), par le nom de fichier de son icône (`<nom>.(UITexture)` parmi les
chemins du `pack.bin`) dans les clients 32 bits (3.0 à 11.0), les seuls repères communs.

    python3 tools/extract_auras.py                  # tout (≈ 10 min, 9 clients)
    python3 tools/extract_auras.py --no-versions    # sans relire les anciens clients
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.fatality_items import Graph, resource_keys  # noqa: E402
from tools.packbin import LocTable, PackBin, inflate  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE / "auras_manifest.json"
DEFAULT_OUT = HERE.parent / "public" / "game" / "auras"

# Champs relevés sur 17.0 et vérifiés sur 16.0 FR (mêmes décalages, format v2).
COLLECTION_NAME = 0x80
COLLECTION_ENTRIES = 0x88
COLLECTION_STRIDE = 56
ENTRY_SPELL = 0x08
SPELL_DESC, SPELL_NAME, SPELL_ICON = 0xE8, 0x108, 0x150
BUFF_DESC, BUFF_NAME, BUFF_ICON, BUFF_SCRIPT = 0x48, 0x68, 0xD8, 0x148
VIS_SCRIPT_ACTION = 0x48
UNLOCK_DESC, UNLOCK_ICON, UNLOCK_NAME = 0x48, 0x50, 0x70
ITEM_DESC, ITEM_ICON, ITEM_NAME = 0x150, 0x1A0, 0x228
SKIN_DESC, SKIN_NAME, SKIN_SOURCE, SKIN_ICON, SKIN_MOUNT = 0x40, 0x60, 0x80, 0x90, 0xE8
MOUNT_NAME = 0xE8
VISUAL_MOUNT_MOB = 0x88
VISUAL_MOB_TEMPLATE = 0x28
TEMPLATE_VISOBJECT = 0x90
NAME_FIELDS = {"ItemResource": ITEM_NAME, "BuffResource": BUFF_NAME, "UnlockResource": UNLOCK_NAME,
               "Spell": SPELL_NAME, "MountSkin": SKIN_NAME, "MountResource": MOUNT_NAME,
               "AlternativeCurrency": 0xA0}
# Collection de la garde-robe, par son nom dans la langue du client de référence.
AURA_COLLECTIONS = {"Ауры", "Auras"}
AURA_ATLAS_WIDTH = 2048
# Part minimale de textes en cyrillique pour qu'un `.loc` soit du russe (même seuil que
# `tools/extract_cinematics.RUSSIAN_SHARE` : 95 % pour le russe du 17.0, 8 % pour son anglais).
RUSSIAN_SHARE = 0.5
CYRILLIC = re.compile(r"[А-Яа-яЁё]")


# --- textes -------------------------------------------------------------------------------------

def cyrillic_share(loc: LocTable, samples: int = 4000) -> float:
    step = max(1, loc.count // samples)
    filled = [s for s in (loc.get(i) for i in range(1, loc.count, step)) if s and s.strip()]
    return sum(1 for s in filled if CYRILLIC.search(s)) / max(1, len(filled))


def check_language(loc: LocTable, lang: str, name: str) -> None:
    """Le russe doit être en cyrillique, les autres langues non (mise à jour du client RU des 23 et
    24/09/2026 : un `pack.rus.loc` peut sortir dans une autre langue)."""
    share = cyrillic_share(loc)
    if (lang == "ru") != (share >= RUSSIAN_SHARE):
        raise ValueError(f"{name} ({lang}) : {share:.0%} de textes en cyrillique, langue inattendue")


def href_index(hexa: str) -> int:
    """Indice de texte d'un `<t href="…"/>` : entier petit-boutiste écrit en hexadécimal."""
    return int.from_bytes(bytes.fromhex(hexa), "little")


REF = re.compile(r"""<t\s+href=["']([0-9a-fA-F]+)["']\s*/>|<o\s+id=["'](\d+)["']\s*/>""")


def resolve_refs(text: str, text_of, object_name, depth: int = 0) -> str:
    """Remplace les références en ligne : `<t href>` par le texte, `<o id>` par le nom de l'objet."""
    def sub(m: re.Match) -> str:
        if depth > 4:
            return ""
        if m.group(1):
            inner = text_of(href_index(m.group(1))) or ""
        else:
            inner = object_name(int(m.group(2))) or ""
        return resolve_refs(inner, text_of, object_name, depth + 1)
    return REF.sub(sub, text or "")


def plain(html: str | None) -> str:
    """Texte d'infobulle sans balises : `<br/>` → saut de ligne, marques de sens et espaces
    doubles retirés."""
    if not html:
        return ""
    s = re.sub(r"<br\s*/?>", "\n", html)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("‎", "").replace("\r", "")
    s = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in s.split("\n"))
    return re.sub(r"\n{2,}", "\n", s).strip()


def is_official(s: str | None, lang: str) -> bool:
    """Texte présent ; un texte anglais ou français resté en cyrillique n'est pas officiel."""
    return bool(s and s.strip()) and not (lang in ("en", "fr") and CYRILLIC.search(s))


# --- obtention ----------------------------------------------------------------------------------

SOURCES = re.compile(r"(?i)^(sources?|источник[а-я ]*получения|источники?)\s*[:：]\s*")
# Descriptions de capacité qui ne font que renvoyer à l'objet (« Accordé par l'Aura de Marquis. »).
GENERIC_UNLOCK = re.compile(r"(?i)^(возможность (получена|доступна) благодаря предмету|accordé par|granted by|"
                            r"conféré par l'|you have unlocked)")
PURCHASE_WORDS = re.compile(r"(?i)(купить|приобрести|покупк|за валюту|s'achète|acheter|purchas|bought|buy)")
OBTAIN_WORDS = re.compile(r"(?i)(получен[аоы]?\b|можно получить|приобре|купить|наград|obten|achète|acheter|récompense|reçue?\b|"
                          r"offert|obtain|purchas|reward|receiv|award|premium|премиум)")


def source_lines(text: str) -> list[str]:
    """Lignes « Sources » d'une description (après l'en-tête « Sources : »), sans puces."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for i, line in enumerate(lines):
        if SOURCES.match(line):
            rest = [SOURCES.sub("", line)] + lines[i + 1:]
            return [re.sub(r"^[-–•]\s*", "", l).strip() for l in rest if l.strip()]
    return []


def is_generic_unlock(text: str, names: tuple[str, ...] = ()) -> bool:
    """Description de capacité qui ne dit rien de l'obtention : simple renvoi à l'objet
    (« Accordé par l'Aura de Marquis. ») ou nom de l'aura répété (« Rune du Seigneur des abysses. »)."""
    bare = text.strip().rstrip(".!").strip()
    if any(bare == n.strip().rstrip(".!").strip() for n in names if n):
        return True
    return bool(GENERIC_UNLOCK.match(text)) and not PURCHASE_WORDS.search(text)


def obtain_text(unlock_desc: str | None, item_descs: list[str], names: tuple[str, ...] = ()) -> tuple[str | None, str | None]:
    """Comment l'obtenir, d'après les textes du client : (texte, origine). Dans l'ordre : les
    lignes « Sources » de la capacité ou de l'objet, la description de la capacité (texte de la
    garde-robe) si elle n'est pas un simple renvoi à l'objet ou le nom répété, la phrase de l'objet
    qui parle d'obtention. `None` : rien dans le client."""
    unlock = plain(unlock_desc)
    items = [plain(d) for d in item_descs if d]
    for text, origin in [(unlock, "unlock")] + [(d, "item") for d in items]:
        lines = source_lines(text)
        if lines:
            return " ; ".join(lines), origin
    if unlock and not is_generic_unlock(unlock, names):
        return unlock.replace("\n", " "), "unlock"
    for d in items:
        hits = [l for l in d.split("\n") if OBTAIN_WORDS.search(l) and not l.rstrip().endswith(":")]
        if hits:
            return " ".join(hits), "item"
    return None, None


# --- client -------------------------------------------------------------------------------------

class Client:
    """Base d'un client (`pack.bin`), ses textes par langue, son graphe de pointeurs."""

    def __init__(self, spec: dict, texts: bool = True, graph: bool = True) -> None:
        from tools.allods_packdb import packs_path
        from tools.extract_talents import cached_pack
        self.spec = spec
        packs = packs_path(Path(spec["root"]) / "data" / "Packs")
        raw = cached_pack(packs / spec["pak"])
        if raw is None:
            raise FileNotFoundError(f"{packs / spec['pak']} : Bin/pack.bin absent")
        self.packs = packs
        self.pb = PackBin(raw)
        self.graph = Graph(self.pb) if graph else None
        self.locs: dict[str, LocTable] = {}
        for lang, (pak, member) in ((spec.get("texts") or {}).items() if texts else ()):
            loc = LocTable(inflate(zipfile.ZipFile(packs / pak).read(member)))
            check_language(loc, lang, member)
            self.locs[lang] = loc
        self.keys = resource_keys(self.pb)
        self.by_key = {v: k for k, v in self.keys.items()}

    def type_at(self, off: int | None) -> str | None:
        return self.pb.type_at(off) if off is not None else None

    def text_ref(self, obj: int, off: int, lang: str) -> str | None:
        loc = self.locs.get(lang)
        if loc is None:
            return None
        v = self.pb.u32(obj + off)
        if not (0 < v < loc.count and self.pb.u32(obj + off + 4) == 0):
            return None
        return loc.get(v)

    def text(self, obj: int, off: int, lang: str) -> str | None:
        """Texte du champ `off`, références résolues (sans balises retirées)."""
        raw = self.text_ref(obj, off, lang)
        if raw is None:
            return None
        loc = self.locs[lang]
        return resolve_refs(raw, loc.get, lambda rid: self.object_name(rid, lang))

    def object_name(self, rid: int, lang: str) -> str | None:
        off = self.by_key.get(rid)
        kind = self.type_at(off)
        if off is None or kind not in NAME_FIELDS:
            return None
        raw = self.text_ref(off, NAME_FIELDS[kind], lang)
        return plain(resolve_refs(raw or "", self.locs[lang].get, lambda r: None)) or None

    def pointers(self, obj: int, kind: str | None = None, nested: bool = True) -> list[int]:
        g = self.graph
        end = g.root_end(obj) if nested else g.object_end(obj)
        out = g.pointers_from(obj, end)
        return [p for p in out if kind is None or self.pb.type_at(p) == kind]

    def referrers(self, obj: int, kind: str | None = None) -> list[int]:
        """Ressources (racines) qui pointent `obj`, sans doublon, dans l'ordre."""
        g = self.graph
        out: list[int] = []
        for loc in g.referrers(obj, g.object_end(obj)):
            root = g.root_of(loc)
            if root is not None and root != obj and root not in out and (kind is None or self.pb.type_at(root) == kind):
                out.append(root)
        return out


def aura_spells(client: Client) -> list[int]:
    """Sorts de la collection « Ауры » de la garde-robe, dans l'ordre de la garde-robe."""
    pb = client.pb
    lang = next(iter(client.locs), None)
    out: list[int] = []
    for coll in pb.objects_of("LifestyleCollection"):
        name = client.text_ref(coll, COLLECTION_NAME, lang) if lang else None
        if name not in AURA_COLLECTIONS:
            continue
        vec, size = pb.vector(coll + COLLECTION_ENTRIES)
        for k in range((size or 0) // COLLECTION_STRIDE):
            spell = pb.ptr(vec + COLLECTION_STRIDE * k + ENTRY_SPELL)
            if spell is not None and pb.type_at(spell) == "Spell" and spell not in out:
                out.append(spell)
    return out


def pick_buff(spell_name: str | None, buffs: list[tuple[int, str | None, bool]]) -> int | None:
    """Buff de l'aura parmi ceux qui ont l'icône du sort `(décalage, nom, scripté)` : celui du même
    nom (scripté de préférence) — même sans script : l'icône d'« Аура Покровителя » sert aussi à
    trois buffs « Уро-Борос слышит », étrangers à l'aura —, sinon le premier scripté, sinon le
    premier."""
    same = [b for b in buffs if spell_name and b[1] == spell_name]
    if same:
        return next((b for b in same if b[2]), same[0])[0]
    scripted = [b for b in buffs if b[2]]
    if scripted:
        return scripted[0][0]
    return buffs[0][0] if buffs else None


@dataclass
class AuraRecord:
    spell: int
    rid: int | None
    icon: int | None
    buff: int | None = None
    script: int | None = None
    unlocks: list[int] = field(default_factory=list)
    items: list[int] = field(default_factory=list)
    containers: list[int] = field(default_factory=list)
    content_key: bool = False
    buff_link: str | None = None       # "icon" (même icône) ou "rid" (buff visuel voisin, sans nom)
    visual_buff: int | None = None


def link_aura(client: Client, spell: int) -> AuraRecord:
    """Buff, capacité, objets et lots d'une aura (voir la docstring du module)."""
    pb = client.pb
    icon = pb.ptr(spell + SPELL_ICON)
    rec = AuraRecord(spell, client.keys.get(spell), icon)
    lang = next(iter(client.locs), "ru")
    name = client.text_ref(spell, SPELL_NAME, lang)
    for p in client.pointers(spell):
        kind = pb.type_at(p)
        if kind == "UnlockResource" and p not in rec.unlocks:
            rec.unlocks.append(p)
        elif kind == "ContentKey":
            rec.content_key = True
    if icon is not None:
        buffs = []
        for b in client.referrers(icon, "BuffResource"):
            script = pb.ptr(b + BUFF_SCRIPT)
            action = pb.ptr(script + VIS_SCRIPT_ACTION) if script is not None else None
            buffs.append((b, client.text_ref(b, BUFF_NAME, lang), action is not None))
        rec.buff = pick_buff(name, buffs)
        if rec.buff is not None:
            script = pb.ptr(rec.buff + BUFF_SCRIPT)
            rec.script = pb.ptr(script + VIS_SCRIPT_ACTION) if script is not None else None
        for u in client.referrers(icon, "UnlockResource"):
            if u not in rec.unlocks:
                rec.unlocks.append(u)
        for it in client.referrers(icon, "ItemResource"):
            rec.items.append(it)
    for u in rec.unlocks:
        for it in client.referrers(u, "ItemResource"):
            if it not in rec.items:
                rec.items.append(it)
    # Objets qui contiennent un objet de l'aura (coffres, lots d'apparence).
    for it in rec.items:
        for cont in client.referrers(it, "ItemResource"):
            if cont not in rec.items and cont not in rec.containers:
                rec.containers.append(cont)
    return rec


# Buff visuel voisin : premier `BuffResource` **sans nom** à script visuel qui suit le sort de
# l'aura dans l'ordre des `resourceId`, avant la ressource d'une autre aura (sort, objet, capacité).
RID_WINDOW = 24


def rid_visual_buff(client: Client, spell_rid: int | None, stops: set[int]) -> tuple[int | None, int | None]:
    """(buff, action) du buff visuel créé avec le sort (voir `link_visual_buffs`), ou (None, None)."""
    if spell_rid is None:
        return None, None
    pb = client.pb
    lang = next(iter(client.locs), "ru")
    for rid in range(spell_rid + 1, spell_rid + RID_WINDOW + 1):
        if rid in stops:
            break
        off = client.by_key.get(rid)
        if off is None or pb.type_at(off) != "BuffResource" or client.text_ref(off, BUFF_NAME, lang):
            continue
        script = pb.ptr(off + BUFF_SCRIPT)
        action = pb.ptr(script + VIS_SCRIPT_ACTION) if script is not None else None
        if action is not None:
            return off, action
    return None, None


def link_visual_buffs(client: Client, records: list[AuraRecord]) -> None:
    """Auras dont le buff de même icône n'a pas de script : le visuel est un buff **sans nom ni
    icône**, créé juste après le sort (resourceId suivant). Établi sur le 17.0 :

    * Aura de Saint Patron / Fondateur / Magnat (sorts 740017009, …016, …023) → buffs 740017010,
      …017, …024 : `CreatureVisObjectComponentsAction` (empreintes `PremiumTrace_Step_01All` /
      `_02All` pendant `run` et `walk`) ; l'arbre serveur 7.0 nomme ces mêmes scripts
      `Items/VisualItems/Pet/PremiumTrace01.(BuffVisScripts).xdb` (…02, …03), du nom de l'icône des
      auras (`PremiumTrace01`…), à l'identique champ pour champ ;
    * six auras de la Vallée d'ambroisie (740165958 → 740165975 `Aura_AmbrosiaWar_13_Gr_01`, …) :
      rangs 1-2-3, vert pour la forêt, jaune pour le progrès, dans l'ordre des sorts.

    Le lien sort → buff est côté serveur : ce voisinage est le seul repère du client (signalé
    `buffLink: "rid"`)."""
    stops = set()
    for rec in records:
        for o in [rec.spell] + rec.unlocks + rec.items:
            k = client.keys.get(o)
            if k is not None:
                stops.add(k)
    for rec in records:
        if rec.script is not None:
            rec.buff_link = "icon"
            continue
        own = {client.keys.get(o) for o in [rec.spell] + rec.unlocks + rec.items}
        buff, action = rid_visual_buff(client, rec.rid, stops - own)
        if action is not None:
            rec.script = action
            rec.buff_link = "rid"
            rec.visual_buff = buff


def texts_of(latest: Client, fr: Client | None, obj: int, off: int, kind: str = "text") -> dict[str, str]:
    """Texte d'un champ en russe et anglais (dernier client) et en français (client FR, même
    `resourceId`) ; une langue sans texte officiel est absente."""
    out: dict[str, str] = {}
    for lang in ("ru", "en"):
        s = latest.text(obj, off, lang)
        if is_official(s, lang):
            out[lang] = s
    if fr is not None:
        other = fr.by_key.get(latest.keys.get(obj)) if latest.keys.get(obj) is not None else None
        if other is not None:
            s = fr.text(other, off, "fr")
            if is_official(s, "fr"):
                out["fr"] = s
    return out


def plain_texts(texts: dict[str, str]) -> dict[str, str]:
    return {k: plain(v) for k, v in texts.items() if plain(v)}


# --- export --------------------------------------------------------------------------------------

def export_icon(client: Client, obj: int, out_dir: Path) -> str | None:
    """Icône (première `UISingleTexture` pointée → `UITexture`), recadrée, en WebP ; nom = celui du
    fichier `(UITexture).bin` du client (même lecture que `tools/fatality_items.export_icon`)."""
    import io
    from tools.fatality_items import export_icon as png_icon
    from types import SimpleNamespace
    from PIL import Image
    tmp = out_dir / ".png"
    key = png_icon(SimpleNamespace(pb=client.pb, graph=client.graph, packs=client.packs), obj, tmp)
    if key is None:
        return None
    img = Image.open(tmp / f"{key}.png")
    img.load()
    (tmp / f"{key}.png").unlink()
    out_dir.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=92, method=6)
    (out_dir / f"{key}.webp").write_bytes(buf.getvalue())
    try:
        tmp.rmdir()
    except OSError:
        pass
    return key


def aura_id(names: dict[str, str], rid: int | None, taken: set[str]) -> str:
    """Identifiant d'URL : le `resourceId` du sort (stable d'un client à l'autre)."""
    base = f"a{rid}" if rid is not None else "a" + re.sub(r"[^a-z0-9]+", "-", (names.get("en") or "aura").lower()).strip("-")
    out, k = base, 2
    while out in taken:
        out, k = f"{base}-{k}", k + 1
    taken.add(out)
    return out


def aura_timeline(script: dict | None, names: dict[int, str], anim_names: dict[int, str]) -> dict:
    """Effets de l'aura : gabarits accrochés (locator, échelle, décalage) et posés, sans fin (le buff
    dure tant que l'aura est active). Le script est aplati par `tools/fatality_script.flatten`."""
    from tools.fatality_script import flatten
    tl = flatten(script, "", {}, anim_names)
    attached = []
    for a in tl.attached:
        if a["vot"] not in names:
            continue
        item = {"t": a["t"], "vot": names[a["vot"]], "locator": a.get("locator") or "Global", "scale": a.get("scale", 1.0)}
        if a.get("offset") and any(abs(v) > 1e-6 for v in a["offset"]):
            item["offset"] = [round(v, 4) for v in a["offset"]]
        if a.get("fadeIn"):
            item["fadeIn"] = a["fadeIn"]
        attached.append(item)
    spawns = []
    for s in tl.spawns:
        if s["vot"] in names:
            spawns.append({"t": s["t"], "vot": names[s["vot"]], "lifeTime": s.get("lifeTime"), "offset": s.get("offset"),
                           "scale": s.get("scale", 1.0)})
    out = {"attached": attached, "spawns": spawns}
    if tl.ignored:
        out["ignored"] = sorted(set(tl.ignored))
    return out


# `CreatureVisObjectComponentsAction` : composant ajouté au gabarit du porteur (+0x70), ici un
# `StateComponent` (montré pendant ses animations) qui porte un `AttachedVisObjectComponent`.
# Champs nommés par l'arbre serveur 7.0 (`PremiumTrace01.(BuffVisScripts).xdb` : `visObjComponents`,
# `StateComponent.animations`, `component.locatorName`/`offset`/`scale`/`visObject`).
VIS_COMPONENTS_ACTION_COMPONENT = 0x70


def state_components(db, script: dict | None, anim_names: dict[int, str]) -> list[dict]:
    """Composants d'état posés sur le porteur par le script (`CreatureVisObjectComponentsAction`) :
    `{visObject, locator, offset, scale, states}` — `states` : animations du porteur pendant
    lesquelles il est montré (`run`, `walk` pour les empreintes)."""
    from tools.allods_visdb import COMP_LOCATOR, COMP_OFFSET, COMP_SCALE, COMP_VISOBJECT, STATE_ANIMS, STATE_CHILD
    out: list[dict] = []

    def walk(node: dict | None, states: list[str] | None = None) -> None:
        if not node:
            return
        if node.get("type") == "CreatureVisObjectComponentsAction":
            comp = db.ptr(node["offset"] + VIS_COMPONENTS_ACTION_COMPONENT)
            shown: list[str] | None = None
            while comp is not None and db.vtype(comp) == "StateComponent":
                v = db.vec(comp + STATE_ANIMS)
                ids = [db.u32(v[0] + 4 * k) for k in range(v[1] // 4)] if v else []
                shown = [anim_names.get(i, str(i)) for i in ids]
                comp = db.ptr(comp + STATE_CHILD)
            if comp is not None and db.vtype(comp) == "AttachedVisObjectComponent" and db.ptr(comp + COMP_VISOBJECT) is not None:
                out.append({"visObject": db.ptr(comp + COMP_VISOBJECT), "locator": db.string(comp + COMP_LOCATOR) or "Global",
                            "offset": [round(float(x), 4) for x in db.floats(comp + COMP_OFFSET, 3)],
                            "scale": round(float(db.f32(comp + COMP_SCALE)), 4), "states": shown})
        for child in node.get("elements", []):
            walk(child)
    walk(script)
    return out


def first_version(presence: list[tuple[str, str | None, bool | None]]) -> dict | None:
    """`since` d'après la présence dans les clients archivés, dans l'ordre des versions :
    `[(version, client, présent)]` (`None` = client illisible). `previous` = dernier client lu sans
    elle ; une version sans `previous` lu juste avant est une fourchette."""
    previous = None
    for version, client, present in presence:
        if present is None:
            continue
        if present:
            out = {"version": version}
            if client:
                out["client"] = client
            if previous:
                out["previous"] = previous
            return out
        previous = version
    return None


def run(manifest: dict, out_dir: Path, versions: bool = True, fx: bool = True, sounds: bool = True,
        report: list[str] | None = None) -> dict:
    report = report if report is not None else []
    latest = Client(manifest["latest"])
    fr = Client(manifest["fr"]) if manifest.get("fr") else None
    icons = out_dir / "icons"
    spells = aura_spells(latest)
    print(f"{len(spells)} auras dans la garde-robe du {manifest['latest']['version']}")
    records = [link_aura(latest, sp) for sp in spells]
    link_visual_buffs(latest, records)
    taken: set[str] = set()
    auras: list[dict] = []
    for rec in records:
        name = plain_texts(texts_of(latest, fr, rec.spell, SPELL_NAME))
        entry: dict = {"id": aura_id(name, rec.rid, taken), "resourceId": rec.rid, "name": name,
                       "description": plain_texts(texts_of(latest, fr, rec.spell, SPELL_DESC)),
                       "icon": None}
        key = export_icon(latest, rec.spell, icons)
        if key:
            entry["icon"] = f"icons/{key}.webp"
            entry["iconKey"] = key
        if rec.buff is not None:
            entry["buff"] = {"resourceId": latest.keys.get(rec.buff),
                             "name": plain_texts(texts_of(latest, fr, rec.buff, BUFF_NAME))}
        obtain: dict[str, str] = {}
        origin: dict[str, str] = {}
        for lang in ("ru", "en", "fr"):
            client, obj_of = (fr, lambda o: fr.by_key.get(latest.keys.get(o))) if lang == "fr" else (latest, lambda o: o)
            if client is None:
                continue
            unlock_desc = None
            for u in rec.unlocks:
                o = obj_of(u)
                if o is not None:
                    unlock_desc = client.text(o, UNLOCK_DESC, lang)
                    if unlock_desc:
                        break
            item_descs = []
            for it in rec.items:
                o = obj_of(it)
                if o is not None:
                    d = client.text(o, ITEM_DESC, lang)
                    if d:
                        item_descs.append(d)
            text, where = obtain_text(unlock_desc, item_descs, (name.get(lang, ""), plain(entry.get("buff", {}).get("name", {}).get(lang, ""))))
            if text and is_official(text, lang):
                obtain[lang] = text
                origin[lang] = where
        entry["obtain"] = obtain
        if origin:
            entry["obtainFrom"] = origin.get("fr") or origin.get("en") or origin.get("ru")
        items = []
        for it in rec.items:
            names = plain_texts(texts_of(latest, fr, it, ITEM_NAME))
            if not names:
                continue
            same = next((m for m in items if m["name"].get("ru") == names.get("ru")), None)
            if same:
                same["resourceIds"].append(latest.keys.get(it))
                continue
            k = export_icon(latest, it, icons)
            items.append({"name": names, "icon": f"icons/{k}.webp" if k else None, "resourceIds": [latest.keys.get(it)]})
        if items:
            entry["items"] = items
        if rec.buff_link == "rid" and rec.visual_buff is not None:
            entry["visualBuff"] = {"resourceId": latest.keys.get(rec.visual_buff), "link": "rid"}
        if rec.content_key:
            entry["contentKey"] = True
        auras.append(entry)
    index = {"schema": 1, "client": manifest["latest"]["version"], "auras": auras}

    # Seules les couleurs de robe des carapaces : les lots (costumes, montures) qui « donnent » une aura
    # font doublon avec l'aura elle-même ou n'en posent aucune (retirés le 24/09/2026).
    bundles = exo_skin_auras(latest, fr, icons, report)
    index["appearances"] = bundles
    # Mémoire : les deux bases (≈ 1,2 Go) sont libérées avant d'ouvrir celle des effets.
    del latest, fr
    import gc
    gc.collect()

    if fx:
        atlas = export_fx(manifest, out_dir, records, auras, bundles, sounds, report)
        if atlas is not None:
            index["particleAtlas"] = atlas
    if fx:
        index["walks"] = export_walks(manifest, out_dir, report)
    if versions:
        apply_versions(manifest, records, auras, bundles, report)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "auras.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return index


def compress_models(files: list[Path], report: list[str]) -> None:
    import subprocess
    if not files:
        return
    try:
        subprocess.run(["node", str(HERE / "compress_glb.mjs"), *map(str, files)], check=True, cwd=HERE.parent)
    except (OSError, subprocess.CalledProcessError) as error:
        report.append(f"AVERTISSEMENT : compression des carapaces impossible — {error}")


def _closure(client: Client, start: int, stop: tuple[str, ...]) -> list[int]:
    pb, g = client.pb, client.graph
    seen: set[int] = set()
    todo, out = [start], []
    while todo:
        o = todo.pop()
        if o in seen:
            continue
        seen.add(o)
        out.append(o)
        if o != start and (client.keys.get(o) is not None or pb.type_at(o) in stop):
            continue
        todo.extend(g.pointers_from(o, g.object_end(o)))
    return out


def exo_skin_branches(client: Client) -> dict[int, list[int]]:
    """`VisualMount` → branches (`VisActionList`) du script des carapaces dont le `playWhile` est un
    `PredicateVisualMountAction` qui ne vise que cette monture (la branche la plus intérieure)."""
    import numpy as np
    pb, g = client.pb, client.graph
    found: dict[int, list[tuple[int, int]]] = {}
    for pred in pb.objects_of("PredicateVisualMountAction"):
        vec, size = pb.vector(pred + PREDICATE_MOUNTS)
        mounts = [pb.ptr(vec + 8 * k) for k in range(size // 8)] if vec is not None else []
        for loc in g.referrers(pred, pred + 8):
            owner = int(g.bounds[int(np.searchsorted(g.bounds, loc, "right")) - 1])
            if pb.type_at(owner) == "VisActionList" and loc - owner == LIST_PLAY_WHILE:
                for m in mounts:
                    if m is not None:
                        found.setdefault(m, []).append((owner, len(mounts)))
    out = {}
    for m, cands in found.items():
        least = min(n for _, n in cands)
        out[m] = [b for b, n in cands if n == least]
    return out


def exo_skin_auras(latest: Client, fr: Client | None, icons: Path, report: list[str]) -> list[dict]:
    """Couleurs de robe de carapace qui posent une aura au sol. Chaîne (17.0, pointeurs ; noms des
    champs par l'arbre 7.0) : `MountSkin +0xE8` → `VisualMount` ; le buff des carapaces (script
    commun, `CreatureRunVisActionResource`) a une branche par monture, gardée par un
    `PredicateVisualMountAction` (+0x48 → ce `VisualMount`) ; la branche change les objets visuels
    du porteur (`CreatureChangeVisItemsAction` → `VisualItem`, pièces par personnage,
    `VICSelectComponentByChar`) ; parmi ces pièces, celle accrochée à `Slot_Global` est l'aura au sol
    (`MEV16Hunter_Dec` pour Néphalion). Le modèle montré est la carapace de la fenêtre
    (`VisualMount +0x90`, `mountForStable`), sans son socle."""
    pb = latest.pb
    branches = exo_skin_branches(latest)
    out: list[dict] = []
    for skin in pb.objects_of("MountSkin"):
        vm = pb.ptr(skin + SKIN_VISUAL_MOUNT)
        items: list[int] = []
        for b in branches.get(vm, []):
            for o in _closure(latest, b, ("VisObjectTemplate", "VisualMount", "PredicateVisualMountAction", "VisualItem")):
                if pb.type_at(o) == "VisualItem" and o not in items:
                    items.append(o)
        ground: list[dict] = []
        for it in items:
            for o in _closure(latest, it, ("VisObjectTemplate", "VisualItem")):
                if pb.type_at(o) != "AttachedVisObjectComponent":
                    continue
                loc = pb.string(o + COMPONENT_LOCATOR) or ""
                vo = pb.ptr(o + COMPONENT_VISOBJECT)
                if vo is None or loc not in GROUND_LOCATORS or any(g["_vot"] == vo for g in ground):
                    continue
                ground.append({"_vot": vo, "locator": loc, "scale": round(float(pb.f32(o + COMPONENT_SCALE)), 4),
                               "offset": [round(float(pb.f32(o + COMPONENT_OFFSET + 4 * k)), 4) for k in range(3)]})
        if not ground:
            continue
        stable_mob = pb.ptr(vm + VISUAL_MOUNT_STABLE) if vm is not None else None
        tpl = pb.ptr(stable_mob + VISUAL_MOB_TEMPLATE) if stable_mob is not None else None
        stable = pb.ptr(tpl + TEMPLATE_VISOBJECT) if tpl is not None else None
        mounts = latest.referrers(skin, "MountResource")
        if not mounts:
            # La liste de peaux la plus courte est celle de la carapace (740050173 les liste toutes).
            lists = sorted(latest.referrers(skin, "SkinListResource"),
                           key=lambda sl: len(latest.pointers(sl, "MountSkin", nested=False)))
            for sl in lists:
                mounts += [m for m in latest.referrers(sl, "MountResource") if m not in mounts]
        rid = latest.keys.get(skin)
        k = export_icon(latest, skin, icons)
        name = plain_texts(texts_of(latest, fr, skin, SKIN_NAME))
        entry = {"id": f"s{rid}", "resourceId": rid, "kind": "exoskin", "name": name,
                 "description": plain_texts(texts_of(latest, fr, skin, SKIN_DESC)),
                 "obtain": plain_texts(texts_of(latest, fr, skin, SKIN_SOURCE)),
                 "icon": f"icons/{k}.webp" if k else None, "iconKey": k, "auras": [],
                 "skin": {"resourceId": rid, "name": name,
                          "mount": plain_texts(texts_of(latest, fr, mounts[0], MOUNT_NAME)) if mounts else {}},
                 "visualItems": [latest.keys.get(i) for i in items],
                 "_stable": stable, "_ground": ground}
        out.append(entry)
    print(f"{len(out)} couleurs de robe de carapace à aura au sol")
    return out


def export_fx(manifest: dict, out_dir: Path, records: list[AuraRecord], auras: list[dict], bundles: list[dict],
              sounds: bool, report: list[str]) -> dict | None:
    """Gabarits d'effet de chaque aura (`fx/<id>.glb`) et modèles des apparences
    (`models/<id>.glb`), particules et textures communes, sons."""
    from tools.allods_fx import FxBuild, ParticlePool, export_sounds
    from tools.allods_gltf import Exporter
    from tools.allods_packdb import open_catalog, open_pack, packs_path
    from tools.allods_visdb import animation_names, read_action
    from tools.chargen_scene import WebpTexturePool
    from tools.extract_fatalities import FX_TEXTURE_MAX, collect_vots
    from tools.extract_menu_scene import BinSource
    client = Path(manifest["latest"]["root"])
    db = open_pack(client)
    cat = open_catalog(db, client)
    packs = packs_path(client / "data" / "Packs")
    bins = BinSource([], [str(packs / p) for p in sorted(cat.names)])
    textures = WebpTexturePool(db, cat, bins, out_dir)
    particles = ParticlePool(db, cat, bins, out_dir)
    # Atlas de 2048 px de large : les auras rangent leurs textures entières (runes, cercles) à 256 px,
    # ce qui tient en 2048 × 4096 (limite des GPU mobiles) au lieu de 1024 × 8192.
    particles.width = AURA_ATLAS_WIDTH
    anim_names = animation_names(db)
    all_sounds: set[str] = set()
    builds: list[tuple[dict, FxBuild]] = []
    for rec, entry in zip(records, auras):
        if rec.script is None:
            entry["visual"] = False
            continue
        script = read_action(db, rec.script)
        build = FxBuild(Exporter(textures, FX_TEXTURE_MAX), db, cat, bins, particles=particles, report=report)
        roots: set[int] = set()
        collect_vots(script, roots)
        states = state_components(db, script, anim_names)
        roots |= {st["visObject"] for st in states}
        for off in sorted(roots):
            node = build.emit(off)
            if node is not None:
                build.roots.append(node)
        emit_seeded(build)
        if not build.roots:
            entry["visual"] = False
            report.append(f"AVERTISSEMENT : {entry['id']} — script sans gabarit exportable")
            continue
        glb = build.exporter.finish(build.roots)
        (out_dir / "fx").mkdir(parents=True, exist_ok=True)
        (out_dir / "fx" / f"{entry['id']}.glb").write_bytes(glb)
        entry["visual"] = True
        entry["fx"] = f"fx/{entry['id']}.glb"
        entry["objects"] = build.meta
        entry["timeline"] = aura_timeline(script, build.names, anim_names)
        if states:
            entry["timeline"]["stateAttached"] = [
                {"vot": build.names[st["visObject"]], "locator": st["locator"], "scale": st["scale"], "states": st["states"],
                 **({"offset": st["offset"]} if any(abs(v) > 1e-6 for v in st["offset"]) else {})}
                for st in states if st["visObject"] in build.names]
        report.extend(f"AVERTISSEMENT : {entry['id']} — {n}" for n in build.exporter.notes)
        all_sounds |= build.sounds
        builds.append((entry, build))
        print(f"{entry['id']:>12}  fx {len(glb) / 1024:.0f} Kio  {len(build.meta)} gabarits  {entry['name'].get('ru')}")
    for bundle in bundles:
        if bundle.get("kind") != "exoskin":
            continue
        stable, ground = bundle.pop("_stable", None), bundle.pop("_ground", [])
        if stable is not None:
            build = FxBuild(Exporter(textures, EXO_TEXTURE_MAX), db, cat, bins, particles=particles, report=report,
                            skip=lambda n: bool(STALL_PARTS.match(n)))
            node = build.emit(stable)
            if node is not None:
                build.roots.append(node)
                glb = build.exporter.finish(build.roots)
                (out_dir / "models").mkdir(parents=True, exist_ok=True)
                (out_dir / "models" / f"{bundle['id']}.glb").write_bytes(glb)
                bundle["model"] = {"glb": f"models/{bundle['id']}.glb", "vot": build.names[stable], "objects": build.meta}
                print(f"{bundle['id']:>12}  modèle {len(glb) / 1024:.0f} Kio  {build.names[stable]}")
        build = FxBuild(Exporter(textures, FX_TEXTURE_MAX), db, cat, bins, particles=particles, report=report)
        attached = []
        for gr in ground:
            node = build.emit(gr["_vot"])
            if node is None:
                continue
            build.roots.append(node)
            item = {"t": 0.0, "vot": build.names[gr["_vot"]], "locator": gr["locator"], "scale": gr["scale"]}
            if any(abs(v) > 1e-6 for v in gr["offset"]):
                item["offset"] = gr["offset"]
            attached.append(item)
        if build.roots:
            glb = build.exporter.finish(build.roots)
            (out_dir / "fx").mkdir(parents=True, exist_ok=True)
            (out_dir / "fx" / f"{bundle['id']}.glb").write_bytes(glb)
            bundle.update({"visual": True, "fx": f"fx/{bundle['id']}.glb", "objects": build.meta,
                           "timeline": {"attached": attached, "spawns": []}})
            all_sounds |= build.sounds
            builds.append((bundle, build))
            print(f"{bundle['id']:>12}  aura {len(glb) / 1024:.0f} Kio  {', '.join(a['vot'] for a in attached)}")
    compress_models([out_dir / b["model"]["glb"] for b in bundles if b.get("kind") == "exoskin" and b.get("model")], report)
    for bundle in bundles:
        tpl = bundle.get("skin", {}).pop("_template", None)
        if tpl is None:
            continue
        build = FxBuild(Exporter(textures, 1024), db, cat, bins, particles=particles, report=report)
        node = build.emit(tpl)
        if node is None:
            continue
        build.roots.append(node)
        glb = build.exporter.finish(build.roots)
        (out_dir / "models").mkdir(parents=True, exist_ok=True)
        (out_dir / "models" / f"{bundle['id']}.glb").write_bytes(glb)
        bundle["model"] = {"glb": f"models/{bundle['id']}.glb", "vot": build.names[tpl], "objects": build.meta}
        all_sounds |= build.sounds
        print(f"{bundle['id']:>12}  modèle {len(glb) / 1024:.0f} Kio  {build.names[tpl]}")
    for bundle in bundles:
        bundle.get("skin", {}).pop("_template", None)
    sound_files: dict[str, str] = {}
    if sounds and all_sounds:
        from tools.extract_audio import DEFAULT_VGMSTREAM
        vgm = Path(os.environ.get("VGMSTREAM", DEFAULT_VGMSTREAM))
        if vgm.exists():
            sound_files = export_sounds(all_sounds, bins, out_dir, vgm, report)
        else:
            report.append(f"AVERTISSEMENT : vgmstream absent ({vgm}), sons non exportés")
    for entry, build in builds:
        for info in entry.get("objects", {}).values():
            if info.get("sound") in sound_files:
                info["sfx"] = sound_files[info["sound"]]
    atlas = particles.write_atlas(textures)
    if atlas is not None and atlas["file"].endswith(".png"):
        # Atlas des particules en WebP (décision du projet : textures en WebP ou JPEG).
        from PIL import Image
        png = out_dir / atlas["file"]
        webp = png.with_suffix(".webp")
        Image.open(png).save(webp, format="WEBP", quality=92, method=6, alpha_quality=100)
        png.unlink()
        atlas["file"] = atlas["file"][:-4] + ".webp"
    print(f"textures : {textures.bytes_written / 1024:.0f} Kio, particules : {particles.bytes_written / 1024:.0f} Kio")
    return atlas


def emit_seeded(build) -> None:
    """Gabarits semés (`EmitterVisObjComponent`, empreintes) : racines à part du `.glb`, posées dans
    le monde par le lecteur."""
    done: set[int] = set()
    while True:
        todo = [v for v in build.emitted if v not in done]
        if not todo:
            return
        for v in todo:
            done.add(v)
            node = build.emit(v)
            if node is not None:
                build.roots.append(node)


# --- marche de l'avatar ------------------------------------------------------------------------------

CHARGEN_INDEX = HERE.parent / "public" / "game" / "character" / "chargen.json"
# Animations de déplacement du client : `<dossier>/Animations/<gabarit>.Walk|Run.(SkeletalAnimation).bin`
# (mêmes noms que l'énumération `Animations` : `walk`, `run`), celles que les empreintes attendent.
WALK_CLIPS = {"walk": "Walk", "run": "Run"}
VCT_ANIMATION_PROPERTIES = 0x88
# `AnimationProperties` (7.0, `Characters/<race>_<sexe>/AnimationProperties.xdb`) : `walk` (m/s),
# vitesse de la marche (2,1 pour KaniaMale, 1,7 pour KaniaFemale…), puis `walkBackwards` et
# `walkForward` (3,5 partout : la course). Même ordre, flottants consécutifs dans le 17.0.
ANIMPROPS_WALK = 0x11C
ANIMPROPS_WALK_FORWARD = 0x124
# `SkeletalAnimation` : `endFrame` (+0xB0, u32), `fps` (+0xB4, f32), `speed` (+0x100, f32 : vitesse
# de lecture, 1,5 pour `KaniaFemale.Walk`, 1,2 pour `UndeadFemale.Walk`, comme dans les xdb 7.0).
SKELANIM_END_FRAME = 0xB0
SKELANIM_SPEED = 0x100
# Chevilles des pieds gauche et droit. Un pied est posé tant qu'il recule dans le repère du modèle
# (+Y, le modèle regardant −Y) ; une phase de moins de `MIN_STANCE` images n'est qu'un à-coup.
FEET = {"L": "LeftFoot", "R": "RightFoot"}
MIN_STANCE = 3


def close_loop(animation) -> None:
    """Clip en boucle : le client joue `endFrame` images (autant que le binaire en porte) et
    revient à la première — `Walk` de KaniaMale : 30 images, cycle d'une seconde. La première
    image est recopiée à la fin, pour que le lecteur interpole la dernière vers la première au
    lieu d'y sauter une image trop tôt (cycle de 29/30 s)."""
    import numpy as np
    for t in animation.tracks:
        if len(t.rotation) == animation.frames:
            t.translation = np.vstack([t.translation, t.translation[:1]])
            t.rotation = np.vstack([t.rotation, t.rotation[:1]])
        if np.size(t.scale) == animation.frames:
            t.scale = np.concatenate([t.scale, t.scale[:1]])
    animation.frames += 1


def frame_world(skeleton, animation, frame: int) -> np.ndarray:
    """Matrices monde des articulations à l'image `frame` du clip (bind pour les autres)."""
    from types import SimpleNamespace
    import numpy as np
    from tools.extract_menu_scene import rest_world_matrices

    def at(values):
        values = np.asarray(values)
        return values[frame:frame + 1] if len(values) > frame else values[:1]
    tracks = [SimpleNamespace(name=t.name, translation=at(t.translation), rotation=at(t.rotation),
                              scale=at(np.atleast_1d(t.scale))) for t in animation.tracks]
    return rest_world_matrices(skeleton, SimpleNamespace(tracks=tracks))


def stance_frames(ys) -> np.ndarray:
    """Images du cycle où le pied est posé : la cheville recule (+Y) jusqu'à l'image suivante.
    `ys` : Y de la cheville sur le cycle **fermé** (première image recopiée à la fin)."""
    import numpy as np
    return np.diff(np.asarray(ys, float)) > 0


def stance_runs(stance: np.ndarray) -> list[list[int]]:
    """Phases posées d'au moins `MIN_STANCE` images, en boucle sur le cycle (indices croissants,
    au-delà du cycle si la phase en passe la fin)."""
    import numpy as np
    n = len(stance)
    if not stance.any() or stance.all():
        return []
    start = int(np.argmin(stance))  # une image levée : aucune phase ne la traverse
    runs: list[list[int]] = []
    run: list[int] = []
    for k in range(start, start + n + 1):
        if k < start + n and stance[k % n]:
            run.append(k)
            continue
        if len(run) >= MIN_STANCE:
            runs.append(run)
        run = []
    return runs


def foot_contacts(stance: np.ndarray, fps: float) -> list[float]:
    """Instants (s, dans le cycle) où le pied se pose : début de chaque phase posée. Sur
    `KaniaMale.Walk`, 0,233 et 0,733 s — les évènements `Action` du clip (xdb 7.0 : 0,233 et 0,7)."""
    n = len(stance)
    return sorted(round((run[0] % n) / fps, 4) for run in stance_runs(stance))


def stance_speed(ys, stance: np.ndarray, fps: float) -> float | None:
    """Vitesse (m/s) à laquelle le pied posé recule — celle dont le corps avance sans glissement :
    médiane des pas de la cheville d'une image à l'autre pendant les phases posées."""
    import numpy as np
    dy = np.diff(np.asarray(ys, float))
    frames = [k % len(stance) for run in stance_runs(stance) for k in run]
    if not frames:
        return None
    return round(float(np.median(dy[frames])) * fps, 3)


def export_walks(manifest: dict, out_dir: Path, report: list[str]) -> dict:
    """Clips `walk` et `run` des gabarits de la création (`walk/<gabarit>.glb` : squelette et clips,
    sans maillage ; mêmes noms de nœuds que `public/game/character/models/<gabarit>.glb`), vitesses
    de marche (`speed`, `AnimationProperties.walk`) et de course (`runSpeed`, `walkForward`) du
    gabarit, instants où chaque pied se pose dans chaque clip (`steps`) et allure propre du clip
    (`pace`, vitesse du pied posé), lus sur le clip. Le lecteur ajoute les clips à ceux de
    l'avatar pour la boucle de marche."""
    from tools.allods_gltf import Exporter, clean_animation, load_animation, load_geometry
    from tools.allods_packdb import open_catalog, open_pack, packs_path
    from tools.chargen_scene import WebpTexturePool
    from tools.extract_menu_scene import BinSource
    import numpy as np
    chargen = json.loads(CHARGEN_INDEX.read_text(encoding="utf-8"))
    client = Path(manifest["latest"]["root"])
    db = open_pack(client)
    cat = open_catalog(db, client)
    packs = packs_path(client / "data" / "Packs")
    bins = BinSource([], [str(packs / p) for p in sorted(cat.names)])
    textures = WebpTexturePool(db, cat, bins, out_dir)
    wanted = {t["binary"]: name for name, t in chargen["templates"].items() if t.get("binary")}
    geometries: dict[str, int] = {}
    for g in db.resources("Geometry") + db.structs("Geometry"):
        n = cat.name(db.binary_ref(g))
        if n in wanted and n not in geometries:
            geometries[n] = g
    anim_names = {f"{b.rsplit('/', 1)[0]}/Animations/{b.rsplit('/', 1)[1].split('.')[0]}.{suffix}.(SkeletalAnimation).bin"
                  for b in wanted for suffix in WALK_CLIPS.values()}
    anim_res: dict[str, int] = {}
    for res in db.resources("SkeletalAnimation") + db.structs("SkeletalAnimation"):
        ref = db.binary_ref(res)
        n = cat.name(ref) if ref is not None else None
        if n in anim_names and n not in anim_res:
            anim_res[n] = res
    speeds: dict[str, dict[str, float]] = {}
    for vct in db.resources("VisCharacterTemplate") + db.structs("VisCharacterTemplate"):
        vo = db.ptr(vct + TEMPLATE_VISOBJECT)
        geo = db.ptr(vo + 0xC0) if vo is not None else None
        n = cat.name(db.binary_ref(geo)) if geo is not None else None
        props = db.ptr(vct + VCT_ANIMATION_PROPERTIES)
        if n in wanted and n not in speeds and props is not None:
            pair = {key: float(db.f32(props + off)) for key, off in (("speed", ANIMPROPS_WALK), ("runSpeed", ANIMPROPS_WALK_FORWARD))}
            speeds[n] = {k: round(v, 3) for k, v in pair.items() if 0.3 < v < 20}
    out: dict[str, dict] = {}
    for binary, name in sorted(wanted.items(), key=lambda x: x[1]):
        g = geometries.get(binary)
        loaded = load_geometry(db, cat, bins, g) if g is not None else None
        if loaded is None or loaded.skeleton is None:
            report.append(f"AVERTISSEMENT : marche de {name} — géométrie introuvable")
            continue
        skeleton = loaded.skeleton
        folder, stem = binary.rsplit("/", 1)
        stem = stem.split(".")[0]
        ex = Exporter(textures, 256)
        joints = ex.emit_skeleton(skeleton, name)
        span = float(np.max(np.abs(loaded.vertices["position"])) * 4.0)
        clips: dict[str, float] = {}
        steps: dict[str, dict[str, list[float]]] = {}
        measured: dict[str, dict[str, float | None]] = {}
        paces: dict[str, float] = {}
        for clip, suffix in WALK_CLIPS.items():
            anim_name = f"{folder}/Animations/{stem}.{suffix}.(SkeletalAnimation).bin"
            anim = load_animation(bins, anim_name, skeleton, span)
            if anim is None:
                report.append(f"AVERTISSEMENT : {name} — animation {suffix} absente")
                continue
            clean_animation(skeleton, anim)
            res = anim_res.get(anim_name)
            rate = float(db.f32(res + SKELANIM_SPEED)) if res is not None else 1.0
            rate = rate if 0.1 < rate < 10 else 1.0
            if res is not None and db.u32(res + SKELANIM_END_FRAME) != anim.frames:
                report.append(f"AVERTISSEMENT : {name} — {suffix} : endFrame {db.u32(res + SKELANIM_END_FRAME)}, "
                              f"{anim.frames} images dans le binaire")
            cycle = anim.frames
            close_loop(anim)
            worlds = [frame_world(skeleton, anim, k) for k in range(anim.frames)]
            fps = anim.fps * rate  # images par seconde réelles
            steps[clip], measured[clip] = {}, {}
            for side, bone in FEET.items():
                if bone not in skeleton.names:
                    continue
                ys = [w[skeleton.names.index(bone)][1, 3] for w in worlds]  # cycle fermé : cycle + 1 images
                stance = stance_frames(ys)
                steps[clip][side] = foot_contacts(stance, fps)
                measured[clip][side] = stance_speed(ys, stance, fps)
            clips[clip] = round(ex.emit_clip(clip, skeleton, joints, anim, rate), 4)
            # Allure propre du clip (m/s, à l'échelle du modèle de la création) : le lecteur y
            # accorde la cadence des pas quand l'avatar avance à la vitesse du gabarit.
            gaits = [v for v in measured[clip].values() if v]
            if gaits:
                paces[clip] = round(float(np.mean(gaits)) * float(chargen["templates"][name].get("scale") or 1.0), 3)
        if not clips:
            continue
        roots = [joints[i] for i in range(len(skeleton)) if not (0 <= skeleton.parents[i] < len(skeleton))]
        root = ex.gltf.add_node({"name": name, "children": roots})
        glb = ex.finish([root])
        (out_dir / "walk").mkdir(parents=True, exist_ok=True)
        (out_dir / "walk" / f"{name}.glb").write_bytes(glb)
        out[name] = {"glb": f"walk/{name}.glb", "clips": clips, **speeds.get(binary, {}), "steps": steps, "pace": paces}
        print(f"marche {name:>18}  {len(glb) / 1024:.0f} Kio  {clips}  vitesses {speeds.get(binary)}  "
              f"pied posé {measured}  pas {steps}")
    return out


def icon_present(pb: PackBin, key: str) -> bool:
    """Le client 32 bits contient-il l'icône `key` (chemin `…/<key>.(UITexture).xdb`) ?"""
    want = f"/{key.lower()}.(uitexture).xdb"
    return any(p.lower().endswith(want) or p.lower() == want[1:] for p in pb.paths)


def apply_versions(manifest: dict, records: list[AuraRecord], auras: list[dict], bundles: list[dict],
                   report: list[str]) -> None:
    """`since` de chaque aura et de chaque apparence (voir la docstring du module)."""
    presence: dict[str, list] = {e["id"]: [] for e in auras + bundles}
    for spec in manifest["clients"]:
        try:
            client = Client({k: v for k, v in spec.items() if k != "texts"}, texts=False, graph=False)
        except (FileNotFoundError, OSError, KeyError, ValueError) as error:
            report.append(f"AVERTISSEMENT : client {spec['version']} illisible — {error}")
            for k in presence:
                presence[k].append((spec["version"], spec.get("game_version"), None, None))
            continue
        v2 = client.pb.fmt == "v2"
        keys = set(client.keys.values()) if v2 else set()
        found = 0
        for e in auras + bundles:
            if v2:
                ok = e.get("resourceId") in keys
            else:
                ok = bool(e.get("iconKey")) and icon_present(client.pb, e["iconKey"])
            presence[e["id"]].append((spec["version"], spec.get("game_version"), ok, "resourceId" if v2 else "icon"))
            found += ok
        print(f"client {spec['version']} ({'resourceId' if v2 else 'icône'}) : {found} présentes")
        del client
    for e in auras + bundles:
        rows = presence[e["id"]]
        since = first_version([r[:3] for r in rows])
        if since:
            since["method"] = next(r[3] for r in rows if r[0] == since["version"])
            e["since"] = since


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Auras de la garde-robe : noms, icônes, obtention, effets, versions")
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--no-versions", action="store_true")
    ap.add_argument("--no-fx", action="store_true")
    ap.add_argument("--no-sounds", action="store_true")
    ap.add_argument("--walks-only", action="store_true", help="seulement les clips de marche (walk/), dans auras.json")
    args = ap.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    report: list[str] = []
    if args.walks_only:
        index = json.loads((args.out / "auras.json").read_text(encoding="utf-8"))
        index["walks"] = export_walks(manifest, args.out, report)
        (args.out / "auras.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    else:
        run(manifest, args.out, not args.no_versions, not args.no_fx, not args.no_sounds, report)
    for line in report:
        print(line, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
