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
- `/` : intro (première visite), puis menu vidéo avec panneau de connexion transformé en menu du site.
- `/succes` : panneau Succès fidèle au jeu, données mockées (`src/data/medals.mock.json`). 4 des 20 succès mockés ont des textes partiellement inventés (nom/description réels du jeu, progression et paliers fictifs).
- Non fait : comptes, addon d'export, import de progression, icônes réelles des succès.
