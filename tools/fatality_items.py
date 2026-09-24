"""Objets qui apprennent les fatalités, retrouvés dans la base compilée d'un client (`pack.bin`).

Chaîne établie sur le client 17.0 (septembre 2026), sans aucun nom deviné :

1. `CreatureFatalityAbilityAction` (script visuel d'un buff) porte le **type** de fatalité (celui
   du vecteur `fatalities` de `SlonSettings`) dans son dernier champ (`+0x44` en 17.0 ; l'arbre
   7.0 le nomme `fatalityType`, énumération `client.SLON.FatalityType`) ;
2. le `BuffVisScripts` qui la contient est le `visScript` d'un ou plusieurs **buffs** : leur
   **nom** est celui de la fatalité en jeu (« Лунный ритуал » / « Lunar Ritual ») et leur **icône**
   (`UISingleTexture`) lui est propre pour les seize fatalités de boutique (les dix de classe et
   la 11 partagent l'icône générique `Fatality`) ;
3. l'`UnlockResource` (« умение », capacité apprise) qui pointe **la même** `UISingleTexture` est
   la capacité que l'objet débloque (« Изучена новая активируемая способность "Лунный ритуал" ») ;
4. un `ItemResource` apprend la fatalité quand l'une de ses structures imbriquées (conditions
   d'emploi `PredicateUnlock`, actions) pointe cette `UnlockResource`. Un objet peut en pointer
   plusieurs (« Подарочный сборник Палача »), une fatalité peut venir de plusieurs objets
   (versions boutique, échange et temporaire).

Ces liens sont des pointeurs du `pack.bin` (table de relocation), sauf deux cas signalés comme
tels : la fatalité 11 (« Расправа »), dont l'icône est générique, n'a pas d'`UnlockResource`
propre — elle est rattachée par son **nom** à la capacité « Умение «Расправа» » du « Кодекс
Палача » (`link: "name"`) ; les buffs n'ont aucun pointeur entrant hors de leur script (les
sorts et effets serveur qui les posent ne sont pas dans le client).

Le module travaille sur `tools/packbin.PackBin` (formats v1 32 bits 8.0–11.x et v2 64 bits
15.x–17.x) : aucun décalage de champ n'est supposé hors de ceux qu'on retrouve par structure
(dernier champ de l'action, premier pointeur vers une `UISingleTexture`, pointeurs entrants).
Les textes (nom d'objet, de buff, de capacité) sont repérés par la **forme** d'une référence de
texte v2 (`u32` indice aligné, suivi d'un `u32` nul) aux décalages fournis par `TEXT_FIELDS`,
relevés sur 17.0 et vérifiés sur 16.0 (client FR).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.packbin import KIND_PTR, PackBin  # noqa: E402

# Décalage du champ texte « nom » par type de ressource, format v2 (15.x–17.x : identiques,
# vérifiés sur 16.0 FR et 17.0 RU).
TEXT_FIELDS = {"ItemResource": 0x228, "BuffResource": 0x68, "UnlockResource": 0x70}
DESCRIPTION_FIELDS = {"ItemResource": 0x150, "BuffResource": 0x48, "UnlockResource": 0x48}


@dataclass
class FatalitySource:
    type: int
    buffs: list[int] = field(default_factory=list)          # décalages des BuffResource
    icons: set[int] = field(default_factory=set)            # UISingleTexture des buffs
    unlocks: list[int] = field(default_factory=list)        # UnlockResource liées (même icône)
    items: list[int] = field(default_factory=list)          # ItemResource qui pointent une unlock
    link: str | None = None                                 # "icon" (pointeurs) ou "name"


class Graph:
    """Pointeurs d'une base, dans les deux sens, et découpage en objets indexés."""

    def __init__(self, pb: PackBin) -> None:
        self.pb = pb
        keys = pb._rkeys
        ptr = (keys & 3) == KIND_PTR
        self.src = (keys[ptr] >> 2).astype(np.int64)
        self.dst = pb._rtarget[ptr].astype(np.int64)
        order = np.argsort(self.dst, kind="stable")
        self.dst_sorted = self.dst[order]
        self.src_by_dst = self.src[order]
        self.bounds = pb.object_bounds()
        roots = list(pb.ids.values()) if pb.ids else list(pb.paths.values())
        self.roots = np.array(sorted(set(int(r) for r in roots)), dtype=np.int64)

    def object_end(self, addr: int) -> int:
        """Fin de l'objet (indexé ou imbriqué) commençant en `addr`."""
        i = int(np.searchsorted(self.bounds, addr, "right"))
        return int(self.bounds[i]) if i < len(self.bounds) else addr + 8

    def root_of(self, addr: int) -> int | None:
        """Objet indexé (ressource) qui contient `addr`."""
        i = int(np.searchsorted(self.roots, addr, "right")) - 1
        return int(self.roots[i]) if i >= 0 else None

    def root_end(self, root: int) -> int:
        i = int(np.searchsorted(self.roots, root, "right"))
        return int(self.roots[i]) if i < len(self.roots) else root + 8

    def referrers(self, start: int, end: int | None = None) -> list[int]:
        """Emplacements des pointeurs qui visent `[start, end)` (ou `start` seul)."""
        end = start + 1 if end is None else end
        a = int(np.searchsorted(self.dst_sorted, start))
        b = int(np.searchsorted(self.dst_sorted, end))
        return [int(x) for x in self.src_by_dst[a:b]]

    def pointers_from(self, start: int, end: int) -> list[int]:
        """Cibles des pointeurs posés dans `[start, end)`."""
        pb = self.pb
        lo = int(np.searchsorted(pb._rkeys, start << 2))
        hi = int(np.searchsorted(pb._rkeys, end << 2))
        k, t = pb._rkeys[lo:hi], pb._rtarget[lo:hi]
        return [int(x) for x in t[(k & 3) == KIND_PTR]]


def fatality_types(pb: PackBin, g: Graph) -> dict[int, int]:
    """Type de fatalité de chaque `CreatureFatalityAbilityAction` (seul champ propre de la classe,
    `fatalityType`). Son décalage change avec le format (`+0x44` en 17.0, `+0x24` en 4.0) : c'est
    le champ dont les valeurs, petites et non nulles, sont **toutes distinctes** d'une action à
    l'autre (les autres champs sont communs : drapeaux de `VisAction`, tailles)."""
    actions = pb.objects_of("CreatureFatalityAbilityAction")
    if not actions:
        return {}
    size = min(g.object_end(a) - a for a in actions)
    best, best_off = -1, None
    for off in range(4, size - 3, 4):
        values = [pb.u32(a + off) for a in actions]
        if not all(0 < v < 256 for v in values):
            continue
        distinct = len(set(values))
        if distinct > best:
            best, best_off = distinct, off
    if best_off is None or (len(actions) > 1 and best < 2):
        return {}
    return {a: pb.u32(a + best_off) for a in actions}


def text_ref(pb: PackBin, obj: int, off: int, count: int) -> int | None:
    """Référence de texte v2 au champ `off` : indice valide suivi d'un mot nul."""
    v = pb.u32(obj + off)
    return v if 0 < v < count and pb.u32(obj + off + 4) == 0 else None


def fatality_sources(pb: PackBin, g: Graph | None = None) -> dict[int, FatalitySource]:
    """Pour chaque type de fatalité : buffs, icônes, capacités (`UnlockResource`) et objets."""
    g = g or Graph(pb)
    out: dict[int, FatalitySource] = {}
    for action, ftype in fatality_types(pb, g).items():
        script = g.root_of(action)
        if not ftype or script is None or pb.type_at(script) != "BuffVisScripts":
            continue
        src = out.setdefault(ftype, FatalitySource(ftype))
        for loc in g.referrers(script, g.root_end(script)):
            buff = g.root_of(loc)
            if buff is None or buff == script or pb.type_at(buff) != "BuffResource" or buff in src.buffs:
                continue
            src.buffs.append(buff)
            icon = next((t for t in g.pointers_from(buff, g.root_end(buff))
                         if pb.type_at(t) == "UISingleTexture"), None)
            if icon is not None:
                src.icons.add(icon)
    # Icône propre à une seule fatalité → ses capacités, puis les objets qui les pointent.
    owners: dict[int, set[int]] = {}
    for src in out.values():
        for icon in src.icons:
            owners.setdefault(icon, set()).add(src.type)
    for src in out.values():
        own = [i for i in src.icons if owners[i] == {src.type}]
        for icon in own:
            for loc in g.referrers(icon):
                unlock = g.root_of(loc)
                if unlock is not None and pb.type_at(unlock) == "UnlockResource" and unlock not in src.unlocks:
                    src.unlocks.append(unlock)
        if src.unlocks:
            src.link = "icon"
    for src in out.values():
        for unlock in src.unlocks:
            for loc in g.referrers(unlock):
                item = g.root_of(loc)
                if item is not None and pb.type_at(item) == "ItemResource" and item not in src.items:
                    src.items.append(item)
    return out


def _bare(s: str) -> str:
    """Texte sans guillemets ni espaces (« Compétence « Carnage » » → `CompétenceCarnage`)."""
    import re
    return re.sub(r"[«»\"“”\s ]", "", s or "")


def link_by_name(pb: PackBin, g: Graph, sources: dict[int, FatalitySource], texts, count: int) -> None:
    """Fatalités sans capacité propre (icône générique) : capacité dont le nom est celui du buff
    (« Умение «Расправа» » ↔ buff « Расправа »), puis objets qui la pointent. `link = "name"`."""
    unlocks = pb.objects_of("UnlockResource")
    names = {}
    for u in unlocks:
        t = text_ref(pb, u, TEXT_FIELDS["UnlockResource"], count)
        if t is not None:
            names[u] = texts(t) or ""
    taken = {u for s in sources.values() for u in s.unlocks}
    for src in sources.values():
        if src.unlocks or not src.buffs:
            continue
        t = text_ref(pb, src.buffs[0], TEXT_FIELDS["BuffResource"], count)
        name = (texts(t) or "") if t is not None else ""
        if not name:
            continue
        for u, n in names.items():
            # « Умение «Расправа» » seulement : la capacité générique « Расправа » (icône commune
            # aux fatalités de classe, apprise par « Знак Палача ») n'est pas propre à celle-ci.
            nn, bare = _bare(n), _bare(name)
            if u not in taken and nn != bare and nn.endswith(bare) and "«" in n:
                src.unlocks.append(u)
        if src.unlocks:
            src.link = "name"
            for unlock in src.unlocks:
                for loc in g.referrers(unlock):
                    item = g.root_of(loc)
                    if item is not None and pb.type_at(item) == "ItemResource" and item not in src.items:
                        src.items.append(item)


def resource_keys(pb: PackBin) -> dict[int, int]:
    """Décalage d'objet → `resourceId` (clé des `.xdb`, commune à tous les builds), table de
    l'entête v2 en `0x30` (`u64 clé, u64 décalage` par entrée) ; vide en v1 (les chemins y
    suffisent). Sert à reconnaître le même objet d'un client à l'autre (FR 16.0 ↔ RU 17.0)."""
    if pb.fmt != "v2":
        return {}
    import struct
    raw = pb.raw
    rel, count = struct.unpack_from("<II", raw, 0x30)
    base = 0x30 + rel
    out: dict[int, int] = {}
    for b in range(count):
        o = base + 8 * b
        r, n = struct.unpack_from("<II", raw, o)
        for k in range(n):
            key, value = struct.unpack_from("<QQ", raw, o + r + 16 * k)
            out[int(value)] = int(key)
    return out


# --- export --------------------------------------------------------------------------------------

def _is_text(s: str | None, lang: str) -> bool:
    """Texte présent ; un texte « anglais » ou « français » resté en cyrillique n'a pas de
    traduction officielle."""
    import re
    if not s or not s.strip():
        return False
    return not (lang in ("en", "fr") and re.search(r"[А-Яа-яЁё]", s))


def _clean(s: str) -> str:
    return s.replace(" ", " ").strip().strip("«»\"").strip()


class Client:
    """Un client archivé : sa base, ses textes (facultatifs) et son graphe."""

    def __init__(self, spec: dict) -> None:
        import zipfile
        from pathlib import Path
        from tools.allods_packdb import packs_path
        from tools.extract_talents import cached_pack
        from tools.packbin import LocTable, inflate
        self.spec = spec
        packs = packs_path(Path(spec["root"]) / "data" / "Packs")
        raw = cached_pack(packs / spec["pak"])
        if raw is None:
            raise FileNotFoundError(f"{packs / spec['pak']} : Bin/pack.bin absent")
        self.pb = PackBin(raw)
        self.graph = Graph(self.pb)
        self.packs = packs
        self.locs = {}
        for lang, (pak, member) in (spec.get("texts") or {}).items():
            self.locs[lang] = LocTable(inflate(zipfile.ZipFile(packs / pak).read(member)))
        self.sources = fatality_sources(self.pb, self.graph)
        main = next(iter(self.locs.values()), None)
        if main is not None:
            link_by_name(self.pb, self.graph, self.sources, main.get, main.count)
        self.keys = resource_keys(self.pb)

    def text(self, obj: int, kind: str, lang: str) -> str | None:
        loc = self.locs.get(lang)
        if loc is None:
            return None
        ref = text_ref(self.pb, obj, TEXT_FIELDS[kind], loc.count)
        s = loc.get(ref) if ref is not None else None
        return _clean(s) if _is_text(s, lang) else None


def export_icon(client: Client, obj: int, out_dir) -> str | None:
    """Icône d'un objet (première `UISingleTexture` pointée → `UITexture`) en PNG, recadrée sur
    sa zone utile comme les autres icônes du site (`tools/chargen_ui.py`) ; nom = celui du
    fichier `(UITexture).bin` du client. Format v2 : pak `+0x40`, rang `+0x48`, hauteur `+0x78`,
    hauteur et largeur utiles `+0x88`/`+0x8C`, largeur `+0x94`."""
    import io
    import re
    import zipfile
    from tools.uitexture import decode_uitexture
    pb, g = client.pb, client.graph
    single = next((t for t in g.pointers_from(obj, g.root_end(obj)) if pb.type_at(t) == "UISingleTexture"), None)
    if single is None or pb.fmt != "v2":
        return None
    tex = next((t for t in g.pointers_from(single, g.root_end(single)) if pb.type_at(t) == "UITexture"), None)
    if tex is None:
        return None
    pak_i, entry = pb.u32(tex + 0x40), pb.u32(tex + 0x48)
    if pak_i >= len(pb.pak_names):
        return None
    z = zipfile.ZipFile(client.packs / pb.pak_names[pak_i])
    info = z.infolist()[entry]
    key = re.sub(r"\.\(UITexture\)\.bin$", "", info.filename.replace("\\", "/").split("/")[-1])
    w, h, rw, rh = pb.u32(tex + 0x94), pb.u32(tex + 0x78), pb.u32(tex + 0x8C), pb.u32(tex + 0x88)
    data = z.read(info)
    try:
        img, _ = decode_uitexture(data, (w, h) if w and h else None)
    except ValueError:
        img, _ = decode_uitexture(data)
    if rw and rh:
        img = img.crop((0, 0, min(rw, img.width), min(rh, img.height)))
    out_dir.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    (out_dir / f"{key}.png").write_bytes(buf.getvalue())
    return key


def collect(spec: dict, out_dir, log=print) -> dict[str, dict]:
    """Objets, noms officiels, icônes et versions d'apparition de chaque fatalité.

    `spec` (manifeste, `items`) : `latest` (client de référence : russe, anglais, icônes), `fr`
    (client FR : français, par `resourceId` commun), `clients` (clients archivés dans l'ordre
    des versions : le premier qui contient le type de fatalité donne `since`)."""
    latest = Client(spec["latest"])
    fr = Client(spec["fr"]) if spec.get("fr") else None
    fr_by_key = {v: k for k, v in fr.keys.items()} if fr else {}
    icons_dir = out_dir / "icons"
    out: dict[int, dict] = {}
    for ftype, src in sorted(latest.sources.items()):
        entry: dict = {"type": ftype}
        if src.buffs:
            name = {lang: latest.text(src.buffs[0], "BuffResource", lang) for lang in ("ru", "en")}
            fb = fr_by_key.get(latest.keys.get(src.buffs[0]))
            if fb is not None:
                name["fr"] = fr.text(fb, "BuffResource", "fr")
            entry["name"] = {k: v for k, v in sorted(name.items()) if v}
        merged: list[dict] = []
        for item in sorted(src.items, key=lambda i: latest.keys.get(i, 0)):
            rid = latest.keys.get(item)
            names = {lang: latest.text(item, "ItemResource", lang) for lang in ("ru", "en")}
            if rid in fr_by_key:
                names["fr"] = fr.text(fr_by_key[rid], "ItemResource", "fr")
            names = {k: v for k, v in sorted(names.items()) if v}
            icon = export_icon(latest, item, icons_dir)
            # Mêmes nom et icône (versions boutique, échange, temporaire) : un seul objet.
            same = next((m for m in merged if m["name"].get("ru") == names.get("ru") and m["icon"] == icon), None)
            if same:
                same["resourceIds"].append(rid)
                for k, v in names.items():
                    same["name"].setdefault(k, v)
            else:
                merged.append({"name": names, "icon": icon, "resourceIds": [rid]})
        if merged:
            entry["items"] = merged
            entry["link"] = src.link
        out[ftype] = entry
    del latest, fr
    seen: dict[int, dict] = {}
    previous: str | None = None
    for c in spec["clients"]:
        try:
            client = Client({k: v for k, v in c.items() if k != "texts"})
        except (FileNotFoundError, OSError, KeyError) as error:
            log(f"AVERTISSEMENT : client {c['version']} illisible — {error}")
            continue
        types = sorted(client.sources)
        log(f"client {c['version']} ({c.get('game_version', '?')}) : types {types}")
        for t in types:
            if t not in seen:
                seen[t] = {"version": c["version"], "client": c.get("game_version")}
                if previous:
                    seen[t]["previous"] = previous
        previous = c["version"]
        del client
    for t, entry in out.items():
        if t in seen:
            entry["since"] = seen[t]
    return {str(k): v for k, v in out.items()}


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    from pathlib import Path
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description="Objets, noms, icônes et versions des fatalités")
    ap.add_argument("--manifest", type=Path, default=here / "fatalities_manifest.json")
    ap.add_argument("--out", type=Path, default=here.parent / "public" / "game" / "fatalities")
    ap.add_argument("--json", type=Path, default=here / "fatality_items.json")
    args = ap.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    data = collect(manifest["items"], args.out)
    args.json.write_text(json.dumps({"_note": "Généré par tools/fatality_items.py (ne pas éditer) ; "
                                     "fusionné dans fatalities.json par tools/extract_fatalities.py.",
                                     "fatalities": data}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{args.json} : {len(data)} fatalités")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
