# Itération 2 — fidélité au jeu : accueil avec barre de boutons, panneau Succès à l'identique

Date : 2026-09-19
Statut : validé en discussion, à implémenter
Précède : `2026-09-18-poc-front-succes-design.md` (POC v1, fusionné dans `main`)

## 1. Retour utilisateur sur le POC v1

- L'accueil montre un champ de recherche et des boutons grisés incompréhensibles ; le bouton « trophée » relance l'intro au lieu d'ouvrir les succès.
- Le panneau Succès est « dans l'esprit » mais pas identique au jeu : chrome de fenêtre différent (plaque de titre brune absente, bandeau turquoise trop haut), boutons de catégorie plats au lieu des pilules vertes à liseré or avec médaillon +/−, catégories toutes dépliées, absence de la case « suivi », de la ligne « Série de succès », de l'infobulle du jeu, menu déroulant natif, ascenseurs CSS.

## 2. Objectif

Reprendre les deux écrans pour qu'ils soient **visuellement identiques au jeu à l'échelle 1:1**, en s'appuyant sur des captures live du client (1920×1009) prises depuis WSL via PowerShell, et sur les textures du client déjà extraites.

## 3. Hors périmètre

- Vue « Progression » (Progrès du succès, barres par catégorie, Terminé récemment) : itération suivante.
- Comptes, addon d'export, import, backend.
- Les autres interfaces de la barre (sac, carte…) : seuls les boutons qui seront branchés un jour apparaissent.

## 4. Références

Captures live dans `refs/` (dossier **git-ignoré** : elles contiennent le HUD et le personnage de l'utilisateur) :

| Fichier | Contenu | Usage |
|---|---|---|
| `refs/astral.png` | Panneau Succès, Astral déplié, « Astral ouvert » sélectionné | géométrie générale, chrome, entrées |
| `refs/tooltip.png` | Idem + infobulle sur « Connecté avec les étoiles » | infobulle |
| `refs/dropdown.png` | Idem + menu « Tout » déroulé | menu déroulant |
| `refs/navscroll.png` | Idem, colonne des catégories défilée en bas | liste complète des catégories, ascenseur |
| `refs/actionbar_user.png` | Barre de boutons du jeu (capture utilisateur) | accueil |
| `refs/progression_user.png` | Vue Progression (capture utilisateur) | hors périmètre, référence future |

`tools/capture_game.ps1` (versionné) : capture la zone client de la fenêtre `AOgame` en PNG. Appel depuis WSL :
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\Llyam\allodex-captures\capture.ps1" -Out "C:\...\x.png"` (copier le script côté Windows au besoin).

Géométrie relevée sur `refs/astral.png` (échelle 1:1, pixels écran) :

| Élément | Mesure |
|---|---|
| Fenêtre (rails verts) | x 522 → 1402 (≈ 880 px), y ≈ 188 → 775 (≈ 590 px) |
| Plaque de titre brune « Succès » | déborde la fenêtre : x 479 → 1483, y ≈ 186 → 222, texte doré centré |
| Bandeau turquoise « 24690points de succès » | y 228 → 257, texte vert foncé |
| Colonne de navigation | x ≈ 540 → 800 ; champ « Recherche de succès... » y ≈ 270 → 296 ; pilules à partir de y ≈ 305, pas de 30 px, hauteur ≈ 28, largeur ≈ 240 ; ascenseur à droite (flèches 18×18, piste, curseur) |
| Colonne contenu | x ≈ 820 → 1385 ; en-tête sombre y ≈ 262 → 300 avec titre doré à gauche et champ « Tout » + bouton or à droite ; entrées à partir de y ≈ 310, pas ≈ 111 px ; parchemin x 900 → 1352 ; badge à gauche (x ≈ 838 → 895) ; ascenseur à droite |
| Entrée terminée | parchemin doré, nom brun en haut à gauche, date en haut à droite, description centrée, barre de progression « 5 sur 5 » |
| Entrée non terminée | parchemin gris, case « suivi » (carré) en haut à droite, ligne « Série de succès : » avec 6 icônes 32×32 portant un chiffre romain |
| Badge | icône 48×48 dans un cadre or avec un petit chiffre romain de palier en bas à droite ; écu rouge avec le score dessous |
| Infobulle | cadre sombre vert bordé, titre vert clair, « Date : 20:54 29.08.2026 », description, séparateur, « [Shift] 🖱 Lien vers les succès » |
| Menu « Tout » | liste sombre à bord or : « Tout », « Terminé », « Pas terminé », alignés à droite |

**(amendé 2026-09-19)** Géométrie ci-dessus remplacée par les mesures faites en tâche 1 sur les
quatre captures (profils numpy, recherche de fenêtres uniformes, test d'identité pixel entre
lignes/colonnes ; voir `.superpowers/sdd/2026-09-19-iteration-2-fidelite/task-1-report.md`) :

| Élément | Mesure amendée |
|---|---|
| Fenêtre (rails verts) | x **518 → 1404** (886 px), y **191 → 783** (592 px) |
| Plaque de titre brune « Succès » | x **574 → 1349** (775 px, pas toute la largeur de l'écran), y 191 → 222 |

Le reste du tableau (bandeau, colonnes, entrées, badge, infobulle, menu) est confirmé à ±3 px
près par les captures de vérification de la tâche 6, à l'exception des couleurs de l'infobulle
et de la taille du curseur d'ascenseur, amendées séparément en §7.2 et §7.3.

Catégories (ordre du jeu, 17) : Progression, Personnage, Batailles, Astral, Raids précédents, Zones de l'histoire, Ordre, Raids actuels, Aventures héroïques, Succès rares, Étincelle, Royaume des éléments, Exploration du monde, Parchemins de retour, Allod privé, Événements, Forteresse de guilde. « Progression » n'a pas de médaillon +/− (c'est une vue, pas une catégorie dépliable).

## 5. Sources d'assets

1. **Textures du client** (déjà extraites) : `Interface/Ingame/Medals/Textures/*` (parchemins, cadres de badge, barre de progression, `CategoryContent`), `Interface/Common/Buttons/Cross/*`, `Interface/Common/Elements/MsgBox/textures/MsgBoxCheckBox*`, `Interface/Common/Elements/Editline/*`.
2. **Nouvelles textures à extraire** : `Interface/Ingame/ContextPinMenu3/textures/*` (barre de boutons : `ButtonMedals*`, `ButtonEquipment*`, …), `Interface/Ingame/ContextActionbar2/ActionBar*` (fond de barre, à évaluer).
3. **Sprites découpés dans les captures** (`tools/cut_sprites.py` + `tools/sprites_manifest.json` → `public/game/sprites/*.png`, git-ignoré) pour le chrome que le client ne stocke pas en textures isolées : plaque de titre (extrémité gauche, tranche répétable, extrémité droite), bandeau turquoise (coins ornés + tranche), rails verts (haut, bas, gauche, droite, coins, séparateur vertical entre colonnes), pilule de catégorie (état normal ; tranche gauche ornée, milieu, droite) et médaillons « + » / « − », champ de recherche, en-tête sombre du contenu, champ + bouton du menu déroulant, cadre du menu déroulé, flèches et curseur d'ascenseur, case de suivi, cadre d'infobulle. Chaque sprite a une boîte `[x0, y0, x1, y1]` dans une capture nommée, et optionnellement des tranches 9-slice.

Toute image dérivée des captures est nettoyée : aucun texte, aucun élément du HUD, aucune information du personnage ne doit finir dans `public/game/sprites/`. Le script refuse une boîte qui déborde de la fenêtre Succès (x < 470 ou x > 1490 ou y < 180 ou y > 790).

## 6. Écran d'accueil

- Vidéo du menu en boucle (inchangé), intro première visite et `?skipIntro` (inchangés).
- Suppression du panneau de connexion, du champ de recherche et des boutons ronds.
- **Barre de boutons du jeu** en bas à droite, comme en jeu : boutons 44×52 sur une bande sombre translucide avec liseré, textures `ContextPinMenu3`. Contenu : **Succès** (`ButtonMedals*`, actif → `/succes`) et **Personnage** (`ButtonEquipment*`, inactif : rendu normal, au survol infobulle « Mon compte — bientôt », clic sans effet). États : Normal / Highlight au survol / Pressed au clic. Infobulle de survol au style du jeu (même cadre que l'infobulle des succès) avec le nom de l'interface.
- La bande basse `BottomLine` avec la mention légale reste.

## 7. Panneau Succès

Rendu à **l'échelle 1:1** (fenêtre 880×590 — **amendé 2026-09-19** : 886×592, voir §4), centré dans la vue, fond vidéo flouté conservé.

### 7.1 Chrome
Plaque de titre brune débordante avec « Succès » doré centré et ornements aux extrémités ; bandeau turquoise avec « N points de succès » (sans espace avant « points », comme le jeu) ; rails verts ; croix de fermeture (`Cross/Close*`) dans le coin supérieur droit ; séparateur vertical entre les deux colonnes.

**(amendé 2026-09-19, itération 2b)** Le cadre de la fenêtre commence **au-dessus** du bandeau
turquoise : un rail vert court de y 205 à y 223 de part et d'autre de la plaque de titre
(sprites `rail-top-left`, x 518→592, et `rail-top-right`, x 1331→1378 ; les deux passent sous
les ornements de la plaque, dont les coins bas sont transparents, et s'arrêtent au bouton de
fermeture). Le haut du cadre a été relevé par test d'identité pixel entre `refs/equip.png` et
`refs/astral.png` : les lignes 205 et suivantes sont identiques dans les deux captures (donc
opaques, c'est la fenêtre), celles d'au-dessus varient avec le décor du jeu. Sans ces sprites,
on voyait la vidéo de fond à la place du cadre.

**(amendé 2026-09-19, itération 2b) Aucun filtre appliqué par le navigateur.** Les corrections
de couleur du jeu (textures du client plus sombres que leur rendu, variantes d'état absentes
des captures) sont **cuites dans les PNG** au moment de l'extraction et de la découpe :
`tools/assets_manifest.json` porte `color_offsets` (`{"<entrée de pak>": [dr, dg, db]}`,
appliqué après rognage par `extract_assets.py` : `FrameNavigation`, `FrameContent02`,
`CategoryContent`, `MedalPaper`, `MedalPaperComplete`, `ProgressBar`, `ProgressBarGauge`) et
`tools/sprites_manifest.json` porte `derive` (`{"from": "<sprite>", "matrix" | "offset"}`,
appliqué par `cut_sprites.py` : `pill-full-open`, `scroll-up-off`, `scroll-down-off`). Les
règles `filter: url(#…)` et le composant `GameFilters` sont supprimés : le Chrome GPU de
l'utilisateur appliquait ces filtres SVG autrement que le Chromium headless et délavait en
rose le texte brun des entrées, alors que les captures headless étaient correctes. Seuls
restent des filtres CSS sans référence externe (`brightness`, `grayscale`), identiques
partout.

Le fond de la colonne de contenu couvre toute la colonne (x 835→1390) : la texture
`FrameContent02` est étirée de 7 px (572 au lieu de 565) au lieu d'être décalée de 7 px vers
la droite, qui laissait une bande verticale transparente sur toute la hauteur (vidéo de fond
visible, constatée sur la vue « Professions »).

### 7.2 Navigation (gauche)
- Champ « Recherche de succès... » (sprite du jeu).
- Liste des 17 catégories en pilules, **toutes repliées** au chargement ; « Progression » sans médaillon (clic : rien pour l'instant, la vue arrive à l'itération suivante) ; les autres avec médaillon « + » (repliée) / « − » (dépliée). Une seule dépliée à la fois ; déplier une catégorie sélectionne automatiquement sa première sous-catégorie.
- Sous-liste sur parchemin `CategoryContent` : « Nom - terminés/total », sous-catégorie active surlignée.
- Ascenseur du jeu à droite : flèche haut, piste, curseur, flèche bas (sprites), synchronisé avec le défilement natif de la liste (molette). **(amendé 2026-09-19)** Le curseur d'ascenseur est à **taille fixe (20 px)** comme dans le jeu, et non proportionnel au ratio contenu visible / contenu total — la même règle s'applique à l'ascenseur de la colonne de contenu (§7.3).
- Au chargement, aucune sous-catégorie sélectionnée ; le contenu affiche l'en-tête « Astral ouvert » **uniquement** si une sous-catégorie est choisie ; sinon le contenu reste vide (la vue Progression prendra cette place plus tard). Exception pratique pour le POC : à l'ouverture, la catégorie **Astral** est dépliée et « Astral ouvert » sélectionnée, pour que l'écran ne soit pas vide.

### 7.3 Contenu (droite)
- En-tête sombre : titre de la sous-catégorie (doré, à gauche) ; à droite champ « Tout » + bouton or ; clic → menu déroulé du jeu avec « Tout », « Terminé », « Pas terminé » (composant maison, plus de `<select>`).
- Liste d'entrées, pas ≈ 111 px, ascenseur du jeu à droite.
- Entrée : badge (icône 48×48 en cadre or, chiffre romain du palier atteint en bas à droite de l'icône, écu rouge avec le score) ; parchemin doré (terminé) ou gris (non terminé) ; nom brun en haut à gauche ; date `JJ.MM.AAAA` en haut à droite si terminé, sinon case de suivi (sprite, cochable localement, état non persisté) ; description centrée ; barre « X sur Y » si `completeProgress > 1` ; si `medalCollection` non vide : « Série de succès : » centré puis rangée d'icônes 32×32 avec chiffre romain (I, II, III…) et état terminé/non terminé (icône pleine / assombrie).
  **(amendé 2026-09-19, itération 2b)** Géométrie du badge : les cinq textures `MedalFrame*`
  portent **la même plaque aux mêmes coordonnées** (région y 20→70 / x 25→76 identique au pixel
  près entre `MedalFrame`, `…30`, `…50`, `…100` et `…500`, écart moyen 0,2/255), seul l'ornement
  qui l'entoure grandit. Le cadre est donc posé pour tous les paliers en ancrant le centre de la
  plaque (50,5 ; 44,5 en pixels de texture) au même point du parchemin (38,5 ; 37,5), à l'échelle
  0,875 — le palier IV n'a pas de centre propre à extrapoler. Vérifié sur `refs/equip.png`
  (entrée « Divin », 100 pts, parchemin à y 366) : cadre relevé à (832 ; 365,6), prédit à
  (830,3 ; 364,6) ; bas du badge relevé à y 468,7, prédit à 467,9. L'écu est centré sur la
  **plaque**, pas sur la texture (qui déborde à droite au palier I) : sans cela le score était
  8 px trop à gauche. `scoreY` est réglé pour que le centre des glyphes tombe à +70 px du haut
  du parchemin aux trois paliers mesurés (I « 20 » et II « 30 » sur `refs/astral.png`, IV « 100 »
  sur `refs/equip.png`) ; les paliers III et V, absents des captures, sont extrapolés sur ce même
  centre. Au palier IV le badge (106 px) est plus haut qu'un parchemin sans barre ni série
  (84 px) : il déborde sur l'entrée suivante, qui le recouvre — dans le jeu, l'entrée « Divin »
  qui porte ce badge est bien plus haute (liste d'emplacements).

  **(à trancher)** Les deux badges 100 pts de `refs/equip.png` (« Divin », « Dragon des temps
  nouveaux ») n'affichent **aucun** chiffre romain, alors que les trois badges de
  `refs/astral.png` (10, 20 et 30 pts) en affichent un. Les captures ne permettent pas de
  déterminer le critère (palier ≥ IV ? succès hors série ?) : le rendu actuel affiche le chiffre
  à tous les paliers. À vérifier sur une capture du jeu montrant un succès 100 pts appartenant à
  une série.

  **(amendé 2026-09-19)** Le chiffre romain du badge est celui du **palier du score** (`toRoman(medalTier(score))`), **pas** celui de `currentRank`, comme le montre `refs/astral.png` : « Parfait ! » (`currentRank: 0`) affiche « I », et « Connecté avec les étoiles » (`currentRank: 1`, 20 pts) affiche « I » quand « Propriétaire » (`currentRank: 1`, 30 pts) affiche « II » — deux succès au même `currentRank` mais deux chiffres différents, donc le chiffre suit le score, pas le rang courant.
- Infobulle au survol du badge ou du nom : cadre du jeu, titre vert clair, « Date : HH:MM JJ.MM.AAAA » si terminé, description, séparateur, « Shift + clic : Lien vers les succès » (texte décoratif). Position fixe calculée, jamais coupée.
  **(amendé 2026-09-19)** Couleurs mesurées sur `refs/tooltip.png` (profils numpy sur les lignes de texte) : titre **et** date en `#00ea38` (vert vif, pas « vert clair »), description en `#ffdc00` (jaune), filet de séparation `#445f4a`, ligne d'aide `#b0d9be`. L'infobulle est ancrée au curseur (décalage +9, +11 depuis le coin haut-gauche), pas centrée sur l'élément survolé.

### 7.4 Données
- `medals.types.ts` : `Medal.tracked?: boolean` ; `MedalRank.image?: string` (icône du palier) ; `medalCollection` items gagnent `icon: string` et `rank: number` (chiffre romain) ; `finishDate` peut porter l'heure (`2026-08-29T20:54`).
- Mock : les 17 catégories dans l'ordre du jeu ; sous-catégories connues (Personnage : Équipement, Professions, Divers, Long service ; Astral : Astral ouvert, Allods Astraux ; les autres : « Général ») ; les 4 succès de la capture `astral.png` reproduits fidèlement (« Connecté avec les étoiles » 20 pts terminé 29.08.2026 20:54, 5 sur 5 ; « Propriétaire » 30 pts terminé 25.05.2026, 10 sur 10 ; « Parfait ! » 10 pts non terminé avec série de 6 ; « Tissu d'Éther » non terminé) plus les succès existants ; compteurs « Astral ouvert - 5/29 » et « Allods Astraux - 15/15 » **calculés** depuis les données, donc le mock contient 29 et 15 succès dans ces sous-catégories (les manquants sont générés avec des noms réels tirés des textes FR quand c'est possible, sinon « Succès astral n° k », marqués `placeholder: true` pour être remplacés par l'import).
- Libellés du filtre : « Tout », « Terminé », « Pas terminé ».

## 8. Vérification

- Captures Playwright 1280×720 **et** 1920×1009 de `/succes` comparées côte à côte à `refs/astral.png` (montage automatique `tools/compare_refs.py` : recadrage de la fenêtre dans la référence et dans la capture, juxtaposition, différence absolue). Critère : géométrie des colonnes, des pilules et des entrées à ±3 px ; mêmes textes aux mêmes places.
- Capture de l'infobulle et du menu déroulé comparées à `refs/tooltip.png` et `refs/dropdown.png`.
- Accueil : capture comparée à `refs/actionbar_user.png` pour la barre.
- Tests : Vitest sur la logique (état de navigation replié/déplié, sélection auto de la première sous-catégorie, filtre à trois valeurs, suivi local, chiffres romains) ; pytest sur `cut_sprites.py` (boîtes valides, refus hors fenêtre, 9-slice).
