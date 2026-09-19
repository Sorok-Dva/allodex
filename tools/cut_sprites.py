#!/usr/bin/env python3
"""Découpe des sprites d'interface dans les captures live du jeu (refs/).

Usage : python3 tools/cut_sprites.py [--manifest tools/sprites_manifest.json]
                                    [--out public/game/sprites] [--sheet [planche.png]]

Écrit `public/game/sprites/<nom>.png` et l'index `public/game/sprites.json`
(`{"<nom>": {"w": int, "h": int, "slice": [top, right, bottom, left] | null}}`).
`--sheet` produit en plus une planche de contrôle (tous les sprites x3 sur damier gris).

Les boîtes sont en pixels écran (captures 1920x1009). Toute boîte hors de la fenêtre
Succès (x 470-1490, y 180-790) est refusée : on ne découpe jamais le HUD du joueur.

Options par sprite dans le manifeste :
  capture     clé de `captures` (source = capture écran) ; alternative : `texture`
  texture     chemin PNG relatif à `textures_dir` (texture du client déjà extraite) ;
              la boîte n'est alors pas contrainte à la fenêtre Succès. Le chemin doit
              rester sous `textures_dir` (ni absolu, ni `..`).
  box         [x0, y0, x1, y1]  obligatoire pour une capture, optionnel pour une texture
  slice       [top, right, bottom, left] ou null (9-slice CSS `border-image`)
  alpha_key   {"rgb": [r, g, b], "tol": n}  rend transparents les pixels proches
  clear_center  true : met l'intérieur des tranches `slice` à alpha 0
  fill        {"rgb": [r,g,b], "box": [x0,y0,x1,y1], "alpha": 255} ou liste : aplat
              posé dans le sprite (coordonnées locales), pour effacer du texte.
              Un rectangle qui déborde du sprite est rogné ; un rectangle vide,
              inversé ou entièrement hors du sprite lève ValueError (il trahit
              presque toujours des coordonnées écran laissées par erreur).
  repeat_x    [{"src": x, "x0": a, "x1": b, "y0": c?, "y1": d?}] : recopie la colonne
              locale `src` sur les colonnes a..b (efface un texte sans casser le dégradé)
  repeat_y    [{"src": y, "y0": a, "y1": b, "x0": c?, "x1": d?}] : idem par lignes
  alpha_poly  [[[x, y], ...], ...] : polygones (coordonnées locales) à GARDER ; tout
              ce qui est en dehors passe à alpha 0. Sert aux ornements non
              rectangulaires (extrémités de la plaque de titre) dont les coins
              laisseraient voir le décor du jeu.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
WINDOW = (470, 180, 1490, 790)
DEFAULT_TEXTURES = HERE.parent / "public" / "game" / "textures"


def _clip_rect(rect: list[int], width: int, height: int, what: str) -> tuple[int, int, int, int]:
    """Rogne un rectangle local aux dimensions du sprite ; refuse ce qui n'y touche pas."""
    x0, y0, x1, y1 = (int(v) for v in rect)
    if x0 >= x1 or y0 >= y1:
        raise ValueError(f"rectangle `{what}` vide ou inversé : {rect}")
    cx0, cy0 = max(0, x0), max(0, y0)
    cx1, cy1 = min(width, x1), min(height, y1)
    if cx0 >= cx1 or cy0 >= cy1:
        raise ValueError(
            f"rectangle `{what}` entièrement hors du sprite {width}x{height} : {rect} "
            "(coordonnées locales attendues, pas des coordonnées écran)"
        )
    return cx0, cy0, cx1, cy1


def resolve_texture(tex_dir: Path, rel: str) -> Path:
    """Chemin d'une texture du client, confiné à `tex_dir` (pas de `..`, pas d'absolu)."""
    p = Path(rel)
    if p.is_absolute() or ".." in p.parts or rel.startswith(("/", "\\")):
        raise ValueError(f"chemin de texture non confiné à textures_dir : {rel}")
    target = (tex_dir / p).resolve()
    if not target.is_relative_to(tex_dir.resolve()):
        raise ValueError(f"chemin de texture non confiné à textures_dir : {rel}")
    return target


def validate_box(box: list[int]) -> None:
    x0, y0, x1, y1 = box
    if not (WINDOW[0] <= x0 < x1 <= WINDOW[2] and WINDOW[1] <= y0 < y1 <= WINDOW[3]):
        raise ValueError(f"boîte hors de la fenêtre Succès : {box}")


def cut_sprite(
    img: Image.Image,
    box: list[int] | None = None,
    alpha_key: dict | None = None,
    clear_center: bool = False,
    slice_: list[int] | None = None,
    fill: dict | list | None = None,
    repeat_x: list[dict] | None = None,
    repeat_y: list[dict] | None = None,
    alpha_poly: list[list] | None = None,
) -> Image.Image:
    out = img.convert("RGBA")
    if box is not None:
        out = out.crop(tuple(box))
    for axis, specs in (("x", repeat_x), ("y", repeat_y)):
        for spec in specs or []:
            a = np.asarray(out).astype(np.uint8).copy()
            if axis == "x":
                y0 = int(spec.get("y0", 0))
                y1 = int(spec.get("y1", out.height))
                col = a[y0:y1, int(spec["src"]) : int(spec["src"]) + 1]
                a[y0:y1, int(spec["x0"]) : int(spec["x1"])] = col
            else:
                x0 = int(spec.get("x0", 0))
                x1 = int(spec.get("x1", out.width))
                row = a[int(spec["src"]) : int(spec["src"]) + 1, x0:x1]
                a[int(spec["y0"]) : int(spec["y1"]), x0:x1] = row
            out = Image.fromarray(a, "RGBA")
    if fill:
        fills = fill if isinstance(fill, list) else [fill]
        a = np.asarray(out).astype(np.uint8).copy()
        for f in fills:
            fx0, fy0, fx1, fy1 = _clip_rect(f["box"], out.width, out.height, "fill")
            a[fy0:fy1, fx0:fx1, 0:3] = f["rgb"]
            a[fy0:fy1, fx0:fx1, 3] = int(f.get("alpha", 255))
        out = Image.fromarray(a, "RGBA")
    if alpha_key:
        a = np.asarray(out).astype(int)
        rgb = np.array(alpha_key["rgb"])
        tol = int(alpha_key.get("tol", 12))
        mask = np.abs(a[:, :, :3] - rgb).max(axis=2) <= tol
        a[:, :, 3] = np.where(mask, 0, 255)
        out = Image.fromarray(a.astype(np.uint8), "RGBA")
    if alpha_poly:
        keep = Image.new("L", out.size, 0)
        dr = ImageDraw.Draw(keep)
        for poly in alpha_poly:
            dr.polygon([tuple(p) for p in poly], fill=255)
        a = np.asarray(out).astype(np.uint8).copy()
        a[:, :, 3] = np.minimum(a[:, :, 3], np.asarray(keep))
        out = Image.fromarray(a, "RGBA")
    if clear_center:
        if not slice_:
            raise ValueError("clear_center exige des tranches `slice`")
        top, right, bottom, left = slice_
        a = np.asarray(out).astype(np.uint8).copy()
        y0, y1 = top, max(top, out.height - bottom)
        x0, x1 = left, max(left, out.width - right)
        a[y0:y1, x0:x1, 3] = 0
        out = Image.fromarray(a, "RGBA")
    return out


def build_sheet(index: dict, sprites_dir: Path, out_path: Path, scale: int = 3, maxw: int = 1400) -> Path:
    """Planche de contrôle : tous les sprites agrandis sur damier gris, avec étiquettes."""
    pad, label = 12, 13
    cells = []
    for name, meta in index.items():
        im = Image.open(sprites_dir / f"{name}.png").convert("RGBA")
        cells.append((name, meta, im.resize((im.width * scale, im.height * scale), Image.NEAREST)))
    lines: list[list] = []
    cur: list = []
    curw = 0
    for cell in cells:
        w = max(cell[2].width, 8 * len(cell[0])) + pad
        if cur and curw + w > maxw:
            lines.append(cur)
            cur, curw = [], 0
        cur.append(cell)
        curw += w
    if cur:
        lines.append(cur)
    width = max(sum(max(c[2].width, 8 * len(c[0])) + pad for c in ln) for ln in lines) + pad
    height = sum(max(c[2].height for c in ln) + label + pad for ln in lines) + pad
    sheet = Image.new("RGBA", (width, height), (128, 128, 128, 255))
    dr = ImageDraw.Draw(sheet)
    for yy in range(0, height, 12):
        for xx in range(0, width, 12):
            if (xx // 12 + yy // 12) % 2:
                dr.rectangle([xx, yy, xx + 11, yy + 11], fill=(150, 150, 150, 255))
    y = pad
    for ln in lines:
        x = pad
        for name, meta, im in ln:
            dr.text((x, y), f"{name} {meta['w']}x{meta['h']}", fill=(0, 0, 0, 255))
            sheet.alpha_composite(im, (x, y + label))
            dr.rectangle(
                [x - 1, y + label - 1, x + im.width, y + label + im.height],
                outline=(255, 0, 0, 255),
            )
            x += max(im.width, 8 * len(name)) + pad
        y += max(c[2].height for c in ln) + label + pad
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(out_path)
    return out_path


def run(manifest_path: Path, out_dir: Path) -> dict:
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    captures = {
        k: Image.open(v if Path(v).is_absolute() else HERE.parent / v)
        for k, v in manifest["captures"].items()
    }
    tex_dir = manifest.get("textures_dir")
    tex_dir = Path(tex_dir) if tex_dir else DEFAULT_TEXTURES
    if not tex_dir.is_absolute():
        tex_dir = HERE.parent / tex_dir
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    index: dict[str, dict] = {}
    for name, spec in manifest["sprites"].items():
        if spec.get("texture"):
            src = Image.open(resolve_texture(tex_dir, spec["texture"]))
        else:
            validate_box(spec["box"])
            src = captures[spec["capture"]]
        img = cut_sprite(
            src,
            spec.get("box"),
            alpha_key=spec.get("alpha_key"),
            clear_center=bool(spec.get("clear_center")),
            slice_=spec.get("slice"),
            fill=spec.get("fill"),
            repeat_x=spec.get("repeat_x"),
            repeat_y=spec.get("repeat_y"),
            alpha_poly=spec.get("alpha_poly"),
        )
        img.save(out_dir / f"{name}.png")
        index[name] = {"w": img.width, "h": img.height, "slice": spec.get("slice")}
        print(f"sprite  {name}  {img.width}x{img.height}")
    (out_dir.parent / "sprites.json").write_text(
        json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    return index


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", default=str(HERE / "sprites_manifest.json"))
    p.add_argument("--out", default=str(HERE.parent / "public" / "game" / "sprites"))
    p.add_argument(
        "--sheet",
        nargs="?",
        const=str(HERE.parent / "public" / "game" / "sprites-planche.png"),
        default=None,
        help="écrit une planche de contrôle (x3, damier gris, étiquettes)",
    )
    a = p.parse_args(argv)
    try:
        index = run(Path(a.manifest), Path(a.out))
        if a.sheet:
            print(f"planche  {build_sheet(index, Path(a.out), Path(a.sheet))}")
    except FileNotFoundError as exc:
        print(
            f"Capture introuvable : {exc} (voir refs/ et tools/capture_game.ps1)",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
