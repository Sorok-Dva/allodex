#!/usr/bin/env python3
"""Juxtapose une capture du site et une référence du jeu, recadrées, et écrit montage + différence.

Usage : python3 tools/compare_refs.py site.png refs/astral.png \\
            --site-box x0 y0 x1 y1 --ref-box 470 180 1490 790 --out /tmp/cmp

Écrit `<out>-montage.png` (site | référence) et `<out>-diff.png` (différence absolue,
niveaux de gris) et renvoie le score moyen : 0 = images identiques.
"""
from __future__ import annotations

import argparse

import numpy as np
from PIL import Image


def compare(site_png, ref_png, site_box, ref_box, out_prefix) -> float:
    s = Image.open(site_png).convert("RGB").crop(tuple(site_box))
    r = Image.open(ref_png).convert("RGB").crop(tuple(ref_box))
    if s.size != r.size:
        s = s.resize(r.size)
    a, b = np.asarray(s).astype(int), np.asarray(r).astype(int)
    diff = np.abs(a - b).mean(axis=2).astype(np.uint8)
    montage = Image.new("RGB", (r.width * 2 + 10, r.height), (40, 40, 40))
    montage.paste(s, (0, 0))
    montage.paste(r, (r.width + 10, 0))
    montage.save(f"{out_prefix}-montage.png")
    Image.fromarray(diff).save(f"{out_prefix}-diff.png")
    score = float(diff.mean())
    print(f"score {score:.2f} (0 = identique)")
    return score


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("site")
    p.add_argument("ref")
    p.add_argument("--site-box", nargs=4, type=int, required=True)
    p.add_argument("--ref-box", nargs=4, type=int, default=[470, 180, 1490, 790])
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    compare(a.site, a.ref, a.site_box, a.ref_box, a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
