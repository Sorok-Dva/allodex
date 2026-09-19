# Allodex

Allodex, site fan Allods Online. POC : écran d'ouverture du jeu + panneau Succès, rendus avec les assets du client.

## Prérequis
- Node 20+, Python 3.10+, ffmpeg (avec libvpx-vp9 et libx264)
- Client Allods Online FR installé (par défaut `/mnt/h/MyGames/Allods Online FR (FR)`)
- Les captures d'écran du plan de vérification utilisent une installation de Playwright empruntée à un projet voisin ; outillage optionnel, pas nécessaire pour lancer le site.

## Installation
    npm install
    pip install -r tools/requirements.txt
    npm run extract -- --client "/mnt/h/MyGames/Allods Online FR (FR)"   # écrit public/game/
    npm run dev

Le dossier client peut aussi être fourni via la variable d'environnement `ALLODS_CLIENT_DIR`, en alternative à `--client` :

    ALLODS_CLIENT_DIR="/mnt/h/MyGames/Allods Online FR (FR)" npm run extract

## Tests
    npm test
    python3 -m pytest tools/tests

Les assets extraits sous `public/game/` appartiennent à My.Games et ne sont pas versionnés ; `public/fonts/allods.ttf` (police du jeu, récupérée depuis le launcher ADC), lui, est versionné.

## État du POC (2026-09)
- `/` : intro (première visite), puis menu vidéo avec, en bas à droite, la barre de boutons du jeu (voir « Itération 2 » ci-dessous — le panneau de connexion et le champ de recherche du POC v1 ont été retirés).
- `/succes` : panneau Succès fidèle au jeu, données mockées (`src/data/medals.mock.json`). La progression et les paliers restent fictifs.
- `/chroniques` : archive des écrans de lancement, version par version, avec leur thème musical (voir « Chroniques » ci-dessous).
- Non fait : comptes, addon d'export, import de progression, icônes réelles de tous les succès.

## Audio

Musique de menu, musique d'ambiance et sons d'interface (ouverture/fermeture de la
fenêtre Succès, clic) sont extraits des banques `.fsb`/`.bsb` du client par
`tools/extract_audio.py` (`python3 tools/extract_audio.py`, options `--client`/
`ALLODS_CLIENT_DIR` comme pour `npm run extract`). Il écrit, comme le reste de
`public/game/` : `public/game/audio/<nom>.{ogg,mp3}` et l'index
`public/game/audio.json` (`{nom: {duration, loop}}`), ni l'un ni l'autre versionnés.

Le morceau/son associé à chaque nom logique (`menu`, `ambient`, `medals-open`,
`medals-close`, `ui-click`) est déclaré dans `tools/audio_manifest.json` (banque,
entrée, numéro de subsong) : pour changer une piste, éditer ce fichier puis relancer
l'extraction. Le rapport de spike (`.superpowers/sdd/2026-09-19-iteration-2b-corrections/
audio-spike-report.md`) documente les choix retenus et les alternatives écoutables.

Côté site, un unique moteur audio (`src/lib/audio/AudioProvider.tsx` +
`useGameAudio()`) est monté dans `App` : rien ne joue avant un premier geste
utilisateur (politique d'autoplay des navigateurs), la musique change de piste avec
un fondu croisé, et l'état muet est persisté dans `localStorage`
(`allodex:audio-muted`) — jamais relancé automatiquement si l'utilisateur avait coupé
le son. Le même moteur joue aussi les sources hors index (`playExternal`, utilisé par
les thèmes des Chroniques) : `pauseMusic` met la piste du site en pause sans oublier sa
position, `resumeAmbient` la reprend en fondu. L'interrupteur haut-parleur (bandeau du bas sur `/`, coin bas-droit sur
`/succes`) coupe la sortie (`.muted`) sans jamais mettre en pause la musique.

## Chroniques

`/chroniques` présente, version par version (1.1 → 17.0), l'écran de lancement du jeu
en plein écran — la vidéo du menu en boucle quand le client en avait une, sinon le fond
statique — et le thème musical du menu de cette version, jouable. La version affichée
vit dans l'URL (`/chroniques?v=8.0`) ; la frise de pilules en bas d'écran, les touches
← → et les flèches du jeu en changent, avec un fondu croisé de 600 ms sur l'image
**et** sur la musique. Pendant la visite, la musique d'ambiance du site est mise en
pause et reprend là où elle en était à la sortie (croix en haut à droite). Une version
dont le client n'était pas monté à l'extraction s'affiche sur le fond de secours
assombri, avec la mention « Média non extrait ».

Les médias viennent de `tools/extract_archive.py`, qui écrit — comme le reste de
`public/game/`, donc **non versionné** — `public/game/archive/<version>/`
(`background.png` ou `menu.{webm,mp4}` + `intro.{webm,mp4}`, `theme.{ogg,mp3}`) et
l'index `public/game/archive.json`.

**Ajouter une version.** Éditer `tools/clients_manifest.json` :
1. Déclarer le client dans `clients` (`root` : chemin WSL du client archivé, en lecture
   seule ; `game_version` pour mémoire).
2. Ajouter une entrée dans `versions` avec `version`, `label`, `client`, puis soit
   `video` (`Video/<N>_0Events/MainMenu/{Intro,MainMenu}.ogv`), soit `background`
   (pack + entrée `(UITexture).bin`, ou `layers` pour les menus composés des clients
   1.x), plus `theme` (banque `SFX/Music/Music_Menu.fsb` ; `prefer` force un subsong par
   son nom, sinon le choix est `MainMenu*` > `MainTitle` > `Menu*` > la plus longue).
   `note` et `theme_note` sont repris tels quels par la page.
3. Extraire cette seule version :

        python3 tools/extract_archive.py --only 8.0          # --force pour réécrire
        python3 tools/extract_archive.py --only 8.0 --skip-video   # sans transcodage vidéo

Un disque non monté n'est pas une erreur : l'outil avertit, laisse `media: null` dans
l'index et conserve les versions déjà extraites (il est idempotent).

## Itération 2 (2026-09)

Reprise des deux écrans pour qu'ils soient visuellement identiques au jeu, à partir de captures live du client (spec détaillée : `docs/superpowers/specs/2026-09-19-iteration-2-fidelite-design.md`).

- **Accueil** (`/`) : le panneau de connexion et le champ de recherche du POC v1 n'existent plus. L'accueil affiche la **barre de boutons du jeu**, en bas à droite, comme en jeu : **Succès** (actif, ouvre `/succes`) et **Personnage** (« bientôt » : au survol, infobulle « Mon compte — bientôt » ; clic sans effet).
- **Panneau Succès** (`/succes`) : reconstruit à l'échelle **1:1** (fenêtre 886 × 592 px) à partir de captures live du client — chrome (plaque de titre, bandeau, rails, pilules, ascenseurs), infobulle et menu déroulant compris. La vue **Progression** (barres par catégorie, terminé récemment) est prévue pour l'itération suivante ; la catégorie « Progression » n'a pour l'instant aucun effet au clic.
- **Données** : `src/data/medals.mock.json` compte 64 succès dont **38 sont des `placeholder`** (`placeholder: true`) — des succès de la catégorie Astral générés pour que les compteurs affichés (« Astral ouvert - 5/29 », « Allods Astraux - 15/15 ») correspondent aux totaux réels du jeu, en attendant un import de la vraie progression du joueur.
- **Recapturer les références du jeu.** Les captures live (`refs/*.png`, dossier **git-ignoré** : elles contiennent le HUD et le personnage de l'utilisateur) sont la source de vérité des mesures ; les sprites qui en sont découpés (`public/game/sprites/*.png`, **jamais versionnés**, comme le reste de `public/game/`) reconstituent le chrome que le client ne fournit pas comme textures isolées (plaque de titre, bandeau, rails, pilules, ascenseurs, cadre d'infobulle, menu déroulant…). Pour recapturer :
  1. Copier `tools/capture_game.ps1` côté Windows (p. ex. dans `C:\Users\<vous>\allodex-captures\`), client `AOgame` ouvert sur l'écran voulu.
  2. Lancer depuis WSL : `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\<vous>\allodex-captures\capture_game.ps1" -Out "C:\Users\<vous>\allodex-captures\x.png"`, puis copier le PNG dans `refs/` du projet.
  3. Découper les sprites : `python3 tools/cut_sprites.py` (lit `tools/sprites_manifest.json`, écrit `public/game/sprites/*.png` et `public/game/sprites.json`).
