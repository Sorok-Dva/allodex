# POC front — site fan Allods Online : écran d'ouverture + panneau Succès

Date : 2026-09-18
Statut : validé en discussion, à implémenter

## 1. Objectif

Construire un prototype front, sans backend, qui reproduit deux écrans du jeu Allods Online (client EU FR, version 16.0) dans un navigateur, en réutilisant les assets du client :

1. **L'écran d'ouverture du jeu** : vidéo d'intro, puis vidéo du menu principal en boucle avec le panneau de connexion, dont les boutons deviennent le menu du site.
2. **Le panneau Succès** (« Medals » en interne) : réplique fidèle de l'interface in-game, alimentée par des données mockées.

Le POC valide la faisabilité visuelle et pose l'architecture des données pour les étapes suivantes (comptes, addon d'export, import de progression), sans les implémenter.

## 2. Hors périmètre

- Backend, API, base de données, comptes utilisateurs.
- Addon Lua d'export des succès et import sur le site.
- Mapping des identifiants de texture (`TextureId`) vers les icônes du client.
- Responsive mobile abouti. Cible : desktop, 1280×720 minimum.
- Commit des assets du jeu dans git (droits d'auteur : seul le script d'extraction est versionné).

## 3. Sources et formats (établis par le spike)

| Élément | Emplacement dans le client | Format |
|---|---|---|
| Client FR | `/mnt/h/MyGames/Allods Online FR (FR)` | dossier `data/Packs/*.pak` |
| Fichiers `.pak` | | ZIP standard |
| Textures UI | `Interface.Mini.pak` → `*.(UITexture).bin` | zlib( u32 `0` + u32 taille + payload DXT1/DXT5 ). Aucune dimension dans l'en-tête. |
| Panneau Succès | `Interface/Ingame/Medals/Textures/**` | 50 textures |
| Écran de connexion | `Interface/Wrap/MainMenu/LoginAccount/**`, `Interface/Wrap/MainMenu/Main2/**` | 42 textures |
| Éléments communs | `Interface/Common/Buttons/**`, `Interface/Common/Elements/**` | boutons, croix, ascenseurs |
| Curseurs | `Interface/System/Cursors/**` | `.cur` |
| Vidéos | `Video.pak` → `Video/16_0Events/MainMenu/{Intro,MainMenu}.ogv` | Theora 1280×720, 24 fps |
| Textes FR | `Texts_x64.pak` → `Bin/pack.loc` | zlib, décodé par `unpack_texts()` de `~/projects/allods-texts-packer/unpack.py` |

Inférence des dimensions d'une texture : le payload donne le nombre de blocs 4×4 (16 octets en DXT5, 8 en DXT1). On énumère les couples (largeur, hauteur) en puissances de deux compatibles, on décode chacun via un en-tête DDS synthétique et Pillow, et on retient celui dont la moyenne des différences entre lignes consécutives est minimale. Validé sur 90 textures sur 92 ; les deux échecs connus (`ButtonLoginNormal`, `ButtonLoginHighlighted`) sont corrigés par une table d'exceptions manuelle dans le script.

## 4. Architecture

```
allods-medals/
├── tools/                    # pipeline d'assets (Python 3, Pillow, numpy, ffmpeg)
│   ├── extract_assets.py     # lit le client, écrit public/game/
│   ├── uitexture.py          # décodeur UITexture → PNG (+ inférence dimensions)
│   ├── assets_manifest.json  # liste blanche des chemins à extraire + exceptions de dimensions
│   └── requirements.txt
├── public/game/              # généré, ignoré par git
│   ├── textures/<chemin miroir>.png
│   ├── video/{intro,mainmenu}.{webm,mp4}
│   └── cursors/*.cur
├── src/
│   ├── data/
│   │   ├── medals.types.ts   # modèle calqué sur medalsLib
│   │   └── medals.mock.json  # ~20 succès réels + progression fictive
│   ├── screens/
│   │   ├── OpeningScreen/    # intro + menu principal + panneau de connexion
│   │   └── MedalsScreen/     # panneau Succès
│   ├── components/game/      # briques UI réutilisables (GameFrame, GameButton, ScrollList, ProgressBar, MedalBadge…)
│   ├── lib/assets.ts         # helper : chemin logique → URL public/game
│   └── App.tsx               # routeur minimal (2 routes)
├── docs/superpowers/
└── package.json              # Vite + React + TypeScript
```

### 4.1 Pipeline d'assets (`tools/`)

- `extract_assets.py --client "<dossier client>" --out public/game` :
  1. ouvre les `.pak` nécessaires en ZIP ;
  2. pour chaque entrée listée dans `assets_manifest.json`, décode et écrit un PNG au chemin miroir (sans le suffixe `.(UITexture).bin`) ;
  3. copie les `.cur` ;
  4. extrait les deux `.ogv` et lance `ffmpeg` : WebM VP9 (sans piste audio, il n'y en a pas) et MP4 H.264 pour Safari ;
  5. écrit `public/game/manifest.json` (chemin → largeur, hauteur) pour que le front connaisse les tailles natives.
- Idempotent : ne réécrit pas un fichier déjà présent sauf `--force`.
- Le chemin du client est aussi lisible depuis la variable `ALLODS_CLIENT_DIR`.
- Dépendances : Python ≥ 3.10, Pillow, numpy, ffmpeg dans le PATH.

### 4.2 Modèle de données (`medals.types.ts`)

Calqué sur `medalsLib.GetCategories`, `GetMedalInfo`, `GetMedalRanks` pour que le futur import d'addon soit une simple désérialisation.

```ts
type MedalCategory = { name: string; subCategories: { name: string; medalIds: string[] }[] };
type MedalRank = { completeProgress: number; name: string; description: string; score: number; reward?: { description: string } };
type Medal = {
  id: string; name: string; description: string;
  icon: string;                       // chemin logique d'icône ; placeholder pour le POC
  categoryIndex: number; subCategoryIndex: number;
  ranks: MedalRank[];                 // au moins 1
  progress?: { value: number; title?: string };   // état joueur ; absent = jamais commencé
  currentRank: number;                // index du palier atteint (0 = aucun)
  finishDate?: string;                // ISO, présent si terminé
  dressCollection?: { slot: string; description: string; success: boolean }[];
  medalCollection?: { medalId: string; success: boolean }[];
};
type MedalsDataset = { categories: MedalCategory[]; medals: Medal[]; totalScore: number };
```

Le mock reprend les trois succès de la capture de référence (Paré pour l'aventure ! Immortalité et Réveil, Dragon des temps nouveaux) plus une quinzaine d'autres extraits des textes FR (Escarmouches, Amalgames, Jeux d'Ammer…), répartis dans les catégories Progression, Personnage (Équipement, Professions, Divers, Long service), Batailles, Astral, etc. Les compteurs de la navigation (« 4/4 », « 45/45 ») sont calculés depuis les données, pas codés en dur.

### 4.3 Écran d'ouverture (`OpeningScreen`)

Séquence :
1. `intro` : `<video autoplay muted playsinline>` plein écran (object-fit cover), noir autour. Un clic ou Espace passe la suite. Fin de vidéo → étape 2. Si autoplay refusé par le navigateur, on saute directement à l'étape 2.
2. `menu` : vidéo `mainmenu` en boucle, avec fondu entrant. Par-dessus, le panneau de connexion reconstruit : cadre `EditlineFrame`, champ de saisie utilisé comme **recherche de succès** (Entrée → écran Succès filtré), bouton principal `ButtonLogin` libellé « Succès », rangée de boutons ronds (`ButtonOptions`, `ButtonCredits`, `ButtonExit`…) réaffectés : Succès, Mon compte (désactivé, « bientôt »), Addon (désactivé), Crédits (lien vers une page très courte : mentions, assets © My.Games). La bande `BottomLine` en bas de l'écran comme dans le jeu.
3. Le curseur du jeu (`Interface/System/Cursors`) est appliqué via `cursor: url()` sur la page.

Le choix « voir l'intro » est mémorisé en `localStorage` : après une première visite, l'intro est sautée par défaut, un petit lien « Rejouer l'intro » la relance.

### 4.4 Panneau Succès (`MedalsScreen`)

Réplique de la capture, sur fond de la vidéo `mainmenu` floutée/assombrie pour rester dans l'ambiance.

- **Fenêtre** : cadre `FrameContent` (1024×1024, découpé en 9 tranches via `border-image` ou grille 3×3), en-tête avec titre « Succès », croix de fermeture en haut à droite qui renvoie à l'écran d'ouverture. Ligne « N points de succès » sous le titre, `totalScore` depuis les données.
- **Navigation gauche** (`FrameNavigation`, `CategoryContent`) : champ « Recherche de succès… », liste des catégories en boutons ; la catégorie active se déplie et affiche ses sous-catégories avec compteur `terminés/total`. Une seule catégorie ouverte à la fois, comme dans le jeu.
- **Contenu droit** : en-tête de sous-catégorie + menu déroulant Tout / Terminés / En cours. Liste verticale scrollable d'entrées `MedalEntry` :
  - médaillon à gauche : icône dans le cadre `MedalFrame{30,50,100,500}` selon le score du palier courant, variante `Complete` si terminé, chiffre du score par-dessus (`Numbers/NumN` quand disponible, sinon texte stylé) ;
  - parchemin `MedalPaper` / `MedalPaperComplete` avec nom (police serif dorée, ombre), date de fin à droite, description centrée ;
  - barre de progression `ProgressBar` + `ProgressBarGauge` avec libellé « X sur Y » si le palier a un `completeProgress` > 1 ;
  - checklist à deux colonnes pour `dressCollection` / `medalCollection` avec coche verte ou grise ;
  - survol : tooltip listant tous les paliers (`MedalRanks`).
- **Ascenseur** : éléments `Interface/Common/Elements` (flèches haut/bas, piste) reconstruits ; la liste native reste scrollable à la molette.
- **Typographie** : police serif proche de celle du jeu (le client embarque une `.ttf` dans `Interface.Mini.pak`, à vérifier ; sinon Google Fonts « Cormorant Garamond » ou équivalent). Couleurs prises dans les balises des textes FR (`0xff122c14` vert foncé, `0xff658e7c` contour clair, or des titres).

### 4.5 Navigation

Deux routes : `/` (ouverture) et `/succes` (panneau), avec `?q=` pour la recherche. React Router ou routeur maison de dix lignes ; on choisit le routeur maison pour rester léger.

## 5. Gestion des erreurs

- Asset manquant (script non lancé) : le helper `assets.ts` renvoie une URL de fallback transparente et un bandeau discret en mode dev signale « lancez `tools/extract_assets.py` ». Le site reste navigable.
- Vidéo non lisible (autoplay bloqué, codec) : image fixe `Background_14_0_Temp` à la place, aucune erreur bloquante.
- Données mock invalides : validation au chargement par une fonction `parseDataset` qui lève une erreur explicite en dev.

## 6. Tests et vérification

- **Pipeline** : tests Python (pytest) sur `uitexture.py` avec deux fixtures synthétiques (DXT1 et DXT5 encodées connues) et sur l'inférence de dimensions ; test d'intégration marqué `slow` qui tourne seulement si le client est présent.
- **Front** : Vitest sur les fonctions pures (calcul des compteurs par sous-catégorie, filtre Tout/Terminés/En cours, choix du cadre de médaillon selon le score, recherche). Pas de tests de rendu visuel automatisés dans le POC.
- **Validation finale** : `npm run dev`, capture d'écran 1280×720 des deux écrans, comparaison à la capture de référence du jeu (fournie par l'utilisateur), corrections d'écart.

## 7. Étapes suivantes envisagées (hors POC)

1. Backend léger (Node) : comptes, upload d'un fichier d'export, stockage de la progression.
2. Addon Lua `MedalsExport` : dump `medalsLib` en JSON dans le dossier de config du personnage.
3. Mapping des icônes de succès vers les fichiers du client.
4. Version RU du client et textes multilingues.
