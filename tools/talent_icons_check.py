"""Vérification objective des icônes de talents extraites.

Chaque talent extrait porte `iconSrc`, le fichier d'où vient son icône (chemin `.bin` pour les
clients 32 bits, entrée du pak pour les clients 64 bits). Deux contrôles :

* **arbre serveur 7.0** (`.xdb` en clair) : pour un talent 7.0, l'icône attendue se lit en suivant
  `<image href>` du sort ou de la capacité (en remontant les `<Prototype>`), puis
  `<singleTexture href>` de l'`UISingleTexture` et `<binaryFile href>` de l'`UITexture` ;
* **d'une version à l'autre** : pour les talents de même nom (même langue), le nom du fichier
  d'icône se conserve presque toujours ; un taux d'accord bas trahit un décalage (bon titre,
  mauvaise image). Sert aux clients 64 bits, dont les ressources n'ont plus de chemin.

Usage : python3 tools/talent_icons_check.py [--data public/game/talents] [--server …]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HREF = re.compile(r'<(image|Prototype|singleTexture|binaryFile)\s+href="([^"#]+)')
DEFAULT_SERVER = "/mnt/f/ALLODS ONLINE SERVER/Allods 7.0/game/data"


class ServerIcons:
    """Icône attendue d'une ressource de l'arbre serveur, par lecture directe des `.xdb`."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self._refs: dict[str, dict[str, str]] = {}

    def refs(self, xdb: str) -> dict[str, str]:
        xdb = xdb.lstrip("/")
        if xdb not in self._refs:
            try:
                text = (self.root / xdb).read_text("utf-8", "replace")
            except OSError:
                text = ""
            out: dict[str, str] = {}
            for tag, href in HREF.findall(text):
                out.setdefault(tag, href.lstrip("/"))
            self._refs[xdb] = out
        return self._refs[xdb]

    def image(self, xdb: str, depth: int = 0) -> str | None:
        r = self.refs(xdb)
        if "image" in r:
            return r["image"]
        if "Prototype" in r and depth < 6:
            return self.image(r["Prototype"], depth + 1)
        return None

    def icon_bin(self, xdb: str) -> str | None:
        """Chemin `.bin` de l'icône d'un sort ou d'une capacité (None si l'arbre ne le dit pas)."""
        single = self.image(xdb)
        if not single:
            return None
        tex = self.refs(single).get("singleTexture") if "UISingleTexture" in single else single
        if not tex:
            return None
        return self.refs(tex).get("binaryFile") or re.sub(r"\.xdb$", ".bin", tex)


def class_files(data: Path, version: str) -> list[Path]:
    return sorted((data / version).glob("*.json"))


def check_server(data: Path, version: str, server: ServerIcons) -> tuple[int, int, list[tuple]]:
    """(accords, comparables, désaccords) entre `iconSrc` et l'icône de l'arbre serveur."""
    ok = total = 0
    bad = []
    for f in class_files(data, version):
        d = json.loads(f.read_text())
        for t in d["talents"].values():
            if not t.get("iconSrc") or "/" not in t["ref"]:
                continue
            want = server.icon_bin(t["ref"])
            if not want:
                continue
            total += 1
            if want.lower() == t["iconSrc"].lstrip("/").lower():
                ok += 1
            else:
                bad.append((f.stem, t["ref"], t["iconSrc"], want))
    return ok, total, bad


def base(src: str) -> str:
    return re.sub(r"\.\(UITexture\)\.bin$", "", src.rsplit("/", 1)[-1]).lower()


def check_cross(data: Path, a: str, b: str, lang: str) -> tuple[int, int, list[tuple]]:
    """Talents de même nom (`lang`) et même classe dans `a` et `b` : noms de fichiers d'icône égaux ?"""
    ok = total = 0
    bad = []
    for fa in class_files(data, a):
        fb = data / b / fa.name
        if not fb.exists():
            continue
        da, db = json.loads(fa.read_text()), json.loads(fb.read_text())
        by_name: dict[str, set[str]] = {}
        for t in db["talents"].values():
            n = t.get("name", {}).get(lang)
            if n and t.get("iconSrc"):
                by_name.setdefault(n, set()).add(base(t["iconSrc"]))
        for t in da["talents"].values():
            n = t.get("name", {}).get(lang)
            if not n or not t.get("iconSrc") or n not in by_name:
                continue
            total += 1
            if base(t["iconSrc"]) in by_name[n]:
                ok += 1
            else:
                bad.append((fa.stem, n, t["iconSrc"], sorted(by_name[n])))
    return ok, total, bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", type=Path, default=Path(__file__).resolve().parent.parent / "public" / "game" / "talents")
    ap.add_argument("--server", default=DEFAULT_SERVER)
    args = ap.parse_args(argv)
    ok, total, bad = check_server(args.data, "7.0", ServerIcons(args.server))
    print(f"7.0 / arbre serveur : {ok}/{total} ({100 * ok / max(1, total):.1f} %)")
    for row in bad[:10]:
        print("  ", row)
    for a, b, lang in (("8.0", "9.0", "fr"), ("9.0", "15.0", "fr"), ("15.0", "16.0", "fr"), ("7.0", "17.0", "en")):
        ok, total, bad = check_cross(args.data, a, b, lang)
        print(f"{a} ↔ {b} ({lang}) : {ok}/{total} ({100 * ok / max(1, total):.1f} %)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
