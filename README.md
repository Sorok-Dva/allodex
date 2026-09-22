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
- `/achievements` : panneau Succès fidèle au jeu, données mockées (`src/data/medals.mock.json`). La progression et les paliers restent fictifs.
- `/chronicles` : archive des écrans de lancement, version par version, avec leur thème musical (voir « Chroniques » ci-dessous).
- `/music` : catalogue musical FR/RU, accessible par le bouton gramophone, avec lecture par catégorie.
- Non fait : comptes, addon d'export, import de progression, icônes réelles de tous les succès.

## Musiques

`/music` rassemble les musiques des clients FR 16.0 et RU 17.0, regroupées par
banque (menus, zones, peuples, instruments, Astral et donjons). Le bouton gramophone
de l'accueil ouvre la fenêtre du jeu : lecture/pause, durée, enchaînement des pistes
du groupe et interrupteur sonore. L'interface est disponible en français et anglais.
Le champ de recherche parcourt les titres et noms internes de toutes les catégories,
sans distinction de casse ou d'accents. La barre du morceau en cours affiche le temps
écoulé et permet de déplacer la lecture par clic, glissement ou touches du clavier,
y compris en pause. La catégorie interne Kadagan est affichée « Xadagan » en FR/EN.
« Zones » se déplie en sous-catégories, avec le parchemin et les boutons +/− des
Succès. Eden, Jigran, Xadagan et Kvator y sont intégrés. Les correspondances vivent
dans `src/data/music-zones.json` : ZL1 → Kania, ZE2 → Empire, Umoir → Umoira ; les
noms non identifiés restent dans « Autres zones ». La recherche inclut les noms de
zone et l'enchaînement reste dans la sous-catégorie du morceau joué.
Airin est affiché « Irene » en français et « Iren » en anglais.
Le bouton son et le volume (0–100 %) sont intégrés à droite du lecteur, disponibles
avant la lecture. Le bouton affiche le curseur, aligné avec la barre de lecture ;
un second clic, un clic ailleurs ou Échap le masque. Le niveau est mémorisé (`allodex:audio-volume`), appliqué à la
musique et aux sons d'interface, et conservé pendant les fondus et les changements
de page ; couper le son conserve le niveau choisi.

`npm run extract` extrait aussi ce catalogue. Pour ne refaire que les musiques :

    python3 tools/extract_music.py
    python3 tools/extract_music.py --only Music_Menu
    python3 tools/extract_music.py --force

Les clients et catégories sont déclarés dans `tools/music_manifest.json`, les titres
certains dans `tools/music_titles.json`. La première occurrence d'un nom interne
gagne (FR avant RU) ; les ajouts RU portent `client: "17.0"`. Sans titre documenté,
la page nettoie simplement le nom interne. Les pistes adaptatives gardent leur
première paire stéréo, sans sommer les calques. Le décodeur natif utilise le repli
WASM existant si nécessaire. Un client absent produit un avertissement et les
exports précédents sont conservés ; `--only` conserve les autres banques.

Sorties non versionnées : `public/game/music/*.{ogg,mp3}` et `public/game/music.json`.
Sans index, la page affiche « Musiques non extraites ».
L'icône du gramophone vient de `https://allods.ru/images/articles/media_player.png`,
déclarée dans `tools/assets_manifest.json` (`remote_textures`) et téléchargée à
l'extraction dans `public/game/textures/Official/media_player.png`. Elle est ensuite
servie localement ; `--force` la retélécharge. Le cadre conserve ses dimensions
natives sur ordinateur et est réduit sur les petits écrans.

## Audio du site

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
`/achievements`) coupe la sortie (`.muted`) sans jamais mettre en pause la musique.

## Chroniques

`/chronicles` présente, version par version (1.0 → 17.0), l'écran de lancement du jeu
en plein écran — la vidéo du menu en boucle quand le client en avait une, sinon une
image de fond — surmonté du **logo de l'add-on** (centré en haut, à sa taille native,
avec un halo qui respire). Le thème musical du menu de la version est jouable en bas à
droite. La version affichée vit dans l'URL (`/chronicles?v=8.0`) ; la frise de pilules
en bas d'écran, les touches ← → et les flèches du jeu en changent, avec un fondu croisé
de 600 ms sur l'image **et** sur la musique. La page **défile toute seule** : le thème
n'est pas bouclé et, quand il se termine, la version suivante s'affiche (la dernière
ramène à la première) ; une version sans thème reste 20 s ; mettre le thème en pause
suspend l'enchaînement. Pendant la visite, la musique d'ambiance du site est mise en pause et reprend
là où elle en était à la sortie (croix en haut à droite). Une version dont le client
n'était pas monté à l'extraction s'affiche sur le fond de secours assombri, avec la
mention « Média non extrait ».

Le bouton « ? » du jeu (à gauche du haut-parleur) ouvre la **fiche de la version** :
date de sortie, histoire de l'add-on et grands changements, lus dans
`src/data/versions.json` (bilingue `{fr, en}` ; les champs `release_note`, `confidence`
et `sources` documentent la recherche dont viennent ces fiches et ne sont pas affichés —
le fichier est à relire et corriger à la main). Tant que la fiche est ouverte, le
défilement automatique attend.

### Langue

L'interface est en français par défaut et en anglais si le navigateur est en anglais ;
`?lang=en` (ou `fr`) force la langue et la mémorise (`localStorage` `allodex:lang`).
Les chaînes vivent dans `src/lib/i18n/messages.ts` (un test vérifie que chaque clé
existe dans les deux langues) ; les données bilingues (fiches) sont des objets
`{fr, en}` lus avec `pick()`. Pour l'instant seuls les Chroniques, les Musiques et le bouton son sont
traduits ; les autres écrans restent à passer par `useI18n().t()`.

Quand aucun client archivé ne conserve un média, le manifeste peut pointer hors client :
`theme: {url}` (bande originale officielle sur allods.ru), `theme: {file}` (MP3 local dans
`refs/themes/`, git-ignoré) ou `logo: {url}` (PNG du forum allods.my.games). Les 17
versions ont ainsi leur thème.

Trois libellés sont construits à partir du manifeste et non écrits à la main :

- **`label`** — « Allods Online - <`name`> (<`version`>) », p. ex. « Allods Online -
  Game of Gods (3.0) » ; sans `name` (1.0, antérieure aux add-ons) : « Allods Online
  (1.0) ». C'est le texte du cartouche en haut à gauche, et le grand titre central des
  versions sans logo.
- **`logo`** — `logo.png`, extrait de
  `Interface/Common/Elements/WrapAllodsLogo/WrapAllodsLogoV<N>` dans la meilleure langue
  disponible (`fra` > `eng_eu`/`eng` > texture non localisée, qui est le russe). Les
  versions dont aucun client archivé ne conserve le logo (1.0, 2.0, 11.0, 12.0)
  n'ont pas de clé `logo` : la page affiche alors le libellé en toutes lettres dans la
  police du jeu.
- **`theme_note`** — une version dont aucun client archivé ne garde le thème (10.0,
  11.0, 13.0, 14.0) a `theme: null` dans le manifeste : le lecteur reste affiché,
  bouton grisé, « Thème non disponible ». Aucun thème approchant n'est substitué.

Les médias viennent de `tools/extract_archive.py`, qui écrit — comme le reste de
`public/game/`, donc **non versionné** — `public/game/archive/<version>/`
(`background.png` ou `menu.{webm,mp4}` + `intro.{webm,mp4}`, `logo.png`,
`theme.{ogg,mp3}`), l'emblème commun `public/game/archive/_common/` et l'index
`public/game/archive.json`.

**Fonds des versions ≤ 8.0 : une capture, pas une texture.** Jusqu'à la 8.0 le menu
principal est une scène 3D (`World_MainMenu_*`) que le client ne stocke pas comme
image : `Interface/Wrap/MainMenu/Main2/Background*` n'en est qu'une illustration de
repli, identique d'une version à l'autre. Le fond de ces versions est donc une **capture
d'écran du jeu**, déclarée par `background.capture` (`refs/menu-<version>.png`).
Tant que le fichier n'existe pas, l'outil retombe sur la texture du client et l'entrée
d'index porte `background_note: "capture de la scène 3D à venir (illustration de
repli)"`, affiché sous le cartouche.

Pour ajouter une capture (client ancien ouvert sur son écran de connexion) :

    powershell.exe -NoProfile -ExecutionPolicy Bypass \
      -File "C:\Users\<vous>\allodex-captures\capture_game.ps1" \
      -Out "C:\Users\<vous>\allodex-captures\menu-3.0.png"
    cp /mnt/c/Users/<vous>/allodex-captures/menu-3.0.png refs/menu-3.0.png
    python3 tools/extract_archive.py --only 3.0 --skip-video

`tools/capture_game.ps1` capture la zone client de la fenêtre `AOgame` (1920 × 1009 en
plein écran fenêtré) ; le fichier n'est ni recadré ni redimensionné par l'outil, et
`refs/` n'est **pas versionné**. La capture l'emporte sur la texture de repli dès le
passage suivant, sans `--force`.

**Ajouter une version.** Éditer `tools/clients_manifest.json` :
1. Déclarer le client dans `clients` (`root` : chemin WSL du client archivé, en lecture
   seule ; `game_version` pour mémoire).
2. Ajouter une entrée dans `versions` avec `version`, `name` (nom de l'add-on, dont le
   libellé est construit), `client`, puis soit `video`
   (`Video/<N>_0Events/MainMenu/{Intro,MainMenu}.ogv`), soit `background` (`capture`
   et/ou pack + entrée `(UITexture).bin`, ou `layers` pour les menus composés des
   clients 1.x), `logo` (pack — ou liste de packs — + entrée
   `…/WrapAllodsLogoV<N>` sans locale ni suffixe) et `theme` (banque
   `SFX/Music/Music_Menu.fsb` ; `prefer` force un subsong par son nom, sinon le choix
   est `MainMenu*` > `MainTitle` > `Menu*` > la plus longue ; `null` = thème
   indisponible). Chaque source accepte `client` pour piocher dans un autre client que
   celui de la version — c'est ainsi que les logos des 5.0/6.0 viennent des clients
   6.0/7.0. `note` et `theme_note` sont repris tels quels par la page.
3. Extraire cette seule version :

        python3 tools/extract_archive.py --only 8.0          # --force pour réécrire
        python3 tools/extract_archive.py --only 8.0 --skip-video   # sans transcodage vidéo

Un disque non monté n'est pas une erreur : l'outil avertit, laisse `media: null` dans
l'index et conserve les versions déjà extraites (il est idempotent).

## Scènes de menu

Jusqu'à la 8.0 le menu principal est une **scène 3D animée** (`World/MainMenu/Animated_Background*`).
`tools/extract_menu_scene.py` la rejoue hors du jeu : il lit les `.xdb` (XML) de l'arbre serveur
décompressé, va chercher les `.bin` dans les paks des clients archivés, et écrit par version —
dans `public/game/archive/<version>/`, donc **non versionné** :

- `scene.glb` — glTF 2.0 binaire écrit à la main (aucune dépendance Python nouvelle) : un maillage
  par objet (`POSITION`, `TEXCOORD_0`, `COLOR_0`, et `JOINTS_0`/`WEIGHTS_0` quand la géométrie est
  skinnée), matériaux `KHR_materials_unlit` (`alphaMode`, `extras: {blend: "add"}` pour les
  matériaux additifs), textures DXT décodées en PNG et intégrées au tampon, hiérarchie d'attaches
  (les objets fixés à un locator du parent) et animations squelettiques ;
- `scene.json` — ce que le glTF ne porte pas : caméra, axe « haut », couleur de fond, noms des
  animations, quelques compteurs.

Lancement :

    python3 tools/extract_menu_scene.py                       # les cinq versions
    python3 tools/extract_menu_scene.py --only 7.0
    python3 tools/extract_menu_scene.py --check-dir /mnt/c/Users/<vous>/allodex-captures/chroniques-scenes

`--check-dir` écrit une **planche de contrôle** par version (`glb-check-<version>.png`) : le `.glb`
relu et rendu par un rasteriseur logiciel interne, à la pose de repos puis trois secondes plus tard,
pour voir d'un coup d'œil ce que contient le fichier et si les animations bougent. Ce n'est pas le
moteur de rendu du site.

`tools/extract_archive.py` ajoute ensuite `scene: {glb, meta}` à l'entrée d'index quand les deux
fichiers sont là ; `background` reste l'illustration de repli (navigateur sans WebGL, mouvement
désactivé).

**Le lecteur.** `src/components/game/MenuScene.tsx` (three.js, chargé à la demande : `three` ne
pèse sur aucun autre écran) rejoue le `.glb` en plein écran sous l'interface des Chroniques. Il lit
d'abord `scene.json`, monte la caméra telle quelle — champ de vision **vertical** constant, seul le
rapport d'image suit la fenêtre, l'équivalent d'un `object-fit: cover` — et joue toutes les
animations en boucle. Deux partis pris reproduisent le moteur du jeu, lui aussi vérifiés sur les
planches de contrôle : aucune gestion d'espace colorimétrique (`ColorManagement` désactivé,
textures en `NoColorSpace`), et un rendu **à la peintre** — tout en mélange alpha, sans tampon de
profondeur, les primitives classées une fois pour toutes par profondeur moyenne (`sortByDepth`, la
caméra ne bouge jamais). Sans cela les quelques primitives exportées en `alphaMode: OPAQUE` — des
halos, en réalité — masqueraient les calques de nuages qui doivent passer par-dessus.

**Replis.** Sans WebGL (`src/lib/webgl.ts`, sonde mise en cache) la page garde le `background.png`
de la version. Avec la scène, ce même fond reste affiché **sous** le canvas jusqu'à la première
image rendue, puis s'efface en fondu : pas d'écran noir au changement de version. `prefers-reduced-motion`
n'affiche qu'une image, à t = 0, mixeur à l'arrêt ; un onglet caché suspend la boucle.

**Recaler une caméra.** La caméra du menu n'existe nulle part dans les données du jeu (elle est
codée dans le client) : `tools/scenes_manifest.json` en porte une **par version**
(`camera.position`, `camera.target`, `camera.fov`, en unités du jeu, axe Z vers le haut). Pour la
corriger, modifier ces valeurs puis relancer l'outil avec `--only <version> --check-dir …` et
comparer la planche à une capture du menu réel (`refs/captures-ui/menu-<version>-*.png`). Le repère
du jeu est en main gauche : l'export enveloppe la scène dans un nœud `scale: [-1, 1, 1]`, les
coordonnées de la caméra sont donc dans ce repère miroir (celui du `.glb`). La 7.0 a été calée sur
`refs/captures-ui/menu-7.0-frame1.png`. Les 4.0 et 5.0 sont publiées depuis leur reprise (voir
« Scène 4.0 » et « Scène 5.0 » plus bas) : leurs cadrages, calés sur l'illustration officielle pour
la 4.0 et sur une capture du menu pour la 5.0, restent approximatifs. Attention : la planche de
contrôle ne remplace pas une capture du site, son rasteriseur jetant les triangles qui frôlent la
caméra et ignorant les crochets du lecteur (ordre de peinture, orientation des textures, brouillard) ;
pour les 4.0 et 5.0 elle n'est pas représentative. `publish: false` dans `tools/scenes_manifest.json`
reste disponible pour retirer une scène qui ne serait plus présentable ; `--only <version>` force
alors l'export pour la retravailler.

**4.0 « Lords of Destiny ».** Un seul objet (`Animated_Background`), sans composant attaché ; le
« voile » qui masquait l'île n'était pas la brume mais le **dôme de ciel** (`Back2`, sphère opaque
à dégradé de couleurs de sommets, et `Back3`, sphère de nuages) : le tri par profondeur moyenne du
lecteur le passait par-dessus l'île, et la caméra d'origine était placée hors du dôme. Le xdb
déclare `sortMode OFFSETS` — le moteur peint les éléments **dans l'ordre du fichier**, sans tri
(dôme, nuages du fond, île, soleil, château, brume, oiseaux, nuages de premier plan). Le crochet
`tools/scenes/v4_0.py` relève ce mode dans `scene.json` (`sortMode`) et
`src/components/scene/MenuScene/v4/` l'applique en `renderOrder` à la place de `sortByDepth`, puis
redresse les textures (origine en bas, comme en 7.0). La caméra du manifeste est à l'intérieur du
dôme, du côté d'où les calques sont vus de face, cadrée sur `background.png` ; le dôme a une
ouverture de 64° face à la caméra, d'où la couleur de fond lavande (`background`) qui la comble.
Les oiseaux et les cristaux flottants viennent de l'animation squelettique du glTF (84 s en boucle).
Pas de défilement UV natif dans cette version (`scrollRGB` sans vitesse).

**Animations.** Le blob `(SkeletalAnimation).bin` a été rétro-conçu (format décrit en tête de
`tools/extract_menu_scene.py`) : pointeurs auto-relatifs, une piste par articulation à sept
composantes — translation, **échelle uniforme** et trois **angles d'Euler** (R = Rz · Ry · Rx) —
dont une table de descripteurs (20 octets par nœud) dit lesquelles sont animées. Translation et
échelle animées valent `base + u16 × pas`, un angle animé `i16 / 32767` **tour**. Cette lecture a été
établie sur la 5.0 (pose de repos du navire de raid retrouvée à 2·10⁻⁴, roue de la tour et faisceaux
du phare tournant autour du bon axe) ; les décodages antérieurs, qui prenaient les angles pour des
composantes de quaternion, sous-estimaient les rotations d'environ un tiers. **Les scènes 4.0,
6.0, 7.0 et 8.0 déposées viennent encore de l'ancien décodage** : vérifié le 22/09/2026 sur des
captures avant/après, la 6.0 et la 7.0 ne changent pas visiblement, mais la 4.0 dérive et la 8.0
bascule entière — leurs sommets « statiques » (`skinIndex` −1 dans le xdb) sont rattachés par défaut
à l'articulation 0, qui devient animée avec le nouveau décodage. Avant de les réexporter, rattacher
ces sommets à `VisualSceneNode` dans l'export. Les matrices inverses de bind du
jeu ne sont pas reprises : elles sont recalculées depuis l'image 0, ce qui garantit que la pose de
repos redonne exactement la géométrie statique.

### Scène 8.0 « Immortality »

Un seul maillage skinné (`AMM_8_0`, 65 éléments nommés, 29 textures, aucun objet d'effet
attaché) ; tout ce qui bouge vient des données : courbes squelettiques (arbres, herbe,
feuillage d'amorce), défilement UV natif des vapeurs de la cascade et de la statue, des braises,
du faisceau et des nuages, matériaux additifs des feux, du halo de la statue et du faisceau.
Calée sur `refs/captures-ui/menu-8.0-frame1.png`. Trois particularités, toutes tirées des
fichiers :

- **repère direct** : la capture montre la statue à gauche et la cité à droite alors que la
  géométrie a la statue en X négatif, et les calques de fond (ciel, nuages, arbres d'amorce,
  brume) sont des arcs concentriques centrés sur Y ≈ -400 — la caméra regarde donc +Y, sens
  dans lequel le nœud miroir générique retourne la scène. `tools/scenes/v8_0.py` reflète une
  première fois géométrie, squelette et courbes pour que les deux reflets s'annulent ;
- **caméra perspective** (`fov` 27°, à (1.8, -399, -5)) placée au centre des arcs ; en 8.0 les
  plans sont courbes, l'orthographique de la 7.0 ne convient pas. Hauteur et champ calés sur la
  statue (98 unités sur 78 % de la hauteur de la capture) ;
- **ordre de peinture natif** : le xdb déclare `sortMode = OFFSETS`, le client peint les
  éléments dans l'ordre du fichier (ciel → cité → faisceau → premiers plans → statue → colonnes
  → arbres d'amorce → brume → feux). `src/components/scene/MenuScene/v8/v8SceneLayers.ts`
  reprend cet ordre à la place du tri par profondeur moyenne, qui mettait les nuages de fond
  devant la statue. Comme en 7.0, les UV du client ont v = 0 en bas de l'image : le crochet
  retourne les textures.

- **halo du dôme** (`glow_add`, seul élément `skinIndex 0` du faisceau, additif, texture
  `Glow04White`) : sa piste décodée grossit le quad de 1 à 2,33 et le fait tourner autour de
  l'axe de visée, avec une translation qui compense exactement ce pivot **dans le repère du
  modèle** (T + s·R·P = P à 0,02 unité sur les 201 images). Son parent est le groupe `group2`
  (translation (39,7 ; -20,4 ; 10,7), échelle 0,81) et sa matrice inverse de bind native est
  l'identité : ses sommets sont exprimés dans le repère de l'articulation, comme la tour de la
  5.0. L'export recalculant les inverses depuis la pose de repos, `tools/scenes/v8_0.py` recale
  ces sommets par `monde_repos(glow_add)` — sans quoi l'animation faisait tourner le quad autour
  de l'origine de l'articulation, à 137 unités de son centre : l'« orbite » qui le sortait du
  cadre. Ainsi composé, le centre du halo tombe sur le croisement des petites lignes du faisceau
  (vérifié en rendant les deux couches seules) ;
- **une vitesse de défilement par élément** : le xdb donne la vitesse à l'élément, l'export ne
  distingue les matériaux que par texture et fusion. `Noise03White03` additif est partagé par
  `Statue_glow` (0,1 ; 0,1), `fire_spots` (0 ; 0,3) et `group3_Fire1` (0,02 ; 0), `BackCloud` par
  les nuages (0,01 ; 0) et la vapeur de la cascade (0 ; 0,2). `v8SceneLayers.ts` clone le
  matériau par vitesse distincte ; braises et cascade défilent désormais à leur vitesse.

Ce que les données disent des flammes : `group3_Fire2/3` (`Lightning10_2White`),
`group3_FireGlow` (`Glow05Yellow`) et `group3_Fire4` (`NoiseFire`) sont `skinIndex -1`, sans
défilement UV, et leurs `(Texture).xdb` ne portent ni atlas ni cadence (`atlasPart`, `wrap`,
mips) ; aucune articulation `group3` n'existe dans le squelette. Le client n'anime donc des
braseros que `group3_Fire1` (u 0,02), `fire_spots` (v 0,3), `Statue_glow` et `Stone_hotspot`
(0,1 ; 0,1). Le dump XML du client V8 (`Tools/ClientUnpacker/ExtractedOld`) a un
`AMM_8_0.(Geometry).xdb` identique à la copie serveur 7.0 hors la ligne `<binaryFile>` ; les
`.bin` n'existent que dans le pak du client FR 8.0.

Non rejoué, faute de formule : le `ZoneLights` du menu V8
(`Maps/MainMenu/ZoneLights/Mainmenu.(ZoneLights).xdb`) déclare un **bloom** (seuil 0,12,
puissance 3,5, contribution 0,75) et un brouillard (FogStart 100, FogEnd 600, FogColor ARGB
`0x78461E00`). Le halo doit sa brillance dans le client à ce bloom (couleur de sommet 0,5 ×
alpha 0,63 : additionné seul, il reste un voile). Un essai d'`UnrealBloomPass` calé sur ces trois
valeurs saturait toute la scène (les cinq niveaux de flou somment à 3 ; le ciel à 0,85 de
luminance passe le seuil) : mesuré sur dix régions contre la capture du client, l'écart RMS
passait de 24 à 33-40 quelle que soit la normalisation. La couleur du brouillard (brun sombre en
ARGB) ne correspond pas non plus au voile pâle de la capture. Reste approximatif : le sens
horizontal des défilements, les rotations squelettiques (≈ 0,15°, arbres quasi immobiles), et
un ciel plus sombre que dans le client (luminance 107 contre 143 en haut à gauche).

## Itération 2 (2026-09)

### Recalage V7 sur les captures du menu

La caméra V7 utilise un cadrage orthographique de 100 unités de hauteur, calibré sur les
captures : il ne s'agit pas d'une caméra extraite du client. Le lecteur corrige les UV verticales V7, atténue les nappes de
brume sans brouillard artificiel et replace le logo au centre. L'export conserve le nom de chaque élément dans les
`extras` de sa primitive (lus sur `mesh.geometry.userData` dans Three.js) : **réexporter avec `python3 tools/extract_menu_scene.py --only 7.0`**
est nécessaire pour cibler les faisceaux `GunRay` et les halos des réacteurs.

`menuSceneV7.ts` masque ces faisceaux et module les halos. `v7Intro.ts` regroupe chaque coque
avec ses réacteurs : tir entrant, incendie, chute puis disparition, successivement pour
les trois navires (ordre 03, 01, 02 ; impacts vers 6,8, 11 et 19,3 s après apparition
du menu, sans boucle). Le calage provient de la rafale du jeu du 21/09/2026 ;
les incendies peuvent se chevaucher. Coques et effets de chute restent sous la
bande des navires permanents. Le masque de distorsion Noise11White n'est pas
affiché comme une texture de feu ; flammes orange et fumée sombre le remplacent.
La piste native de destruction partiellement décodée n'est plus jouée en parallèle.
Les canons utilisent les locators du jeu, attachés aux sabords mobiles. L'export ajoute
`AMM_Shot01` comme bibliothèque masquée dans `scene.glb`. `v7NativeShots.ts` instancie
ses maillages **natifs** : `Proj_*`, les trois couches `Tail_*`, `FireMuzzle`,
`ShockWave*`, `Shield01`, `ShieldRays01`, `Flash01` et `ShieldFlash01`.
UV, couleurs de sommets et mélanges alpha/additif sont conservés ; aucun shader ne
redessine les projectiles ou les anneaux du bouclier. Three.js anime leurs placements,
échelles, opacités et défilements UV. Deux canons par bateau, trajet de six secondes ;
impact de 1,4 s : choc concentré seul pendant 0,28 s (`ShieldRays`, `ShockWave`,
flash), puis deux couches de `Shield01` espacées de 0,12 s. Les couches bleues
s'étendent, se rétractent légèrement (18 %) puis s'effacent ; les rayons du
choc initial ne restent pas superposés aux anneaux. Fumée de bouche renforcée sur 2 s.
Ces durées et poses restent un calage visuel, pas un décodage de `ParticleAnimation`.
Sans la bibliothèque native réexportée ou sans ses textures, les tirs restent masqués
(aucun remplacement procédural ni carré blanc). Les textures `cannon-*.png` servent
encore à la fumée et à l'introduction des navires secondaires.
Les sommets des drapeaux et rochers sont recentrés avec les matrices natives complètes
avant attachement aux locators. Les rochers opaques ne sont plus additifs et passent devant
les nappes de brume, derrière les coques ; les deux plans ont un petit recalage visuel.
La vignette V7 est allégée, les tirs portent une traînée dorée et les impacts sont étirés
verticalement. Le timing exact des destructions, certains plans secondaires et les
rotations/échelles squelettiques restent approximatifs. Le mode mouvements réduits montre
le décor sans tirs ni destructions.

La V7 surcharge `max_texture` à 2048 : le paysage `AMM_Background_03` conserve ses
2048 × 512 pixels natifs (au lieu de 512 × 128), et les coques leurs 1024 × 1024 pixels.
Les autres versions gardent leur limite existante. L'export V7 pèse environ 10,2 Mio.

Les vitesses `uTranslateSpeed`/`vTranslateSpeed` des matériaux sont exportées en
`uvScroll` et appliquées sur des textures indépendantes : brumes, nuages et réacteurs
défilent sans entraîner les textures partagées du paysage. Les petits navires sont
réduits à 82 % et composés derrière le premier plan. Les flammes/halos visibles passent
devant leur coque, leurs halos arrière restent derrière. L'export applique les matrices
natives aux seuls sommets des réacteurs : notamment `Engine_Glow01`, créé au niveau du
navire droit, est ainsi replacé sur les tuyères gauches sans déplacer les coques.

### Scène 5.0 « Heart of the World »

La scène est un seul objet skinné (tour-phare, roue et bielles, éclairs, arbres, nappes de brume et
coupole de nuages `Back6`) auquel le navire de raid est attaché par un locator ; ses deux animations
natives (100 s et 133 s) sont rejouées telles quelles par le mixeur générique. Ce qui n'est vrai que
d'elle vit dans `tools/scenes/v5_0.py` et `src/components/scene/MenuScene/v5/` :

- **Angles fixes de la pose de bind.** Dans le blob d'animation, un angle d'Euler *fixe* n'est pas
  écrit (son flottant vaut 0) alors que la matrice locale de bind du squelette porte la rotation :
  `root` (rochers) et `root1` (grand arbre) tournent de ~180°, `Tower`/`group5` de 10,4° autour de Z,
  les bielles ont un Z fixe à 180°, la branche `joint9` un Y fixe à 90°. Les angles *animés* sont
  absolus et valent ceux du bind à l'image 0. `restore_fixed_rotations` remplace chaque angle fixe
  par celui du bind, dans la branche d'Euler qui s'accorde aux angles animés : la pose de bind
  stockée est retrouvée exactement pour 23 des 35 articulations à inverse réelle (les autres à moins
  de 0,3), et toutes les pièces de la tour s'alignent sur un même axe (X ≈ −52, Y ≈ 24). Le premier
  jet laissait ces rotations à l'identité : arbre 33 unités trop bas, rochers derrière la tour,
  pièces de la tour étalées sur 14 unités, et surtout **le bol de nuages retourné** (ses sommets
  `skinIndex -1` sont liés par le tampon à `joint17`, un rocher sous `root`) — d'où la caméra hors du
  décor et le voile. Ces sommets peints restent maintenant en espace monde, comme dans le client.
- **Repère natif cuit dans les sommets.** Toute la tour et le navire ont des matrices inverses de
  bind identité : leurs sommets sont dans le repère de l'articulation. Le crochet `positions`
  applique `monde_repos · inverse_native` avant l'export, sans quoi roue, phares et halos s'empilent
  à l'origine et le navire reste figé sur son locator. Le navire naît à l'échelle 0 (sa pose de bind
  est sa pose finale, échelle 0,632, retrouvée à 2·10⁻⁴) : la pose de repos est bornée à 10⁻³.
- **Caméra dérivée du bol.** Les calques peints sont des arcs concaves tournés vers +X ; `Back6` est
  un bol un peu plus profond qu'une demi-sphère (fond à X = −91, bord à X = +16, rayon ~120) dont la
  sphère ajustée a pour centre (27, −1, −13) : la caméra y est posée et regarde −X le long de l'axe du
  bol. Champ vertical 53° = 2·atan(39/79) (la tour, 60 unités à 79 unités, couvre 77 % de la hauteur
  de la capture). Repère direct (`"mirror": false`) : la droite de l'image est +Y, où sont la tour et
  les rochers. Réglage : la cible est relevée de 12 unités (9°) pour placer la tour comme sur la
  capture. La couleur de fond est celle du bol (médiane des couleurs de sommet ×2, modulée par sa
  texture) ; plus de brouillard ajouté (ses paramètres 5.0 ne sont nulle part).
- **Ordre de peinture et matériaux du xdb.** Les deux Geometry déclarent `sortMode OFFSETS` : le
  lecteur peint dans l'ordre du fichier (relevé dans `scene.json`, comme en 4.0). Le xdb distingue
  les matériaux `transparent` (mélange alpha/additif, alpha de sommet actif) des autres — fûts et
  flèche de la tour, sabres, bielles, écorces, coque du navire, bol `Back6` — que le client peint sans
  mélange : `scene.json` porte ces drapeaux par primitive (`materials`) et le lecteur leur applique
  un test d'alpha (seuil 0,5, réglage), le tampon de profondeur et la couleur de sommet RGB seule ;
  les matériaux mélangés testent la profondeur sans l'écrire. Les textures ont leur origine en bas
  (pointe de la flèche à V = 0,99 ; corrélation Z/V = +1), retournées comme en 4.0/7.0.
- **Écarts et manques.** Le navire est reclassé à chaque image : juste avant la tour quand il est
  derrière (X ≈ −73 à −87, 25-55 s), après tout le décor quand il revient au premier plan (65-85 s,
  il croise le plan de la caméra vers 80 s et remplit l'image comme sur
  `refs/captures-ui/menu-5.0-frame2-raid-ship.png`). Les rochers `Allods`/`Allods3` portent un
  alpha de sommet **nul sur tous leurs sommets** : appliqué, il les effacerait, alors qu'ils
  partagent le matériau `Allods_01_psd_SG` avec `Allods2`, dont l'alpha va bien de 0 à 255, et
  qu'ils sont visibles dans le client. Ce canal ne porte donc pas d'information (comme une
  couleur de sommet entièrement nulle vaut « pas de teinte » pour l'exportateur) : le lecteur
  l'ignore pour ces primitives — matériau cloné, car un seul matériau glTF sert les trois — et
  c'est l'alpha de la texture qui découpe le rocher. Les effets attachés
  `/Spells/FX/World/AnimBack_Raid_Ship_*` et `EngineTL01.Malfunction` (particules) ne sont pas
  exportés.

### Scène 6.0 « Broken Chains »

Un seul maillage skinné (46 éléments) et son animation `idle` de 100 s : drapeau du
laboratoire, arbres et balancement du train sont natifs et joués par le mixeur ; les
46 matériaux arment tous le défilement UV (`scrollRGB`) mais le xdb n'en donne aucune
vitesse, le VisObjectTemplate n'attache aucun effet, `Manatrain_6_0_01_FX`, `Bird`
et `BackClouds_02` sont des textures que rien ne référence (reliquats d'une version
antérieure de la scène). Les binaires sont identiques octet pour octet dans les clients 6.0
(`/home/llyam/allods-clients/6.0`), 7.0 et 8.0. Six constats, tous tirés des fichiers :

- **caméra au centre du dôme de ciel.** `Sky_Back` est une demi-coque d'ellipsoïde
  (ajustement sur ses 158 sommets : centre (−2,8, 4,3, −2,8), demi-axes (83, 192, 83), erreur
  2 %) ; comme en 8.0 les calques de fond entourent le point de vue, et le manifeste y place
  la caméra, regard vers −X (laboratoire à Y > 0 à droite, station et pylône à Y < 0 à
  gauche). Le champ est ajusté sur `refs/captures-ui/menu-6.0-frame1.png`
  (image 4:3 étirée en 16:9, abscisses corrigées) : champ vertical 92° en 4:3, soit 108°
  horizontal ; le lecteur gardant le champ vertical constant, le manifeste pose 76° pour
  retrouver ce champ horizontal en 16:9. Le tangage ajusté sur la capture valait −7°, et le
  petit drapeau du mât du laboratoire (sommet à (−38,1 ; 48,8 ; 22,3)) sortait alors du cadre
  par le haut en 16:9 ; **choix de l'utilisateur** : le tangage passe à **−1°** (cible relevée
  de `z = −7,5` à `z = −3,449`), le drapeau rentre dans l'image et l'horizon descend plus bas
  que sur la capture. La première caméra (40, −7, 30, champ 56°), ajustée à l'aveugle sur des
  repères, était trop haute et trop loin : elle rendait la station vue de haut et séparait
  les nappes de prairie ;
- **`v = 0` en bas des textures**, comme en 7.0 et 8.0 (corrélation z/v positive sur 37 des
  41 calques peints ; la coupole est en `v = 1`, la base des maisons en `v = 0`) :
  `src/components/scene/MenuScene/v6/hooks.ts` retourne les textures. C'était la cause
  principale du rendu illisible de la première passe (coupole pendue sous le laboratoire,
  prairies montrant leur ciel découpé vers le bas) ;
- **les canaux de rotation fixes de l'animation valent la rotation de bind, pas 0.** Une
  piste dont les trois angles sont fixes stocke trois flottants nuls — dans les cinq
  versions — alors que la matrice locale de bind porte une rotation franche (85° autour de Z
  pour `group2`, le mât du drapeau ; (56°, −10°, −22°) pour `group1`, le porte-train), et la
  décomposition ZYX du bind donne des valeurs rondes exactement sur les canaux fixes des
  pistes mixtes. `tools/scenes/v6_0.py` (`restore_bind_rotations`) remet cette rotation dans
  les pistes avant l'export ; sans elle le drapeau, modelé le long de X, était vu de chant et
  le train pendait de travers. Le décodeur générique n'est pas modifié : la même règle vaut
  probablement pour les 5.0 et 7.0 (tours à −10°, coques à ±90°), à vérifier sur leurs
  captures avant de l'y appliquer ;
- le train et le drapeau sont **modelés à l'origine** (inverses stockées = identité) et posés
  par la palette de bind (rotation et échelle : `group1` à 0,81, `group2` à 0,37, désormais
  lue par le décodeur) : `v6_0.py` la cuit dans les sommets des trois éléments skinnés
  (`skinIndex` 0 : `Flag1`, `Train`, `Trees`), et applique la règle 7.0 « additif seulement
  si transparent » (le train est peint opaque). Le décor peint (`skinIndex` −1) est rattaché
  par l'export générique à une articulation immobile : l'ancien `v6Landscape` du lecteur, qui
  le figeait, a été retiré ;
- **le manatrain ne parcourt pas son câble** — les données ne l'y envoient nulle part. Le
  blob d'animation a été relu champ par champ pour en avoir le cœur net : la piste `Train`
  porte le drapeau `0b1011111` (bit levé = composante fixe), c'est-à-dire translation figée à
  (0, 0, 0), échelle 1, angles Z et X fixes à 0, et **un seul canal** — l'angle Y, 3 001
  entiers 16 bits dans [−165, +182], soit [−1,81°, +2,00°] avec une période de ≈ 16,7 s. Son
  parent `group1` (le porte-train) est entièrement fixe. L'`aabb` du `(SkeletalAnimation).xdb`
  ne dit pas autre chose : ce n'est pas un volume balayé mais la boîte des trois éléments
  skinnés au repos. Recalculée avec la formule du jeu (palette = `W_anim · inverse_stockée`)
  sur les 3 001 images, elle vaut [−38,659 ; −27,1694] × [−26,9695 ; 62,511] ×
  [−23,5719 ; 22,3359] contre [−38,681 ; −27,1694] × [−26,9693 ; 62,756] × [−23,5719 ;
  22,3359] déclarés : **quatre faces sur six à 3·10⁻⁴ près**. Les 90 unités en Y sont l'écart
  entre le train (Y ≈ −22) et les arbres (Y de 25 à 62), pas un trajet. Surtout,
  `aabbLastFrame` ne s'écarte de `aabb` que de 0,13 unité — là où, en 5.0, les deux boîtes
  diffèrent de 4,3 unités parce que le navire de raid, lui, se déplace vraiment ;
- **les arbres translatent de quelques dixièmes d'unité, sans tourner.** `Bush_joint9`,
  `Tree01_joint3/4` et `Tree02_joint6/7` n'animent que Ty (et Tz pour trois d'entre eux), avec
  des u16 qui couvrent toute la plage 0…65535 : l'amplitude lue est celle qui est stockée,
  0,017 à 0,284 unité. Leurs trois angles sont fixes à zéro et leur rotation de bind est
  l'identité. Le feuillage frémit donc à peine — c'est ce que disent les fichiers, et l'écart
  de 0,13 unité entre `aabb` et `aabbLastFrame` l'exclut de faire davantage.

Sur la lecture du blob : l'entête est `u16 fps, u16 nb_images`, un pointeur auto-relatif vers
les descripteurs en **4**, puis trois couples `(count, ptr)` en 8/12 (noms), 16/20 (ordre
d'évaluation) et 24/28 (une table posée juste après les descripteurs, inutilisée). Dans un
descripteur de 20 octets, les deux pointeurs sont en **4** (`ptr_courbes`) et **12**
(`ptr_flottants`), les deux compteurs en **8** (`nb_valeurs`) et **16** (`nb_flottants`) — ils
s'entrelacent, ce qui se lit mal. Les 22 `ptr_flottants` du fichier 6.0 tombent exactement sur
`adresse_du_nom + longueur arrondie à 4 octets` et les `ptr_courbes` sur
`ptr_flottants + 4 × nb_flottants` : le découpage par le nom que fait
`parse_skeletal_animation` est celui des pointeurs du fichier. `tools/tests/test_scenes_v6_0.py`
reconstruit cette disposition (les autres tests écrivent des blobs *sans* table, décodés par
inférence) et verrouille les trois pistes.

Le bloc 6.0 du manifeste porte `"mirror": false` (décor modelé dans l'autre chiralité que la
7.0). Côté lecteur, `v6SceneLayers` peint dans l'ordre des `modelElements` du xdb
(`sortMode OFFSETS`), `v6Sky` rend le dôme `Sky_Back` dont l'alpha de sommet est nul partout,
et **`v6Clouds` fait dériver les nappes** : le xdb arme `scrollRGB` sur ses 46 matériaux sans
donner une seule vitesse, exactement comme en 4.0, donc les vitesses sont **empruntées à la
7.0** (`AMM_7_0.(Geometry).xdb`) comme l'utilisateur l'a validé pour la 4.0 — anneaux et
nuages sombres 0,01 ou 0,02 tuile/s (`Back_Cloud_*`), brume de vallée `MidClouds_01` −0,05 à
contresens (`Back_Myst`), rayons `Noise01White` 0,04 (`Ground_lights`). Deux contraintes de la
6.0 : l'export ne distingue les matériaux que par (nom, texture, fusion, transparence), donc
les six nappes `BackClouds_01`, les quatre `Ferris01_Clouds_Up` et les deux `MidClouds_01`
partagent chacune un matériau et reçoivent la même vitesse (`Lab_Add` partage le
`Noise01White` additif des rayons) ; et l'axe du motif change — les nuages sont tuilés en u
(de −3,5 à 2,8), les rayons ont un u constant et défilent en v.

Écart assumé : la capture montre la cabine du train deux fois plus grande que ne le permet sa
position dans les données (`group1` statique en (−36, −22, 9)) ; elle vient sans doute d'une
autre révision de la scène (les textures `Bird`, `BackClouds_02` inutilisées en témoignent).
Le rendu suit les données : le train pend au-dessus du pylône 02, à gauche, et s'y balance.

Reprise des deux écrans pour qu'ils soient visuellement identiques au jeu, à partir de captures live du client (spec détaillée : `docs/superpowers/specs/2026-09-19-iteration-2-fidelite-design.md`).

- **Accueil** (`/`) : le panneau de connexion et le champ de recherche du POC v1 n'existent plus. L'accueil affiche la **barre de boutons du jeu**, en bas à droite, comme en jeu : **Succès** (actif, ouvre `/achievements`) et **Personnage** (« bientôt » : au survol, infobulle « Mon compte — bientôt » ; clic sans effet).
- **Panneau Succès** (`/achievements`) : reconstruit à l'échelle **1:1** (fenêtre 886 × 592 px) à partir de captures live du client — chrome (plaque de titre, bandeau, rails, pilules, ascenseurs), infobulle et menu déroulant compris. La vue **Progression** (barres par catégorie, terminé récemment) est prévue pour l'itération suivante ; la catégorie « Progression » n'a pour l'instant aucun effet au clic.
- **Données** : `src/data/medals.mock.json` compte 64 succès dont **38 sont des `placeholder`** (`placeholder: true`) — des succès de la catégorie Astral générés pour que les compteurs affichés (« Astral ouvert - 5/29 », « Allods Astraux - 15/15 ») correspondent aux totaux réels du jeu, en attendant un import de la vraie progression du joueur.
- **Recapturer les références du jeu.** Les captures live (`refs/*.png`, dossier **git-ignoré** : elles contiennent le HUD et le personnage de l'utilisateur) sont la source de vérité des mesures ; les sprites qui en sont découpés (`public/game/sprites/*.png`, **jamais versionnés**, comme le reste de `public/game/`) reconstituent le chrome que le client ne fournit pas comme textures isolées (plaque de titre, bandeau, rails, pilules, ascenseurs, cadre d'infobulle, menu déroulant…). Pour recapturer :
  1. Copier `tools/capture_game.ps1` côté Windows (p. ex. dans `C:\Users\<vous>\allodex-captures\`), client `AOgame` ouvert sur l'écran voulu.
  2. Lancer depuis WSL : `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\<vous>\allodex-captures\capture_game.ps1" -Out "C:\Users\<vous>\allodex-captures\x.png"`, puis copier le PNG dans `refs/` du projet.
  3. Découper les sprites : `python3 tools/cut_sprites.py` (lit `tools/sprites_manifest.json`, écrit `public/game/sprites/*.png` et `public/game/sprites.json`).
