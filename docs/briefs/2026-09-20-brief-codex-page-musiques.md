# Brief pour Codex — page « Musiques » d'Allodex

Rédigé le 2026-09-20 par l'agent qui a construit le site jusqu'ici, pour qu'un autre agent
(Codex) réalise la page Musiques **dans la continuité exacte** de ce qui existe. Lis ce brief
en entier, puis `README.md`, puis les fichiers cités, avant d'écrire une ligne.

## 0. Ce qu'est Allodex, en trois phrases
Site fan (non officiel) sur Allods Online, en français avec i18n fr/en, dont chaque écran
**reproduit l'interface du jeu au pixel** à partir des assets du client (textures DXT
décodées, sprites découpés sur des captures du jeu, sons FMOD décodés). Le dépôt est
`~/projects/allodex` (Vite 8 + React 19 + TypeScript 6 strict + Vitest ; outils Python 3
avec Pillow/numpy/pytest). Tout ce qui vient du client est généré dans `public/game/`
(**git-ignoré**) par des scripts `tools/*.py` pilotés par des manifestes JSON : seuls
`tools/`, `src/`, `docs/`, `README.md` sont versionnés. Ne commite jamais `public/game/`,
`refs/`, `.superpowers/`.

Écrans existants : accueil (`/`, vidéo d'intro puis menu, barre de boutons du jeu),
`/succes` (fenêtre des Succès 1:1), `/chroniques` (écrans de lancement par version, avec
thème musical, défilement automatique, fiche de version). La page Musiques est la
**quatrième** et la dernière demandée par l'utilisateur pour cette phase.

## 1. Ce que l'utilisateur veut (ses mots)
« une page avec toutes les musiques du jeu », bouton d'accès dans la barre d'actions de
l'accueil avec « l'icône de l'emote trompette (ou guitare) ». Rien d'autre n'a été précisé :
pas de refonte, pas d'options non demandées, quota utilisateur limité → **rester sobre et
finir**.

## 2. Comment je l'aurais fait

### 2.1 Pipeline : `tools/extract_music.py` + `tools/music_manifest.json`
- Source : le client courant `/mnt/h/MyGames/Allods Online FR (FR)/data/Packs/SFX_Music.Mini.pak`
  (ZIP), entrées `SFX/Music/*.fsb` : `Music_Menu` (5), `Music_Ingame` (13), `Music_Ingame01`
  (2), `Music_Zone` (90), `Music_StartZones` (14), `Music_Race` (9), `Music_RacesInstruments`
  (7), `Music_Astral` (3), `Music_Astral_hangar`, `Music_ASS`, `Music_Isa` (5),
  `Music_Zone_Eden` (2), `Music_Zone_Jigran` (2), `Music_Zone_Kadagan` (5). Le client RU 17.0
  (`/mnt/h/MyGames/AllodsRU`) ajoute `Music_Zone_Kvator` (6) et deux thèmes de menu de plus :
  prévoir `clients` multiples dans le manifeste, la première occurrence d'un nom de piste
  gagne (FR d'abord), les pistes seulement-RU sont ajoutées avec `client: "17.0"`.
- **Réutiliser `tools/extract_audio.py`** (import, pas de copie) : `extract_pak_entry_bytes`,
  `fsb_payload_from_bytes`, `run_vgmstream`, `encode_outputs(wav, out_base, "tracks")`,
  `probe_duration`. Regarde comment `tools/extract_archive.py` (`list_subsongs`,
  `decode_subsong`, `fold_to_stereo`, `_stem`) fait la même chose pour un seul subsong :
  généralise à « tous les subsongs de toutes les banques ». vgmstream natif :
  `/home/llyam/projects/allods-texts-packer/voices/tools/vgmstream/vgmstream-cli` ; il
  segfaulte sur les banques CELT des vieux clients → repli WASM dans
  `/home/llyam/projects/allods-texts-packer/voices/vgmstream_wasm` (déjà géré dans
  `extract_archive.decode_subsong`). Les pistes `*_adaptive`/`*_Adaptive` sont des stems
  4 canaux : garder la première paire stéréo (`fold_to_stereo`), ne jamais sommer.
- Sorties : `public/game/music/<slug>.ogg` + `.mp3`, index `public/game/music.json` =
  liste triée de `{ id, name (nom interne, ex. "AC5_Main_NM"), title: {fr, en} | null,
  bank, group, duration, ogg, mp3, client }`. `group` = catégorie d'affichage déduite de la
  banque (`Menu`, `Zones`, `Zones de départ`, `Peuples`, `Instruments des peuples`, `Astral`,
  `Donjons/Combat` pour Ingame, `Eden`, `Jigran`, `Kadagan`, `Kvator`, `Isa`) — table dans le
  manifeste, pas en dur dans le code.
- Titres humains : `tools/music_titles.json` `{ "<nom interne>": {"fr": "...", "en": "..."} }`,
  rempli à la main pour ce qui est sûr (thèmes de menu : `MainMenu_DesertDreams` → « Desert
  Dreams », etc.), **sans inventer** : piste sans titre → on affiche le nom interne nettoyé
  (`_` → espace, suffixes `_NM`/`_Adaptive` retirés). La bande originale officielle
  (`https://allods.ru/about.php?show=soundtrack`, page en cp1251, 61 MP3 avec titres russes)
  peut servir plus tard à nommer ; ne pas bloquer dessus.
- Idempotent (`--force` pour refaire), `--only <banque>`, avertit et continue si un client
  manque. Tests pytest : slug/nettoyage des noms, groupage, construction de l'index sur des
  streams factices (monkeypatch de vgmstream/ffmpeg comme dans `tools/tests/test_extract_archive.py`).
- Ajouter la commande à `npm run extract` (voir `package.json`) et au README.

### 2.2 Front : `/musiques`
- Route dans `src/App.tsx` (routeur maison `src/lib/router.tsx` : `navigate`, `useRoute`).
- Bouton dans `GameActionBar` de l'accueil (`src/screens/OpeningScreen/OpeningScreen.tsx`,
  tableau des boutons) : les boutons existants utilisent les textures
  `Interface/Ingame/ContextPinMenu3/textures/Button<X>{Normal,Pressed,Highlight}` (rendu à
  deux couches, la `Highlight` est un halo). L'icône emote n'a pas ces trois états : afficher
  l'icône `Interface/Icons/Special/Emotions/PlayedTrumpet` (ou `Playing_ElectricGuitar`)
  **par-dessus** un bouton vide du même style (regarde s'il existe un `Button*Normal` neutre
  dans ContextPinMenu3 ; sinon dérive un fond depuis un bouton existant avec l'option
  `inpaint_disc`/`derive` de `tools/cut_sprites.py`, comme on l'a fait pour le bouton son
  `medallion-normal`). Ajoute le préfixe/fichier de texture dans `tools/assets_manifest.json`
  (`texture_files`) et relance `python3 tools/extract_assets.py --skip-video`.
- Mise en page : **la fenêtre du jeu des Succès** (`src/screens/MedalsScreen/MedalsWindow*` :
  cadre, plaque de titre, bandeau, colonne de navigation à pilules `pill-full`, colonne de
  contenu, scrollbar `GameScrollbar`) réutilisée telle quelle — extraire ce chrome dans un
  composant partagé si nécessaire, **sans changer le rendu des Succès** (les tests de
  MedalsScreen doivent rester verts). Navigation = les `group`s ; contenu = liste des pistes
  (titre, nom interne en petit, durée `m:ss` avec le deux-points élargi comme
  `ThemePlayer.Duration`, bouton lecture/pause = pilule courte de `ThemePlayer`). Piste en
  cours surlignée (`pill-full-open`).
- Audio : **le moteur existant** `src/lib/audio/AudioProvider.tsx` via `useGameAudio()` :
  `playExternal(id, {ogg, mp3}, {loop:false, crossfadeMs})`, `pauseMusic`, `resumeAmbient`,
  `playing`, `external`, `ended` (déjà utilisé par les Chroniques pour enchaîner). À l'entrée :
  `playSfx('medals-open')` + `pauseMusic()` ; à la sortie (croix, `navigate('/')`) :
  `playSfx('medals-close')` + `resumeAmbient()`. Quand `ended === id` de la piste en cours →
  piste suivante du groupe (comme le défilement des Chroniques). Le bouton son
  (`SpeakerToggle`) en haut à droite comme sur les Chroniques (voir `.speaker` / `.close`
  dans `ChroniclesScreen.module.css` pour les positions : croix `right:24 top:20`, son
  `right:66 top:19`).
- i18n : `useI18n().t('…')`, toutes les chaînes dans `src/lib/i18n/messages.ts` (fr **et** en,
  un test vérifie la parité des clés) ; titres de pistes via `pick(track.title, lang)`.
- Tests Testing Library : rend les groupes et les pistes ; clic lecture → `playExternal`
  avec la bonne source ; `ended` → piste suivante ; croix → `navigate('/')` + SFX ; version
  sans `music.json` (assets absents) → message « Musiques non extraites ».
- Captures Playwright 1920×1009 pour contrôle visuel (Playwright dans
  `/home/llyam/projects/42portfolio/node_modules/playwright`, voir les scripts `.mjs` du
  scratchpad : `chromium.launch()`, viewport 1920×1009, `?lang=fr` obligatoire car le
  Chromium headless est en anglais). Dev server : `npm run dev -- --host 0.0.0.0`.

### 2.3 Gates et commits
`npm test && npm run build && python3 -m pytest tools/tests -q` verts avant chaque commit.
Commits en français, un par tâche (pipeline, puis page), terminés par
`Co-Authored-By: Codex <noreply@openai.com>` (ou l'attribution demandée par l'utilisateur).
Mettre à jour `README.md` (section « Musiques ») et la note `_note` des manifestes.

## 3. Pièges connus (chacun m'a coûté du temps)
- `public/game/manifest.json`, `sprites.json`, `audio.json`, `archive.json` sont chargés par
  `loadManifest()` (`src/lib/assets.ts`) : ajouter `music.json` au même endroit, avec un
  accesseur typé (`musicTracks()`), et tolérer son absence.
- **Aucun filtre SVG/CSS côté navigateur** pour corriger les couleurs : tout est cuit dans
  les PNG par les outils (`color_offsets`, `derive`). Le Chrome de l'utilisateur a un mode
  sombre forcé : `color-scheme: dark` est déjà déclaré, ne pas y toucher.
- Le texte de la plaque de titre est calé en haut de la plaque (`padding-top: 4px`,
  `line-height: 19px`, 15–16 px), pas centré verticalement.
- Les pilules `pill-full` ont deux ornements de 24 px : un bouton nine-slice plus étroit que
  ~60 px les fait se chevaucher.
- Ne pas afficher de notes techniques à l'écran (l'utilisateur les a fait retirer) ; les
  garder dans les JSON.
- Le glyphe `Highlight` des boutons ronds est en DXT1 sans alpha (fond noir) :
  `mix-blend-mode: screen`.
- `TaskOutput`/lecture des transcriptions d'agents : ne jamais `cat` un fichier `.output`
  d'agent, il fait exploser le contexte.
- Un agent travaille peut-être encore sur `tools/extract_menu_scene.py`,
  `tools/scenes_manifest.json`, `src/components/game/MenuScene*` et
  `src/screens/ChroniclesScreen/ChroniclesScreen.tsx` (scènes de menu three.js, plan
  `docs/superpowers/plans/2026-09-19-scenes-menu-3d.md`) : **ne modifie pas ces fichiers**,
  et rebase si `main` a avancé.

## 4. Où regarder d'abord
`README.md` · `docs/superpowers/specs/2026-09-19-chroniques-design.md` (page la plus proche
en esprit) · `src/screens/ChroniclesScreen/{ChroniclesScreen,ThemePlayer}.tsx` (audio,
i18n, lecteur) · `src/screens/MedalsScreen/MedalsWindow.tsx` (chrome de fenêtre) ·
`tools/extract_archive.py` (vgmstream, banques FMOD) · `tools/audio_manifest.json`
(`_candidates` liste déjà les subsongs de Music_Menu) · mémoire de session dans
`C:\Users\Llyam\allodex-captures\` (captures et sheets de contrôle).
