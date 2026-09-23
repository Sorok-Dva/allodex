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

## Commits
Messages en anglais, au format gitmoji `<gitmoji> <type>(<scope>): <message>` (ex. `✨ feat(chronicles): add fullscreen toggle that hides the HUD`), sans trailer `Co-Authored-By`. Détails dans [CONTRIBUTING.md](CONTRIBUTING.md). Activer le hook qui vérifie le format, une fois par clone :

    git config core.hooksPath .githooks
    git config commit.template .gitmessage

## État du POC (2026-09)
- `/` : intro (première visite), puis menu vidéo avec, en bas à droite, la barre de boutons du jeu (voir « Itération 2 » ci-dessous — le panneau de connexion et le champ de recherche du POC v1 ont été retirés).
- `/achievements` : panneau Succès fidèle au jeu, données mockées (`src/data/medals.mock.json`). La progression et les paliers restent fictifs.
- `/chronicles` : archive des écrans de lancement, version par version, avec leur thème musical (voir « Chroniques » ci-dessous).
- `/music` : catalogue musical FR/RU, accessible par le bouton gramophone, avec lecture par catégorie.
- `/character` (développement seulement) : création de personnage du client 17.0 (voir « Création de personnage »).
- `/cinematics` : toutes les cinématiques du jeu en film complet par faction, avec sous-titres officiels FR/EN/RU (voir « Cinématiques » ci-dessous).
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

## Cinématiques

`/cinematics` (alias `/cinematiques`, bouton « clap » de l'accueil) joue toutes les
cinématiques précalculées du jeu en **film complet par faction** : on choisit la Ligue ou
l'Empire sur les bannières de l'écran de choix de faction du client
(`Interface/Ingame/ChoiceFaction`), puis les cinématiques de la faction et les communes
s'enchaînent dans l'ordre chronologique, avec un carton de titre à chaque chapitre, la
liste des chapitres (vignettes, navigation), une barre de progression sur la durée du
film (repères de chapitres) et les sous-titres officiels en `<track>` WebVTT (FR, EN, RU
ou aucun). Deux lecteurs se relaient : pendant qu'un chapitre joue, l'autre, caché et
muet, précharge le suivant, d'où un passage sans attente. `?faction=league|empire` ouvre
directement un film. Clavier : espace (lecture/pause), Maj+←/→ (chapitre), F (plein écran),
Échap (quitte le plein écran, sinon retour au choix de faction).

**Plein écran** : bouton, touche F ou double-clic sur l'image. C'est le conteneur du lecteur
qui passe en plein écran (API Fullscreen), pas la balise `<video>` : nos sous-titres restent
affichés, à la même taille qu'en fenêtre. Commandes, chapitres et curseur s'effacent après
2,5 s sans mouvement et reviennent au moindre geste ; tant qu'ils sont visibles, l'image
remonte au-dessus de la barre pour garder les sous-titres lisibles. Sans API Fullscreen sur
un `div` (iOS Safari), le lecteur passe en mode CSS fixe plein cadre.

**Bonus** : les douze présentations de boss (9.0) ne coupent plus le récit. Elles forment
une section « Bonus » après la fin du film (`bonus: true` dans le manifeste) : le film
s'arrête sur l'écran de fin, qui propose « Voir le bonus » ; pendant le bonus, « Passer le
bonus » mène à la fin. La bannière de faction indique la durée du film sans le bonus.

    python3 tools/extract_cinematics.py                 # extraction (idempotente)
    python3 tools/extract_cinematics.py --only zc13-forum --force
    python3 tools/extract_cinematics.py --measure-sync --skip-video   # re-mesure du minutage (GPU conseillé)

### Sources

- **Dernier client (17.0.01.64, `/mnt/h/MyGames/AllodsRU`), source par défaut** :
  `data/Packs/Video.pak` (46 entrées), `Texts_x64.pak` (`pack.rus.loc`, `pack.eng_eu.loc`),
  `BaseLocall_x64.pak` (`Bin/pack.bin`, base de données compilée du client).
- **Client FR 16.0.01.78.2 (`/mnt/h/MyGames/Allods Online FR (FR)`)** : sous-titres
  français officiels (`Texts_x64.pak` → `Bin/pack.loc`, `BaseLocfra_x64.pak` → `Bin/pack.bin`).
- **Client « Warp » 11.0.00.37 (`~/allods-clients/11.0`)** : les quatre vidéos de l'histoire
  10.0 (Vychegrad), **retirées du jeu** (absentes des clients 15.0, 16.0 et 17.0).
- Comparaison seulement : clients 7.0 (ADC, Divinity), 8.0, 9.0, 15.0, 16.0 : mêmes vidéos,
  octet pour octet (CRC identiques), que le 17.0 pour tout ce qu'ils ont en commun. Les clients 1.x → 6.x
  n'ont aucune vidéo (pas de `Video.pak`) ; l'arbre serveur 7.0 (xdb) a servi à repérer les
  cinématiques moteur et le mécanisme des sous-titres.

### Méthode

- **Inventaire** : le `pack.bin` du client contient un registre vidéo (groupe → événement →
  fichier : `Invasion/plague → Video/7_0Events/Invasion/Beregovoy_HD.ogv`, …). Il liste
  toutes les vidéos du `Video.pak` ; le manifeste (`tools/cinematics_manifest.json`) en
  reprend chaque entrée non-menu, avec l'événement, la faction, la clé d'ordre et la
  justification de sa place (`chronology`). Les titres sont éditoriaux : le jeu ne nomme
  pas ses vidéos.
- **Vidéo** : Theora 1280×720 (Nihaz : 1920×1080) + Vorbis stéréo, transcodés en WebM
  (VP9 CRF 40 + Opus 96 k) et MP4 (H.264 CRF 29 + AAC 128 k), 720p au plus, et une affiche.
- **Audio** : la piste est **incrustée** dans l'`.ogv` et identique dans tous les clients
  (FR compris) : voix **russes** quand il y a des dialogues (23 vidéos), musique et effets
  seulement pour les 11 autres. Les paks `SFX_Voice_*` du 17.0 ne contiennent que les
  répliques de Kvator ; les voix des scènes moteur des quêtes sont dans `BaseLocall_x64.pak`
  (`SFX/Voice/*.bsb`, 226 banques russes), rien pour les vidéos.
- **Sous-titres** : ils ne sont pas dans la vidéo. Le client les affiche par l'add-on
  `Subtitles` (événement `EVENT_SHOW_SUBTITLES`) depuis des ressources `UISubtitleShow`
  (`subtitles[] = {delayMs, text}` ; `delayMs` = durée d'affichage). Compilées dans
  `pack.bin`, elles y laissent un bloc reconnaissable (voir `scan_subtitles`) : index du
  texte dans les `pack.*.loc` + durée. Le manifeste désigne chaque réplique par le début de
  son texte russe ; RU et EN viennent du 17.0 (même index), FR du client FR 16.0 (décalage
  d'index constant dans une ressource, contrôlé par l'égalité des durées : 100 % des lignes
  retrouvées). Une ligne anglaise restée en russe dans le client est omise de la piste EN.
- **Minutage** : l'ordre et la durée viennent des données ; **l'instant de départ, non** —
  il est fixé par le script de la scène, que je n'ai pas décodé dans le `pack.bin`. Les
  départs sont donc **mesurés** sur la voix (faster-whisper large-v3, deux passes, amorcé
  par le texte officiel, seul l'horodatage des mots est gardé) et rangés dans
  `tools/cinematics_sync.json`, contrôlé contre une transcription indépendante (la
  première réplique du prologue de la Ligue, mal retrouvée, y a été remise à `null`) ; une
  réplique introuvable (`null`) est placée à la suite de la précédente, ou juste avant la
  première réplique mesurée quand elle ouvre la vidéo. Les présentations de boss
  (une seule ligne couvrant toute la vidéo) partent de 0 sans mesure (`timing: client`).
- **Chronologie** : film = prologue de la faction (groupe `FactionsIntro`, 16.0), puis les
  arcs dans l'ordre des versions (Invasion 7.0 → raid 7.2 → Kyros 8.0 → Talos 8.1 → Nihaz
  8.2 → Vychegrad 10.0 → Éveil 11.0 → Suslanger 12.0 → Toute-Mère 13.0), puis le bonus
  (donjons 9.0) ;
  dans un arc, l'ordre du registre, sauf ZC13 où les dialogues placent le Forum avant la
  tombe d'Aellona (voir `chronology` de chaque entrée).

Sorties : `public/game/cinematics/<id>/{video.webm, video.mp4, poster.jpg, fr.vtt, en.vtt,
ru.vtt}` et `public/game/cinematics/cinematics.json`, versionnées comme le reste de
`public/game/` (≈ 380 Mo : 193 Mo de MP4, 186 Mo de WebM, moins d'1 Mo d'affiches et de pistes ; environ 25 min 30 s de film par faction).

### Cinématiques moteur recréées en 3D (pilote)

Les mini-cinématiques des quêtes ne sont pas des vidéos : le jeu les joue en temps réel. Le
chapitre 12.0 « Le monde caché » (`ao12-prologue04`, quête `AO12_Prologue04`, carte
`AO12_PrologueInst`, la Citadelle de Nihaz) en est une, **recréée dans three.js** avec les
données du dernier client et jouée dans le film comme un chapitre vidéo (même barre, mêmes
raccourcis, sous-titres FR/EN/RU, voix russes).

    python3 tools/extract_engine_cutscene.py                 # tout le pilote
    python3 tools/extract_engine_cutscene.py --no-voices     # garde les voix déjà extraites
    python3 tools/inventory_engine_cutscenes.py --client-only   # relevé du 17.0 (4 s)

**Inventaire** (`engine_cutscenes` du manifeste). Deux relevés : celui de l'arbre serveur 7.0
croisé avec le 17.0 (141 scènes, `scenes`) et celui du **17.0 seul** (`client_17`) :
555 trajets de caméra (`CameraTrackAction`), dont 375 dans des scripts de buff de
cinématique, 69 dans des `ClientData`, 7 dans des actions de créature ; 73 de ces buffs ont,
rangées à côté d'eux, des répliques sous-titrées et doublées (67 avec des voix
`Cutscenes/*`) — les meilleurs candidats ; 36 `GameViewScene`, 37 `GameViewScript` et 60
`ShowSceneAction` (figurants des instances de départ, fantômes, combats : pas de dialogue) ;
662 ressources de sous-titres. Le rattachement réplique ↔ buff se fait par proximité
d'identifiants (`pack.bin` range les ressources dossier par dossier) : approché, signalé.

**Ce qui vient du client 17.0** (lecteurs `tools/allods_bins17.py`, `tools/allods_vis17.py`) :

- *caméra* : `BuffResource 507556` → `BuffVisScripts` → `CameraTrackAction`, six points de
  caméra et six visées avec leur durée, identiques au `.xdb` 7.0 ; la durée d'un point est le
  temps pour rejoindre le suivant (82 s au total) ;
- *répliques* : dix `ClientData` (voix `Cutscenes/Eden2/Prologue04_Cutscene_1…10`) : sous-titre
  (indice de texte + durée), voix, animation du locuteur (`emoteSpeech`) ; FR du client 16.0 ;
  voix de `SFX/Voice/Voice_Eden06_rus.bsb` (sous-pistes nommées comme les événements) ;
- *décor* : base propre à la carte `Bin/Maps_AO12_PrologueInst.bin` (même format que
  `pack.bin` ; ses pointeurs de genre 1 visent `pack.bin`) : 4 régions, 193 objets posés
  (27 géométries — le quartier général de Nihaz, le Pointeur, portails, colonne d'éclairs —,
  164 lumières ponctuelles, 1 particule) ; **éclairage précalculé** `…_lightvrt.bin` (un
  sommet par sommet de géométrie, vérifié sur les 27) ; éclairage de zone `ZoneLights`
  (ambiante, brouillard, auto-illumination ; champs rangés par ordre alphabétique, recoupés
  sur `AC5_base` 7.0) ;
- *acteurs* : `MobWorld` → `VisualMob` → gabarit : Gort-Kostolom (Kania, cuir), Reniesta
  (Kania, robe violette, bâton), Véronika (modèle `Creatures/Veronika`), Nihaz (dragon
  `NihazDragonBoss`, seul visuel du `MobWorld` « Нихаз » rangé avec la quête) ; habillage
  comme le client : tenue par défaut, variations (visage, coiffure), objets portés
  (géosets montrés/cachés, objets accrochés aux articulations `Slot_*`, élément « L »/« R »
  choisi par le nom de la forme, texture de remplacement), **atlas de peau** composé des
  patchs de texture des objets (rectangles UV, sous-vêtements d'abord) ; animations `Idle`,
  `Idle01`, `EmoteSpeech`, `SpellCastOmni`.

**Ce que le client ne contient pas** (décidé par le serveur) et que le manifeste fournit,
justifié (`engine_scenes`) : la **place des acteurs** (le groupe autour du Pointeur, visé
par les 42 premières secondes ; Nihaz au point visé par le plan fixe de ses répliques, visible
à partir de 39 s) et l'**instant des répliques** (trois groupes calés sur trois tronçons de la
trajectoire : 4 répliques dans le premier plan de 39 s, 3 dans le plan fixe de 21 s, 3 dans le
dernier de 15 s ; dans un groupe, à la fin de la voix précédente + 0,6 s). Choix du lecteur,
nommés : champ vertical 45° ; couleur des sommets du décor = ambiante × 2 + octet 2 du
`lightvrt` × auto-illumination × 2 (le shader du client n'est pas lu, les octets 0-1 restent
à comprendre) ; acteurs éclairés par la lumière précalculée moyenne du décor autour d'eux.
L'affiche (`poster.jpg`) est une capture du lecteur à 46 s.

**Manques du pilote** : particules et effets posés par le serveur (le dernier travelling
vise un point vide, (90 ; 148 ; 210), sans doute un effet de vision) ; ciel (`SkyMesh`, fond =
couleur du brouillard) ; lumières ponctuelles temps réel ; objets animés du décor figés à leur
pose de bind ; le joueur, présent dans le jeu, absent ici ; interpolation de caméra linéaire.
Poids : 13 Mo (décor 2 Mo, acteurs 4 Mo, textures 5,5 Mo, voix 1 Mo).

**Code repris** : `tools/packbin.py` est une copie telle quelle de la branche des talents
(commit 1ad668d) ; les décalages de `Geometry`, `Texture`, `VisObjectTemplate` et
l'assemblage glTF (`Glb`) viennent de la branche des fatalités (`allods_visdb.py`,
`extract_fatalities.py`, commit 5615126), recopiés et adaptés (doublon à réunir quand les
deux branches seront fusionnées).

### Ce qui manque

- **Cinématiques moteur** : une seule est recréée (pilote, voir ci-dessous). Liste dans
  `engine_cutscenes` du manifeste. Huit d'entre elles ont été refaites en sept vidéos HD
  (7_0Events), extraites ici.
- **Sous-titres absents des données** : prologue 10.0 (narration russe, client Warp) et
  « Pas prévu au plan » (11.0). « Le héros de Sarnaut » a 12 répliques officielles mais
  leur texte diffère parfois de ce qui est dit (« Он сделал нас богатыми » écrit, « Он
  нашёл богатство в пустыне » prononcé) : 4 ne sont pas retrouvées dans la voix et sont
  placées à la suite de la précédente.
- Anomalie des données conservée : dans le Forum, la réplique « Regardez-vous ! Vous
  tremblez ! » a `delayMs` = 85 000 (sans doute 8 500) ; sa fin est coupée au départ de la
  réplique suivante.
- **Minutage exact** : les instants du jeu restent à trouver dans les scripts compilés ;
  le minutage mesuré peut décaler une réplique d'une ou deux secondes.
- Vidéos de menu (Intro/MainMenu 9.0 → 17.0) exclues : déjà dans les Chroniques ; clip de
  test `Raid7_2Events/TestClip.ogv` (1 s, client 8.0 seulement) exclu.

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
  modèle** — `T(f) + s(f)·R(f)·P = P` à 0,029 unité sur les 201 images, avec
  P = (41,601 ; −129,973 ; 44,921), le centre brut du quad. Sa matrice inverse de bind native
  est l'identité : ses sommets sont exprimés dans le repère de l'articulation, comme la tour de
  la 5.0. L'export recalculant les inverses depuis la pose de repos, `tools/scenes/v8_0.py`
  recale ces sommets par `monde_repos(glow_add)` — sans quoi l'animation faisait tourner le quad
  autour de l'origine de l'articulation, à 137 unités de son centre : l'« orbite » qui le sortait
  du cadre. Le halo se pose donc en `monde_repos(group2) · P`, sans dérive (0,02 unité entre les
  images) : tout se joue sur la composition de `group2` ;
- **une piste sans canal animé vaut la matrice de liaison, pas ses propres flottants**
  (`restore_static_binds`). C'est ce qui recentrait mal le halo : la piste figée de `group2`
  écrit sa translation, une échelle *uniforme* 0,814422 et trois angles nuls, alors que sa
  matrice de liaison est `R_z(−5,959°) · diag(0,82770 ; 0,77981 ; 0,83692)` — colonnes
  orthogonales à 7·10⁻¹⁰, donc bien une rotation suivie d'une échelle **non uniforme**, et
  0,814422 n'en est que la moyenne géométrique (à 7·10⁻⁹). Le format d'animation n'a qu'un
  flottant d'échelle et n'écrit jamais les angles fixes : vérifié sur les 284 pistes des cinq
  versions — translation fixe = translation du bind (282/284, les deux exceptions étant des
  locators `Slot_Special` de la 7.0), échelle fixe = moyenne géométrique des trois échelles du
  bind (271/271, écart max 2,7·10⁻⁶), angle fixe toujours nul (284/284). Une piste figée est donc
  une copie appauvrie : on l'écarte et `rest_local` reprend la matrice du squelette. Chiffres :
  le centre du halo passe de (73,58 ; −126,29 ; 47,31) à (63,42 ; −124,82 ; 48,32), soit
  0,15 unité du croisement des `Smal_Line_*` (63,57) au lieu de 9,94 — mesuré au rendu, l'écart
  horizontal halo ↔ croisement tombe de 9,7 px à 0,7 px sur 1280 px de large, les couches
  `Smal_Line_*` et `In_Big_*` restant identiques au pixel près. La rotation pure seule
  (5,959° + échelle uniforme) laisserait 1,24 unité d'erreur : c'est l'échelle non uniforme qui
  ferme l'écart. `group2` est la seule articulation des cinq versions dont la liaison soit
  anisotrope (rapport 1,073) ; `rest_local` porte donc une échelle par axe, sans effet ailleurs
  (glb de 4.0, 5.0, 6.0 et 7.0 identiques octet pour octet). Même règle appliquée à `Root` et
  `Root_grass` (rotations pures autour de Y, 155,5° et 119,9°) : les pivots des arbres et de
  l'herbe reviennent sur la géométrie qu'ils emportent — distance moyenne articulation ↔ sommets
  emportés 188 → 65 unités, `joint9` 43,4 → 8,6 — pour un balancement natif inchangé
  (0,15 à 0,5°, écart maximal de 4,07 unités sur les sommets) ;
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

Trois vérifications referment la question (2026-09) :

- **absence de vitesse = zéro, pas donnée manquante.** `Types/types.xml` décrit
  `client.Scene3D.Geometry$MaterialInstance` avec treize champs et pas un de plus :
  `uTranslateSpeed` et `vTranslateSpeed` (défaut **vide**, donc 0), `scrollRGB` et `scrollAlpha`
  (défaut **`true`** — l'exportateur les écrit partout, ils ne signalent rien), `BlendEffect`,
  `diffuseTexture`, `transparencyModifier`… Aucun atlas, aucune cadence, aucune distorsion. Le
  xdb de la 8.0 porte 45 balises de vitesse soigneusement réglées élément par élément : les
  omettre sur `group3_Fire2/3/4` et `group3_FireGlow` est un choix d'auteur, pas un trou de
  données — contrairement à la 4.0, dont le xdb n'en porte aucune (voir `v4/v4Fog.ts`) ;
- **`useProceduralEffect` ne pilote pas le feu.** C'est un `java.lang.Boolean` de
  `client.Scene3D.ExportGeometry` **de défaut `true`** (d'où sa présence sur les cinq scènes) ;
  il autorise un `client.VisualConstructor.ProceduralEffect`, ressource de **recoloration** :
  `color0` = « premier ton du dégradé, RVB ajouté à la couleur d'origine multipliée par
  l'alpha », `color1` = second ton. Elle s'applique par `ProceduralEffectVisAction`
  (`timeOn`/`timeOff`/`priority`) aux créatures — rien à voir avec une flamme ;
- **une seule couche de feu de tout le corpus porte une vitesse** :
  `SmalShip_destr_03_fire1` de la 7.0 (`AMM_7_0_Ships_Destroyed`), à 0,5 / 1,0. Les
  `SmallShip_fire_01/02`, `Engine_Glow01/02` et les `FireMuzzle` sont tous à (0 ; 0), comme les
  quatre couches de la 8.0.

Mesuré au navigateur (sept. 2026, temps piloté, captures toutes les 0,4 s) : tous les
défilements natifs tournent — offsets relevés par primitive, textures indépendantes en
`RepeatWrapping`, horloge du lecteur. Mais le brasero **paraissait figé** : 0,3 % des pixels
du grand brasero changeaient d'une capture à l'autre. `fire_spots` n'est pas le cœur du feu
mais le fin liseré du bord des vasques (quelques pixels de haut, UV larges de 0,01 tuile en u) :
son défilement v 0,3 tourne bien, sans rien montrer ; `group3_Fire1` (u 0,02) s'étale sur
3,22 tuiles, soit **161 s de traversée** ; les grandes langues (`group3_Fire2/3/4`,
`group3_FireGlow`) n'ont aucune vitesse. Aucun paramètre ne manque : c'est ce que le client
affiche.

**Loi du défilement, une seule pour u et v** : le contenu avance dans le sens de la vitesse
dans l'espace UV de la géométrie (échantillonnage `uv − vitesse × t`, décalage three.js
`−repeat × vitesse × t`). Tous les calques dont le mouvement se lit la confirment : vapeurs de
la cascade (v 0,2) et de la statue (v 0,04 / 0,05), liseré `fire_spots` (v 0,3) et brume de
rivière `river_steam_01` (u 0,02) ont leur axe positif tourné vers le haut et montent ; la
cascade `waterfall_water` (u 0,5) a +u tourné vers le bas et **tombe**. Jusqu'ici le lecteur
appliquait u avec le signe opposé à v : la cascade **remontait** (vérifié par une mire
substituée à sa texture). Seul `group3_Fire1` (u 0,02, +u vers le bas) descend désormais, à
une vitesse invisible. `tools/tests/test_scenes_v8_0.py` relit ces orientations dans le glb.

**Emprunt non natif, demandé par l'utilisateur** : les trois grandes langues de feu défilent
(`BORROWED_FIRE_SPEEDS`, `v8/v8SceneLayers.ts`), à la grandeur du voisin natif `fire_spots`
(0,3 tuile/s), désynchronisées : `group3_Fire2` 0,30, `group3_Fire3` 0,24, `group3_Fire4` 0,18.
**Sur u, pas sur v** : ces couches tuilent leurs UV le long de u (1,40 → 3,73 ; −1,76 → −1,28 ;
0,10 → 0,86) et c'est u qui suit la hauteur de la flamme (+u vers le bas sur 88 à 100 % de leur
surface, v surtout horizontal : un défilement v ferait glisser le feu de côté) — l'axe même que
l'auteur a animé sur `group3_Fire1`. Vitesse **négative** pour que le feu monte (vérifié par
mire). `group3_FireGlow` et `glow_add` (vignettes posées une fois, UV dans [0 ; 1]) restent
figés, `group3_Fire1` garde sa vitesse native. Au rendu, 8 à 10 % des pixels du grand brasero
changent désormais toutes les 0,4 s (0,3 % avant). À retirer si une vitesse native apparaît.

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

## Fatalités

La page `/fatalities` (désactivée en production) rejoue les 26 fatalités du jeu — 10 de classe,
16 de la boutique — sur les seize personnages jouables, dans un coin des Prés bénis.

**Source : le dernier client** (RU 17.x, `/mnt/h/MyGames/AllodsRU`). Il ne livre plus aucun
`.xdb` : tout ce que l'arbre serveur 7.0 décrit en XML est compilé dans `Bin/pack.bin`
(pak `BaseLocall_x64.pak`, 75 Mo → 703 Mo décompressés). `tools/allods_packdb.py` en relit la
structure (entête, table des 1498 types `NDb::…`, image mémoire des objets, table de
relocations qui dit seule où pointent les champs pointeurs et les vecteurs, chemins des
ressources racines) et reconstitue par vote la table « code de pak → pak » des références
binaires ; `tools/allods_visdb.py` décode les ressources utiles (Geometry, Texture,
VisObjectTemplate, ParticleAnimation, scripts `VisAction`, `SlonRoot`), chaque décalage étant
vérifié sur les ressources communes avec l'arbre 7.0 (tests `tools/tests/test_fatalities.py`,
dont trois sur les vraies données). Ce basculement a débloqué les fatalités de boutique : toutes
ont désormais leurs métadonnées complètes (fini « decoded without its metadata »), et les
associations animation ↔ effet ne sont plus devinées sur les noms de fichiers.

**Chaîne de données.** `Interface/System/SlonSettings.(SlonRoot)` → vecteur `fatalities`
(26 × `type, offenderDeathScript, casterFxScript, fadeStartTime, fadeDuration, sparkDelay`).
Le `offenderDeathScript` est l'arbre de `VisAction` joué sur la victime ; `tools/fatality_script.py`
l'aplatit, pour chaque personnage, en chronologie : animations de la victime (indices de
l'énumération `Animations`, prolongée au-delà de 1402 par les propriétés d'animation du client :
1591 `deathFatality`, 1594 `deathFatalityPhoenix`, 1609 `deathFatalityTree`…) avec leur vitesse,
changements d'échelle (×1,3 en classe) et de transparence, objets d'effet posés
(`CreatureIndependentFxAction` : décalage, échelle, durée de vie) ou accrochés à un locator
(`CreatureEffectsAction`), secousses de caméra. Chaque objet est un `VisObjectTemplate` :
géométrie skinnée et son animation (vitesse, boucle), composants accrochés, système de particules,
son (événement FMOD dont l'onde porte le même nom dans `SFX/Spells/Fatality*.bsb`).

    python3 tools/extract_fatalities.py              # tout (≈ 3 min)
    python3 tools/extract_fatalities.py --only-fx phoenix --no-characters

**Règles établies sur les données** (chacune testée) :

- `VisActionList` joue en séquence ou simultanément ; un `playWhile` délai borne la liste, et
  comme `stopWhileWhenElementsEnded` vaut vrai la liste s'arrête aussi quand ses éléments sont
  finis (durée = le plus court des deux) ; `PredicateCreatureVisCharacterAction` choisit les
  variantes par race (Lotus, Avatar) ;
- une boucle sans borne (`Stun` de l'Avatar, d'Avril 2024) s'arrête au fondu final de la victime ;
  une animation courte jouée par-dessus une boucle lui rend la main ;
- énumérations propres au client : `orientationMode` 3 WORLD_Z, 6 Z_AXIS, 7 BILLBOARD ;
  `Texture.type` 3 = RGBA non compressé (B G R A) ;
- les règles des scènes de menu valent ici : piste figée = copie appauvrie du bind (écartée),
  angles fixes repris du bind, `skinIndex −1` non skinné, sommets à inverse de bind identité dans
  le repère de l'articulation (`bind_pose_positions`), V = 0 en bas, `BLEND_EFFECT_ADD` additif
  seulement si `transparent` ;
- un élément de géométrie sans texture n'est pas dessiné (formes d'émission Maya de l'Occultiste,
  emplacements d'armure vides des personnages) ;
- particules **précalculées** (`tools/allods_particles.py`) : par émetteur, liste de particules
  (naissance, durée de vie) à cinq canaux clés — position, taille, rotation, couleur, image de
  l'atlas `Client/Render/ParticleAtlas` ; les 79 fichiers utilisés sont décodés et réencodés à
  l'identique, allégés des clés redondantes (tolérance nommée) ;
- sons : événement ↔ onde par nom, casse et soulignés ignorés (`FatalityUniversal` →
  `fatality_universal`).

**Personnages** (`tools/allods_characters.py`, module réutilisable — future page de création de
personnage). Tout vient du client 17.0 : le constructeur visuel compilé (`VisCharacterTemplate`,
`CharacterVariations`, `VisualItem`, `TexturePatch`, `IndexedTexture`) est décodé, chaque décalage
vérifié sur les `.xdb` 7.0 des mêmes ressources (test sur `HadaganFemale`). Le personnage est celui
que le client montre sans équipement :

- géosets : tous ceux de la géométrie, moins ceux que cache la tenue par défaut (`hiddenGeosets`,
  par sexe + unisexe), plus ceux que montrent les `armorShapes` de la variation par défaut
  (`face_0`, `hair_0`, `facial_0`, ailes, lumières des Aèdes…) ; sans texture, pas dessiné ;
- **peau cuite** : peau de base (`mainBakedTexture`), teinte de peau multipliée sous le masque
  (alpha de l'`IndexedTexture` : exclut yeux et dents), puis les calques dans l'ordre du client —
  visage, pilosité, tatouages, cuir chevelu, **sous-vêtements** (`braTexturePatches`,
  `pantsTexturePatches`) ; rectangles en fraction de la texture, V compté depuis le bas ;
- couleur des cheveux multipliée sur les `hairColoredGeosets` (matériau `extras.tint`) ;
- API : `find_character_template`, `read_character_template`, `resolve_appearance(template,
  géosets, textures, variation=None, items=())`, `bake_skin(...)` — une autre variation (visage,
  coiffure, couleurs de `Variations`) ou des objets portés s'y passent tels quels.

Clips : `Idle01` et les animations demandées par les scripts (victime **et** tueur), clés
redondantes retirées (1 mm, 2·10⁻⁴ de quaternion) et rotations en entiers 16 bits
(`KHR_mesh_quantization`). Les gibelins n'ont pas trois des animations de sort demandées par
certaines fatalités de boutique (le client ne les livre pas pour eux).

**Tueur** (`casterFxScript`) : `Fatality_Cast` accroché à son `Slot_BodyFX` et un **rayon**
(`CreatureChannelDirectAction` : gabarit `Fatality_Channel` modelé sur `fxLength` = 10 m le long de
−Y, étiré entre ses extrémités — racine + 1 m chez le tueur et chez la victime —, fondus 0,2 s /
0,1 s) ; le Phénix ajoute ses deux animations (`speed` 1,5) et un second rayon. Le script du client
n'a pas de fin propre : il s'éteint avec la victime. Les ailes (`CreatureRunVisActionResource`, sous
drapeaux `FatalityWings*` achetés en boutique) ne sont pas jouées. Mise en scène (constantes du
lecteur) : le tueur se tient à 5 m, à 55° de l'avant de la victime côté −X, tourné vers elle ; il
se choisit dans le panneau (défaut : même sexe, première race de l'autre faction, URL `k=`).

**Décor** (`scene/scene.glb`) : sol aux textures de terrain des Prés bénis, bouleaux, pins,
rochers et buissons de la zone à leur pose de bind, ciel `Sky01_Day*` du client (fond, soleil,
nuages) ; lumière et brouillard du `ZoneLights` 7.0 `BlessedMeadowsDefault` à midi. La disposition
est une mise en scène (manifeste, `scene.props`), aucune carte n'est lue.

**Table des paks** (`tools/allods_packdb.vote_pak_codes`) : le vote « l'entrée au rang indiqué
finit par `(Texture).bin` » ne départage pas deux paks de textures (n'importe quel rang y tombe
sur une texture) ; `World_Sky_Textures` perdait contre `Spells_FX_Textures`, bien plus grand, et le
ciel était texturé de bruits d'effets au hasard. Les textures votent désormais par **paire** : le
nom trouvé au rang du `.bin`, suffixé `.hi`, doit se trouver au rang de la référence haute
résolution d'un autre pak (170 codes corrigés, dont tous les `*.HiRes`). Plusieurs ressources
`Texture` pouvant nommer le même `.bin` avec des dimensions différentes (`Rays12White` 256² et 128²),
le décodage essaie chacune puis les dimensions déduites des mipmaps, et garde celle dont les
niveaux ont la taille exacte : plus aucune texture illisible.

**Lecteur** (`src/components/scene/FatalityViewer/`) : temps piloté à la main (pause, vitesse,
recherche), chaque image recalculée d'après la chronologie (`timeline.ts`) ; gabarits clonés à leur
instant, fondus d'entrée/sortie des `VisObjectTemplate`, composants retardés/arrêtés
(`DelayComponent`, `StopVisObjectComponents`), défilement UV, orientation Z_AXIS et BILLBOARD face
caméra, particules en quads instanciés (`particles.ts`), sons calés sur la chronologie.

- **Géométrie douce** (`softGeometry.ts`) : les matériaux d'effet dont la texture d'environnement
  est un `SoftGeometryGrain*` (≈ 300 éléments) la lisent à la normale vue de la caméra
  (`n.xy · ½ + ½`) et en multiplient leur alpha : les colonnes et halos cylindriques s'estompent sur
  la tranche (la colonne de l'Occultiste n'est plus un drap blanc à bords durs) ;
- **éclairage** : le jeu éclaire en `texture × (ambiante + soleil · N·L)`, couleurs à 1 = 0x80 ;
  le Lambert de three.js divise par π, compensé (`LIGHT_SCALE`) — les personnages ne sont plus
  sombres ;
- **caméra** (`cameraCollision.ts`) : jamais sous le terrain (rayon vertical sur les maillages de
  sol, marge 0,4 m, plancher strict 0,15 m) ; rapprochée devant un obstacle entre la cible et elle
  (rayon cible → caméra sur le décor opaque, feuillages découpés traversables) ; correction lissée
  (rapide pour rentrer, lente pour ressortir) sans toucher au rayon d'orbite ni au zoom.

Constantes propres au lecteur, nommées : `TRANSPARENCY_FADE_SECONDS` (vitesse de base de
`CreatureSetTransparencyAction`, non publiée), cadrage de la caméra, place du tueur, seuil de
découpe des feuillages.

**Manques.** Teintes (`CreatureColorAction`, `ProceduralEffect`) et secousses de caméra relevées
mais non appliquées. Particules : `WorldSpaceEmitter` et `Z_BOX` traités comme locales / face
caméra. Pas de bloom : les empilements additifs (Prêtre) saturent au blanc. Les gibelins jouables
sont un trio dans le jeu (placement codé dans le client, absent des données) : un seul est montré.
Aucune capture du jeu pour comparer les fatalités image par image. La durée affichée est celle
du script (dernier gabarit éteint) : certaines fatalités (Occultiste, Crâne 2024) finissent par
plusieurs secondes vides, comme leurs gabarits le demandent.
Poids : 62 Mo de personnages, 32 Mo d’effets, 28 Mo de textures partagées, 11 Mo de particules,
7 Mo de sons (54 ondes, toutes trouvées).

## Création de personnage (développement)

La page `/character` (entrée « Personnage » de l'accueil, désactivée et absente du build de
production : la route n'existe que si `import.meta.env.DEV`) reproduit l'écran de création du
**client 17.0** (`/mnt/h/MyGames/AllodsRU`), dans l'ordre du jeu : **faction** → **race et
classe** (avec sexe et niveau de tenue) → **apparence et nom** (familier des Pacificateurs, trio
des gibberlings), puis « Créer ».

    python3 tools/extract_character_creation.py          # tout (≈ 25 min)
    python3 tools/extract_character_creation.py --only Elf --no-scenes

**Sources, toutes dans le client 17** (`Bin/pack.bin`, lu par `tools/allods_packdb.py`) :

- interface : addon `CharacterGenerator` (arbre de widgets, placements, calques, textures de
  `Interface/Wrap/MainMenu/CharacterGenerator3`, icônes de races et de classes, textes RU/EN du
  `.loc`, FR relus par clé dans le client FR) — `tools/chargen_ui.py` ;
- données : `CharacterRoot` → factions → races → classes → deux sexes (`Character` : trois tenues
  de création avec leurs animations `chargen<Classe>Start`/`chargen<Classe>`, familier), gabarits
  `VisCharacterTemplate` et `CharacterVariations` (visages, traits, coiffures, couleurs, peaux,
  teintes, signes, pierres des aèdes), `VisualItem` (géosets montrés/cachés, calques de peau,
  modèles accrochés), règles de nommage `NameRules` — `tools/allods_chargen.py` ;
- décors : la carte `MainMenu` compilée à part dans `Bin/Maps_MainMenu.bin` (même format, codes
  de pak propres) : décor `World/MainMenu/Chargen_<Race>` et ses objets accrochés et animés,
  `ZoneLights` de la case (ambiante, soleil, brouillard), ambiance sonore ; place et caméra de
  `UICharacterScenes` (`CharacterSelect<Race>`) — `tools/chargen_scene.py`.

Sorties dans `public/game/character/` : `chargen.json` (index versionné, `schema: 1`),
`ui/layout.json` + textures, `models/<Gabarit>.glb` (tous les géosets, squelette, attente et
animations de création), `attach/` (casques, épaulières, armes), `textures/`, `scenes/<Race>.glb`.

**Règles établies sur les données** : tenue par défaut = corps nu (cache tous les géosets à
variantes) ; un objet porté montre ses formes et cache ses géosets, un géoset caché par un objet
l'emporte (le casque cache les cheveux) ; texture cuite = peau (`IndexedTexture`, teinte sous le
masque alpha) puis calques (visage, pilosité, signe, cuir chevelu teint de la couleur des cheveux,
sous-vêtements `bra`/`pants`, pièces de tenue), rectangles `x1 x2 y1 y2` avec V depuis le bas ;
décors de plus de 32 768 sommets : indices 16 bits par pages de 32 768 ; calques additifs de
l'interface (`WidgetLayer` +0x24 = 2) rendus en alpha (noir transparent).

**Descripteur** (`src/data/character/descriptor.ts`, `kind: "allodex.character"`, `version: 1`) :
faction, race, sexe, classe, nom, indices d'apparence dans les listes du gabarit, niveau de tenue,
compagnons du trio, familier (gabarit, pelage, nom). Validé contre `chargen.json`
(`validateDescriptor`, utilisable côté serveur). Persistance derrière `CharacterStore`
(`src/data/character/store.ts`) : `LocalCharacterStore` (`localStorage`) aujourd'hui, une
implémentation HTTP demain sans toucher à l'écran.

**Export `.glb`** : côté navigateur (`GLTFExporter`), de ce qui est affiché — géosets visibles,
texture cuite composée, modèles accrochés, compagnons et familier en nœuds frères, clips de la
tenue et attente ; repère converti en Y en haut (nœud racine), descripteur dans les `extras`.

**Écarts connus** : caméra de la place de *sélection* (`UICharacterScenes`), celle de la création
(`preMissionCamera`) n'étant pas décodée ; effets animés des tenues (plantes du Pacificateur,
lueurs) non rejoués ; ambiances FMOD relevées mais non jouées (musique du menu 17.0 à la place) ;
morphologie (`morphPresets`, citée par le script) non décodée ; aèdes : estrade reprise du décor.

## Talents

`/talents` affiche les talents de chaque classe jouable, version par version, dans la fenêtre
« Talents » du client 17.0 reconstruite depuis ses ressources (livre et trois grilles côte à
côte), et sert de calculateur de build partageable par lien
(`/talents?v=17.0&c=druid&b=1.3330…` : version, classe, build).

    python3 tools/extract_talents.py            # toutes les versions → public/game/talents/
    python3 tools/extract_talents.py --only 17.0
    python3 tools/extract_talents.py --ui       # fenêtre TalentBuilder + constantes de ses scripts (17.0)

Sources par version : `tools/talents_manifest.json` (chemins absents signalés, jamais devinés).

### Format des données du client

Les clients ne livrent pas de `.xdb` : tout est compilé dans `Bin/pack.bin` (zlib), image
mémoire des structures C++ `NDb::*` avec une table de relocalisation, et les textes dans
`Bin/pack*.loc`. `tools/packbin.py` lit les deux familles :

- **v1** (32 bits, 1.x → 11.x) : blocs `(id, taille)` — table des textes (chemin → indice),
  hachage des chemins xdb, noms de types, objets, couples de relocalisation `X = 2·adresse + drapeau`
  (pointeur d'objet, pointeur de données, étiquette de type à +1 ou +3 selon les builds) ;
- **v2** (64 bits, 15.x → 17.x) : chemins supprimés (sauf ~500 racines), objets indexés par
  identifiant ; relocalisations `X = 8·adresse + genre` en 15/16, `X = adresse + genre` en 17 ;
  les `UITexture` désignent leur fichier par (indice de pak dans le bloc 6, indice d'entrée zip).

L'extracteur ne dépend d'aucun décalage codé en dur pour les données de talents : il reconnaît
les champs par leur structure (pointeurs typés, tableaux de pointeurs, chaînes `….Name.txt`).
Deux heuristiques documentées dans le code : l'étalonnage des identifiants de texte des clients
64 bits (emplacement dont les valeurs mènent à des textes variés ; le plus balisé `<html>` est la
description) et la position du palier de points d'une couche du livre (entier qui vaut 0 sur la
première couche et croît). La valeur des variables `<r name="…"/>` est la valeur brute du
client ; les formules appliquées ensuite par le jeu (arme, caractéristiques) ne sont pas
calculées et sont signalées par `*`.

### Systèmes de talents identifiés

| Système | Ressources | Versions |
|---|---|---|
| Livre (couches de 4 sorts débloquées par paliers de points dépensés) | `BaseTalentsTable.layers` | 1.1 (6 couches, paliers 0-36) → 2.0-4.0 (9 couches, 0-60) → 7.0-17.0 (10 couches, 0-60) |
| Grilles de talents (3 par classe, une case par rang, départ au centre) | `TalentFieldResource` | 1.1 (7 × 7) → 2.0-4.0 (9 lignes × 7) → 7.0-17.0 (9 × 9) |
| Coût en rubis de talents | `RubyCostCalcer` | 1.1-3.0 (non extrait) |
| Talents de guilde | `GuildTalentFieldResource` | 7.0 → 17.0 (non extrait) |
| Talents de monture | `MountTalentGroup` | 9.0 → 17.0 (non extrait) |
| Talents de l'âme (graphe de capacités, niveau d'âme) | `SoulRoot → TalentGraph → AbilityGraphNode` | 9.0 (268 nœuds), 11.0 (345), 15.0-17.0 (550) — non extrait : le graphe n'a pas de coordonnées dans les données, la disposition est calculée par le script de l'addon `SoulTalents` |
| Runes | `Rune`, `RuneRegistry` | toutes (objets d'équipement, hors arbre de talents) |

Les talents ne dépendent pas de la race : `BaseTalentsTable` n'est référencée que par
`CharacterClass`. Les classes `ANGEL` (réutilise la table du mage) et `CORK` (bouchon) sont
écartées.

### Versions

| Version | Source | Textes | Classes | Talents |
|---|---|---|---|---|
| 1.1.02 | arbre de développement (`Allods 1.0/allods/Client`) | RU (fichiers `.txt`) | 8 | 438 |
| 2.0.04 | client anglais | EN | 8 | 560 |
| 3.0.2.19 | client russe | RU | 9 | 622 |
| 4.0.02 | `pack.bin` d'origine du repacker (même empreinte que le client « AllodsLegend ») | FR (`Texts.pak` du même dossier) | 9 | 630 |
| 7.0 | client « Revelation » | EN + RU | 10 | 880 |
| 8.0 | client français | FR | 10 | 895 |
| 9.0.01.89 | client français | FR | 11 | 1 003 |
| 11.0 | client Steam anglais incomplet | aucun (noms internes) | 11 | 1 009 |
| 15.0.03.23 | client français x64 | FR | 11 | 1 048 |
| 16.0.01.78 | client français x64 | FR | 11 | 1 055 |
| 17.0 | dernier client russe x64 | EN + RU | 11 | 1 058 |

Sans données : 5.0 et 6.0 (clients partiels : interface et musiques seulement), 10.0, 12.0
(paks de textes seuls), 13.0, 14.0 (aucun client). Le client arabe 3.0 et le client « Allods
Warp » (`~/allods-clients/11.0`, autre jeu) sont lisibles mais non retenus. Le `.loc` anglais du
17.0 contient des textes restés en russe : une entrée « en » identique à « ru » est retirée.

### Fenêtre 17.0 (addon `TalentBuilder`)

La fenêtre du jeu actuel n'est pas `ContextTalents` (508 × 749, une grille à la fois, onglets
Livre/Talents — l'ancienne fenêtre, encore présente dans le client) mais l'addon
**`TalentBuilder`** : panneau `TalentsBuilder` de **1810 × 701** (posé en 10 × 119 dans le
formulaire plein écran), livre à gauche (`TalentsPanel` 388 × 536,5), trois panneaux de grille
(`MilestonePanel01…03`, 446 × 536,5, damier `Chess` 411 × 416), cadre `Frame`, compteurs
`BaseTalentsHeader`/`FieldTalentsHeader`, commandes `Controls` (changer de classe, apprendre,
réinitialiser, activer le build) et sélecteur de build `ActiveBuildSelector` (I / II).
`public/game/talents/ui/talent_builder.json` contient :

- l'arbre de widgets (nom, type, `WidgetPlacement`, priorité, calques) ; les variantes de bouton
  avec tous leurs calques (`+0x08` survol, `+0x70` désactivé, `+0xA0`, `+0xD0` normal,
  `+0x100` enfoncé, `+0x130`), relevés sur les boutons du « Contextructor » dont les textures
  portent le nom de l'état ; les calques `WidgetLayerTiledTexture` avec leur découpe en neuf
  (`+0x38` haut, gauche, largeur et hauteur du milieu, droite, bas ; `+0x50`/`+0x54` milieu
  étiré ou répété — vérifié : `MainPanelBackground` 1496 × 600 = 28 + 1440 + 28 × 65 + 445 + 90),
  rendus en `border-image` ;
- les gabarits `UIRelatedWidgets` que les scripts clonent (case du livre `BaseTalent`, case de
  grille `FieldTalent`, états `FieldTalentLearned`/`FieldTalentReadyToLearn`, liens
  `BaseFieldLinkLeft/Right`, surbrillances) et les textures nommées `UIRelatedTextures` ;
- `layout` : les constantes des scripts, lues dans leur bytecode (voir ci-dessous).

Le `.xdb` ne place ni les cases ni les panneaux de grille : les scripts de l'addon le font. Ils
sont livrés compilés (`LuaCompiledIngame_x64.pak`, LuaJIT 2.1 dépouillé, octet de version 0xA1
mais jeu d'instructions standard) ; `tools/luajit.py` en lit les constantes et les instructions,
et l'extracteur y prend :

| Script | Constantes | Usage |
|---|---|---|
| `ClassBaseField` | `SCALE` 0,9244, `LEFT_BORDER` 42,29, `UP_BORDER` 15,71, `INTERVAL_X` 30,21, `INTERVAL_Y` −3,62 ; liens 14 × (Δy + 11), à +24, côté −9 / +56 | case du livre (59 × SCALE) en `LEFT_BORDER + (col−1)·(taille + INTERVAL_X)` ; 2ᵉ lien d'une colonne à droite |
| `ClassRubyField` | `SCALE` 1,1561, `LEFT_BORDER` 36,25, `UP_BORDER` 79,75, intervalles 0 | cases de grille (36 × SCALE) dans leur panneau |
| `ClassBuilder` | `fieldsInterval` 15, `mainOffsetY` 117 | panneaux de grille en 19 + 388 + 15 = 422, 883, 1344 ; compteur = libres / (libres + dépensés + appris − 3) |
| `ClassBuild` | 10 × 4, 3 grilles de 9 × 9, coût des rangs `{1, 2, 3}` | règles du calculateur |
| `ClassFieldTalent`, `ClassBaseTalent` | tailles 36/40 et 59/42, couleurs de surbrillance (même talent : `(0,07 ; 0,48 ; 0,48)`) | états des cases |
| `ClassControls` | `ChangeClass` déplacé en `posX` de `SavedBuilds` (masqué) | pied de fenêtre |
| `ScriptPlayerClasses` | icône et couleur de chaque classe | sous le titre |

Le site rend la fenêtre à l'échelle 1:1 quand l'écran le permet (réduite sinon, jamais sous
0,5 sur téléphone : la page défile). États des cases, comme le script : sort du livre en
couleur dès le rang 1, rang en jaune (vert au maximum) ; case de grille apprise en couleur sur
`FieldTalent` ; case que l'on peut apprendre encadrée d'orange (`FieldReady`, gabarit
`FieldTalentReadyToLearn` : le script l'affiche quand `canLearn` ou pour une case en file
d'attente) ; autres en gris.

**Survol = talents liés.** Le cadre sarcelle du jeu n'indique pas les cases accessibles : au
survol d'un rubis ou d'un sort, `ClassFieldTalent.UpdateHighlight` surligne en
`TALENT_HIGHLIGHT_FULL` (0,07 ; 0,48 ; 0,48 sur `TalentBuiderHighlighted`) les cases du même
talent et celles des talents liés, et `ClassBaseTalent` pose `HighlightBlueFull` (`Highlighted`,
mélange additif) sur les sorts du livre concernés. Le lien vient de `GetLinkedTalents`, que
`ClassBuild.CalcTalentLinkedResources` rend réciproque ; dans les données, c'est le tableau de
sorts de la partie fixe de l'`AbilityResource` du rubis (`+0xE8` en 17.0 : « Sève toxique » →
« Chute des feuilles »), extrait en `links` (563 rubis liés sur 682 en 17.0). Ce tableau
n'existe pas avant la 17.0 (aucune référence rubis → sort du livre en 15.0/16.0) : pas de
surbrillance de liens dans les versions anciennes. Au toucher, sans survol : un premier toucher
sélectionne la case (infobulle et liens), un second ajoute un rang, l'appui long en retire un.

**Icônes sans fond.** Certaines icônes (potions, soleils, 39 × 39, 32 × 39, 25 × 25…) occupent
le coin haut-gauche d'une texture de 64 × 64 : le jeu n'en affiche que la zone utile
(`realWidth × realHeight` de la `UITexture`), étirée sur la case, sur le fond normal de la case
(damier ou `BaseTalentBack`). L'extracteur recadre donc chaque icône sur cette zone : champs
`+0x88`/`+0x8C` en 64 bits ; en 32 bits, repérés par le marqueur `FFFFFFFF, dimension` (7.0-11.x :
hauteur et largeur utiles 0x14 plus loin ; 1.1-4.0 : largeur et hauteur 0xC avant, ordre vérifié
sur les icônes de monnaie 32 × 39). Test : aucune icône extraite n'a plus son dessin confiné au
coin haut-gauche. Les versions
anciennes sont dessinées dans ce même cadre (grilles 7 × 7 ou 9 × 7 centrées sur le damier,
note en pied de fenêtre).

Écarts assumés avec le jeu : les étoiles de recommandation (`RecommendedStar(Silver)`,
priorité fournie par le serveur) ne sont pas affichées ; les boutons du pied servent le site
(`SavedBuilds` → version, `ChangeClass` → classe, `LearnSelected` → copier le lien,
`ResetSelected` → réinitialiser ; « activer le build » masqué) ; le build II est inerte ; les
textes français des compteurs viennent de la capture du client FR (le client 17.0 n'a que
l'anglais et le russe) ; le nom français d'une classe est repris de la dernière version qui en a
un. Icônes de classe Paladin et Guérisseur : les fichiers sont dans `BaseLocall_x64.pak` du
17.0 mais son `pack.bin` n'a pas de `UITexture` pour eux ; leurs dimensions viennent de la
`UITexture` de même chemin du client FR 16.0 (provenance dans `ui_class_icons` du manifeste et
dans `from`/`dimsFrom` des textures).

Poids : ≈ 9,6 Mo de JSON de talents, 1 150 icônes PNG dédupliquées (6,4 Mo), fenêtre ≈ 1,5 Mo
(29 Ko de JSON, 52 textures).

### Calculateur

Clic : +1 rang (case de grille : +1 case) ; clic droit, ou appui long au toucher : −1 ; Maj :
tous les rangs permis (grille : toutes les cases accessibles du même talent). Les compteurs
« Points de compétence » et « Événements de développement » suivent en direct, au format du jeu
(points libres / total). Deux builds indépendants, comme le jeu : les boutons I / II basculent
de l'un à l'autre (double spécialisation, par exemple dégâts et soins), chacun avec ses compteurs.

Règles (`src/data/talents.build.ts`), reprises de `ClassBuild`/`ClassState` :

- **Livre** : le rang *r* coûte *r* points (1, 2, 3 : 6 pour un sort complet) ; une couche n'est
  accessible que si les couches précédentes totalisent son palier (données `layers[i].points` :
  0, 4, 11, 18… 60 en 7.0-17.0 ; 0, 4, 12… en 1.1-4.0), rangs de départ compris ; un sort qui a
  un parent (`parentTalent`) ne dépasse pas le rang de ce parent. Retirer un rang recalcule comme
  le jeu : rangs devenus hors palier ramenés, enfants ramenés au rang du parent.
- **Grilles** : une case coûte 1 point et doit toucher (4-voisinage) une case apprise reliée à la
  case de départ (déclarée par la ressource, sinon le centre). Une case de départ qui porte un
  talent est apprise d'office ; vide (quelques grilles 8.0/9.0/11.0), elle sert d'ancre. Retirer
  une case retire celles qui ne sont plus reliées au départ.
- **Première couche** offerte au rang 1 dans toutes les versions (les trois sorts de départ).
- **Totaux** : absents des données du client (accordés par le serveur au fil des niveaux) ; ils
  viennent de `points` dans `tools/talents_manifest.json` (avec leur source, recopiés dans l'index
  par `python3 tools/extract_talents.py --index-only`).
  - 17.0 : **82** points de compétence et **77** événements de développement, relevés dans la
    fenêtre du jeu d'un personnage au niveau maximal. Le script affiche `libres + dépensés +
    appris − 3` : les trois sorts de la première couche au rang 1 et les trois cases de départ
    sont offerts, ce que confirme la capture (rangs appris = 85 = 82 + 3).
  - Calculateurs en ligne consultés (23/09/2026) : `en.allodswiki.ru/calc` (« allodsdb ») et
    `allodsdb.com` sont derrière une vérification de navigateur (preuve de travail et curseur à
    glisser) que l'outil n'a pas contournée : leurs totaux par version restent à relever à la main.
    `alloder.pro/calc-en` (`/c/data/en.config.json` : 91 / 80 en f2p, 86 / 76 en p2p) et
    `allods-sunshine.com/calc` (80 / 79) donnent les totaux des serveurs actuels, sans version :
    non repris, faute de pouvoir les rattacher à une version du site. Le premier retire aussi un
    point par sort de départ, comme le script du jeu.
  - Autres versions : pas de total, les compteurs affichent les points dépensés sans plafond
    (note en pied de fenêtre). Coût d'une case de grille (1) et des rangs (1, 2, 3) appliqués à
    toutes les versions.
- Les déblocages (`requiredUnlocks`, quêtes) sont ignorés, comme en « mode calcul » du jeu.

**Lien** : `?v=<version>&c=<classe>&b=<build I>&b2=<build II>&s=2`, chaque code au format
`1.<livre>.<grille 1>.<grille 2>.<grille 3>` ; `s=2` quand le build II est affiché. Un ancien
lien à un seul build (`b`) reste valable ; un build invalide est signalé sans toucher à l'autre.

- `1` : version du format de codage ;
- livre : un chiffre par emplacement (rang), couche après couche, 4 par couche, zéros de fin
  retirés (`3330` = trois sorts au rang 3 sur la première couche) ;
- grille : cases apprises en base64url (A–Z, a–z, 0–9, `-`, `_`), 6 cases par caractère, bit de
  poids faible d'abord, ligne après ligne sur la largeur de la grille, `A` de fin retirés ; la case
  de départ offerte n'est pas codée ;
- segments vides de fin retirés ; l'état de départ n'a pas de `b`. Un build complet de 17.0 (82 + 77
  points) tient en moins de 90 caractères.

Un lien est refusé (note en pied de fenêtre, build remis à l'état de départ) si la version ou la
classe est inconnue — pas de repli sur une autre version, les grilles changent —, si le format
n'est pas `1`, si le code est mal formé, trop long, désigne un emplacement vide ou un rang trop
haut, si le build viole une règle (palier, parent, case détachée, rang de départ manquant) ou
dépasse les totaux. Tests : `src/data/talents.build.test.ts` (règles, aller-retour, refus, build
complet sur les données réelles 17.0), `src/screens/TalentsScreen/TalentBuilder.test.tsx`
(placements des scripts, compteurs, gestes), `tools/tests/test_luajit.py`.

## Lorebook (préparation)

Étape de préparation d'une future page **Lorebook**, dont la langue cible est l'**anglais**. Pas
encore de page : `tools/extract_lore.py` rassemble les textes de lore **officiels** du client, leur
anglais officiel quand il existe, un glossaire russe → anglais et un index du corpus communautaire.

    python3 tools/extract_lore.py              # ≈ 80 s, écrit public/game/lore/
    python3 tools/extract_lore.py --evaluate   # + précision du classifieur de types (80/20)
    python3 tools/extract_lore.py --fr-client "/chemin/Allods Online FR (FR)"   # autre client FR

### Sources

Toutes décrites dans `tools/lore_manifest.json` ; une source optionnelle absente est signalée.
Chemins surchargeables : `--client` / `ALLODS_RU_CLIENT_DIR` (client 17.0), `--fr-client` /
`ALLODS_FR_CLIENT_DIR` (à défaut `ALLODS_CLIENT_DIR`, la variable du client FR des autres outils),
`--server-root` / `ALLODS_SERVER_ROOT`, `--corpus` / `ALLODS_LORE_CORPUS`.

- **Dernier client officiel** (`/mnt/h/MyGames/AllodsRU`, 17.0.01.64) — référence. `Texts_x64.pak`
  contient `pack.rus.loc` et `pack.eng_eu.loc` : deux tables de 277 187 textes **alignées index par
  index** (même empreinte `5e102aa3`). L'anglais est celui de l'**édition européenne** : 250 654 des
  250 869 textes anglais du client se retrouvaient à l'identique dans les packs officiels EU 16.0
  (CDN my.games, contrôle ponctuel ; ces packs ne sont plus une source). Une entrée restée en cyrillique n'a pas de traduction officielle. Le client propose
  d'ailleurs cet anglais au joueur (`Profiles/localizations.cfg` : `eng_eu:English`).
- **`Bin/pack.bin`** (`BaseLocall_x64.pak`, 703 Mo décompressé) — la base de ressources compilée.
  Elle ne contient pas les chemins, mais chaque ressource y référence ses textes par leur index dans
  les `.loc` : on sait quelle ressource porte quel texte, à quel décalage, ce qui regroupe les textes
  (une quête = nom, objectif, textes de début, de vérification et de fin). Format décodé dans la
  docstring de l'outil (tables de hachage à pointeurs auto-relatifs ; la table S3 associe le
  `resourceId` des xdb à la ressource). Les pointeurs du corps (références entre ressources,
  tableaux) sont nuls dans le fichier ; une **table de relocation** de 7,66 M paires
  `(emplacement | étiquette, cible)` suit la dernière ressource et permet de les résoudre.
- **Arbre serveur** (`/mnt/f/ALLODS ONLINE SERVER/Allods 7.0/game/data`, dépôt git lu par
  `git cat-file`, contenus jusqu'à ZC14/Ferris/Umoir malgré l'étiquette 7.0) — chemins de
  ressources, types (balise racine du xdb) et champs (`name`, `startText`…) des contenus qui y
  figurent : 121 488 ressources reliées au client par leur `resourceId`. Pour les ressources plus
  récentes (Eden, Jigran, Kadagan, Kvator, Isa, Suslanger, Airin…), le type est **déduit** de la
  disposition binaire par un classifieur bayésien naïf (décalages des textes + silhouette des
  premiers mots) : **94,9 %** de bonnes réponses sur 12 612 ressources connues tenues à l'écart ;
  quêtes 100 %, dialogues et objets 99,9 %, PNJ 98,9 %, zones 98 % (messages `TextMessage` : 77 %).
- **Client FR officiel** (`/mnt/h/MyGames/Allods Online FR (FR)`, 16.0.01.78.2, français seul :
  `Texts_x64.pak` → `Bin/pack.loc`, 264 463 textes ; `BaseLocfra_x64.pak` → `Bin/pack.bin`) —
  source du français, sans autre dépendance. Son `pack.bin` relie ses textes à ses ressources
  comme pour le 17.0 ; une ressource commune (même `resourceId`) au même décalage de champ donne
  la traduction (`bridge_fr`). Les deux `.loc` suivant l'ordre des chemins, l'écart d'index
  17.0 → 16.0 est constant par plages : un appariement n'est gardé que si son écart est
  **majoritaire** parmi les 8 appariements voisins (avant ou après) ; un « appariement » à écart
  nul est un entier identique dans les deux builds, pas un texte, et il est écarté ; les trous
  entre deux ancres de même écart (≤ 100 index) sont comblés par cet écart si les `<t href>` et
  variables concordent — le même principe que le recalage des sous-titres des cinématiques
  (décalage d'index constant par ressource).
- **Corpus communautaire** (`refs/lorebook`, git-ignoré, fourni par **Makar Terentiev**,
  GitHub [DarkyAndSparky](https://github.com/DarkyAndSparky/atlas-ao), voir « Provenance ») —
  jamais recopié : il est apparié au client et **référencé par chemin**. Les ~2 000 images (art de
  fans, fonds d'écran, artbook) sont écartées ; les dumps bruts de textes client (`Texts.pak`,
  `текстовик 15.0/pack.txt`) ne servent pas de source.

Langues rencontrées dans les autres clients (pour mémoire) : RU 17 (sauvegarde) = pak identique au
client de référence (ru + eng_eu) ; FR 8.0 / 9.0 / 15.0 / 16.0 = français seul ; 2.0.04 = anglais
(époque gPotato) et 4.0 « Nova » = anglais, français, russe, arabe, portugais, dans l'**ancien
format** de `.loc`, qui porte encore les chemins des textes ; 3.0 arabe = arabe ; « AllodsLegend »
(4.0) = russe en `.txt` par chemin ; 11.0 « Warp » = russe ; 11.0-steam = anglais, mais sans pak de
textes téléchargé ; « Revelation 7.0 » (client de serveur privé) = anglais + russe, ancien format ;
Cloud Pirates (autre jeu) = en, fr, de, pl, tr.
L'anglais officiel ne se limite donc pas aux vieilles versions : l'édition européenne a suivi le
jeu jusqu'à la 16.0.

### Méthode

1. Lecture des deux `.loc` (alignés) et de `pack.bin` ; balayage des références de textes (u32 aligné
   suivi d'un u32 nul). Le propriétaire d'un texte est la ressource dont les autres textes sont ses
   voisins d'index (les `.loc` sont triés par chemin de ressource) : 273 897 textes rattachés.
2. Rattachement à l'arbre serveur (contenu identique au caractère près, `href` exceptés) puis
   apprentissage `(type, décalage) → champ`. Un texte dont la ressource existe dans l'arbre serveur
   mais dont le russe a changé porte `ru_revised` : **l'anglais officiel peut alors traduire
   l'ancienne version** (3 216 textes, surtout les quêtes réécrites des zones de départ de
   l'Empire et de la Ligue).
3. Sélection des types à portée narrative → catégories : `quests` (QuestResource), `dialogues`
   (Cue : option du joueur + réponse du PNJ), `library` (objets lisibles : pages de livres, lettres,
   journaux — `kind: document` — et descriptions d'ambiance — `kind: flavor`), `scenes`
   (répliques scriptées, résumés d'intrigue, messages au monde), `events`, `places`, `characters`
   (PNJ nommés : titre ou nom propre), `factions` (factions, races, classes), `mail`, `secrets`
   (secrets du monde, voir plus bas).
   `series.json` regroupe les documents en plusieurs pages (« Путеводитель Данаса », « Летопись
   Валиров », « Архив Скракана »…).
4. Rendu : `<t href>` résolus dans la bonne langue, balises du jeu retirées, variables en `{nom}`.
5. Noms : l'**anglais officiel fait foi** partout — `glossary.json` est la référence (Смеяна →
   Catherina, Найан → Zayan, Иркалла → Hirkalla, Кадаган → Xadagan…). Un texte `ru_revised` garde
   son anglais officiel, marqué ; sa retraduction viendra plus tard (rien n'est retraduit ici).

### Secrets du monde

La ressource `WorldSecrets` (`Mechanics/GameRoot/WorldSecrets.xdb`) est un tableau de secrets, dont
chacun porte un tableau d'étapes, dont chacune porte un tableau de quêtes (`path`). Ces tableaux
imbriqués sont rangés dans la région d'autres ressources et leurs pointeurs sont nuls dans le
fichier : la **table de relocation** de `pack.bin` les résout exactement (élément de 56 o : étapes
@8, ressource du secret @48 ; étape de 120 o : `finalQuest` @8, `path` @48, texte « pas encore
disponible » @76, `startQuest` @80, texte de l'étape @148 ; taille d'un tableau 44 o après son
pointeur). Résultat : **50 secrets, 283 étapes** (l'ancienne recherche par motifs en trouvait 47 et
265), chacun avec son nom, sa description, sa question, son état, son titre une fois résolu, et
pour chaque étape son texte, son texte d'attente et ses quêtes (`quests.start`, `quests.final`,
`quests.path` : identifiants `r<rid>` des entrées de `quests.json`, 1 863 des 1 904 références y
figurent). Vérification sur l'arbre serveur : les 32 secrets qui y figurent sont retrouvés ; 127
étapes sur 131 ont exactement les mêmes textes et quêtes de début et de fin (les 4 autres suivent
une étape **ajoutée** depuis dans « Абсолют » et « Боги Сарнаута »), 120 le même `path`. 814
textes : 67 % avec anglais officiel, **90 % avec français**. Les 18 secrets récents (Великий Бал,
Валиры, Бог Тьмы, Потерянная Иса…) n'ont pas de chemin xdb.

### Sorties (`public/game/lore/`)

| Fichier | Contenu |
|---|---|
| `index.json` | sources, empreinte, couverture par catégorie et par ère, poids des fichiers |
| `<catégorie>.json` | entrées par ressource : `id` (`r<rid>` de pack.bin), `resource_id`, `type`, `type_source` (`server`/`inferred`/`relocation`), `path` (xdb) si connu, `era`, et par champ `loc` (index dans les `.loc` 17.0.01.64), `en`, `en_status`, `ru_revised`, `fr` (présence) ; `secrets.json` ajoute `order` et `components` (étapes) |
| `ru/<catégorie>.json`, `fr/<catégorie>.json` | tables `loc → texte` |
| `glossary.json` | 3 706 noms propres et termes russe → anglais officiel, variantes, fréquence dans le corpus |
| `community.json` | `credit` (auteur, dépôt, licence, ligne de crédit) et `files` : pour chaque fichier du corpus, classe, couverture, textes du client retrouvés, `credit` et `source` (provenance précise) |
| `atlas.json` | `credit`, `credit_source` et les allods de l'atlas communautaire ↔ client (ligne, nom, anglais officiel) |

Poids : **52,2 Mo** (13,8 Mo gzip) : 19,0 Mo pour les fichiers anglais + métadonnées, 20,9 Mo
pour `ru/`, 12,4 Mo pour `fr/` ; `quests` (8,5 Mo en, 11,4 Mo ru, 6,8 Mo fr) et `dialogues`
(6,2 / 7,1 / 4,3 Mo) pèsent le plus. La page devra charger par catégorie et par langue, jamais tout
d'un bloc.

### Couverture (client 17.0.01.64)

Client entier : 272 146 textes non vides, **250 869 avec un anglais officiel (92,2 %)**. Sélection
lore : 31 699 entrées, 71 697 textes, 1,72 M mots russes.

| Catégorie | Entrées | Textes | Anglais officiel | Français | Mots EN disponibles | Mots RU à traduire |
|---|---:|---:|---:|---:|---:|---:|
| quests | 6 962 | 32 289 | 89,5 % | 93,2 % | 993 475 | 96 749 |
| dialogues | 13 674 | 22 836 | 89,3 % | 93,7 % | 577 889 | 88 351 |
| scenes | 3 567 | 4 001 | 87,0 % | 91,4 % | 64 433 | 7 687 |
| library | 663 | 1 319 | 58,6 % | 72,6 % | 26 938 | 16 410 |
| mail | 698 | 1 667 | 90,2 % | 93,3 % | 25 675 | 2 849 |
| secrets | 50 | 814 | 67,4 % | 90,2 % | 19 371 | 12 275 |
| characters | 4 338 | 6 804 | 91,8 % | 90,7 % | 13 985 | 1 137 |
| events | 45 | 115 | 98,3 % | 98,3 % | 4 508 | 27 |
| places | 1 298 | 1 308 | 96,2 % | 96,9 % | 3 053 | 100 |
| factions | 404 | 544 | 97,4 % | 83,8 % | 1 750 | 23 |
| **total** | **31 699** | **71 697** | **88,9 %** | **92,6 %** | **1 731 077** | **225 608** |

Par ère : **98,5 %** des textes anciens (présents dans l'arbre serveur) ont un anglais officiel,
**79,7 %** des récents. Ce qui manque est surtout la 17.0 (Kvator : « Сказ о Валирах », « Сказ о
Соловье-разбойнице »), Kadagan, les « Новости 1025/1026 года », le Jubilé 2025, une partie des
objets d'ambiance récents et des secrets récents ; 163 793 mots russes supplémentaires ont un
anglais **peut-être périmé** (`ru_revised`) à relire.

**Français (client FR 16.0.01.78.2)** : 231 357 textes du client 17.0 (197 516 par ressource
commune, 33 841 comblés par décalage), dont **66 404 textes lore sur 71 697 (92,6 %)** — contre
63 270 (88,3 %) avec l'ancien pont par les packs EU. Ce qui manque : textes absents du 16.0
(contenu 17.0), ressources sans voisin fiable, textes restés en cyrillique ou en anglais dans le
client FR. **Fiabilité**, mesurée contre le pont anglais → français des packs EU (outil de mesure
seulement, plus une source) sur les 128 494 textes appariés dont l'anglais est unique dans les deux
packs : **4 faux (0,003 %)** et 28 variantes proches (texte révisé entre les deux builds) ;
l'ancienne règle « ≥ 2 voisins d'accord » en commettait 156 (0,12 %), surtout des répliques de
cinématique décalées d'une ligne et des entiers pris pour des textes. Sur les textes lore communs
aux deux méthodes, 62 643 / 62 665 sont identiques ; parmi les 22 écarts, des révisions entre builds
(nombre de monstres, noms de PNJ) et quelques erreurs de l'ancien pont (« Остров Нордхейм » y
donnait « Grotte du dragon »). 45 % des textes appariés ne sont pas vérifiables ainsi (anglais non
unique ou absent) ; la méthode étant la même, on en attend la même fiabilité.

### Provenance

Chaque entrée est étiquetée :

- **in-game** — texte livré dans le client officiel ; `en_status` dit s'il existe un anglais
  officiel (`official`), s'il manque un fragment (`partial`) ou rien (`missing`).
- **official** — texte officiel hors jeu (annonces de mise à jour, articles datés du site, interviews
  de l'équipe, FAQ scénario Discord : réponses présentées comme officielles, **à vérifier**).
- **community** — travail de fans, jamais recopié, référencé par chemin.

Corpus (`community.json`, 128 fichiers dont 115 `.txt`) : 56 `in-game (official EN available)`,
8 `in-game (RU/FR only)`, 25 `official out-of-game`, 29 `community`, 10 `excluded` (dumps bruts,
autres jeux : Allods Adventure, Cloud Pirates, Аллоды 1998). La règle : un texte dont au moins la
moitié des phrases se retrouve dans le client est « en jeu » (et « EN disponible » si 80 % de ces
phrases ont un anglais officiel) ; sinon, classement du manifeste (`provenance`), puis titre daté
(format des articles du site officiel) ; sinon « community ». Les récits d'origine inconnue
(« Путь Изгнанника », « Найан. Груз тысячелетий », « Воспоминания Смеяны »…) sont ceux du matériel
fourni par Makar Terentiev : paternité et origine **à confirmer avec lui** avant toute reprise.
Surprise utile : les lettres des jubilés 2023 et 2024 sont des textes **du jeu** (avec
anglais officiel), celle de 2025 aussi (sans anglais).

Atlas (`АТЛАС АЛЛОДЫ табл.xlsx`) : **318 allods** (la feuille s'étend sur 1 008 lignes, mais
318 seulement sont remplies). 65 correspondent à une zone du client, 112 à un nom exact d'un autre
texte, 49 ne sont que **mentionnés** dans des textes, 92 introuvables ; **173 ont un nom anglais
officiel**. Hors catégories d'autres jeux (Allods Adventure, Cloud Pirates), 216 des 274 allods
sont rattachés au client (79 %).

### Crédit du matériel communautaire

Le matériel communautaire (l'atlas et les récits d'origine inconnue) vient de **Makar Terentiev**
(Макар Терентьев, GitHub **DarkyAndSparky**), auteur du dépôt
[atlas-ao](https://github.com/DarkyAndSparky/atlas-ao) — « site-atlas non officiel de l'univers
d'Allods Online » (Node.js + SQLite : carte interactive, catalogue wiki, éditeur), créé le
31/07/2026, étudié le 23/09/2026 :

- **Ce qui est dans le dépôt** : le code du site et `server/seed-data.json`, **la même table de
  318 allods** que `АТЛАС АЛЛОДЫ табл.xlsx` du corpus (318/318 noms, aux espaces près) — nom,
  climat, taille, détenteur, faction, catégorie, archipel, type, extension, carte ; 9 courtes
  descriptions, aucun texte d'histoire.
- **Ce qui n'y est pas** : les récits, les documents de travail de l'atlas (`.docx`, « Астральные
  Острова », « BETA », `sec list`) et les autres textes de `refs/lorebook`, fournis directement par
  l'auteur. Quelques pièces du corpus ont une autre origine, notée dans `source` : billet de blog
  reposté sur le forum (druidsdiary), artbook de Fardreamer, extraits d'anciens clients,
  « Энциклопедия Сарнаута » signée « Номарх Авилар » (origine à confirmer).
- **Licence** : MIT, mais **pour le code du site seulement**. Le fichier `LICENSE` exclut
  explicitement le contenu du jeu et les **données de l'atlas** (`server/seed-data.json`,
  `uploads/`, `atlas.db`) ; le site se présente comme un projet de fans « собранные энтузиастами ».
  Aucune licence n'est accordée sur les données ni sur les textes : **l'autorisation de l'auteur a
  été obtenue** (septembre 2026) pour reprendre l'atlas et les récits sur la page Lorebook, avec le
  crédit ci-dessous.

L'attribution est enregistrée dans `tools/lore_manifest.json` (`credit`), reportée en tête de
`community.json` et d'`atlas.json`, et par fichier (`credit`, `source`). Ligne de crédit prête pour
la future page :

> Allods atlas and community lore material compiled by Makar Terentiev (DarkyAndSparky) —
> https://github.com/DarkyAndSparky/atlas-ao

### Droits

Les textes du client appartiennent à l'éditeur (Astrum / My.Games) — comme les autres assets de
`public/game/`. L'atlas et les récits de Makar Terentiev sont repris avec son accord et le crédit
ci-dessus. Les autres travaux de fans ou de tiers du corpus (« Энциклопедия Сарнаута », billet de
blog, artbook) ne sont pas repris ; les images du corpus ne sont pas utilisables (droits inconnus).

### Page Lorebook (`/lorebook`)

Entrée « Lorebook » de l'accueil (icône du grimoire). Interface en français ou en anglais (i18n du
site) ; **contenu en anglais par défaut**, avec un sélecteur **EN / FR / RU** des textes
(`?text=fr` pour partager, choix mémorisé). Un texte sans anglais officiel s'affiche en français,
sinon en russe, avec le badge rouge « Not yet translated — French text » ; un texte `ru_revised`
porte le badge discret « English may predate a Russian revision ». Décor du journal de quêtes du jeu
(cadres `QuestLog/MainFrameLeft|Right`), plaque de titre `WindowHeader/TiledHeader`, onglets aux
boutons de l'hôtel des ventes, lecture sur le parchemin du courrier (`MailBox/BackgroundMessage`) ;
colonne de lecture de 72 caractères, une seule page à la fois sur mobile.

    python3 tools/build_lorebook.py     # ≈ 15 s, écrit public/game/lorebook/ depuis public/game/lore/

| Section | Contenu | Entrées |
|---|---|---:|
| Timeline | chronologie de Sarnaut (communautaire, 3 ères), 45 événements, 1 403 scènes et narrations par région | 1 451 |
| Atlas | les 318 allods de l'atlas de Makar Terentiev (données, descriptions), 13 notes d'atlas, 111 régions, 1 298 lieux du jeu | 1 740 |
| Library | 11 livres et séries (pages dans l'ordre), 10 récits communautaires, 143 documents, 507 lettres, 447 descriptions d'ambiance | 1 118 |
| Characters | 3 640 PNJ nommés (homonymes fusionnés) avec leurs dialogues, 403 factions/races/classes, 10 517 autres dialogues | 14 560 |
| World Secrets | 50 secrets, leurs étapes et les quêtes de chaque étape | 50 |
| Quests | 6 962 quêtes par région | 6 962 |

**URL stables** : `/lorebook/<section>/<id>` (`r<rid>` pour les textes du jeu, `a-…` allods,
`z-…` régions, `s-…` séries, `c-…` textes communautaires), `/lorebook/<section>?group=…`,
`/lorebook/search?q=…`. **Liens croisés** : quête → secret, PNJ et région ; PNJ → quêtes, région
et répliques ; région → lieux, quêtes et PNJ ; allod → lieu du jeu ; étape de secret → quêtes ; et
dans les textes, chaque nom propre connu (PNJ, lieu, allod, secret, faction : 3 875 noms en anglais)
devient un lien vers son entrée. Les liens réplique → PNJ (3 156), réplique → quête (1 801) et
quête → PNJ (1 606) viennent des **références entre ressources** de `pack.bin` (table de
relocation, `public/game/lore/links.json`).

**Recherche** (noms, titres, textes, dans la langue du contenu) : index inversé précalculé,
fragmenté par les deux premiers caractères du mot (760 fragments par langue) ; une requête ne
charge que le fragment de ses mots puis les blocs du répertoire (64 entrées) des 30 premiers
résultats, titres en tête. **Chargement à la demande** : `meta.json` (7 Ko) à l'accueil, la liste
de la section ouverte (`list/<langue>/`, 2 Ko à 870 Ko ; 250 Ko gzip pour les personnages), le bloc
de l'entrée (~90 Ko) et, s'il manque un texte, le même bloc dans la langue de repli ; les listes
sont **virtualisées** (seules les lignes visibles existent dans le DOM). Poids total sur disque :
78 Mo (textes 48, index 18, répertoire 7, listes 5), dont rien n'est chargé d'un bloc.

**Matériel communautaire** (repris avec l'accord de Makar Terentiev) : badge vert « Community »,
encadré « Community text, translated by Allodex », ligne de crédit et source sur chaque entrée,
crédit en pied de page. Traductions faites par Allodex (fidèles, noms anglais officiels du
glossaire et des textes parallèles du client), dans `tools/lorebook/` :

- `community/` : la chronologie et dix récits — « Memories of Catherina », « Zayan. The Burden of
  Millennia », « The Exile's Path », « The Shadow of the Void over Sarnaut », « Mauni the Dancer and
  the Harsh Winter », « Report on the Arisen Community of Xadagan », « Sarang Kido's Report to the
  Scientific Council », « A Spark in the Ashes of Illusions », « A Letter from Skrakan's Archive »,
  « Dreams of the Great Tree » (≈ 36 600 mots russes) ; le russe original reste lisible en mode RU ;
- `atlas/allods.json` : la table des 318 allods (203 noms officiels, 115 traduits ou translittérés,
  marqués « Unofficial name ») ; `atlas/descriptions.json` : sections 1 et 2 de l'atlas (îles des
  jeux classiques, îles mentionnées, allods du scénario) ; `atlas/astral-islands-*.json` : les
  quatre documents des îles astrales (AO 2.0+ parties 1 à 3, BETA) (≈ 28 000 mots russes).

Reste à traduire : les sections 3 à 7 de `ATLAS ALLODS.docx` (≈ 12 000 mots, en partie redondantes
avec les documents des îles astrales), `sec list.txt` (liste de 2 400 mots) et deux notes courtes
(« Созвездия », `boses.txt`). Non repris : le billet de blog tiers « Край мира с форума АО »,
l'artbook de Fardreamer et l'« Энциклопедия Сарнаута » (droits de tiers).

Crédit affiché : *Allods atlas and community lore material compiled by Makar Terentiev
(DarkyAndSparky), https://github.com/DarkyAndSparky/atlas-ao*.

## Déploiement (production)

Le site public (`allodex.eu`, `allodex.online`, `allodex.allods-developers.eu`) est servi
**en statique par nginx** depuis `/srv/node/allodex/dist` sur `<utilisateur>@<serveur>`. Jusqu'au
22/09/2026 le vhost renvoyait vers le **serveur de développement de Vite** (pm2 `allodex`
→ `npm run dev`, port 5173) : la production tournait donc en mode développement — avec les
sondes de dev (`import.meta.env.DEV`) actives et les entrées désactivées en production
(Fatalités, Personnage) encore cliquables. Le processus pm2 est désormais **arrêté**
(`pm2 stop allodex`, état sauvegardé) ; il n'est plus nécessaire.

**Redéployer** (les sources sont déjà sur le serveur) :

    # 1. envoyer ce qui a changé (depuis le poste de dev)
    git diff --name-status <ref-serveur> main            # contrôler la liste
    rsync -az --files-from=<liste> ./ <utilisateur>@<serveur>:/srv/node/allodex/

    # 2. reconstruire sur place (≈ 5 min : la copie de public/game pèse 2 Gio)
    ssh <utilisateur>@<serveur> 'cd /srv/node/allodex && npm run build'

nginx sert `dist/` avec repli à page unique (`try_files $uri $uri/ /index.html`), cache d'un
an sur `/assets/` (noms hachés), de trente jours sur `/game/` et `/fonts/`, et `no-cache` sur
`index.html` — sans quoi un déploiement passerait inaperçu. Le vhost est
`/etc/nginx/sites-enabled/allodex.conf` ; les sauvegardes vivent dans `/root/nginx-backups/`
(**jamais** dans `sites-enabled/`, qui est inclus par joker : un `.bak` y est chargé et casse
la configuration pour cause de `listen` en double).

Rien à mettre dans un `.env` : l'application est une page statique, `vite build` fige
`import.meta.env.PROD` à la construction et le serveur n'exécute aucun code Node.

**Attention au dépôt du serveur.** `/srv/node/allodex` est un clone de `origin`, mais le
déploiement y copie des fichiers directement : son arbre de travail est donc en avance sur
son `HEAD` tant que la branche n'est pas poussée. Un `git pull`/`git checkout` sur le serveur
**remettrait une version plus ancienne en ligne**. Pousser `main` sur `origin` remet tout
d'aplomb (compter ≈ 1,8 Gio de transfert : l'historique contient chaque réexport des `.glb`).

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
- **Caméra dérivée du bol, calée sur les captures.** Les calques peints sont des arcs concaves tournés
  vers +X ; `Back6` est un bol un peu plus profond qu'une demi-sphère (fond à X = −91, bord à X = +16)
  dont la sphère ajustée a pour centre X = 27 : la caméra y est posée, à Y = −1, et regarde −X le long
  de l'axe du bol. Repère direct (`"mirror": false`) : la droite de l'image est +Y, où sont la tour et
  les rochers. Le cadrage est un réglage sur les captures : trois repères de la tour (boussole, vergue,
  rouage) fixent la pente et le champ, mais pas la hauteur, car ils sont tous à 79 unités (monter la
  caméra de 7 unités ne les déplace que de 0,03 NDC). C'est le navire de raid, qui passe à 15-25 unités,
  qui la fixe : `refs/captures-ui/menu-5.0-frame2-raid-ship.png` montre son pont vu d'au-dessus. Balayage
  de Z = −4,9 à +9, cible et champ résolus à chaque hauteur : **Z = −2** redonne la capture vers 71,6 s
  (voiles, pont, dômes et tour à 1-3 % de la hauteur d'image près), cible (−52, −1, 1,82), champ 48,5°.
  L'ancien cadrage (Z = −4,9) passait sous la coque. La calotte d'énergie à l'avant
  (`group_SphereFront01/03`, additive) remplissait alors l'image, et c'était la « bulle ». Elle est
  native (voile rose au bord droit de la capture) et ne couvre plus l'image qu'une seconde, vers
  74-75 s, quand la proue frôle la caméra. La couleur de fond est celle du bol (médiane des couleurs
  de sommet ×2, modulée par sa texture) ; plus de brouillard ajouté (ses paramètres 5.0 ne sont nulle part).
- **Traînée `ship_tail`.** Sa piste brute passe déjà par sa rotation de bind (l'identité) de l'image
  1725 à la fin, exactement quand son échelle vaut 1 ; à l'image 0, où elle est invisible (échelle
  nulle), elle porte un demi-tour autour de Z. `restore_fixed_rotations` choisissait sa branche d'Euler
  sur l'image 0 et posait 180° sur Y et X : la traînée, retournée, se refermait autour du navire. Garde
  (`reaches_bind`) : une piste qui atteint déjà son bind garde ses canaux fixes à 0. C'est la seule
  articulation de la 5.0 dans ce cas (les autres plafonnent à 0,997 de produit scalaire).
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
- **le balancement du train est amplifié ×3 — seul écart non natif de la scène.** À son
  amplitude native (3,8° crête à crête, 16,7 s de période), la cabine, à 7 unités de son
  articulation, ne parcourt que 0,47 unité dans une scène large de 92 : le mouvement est
  invisible à l'écran. Le décodage n'est pas en cause (voir l'`aabb` ci-dessus) ; le client
  devait donc ajouter ce mouvement hors données, comme il code sa caméra.
  `tools/scenes/v6_0.py::amplify_train_swing` multiplie l'angle **autour de la position
  moyenne de la piste** — la cabine garde sa place, seul son débattement change (11,4° crête
  à crête). Facteur dans `TRAIN_SWING_FACTOR`, choix de l'utilisateur du 22/09/2026 ;
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
nuages sombres 0,01 ou 0,02 tuile/s (`Back_Cloud_*`), brume de vallée `MidClouds_01` −0,02 à
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
