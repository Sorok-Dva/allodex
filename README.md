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
- Non fait : comptes, addon d'export, import de progression, icônes réelles de tous les succès.

## Itération 2 (2026-09)

Reprise des deux écrans pour qu'ils soient visuellement identiques au jeu, à partir de captures live du client (spec détaillée : `docs/superpowers/specs/2026-09-19-iteration-2-fidelite-design.md`).

- **Accueil** (`/`) : le panneau de connexion et le champ de recherche du POC v1 n'existent plus. L'accueil affiche la **barre de boutons du jeu**, en bas à droite, comme en jeu : **Succès** (actif, ouvre `/succes`) et **Personnage** (« bientôt » : au survol, infobulle « Mon compte — bientôt » ; clic sans effet).
- **Panneau Succès** (`/succes`) : reconstruit à l'échelle **1:1** (fenêtre 886 × 592 px) à partir de captures live du client — chrome (plaque de titre, bandeau, rails, pilules, ascenseurs), infobulle et menu déroulant compris. La vue **Progression** (barres par catégorie, terminé récemment) est prévue pour l'itération suivante ; la catégorie « Progression » n'a pour l'instant aucun effet au clic.
- **Données** : `src/data/medals.mock.json` compte 64 succès dont **38 sont des `placeholder`** (`placeholder: true`) — des succès de la catégorie Astral générés pour que les compteurs affichés (« Astral ouvert - 5/29 », « Allods Astraux - 15/15 ») correspondent aux totaux réels du jeu, en attendant un import de la vraie progression du joueur.
- **Recapturer les références du jeu.** Les captures live (`refs/*.png`, dossier **git-ignoré** : elles contiennent le HUD et le personnage de l'utilisateur) sont la source de vérité des mesures ; les sprites qui en sont découpés (`public/game/sprites/*.png`, **jamais versionnés**, comme le reste de `public/game/`) reconstituent le chrome que le client ne fournit pas comme textures isolées (plaque de titre, bandeau, rails, pilules, ascenseurs, cadre d'infobulle, menu déroulant…). Pour recapturer :
  1. Copier `tools/capture_game.ps1` côté Windows (p. ex. dans `C:\Users\<vous>\allodex-captures\`), client `AOgame` ouvert sur l'écran voulu.
  2. Lancer depuis WSL : `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\<vous>\allodex-captures\capture_game.ps1" -Out "C:\Users\<vous>\allodex-captures\x.png"`, puis copier le PNG dans `refs/` du projet.
  3. Découper les sprites : `python3 tools/cut_sprites.py` (lit `tools/sprites_manifest.json`, écrit `public/game/sprites/*.png` et `public/game/sprites.json`).
