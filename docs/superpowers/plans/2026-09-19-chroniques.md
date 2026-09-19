# Chroniques — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Deux tâches séquentielles (pipeline, puis page).

**Goal:** Page `/chroniques` : écran de lancement + thème musical par version d'Allods Online, extraits des clients archivés de l'utilisateur.

**Spec:** `docs/superpowers/specs/2026-09-19-chroniques-design.md` (autorité).

## Global Constraints
- Tout en lecture seule sur les clients ; sorties dans `public/game/archive/` (git-ignoré) ; seuls `tools/`, `src/`, docs versionnés.
- Réutiliser `tools/uitexture.py`, `tools/extract_audio.py` (import), `src/lib/audio` (`useGameAudio`), `GameActionBar`, `GameStrip`/sprites (`pill-full`, `title-plate-*`, `scroll-*`), `GameTooltip`.
- Libellés FR ; commits FR ; TS strict ; gates `npm test && npm run build && python3 -m pytest tools/tests -q`.
- Quota utilisateur limité : pas de refonte, pas d'options non demandées.

### Task 1 : pipeline `extract_archive.py`
**Files:** create `tools/clients_manifest.json`, `tools/extract_archive.py`, `tools/tests/test_extract_archive.py`.
**Interfaces:** `pick_theme_subsong(streams: list[{index,name,duration}]) -> int` (préférence `MainMenu*` > `MainTitle` > `Menu*` > plus longue) ; `build_index(entries) -> list[dict]` ; CLI `--client-root-override VERSION=PATH`, `--only`, `--force`, `--skip-video`.
- [ ] Manifeste rempli avec les 11 versions de la spec §2 (chemins WSL `/mnt/f/...`, `/mnt/i/...`, `/mnt/h/...`), en vérifiant l'existence de chaque pack listé et le nom exact des entrées de fond (lister `Interface*.pak` de chaque client : `Wrap/MainMenu/Main2/Background*`). Pour 10–14 : vidéo du client 16.0, thème = client 15.0 marqué `"theme_note": "approximation (client 15.0)"`.
- [ ] Tests RED → GREEN pour `pick_theme_subsong`, `build_index`, client absent → avertissement + entrée `media: null`.
- [ ] Extraction réelle de toutes les versions ; contrôler visuellement 3 fonds (`Read`) et les durées des thèmes ; noter dans le rapport les versions incomplètes et pourquoi.
- [ ] Commit `feat(tools): extraction des écrans de lancement et thèmes par version (Chroniques)`.

### Task 2 : page `/chroniques`
**Files:** create `src/screens/ChroniclesScreen/ChroniclesScreen.tsx` (+css), `VersionTimeline.tsx` (+css), `ThemePlayer.tsx` (+css), tests ; modify `src/lib/assets.ts` (`loadManifest` charge `archive.json` ; `archiveEntries()`), `src/lib/audio/AudioProvider.tsx` (`setTrack` accepte `{ src: {ogg,mp3}, loop }` ou nouvelle méthode `playExternal`, et `pause/resume` de l'ambiance), `src/App.tsx` (route), `src/screens/OpeningScreen/OpeningScreen.tsx` (bouton `ButtonQuestlog` « Chroniques »), README.
- [ ] Tests (Testing Library) : frise rend N versions et met en surbrillance l'active ; ← → changent la version ; version sans média → carte « Média non extrait » ; croix → `navigate('/')` + `medals-close` ; montage → `medals-open` et pause de l'ambiance.
- [ ] Rendu : fond plein écran (vidéo `loop muted` ou image `cover`), cartouche plaque de titre, frise en pilules (sprites `pill-full` + surbrillance `pill-full-open`), lecteur du thème (nom, durée, bouton lecture) ; fondu 600 ms à chaque changement.
- [ ] Captures 1920×1009 : version vidéo (16.0), version image (8.0), version manquante ; lecture avec `Read` ; ajustements.
- [ ] Commit `feat(chroniques): page des écrans de lancement par version avec thème musical`, README.
