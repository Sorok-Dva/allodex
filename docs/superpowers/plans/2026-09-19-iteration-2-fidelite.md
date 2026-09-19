# Itération 2 — fidélité au jeu : Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refaire l'accueil (barre de boutons du jeu) et le panneau Succès pour qu'ils soient identiques au jeu à l'échelle 1:1, à partir des captures live de `refs/` et des textures du client.

**Architecture:** Le pipeline `tools/` gagne un découpeur de sprites (`cut_sprites.py`, boîtes déclarées dans `sprites_manifest.json`, sortie `public/game/sprites/`) et un comparateur (`compare_refs.py`). Le front remplace le panneau de connexion par `GameActionBar`, et reconstruit le panneau Succès autour d'un composant `MedalsWindow` (chrome 9-slice depuis les sprites) avec `GameScrollbar`, `GameDropdown`, `GameTooltip` réutilisables. La logique (navigation repliée, sélection auto, filtre à trois valeurs, chiffres romains, suivi local) reste pure et testée.

**Tech Stack:** inchangé (Vite 8, React 19, TS 6 strict, Vitest 4, Python 3 + Pillow + numpy + pytest, Playwright 1.61 de `~/projects/42portfolio/node_modules/playwright`).

**Spec:** `docs/superpowers/specs/2026-09-19-iteration-2-fidelite-design.md`

## Global Constraints

- Échelle **1:1** : la fenêtre Succès mesure 880×590 px dans le navigateur ; les tailles de sprites sont leurs tailles de découpe, sans redimensionnement (sauf tranches 9-slice étirées).
- Références : `refs/astral.png`, `refs/tooltip.png`, `refs/dropdown.png`, `refs/navscroll.png` (1920×1009, fenêtre Succès entre x 470–1490 et y 180–790). `refs/` et `public/game/` sont git-ignorés ; **aucun sprite ne doit contenir de texte, de HUD ou d'information du personnage**.
- Libellés : « Succès », « points de succès » (collé au nombre : « 24690points de succès »), « Recherche de succès... », « Tout », « Terminé », « Pas terminé », « Série de succès : », « Date : », « Lien vers les succès », « Mon compte — bientôt ».
- Catégories (ordre, 17) : Progression, Personnage, Batailles, Astral, Raids précédents, Zones de l'histoire, Ordre, Raids actuels, Aventures héroïques, Succès rares, Étincelle, Royaume des éléments, Exploration du monde, Parchemins de retour, Allod privé, Événements, Forteresse de guilde.
- Captures du site : `node /home/llyam/projects/42portfolio/node_modules/playwright/cli.js screenshot --viewport-size=1920,1009 …` (et 1280×720 pour l'accueil) avec `npm run dev -- --host 127.0.0.1 &`.
- TS 6 strict, `import type`, CSS Modules ; commits en français ; jamais `public/game/` ni `refs/` dans git.
- Dépôt `/home/llyam/projects/allodex`, branche de travail `iteration-2` créée depuis `main`.

---

## Fichiers

| Fichier | Responsabilité |
|---|---|
| `tools/cut_sprites.py` | Lit `refs/<capture>.png`, découpe les boîtes du manifeste, applique un `alpha_key` optionnel (rend transparent tout pixel hors fenêtre de teinte), écrit `public/game/sprites/<name>.png` + `public/game/sprites.json` (`{name: {w,h,slice?}}`). Refuse toute boîte hors de la fenêtre Succès. |
| `tools/sprites_manifest.json` | Boîtes `[x0,y0,x1,y1]`, capture source, tranches 9-slice, notes. |
| `tools/compare_refs.py` | Juxtapose une capture du site et une référence recadrées sur la fenêtre, écrit un montage PNG + une image de différence + un score (moyenne des diffs). |
| `tools/tests/test_cut_sprites.py`, `tools/tests/test_compare_refs.py` | Tests. |
| `tools/assets_manifest.json` | + préfixes `Interface/Ingame/ContextPinMenu3/textures/`, `Interface/Ingame/ContextActionbar2/`, `Interface/Common/Elements/Editline/`. |
| `src/lib/assets.ts` | + `sprite(name)` → `/game/sprites/<name>.png`, `loadManifest` charge aussi `sprites.json`, `spriteSize(name)`. |
| `src/lib/roman.ts` (+ test) | `toRoman(n)` 1..20. |
| `src/data/medals.types.ts`, `medals.mock.json`, `medals.logic.ts` (+ tests) | Champs `tracked`, `placeholder`, `medalCollection[].icon/rank`, `MedalRank.image` ; libellés du filtre ; `FILTER_LABELS`. |
| `src/components/game/GameTooltip.tsx` (+css) | Infobulle du jeu : cadre sprite, position fixe clampée, contenu enfants. |
| `src/components/game/GameScrollbar.tsx` (+css) | Ascenseur du jeu lié à un conteneur scrollable (flèches, piste, curseur proportionnel, drag). |
| `src/components/game/GameDropdown.tsx` (+css) | Champ + bouton or ; liste déroulée ; options alignées à droite ; fermeture au clic extérieur / Échap. |
| `src/components/game/GameActionBar.tsx` (+css) | Barre de boutons `ContextPinMenu3` avec états et infobulles. |
| `src/screens/OpeningScreen/OpeningScreen.tsx` (+css) | Retrait du panneau ; ajout de la barre. |
| `src/screens/MedalsScreen/MedalsWindow.tsx` (+css) | Chrome : plaque de titre, bandeau, rails, croix, séparateur ; slot nav + slot contenu. |
| `src/screens/MedalsScreen/MedalsNavigation.tsx` (+css) | Pilules, médaillons, sous-liste, recherche, `GameScrollbar`. |
| `src/screens/MedalsScreen/MedalsList.tsx`, `MedalEntry.tsx` (+css) | En-tête + `GameDropdown` ; entrées ; série de succès ; case de suivi ; `GameTooltip`. |
| `src/screens/MedalsScreen/useMedalsState.ts` (+test) | Repliage/dépliage avec sélection auto, `tracked` local, état initial Astral/Astral ouvert. |
| `src/screens/MedalsScreen/MedalsScreen.tsx` | Assemblage. |
| `README.md` | Section itération 2 + capture du jeu. |

---

### Task 1 : Sprites depuis les captures, nouvelles textures, comparateur

**Files:**
- Create: `tools/cut_sprites.py`, `tools/sprites_manifest.json`, `tools/compare_refs.py`, `tools/tests/test_cut_sprites.py`, `tools/tests/test_compare_refs.py`
- Modify: `tools/assets_manifest.json`

**Interfaces:**
- Produces : `public/game/sprites/<name>.png`, `public/game/sprites.json` = `{"<name>": {"w": int, "h": int, "slice": [top,right,bottom,left] | null}}` ; `cut_sprite(img, box, alpha_key=None) -> Image` ; `validate_box(box) -> None` (lève `ValueError` hors fenêtre 470–1490 × 180–790) ; `compare(site_png, ref_png, site_box, ref_box, out_prefix) -> float`.
- Noms de sprites requis (consommés par les tâches 3–5) : `title-plate-left`, `title-plate-mid`, `title-plate-right`, `band-left`, `band-mid`, `band-right`, `rail-top`, `rail-bottom`, `rail-left`, `rail-right`, `corner-tl`, `corner-tr`, `corner-bl`, `corner-br`, `divider-v`, `pill-left`, `pill-mid`, `pill-right`, `medallion-plus`, `medallion-minus`, `search-field` (slice), `content-header` (slice), `dropdown-field` (slice), `dropdown-button`, `dropdown-frame` (slice), `scroll-up`, `scroll-down`, `scroll-track` (slice vertical), `scroll-thumb`, `checkbox-off`, `checkbox-on` (depuis `MsgBoxCheckBox*` textures si l'aspect correspond, sinon découpe), `tooltip-frame` (slice, depuis `refs/tooltip.png`, zone sans texte : prendre les bords et reconstruire par 9-slice), `badge-icon-frame` (cadre or 56×56 autour de l'icône, depuis une entrée), `rank-tag` (petite étiquette du chiffre romain sur l'icône), `series-slot` (cadre 32×32 d'une icône de série).

- [ ] **Step 1 : Nouvelles textures**

Dans `tools/assets_manifest.json`, ajouter aux `texture_prefixes` : `"Interface/Ingame/ContextPinMenu3/textures/"`, `"Interface/Ingame/ContextActionbar2/"`, `"Interface/Common/Elements/Editline/"`. Lancer `python3 tools/extract_assets.py --skip-video` ; vérifier dans `public/game/manifest.json` la présence de `Interface/Ingame/ContextPinMenu3/textures/ButtonMedalsNormal` (46×52) et `ButtonEquipmentNormal` (45×52).

- [ ] **Step 2 : Tests échouants du découpeur**

```python
# tools/tests/test_cut_sprites.py
import json, pytest
from PIL import Image
from tools.cut_sprites import validate_box, cut_sprite, run

def test_validate_box_rejects_outside_medals_window():
    with pytest.raises(ValueError): validate_box([100, 200, 300, 250])
    with pytest.raises(ValueError): validate_box([600, 100, 700, 200])
    validate_box([600, 300, 700, 330])  # ok, ne lève pas

def test_cut_sprite_crops_and_applies_alpha_key():
    img = Image.new("RGB", (40, 40), (10, 200, 10))
    for x in range(10, 30):
        for y in range(10, 30): img.putpixel((x, y), (120, 80, 30))
    out = cut_sprite(img, [5, 5, 35, 35], alpha_key={"rgb": [10, 200, 10], "tol": 20})
    assert out.size == (30, 30) and out.mode == "RGBA"
    assert out.getpixel((0, 0))[3] == 0 and out.getpixel((15, 15))[3] == 255

def test_run_writes_sprites_and_index(tmp_path):
    ref = tmp_path / "astral.png"; Image.new("RGB", (1920, 1009), (0, 0, 0)).save(ref)
    manifest = {"captures": {"astral": str(ref)}, "sprites": {"pill-mid": {"capture": "astral", "box": [600, 300, 640, 328], "slice": None}}}
    mpath = tmp_path / "m.json"; mpath.write_text(json.dumps(manifest))
    out = tmp_path / "sprites"; run(mpath, out)
    assert (out / "pill-mid.png").exists()
    assert json.loads((out.parent / "sprites.json").read_text())["pill-mid"] == {"w": 40, "h": 28, "slice": None}
```

Lancer : `python3 -m pytest tools/tests/test_cut_sprites.py -v` → `ModuleNotFoundError`.

- [ ] **Step 3 : Implémentation `tools/cut_sprites.py`**

```python
#!/usr/bin/env python3
"""Découpe des sprites d'interface dans les captures live du jeu (refs/).

Usage : python3 tools/cut_sprites.py [--manifest tools/sprites_manifest.json] [--out public/game/sprites]
Les boîtes sont en pixels écran (captures 1920x1009). Toute boîte hors de la fenêtre
Succès (x 470-1490, y 180-790) est refusée : on ne découpe jamais le HUD du joueur.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
WINDOW = (470, 180, 1490, 790)

def validate_box(box: list[int]) -> None:
    x0, y0, x1, y1 = box
    if not (WINDOW[0] <= x0 < x1 <= WINDOW[2] and WINDOW[1] <= y0 < y1 <= WINDOW[3]):
        raise ValueError(f"boîte hors de la fenêtre Succès : {box}")

def cut_sprite(img: Image.Image, box: list[int], alpha_key: dict | None = None) -> Image.Image:
    out = img.convert("RGBA").crop(tuple(box))
    if alpha_key:
        a = np.asarray(out).astype(int)
        rgb = np.array(alpha_key["rgb"]); tol = int(alpha_key.get("tol", 12))
        mask = (np.abs(a[:, :, :3] - rgb).max(axis=2) <= tol)
        a[:, :, 3] = np.where(mask, 0, 255)
        out = Image.fromarray(a.astype(np.uint8), "RGBA")
    return out

def run(manifest_path: Path, out_dir: Path) -> dict:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    captures = {k: Image.open(v if Path(v).is_absolute() else HERE.parent / v) for k, v in manifest["captures"].items()}
    out_dir.mkdir(parents=True, exist_ok=True)
    index: dict[str, dict] = {}
    for name, spec in manifest["sprites"].items():
        validate_box(spec["box"])
        img = cut_sprite(captures[spec["capture"]], spec["box"], spec.get("alpha_key"))
        img.save(out_dir / f"{name}.png")
        index[name] = {"w": img.width, "h": img.height, "slice": spec.get("slice")}
        print(f"sprite  {name}  {img.width}x{img.height}")
    (out_dir.parent / "sprites.json").write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")
    return index

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", default=str(HERE / "sprites_manifest.json"))
    p.add_argument("--out", default=str(HERE.parent / "public" / "game" / "sprites"))
    a = p.parse_args(argv)
    try:
        run(Path(a.manifest), Path(a.out))
    except FileNotFoundError as exc:
        print(f"Capture introuvable : {exc} (voir refs/ et tools/capture_game.ps1)", file=sys.stderr); return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4 : Manifeste des sprites**

`tools/sprites_manifest.json` : `captures` = `{"astral": "refs/astral.png", "tooltip": "refs/tooltip.png", "dropdown": "refs/dropdown.png", "navscroll": "refs/navscroll.png"}`. Pour chaque sprite requis (liste dans Interfaces), déterminer la boîte **en mesurant** dans la capture : ouvrir des recadrages agrandis avec l'outil Read (`Image.crop(...).resize(...)`), puis affiner au pixel avec des profils numpy (transitions de couleur sur une ligne/colonne). Points de départ mesurés :

| Sprite | Capture | Boîte de départ | Remarque |
|---|---|---|---|
| `title-plate-left` | astral | `[479, 184, 560, 224]` | ornement gauche ; `title-plate-right` symétrique vers x 1483 ; `title-plate-mid` = tranche 8 px large prise vers x 700 sans texte |
| `band-left` / `band-right` / `band-mid` | astral | y `[226, 259]` ; gauche x 522→600 (volute), droite x 1320→1402, milieu tranche 8 px vers x 700 | éviter le texte « points de succès » (x ≈ 860–1090) |
| `rail-left` / `rail-right` | astral | x 522→540 / 1385→1402, y tranche 8 px vers 450 | |
| `rail-bottom` | astral | y 760→776, tranche 8 px vers x 700 | `rail-top` = juste sous le bandeau si distinct, sinon 1 px transparent |
| `corner-*` | astral | 18×18 aux 4 coins des rails | |
| `divider-v` | astral | x ≈ 806→820, tranche 8 px de haut vers y 450 | |
| `pill-left` / `pill-mid` / `pill-right` | navscroll | pilule « Ordre » (repliée, sans texte à gauche : prendre les 22 px de gauche ornés, 8 px de milieu **hors texte** vers la droite du texte, 34 px de droite **avec** le médaillon exclu) | le médaillon se découpe séparément |
| `medallion-plus` / `medallion-minus` | astral | 18×18 : « + » sur « Personnage », « − » sur « Astral » | `alpha_key` inutile si fond de pilule inclus ; sinon découper serré |
| `search-field` | astral | `[548, 268, 792, 298]` slice `[6,10,6,10]` | contient le texte : prendre plutôt une boîte **sans texte** : les 14 px de gauche + 14 px de droite + 6 px du milieu pris à droite du texte |
| `content-header` | astral | y 262→300, tranche 8 px vers x 1000 (hors titre) slice vertical `[6,0,6,0]` | |
| `dropdown-field` | astral | champ « Tout » : bords gauche/droit hors texte, slice `[4,8,4,8]` | |
| `dropdown-button` | astral | bouton or 22×22 à droite du champ | |
| `dropdown-frame` | dropdown | cadre de la liste déroulée : prendre les 8 px de bord + coins, slice `[8,8,8,8]`, le centre est un aplat sombre | |
| `scroll-up` / `scroll-down` / `scroll-thumb` / `scroll-track` | astral | ascenseur de la colonne contenu (x ≈ 1370→1388) | `scroll-track` = tranche 8 px de haut |
| `checkbox-off` | astral | case de « Parfait ! » (x ≈ 1300→1318, y ≈ 545→563) | `checkbox-on` : dupliquer et dessiner une coche verte `#3fae4a` si aucune référence cochée |
| `tooltip-frame` | tooltip | boîte du cadre entière puis slice `[10,10,10,10]` ; **remplacer l'intérieur** par l'aplat de la couleur de fond (moyenne d'une zone sans texte) pour effacer le texte | |
| `badge-icon-frame` | astral | cadre or autour de l'icône « Connecté avec les étoiles » | icône incluse → mettre l'intérieur en transparent via `alpha_key` impossible (icône variée) : découper les 4 bords (6 px) + slice `[6,6,6,6]` et centre transparent : ajouter au manifeste une clé `"clear_center": true` que `cut_sprite` honore (met alpha 0 à l'intérieur des tranches) |
| `rank-tag` | astral | étiquette du chiffre romain en bas à droite de l'icône (≈ 14×12) sans le chiffre : prendre l'étiquette de « Tissu d'Éther » si vierge, sinon aplat | |
| `series-slot` | astral | cadre 32×32 d'une icône de la série de « Parfait ! », `clear_center` | |

Ajouter à `cut_sprite` la prise en charge de `clear_center` (paramètre `slice`) : alpha 0 pour la zone intérieure `[left, top, w-right, h-bottom]`. Ajouter un test pour `clear_center`.

- [ ] **Step 5 : Découpe et contrôle visuel**

`python3 tools/cut_sprites.py` puis monter une planche de tous les sprites (fond gris, agrandis ×3) et la lire avec l'outil Read. Critères : aucun texte, aucun fragment du HUD, bords nets. Ajuster les boîtes jusqu'à satisfaction. Vérifier que les 9-slice reconstruisent correctement : petit script Pillow qui étire `pill-*` à 240×28 et `title-plate-*` à 1004×40 et sauvegarde le résultat pour lecture.

- [ ] **Step 6 : Comparateur**

```python
# tools/compare_refs.py
"""Juxtapose une capture du site et une référence du jeu, recadrées, et écrit montage + différence.
Usage : python3 tools/compare_refs.py site.png refs/astral.png --site-box x0 y0 x1 y1 --ref-box 470 180 1490 790 --out /tmp/claude-1000/cmp
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
    montage.paste(s, (0, 0)); montage.paste(r, (r.width + 10, 0))
    montage.save(f"{out_prefix}-montage.png"); Image.fromarray(diff).save(f"{out_prefix}-diff.png")
    score = float(diff.mean()); print(f"score {score:.2f} (0 = identique)"); return score

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("site"); p.add_argument("ref")
    p.add_argument("--site-box", nargs=4, type=int, required=True); p.add_argument("--ref-box", nargs=4, type=int, default=[470, 180, 1490, 790])
    p.add_argument("--out", required=True)
    a = p.parse_args(argv); compare(a.site, a.ref, a.site_box, a.ref_box, a.out); return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

Test `tools/tests/test_compare_refs.py` : deux images synthétiques identiques → score 0.0 et fichiers écrits ; une image décalée → score > 0.

- [ ] **Step 7 : Suite complète, commit**

`python3 -m pytest tools/tests -q` → PASS. Commit : `feat(tools): découpe de sprites depuis les captures du jeu, comparateur de références, textures de la barre`.

---

### Task 2 : Données et logique

**Files:**
- Create: `src/lib/roman.ts`, `src/lib/roman.test.ts`
- Modify: `src/data/medals.types.ts`, `src/data/medals.mock.json`, `src/data/medals.logic.ts`, `src/data/medals.logic.test.ts`

**Interfaces:**
- `toRoman(n: number): string` (1..20 ; 0 ou > 20 → `String(n)`).
- Types : `Medal.tracked?: boolean`, `Medal.placeholder?: boolean`, `MedalRank.image?: string`, `medalCollection?: { medalId: string; success: boolean; icon: string; rank: number }[]`, `finishDate?: string` (ISO date ou date-heure).
- `FILTER_LABELS: Record<MedalFilter, string>` = `{ all: 'Tout', completed: 'Terminé', inProgress: 'Pas terminé' }`.
- `formatGameDateTime(iso)` → `'HH:MM JJ.MM.AAAA'` si heure présente, sinon `'JJ.MM.AAAA'` (déplacer `formatGameDate` de `screens/MedalsScreen/formatDate.ts` vers `src/lib/dates.ts` et y ajouter la variante ; mettre à jour l'import).
- `parseDataset` accepte les nouveaux champs optionnels ; `medalCollection[].rank` entier ≥ 1.

- [ ] **Step 1 : Tests échouants** (`roman.test.ts` : 1→I, 4→IV, 6→VI, 9→IX, 14→XIV, 20→XX, 0→'0' ; `medals.logic.test.ts` : `FILTER_LABELS`, `parseDataset` accepte `tracked`/`placeholder`/`medalCollection` enrichi et rejette `rank: 0` ; `dates.test.ts` : `formatGameDateTime('2026-08-29T20:54')` → `'20:54 29.08.2026'`, `formatGameDateTime('2026-05-25')` → `'25.05.2026'`).
- [ ] **Step 2 : Implémentations** (`toRoman` par table `[[10,'X'],[9,'IX'],[5,'V'],[4,'IV'],[1,'I']]`).
- [ ] **Step 3 : Mock.** 17 catégories dans l'ordre ; sous-catégories : Personnage (Équipement, Professions, Divers, Long service), Astral (Astral ouvert, Allods Astraux), Batailles (Escarmouches, Domination), autres « Général ». Conserver les 20 succès existants (réaffecter `categoryIndex` selon le nouvel ordre !). Ajouter dans Astral / Astral ouvert (29 succès, 5 terminés) : « Connecté avec les étoiles » (20 pts, `completeProgress` 5, `progress.value` 5, `finishDate` `2026-08-29T20:54`, icône `Interface/Icons/Special/VeteranRewards/VeteranRankMaster` faute de mieux, `currentRank` 1 avec `ranks[0].image` identique), « Propriétaire » (30 pts, 10/10, `2026-05-25`), « Parfait ! » (10 pts, non terminé, `medalCollection` de 6 éléments `rank` 1..6, `success` false, `icon` `Interface/Icons/Misc/Event/GoldMedal`), « Tissu d'Éther » (10 pts, non terminé, sans barre), 3 autres terminés et 22 non terminés `placeholder: true` nommés d'après des lignes réelles des textes FR si disponibles (`/tmp/claude-1000/…/scratchpad/texts_fr.txt`, chercher « Astral », « Allod », « Éther ») sinon « Succès astral n° k ». Astral / Allods Astraux : 15 succès tous terminés (`placeholder: true`, dates 2025–2026). `totalScore` 24690 inchangé.
- [ ] **Step 4 : Tests du mock** : `subCategoryCounts(ds, 3, 0)` → `{done: 5, total: 29}`, `(ds, 3, 1)` → `{done: 15, total: 15}`, `ds.categories.length === 17`, `ds.categories[16].name === 'Forteresse de guilde'`, `parseDataset(mock)` ok.
- [ ] **Step 5 : `npm test` PASS, commit** `feat(data): 17 catégories du jeu, succès Astral de la capture, séries, suivi, libellés du filtre`.

---

### Task 3 : Accueil avec la barre de boutons du jeu

**Files:**
- Create: `src/components/game/GameTooltip.tsx`, `GameTooltip.module.css`, `src/components/game/GameActionBar.tsx`, `GameActionBar.module.css`
- Modify: `src/lib/assets.ts` (+ `sprite`, `spriteSize`, chargement `sprites.json`), `src/lib/assets.test.ts`, `src/screens/OpeningScreen/OpeningScreen.tsx`, `OpeningScreen.module.css`

**Interfaces:**
- `sprite(name)` → `/game/sprites/${name}.png` ; `spriteSize(name)` → `{w,h,slice}|undefined`.
- `<GameTooltip anchor={DOMRect|null} title? children />` : cadre `tooltip-frame` en 9-slice, `position: fixed`, sous l'ancre, clampé à la fenêtre, `pointer-events: none`.
- `<GameActionBar items={[{ id, base: 'Interface/Ingame/ContextPinMenu3/textures/ButtonMedals', label: 'Succès', onClick }, { id, base: '...ButtonEquipment', label: 'Personnage', hint: 'Mon compte — bientôt' }]} />` : boutons à leur taille native (44–46 × 52), états Normal/Highlight/Pressed (nommage `…Normal` / `…Highlight` / `…Pressed` — pas `Highlighted`), infobulle `GameTooltip` au survol avec `label` et `hint`.

- [ ] **Step 1 : Test échouant** `assets.test.ts` : `sprite('pill-mid')` → `/game/sprites/pill-mid.png`.
- [ ] **Step 2 : `assets.ts`** : `loadManifest` fait les deux `fetch` en parallèle (`Promise.all`), tolérants aux échecs.
- [ ] **Step 3 : Composants** `GameTooltip` et `GameActionBar` (réutiliser la logique d'états de `GameButton` avec un prop `stateNames={{ hover: 'Highlight', pressed: 'Pressed' }}` — étendre `GameButton` si plus simple).
- [ ] **Step 4 : `OpeningScreen`** : supprimer `.loginPanel`, `.title`, `.searchRow`, `.field`, `.input`, `.roundRow` et le state `query` ; ajouter `<GameActionBar>` positionné `right: 24px; bottom: 72px` (au-dessus de la bande basse), fond `rgba(10,18,10,0.55)` avec bordure 1 px `#6c8a5a` et coins arrondis 6 px, padding 6 px 10 px. Le bouton Succès → `navigate('/succes')`. Conserver intro/skipIntro/bande basse.
- [ ] **Step 5 : Captures** 1280×720 `?skipIntro` ; lire ; comparer visuellement la barre à `refs/actionbar_user.png` (taille des icônes 1:1, espacement ≈ 4 px).
- [ ] **Step 6 : `npm test && npm run build`, commit** `feat(opening): barre de boutons du jeu (Succès, Personnage), retrait du panneau de connexion`.

---

### Task 4 : Chrome de la fenêtre et navigation à l'identique

**Files:**
- Create: `src/screens/MedalsScreen/MedalsWindow.tsx`, `MedalsWindow.module.css`, `src/components/game/GameScrollbar.tsx`, `GameScrollbar.module.css`, `src/components/game/GameScrollbar.test.tsx`
- Modify: `src/screens/MedalsScreen/MedalsScreen.tsx`, `MedalsScreen.module.css`, `MedalsNavigation.tsx`, `MedalsNavigation.module.css`, `useMedalsState.ts`, `useMedalsState.test.ts`

**Interfaces:**
- `<MedalsWindow title="Succès" points={n} onClose nav={ReactNode} content={ReactNode} />` : 880×590, plaque de titre débordante (1004 px de large, centrée), bandeau, rails, croix, séparateur ; grille interne : nav 260 px, séparateur 14 px, contenu reste.
- `<GameScrollbar targetRef={RefObject<HTMLElement>} />` : lit `scrollTop/scrollHeight/clientHeight` du conteneur (écoute `scroll` et `ResizeObserver`), rend flèche haut, piste, curseur (hauteur proportionnelle, min 18 px), flèche bas ; clic flèches → ±40 px ; drag du curseur ; masque le curseur si rien à défiler.
- `useMedalsState` : `openCategory` initial = index d'« Astral », `selected` initial = Astral / Astral ouvert ; `toggleCategory(c)` déplie et **sélectionne la première sous-catégorie** de `c` (et replie l'autre) ; replier remet `selected` à `null` et le contenu vide ; `setTracked(medalId, boolean)` stocké dans un `Map` local ; `visible` tient compte de `tracked`.
- Pilule : sprites `pill-left/mid/right` en 3 tranches horizontales (largeur 240, hauteur 28), texte `AllodsWest` 15 px couleur `#e6efe0` avec ombre ; médaillon `medallion-plus/minus` 18×18 à droite (aucun pour « Progression ») ; survol : `filter: brightness(1.12)`.

- [ ] **Step 1 : Tests échouants** `useMedalsState.test.ts` : état initial (Astral déplié, Astral ouvert sélectionné) ; `toggleCategory(1)` → `openCategory === 1`, `selected === {1,0}` ; `toggleCategory(1)` de nouveau → `openCategory === null`, `selected === null` ; `setTracked`. `GameScrollbar.test.tsx` (Testing Library, jsdom) : rend un conteneur de 100 px avec contenu 400 px (`Object.defineProperty` sur `scrollHeight`/`clientHeight`), vérifie que le curseur a une hauteur ≈ 25 % de la piste et que le clic sur « bas » incrémente `scrollTop` de 40.
- [ ] **Step 2 : Implémentations.** Mesurer dans `refs/astral.png` les positions exactes : plaque (y 184→224), bandeau (226→259), champ de recherche (268→298), première pilule (y 305), pas 30, largeur 240 ; colonne contenu x 820→1385 ; reporter en CSS relatif à l'origine de la fenêtre (x 522, y 188).
- [ ] **Step 3 : Assemblage** `MedalsScreen` avec `MedalsWindow`, `MedalsNavigation` réécrite, `MedalsList` existant (provisoire jusqu'à la tâche 5).
- [ ] **Step 4 : Capture 1920×1009 + comparaison** : `python3 tools/compare_refs.py /tmp/claude-1000/it2-nav.png refs/astral.png --site-box <x0 y0 x1 y1 de la fenêtre dans la capture, à calculer : fenêtre centrée → x0 = (1920-1004)/2 pour la plaque> --out /tmp/claude-1000/cmp-nav`. Lire le montage ; corriger jusqu'à alignement des pilules et du bandeau à ±3 px.
- [ ] **Step 5 : `npm test && npm run build`, commit** `feat(medals): chrome de fenêtre et navigation reconstruits d'après les captures du jeu`.

---

### Task 5 : Contenu à l'identique — en-tête, menu, entrées, série, suivi, infobulle

**Files:**
- Create: `src/components/game/GameDropdown.tsx`, `GameDropdown.module.css`, `GameDropdown.test.tsx`
- Modify: `src/screens/MedalsScreen/MedalsList.tsx`, `MedalsList.module.css`, `MedalEntry.tsx`, `MedalEntry.module.css`, `src/components/game/MedalBadge.tsx`, `MedalBadge.module.css`

**Interfaces:**
- `<GameDropdown value options={{value,label}[]} onChange width={120} />` : champ `dropdown-field` + bouton `dropdown-button` ; liste `dropdown-frame` sous le champ, options alignées à droite, 15 px, couleur `#e6efe0`, survol doré ; fermeture clic extérieur/Échap ; `role="listbox"`.
- `MedalBadge` : icône 48×48 dans `badge-icon-frame` (56×56), `rank-tag` + `toRoman(currentRank)` en bas à droite de l'icône (si `currentRank ≥ 1`), écu (`MedalFrame*`) avec score sous l'icône ; hauteur totale ≈ 96 px.
- Entrée : hauteur 100 px, pas 111 px (marge 11) ; parchemin `MedalPaperComplete` si terminé sinon `MedalPaper` ; en-tête nom (`#6b3f0a`, 17 px) à gauche / date (`formatGameDate`) ou `checkbox-*` à droite ; description centrée 15.5 px `#2c2413` ; barre si `completeProgress > 1` ; « Série de succès : » puis rangée de `series-slot` 32×32 avec icône et `toRoman(rank)` en bas à droite, icône assombrie (`filter: brightness(0.45) grayscale(0.4)`) si `!success`.
- Infobulle `GameTooltip` au survol du badge ou du nom : titre `#7ad66b` 16 px, « Date : HH:MM JJ.MM.AAAA » si terminé (`#d9c98a`), description `#e6efe0`, séparateur 1 px `#4b6b45`, ligne « Shift + clic : Lien vers les succès » (`#b9c9b4`, 13 px).

- [ ] **Step 1 : Test échouant** `GameDropdown.test.tsx` : rend 3 options, ouvre au clic, sélectionne « Pas terminé » → `onChange('inProgress')` et fermeture ; Échap ferme.
- [ ] **Step 2 : Implémentations** ; supprimer le `<select>` et les règles CSS associées.
- [ ] **Step 3 : Captures 1920×1009** : `/succes` (défaut), survol du premier succès (script Node Playwright : `page.hover('article:first-of-type h3')`), menu ouvert (`page.click('[role=combobox]')`). Comparer avec `compare_refs.py` à `refs/astral.png`, `refs/tooltip.png`, `refs/dropdown.png` ; lire les montages ; ajuster jusqu'à ±3 px sur la géométrie et mêmes textes aux mêmes places.
- [ ] **Step 4 : `npm test && npm run build`, commit** `feat(medals): entrées, série de succès, suivi, menu et infobulle identiques au jeu`.

---

### Task 6 : Vérification finale et documentation

**Files:**
- Modify: `README.md`, `docs/superpowers/specs/2026-09-19-iteration-2-fidelite-design.md` (écarts constatés, s'il y en a)

- [ ] **Step 1 :** captures finales : accueil 1280×720 (`?skipIntro`), panneau 1920×1009 et 1280×720 (vérifier que la fenêtre 880×590 tient et reste centrée) ; montages `compare_refs` pour les trois états ; lecture et liste des écarts résiduels avec leur cause.
- [ ] **Step 2 :** mode sans assets (déplacer `public/game`, capturer `/succes`, restaurer) : bandeau rouge, aucune exception.
- [ ] **Step 3 :** gates : `npm test && npm run build && python3 -m pytest tools/tests -q` ; `git status --short` sans `public/game` ni `refs`.
- [ ] **Step 4 :** README : section « Itération 2 » (barre de boutons, panneau 1:1, sprites découpés depuis les captures — jamais versionnés — comment recapturer avec `tools/capture_game.ps1` puis `python3 tools/cut_sprites.py`), et note que la vue Progression est prévue ensuite.
- [ ] **Step 5 :** commit `docs: itération 2 — vérification, README`.

---

## Auto-revue

- Couverture spec : §5 assets → T1 ; §6 accueil → T3 ; §7.1 chrome, §7.2 nav → T4 ; §7.3 contenu → T5 ; §7.4 données → T2 ; §8 vérification → T4/T5/T6.
- Noms partagés : `sprite`, `spriteSize` (T3) utilisés en T4/T5 ; `GameTooltip` (T3) en T5 ; `toRoman`, `FILTER_LABELS`, `formatGameDateTime` (T2) en T5 ; `useMedalsState.setTracked`/`selected: null` (T4) en T5 ; noms de sprites (T1) en T4/T5.
- Placeholders : les boîtes de sprites sont des points de départ mesurés avec méthode de mesure et critère d'acceptation explicites ; pas de TBD.
