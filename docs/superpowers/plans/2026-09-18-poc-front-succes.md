# POC front Succès Allods — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un site Vite + React qui rejoue l'écran d'ouverture d'Allods Online (intro, menu vidéo, panneau de connexion devenu menu) puis affiche un panneau Succès identique à celui du jeu, à partir d'assets extraits du client FR et de données mockées.

**Architecture:** Un pipeline Python (`tools/`) lit les `.pak` (ZIP) du client, décode les textures `UITexture` (zlib + DXT) en PNG et transcode les vidéos Theora en WebM/MP4 dans `public/game/` (non versionné). Le front React consomme ces assets via un helper unique et un modèle de données calqué sur l'API Lua `medalsLib`, de sorte que l'import d'un dump d'addon soit plus tard une simple désérialisation.

**Tech Stack:** Python 3.10+, Pillow, numpy, pytest, ffmpeg (libvpx-vp9, libx264) ; Node 20, Vite 5, React 18, TypeScript 5, Vitest ; CSS modules ; pas de backend.

**Spec:** `docs/superpowers/specs/2026-09-18-poc-front-succes-design.md`

## Global Constraints

- Client FR de référence : `/mnt/h/MyGames/Allods Online FR (FR)` (version 16.0.01.78). Chemin surchargeable par `--client` ou `ALLODS_CLIENT_DIR`.
- `public/game/` est **toujours** ignoré par git. Seuls les scripts et le manifest sont versionnés.
- Cible desktop 1280×720 minimum ; pas de responsive mobile.
- Le modèle de données reprend les noms de champs de `medalsLib` (`categoryIndex`, `subCategoryIndex`, `completeProgress`, `dressCollection`, `medalCollection`, `finishDate`).
- Textes UI en français, repris du jeu : « Succès », « points de succès », « Recherche de succès... », « Tout », « Terminés », « En cours », « X sur Y ».
- Couleurs du jeu : vert foncé texte `#122c14`, contour clair `#658e7c`, vert libellé recherche `#618b5e`, or titres `#e8c877`, vert coche `#3fae4a`.
- Commits fréquents, messages en français, suffixe `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Le dépôt est `/home/llyam/projects/allods-medals`, branche `main`. Toutes les commandes s'exécutent depuis cette racine.

---

## Fichiers du projet

| Fichier | Responsabilité |
|---|---|
| `tools/uitexture.py` | Décodage d'un `.(UITexture).bin` en image PIL : zlib, en-tête, inférence dimensions/format, en-tête DDS synthétique. |
| `tools/extract_assets.py` | CLI : ouvre les `.pak`, applique `assets_manifest.json`, écrit PNG/curseurs/vidéos et `public/game/manifest.json`. |
| `tools/assets_manifest.json` | Liste blanche des chemins à extraire (préfixes de dossiers et fichiers), exceptions de dimensions, vidéos. |
| `tools/tests/test_uitexture.py` | Tests unitaires du décodeur avec fixtures synthétiques. |
| `tools/requirements.txt` | `Pillow`, `numpy`, `pytest`. |
| `src/data/medals.types.ts` | Types `Medal`, `MedalRank`, `MedalCategory`, `MedalsDataset`. |
| `src/data/medals.mock.json` | Jeu de données (~20 succès). |
| `src/data/medals.logic.ts` | Fonctions pures : `parseDataset`, `subCategoryCounts`, `filterMedals`, `frameForScore`, `searchMedals`, `isComplete`. |
| `src/data/medals.logic.test.ts` | Tests Vitest de la logique. |
| `src/lib/assets.ts` | `tex(path)`, `video(name)`, `cursor(name)`, lecture de `manifest.json`, fallback. |
| `src/lib/router.tsx` | Routeur maison : `useRoute()`, `navigate()`, composant `Link`. |
| `src/styles/global.css` | Reset, police, curseur, variables de couleur. |
| `src/components/game/GameFrame.tsx` + `.module.css` | Cadre 9 tranches à partir d'une texture. |
| `src/components/game/GameButton.tsx` + `.module.css` | Bouton à 4 états (normal/highlight/pressed/disabled) à partir d'un préfixe de texture. |
| `src/components/game/ProgressBar.tsx` + `.module.css` | Barre `ProgressBar` + `ProgressBarGauge`. |
| `src/components/game/MedalBadge.tsx` + `.module.css` | Médaillon : cadre selon score, icône, chiffre. |
| `src/screens/OpeningScreen/OpeningScreen.tsx` + `.module.css` | Intro → menu, panneau de connexion en menu. |
| `src/screens/OpeningScreen/useIntroState.ts` | Machine d'états `intro` / `menu` + `localStorage`. |
| `src/screens/MedalsScreen/MedalsScreen.tsx` + `.module.css` | Fenêtre, en-tête, agencement deux colonnes. |
| `src/screens/MedalsScreen/MedalsNavigation.tsx` + `.module.css` | Colonne gauche : recherche, catégories, sous-catégories. |
| `src/screens/MedalsScreen/MedalEntry.tsx` + `.module.css` | Une entrée de succès (parchemin, badge, barre, checklist, tooltip). |
| `src/screens/MedalsScreen/MedalsList.tsx` + `.module.css` | En-tête de sous-catégorie, filtre, liste scrollable. |
| `src/App.tsx`, `src/main.tsx` | Montage, routes. |
| `README.md` | Installation, extraction, lancement. |

---

### Task 1 : Scaffold Vite + React + TypeScript + Vitest

**Files:**
- Create: `package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`, `src/main.tsx`, `src/App.tsx`, `src/styles/global.css`, `README.md`
- Existant : `public/fonts/allods.ttf` (police « AllodsWest » du jeu, copiée depuis `~/projects/adc-launcher-public/public/fonts/allods.ttf` ; versionnée, contrairement à `public/game/`)
- Modify: `.gitignore`

**Interfaces:**
- Produces : `npm run dev`, `npm run build`, `npm test` (Vitest), alias `@/` → `src/`.

- [ ] **Step 1 : Générer le squelette**

```bash
cd /home/llyam/projects/allods-medals
npm create vite@latest . -- --template react-ts
npm install
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

Si `npm create vite` refuse le dossier non vide, répondre « Ignore files and continue ».

- [ ] **Step 2 : Configurer Vite et Vitest**

`vite.config.ts` :

```ts
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
  server: { port: 5173 },
  test: { environment: 'jsdom', globals: true, setupFiles: [] },
});
```

Dans `tsconfig.json`, section `compilerOptions`, ajouter :

```json
"baseUrl": ".",
"paths": { "@/*": ["src/*"] },
"types": ["vitest/globals"]
```

Dans `package.json`, `scripts` :

```json
"dev": "vite",
"build": "tsc -b && vite build",
"preview": "vite preview",
"test": "vitest run",
"test:watch": "vitest",
"extract": "python3 tools/extract_assets.py"
```

- [ ] **Step 3 : Nettoyer le squelette**

Supprimer `src/App.css`, `src/index.css`, `src/assets/react.svg`, `public/vite.svg`. Écrire :

`src/styles/global.css` :

```css
@font-face {
  font-family: 'AllodsWest';
  src: url('/fonts/allods.ttf') format('truetype');
  font-weight: 400 700;
  font-display: swap;
}

:root {
  --ink: #122c14;
  --ink-outline: #658e7c;
  --search-green: #618b5e;
  --gold: #e8c877;
  --gold-dark: #b9923f;
  --check-green: #3fae4a;
  --paper: #e9dcbf;
  --font-serif: 'AllodsWest', Georgia, serif;   /* police du jeu, fournie par le launcher ADC */
  --font-caps: 'AllodsWest', Georgia, serif;
}

*, *::before, *::after { box-sizing: border-box; }
html, body, #root { margin: 0; height: 100%; }
body {
  background: #000;
  color: var(--ink);
  font-family: var(--font-serif);
  font-size: 16px;
  overflow: hidden;
  user-select: none;
}
button { font: inherit; color: inherit; background: none; border: 0; padding: 0; cursor: inherit; }
```

`src/main.tsx` :

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './styles/global.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><App /></React.StrictMode>,
);
```

`src/App.tsx` (provisoire, remplacé en Task 5) :

```tsx
export default function App() {
  return <main style={{ color: 'white', padding: 24 }}>allods-medals</main>;
}
```

`index.html` : titre `Allods — Succès`, `<html lang="fr">`.

- [ ] **Step 4 : README**

```markdown
# allods-medals

Site fan Allods Online. POC : écran d'ouverture du jeu + panneau Succès, rendus avec les assets du client.

## Prérequis
- Node 20+, Python 3.10+, ffmpeg (avec libvpx-vp9 et libx264)
- Client Allods Online FR installé (par défaut `/mnt/h/MyGames/Allods Online FR (FR)`)

## Installation
    npm install
    pip install -r tools/requirements.txt
    npm run extract -- --client "/mnt/h/MyGames/Allods Online FR (FR)"   # écrit public/game/
    npm run dev

## Tests
    npm test
    python3 -m pytest tools/tests

Les assets extraits appartiennent à My.Games et ne sont pas versionnés.
```

- [ ] **Step 5 : Vérifier**

```bash
npm run build && npm test
```

Attendu : build OK, Vitest « No test files found » sans erreur (code 0 grâce à `passWithNoTests` : ajouter `"passWithNoTests": true` dans `test` de `vite.config.ts` si Vitest sort en erreur).

- [ ] **Step 6 : Commit**

```bash
git add -A
git commit -m "chore: scaffold Vite + React + TS + Vitest

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2 : Décodeur `UITexture` (Python, TDD)

**Files:**
- Create: `tools/uitexture.py`, `tools/tests/test_uitexture.py`, `tools/tests/__init__.py`, `tools/requirements.txt`

**Interfaces:**
- Produces :
  - `decode_uitexture(data: bytes, dims_hint: tuple[int,int] | None = None) -> tuple[PIL.Image.Image, DecodeInfo]` où `DecodeInfo = dataclass(width: int, height: int, fourcc: str)`.
  - `candidate_dims(n_blocks: int, max_ratio: int = 16) -> list[tuple[int,int]]`.
  - `row_smoothness(img: PIL.Image.Image) -> float`.
  - `build_dds(width, height, fourcc: bytes, payload: bytes) -> bytes`.

- [ ] **Step 1 : requirements**

`tools/requirements.txt` :

```
Pillow>=10
numpy>=1.24
pytest>=7
```

Puis `pip install -r tools/requirements.txt` (Pillow 11.2 et numpy sont déjà présents sur la machine ; pytest 6.2.5 existe, la contrainte `>=7` peut être abaissée à `>=6` si l'installation pose problème).

- [ ] **Step 2 : Test échouant — candidate_dims et build_dds**

`tools/tests/test_uitexture.py` :

```python
import io, struct, zlib
from PIL import Image
import pytest

from tools.uitexture import candidate_dims, build_dds, decode_uitexture, row_smoothness


def test_candidate_dims_lists_power_of_two_pairs():
    # 2048 blocs DXT5 → 32768 px : 256x128, 128x256, 512x64...
    dims = candidate_dims(2048)
    assert (256, 128) in dims and (128, 256) in dims
    assert all((w // 4) * (h // 4) == 2048 for w, h in dims)
    assert (2048, 16) not in candidate_dims(2048, max_ratio=16)  # ratio 128 exclu


def test_build_dds_header_is_128_bytes_plus_payload():
    payload = b"\0" * 16
    dds = build_dds(4, 4, b"DXT5", payload)
    assert dds[:4] == b"DDS " and len(dds) == 128 + 16
    height, width = struct.unpack("<II", dds[12:20])
    assert (width, height) == (4, 4)
```

- [ ] **Step 3 : Lancer, vérifier l'échec**

```bash
cd /home/llyam/projects/allods-medals && python3 -m pytest tools/tests -v
```

Attendu : `ModuleNotFoundError: No module named 'tools.uitexture'`. Créer `tools/__init__.py` vide et `tools/tests/__init__.py` vide.

- [ ] **Step 4 : Implémentation minimale**

`tools/uitexture.py` :

```python
"""Décodage des textures UI d'Allods Online : *.(UITexture).bin.

Format : zlib( u32 zéro + u32 taille_payload + payload DXT1/DXT5 ).
Les dimensions ne sont pas stockées ; on les infère parmi les puissances de deux
en choisissant le décodage dont les lignes consécutives se ressemblent le plus.
"""
from __future__ import annotations

import io
import struct
import zlib
from dataclasses import dataclass

import numpy as np
from PIL import Image

BLOCK_BYTES = {b"DXT1": 8, b"DXT5": 16}


@dataclass(frozen=True)
class DecodeInfo:
    width: int
    height: int
    fourcc: str


def candidate_dims(n_blocks: int, max_ratio: int = 16) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    bw = 1
    while bw <= n_blocks:
        if n_blocks % bw == 0:
            bh = n_blocks // bw
            w, h = bw * 4, bh * 4
            if max(w, h) / min(w, h) <= max_ratio:
                out.append((w, h))
        bw *= 2
    return out


def build_dds(width: int, height: int, fourcc: bytes, payload: bytes) -> bytes:
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000  # caps|height|width|pixelformat|linearsize
    pixel_format = struct.pack("<II4s5I", 32, 0x4, fourcc, 0, 0, 0, 0, 0)
    header = struct.pack("<7I", 124, flags, height, width, len(payload), 0, 0)
    header += b"\0" * 44 + pixel_format + struct.pack("<5I", 0x1000, 0, 0, 0, 0)
    return b"DDS " + header + payload


def row_smoothness(img: Image.Image) -> float:
    a = np.asarray(img.convert("L"), dtype=np.float32)
    if a.shape[0] < 2:
        return float("inf")
    return float(np.abs(np.diff(a, axis=0)).mean())


def _try_decode(width: int, height: int, fourcc: bytes, payload: bytes) -> Image.Image | None:
    try:
        img = Image.open(io.BytesIO(build_dds(width, height, fourcc, payload)))
        img.load()
        return img.convert("RGBA")
    except Exception:  # Pillow lève diverses erreurs sur un DDS incohérent
        return None


def decode_uitexture(data: bytes, dims_hint: tuple[int, int] | None = None) -> tuple[Image.Image, DecodeInfo]:
    raw = zlib.decompress(data)
    _zero, size = struct.unpack("<II", raw[:8])
    payload = raw[8:8 + size]
    if len(payload) != size:
        raise ValueError(f"payload tronqué : {len(payload)} != {size}")

    best: tuple[float, Image.Image, DecodeInfo] | None = None
    for fourcc, block_bytes in BLOCK_BYTES.items():
        if size % block_bytes:
            continue
        n_blocks = size // block_bytes
        dims = [dims_hint] if dims_hint else candidate_dims(n_blocks)
        for w, h in dims:
            if (w // 4) * (h // 4) != n_blocks:
                continue
            img = _try_decode(w, h, fourcc, payload)
            if img is None:
                continue
            score = row_smoothness(img)
            if best is None or score < best[0]:
                best = (score, img, DecodeInfo(w, h, fourcc.decode()))
    if best is None:
        raise ValueError("aucun décodage DXT possible")
    return best[1], best[2]
```

- [ ] **Step 5 : Lancer, vérifier le succès**

```bash
python3 -m pytest tools/tests -v
```

Attendu : 2 PASS.

- [ ] **Step 6 : Test échouant — décodage bout en bout avec une fixture synthétique**

Ajouter dans `tools/tests/test_uitexture.py` :

```python
def _dxt1_solid_block(r: int, g: int, b: int) -> bytes:
    c = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    return struct.pack("<HHI", c, c, 0)  # deux couleurs identiques, indices 0


def _make_uitexture(width: int, height: int, blocks: bytes) -> bytes:
    return zlib.compress(struct.pack("<II", 0, len(blocks)) + blocks)


def test_decode_solid_dxt1_texture_with_hint():
    blocks = _dxt1_solid_block(255, 0, 0) * (4 * 2)  # 16x8
    img, info = decode_uitexture(_make_uitexture(16, 8, blocks), dims_hint=(16, 8))
    assert (info.width, info.height, info.fourcc) == (16, 8, "DXT1")
    assert img.getpixel((0, 0))[:3] == (255, 0, 0)


def test_decode_infers_dims_from_gradient():
    # Dégradé horizontal 64x16 en DXT1 : la bonne largeur donne des lignes identiques.
    blocks = b"".join(_dxt1_solid_block(x * 16, 0, 0) for _y in range(4) for x in range(16))
    img, info = decode_uitexture(_make_uitexture(64, 16, blocks))
    assert (info.width, info.height) == (64, 16)
    assert row_smoothness(img) == 0.0
```

- [ ] **Step 7 : Lancer**

```bash
python3 -m pytest tools/tests -v
```

Attendu : 4 PASS (l'implémentation couvre déjà ces cas ; si `test_decode_infers_dims_from_gradient` échoue parce qu'un autre couple obtient aussi 0.0, resserrer le test en vérifiant `img.getpixel((63, 0))[:3][0] > 200`).

- [ ] **Step 8 : Test d'intégration optionnel sur le vrai client**

Ajouter :

```python
import os, zipfile
CLIENT = os.environ.get("ALLODS_CLIENT_DIR", "/mnt/h/MyGames/Allods Online FR (FR)")

@pytest.mark.skipif(not os.path.isdir(CLIENT), reason="client Allods absent")
def test_decode_real_medal_frame():
    pak = zipfile.ZipFile(os.path.join(CLIENT, "data/Packs/Interface.Mini.pak"))
    data = pak.read("Interface/Ingame/Medals/Textures/MedalFrame100.(UITexture).bin")
    img, info = decode_uitexture(data)
    assert (info.width, info.height, info.fourcc) == (128, 256, "DXT5")
    assert img.getpixel((0, 0))[3] == 0  # coin transparent
```

Lancer : `python3 -m pytest tools/tests -v` → 5 PASS.

- [ ] **Step 9 : Commit**

```bash
git add tools
git commit -m "feat(tools): décodeur UITexture (zlib + DXT) avec inférence des dimensions

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3 : Script d'extraction des assets

**Files:**
- Create: `tools/extract_assets.py`, `tools/assets_manifest.json`, `tools/tests/test_extract_assets.py`

**Interfaces:**
- Consumes : `decode_uitexture` (Task 2).
- Produces : `public/game/textures/<chemin>.png` (chemin = entrée du pak sans `.(UITexture).bin`, ex. `Interface/Ingame/Medals/Textures/MedalFrame100.png`), `public/game/cursors/<Nom>.cur`, `public/game/video/{intro,mainmenu}.{webm,mp4}`, `public/game/manifest.json` = `{ "textures": { "<chemin sans extension>": { "w": int, "h": int } } }`.
- Fonctions : `select_entries(names: list[str], manifest: dict) -> list[str]`, `output_path_for(entry: str) -> str`.

- [ ] **Step 1 : Manifest**

`tools/assets_manifest.json` :

```json
{
  "packs": {
    "interface": "data/Packs/Interface.Mini.pak",
    "video": "data/Packs/Video.pak"
  },
  "texture_prefixes": [
    "Interface/Ingame/Medals/Textures/",
    "Interface/Wrap/MainMenu/LoginAccount/",
    "Interface/Wrap/MainMenu/Main2/",
    "Interface/Common/Buttons/Cross/",
    "Interface/Common/Buttons/Menu/",
    "Interface/Common/Buttons/Standard/",
    "Interface/Common/Elements/MsgBox/textures/"
  ],
  "texture_files": [
    "Interface/Icons/Equipment/Helm/LionHelmet.(UITexture).bin",
    "Interface/Icons/Special/VeteranRewards/VeteranRankMaster.(UITexture).bin",
    "Interface/Icons/Misc/Event/GoldMedal.(UITexture).bin",
    "Interface/Icons/Special/Currency/DiamondMedal.(UITexture).bin"
  ],
  "dims_overrides": {
    "Interface/Wrap/MainMenu/LoginAccount/ButtonLoginNormal.(UITexture).bin": [256, 256],
    "Interface/Wrap/MainMenu/LoginAccount/ButtonLoginHighlighted.(UITexture).bin": [256, 256]
  },
  "cursor_prefix": "Interface/System/Cursors/",
  "videos": {
    "intro": "Video/16_0Events/MainMenu/Intro.ogv",
    "mainmenu": "Video/16_0Events/MainMenu/MainMenu.ogv"
  }
}
```

Note : `LionHelmet` est présent dans `Interface.HiRes.pak` en `.(Texture).hi.bin`, format différent. Si l'entrée n'existe pas dans `Interface.Mini.pak` en `(UITexture).bin`, le script doit **avertir et continuer**, pas planter. Vérifier avec `unzip -l ".../Interface.Mini.pak" | grep LionHelmet` ; si absent, remplacer par la première entrée listée sous `Interface/Icons/Equipment/Helm/`.

- [ ] **Step 2 : Test échouant — sélection et chemins**

`tools/tests/test_extract_assets.py` :

```python
from tools.extract_assets import select_entries, output_path_for

MANIFEST = {
    "texture_prefixes": ["Interface/Ingame/Medals/Textures/"],
    "texture_files": ["Interface/Icons/Misc/Event/GoldMedal.(UITexture).bin"],
}


def test_select_entries_keeps_prefix_matches_and_explicit_files():
    names = [
        "Interface/Ingame/Medals/Textures/MedalFrame.(UITexture).bin",
        "Interface/Ingame/Medals/Scripts/ClassMain.luac",
        "Interface/Icons/Misc/Event/GoldMedal.(UITexture).bin",
        "Interface/Icons/Misc/Event/SilverMedal.(UITexture).bin",
    ]
    assert select_entries(names, MANIFEST) == [
        "Interface/Ingame/Medals/Textures/MedalFrame.(UITexture).bin",
        "Interface/Icons/Misc/Event/GoldMedal.(UITexture).bin",
    ]


def test_output_path_strips_type_suffix():
    assert output_path_for("Interface/Ingame/Medals/Textures/Numbers/Num1.(UITexture).bin") == \
        "Interface/Ingame/Medals/Textures/Numbers/Num1"
```

Lancer : `python3 -m pytest tools/tests/test_extract_assets.py -v` → échec `ModuleNotFoundError`.

- [ ] **Step 3 : Implémentation**

`tools/extract_assets.py` :

```python
#!/usr/bin/env python3
"""Extrait les assets nécessaires au site depuis le client Allods Online.

Usage : python3 tools/extract_assets.py [--client DIR] [--out public/game] [--force] [--skip-video]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.uitexture import decode_uitexture  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_CLIENT = os.environ.get("ALLODS_CLIENT_DIR", "/mnt/h/MyGames/Allods Online FR (FR)")
TEXTURE_SUFFIX = ".(UITexture).bin"


def select_entries(names: list[str], manifest: dict) -> list[str]:
    prefixes = tuple(manifest.get("texture_prefixes", []))
    explicit = set(manifest.get("texture_files", []))
    return [n for n in names if n.endswith(TEXTURE_SUFFIX) and (n.startswith(prefixes) or n in explicit)]


def output_path_for(entry: str) -> str:
    return entry[: -len(TEXTURE_SUFFIX)] if entry.endswith(TEXTURE_SUFFIX) else entry


def extract_textures(pak: zipfile.ZipFile, manifest: dict, out: Path, force: bool) -> dict:
    index: dict[str, dict] = {}
    names = pak.namelist()
    entries = select_entries(names, manifest)
    missing = set(manifest.get("texture_files", [])) - set(names)
    for m in sorted(missing):
        print(f"AVERTISSEMENT : introuvable dans le pak : {m}", file=sys.stderr)
    overrides = {k: tuple(v) for k, v in manifest.get("dims_overrides", {}).items()}
    for entry in entries:
        rel = output_path_for(entry)
        target = out / "textures" / f"{rel}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not force:
            from PIL import Image
            with Image.open(target) as im:
                index[rel] = {"w": im.width, "h": im.height}
            continue
        img, info = decode_uitexture(pak.read(entry), overrides.get(entry))
        img.save(target)
        index[rel] = {"w": info.width, "h": info.height}
        print(f"texture  {rel}  {info.width}x{info.height} {info.fourcc}")
    return index


def extract_cursors(pak: zipfile.ZipFile, manifest: dict, out: Path, force: bool) -> None:
    prefix = manifest["cursor_prefix"]
    for entry in pak.namelist():
        if entry.startswith(prefix) and entry.endswith(".cur"):
            target = out / "cursors" / Path(entry).name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and not force:
                continue
            target.write_bytes(pak.read(entry))
            print(f"cursor   {target.name}")


def transcode_videos(pak: zipfile.ZipFile, manifest: dict, out: Path, force: bool) -> None:
    if shutil.which("ffmpeg") is None:
        print("AVERTISSEMENT : ffmpeg absent, vidéos ignorées", file=sys.stderr)
        return
    (out / "video").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for name, entry in manifest["videos"].items():
            webm, mp4 = out / "video" / f"{name}.webm", out / "video" / f"{name}.mp4"
            if webm.exists() and mp4.exists() and not force:
                continue
            src = Path(tmp) / f"{name}.ogv"
            src.write_bytes(pak.read(entry))
            base = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-an"]
            subprocess.run(base + ["-c:v", "libvpx-vp9", "-b:v", "2500k", "-row-mt", "1", str(webm)], check=True)
            subprocess.run(base + ["-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)], check=True)
            print(f"video    {name}.webm / {name}.mp4")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--client", default=DEFAULT_CLIENT)
    p.add_argument("--out", default=str(HERE.parent / "public" / "game"))
    p.add_argument("--force", action="store_true")
    p.add_argument("--skip-video", action="store_true")
    args = p.parse_args(argv)

    client, out = Path(args.client), Path(args.out)
    if not client.is_dir():
        print(f"Client introuvable : {client}", file=sys.stderr)
        return 2
    manifest = json.loads((HERE / "assets_manifest.json").read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(client / manifest["packs"]["interface"]) as pak:
        textures = extract_textures(pak, manifest, out, args.force)
        extract_cursors(pak, manifest, out, args.force)
    if not args.skip_video:
        with zipfile.ZipFile(client / manifest["packs"]["video"]) as pak:
            transcode_videos(pak, manifest, out, args.force)

    (out / "manifest.json").write_text(json.dumps({"textures": textures}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"OK : {len(textures)} textures → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4 : Tests**

```bash
python3 -m pytest tools/tests -v
```

Attendu : tous PASS.

- [ ] **Step 5 : Lancer l'extraction réelle**

```bash
cd /home/llyam/projects/allods-medals && python3 tools/extract_assets.py
ls public/game/textures/Interface/Ingame/Medals/Textures | head; ls public/game/video public/game/cursors | head
python3 -c "import json;m=json.load(open('public/game/manifest.json'));print(len(m['textures']))"
```

Attendu : ~130 textures, 22 curseurs, 4 vidéos (la passe VP9 prend 1 à 3 minutes). Ouvrir deux PNG (par ex. `MedalFrame100.png`, `FrameNavigation.png`) avec l'outil Read pour vérifier visuellement qu'ils ne sont pas striés ; toute texture striée reçoit une entrée dans `dims_overrides` puis `--force`.

- [ ] **Step 6 : Commit**

```bash
git add tools
git commit -m "feat(tools): script d'extraction des assets (textures, curseurs, vidéos, manifest)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4 : Modèle de données, mock et logique pure (TDD Vitest)

**Files:**
- Create: `src/data/medals.types.ts`, `src/data/medals.mock.json`, `src/data/medals.logic.ts`, `src/data/medals.logic.test.ts`

**Interfaces:**
- Produces :
  - types `MedalRank`, `Medal`, `MedalSubCategory`, `MedalCategory`, `MedalsDataset`, `MedalFilter = 'all' | 'completed' | 'inProgress'`.
  - `parseDataset(raw: unknown): MedalsDataset` (lève `Error` avec message explicite).
  - `isComplete(m: Medal): boolean` → `m.currentRank >= m.ranks.length`.
  - `currentRankOf(m: Medal): MedalRank` → palier en cours (ou dernier si terminé).
  - `frameForScore(score: number): 30 | 50 | 100 | 500` → seuil ≤ score parmi {30,50,100,500}, 30 par défaut.
  - `subCategoryCounts(ds, categoryIndex, subCategoryIndex): { done: number; total: number }`.
  - `filterMedals(medals: Medal[], filter: MedalFilter): Medal[]`.
  - `searchMedals(ds: MedalsDataset, query: string): Medal[]` (insensible casse/accents, nom + description).
  - `medalsOf(ds, categoryIndex, subCategoryIndex): Medal[]`.

- [ ] **Step 1 : Types**

`src/data/medals.types.ts` :

```ts
export type MedalRank = {
  completeProgress: number;   // points de progression pour terminer le palier (1 = binaire)
  name: string;
  description: string;
  score: number;              // points de succès gagnés
  reward?: { description: string };
};

export type ConditionItem = { description: string; success: boolean };

export type Medal = {
  id: string;
  name: string;
  description: string;
  icon: string;               // chemin logique de texture (sans extension), ex. "Interface/Icons/Misc/Event/GoldMedal"
  categoryIndex: number;
  subCategoryIndex: number;
  ranks: MedalRank[];         // longueur >= 1
  currentRank: number;        // 0 = aucun palier atteint ; ranks.length = terminé
  progress?: { value: number; title?: string };
  finishDate?: string;        // ISO 8601, présent si terminé
  dressCollection?: (ConditionItem & { slot: string })[];
  medalCollection?: (ConditionItem & { medalId: string })[];
};

export type MedalSubCategory = { name: string };
export type MedalCategory = { name: string; subCategories: MedalSubCategory[] };

export type MedalsDataset = {
  categories: MedalCategory[];
  medals: Medal[];
  totalScore: number;
};

export type MedalFilter = 'all' | 'completed' | 'inProgress';
```

- [ ] **Step 2 : Tests échouants**

`src/data/medals.logic.test.ts` :

```ts
import { describe, it, expect } from 'vitest';
import type { Medal, MedalsDataset } from './medals.types';
import {
  parseDataset, isComplete, currentRankOf, frameForScore,
  subCategoryCounts, filterMedals, searchMedals, medalsOf,
} from './medals.logic';

const rank = (score: number, completeProgress = 1) => ({ completeProgress, name: 'r', description: 'd', score });

const medal = (over: Partial<Medal>): Medal => ({
  id: 'x', name: 'Nom', description: 'Desc', icon: 'i',
  categoryIndex: 0, subCategoryIndex: 0, ranks: [rank(10)], currentRank: 0, ...over,
});

const ds: MedalsDataset = {
  categories: [{ name: 'Personnage', subCategories: [{ name: 'Équipement' }, { name: 'Divers' }] }],
  totalScore: 0,
  medals: [
    medal({ id: 'a', name: 'Paré pour l\'aventure ! (Réveil)', ranks: [rank(10, 21500)], currentRank: 1, finishDate: '2019-01-28' }),
    medal({ id: 'b', name: 'Dragon des temps nouveaux', description: 'Équipez un ensemble complet', ranks: [rank(100)], currentRank: 0 }),
    medal({ id: 'c', name: 'Glaneur', subCategoryIndex: 1, ranks: [rank(10), rank(30)], currentRank: 1 }),
  ],
};

describe('isComplete / currentRankOf', () => {
  it('est terminé quand currentRank atteint le nombre de paliers', () => {
    expect(isComplete(ds.medals[0])).toBe(true);
    expect(isComplete(ds.medals[2])).toBe(false);
  });
  it('renvoie le palier en cours, ou le dernier si terminé', () => {
    expect(currentRankOf(ds.medals[2]).score).toBe(30);
    expect(currentRankOf(ds.medals[0]).score).toBe(10);
  });
});

describe('frameForScore', () => {
  it('choisit le cadre par seuil', () => {
    expect(frameForScore(10)).toBe(30);
    expect(frameForScore(30)).toBe(30);
    expect(frameForScore(75)).toBe(50);
    expect(frameForScore(100)).toBe(100);
    expect(frameForScore(1000)).toBe(500);
  });
});

describe('subCategoryCounts / medalsOf', () => {
  it('compte terminés/total par sous-catégorie', () => {
    expect(subCategoryCounts(ds, 0, 0)).toEqual({ done: 1, total: 2 });
    expect(subCategoryCounts(ds, 0, 1)).toEqual({ done: 0, total: 1 });
    expect(medalsOf(ds, 0, 1).map(m => m.id)).toEqual(['c']);
  });
});

describe('filterMedals', () => {
  it('filtre Tout / Terminés / En cours', () => {
    expect(filterMedals(ds.medals, 'all')).toHaveLength(3);
    expect(filterMedals(ds.medals, 'completed').map(m => m.id)).toEqual(['a']);
    expect(filterMedals(ds.medals, 'inProgress').map(m => m.id)).toEqual(['b', 'c']);
  });
});

describe('searchMedals', () => {
  it('cherche sans casse ni accents dans nom et description', () => {
    expect(searchMedals(ds, 'PARE').map(m => m.id)).toEqual(['a']);
    expect(searchMedals(ds, 'equipez').map(m => m.id)).toEqual(['b']);
    expect(searchMedals(ds, '')).toHaveLength(3);
  });
});

describe('parseDataset', () => {
  it('accepte un dataset valide et rejette un succès sans palier', () => {
    expect(parseDataset(ds)).toBe(ds);
    expect(() => parseDataset({ ...ds, medals: [medal({ ranks: [] })] })).toThrow(/ranks/);
    expect(() => parseDataset({ ...ds, medals: [medal({ categoryIndex: 7 })] })).toThrow(/categoryIndex/);
  });
});
```

- [ ] **Step 3 : Lancer**

```bash
npm test
```

Attendu : échec, module `./medals.logic` introuvable.

- [ ] **Step 4 : Implémentation**

`src/data/medals.logic.ts` :

```ts
import type { Medal, MedalFilter, MedalRank, MedalsDataset } from './medals.types';

export function isComplete(m: Medal): boolean {
  return m.currentRank >= m.ranks.length;
}

export function currentRankOf(m: Medal): MedalRank {
  return m.ranks[Math.min(m.currentRank, m.ranks.length - 1)];
}

const FRAMES = [500, 100, 50, 30] as const;
export function frameForScore(score: number): 30 | 50 | 100 | 500 {
  return FRAMES.find(f => score >= f) ?? 30;
}

export function medalsOf(ds: MedalsDataset, categoryIndex: number, subCategoryIndex: number): Medal[] {
  return ds.medals.filter(m => m.categoryIndex === categoryIndex && m.subCategoryIndex === subCategoryIndex);
}

export function subCategoryCounts(ds: MedalsDataset, categoryIndex: number, subCategoryIndex: number) {
  const list = medalsOf(ds, categoryIndex, subCategoryIndex);
  return { done: list.filter(isComplete).length, total: list.length };
}

export function filterMedals(medals: Medal[], filter: MedalFilter): Medal[] {
  if (filter === 'completed') return medals.filter(isComplete);
  if (filter === 'inProgress') return medals.filter(m => !isComplete(m));
  return medals;
}

export function normalize(s: string): string {
  return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

export function searchMedals(ds: MedalsDataset, query: string): Medal[] {
  const q = normalize(query.trim());
  if (!q) return ds.medals;
  return ds.medals.filter(m => normalize(m.name).includes(q) || normalize(m.description).includes(q));
}

function fail(path: string, msg: string): never {
  throw new Error(`Dataset invalide (${path}) : ${msg}`);
}

export function parseDataset(raw: unknown): MedalsDataset {
  const ds = raw as MedalsDataset;
  if (!ds || !Array.isArray(ds.categories) || !Array.isArray(ds.medals)) fail('root', 'categories/medals manquants');
  if (typeof ds.totalScore !== 'number') fail('totalScore', 'nombre attendu');
  ds.medals.forEach((m, i) => {
    const p = `medals[${i}]`;
    if (!m.id || !m.name) fail(p, 'id/name manquants');
    if (!Array.isArray(m.ranks) || m.ranks.length === 0) fail(`${p}.ranks`, 'au moins un palier requis');
    const cat = ds.categories[m.categoryIndex];
    if (!cat) fail(`${p}.categoryIndex`, `catégorie ${m.categoryIndex} inexistante`);
    if (!cat.subCategories[m.subCategoryIndex]) fail(`${p}.subCategoryIndex`, `sous-catégorie ${m.subCategoryIndex} inexistante`);
    if (m.currentRank < 0 || m.currentRank > m.ranks.length) fail(`${p}.currentRank`, 'hors bornes');
  });
  return ds;
}
```

- [ ] **Step 5 : Lancer**

```bash
npm test
```

Attendu : tous PASS.

- [ ] **Step 6 : Mock**

`src/data/medals.mock.json`. Catégories dans l'ordre du jeu : `Progression`, `Personnage` (Équipement, Professions, Divers, Long service), `Batailles` (Escarmouches, Domination), `Astral` (Alliés), `Raids précédents` (Laboratoire central), `Zones de l'histoire` (Ferris), `Ordre`, `Raids actuels`, `Aventures héroïques`, `Succès rares`. Les catégories sans succès mockés ont une sous-catégorie `Général` vide. Contenu minimal exigé (textes tirés du client) :

```json
{
  "totalScore": 24690,
  "categories": [
    { "name": "Progression", "subCategories": [{ "name": "Général" }] },
    { "name": "Personnage", "subCategories": [{ "name": "Équipement" }, { "name": "Professions" }, { "name": "Divers" }, { "name": "Long service" }] },
    { "name": "Batailles", "subCategories": [{ "name": "Escarmouches" }, { "name": "Domination" }] },
    { "name": "Astral", "subCategories": [{ "name": "Général" }] },
    { "name": "Raids précédents", "subCategories": [{ "name": "Laboratoire central" }] },
    { "name": "Zones de l'histoire", "subCategories": [{ "name": "Ferris" }] },
    { "name": "Ordre", "subCategories": [{ "name": "Général" }] },
    { "name": "Raids actuels", "subCategories": [{ "name": "Général" }] },
    { "name": "Aventures héroïques", "subCategories": [{ "name": "Bestiaire" }] },
    { "name": "Succès rares", "subCategories": [{ "name": "Général" }] }
  ],
  "medals": [
    {
      "id": "equip-immortalite", "name": "Paré pour l'aventure ! (Immortalité)",
      "description": "Augmentez la côte d'équipement maximum à 100 000 points.",
      "icon": "Interface/Icons/Equipment/Helm/LionHelmet", "categoryIndex": 1, "subCategoryIndex": 0,
      "ranks": [{ "completeProgress": 100000, "name": "Paré pour l'aventure ! (Immortalité)", "description": "Augmentez la côte d'équipement maximum à 100 000 points.", "score": 10 }],
      "currentRank": 1, "progress": { "value": 100000 }, "finishDate": "2017-09-13"
    },
    {
      "id": "equip-reveil", "name": "Paré pour l'aventure ! (Réveil)",
      "description": "Augmentez la côte d'équipement maximum à 21 500 points.",
      "icon": "Interface/Icons/Equipment/Helm/LionHelmet", "categoryIndex": 1, "subCategoryIndex": 0,
      "ranks": [{ "completeProgress": 21500, "name": "Paré pour l'aventure ! (Réveil)", "description": "Augmentez la côte d'équipement maximum à 21 500 points.", "score": 10 }],
      "currentRank": 1, "progress": { "value": 21500 }, "finishDate": "2019-01-28"
    },
    {
      "id": "dragon-temps-nouveaux", "name": "Dragon des temps nouveaux",
      "description": "Équipez un ensemble complet de Reliques du dragon.",
      "icon": "Interface/Icons/Special/Currency/DiamondMedal", "categoryIndex": 1, "subCategoryIndex": 0,
      "ranks": [{ "completeProgress": 1, "name": "Dragon des temps nouveaux", "description": "Équipez un ensemble complet de Reliques du dragon.", "score": 100 }],
      "currentRank": 1, "finishDate": "2020-01-29",
      "dressCollection": [
        { "slot": "chest", "description": "Torse", "success": true }, { "slot": "waist", "description": "Taille", "success": true },
        { "slot": "feet", "description": "Pieds", "success": true }, { "slot": "wrist", "description": "Poignets", "success": true },
        { "slot": "ear1", "description": "Oreilles", "success": true }, { "slot": "ear2", "description": "Oreilles", "success": true },
        { "slot": "hands", "description": "Mains", "success": true }, { "slot": "head", "description": "Tête", "success": true },
        { "slot": "shoulders", "description": "Épaules", "success": true }, { "slot": "neck", "description": "Cou", "success": true }
      ]
    },
    {
      "id": "divin", "name": "Divin", "description": "Équipez-vous d'un ensemble complet d'équipement fabuleux.",
      "icon": "Interface/Icons/Special/Currency/DiamondMedal", "categoryIndex": 1, "subCategoryIndex": 0,
      "ranks": [{ "completeProgress": 1, "name": "Divin", "description": "Équipez-vous d'un ensemble complet d'équipement fabuleux.", "score": 50 }],
      "currentRank": 1, "finishDate": "2021-03-02"
    },
    {
      "id": "glaneur", "name": "Glaneur", "description": "Créez des Amalgames avec des gouttes d'Amalgame.",
      "icon": "Interface/Icons/Misc/Event/GoldMedal", "categoryIndex": 1, "subCategoryIndex": 1,
      "ranks": [
        { "completeProgress": 10, "name": "Goutte à goutte", "description": "Créez 10 Amalgames avec des gouttes d'Amalgame.", "score": 10 },
        { "completeProgress": 50, "name": "Glaneur", "description": "Créez 50 Amalgames avec des gouttes d'Amalgame.", "score": 10 },
        { "completeProgress": 100, "name": "Glaneur", "description": "Créez 100 Amalgames avec des gouttes d'Amalgame.", "score": 30 },
        { "completeProgress": 1000, "name": "Magnat de l'Amalgame", "description": "Créez 1000 Amalgames avec des gouttes d'Amalgame.", "score": 100 }
      ],
      "currentRank": 2, "progress": { "value": 73, "title": "Amalgame récolté" }
    },
    {
      "id": "escarmouches", "name": "Légende du Goblinoball", "description": "Remportez des Escarmouches.",
      "icon": "Interface/Icons/Misc/Event/GoldMedal", "categoryIndex": 2, "subCategoryIndex": 0,
      "ranks": [
        { "completeProgress": 5, "name": "Parties gagnées", "description": "Remportez 5 Escarmouches.", "score": 10 },
        { "completeProgress": 50, "name": "Parties gagnées", "description": "Remportez 50 Escarmouches.", "score": 30 },
        { "completeProgress": 500, "name": "Légende du Goblinoball", "description": "Remportez 500 Escarmouches.", "score": 100 }
      ],
      "currentRank": 1, "progress": { "value": 23, "title": "Parties gagnées" }
    },
    {
      "id": "vieille-querelle", "name": "Vieille querelle", "description": "Éliminez votre tueur.",
      "icon": "Interface/Icons/Misc/Event/GoldMedal", "categoryIndex": 2, "subCategoryIndex": 1,
      "ranks": [
        { "completeProgress": 5, "name": "Vieille querelle", "description": "Éliminez votre tueur 5 fois.", "score": 10 },
        { "completeProgress": 100, "name": "Vieille querelle", "description": "Éliminez votre tueur 100 fois.", "score": 50 },
        { "completeProgress": 500, "name": "Vieille querelle", "description": "Éliminez votre tueur 500 fois.", "score": 500 }
      ],
      "currentRank": 0, "progress": { "value": 2 }
    },
    {
      "id": "faux-semblants", "name": "Faux semblants", "description": "Battez le clone d'Herbert dans le Laboratoire central.",
      "icon": "Interface/Icons/Special/VeteranRewards/VeteranRankMaster", "categoryIndex": 4, "subCategoryIndex": 0,
      "ranks": [{ "completeProgress": 1, "name": "Faux semblants", "description": "Battez le clone d'Herbert dans le Laboratoire central.", "score": 30 }],
      "currentRank": 1, "finishDate": "2016-11-05"
    },
    {
      "id": "variable-indefinie", "name": "Variable indéfinie", "description": "Battez le Mécanoïde dans le Laboratoire central.",
      "icon": "Interface/Icons/Special/VeteranRewards/VeteranRankMaster", "categoryIndex": 4, "subCategoryIndex": 0,
      "ranks": [{ "completeProgress": 1, "name": "Variable indéfinie", "description": "Battez le Mécanoïde dans le Laboratoire central.", "score": 30 }],
      "currentRank": 0
    },
    {
      "id": "partie-terminee", "name": "Partie terminée", "description": "Battez Negus Jeeg dans le Laboratoire central.",
      "icon": "Interface/Icons/Special/VeteranRewards/VeteranRankMaster", "categoryIndex": 4, "subCategoryIndex": 0,
      "ranks": [{ "completeProgress": 1, "name": "Partie terminée", "description": "Battez Negus Jeeg dans le Laboratoire central.", "score": 50 }],
      "currentRank": 0
    },
    {
      "id": "petit-chef", "name": "Petit chef", "description": "Battez le chef Tungar dans les grandes batailles de Ferris.",
      "icon": "Interface/Icons/Special/VeteranRewards/VeteranRankMaster", "categoryIndex": 5, "subCategoryIndex": 0,
      "ranks": [{ "completeProgress": 1, "name": "Petit chef", "description": "Battez le chef Tungar dans les grandes batailles de Ferris.", "score": 10 }],
      "currentRank": 1, "finishDate": "2018-06-14"
    },
    {
      "id": "provisions-hiver", "name": "Provisions pour l'hiver", "description": "Battez Toros dans les grandes batailles de Ferris.",
      "icon": "Interface/Icons/Special/VeteranRewards/VeteranRankMaster", "categoryIndex": 5, "subCategoryIndex": 0,
      "ranks": [{ "completeProgress": 1, "name": "Provisions pour l'hiver", "description": "Battez Toros dans les grandes batailles de Ferris.", "score": 10 }],
      "currentRank": 0
    },
    {
      "id": "gros-gibier", "name": "Gros gibier", "description": "Éliminez Courlis-Khan dans le Bestiaire.",
      "icon": "Interface/Icons/Special/VeteranRewards/VeteranRankMaster", "categoryIndex": 8, "subCategoryIndex": 0,
      "ranks": [{ "completeProgress": 1, "name": "Gros gibier", "description": "Éliminez Courlis-Khan dans le Bestiaire.", "score": 30 }],
      "currentRank": 1, "finishDate": "2022-02-11"
    },
    {
      "id": "cavaliers-tempete", "name": "Cavaliers de la tempête", "description": "Éliminez Havoc dans le Bestiaire.",
      "icon": "Interface/Icons/Special/VeteranRewards/VeteranRankMaster", "categoryIndex": 8, "subCategoryIndex": 0,
      "ranks": [{ "completeProgress": 1, "name": "Cavaliers de la tempête", "description": "Éliminez Havoc dans le Bestiaire.", "score": 30 }],
      "currentRank": 0
    },
    {
      "id": "tenu-en-laisse", "name": "Tenu en laisse", "description": "Éliminez Rustle dans le Bestiaire.",
      "icon": "Interface/Icons/Special/VeteranRewards/VeteranRankMaster", "categoryIndex": 8, "subCategoryIndex": 0,
      "ranks": [{ "completeProgress": 1, "name": "Tenu en laisse", "description": "Éliminez Rustle dans le Bestiaire.", "score": 30 }],
      "currentRank": 1, "finishDate": "2022-02-18"
    },
    {
      "id": "licorne-magique", "name": "Licorne magique", "description": "Devenez un véritable chevaucheur de bâton en ramassant et en utilisant 100 poils de licorne.",
      "icon": "Interface/Icons/Misc/Event/GoldMedal", "categoryIndex": 9, "subCategoryIndex": 0,
      "ranks": [{ "completeProgress": 100, "name": "Licorne magique", "description": "Devenez un véritable chevaucheur de bâton en ramassant et en utilisant 100 poils de licorne.", "score": 500 }],
      "currentRank": 0, "progress": { "value": 41, "title": "Je suis un chevaucheur de bâton." }
    }
  ]
}
```

Compléter jusqu'à ~20 succès en ajoutant 4 entrées dans `Personnage / Divers` et `Personnage / Long service` (textes libres tirés de `texts_fr.txt` autour des lignes 122600–122700, mêmes structures que ci-dessus). Les chemins `icon` doivent exister dans `public/game/manifest.json` après la Task 3 ; sinon les remplacer par un chemin qui existe.

- [ ] **Step 7 : Test du mock**

Ajouter dans `medals.logic.test.ts` :

```ts
import mock from './medals.mock.json';
it('le mock est un dataset valide', () => {
  const parsed = parseDataset(mock);
  expect(parsed.medals.length).toBeGreaterThanOrEqual(16);
  expect(subCategoryCounts(parsed, 1, 0)).toEqual({ done: 4, total: 4 });
});
```

`npm test` → PASS. (Dans `tsconfig.json`, `resolveJsonModule: true` doit être présent ; le template Vite l'active.)

- [ ] **Step 8 : Commit**

```bash
git add src/data
git commit -m "feat(data): modèle medalsLib, logique pure et jeu de données mock

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5 : Helper d'assets, routeur, briques UI de base

**Files:**
- Create: `src/lib/assets.ts`, `src/lib/assets.test.ts`, `src/lib/router.tsx`, `src/components/game/GameFrame.tsx`, `src/components/game/GameFrame.module.css`, `src/components/game/GameButton.tsx`, `src/components/game/GameButton.module.css`, `src/components/game/ProgressBar.tsx`, `src/components/game/ProgressBar.module.css`, `src/components/game/MedalBadge.tsx`, `src/components/game/MedalBadge.module.css`
- Modify: `src/App.tsx`, `src/styles/global.css`

**Interfaces:**
- Produces :
  - `tex(path: string): string` → `/game/textures/${path}.png`.
  - `texSize(path: string): { w: number; h: number } | undefined` (lit `manifest.json` chargé une fois via `loadManifest(): Promise<void>` ; retourne `undefined` avant chargement).
  - `video(name: 'intro' | 'mainmenu'): { webm: string; mp4: string }`.
  - `cursor(name: string): string` → `/game/cursors/${name}.cur`.
  - `useRoute(): { path: string; query: URLSearchParams }`, `navigate(to: string): void`, `<Link to>`.
  - `<GameFrame texture slice={{ top, right, bottom, left }} className style>` : `border-image` 9 tranches, enfants en `position: relative`.
  - `<GameButton base label onClick disabled shape="round"|"wide" size>` : `base` = préfixe de texture (ex. `Interface/Wrap/MainMenu/LoginAccount/ButtonLogin`), états `Normal`, `Highlighted`, `Pressed`, `Disabled` ; pour `Interface/Common/Buttons/Cross/Close` les états sont `Normal`, `Highlight`, `Pressed`, `Disabled` → prop `stateNames?: { hover: string }` défaut `'Highlighted'`.
  - `<ProgressBar value max label>`.
  - `<MedalBadge score icon complete>`.

- [ ] **Step 1 : Test échouant assets**

`src/lib/assets.test.ts` :

```ts
import { describe, it, expect } from 'vitest';
import { tex, video, cursor } from './assets';

describe('assets', () => {
  it('construit les URLs publiques', () => {
    expect(tex('Interface/Ingame/Medals/Textures/MedalFrame')).toBe('/game/textures/Interface/Ingame/Medals/Textures/MedalFrame.png');
    expect(video('intro')).toEqual({ webm: '/game/video/intro.webm', mp4: '/game/video/intro.mp4' });
    expect(cursor('Default')).toBe('/game/cursors/Default.cur');
  });
});
```

`npm test` → échec module introuvable.

- [ ] **Step 2 : Implémentation assets**

`src/lib/assets.ts` :

```ts
const BASE = '/game';
type Size = { w: number; h: number };
let manifest: Record<string, Size> | null = null;

export async function loadManifest(): Promise<void> {
  try {
    const res = await fetch(`${BASE}/manifest.json`);
    if (!res.ok) throw new Error(String(res.status));
    manifest = (await res.json()).textures ?? {};
  } catch {
    manifest = {};
    if (import.meta.env.DEV) console.warn('[assets] manifest.json absent : lancez `npm run extract`');
  }
}

export const hasAssets = () => manifest !== null && Object.keys(manifest).length > 0;
export const tex = (path: string) => `${BASE}/textures/${path}.png`;
export const texSize = (path: string): Size | undefined => manifest?.[path];
export const video = (name: 'intro' | 'mainmenu') => ({ webm: `${BASE}/video/${name}.webm`, mp4: `${BASE}/video/${name}.mp4` });
export const cursor = (name: string) => `${BASE}/cursors/${name}.cur`;

export const T = {
  medals: 'Interface/Ingame/Medals/Textures',
  login: 'Interface/Wrap/MainMenu/LoginAccount',
  main2: 'Interface/Wrap/MainMenu/Main2',
  cross: 'Interface/Common/Buttons/Cross/Close',
  msgbox: 'Interface/Common/Elements/MsgBox/textures',
} as const;
```

`npm test` → PASS.

- [ ] **Step 3 : Routeur**

`src/lib/router.tsx` :

```tsx
import { useEffect, useState, type ReactNode, type MouseEvent } from 'react';

function read() {
  return { path: window.location.pathname, query: new URLSearchParams(window.location.search) };
}

export function navigate(to: string) {
  window.history.pushState(null, '', to);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

export function useRoute() {
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const onPop = () => setRoute(read());
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);
  return route;
}

export function Link({ to, children, className }: { to: string; children: ReactNode; className?: string }) {
  const onClick = (e: MouseEvent) => { e.preventDefault(); navigate(to); };
  return <a href={to} onClick={onClick} className={className}>{children}</a>;
}
```

- [ ] **Step 4 : GameFrame**

`src/components/game/GameFrame.tsx` :

```tsx
import type { CSSProperties, ReactNode } from 'react';
import { tex } from '@/lib/assets';
import s from './GameFrame.module.css';

type Slice = { top: number; right: number; bottom: number; left: number };
type Props = { texture: string; slice: Slice; className?: string; style?: CSSProperties; children?: ReactNode; fill?: boolean };

export function GameFrame({ texture, slice, className, style, children, fill = true }: Props) {
  const { top, right, bottom, left } = slice;
  const frameStyle: CSSProperties = {
    borderImageSource: `url(${tex(texture)})`,
    borderImageSlice: `${top} ${right} ${bottom} ${left}${fill ? ' fill' : ''}`,
    borderImageWidth: `${top}px ${right}px ${bottom}px ${left}px`,
    borderWidth: `${top}px ${right}px ${bottom}px ${left}px`,
    ...style,
  };
  return <div className={`${s.frame} ${className ?? ''}`} style={frameStyle}>{children}</div>;
}
```

`GameFrame.module.css` :

```css
.frame { position: relative; border-style: solid; border-image-repeat: stretch; }
```

- [ ] **Step 5 : GameButton**

`src/components/game/GameButton.tsx` :

```tsx
import { useState, type CSSProperties, type ReactNode } from 'react';
import { tex } from '@/lib/assets';
import s from './GameButton.module.css';

type Props = {
  base: string; label?: ReactNode; title?: string; onClick?: () => void; disabled?: boolean;
  width: number; height: number; hoverState?: string; className?: string; style?: CSSProperties;
};

export function GameButton({ base, label, title, onClick, disabled, width, height, hoverState = 'Highlighted', className, style }: Props) {
  const [hover, setHover] = useState(false);
  const [pressed, setPressed] = useState(false);
  const state = disabled ? 'Disabled' : pressed ? 'Pressed' : hover ? hoverState : 'Normal';
  return (
    <button
      type="button" title={title} disabled={disabled} onClick={onClick}
      className={`${s.btn} ${className ?? ''}`}
      style={{ width, height, backgroundImage: `url(${tex(`${base}${state}`)})`, ...style }}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => { setHover(false); setPressed(false); }}
      onMouseDown={() => setPressed(true)} onMouseUp={() => setPressed(false)}
    >
      {label && <span className={s.label}>{label}</span>}
    </button>
  );
}
```

`GameButton.module.css` :

```css
.btn { display: inline-flex; align-items: center; justify-content: center; background: center / 100% 100% no-repeat; }
.btn:disabled { filter: saturate(0.4); }
.label {
  font-family: var(--font-caps); font-weight: 700; color: var(--gold);
  text-shadow: 0 0 2px #000, 0 1px 0 #000; letter-spacing: 0.02em;
}
```

- [ ] **Step 6 : ProgressBar et MedalBadge**

`ProgressBar.tsx` :

```tsx
import { T, tex } from '@/lib/assets';
import s from './ProgressBar.module.css';

export function ProgressBar({ value, max, label }: { value: number; max: number; label?: string }) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  return (
    <div className={s.bar} style={{ backgroundImage: `url(${tex(`${T.medals}/ProgressBar`)})` }}>
      <div className={s.gauge} style={{ width: `${pct}%`, backgroundImage: `url(${tex(`${T.medals}/ProgressBarGauge`)})` }} />
      <span className={s.text}>{label ?? `${value.toLocaleString('fr-FR')} sur ${max.toLocaleString('fr-FR')}`}</span>
    </div>
  );
}
```

`ProgressBar.module.css` :

```css
.bar { position: relative; height: 16px; background: center / 100% 100% no-repeat; border-radius: 8px; overflow: hidden; }
.gauge { position: absolute; inset: 0 auto 0 0; background: left / auto 100% no-repeat; }
.text {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 700; color: #fff; text-shadow: 0 0 2px #000, 0 0 2px #000;
}
```

`MedalBadge.tsx` :

```tsx
import { T, tex } from '@/lib/assets';
import { frameForScore } from '@/data/medals.logic';
import s from './MedalBadge.module.css';

export function MedalBadge({ score, icon, complete }: { score: number; icon: string; complete: boolean }) {
  const frame = `${T.medals}/MedalFrame${complete ? 'Complete' : ''}${frameForScore(score)}`;
  return (
    <div className={s.badge} style={{ backgroundImage: `url(${tex(frame)})` }}>
      <img className={s.icon} src={tex(icon)} alt="" draggable={false} />
      <span className={s.score}>{score}</span>
    </div>
  );
}
```

`MedalBadge.module.css` (la texture du cadre fait 128×256 mais le dessin utile occupe environ 64×96 en haut ; ajuster `background-size`/`background-position` après visualisation du PNG) :

```css
.badge { position: relative; width: 64px; height: 84px; background: top center / 128px 168px no-repeat; }
.icon { position: absolute; top: 8px; left: 12px; width: 40px; height: 40px; border-radius: 4px; }
.score {
  position: absolute; bottom: 10px; left: 0; right: 0; text-align: center;
  font-family: var(--font-caps); font-weight: 700; font-size: 15px; color: #fff; text-shadow: 0 0 3px #000, 0 1px 0 #000;
}
```

- [ ] **Step 7 : App avec routes et curseur**

`src/App.tsx` :

```tsx
import { useEffect, useState } from 'react';
import { loadManifest, cursor, hasAssets } from '@/lib/assets';
import { useRoute } from '@/lib/router';

export default function App() {
  const [ready, setReady] = useState(false);
  const { path } = useRoute();
  useEffect(() => { loadManifest().then(() => setReady(true)); }, []);
  useEffect(() => { document.body.style.cursor = `url(${cursor('Default')}), auto`; }, []);
  if (!ready) return null;
  return (
    <>
      {import.meta.env.DEV && !hasAssets() && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, zIndex: 99, background: '#a33', color: '#fff', padding: 6, textAlign: 'center', fontSize: 14 }}>
          Assets du jeu absents : lancez <code>npm run extract</code>
        </div>
      )}
      {path === '/succes' ? <div style={{ color: '#fff' }}>succès (Task 7)</div> : <div style={{ color: '#fff' }}>ouverture (Task 6)</div>}
    </>
  );
}
```

- [ ] **Step 8 : Vérifier**

```bash
npm test && npm run build
```

Attendu : tests PASS, build sans erreur TypeScript.

- [ ] **Step 9 : Commit**

```bash
git add src
git commit -m "feat(ui): helper d'assets, routeur maison et briques GameFrame/GameButton/ProgressBar/MedalBadge

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6 : Écran d'ouverture (intro → menu → panneau de connexion)

**Files:**
- Create: `src/screens/OpeningScreen/OpeningScreen.tsx`, `src/screens/OpeningScreen/OpeningScreen.module.css`, `src/screens/OpeningScreen/useIntroState.ts`, `src/screens/OpeningScreen/useIntroState.test.ts`
- Modify: `src/App.tsx`

**Interfaces:**
- Consumes : `video`, `tex`, `T` (Task 5), `GameButton`, `navigate`.
- Produces : `useIntroState(storage: Storage = localStorage): { phase: 'intro' | 'menu'; skipIntro(): void; replayIntro(): void }` ; clé `localStorage` = `allods.introSeen` (`'1'`).

- [ ] **Step 1 : Test échouant de la machine d'états**

`useIntroState.test.ts` :

```ts
import { describe, it, expect } from 'vitest';
import { initialPhase, INTRO_SEEN_KEY } from './useIntroState';

const mem = (init: Record<string, string> = {}) => {
  const m = new Map(Object.entries(init));
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) } as Storage;
};

describe('initialPhase', () => {
  it('joue l’intro à la première visite', () => expect(initialPhase(mem())).toBe('intro'));
  it('saute l’intro si déjà vue', () => expect(initialPhase(mem({ [INTRO_SEEN_KEY]: '1' }))).toBe('menu'));
});
```

`npm test` → échec.

- [ ] **Step 2 : Hook**

`useIntroState.ts` :

```ts
import { useCallback, useState } from 'react';

export const INTRO_SEEN_KEY = 'allods.introSeen';
export type Phase = 'intro' | 'menu';

export function initialPhase(storage: Storage): Phase {
  try { return storage.getItem(INTRO_SEEN_KEY) === '1' ? 'menu' : 'intro'; } catch { return 'menu'; }
}

export function useIntroState(storage: Storage = window.localStorage) {
  const [phase, setPhase] = useState<Phase>(() => initialPhase(storage));
  const skipIntro = useCallback(() => {
    try { storage.setItem(INTRO_SEEN_KEY, '1'); } catch { /* stockage indisponible */ }
    setPhase('menu');
  }, [storage]);
  const replayIntro = useCallback(() => setPhase('intro'), []);
  return { phase, skipIntro, replayIntro };
}
```

`npm test` → PASS.

- [ ] **Step 3 : Composant**

`OpeningScreen.tsx` :

```tsx
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { T, tex, video } from '@/lib/assets';
import { navigate } from '@/lib/router';
import { GameButton } from '@/components/game/GameButton';
import { useIntroState } from './useIntroState';
import s from './OpeningScreen.module.css';

function Video({ name, loop, onEnded, onError, className }: { name: 'intro' | 'mainmenu'; loop?: boolean; onEnded?: () => void; onError?: () => void; className?: string }) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    v.play().catch(() => onError?.());   // autoplay refusé → on passe au menu
  }, [name, onError]);
  const src = video(name);
  return (
    <video ref={ref} className={className} muted playsInline loop={loop} onEnded={onEnded} onError={onError} poster={tex(`${T.main2}/Background_14_0_Temp`)}>
      <source src={src.webm} type="video/webm" />
      <source src={src.mp4} type="video/mp4" />
    </video>
  );
}

export function OpeningScreen() {
  const { phase, skipIntro, replayIntro } = useIntroState();
  const [query, setQuery] = useState('');

  useEffect(() => {
    if (phase !== 'intro') return;
    const onKey = (e: KeyboardEvent) => { if (e.key === ' ' || e.key === 'Escape' || e.key === 'Enter') skipIntro(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [phase, skipIntro]);

  const goMedals = (e?: FormEvent) => {
    e?.preventDefault();
    navigate(query.trim() ? `/succes?q=${encodeURIComponent(query.trim())}` : '/succes');
  };

  if (phase === 'intro') {
    return (
      <div className={s.screen} onClick={skipIntro}>
        <Video name="intro" className={s.video} onEnded={skipIntro} onError={skipIntro} />
        <span className={s.skipHint}>Cliquez pour passer</span>
      </div>
    );
  }

  return (
    <div className={s.screen}>
      <Video name="mainmenu" loop className={`${s.video} ${s.fadeIn}`} />
      <div className={s.vignette} />

      <form className={s.loginPanel} onSubmit={goMedals}>
        <label className={s.field} style={{ backgroundImage: `url(${tex(`${T.login}/EditlineFrame`)})` }}>
          <input
            className={s.input} value={query} onChange={e => setQuery(e.target.value)}
            placeholder="Recherche de succès..." autoFocus spellCheck={false}
          />
        </label>
        <GameButton base={`${T.login}/ButtonLogin`} width={220} height={64} label="Succès" onClick={() => goMedals()} className={s.mainButton} />
        <div className={s.roundRow}>
          <GameButton base={`${T.login}/ButtonOptions`} width={56} height={56} title="Mon compte (bientôt)" disabled />
          <GameButton base={`${T.login}/ButtonKeyboard`} width={56} height={56} title="Addon d'export (bientôt)" disabled />
          <GameButton base={`${T.login}/ButtonCredits`} width={56} height={56} title="Rejouer l'intro" onClick={replayIntro} />
        </div>
      </form>

      <div className={s.bottomLine} style={{ backgroundImage: `url(${tex(`${T.main2}/BottomLine`)})` }}>
        <span>Site fan non officiel. Allods Online, ses images et vidéos sont la propriété de My.Games.</span>
      </div>
    </div>
  );
}
```

`OpeningScreen.module.css` :

```css
.screen { position: fixed; inset: 0; background: #000; overflow: hidden; }
.video { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.fadeIn { animation: fade 900ms ease-out both; }
@keyframes fade { from { opacity: 0; } to { opacity: 1; } }
.skipHint { position: absolute; right: 24px; bottom: 20px; color: #ccc; font-size: 14px; opacity: 0.7; }
.vignette { position: absolute; inset: 0; background: radial-gradient(ellipse at 50% 60%, transparent 55%, rgba(0,0,0,0.55)); pointer-events: none; }

.loginPanel {
  position: absolute; left: 50%; bottom: 18%; transform: translateX(-50%);
  display: flex; flex-direction: column; align-items: center; gap: 14px;
}
.field { display: block; width: 320px; height: 44px; background: center / 100% 100% no-repeat; padding: 8px 22px; }
.input {
  width: 100%; height: 100%; background: transparent; border: 0; outline: none;
  color: #e6efe0; font-family: var(--font-serif); font-size: 18px;
}
.input::placeholder { color: var(--search-green); font-style: italic; }
.mainButton span { font-size: 22px; }
.roundRow { display: flex; gap: 12px; margin-top: 4px; }

.bottomLine {
  position: absolute; left: 0; right: 0; bottom: 0; height: 56px;
  background: center bottom / 100% 100% no-repeat;
  display: flex; align-items: center; justify-content: center;
  color: #b9c9b4; font-size: 13px; text-shadow: 0 1px 1px #000;
}
```

- [ ] **Step 4 : Brancher dans App**

Dans `src/App.tsx`, remplacer le placeholder « ouverture » par `<OpeningScreen />` (import `@/screens/OpeningScreen/OpeningScreen`).

- [ ] **Step 5 : Vérifier à l'écran**

```bash
npm run dev -- --host 127.0.0.1 &
sleep 3 && npx playwright screenshot --viewport-size=1280,720 --wait-for-timeout=4000 http://127.0.0.1:5173/ /tmp/claude-1000/opening.png
```

Si `npx playwright` n'est pas disponible : `npm i -D playwright && npx playwright install chromium` (une fois). Ouvrir la capture avec l'outil Read. Attendu : vidéo d'intro plein écran à la première visite ; relancer avec `--wait-for-timeout=25000` pour voir le menu, ou ajouter `?skipIntro` : dans `useIntroState`, si `window.location.search.includes('skipIntro')` alors phase initiale `menu` (ajouter cette ligne dans `initialPhase` via un paramètre `forceMenu = false`). Vérifier : vidéo du menu en fond, champ de recherche et bouton « Succès » lisibles, boutons ronds, bande basse.

Arrêter le serveur (`kill %1`).

- [ ] **Step 6 : Commit**

```bash
git add src
git commit -m "feat(opening): écran d'ouverture — intro, menu vidéo, panneau de connexion en menu

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7 : Panneau Succès — fenêtre et navigation

**Files:**
- Create: `src/screens/MedalsScreen/MedalsScreen.tsx`, `src/screens/MedalsScreen/MedalsScreen.module.css`, `src/screens/MedalsScreen/MedalsNavigation.tsx`, `src/screens/MedalsScreen/MedalsNavigation.module.css`, `src/screens/MedalsScreen/useMedalsState.ts`
- Modify: `src/App.tsx`

**Interfaces:**
- Consumes : `parseDataset`, `subCategoryCounts`, `searchMedals`, `medalsOf`, `filterMedals` (Task 4), `GameFrame`, `GameButton`, `T`, `tex`, `video`, `useRoute`, `navigate`.
- Produces :
  - `useMedalsState(ds, initialQuery)` → `{ selected: { categoryIndex, subCategoryIndex } | null; select(c, s); openCategory: number | null; toggleCategory(c); query; setQuery; filter; setFilter; visible: Medal[]; title: string }`. Règles : si `query` non vide, `visible = filterMedals(searchMedals(ds, query), filter)` et `title = 'Résultats de la recherche'` ; sinon `visible = filterMedals(medalsOf(ds, c, s), filter)` et `title = nom de la sous-catégorie`. Sélection initiale : première catégorie ayant au moins un succès, première sous-catégorie non vide (par défaut Personnage / Équipement pour le mock).
  - `<MedalsNavigation ds state />`, `<MedalsList ds state />` (Task 8).

- [ ] **Step 1 : État**

`useMedalsState.ts` :

```ts
import { useMemo, useState } from 'react';
import type { Medal, MedalFilter, MedalsDataset } from '@/data/medals.types';
import { filterMedals, medalsOf, searchMedals } from '@/data/medals.logic';

export type Selection = { categoryIndex: number; subCategoryIndex: number };

export function firstNonEmpty(ds: MedalsDataset): Selection {
  for (let c = 0; c < ds.categories.length; c++)
    for (let s = 0; s < ds.categories[c].subCategories.length; s++)
      if (medalsOf(ds, c, s).length) return { categoryIndex: c, subCategoryIndex: s };
  return { categoryIndex: 0, subCategoryIndex: 0 };
}

export function useMedalsState(ds: MedalsDataset, initialQuery = '') {
  const [selected, setSelected] = useState<Selection>(() => firstNonEmpty(ds));
  const [openCategory, setOpenCategory] = useState<number | null>(selected.categoryIndex);
  const [query, setQuery] = useState(initialQuery);
  const [filter, setFilter] = useState<MedalFilter>('all');

  const select = (categoryIndex: number, subCategoryIndex: number) => { setSelected({ categoryIndex, subCategoryIndex }); setQuery(''); };
  const toggleCategory = (c: number) => setOpenCategory(prev => (prev === c ? null : c));

  const { visible, title } = useMemo(() => {
    if (query.trim()) return { visible: filterMedals(searchMedals(ds, query), filter), title: 'Résultats de la recherche' };
    const list = medalsOf(ds, selected.categoryIndex, selected.subCategoryIndex);
    return { visible: filterMedals(list, filter), title: ds.categories[selected.categoryIndex].subCategories[selected.subCategoryIndex].name };
  }, [ds, query, filter, selected]);

  return { selected, select, openCategory, toggleCategory, query, setQuery, filter, setFilter, visible: visible as Medal[], title };
}
export type MedalsState = ReturnType<typeof useMedalsState>;
```

- [ ] **Step 2 : Test de firstNonEmpty et des règles de visibilité**

Ajouter `src/screens/MedalsScreen/useMedalsState.test.ts` :

```ts
import { describe, it, expect } from 'vitest';
import mock from '@/data/medals.mock.json';
import { parseDataset } from '@/data/medals.logic';
import { firstNonEmpty } from './useMedalsState';

describe('firstNonEmpty', () => {
  it('sélectionne Personnage / Équipement pour le mock', () => {
    const ds = parseDataset(mock);
    const sel = firstNonEmpty(ds);
    expect(ds.categories[sel.categoryIndex].name).toBe('Personnage');
    expect(ds.categories[sel.categoryIndex].subCategories[sel.subCategoryIndex].name).toBe('Équipement');
  });
});
```

`npm test` → PASS.

- [ ] **Step 3 : Navigation**

`MedalsNavigation.tsx` :

```tsx
import { T, tex } from '@/lib/assets';
import { subCategoryCounts } from '@/data/medals.logic';
import type { MedalsDataset } from '@/data/medals.types';
import type { MedalsState } from './useMedalsState';
import s from './MedalsNavigation.module.css';

export function MedalsNavigation({ ds, state }: { ds: MedalsDataset; state: MedalsState }) {
  return (
    <aside className={s.nav} style={{ backgroundImage: `url(${tex(`${T.medals}/FrameNavigation`)})` }}>
      <label className={s.search} style={{ backgroundImage: `url(${tex(`${T.login}/EditlineFrame`)})` }}>
        <input value={state.query} onChange={e => state.setQuery(e.target.value)} placeholder="Recherche de succès..." spellCheck={false} />
      </label>

      <ul className={s.categories}>
        {ds.categories.map((cat, c) => {
          const open = state.openCategory === c;
          return (
            <li key={cat.name} className={s.category}>
              <button type="button" className={`${s.catButton} ${open ? s.catOpen : ''}`} onClick={() => state.toggleCategory(c)}>
                <span>{cat.name}</span>
                <span className={s.toggle}>{open ? '−' : '+'}</span>
              </button>
              {open && (
                <ul className={s.subList} style={{ backgroundImage: `url(${tex(`${T.medals}/CategoryContent`)})` }}>
                  {cat.subCategories.map((sub, i) => {
                    const { done, total } = subCategoryCounts(ds, c, i);
                    const active = !state.query && state.selected.categoryIndex === c && state.selected.subCategoryIndex === i;
                    return (
                      <li key={sub.name}>
                        <button type="button" className={`${s.subButton} ${active ? s.subActive : ''}`} onClick={() => state.select(c, i)}>
                          {sub.name} - {done}/{total}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
```

`MedalsNavigation.module.css` :

```css
.nav {
  width: 268px; padding: 14px 12px 12px; display: flex; flex-direction: column; gap: 10px;
  background: center / 100% 100% no-repeat;
}
.search { display: block; height: 36px; background: center / 100% 100% no-repeat; padding: 6px 16px; }
.search input { width: 100%; height: 100%; background: transparent; border: 0; outline: 0; color: #dfe9d8; font: italic 16px var(--font-serif); }
.search input::placeholder { color: var(--search-green); }

.categories { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; overflow-y: auto; }
.catButton {
  width: 100%; height: 30px; display: flex; align-items: center; justify-content: space-between; padding: 0 12px;
  background: linear-gradient(#3d5a3d, #22361f); border: 1px solid #6c8a5a; border-radius: 4px;
  color: var(--gold); font: 700 17px var(--font-caps); text-shadow: 0 1px 1px #000;
}
.catButton:hover { filter: brightness(1.15); }
.catOpen { border-color: #d9b45a; }
.toggle { width: 18px; height: 18px; border-radius: 50%; background: radial-gradient(#e6d18a, #8f6a1c); color: #2a1f05; font-size: 14px; line-height: 18px; text-align: center; }

.subList { list-style: none; margin: 4px 0 0; padding: 10px 14px; background: center / 100% 100% no-repeat; }
.subButton { width: 100%; text-align: left; padding: 4px 6px; color: var(--ink); font: 600 16px var(--font-serif); }
.subButton:hover { background: rgba(255, 255, 255, 0.18); }
.subActive { background: rgba(255, 255, 255, 0.35); box-shadow: inset 0 0 0 1px rgba(60, 40, 10, 0.25); }
```

- [ ] **Step 4 : Écran**

`MedalsScreen.tsx` :

```tsx
import { useMemo } from 'react';
import mock from '@/data/medals.mock.json';
import { parseDataset } from '@/data/medals.logic';
import { T, tex, video } from '@/lib/assets';
import { navigate, useRoute } from '@/lib/router';
import { GameFrame } from '@/components/game/GameFrame';
import { GameButton } from '@/components/game/GameButton';
import { MedalsNavigation } from './MedalsNavigation';
import { MedalsList } from './MedalsList';
import { useMedalsState } from './useMedalsState';
import s from './MedalsScreen.module.css';

export function MedalsScreen() {
  const ds = useMemo(() => parseDataset(mock), []);
  const { query } = useRoute();
  const state = useMedalsState(ds, query.get('q') ?? '');
  const bg = video('mainmenu');

  return (
    <div className={s.screen}>
      <video className={s.bg} autoPlay muted loop playsInline poster={tex(`${T.main2}/Background_14_0_Temp`)}>
        <source src={bg.webm} type="video/webm" /><source src={bg.mp4} type="video/mp4" />
      </video>

      <GameFrame texture={`${T.medals}/FrameContent`} slice={{ top: 96, right: 40, bottom: 40, left: 40 }} className={s.window}>
        <header className={s.header}>
          <h1 className={s.title}>Succès</h1>
          <GameButton base={T.cross} hoverState="Highlight" width={28} height={28} title="Fermer" onClick={() => navigate('/')} className={s.close} />
        </header>
        <div className={s.points}>{ds.totalScore.toLocaleString('fr-FR')} points de succès</div>
        <div className={s.columns}>
          <MedalsNavigation ds={ds} state={state} />
          <MedalsList ds={ds} state={state} />
        </div>
      </GameFrame>
    </div>
  );
}
```

`MedalsScreen.module.css` (les valeurs `slice` et paddings sont à ajuster après visualisation de `FrameContent.png`, dont la bande turquoise d'en-tête occupe le haut) :

```css
.screen { position: fixed; inset: 0; background: #000; overflow: hidden; display: grid; place-items: center; }
.bg { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; filter: blur(6px) brightness(0.55); transform: scale(1.04); }
.window { position: relative; width: 860px; height: 640px; display: flex; flex-direction: column; padding: 0 18px 18px; }
.header { position: relative; height: 40px; display: flex; align-items: center; justify-content: center; margin-top: -84px; }
.title { margin: 0; font: 700 22px var(--font-caps); color: var(--gold); text-shadow: 0 1px 2px #000; letter-spacing: 0.04em; }
.close { position: absolute; right: -6px; top: 4px; }
.points { text-align: center; margin: 8px 0 12px; font: 700 18px var(--font-serif); color: var(--ink); text-shadow: 0 0 2px var(--ink-outline); }
.columns { flex: 1; min-height: 0; display: flex; gap: 12px; }
```

- [ ] **Step 5 : Stub de MedalsList pour compiler**

Créer provisoirement `src/screens/MedalsScreen/MedalsList.tsx` :

```tsx
import type { MedalsDataset } from '@/data/medals.types';
import type { MedalsState } from './useMedalsState';
export function MedalsList({ state }: { ds: MedalsDataset; state: MedalsState }) {
  return <section style={{ flex: 1 }}>{state.title} — {state.visible.length} succès</section>;
}
```

Brancher `<MedalsScreen />` dans `App.tsx` pour `path === '/succes'`.

- [ ] **Step 6 : Vérifier**

```bash
npm test && npm run build
npm run dev -- --host 127.0.0.1 &
sleep 3 && npx playwright screenshot --viewport-size=1280,720 --wait-for-timeout=2500 "http://127.0.0.1:5173/succes" /tmp/claude-1000/medals-nav.png; kill %1
```

Lire la capture : cadre visible, titre « Succès », points, colonne de navigation avec « Personnage » déplié et « Équipement - 4/4 ». Ajuster `slice`, `margin-top` de l'en-tête et `background-size` des textures jusqu'à ce que ça ressemble à la capture de référence.

- [ ] **Step 7 : Commit**

```bash
git add src
git commit -m "feat(medals): fenêtre Succès, en-tête, points et navigation par catégories

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8 : Panneau Succès — liste, entrées, filtre, tooltip

**Files:**
- Create: `src/screens/MedalsScreen/MedalEntry.tsx`, `src/screens/MedalsScreen/MedalEntry.module.css`, `src/screens/MedalsScreen/MedalsList.module.css`, `src/screens/MedalsScreen/formatDate.ts`, `src/screens/MedalsScreen/formatDate.test.ts`
- Modify: `src/screens/MedalsScreen/MedalsList.tsx`

**Interfaces:**
- Consumes : `Medal`, `isComplete`, `currentRankOf`, `MedalBadge`, `ProgressBar`, `T`, `tex`, `MedalsState`.
- Produces : `formatGameDate(iso: string): string` → `JJ.MM.AAAA` ; `<MedalEntry medal />` ; `<MedalsList ds state />` complet.

- [ ] **Step 1 : Test échouant formatGameDate**

`formatDate.test.ts` :

```ts
import { it, expect } from 'vitest';
import { formatGameDate } from './formatDate';
it('formate comme le jeu : JJ.MM.AAAA', () => {
  expect(formatGameDate('2017-09-13')).toBe('13.09.2017');
  expect(formatGameDate('2020-01-29T10:00:00Z')).toBe('29.01.2020');
});
```

`npm test` → échec.

- [ ] **Step 2 : Implémentation**

`formatDate.ts` :

```ts
export function formatGameDate(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split('-');
  return `${d}.${m}.${y}`;
}
```

`npm test` → PASS.

- [ ] **Step 3 : MedalEntry**

`MedalEntry.tsx` :

```tsx
import { useState } from 'react';
import type { Medal } from '@/data/medals.types';
import { currentRankOf, isComplete } from '@/data/medals.logic';
import { T, tex } from '@/lib/assets';
import { MedalBadge } from '@/components/game/MedalBadge';
import { ProgressBar } from '@/components/game/ProgressBar';
import { formatGameDate } from './formatDate';
import s from './MedalEntry.module.css';

export function MedalEntry({ medal }: { medal: Medal }) {
  const complete = isComplete(medal);
  const rank = currentRankOf(medal);
  const [tip, setTip] = useState(false);
  const conditions = [...(medal.dressCollection ?? []), ...(medal.medalCollection ?? [])];
  const showBar = rank.completeProgress > 1 && !complete || (complete && rank.completeProgress > 1);
  const value = complete ? rank.completeProgress : medal.progress?.value ?? 0;

  return (
    <article className={`${s.entry} ${complete ? s.complete : ''}`} onMouseEnter={() => setTip(true)} onMouseLeave={() => setTip(false)}>
      <div className={s.badge}><MedalBadge score={rank.score} icon={medal.icon} complete={complete} /></div>
      <div className={s.paper} style={{ backgroundImage: `url(${tex(`${T.medals}/MedalPaper${complete ? 'Complete' : ''}`)})` }}>
        <header className={s.head}>
          <h3 className={s.name}>{medal.name}</h3>
          {medal.finishDate && <time className={s.date}>{formatGameDate(medal.finishDate)}</time>}
        </header>
        <p className={s.desc}>{rank.description}</p>
        {showBar && <div className={s.bar}><ProgressBar value={value} max={rank.completeProgress} /></div>}
        {conditions.length > 0 && (
          <ul className={s.conditions}>
            {conditions.map((c, i) => (
              <li key={i} className={c.success ? s.ok : s.ko}><span className={s.check}>✔</span>{c.description}</li>
            ))}
          </ul>
        )}
      </div>
      {tip && medal.ranks.length > 1 && (
        <div className={s.tooltip}>
          {medal.ranks.map((r, i) => (
            <div key={i} className={`${s.tipRank} ${i < medal.currentRank ? s.tipDone : ''}`}>
              <span className={s.tipScore}>{r.score}</span>
              <span>{r.description}</span>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}
```

`MedalEntry.module.css` :

```css
.entry { position: relative; display: flex; align-items: flex-start; gap: 8px; padding: 6px 4px; }
.badge { flex: 0 0 64px; padding-top: 6px; }
.paper {
  flex: 1; min-height: 96px; padding: 10px 18px 12px 22px;
  background: center / 100% 100% no-repeat; color: var(--ink);
}
.head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
.name { margin: 0; font: 700 17px var(--font-caps); color: #7a4a10; text-shadow: 0 0 1px rgba(255, 240, 200, 0.6); }
.complete .name { color: #6b3f0a; }
.date { font: 600 15px var(--font-serif); color: #4a3a20; white-space: nowrap; }
.desc { margin: 8px 0 6px; text-align: center; font: 600 15.5px var(--font-serif); line-height: 1.25; }
.bar { margin: 4px 8px 2px; }
.conditions { list-style: none; margin: 6px 0 0; padding: 0 6px; display: grid; grid-template-columns: 1fr 1fr; gap: 3px 16px; font: 600 15px var(--font-serif); }
.check { display: inline-block; width: 18px; color: var(--check-green); font-size: 14px; }
.ko .check { color: #8a8a8a; }
.ko { color: #6e6a5e; }
.tooltip {
  position: absolute; left: 72px; top: calc(100% - 4px); z-index: 5; min-width: 320px; max-width: 460px;
  padding: 10px 12px; background: rgba(12, 22, 12, 0.94); border: 1px solid #8fae7a; border-radius: 4px;
  color: #dfe9d8; font-size: 14px; box-shadow: 0 6px 16px rgba(0, 0, 0, 0.6);
}
.tipRank { display: flex; gap: 10px; padding: 2px 0; }
.tipDone { color: #9fd08a; }
.tipScore { flex: 0 0 34px; text-align: right; color: var(--gold); font-weight: 700; }
```

- [ ] **Step 4 : MedalsList complet**

`MedalsList.tsx` :

```tsx
import type { MedalFilter, MedalsDataset } from '@/data/medals.types';
import { T, tex } from '@/lib/assets';
import type { MedalsState } from './useMedalsState';
import { MedalEntry } from './MedalEntry';
import s from './MedalsList.module.css';

const FILTERS: { value: MedalFilter; label: string }[] = [
  { value: 'all', label: 'Tout' }, { value: 'completed', label: 'Terminés' }, { value: 'inProgress', label: 'En cours' },
];

export function MedalsList({ state }: { ds: MedalsDataset; state: MedalsState }) {
  return (
    <section className={s.content} style={{ backgroundImage: `url(${tex(`${T.medals}/FrameContent02`)})` }}>
      <header className={s.header} style={{ backgroundImage: `url(${tex(`${T.medals}/MedalHeader`)})` }}>
        <h2 className={s.title}>{state.title}</h2>
        <label className={s.filter}>
          <select value={state.filter} onChange={e => state.setFilter(e.target.value as MedalFilter)}>
            {FILTERS.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
          </select>
        </label>
      </header>
      <div className={s.list}>
        {state.visible.length === 0 && <p className={s.empty}>Aucun succès.</p>}
        {state.visible.map(m => <MedalEntry key={m.id} medal={m} />)}
      </div>
    </section>
  );
}
```

`MedalsList.module.css` :

```css
.content { flex: 1; min-width: 0; display: flex; flex-direction: column; background: center / 100% 100% no-repeat; padding: 10px 12px 12px; }
.header { height: 40px; display: flex; align-items: center; justify-content: space-between; padding: 0 12px; background: center / 100% 100% no-repeat; }
.title { margin: 0; font: 700 18px var(--font-caps); color: var(--gold); text-shadow: 0 1px 2px #000; }
.filter select {
  height: 26px; padding: 0 28px 0 10px; border: 1px solid #b9923f; border-radius: 3px;
  background: linear-gradient(#233a22, #142414); color: var(--gold); font: 600 15px var(--font-serif);
}
.list { flex: 1; min-height: 0; overflow-y: auto; padding: 8px 6px 8px 2px; scrollbar-width: thin; scrollbar-color: #b9923f #1d2c1a; }
.list::-webkit-scrollbar { width: 12px; }
.list::-webkit-scrollbar-track { background: #1d2c1a; border-radius: 6px; }
.list::-webkit-scrollbar-thumb { background: linear-gradient(#e6d18a, #8f6a1c); border-radius: 6px; border: 2px solid #1d2c1a; }
.empty { color: var(--ink); text-align: center; margin-top: 40px; }
```

- [ ] **Step 5 : Vérifier et ajuster contre la capture de référence**

```bash
npm test && npm run build
npm run dev -- --host 127.0.0.1 &
sleep 3 && npx playwright screenshot --viewport-size=1280,720 --wait-for-timeout=2500 "http://127.0.0.1:5173/succes" /tmp/claude-1000/medals.png
npx playwright screenshot --viewport-size=1280,720 --wait-for-timeout=2500 "http://127.0.0.1:5173/succes?q=laboratoire" /tmp/claude-1000/medals-search.png; kill %1
```

Lire les captures. Checklist visuelle par rapport à la capture in-game :
- trois entrées Équipement visibles : deux « Paré pour l'aventure ! » avec badge 10 et barre « 100 000 sur 100 000 » / « 21 500 sur 21 500 », « Dragon des temps nouveaux » badge 100 avec checklist deux colonnes et coches vertes ;
- dates à droite du nom ;
- parchemin clair sur fond brun ; en-tête turquoise ;
- filtre « Tout » en haut à droite.
Corriger tailles, marges et `background-size` jusqu'à correspondance raisonnable. La recherche `?q=laboratoire` doit afficher 3 entrées et le titre « Résultats de la recherche ».

- [ ] **Step 6 : Commit**

```bash
git add src
git commit -m "feat(medals): liste des succès — parchemin, médaillon, progression, conditions, filtre, tooltip

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9 : Finitions et vérification de bout en bout

**Files:**
- Modify: `README.md`, `src/screens/OpeningScreen/OpeningScreen.tsx` (si besoin), `.gitignore`

- [ ] **Step 1 : Parcours complet**

```bash
npm run dev -- --host 127.0.0.1 &
sleep 3
npx playwright screenshot --viewport-size=1280,720 --wait-for-timeout=3000 "http://127.0.0.1:5173/" /tmp/claude-1000/e2e-intro.png
npx playwright screenshot --viewport-size=1280,720 --wait-for-timeout=3000 "http://127.0.0.1:5173/?skipIntro" /tmp/claude-1000/e2e-menu.png
npx playwright screenshot --viewport-size=1280,720 --wait-for-timeout=3000 "http://127.0.0.1:5173/succes" /tmp/claude-1000/e2e-medals.png
kill %1
```

Lire les trois captures. Corriger tout écart bloquant (texture manquante = URL 404 dans la console : vérifier le nom dans `public/game/manifest.json`).

- [ ] **Step 2 : Sans assets**

```bash
mv public/game public/_game && npm run dev -- --host 127.0.0.1 &
sleep 3 && npx playwright screenshot --viewport-size=1280,720 "http://127.0.0.1:5173/succes" /tmp/claude-1000/no-assets.png; kill %1; mv public/_game public/game
```

Attendu : bandeau rouge « Assets du jeu absents », page navigable, aucune erreur JS non interceptée.

- [ ] **Step 3 : Qualité**

```bash
npm test && npm run build && python3 -m pytest tools/tests -q
git status --short   # public/game ne doit PAS apparaître
```

- [ ] **Step 4 : README — section « État du POC »**

Ajouter au README :

```markdown
## État du POC (2026-09)
- `/` : intro (première visite), puis menu vidéo avec panneau de connexion transformé en menu du site.
- `/succes` : panneau Succès fidèle au jeu, données mockées (`src/data/medals.mock.json`).
- Non fait : comptes, addon d'export, import de progression, icônes réelles des succès.
```

- [ ] **Step 5 : Commit final**

```bash
git add -A
git commit -m "docs: état du POC et vérification de bout en bout

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Auto-revue du plan

- **Couverture spec** : §3 formats → Task 2/3 ; §4.1 pipeline → Task 3 ; §4.2 modèle et mock → Task 4 ; §4.3 ouverture (intro, menu, recherche, boutons réaffectés, bande basse, localStorage, curseur) → Task 6 + curseur en Task 5 ; §4.4 panneau (cadre, en-tête, points, navigation, compteurs, filtre, entrées, barre, checklist, tooltip, ascenseur stylé) → Task 7/8 ; §4.5 routes → Task 5 ; §5 erreurs (assets manquants, vidéo, dataset) → Task 5/6/4 ; §6 tests → Task 2/3/4/6/8/9. La page Crédits de la spec est remplacée par la mention dans la bande basse et le bouton « Rejouer l'intro » ; écart assumé pour le POC.
- **Placeholders** : aucun TBD ; les ajustements visuels (`slice`, `background-size`) sont explicitement des étapes de calage avec critère (comparaison à la capture).
- **Cohérence des noms** : `tex`, `T`, `video`, `cursor`, `loadManifest`, `hasAssets` (Task 5) utilisés à l'identique en 6/7/8 ; `useMedalsState`/`MedalsState`/`firstNonEmpty` (Task 7) consommés en 8 ; `frameForScore`, `isComplete`, `currentRankOf`, `filterMedals`, `searchMedals`, `medalsOf`, `subCategoryCounts`, `parseDataset` (Task 4) consommés en 5/7/8 ; `hoverState` de `GameButton` utilisé pour la croix (`Highlight`).
