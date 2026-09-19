# Scènes de menu animées — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Deux tâches séquentielles.

**Spec :** `docs/superpowers/specs/2026-09-19-scenes-menu-3d-design.md` (autorité). Spike de référence : `.superpowers/amm-spike/` (render2.py, tex.py, README-textured.md) — à refactoriser dans `tools/`, pas à copier tel quel.

## Global Constraints
- Lecture seule sur les clients et l'arbre serveur ; sorties dans `public/game/archive/<v>/` (git-ignoré) ; seuls `tools/`, `src/`, docs, `package.json` versionnés.
- Réutiliser `tools/uitexture.py` (DXT), `tools/extract_archive.py` (index `archive.json` : ajouter la clé `scene` sans casser l'existant), `src/lib/assets.ts` (`ArchiveEntry.scene`).
- TS strict, libellés FR, commits FR, gates `npm test && npm run build && python3 -m pytest tools/tests -q`. Quota limité : pas d'options non demandées.

### Task 1 : pipeline `extract_menu_scene.py`
**Files:** create `tools/extract_menu_scene.py`, `tools/scenes_manifest.json`, `tools/tests/test_extract_menu_scene.py` ; modify `tools/extract_archive.py` (lit `scene.glb`/`scene.json` s'ils existent → `entry.scene`), README.
- [ ] Manifeste : 5 versions (racine xdb, source des `.bin` (dossier ou paks), caméra initiale du spike, axe haut).
- [ ] Parseur xdb (ElementTree) + lecture des chunks + décodage VB/IB + textures (via `tools.uitexture`) ; hiérarchie d'attaches ; export glTF `.glb` (écriture manuelle, pas de dépendance ; ou `pygltflib` si déjà installé — vérifier) ; `scene.json`.
- [ ] Rétro-ingénierie du blob `(SkeletalAnimation).bin` (AMM_7_0_FrontShips : 114 584 o, 601 images, joints du Geometry) : hypothèses à tester = par joint, par image, quaternion (4×f32 ou 4×i16) + translation (3×f32) ; vérifier avec `aabb`/`aabbLastFrame` du xdb (la boîte des positions animées doit y tenir). Si non concluant après un effort raisonnable : export sans animation + note explicite dans le rapport et le README.
- [ ] Tests RED → GREEN ; extraction réelle des 5 versions ; contact sheet de contrôle (rendu logiciel du spike réutilisable pour vérifier le glb, ou capture du viewer en Task 2).
- [ ] Commit `feat(tools): export glTF des scènes de menu animées (4.0 → 8.0)`.

### Task 2 : `MenuScene` three.js dans les Chroniques
**Files:** `package.json` (+ `three`, `@types/three`), create `src/components/game/MenuScene.tsx` (+css, tests), modify `src/lib/assets.ts`, `src/screens/ChroniclesScreen/ChroniclesScreen.tsx` (MediaLayer), README.
- [ ] Tests : repli image sans WebGL ; montage/démontage (dispose appelé) ; reduced-motion ; caméra lue depuis `scene.json`.
- [ ] Rendu, tri des transparents, additif, boucle d'animation, `cover`.
- [ ] Captures Playwright des 5 versions (WebGL logiciel) → `C:\Users\Llyam\allodex-captures\chroniques-scenes\` ; comparaison au spike ; ajustement des caméras dans `scenes_manifest.json` si nécessaire (et re-export).
- [ ] Commit `feat(chroniques): scènes de menu animées en three.js`, README.
