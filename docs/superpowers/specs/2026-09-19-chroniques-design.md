# Chroniques — archive des écrans de lancement par version, avec leur thème musical

Date : 2026-09-19 · Statut : validé en discussion · Priorité : avant la page Musiques.

## 1. Objectif
Une page `/chroniques` qui présente, version par version, l'écran de lancement du jeu (vidéo du menu en boucle quand elle existe, sinon le fond statique du menu) et le thème musical principal associé, jouable. Accessible depuis la barre de boutons de l'accueil (icône journal `ButtonQuestlog`).

## 2. Sources (clients archivés de l'utilisateur, tous en lecture seule)

| Version affichée | Client | Fond | Thème |
|---|---|---|---|
| 1.1 | `F:\ALLODS ONLINE SERVER\Allods 1.0\allods\Client` (game.version 1.1.02.0) — `Interface.pak`, `SFX_Music.pak` | texture `Interface/Wrap/MainMenu/Main2/Background*` | `Music_Menu.fsb` (nom du subsong menu à déterminer) |
| 2.0 | `F:\ALLODS ONLINE SERVER\Clients\Allods 2.0.04` (2.0.04.49) | `Main2/Background` | idem |
| 3.0 | `F:\ALLODS ONLINE SERVER\Clients\AllodsOnline3.0.2.19[5.12GB]-20200522T111620Z-001\AllodsOnline3.0.2.19[5.12GB]` | idem | idem |
| 4.0 | `F:\ALLODS ONLINE SERVER\Allods 4.2\Allods Nova\Allods Nova` (4.0.02.42) | idem | idem |
| 7.0 | `F:\ALLODS ONLINE SERVER\Clients\Allods Revelation 7.0` (7.0.00.00) | `Main2/Background*` ou Lobby | idem |
| 8.0 | `I:\Backups\GameClients\AllodsClient\MyGames\Allods Online FR 8.0` (8.0.02.61.1) | `Main2/BackgroundGOG` | idem |
| 9.0 | `I:\…\Allods Online FR 9.0.01.89` | `Main2/Background*` | idem |
| 10.0 → 15.0 | vidéos `Video/<N>_0Events/MainMenu/{Intro,MainMenu}.ogv` du client 16.0 ; thème : `Music_Menu.fsb` du client 15.0 (`I:\…\Allods Online FR (FR) 15.0.03.23.2 (end of patch)`) pour 15.0, et pour 10–14 le thème du client le plus proche disponible (à indiquer comme « approximation » dans les données) | vidéo | fsb |
| 16.0 | client courant (`H:\MyGames\Allods Online FR (FR)`) | vidéo | `MainMenu_DesertDreams` / `ThePowerOfMetal` (au choix de l'utilisateur) |
| 17.0 | `H:\MyGames\AllodsRU` (17.0.01.64) | `Video/17_0Events/MainMenu/MainMenu.ogv` | `Music_Menu.fsb` du client RU |

Le fond statique est décodé avec `tools/uitexture.py` (même format sur toutes les versions à vérifier ; en cas d'échec sur une vieille version, le noter et passer). Les banques FMOD se décodent avec vgmstream comme dans `tools/extract_audio.py` ; le subsong « thème » est choisi par nom (`MainMenu*`, `MainTitle`, `Menu*`) puis par durée, et documenté dans le manifeste avec les alternatives.

## 3. Pipeline
- `tools/clients_manifest.json` : liste des versions ci-dessus avec chemin WSL du client, packs à ouvrir, entrée de fond (texture ou vidéo), banque + subsong du thème, et méta (`label`, `year` si connu, `note`).
- `tools/extract_archive.py` : pour chaque version, écrit `public/game/archive/<version>/background.png` ou `menu.{webm,mp4}` (+ `intro.{webm,mp4}` si présent), `theme.{ogg,mp3}`, et l'index `public/game/archive.json` (`[{version, label, media: 'video'|'image', duration, theme: {name, duration}, note}]`). Idempotent, `--only 8.0`, `--force`, avertit et continue quand un client ou une entrée manque (les disques externes peuvent être absents). Réutilise `decode_uitexture`, `trim_transparent_padding`, et les fonctions de `extract_audio.py` (import, pas de copie).
- Tests pytest : sélection du subsong thème par nom/durée (fonction pure), génération de l'index, tolérance aux clients absents (monkeypatch).

## 4. Page
- Route `/chroniques`. Fond : l'écran de lancement de la version courante en plein écran (vidéo en boucle ou image), avec le même traitement que l'accueil. Par-dessus, en bas, une **frise horizontale** de versions (pilules du jeu, 1.1 → 17.0) ; la version active est en surbrillance ; flèches gauche/droite (sprites `scroll-*` ou touches ← →).
- Cartouche en haut à gauche dans le style plaque de titre : « Allods Online 8.0 » + note éventuelle (« Game of Gods », etc. si fournie plus tard) ; en bas à droite le lecteur du thème : nom de la piste, durée, bouton lecture/pause dans le style des boutons du jeu.
- Changer de version : fondu croisé de la vidéo/image et du thème (via `useGameAudio.setTrack` étendu pour accepter une source arbitraire, ou une piste `archive` dédiée) ; la musique d'ambiance du site est mise en pause pendant la visite, reprise à la sortie.
- Retour à l'accueil par la croix du jeu en haut à droite (comme le panneau Succès) ; son d'ouverture/fermeture identiques à ceux du panneau.
- Bouton d'accès : `ButtonQuestlog*` dans `GameActionBar`, libellé « Chroniques ».
- Versions dont le média manque (client absent au moment de l'extraction) : carte avec fond `Background_14_0_Temp` assombri et mention « Média non extrait ».

## 5. Vérification
Captures 1920×1009 de `/chroniques` sur 3 versions (une vidéo, une image, une manquante) ; test de la frise au clavier ; gates habituels ; README section « Chroniques » (comment ajouter une version dans `clients_manifest.json`).
