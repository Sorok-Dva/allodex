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
- `/cinematics` : toutes les cinématiques du jeu en film complet par faction, avec sous-titres officiels FR/EN/RU, et transcription automatique signalée pour les deux chapitres doublés que le jeu ne sous-titre pas (voir « Cinématiques » ci-dessous).
- `/talents` : arbres de talents de chaque classe de la 1.1 à la 17.0 dans la fenêtre TalentBuilder du jeu, calculateur de build (deux builds) partageable par lien (voir « Talents »).
- `/lorebook` : lore officiel du jeu en anglais (FR/RU en option), atlas et récits communautaires crédités, recherche et liens croisés (voir « Lorebook »).
- `/fatalities` (développement seulement) : les 26 fatalités rejouées avec modèles, effets et sons du client 17.0 (voir « Fatalités »).
- `/stats` : tableau de bord d'audience (pages vues, visiteurs en direct par page, provenances…), protégé par mot de passe (voir « Référencement et audience »).
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
Succès. Eden, Jigran, Xadagan et Quator y sont intégrés. Les correspondances vivent
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
muet, précharge le suivant, d'où un passage sans attente ; après un changement de chapitre, le
lecteur libéré attend 1,5 s avant de précharger (la lecture des modèles d'une scène moteur ne tombe
pas pendant le fondu). **Fondus** : un voile noir ferme chaque chapitre et ouvre le suivant (0,6 s,
vidéo comme scène moteur) et reste posé tant que le lecteur montré n'est pas prêt ; une scène moteur
n'est prête qu'une fois préparée (programmes compilés, textures envoyées quelques-unes par image,
premier rendu), et son horloge ne part qu'ensuite. `?faction=league|empire` ouvre
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
  répliques de Quator ; les voix des scènes moteur des quêtes sont dans `BaseLocall_x64.pak`
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

### Sous-titres transcrits (pas ceux du jeu)

Deux chapitres doublés n'ont aucune ressource de sous-titres dans le client : « Prologue — Vychegrad »
(`warp-prologue`, 10.0, narrateur, 18 répliques) et « Pas prévu au plan » (`awakening-not-by-plan`,
11.0, échanges radio, 8 répliques). Leur voix russe est **transcrite automatiquement**, en local, par
`tools/transcribe_cinematics.py` (faster-whisper, CPU `int8`, filtre de voix, pas de reprise du texte
précédent ; `small` d'abord, `medium` retenu pour les deux), puis relue et traduite à la main dans
`tools/cinematics_transcripts.json` (versionné) : texte russe corrigé, anglais et français avec les noms
officiels des textes du client (Вышеград = Hightown / Hauteville, « на краю мира » = Horizon, Ковчег =
the Ark / l'Arche, эра Аллодов = the Allods Era / l'Ère des allods), sortie brute de Whisper,
confiance, et notes de relecture (répliques douteuses de « Pas prévu au plan », recoupées par un second
modèle acoustique, wav2vec2 russe sans modèle de langue). Les segments inventés par Whisper sur la
musique ou le silence (« Редактор субтитров… », « СПОКОЙНАЯ МУЗЫКА ») sont écartés par le filtre ;
les onze vidéos sans dialogue déclaré n'en contiennent pas d'autres. Index : `subtitles.status:
"transcribed"`, pistes libellées « (auto) » ; le lecteur écrit « transcription automatique » dans la
liste des chapitres et, tant que ces sous-titres sont affichés, « Sous-titres : transcription
automatique, pas ceux du jeu » en haut de l'image. Les scènes moteur `ferris-awakening` et
`invasion-engineer-kania` n'ont pas de voix : rien à transcrire.

    python3 tools/transcribe_cinematics.py --list                  # chapitres doublés sans sous-titres
    python3 tools/transcribe_cinematics.py --only <id> [--model medium]   # transcrit (un chapitre à la fois)
    python3 tools/transcribe_cinematics.py --probe --only <id>     # segments et verdicts, sans rien écrire
    python3 tools/transcribe_cinematics.py --apply                 # pistes et index depuis la relecture

Un chapitre relu (`"reviewed": true`) n'est pas réécrit par une relance : la nouvelle sortie va dans
`draft` (`--replace` pour remplacer). `extract_cinematics.py` et `extract_engine_cutscene.py` réécrivent
ces pistes depuis le fichier de relecture, jamais par-dessus des sous-titres officiels.

Sorties : `public/game/cinematics/<id>/{video.webm, video.mp4, poster.jpg, fr.vtt, en.vtt,
ru.vtt}` et `public/game/cinematics/cinematics.json`, versionnées comme le reste de
`public/game/` (≈ 380 Mo : 193 Mo de MP4, 186 Mo de WebM, moins d'1 Mo d'affiches et de pistes ; environ 25 min 30 s de film par faction).

### Cinématiques moteur recréées en 3D

Les mini-cinématiques des quêtes ne sont pas des vidéos : le jeu les joue en temps réel. Vingt-neuf
sont **recréées dans three.js** avec les données du dernier client et jouées dans le film comme
des chapitres vidéo (même barre, mêmes raccourcis, sous-titres FR/EN/RU, voix russes) :

| Chapitre | Source du déroulé | Carte | Durée |
|---|---|---|---|
| Ferris 6.0 · « Rétrospective » (`ferris-retrospective`, quête `Ferris_4_secret1`) | serveur 7.0 | `Ferris4` (laboratoire) | 82 s |
| Ferris 6.0 · « Incident n° 42 » (`ferris-incident`, `Ferris_4_secret2`) | serveur 7.0 | `Ferris4` (base, couche inst2) | 42 s |
| Ferris 6.0 · « Un dialogue parfait » (`ferris-awakening`, `Ferris_4_6_1`) | serveur 7.0 | `Ferris4` | 13 s |
| Ferris 6.0 · « Le portail de Ferris » (`ferris-portal`, `FR4Intro`) | serveur 7.0 | `Ferris4` | 94 s |
| Ferris 6.0 · « La profanation du Fractal » (`ferris-fractal`, `Portal_Start`) | serveur 7.0 | `FerrisRaid` | 64 s |
| Ferris 6.0 · « Pas de retour » (`ferris-no-way-back`, `Portal_Ending_Main`) | serveur 7.0 | `FerrisRaid` | 44 s |
| Ferris 6.0 · « L’essaim » (`ferris-swarm`, `Swarm_CutScene`) | serveur 7.0 | `FerrisRaid` | 72 s |
| Ferris 6.0 · « La force de l’Ordre » (`ferris-power-of-order`, `Swarm_Ending_Main`) | serveur 7.0 | `FerrisRaid` | 54 s |
| Ferris 6.0 · « Les serviteurs de l’Ordre » (`ferris-order`) | serveur 7.0 | `FerrisRaid` | 51 s |
| Ferris 6.0 · « Le Locus » (`ferris-locus`) | serveur 7.0 | `FerrisRaid` | 106 s |
| Ferris 6.0 · « La chute du Locus » (`ferris-locus-fall`) | serveur 7.0 | `FerrisRaid` | 122 s |
| Invasion 7.0 · « La mort de l’ingénieur » (`invasion-engineer-kania`, Ligue) | client (`GameViewScene`) | `Inst_ZoneContested12_Start` | 13 s |
| Citadelle de Nihaz 12.0 · « Le monde caché » (`ao12-prologue04`, pilote) | manifeste | `AO12_PrologueInst` | 82 s |
| Zone de départ de l’Empire · « Au poste de commandement » (`empire-start-command-post`, zone `ComanadPost`) | serveur 7.0 (déclencheur) | `Inst_EmpireStart` | 12 s |
| Zone de départ de l’Empire · « L’artefact perdu » (`empire-start-lost-artifact`, récompense de `Quest4_1`) | serveur 7.0 (déclencheur) | `Inst_EmpireStart` | 28 s |
| Zone de départ de l’Empire · « L’ordre d’abordage » (`empire-start-boarding-order`, début de `Quest4_4`) | serveur 7.0 (déclencheur) | `Inst_EmpireStart` | 9 s |
| Zone de départ de l’Empire · « L’appareil volé » (`empire-start-stolen-device`, zone `TeleportPaladin`) | serveur 7.0 (déclencheur) | `Inst_EmpireStart` | 7 s |
| Zone de départ de l’Empire · « L’abordage » (`empire-start-boarding`, zone `Jump`, quête `Quest4_4`) | serveur 7.0 (déclencheur) | `Inst_EmpireStart` | 14 s |
| Zone de départ de l’Empire · « Le chevalier vaincu » (`empire-start-knight-defeated`, `DeathTriggerPaladinFinal`) | serveur 7.0 (déclencheur) | `Inst_EmpireStart` | 15 s |
| Zone de départ de la Ligue · « La mort du Grand Mage » (`league-klement-death`, zone `PaladinQuest`) | serveur 7.0 (déclencheur) | `Inst_LeagueStart` | 53 s |
| Zone de départ de la Ligue · « L’évacuation » (`league-evacuation`, quête `Quest_4_30`) | serveur 7.0 (déclencheur) | `Inst_LeagueStart` | 81 s |
| Zone de départ des Pridiens · « Ah, le cinéma ! » (`pride-cinema`, quête `Pride_1_9`) | serveur 7.0 (déclencheur) | `PridensStart` | 12 s |
| Zone de départ des Pridiens · « Le spectacle » (`pride-performance`, quête `Pride_1_11`) | serveur 7.0 (déclencheur) | `PridensStart` | 11 s |
| Isa 14.0 · six chapitres (`isa-unn-trance`, `isa-arrival`, `isa-fighting-pit`, `isa-fishers-legend`, `isa-freya`, `isa-captain-journal`) | client 17.0 (voir « Isa ») | `Isa`, `Isa_Prologue` | 21 à 91 s |

**Zone de départ de l’Empire** (arc `empire-start`, en tête du film de l’Empire ; le prologue de l’Empire vient juste après sa fin, choix de l’utilisateur) : dans le
17.0, les trois races de l’Empire (Xadaganiens, Orcs, Arisen) commencent au même tutoriel,
`Inst_EmpireStart` (navire astral attaqué par la Ligue), qui sort vers `Hadagan_Sanatorium` (Igsh,
d’après l’`ImpactTeleport` du 7.0) ; Pridiens et Aoidoi, factions à part à la création
(`chargen.json`), n’en font pas partie (le départ pridien, `PridensStart`/`Inst_PridensStart`, montre
des PNJ des deux factions). Le client 17.0 garde pour ce tutoriel deux `CameraTrackAction` (buffs 389009 et
389797, points identiques au millième aux `JumpCameraFix` et `IE1_Teleport_Camera` du 7.0) et deux
`GameViewScene` (389716, 389728, combattants des deux navires) ; `Hadagan_Sanatorium` n’a qu’une
`GameViewScene` de figurants (faucons au repos, pas de caméra : une vue de jeu, pas une cinématique).
Ces scènes ne sont pas des chaînes de buffs mais des **déclencheurs** (`"trigger"` du manifeste) :
la zone de script `Jump` (entrée du joueur, `impactsIn`) et la capacité de mort de Gradimir Belov
(`HealthTrigger`, porteur `trigger_owner`). Le déroulé en suit les branches `ImpactIfTarget`, les
impacts instanciés et ceux sur les avatars voisins ; il en relève les **états des stèles**
(`ImpactSetVisualState` : navire kanien `League_Ship_Final`, modèle `KaniaShip` et ses `idle`/
`idle01`/`special` ; stèles `Empire_Ship_Fight1`/`League_Ship_Fight1`, dont chaque état joue un
`GameViewScript` : combat en boucle, morts, disparition), les **explosions** des `ClientData`
(`CreatureFixedPointProjectileAction` : gabarit d’explosion posé au repère d’arrivée, retrouvé au
17.0 par ses gabarits et son `theGe`), les **sons** ponctuels (`Sound2DAction` des projets `World`),
les PNJ posés qui marchent (`GoThroughPath`) ou disparaissent, et la sortie du joueur
(`ImpactTeleport`, fin de scène). L’état de départ des stèles (laissé par le tutoriel avant le
déclencheur) et la musique/ambiance encore actives viennent du manifeste, justifiés par les zones
qui les posent. La scène commence au premier plan de caméra (avant, c’est la vue du joueur).
Stèle du 17.0 retrouvée par sa place (`SpawnLocation` : case de 32 m en `+0x30`, repère local en
`+0x24`) ; lacet propre d’un PNJ de `GameViewScene` en `+0xB8` ; délai `delayBefore` d’une action de
`GameViewScript` en `+0x2C` (recoupés sur le 7.0).

Corrections du tutoriel de l’Empire (toutes génériques, règles tirées des données) :

- **Composants d’état** (`StateComponent` : indices d’animations en `+0x68`, composant porté en
  `+0x88`, `stopForOtherAnimation` en `+0x99`, recoupés sur `KaniaShip` 7.0) : un composant montré tant
  que le gabarit joue l’une de ces animations. Le modèle de la stèle `League_Ship_Final`, `KaniaShip`,
  n’est qu’une boîte invisible : la coque du navire kanien (`KaniaShip_Clear` en `idle`,
  `KaniaShip_Break` en flammes en `idle01`, `KaniaShip_Part01` en `special`) et le Спрутоглав qui
  l’enserre (`AstralCtulhuShip`, `idle01`/`special`, à (100, −35, 0), échelle 0,75) sont ses
  composants d’état ; ils sont posés comme effets accrochés à la stèle, pendant les états qui les
  montrent (d’où les combattants kaniens qui flottaient : leur pont n’était pas dessiné). Le décor et
  les effets ne les posent pas (aucun ne les pilote).
- **Échelle de la `VisualMob`** (`+0xB4`, f32 ; 12 066 `VisualMob`, 8 971 à 1) appliquée aux acteurs :
  le Спрутоглав est à 0,4 (`AstralCthulhu_Inst`) ; à l’échelle 1 il traversait le navire. Il se
  déplace à sa `walkSpeed` (8 m/s) sur son chemin serveur, 14 m sous le pont (`z` 0,889 des
  `ServerObjects`) ; son modèle n’a pas de marche : il court (`Run`), choix documenté.
- **Portes** : un objet du décor qui porte une `StaticDevice` à `DoorResource` dans l’arbre 7.0 (le
  17.0 ne le dit pas : le serveur envoie l’état) est une porte. Elle est montrée dans l’état de sa
  ressource (`isOpen`, `openVisState`/`closedVisState` → animation `CLAMP` du `DeviceVisScripts`),
  ou dans celui que le tutoriel lui a laissé (`"doors"` du manifeste, justifié), puis suit les
  `DoorSwitch` du déroulé ; chaque état est une variante du gabarit (`IH1_Door_01@special01`) tenue sur
  sa dernière image. Sans cela, le modèle jouait en boucle son premier état (l’ouverture).
- **Ciel du pont** (`"sky"` du manifeste) : dans le 7.0, le pont (région 0_5, zone `FinalZone`) a
  l’éclairage `AstralShip_Tubes` et son ciel astral `Astral_Sky` ; le 17.0 ne relie plus le pont à
  aucun éclairage, et le premier de la carte (`AstralShip`) n’a que le dôme de nuit gris et les
  étoiles. Le `SkyMesh` 103155 du 17.0 a les trois mêmes calques qu’`Astral_Sky`. Non repris : ses
  animations, le plancton (`AreaEffect` `Plankton_Tubes`) et l’ombrage astral (`AstralShadingParams`).
- **Lacet des `ServerObjects`** : c’est un cap (direction de l’axe X tourné, comme le lacet d’une
  téléportation) ; un modèle, dont l’avant est −Y, tourne de ce cap + π/2 (`model_yaw`). Prouvé sur le
  navire kanien : stèle `League_Ship_Final` à 3,26141, sa collision posée dans la région au même point
  à 4,82951. Appliqué aux PNJ posés, aux stèles et au donneur de quête ; pas aux invocations
  (`ImpactSummon`), non vérifiées. Avant, le navire kanien était tourné d’un quart de tour (ses voiles
  barraient le pont impérial) et le second tournait le dos au joueur.
- **Orientations** : un PNJ que le manifeste replace (`start_at`, `"yaw": "walk"`) garde le cap de
  la marche qui l’y a mené ; un donneur de quête (`"interlocutor"`, `"face": "player"`) se tourne
  vers le joueur qui lui parle (comportement du client, non tiré des fichiers), à la place que donne
  `"player"` (centre de la zone `Lazor`, où le joueur rend la quête).
- **Composants d’état du décor** : un objet posé ne montre que ceux de son état par défaut (animation
  de son premier état, `FxBuild.default_state`) ; un objet fait seulement de composants d’état n’est
  plus invisible (lacune relevée côté Ligue).
- **Découpe par l’alpha** (`cutout`) désactivée pour `Inst_EmpireStart` (`"decor_cutout": false`) :
  le 17.0 ne marque pas les matériaux découpés, et l’alpha des textures opaques du navire y est un
  masque (`Hadagan_Inst_Board`, les planches du pont : alpha sous 0,5 sur 80 % ; `Heraldic_Base` :
  nul partout) ; la découpe creusait le pont.

**Tutoriel de l’Empire, scènes doublées** (étape 2) : comme pour la Ligue, les enchaînements doublés des
zones de script et des quêtes d’`Inst_EmpireStart` qui mettent en scène plusieurs répliques sont montés,
dans l’ordre des quêtes : zone `ComanadPost` (le second et le capitaine au poste de commandement,
dialogue `IE1/08-10`, bulles, bombardement), récompense de « Сердце корабля » (`Quest4_1.rewardImpacts` :
le capitaine et le second montent au réacteur, techniciens aux machines, ordres doublés, annonce du
navigateur), début de « Схватка с витязем » (`Quest4_4.startImpacts` : l’ordre d’abordage, capitaine
changé en donneur de quête par `ImpactMobMorph`, second laissé là par la scène précédente :
`"start_at"`, que le déroulé ne nomme pas), zone `TeleportPaladin` (Градимир Белов, le « прибор » en main,
sur le pont, 9 s avant `Jump`). Voix d’après les `.bev` (`IE1/13_Master_07` →
`13_Master_07_Captain_StartTheReactor_patch403` ; `IE1/22_Gradimir_Paluba` →
`02-Gradimir_No_04-Gradimir_StopThem03`) ; bulles et messages RU/EN du 17.0, FR du 16.0 par deux blocs
alignés (écart −6149, relus réplique par réplique). Musique `IE1_main` (buff `MusicBuff` de la zone
`EnemyAtack`), ambiance `4Layer_3Tier` seulement après `LastEventStart`. **Caméra** : aucune dans les
données ; point de vue fixe du manifeste, justifié : centre de la zone de script atteinte, à 2 m
(`ComanadPost`, `TeleportPaladin` : 2 m au-dessus du centre de la zone, en bas de la rampe du pont),
salle du réacteur (centre de la zone `Lazor`) pour les deux scènes de quête ; regard vers le locuteur
ou la place d’où il part. Points de vue retouchés (choix, non tirés des données) : au poste de
commandement, avancé de 2,5 m (au centre de la zone, la caméra est dans l’encadrement de la porte
`ES_Door7_2`, que la zone ouvre) ; « L’artefact perdu », depuis la salle du réacteur vers son entrée
(savant, capitaine, second et techniciens dans le champ ; au centre de `Lazor`, le savant était à
1,5 m et les techniciens derrière la caméra) ; « L’ordre d’abordage », derrière le joueur, reculé à
4,5 m, les deux officiers tournés vers lui. **Non repris** : l’annonce du navigateur n’a ni bulle ni sous-titre (voix seule) ; les
lampes d’alerte (`IE1_Lamp*`, stèles absentes du 17.0) ; les répliques isolées (sergent `EnemyAtack`,
canonnier `Fire`, savant `Lazor`, annonces `StartBuff`, `Quest1_2`, `LastEventStart`, ordre `Quest3_2`) :
une voix sur un PNJ immobile, sans enchaînement. **Zones suivantes** (`Hadagan`, `Hadagan_AE1…3`,
`Inst_Empire1End`, `AstralHangarHadagan`) : l’arbre 7.0 n’y a ni `CameraTrackAction`, ni `ShowSceneAction`,
ni buff de cinématique, ni banque de voix ; le 17.0 n’y pose aucune `GameViewScene`, et ses 48 trajets de
caméra « 17.0 seul » dont les points tombent dans leurs régions tombent aussi dans celles de 8 à 75
autres cartes (`Ferris4`, `ZC12`, `Eden`…), leurs voisins de ressource désignant d’autres zones (Ferris,
Isa, Eden) : aucune scène attribuable, rien n’est monté. `AstralHangarHadagan` et `Inst_Empire1End`
n’ont que des `Tour` (trajet du navire à la sortie du hangar, avec son son) : du transport, pas une scène.

**Zone de départ de la Ligue** (arc `league-start`, en tête du film de la Ligue ; le prologue de la Ligue vient juste après sa fin) : Kanians,
elfes et gibberlings commencent au même tutoriel, `Inst_LeagueStart` (la tour du Grand Mage Klement
attaquée par les démons ; `CharacterType` de la Ligue du 7.0 : `LeagueStartOrdinary`, voix
enregistrées au 4.0.3, `patch403`), qui sort vers Novograd (quête « Дорога в Новоград »). Le client
17.0 n'y garde **aucune caméra** (ni `CameraTrackAction` ni `CameraMovesAction` dans ses régions) :
ses scènes moteur sont les `GameViewScene` jouées par des stèles pendant le jeu, et les
enchaînements doublés des zones de script et des quêtes qui les posent. Deux sont montées :
la zone `PaladinQuest` (discours du Grand Mage, l'Ombre qui le tue, mort des apprentis de l'étage 6,
effondrement) et le début de la quête « Эвакуация » (`startImpacts` : `"trigger_tag"`), trois
`GameViewScene` de l'étage 1 (combat, fuite des civils par le portail, démons). Ajouts au déroulé :
impacts d'une quête, `DeviceImpactsDeferred`, `ImpactsToInterlocutor` (le donneur de la quête,
placé par le manifeste : `"interlocutor"`), `ImpactKill` (mort tenue), `ImpactMobChat` (message de
PNJ), marche en courant (`runningMode`, à 6,5 m/s, vitesse de course des foules des scripts de
l'instance : le `MobWorld` ne donne que `walkSpeed`), PNJ déjà déplacés par une zone précédente
(`"start_at"`) ; fin de scène (`"until_last"`) : la fin de ce qu'elle montre (voix, marches, scripts
des scènes du client), pas les remises à zéro des stèles des minutes suivantes. Dans les
`GameViewScript` : marche le long d'un chemin de la scène (`GameViewActionMoveCreature` : `+0xC0`
PNJ, `+0xD8` chemin, `+0xF0` vitesse ; chemins de la scène en `+0xC0`, 72 o : points en `+0x08`,
`scriptID` en `+0x28`), `ClientData` (échelle ou transparence 0 : le PNJ disparaît ; effet posé :
téléportation des civils) ; état `NoScene` d'une stèle : ses PNJ ne sont plus montrés ; stèle
absente du 17.0 à sa place (`Device_Floor6_GameScene`, posée par une table d'apparition) : états
relus dans l'arbre 7.0, `GameViewScene` retrouvée par sa place et ses PNJ. **Bulles** : le texte
d'une réplique d'instance est une bulle (`InterfaceAction` `ENUM_SHOW_BUBBLE`, indice du texte en
`+0x78` ; message `TextMessage` en `+0x40`), sous-titre de la voix posée au même instant ; RU/EN
du 17.0, FR du client 16.0 par blocs d'indices alignés relus réplique par réplique
(`"fr_blocks"`) ; une bulle sans voix reste 5 s. Voix en variantes (`15_amanda_04_v1…v3`) : la
première. Éclairage : la base de carte n'a pas de `ZoneLights` ; celle de `pack.bin` aux couleurs
de `AstralCoast_Tubes` (7.0) est désignée par `"zone_lights"`. **Caméra** : aucune dans les données
(scènes vues par le joueur) ; point de vue fixe du manifeste, justifié : centre de la zone
`PaladinQuest` vers le Grand Mage ; centre de la zone `FinalGibberlingMorph` (où le joueur retrouve
le gibberling qui lui donne la quête) vers la place du combat. À 25,5 s, `PlayerFall_GM` téléporte le
joueur sur l'étage effondré (`impactsOnAttach` → `ImpactTeleport` vers `Floor6_PlayerPos`, carte
même : pas une sortie) : la vue le suit, à 2 m, tournée selon le lacet donné (2,86 rad, lu comme un
cap : c'est au centième la direction du Grand Mage vue de ce point). **Musique** : `Siege_warfare` (buff `Music_Buff`, sans durée,
posé par `PaladinQuest` à 25,5 s, retiré par la récompense de « Эвакуация ») : onde
`Siege_warfare_adaptive` d'après `Music.bev` ; ses enveloppes adaptatives ne sont pas reproduites.

*Étape 2* (ajouts au déroulé, `extended`) : `VisActionList` lue dans l'ordre (`VisActionDelay`,
`VisActionStopAction` par `visActionID`), `postAction` et `Switch.impactsOff` au retrait d'un buff à
durée, `impactsOnAttach`, `Sound3DAction` du joueur (entendu en 2D ; projet `Music` → musique), PNJ
posés visés par un buff visible (en scène). **Stèles du décor** (`serverStatic` `StaticDevice` des
`MapRegion`, relues avec leur `StaticObjectTemplate`) : un état `DeviceVisActionChangeModel` retire
l'objet posé et pose, à sa place, le gabarit du 17.0 du même nom (`Floor_6` : `InstLeague1_Floor6_Intact`
→ `InstLeague1_Floor6_Destroyed` et ses débris, `Corridor_Floor6` → `InstLeague1_Corridor1_Destroyed`,
à 25,5 s ; hors `lightvrt`, ambiante seule) ; un état `DeviceAnimationAction` joue ses animations en
acteur (portail kanien `KaniaPortal` : `special` en boucle dès 5 s) ; une stèle qui lit un drapeau
visuel (`DeviceIfFlagVisAction`) posé sur le joueur (`CreatureSetFlagVisAction`) s'anime tant qu'il
l'est. **Poussière** : le gabarit 7.0 `Descending_Dust_enlarge` n'a pas de nom propre dans le 17.0
(nommé par son binaire, `Descending_Dust`) ; il est celui du 17.0 aux mêmes binaire, fondus (0/0 ms)
et échelle, tiré par une action du même projectile (id 334034, un seul) ; une seule ligne de tir
(`endPointIndex` 1) : deux nuages, `F6_DustMassiveFall_02` (31 s) et `_07` (32 s), les autres repères
ne sont pas visés. **Secousse** (`MinorShake`, 28,5 s, source le joueur) : `ShakeAction` →
`CameraShakeParameters` (`amplitudeScale` 4, `timeScale` 2, rayons 30/60 m) et courbe
`cameraTranslate` (61 images à 30 i/s) de `cam.(AnimatedParameters)` ; appliquée dans le repère de la
caméra, temps multiplié par `timeScale` (lecture choisie, le moteur n'en dit pas plus). Les secousses
de `PremanentShake` (tirage à 80 % toutes les 10 s, `ProbabilisticImpact`) ne sont pas jouées.
**Paladins** `Paladin_live1…4` (`MobWorld` sans nom) : `VisualMob` du 17.0 retrouvée par son contenu —
mêmes couleurs de peau et de cheveux, et textures de tenue (`armorShapes.replacement`) toutes
communes, seule en tête (druide kanienne, elfe, soldat kanien, gibberling) ; ils tombent (`sleep` en
boucle), se relèvent (`sleepUp`, `postAction`), puis marchent vers le mage (`PlayerFall*b` →
`ImpactGoTo`). **Champ protecteur** (évacuation) : mur magique de la table `Floor_Firewall`
(`SpawnTableObjects` : stèle `Magic_Wall`, échelle 0,35, à 20 s) et rayon d'Amanda
(`CreatureChannelDirectAction` : gabarit `MagePrismaticRayAbility_RayBlue`, longueur modelée de
l'action du 17.0, de sa main droite au repère `Firewall`, 1,5 s jusqu'à `InterruptChannel2`).
**Non repris** : les vagues de démons de combat (tables d'apparition de PNJ du jeu : `DemonScout1_1`…) et les cris aléatoires des
réfugiés (`NPC_Ask` : `RandomImpact`), la chute du joueur lui-même (`KnockDown`, vue à la première
personne). Non montées : la foule immobile de l'étage 5 (`Floor5_People`, script vide, déclenchée à la
sortie d'une zone de 30 m sans point de vue), les corps et la poussière de l'étage 1 (`Floor1_Dead`,
`Dust1/2`, décor), le discours d'ambiance répété du Grand Mage (`StartSpeech`, toutes les 60 s).

**Zone de départ des Pridiens** (arc `pride-start`) : les Pridiens sont une faction à part à la
création (`chargen.json`) ; leur départ (`PridensStart`) se clôt sur « Присяга Лиге » (`Pride_7_8_L` :
aller à Novograd voir Aidenus), au même point que la zone de départ de la Ligue, qui sort aussi vers
Novograd : l'arc suit donc celle-ci dans le film de la Ligue (choix documenté, `faction` `league` ; la
branche impériale, `Pride_7_8_E`, rejoindrait de même le film de l'Empire). Deux débuts de quête,
seules scènes de la zone qui ont une caméra (inventaire : `Pride_1_9`, `Pride_1_11`), relus comme
l'instance de la Ligue (`startImpacts`, `until_last`). « Ах, синема, синема! » : voile noir (3 s),
travelling vers l'écran du cinéma hadagan et musique `Music/Ingame/Cinema` (onde du `.bev` :
`YaskerBirthdayPatefon1_lp`) ; le drapeau visuel `Pride_Cinema_state2` posé à 1,5 s met la stèle du
décor (`StaticDevice` sans `scriptID`, retrouvée par le drapeau que lit son script) dans son état
`special` : son gabarit (`Hadagan_Cinema_PridenAll`, géométrie de base invisible) montre alors le
modèle accroché par son `StateComponent` d'état (`+0x68` animations, `+0x88` composant
`AttachedVisObjectComponent`, gabarit en `+0x88` : le film projeté, `Hadagan_Cinema_PridenReview` du
7.0), posé à sa place et à son échelle. « Спектакль » : voile noir, travelling vers la scène,
Эстель ди Грандер (5 s) puis Ромулус ди Ардер (9 s) jouent (bulles `CustomClientDataList`, RU/EN du
17.0, FR du 16.0 par bloc aligné : écart 12 303), les spectateurs de la table `Pride_1_11_Spectators`
applaudissent ; la scène s'arrête quand le joueur reçoit ses émotes (13 s). Son : la base de carte
porte les six musiques de la carte ; on garde celles des cases de son de la région de la scène
(`Muz_OlmEast` → `Music/RacesMusic/Priden`, `Amb_OlmEast`). Hors du film : `Inst_PS_critters`
(serpents de décor, `GameViewScene` sans caméra). Les feuillages du décor sont découpés par l'alpha
de leur texture (`Exporter.cutout`, comme la création de personnage).

**Kvatoh** (`Kvator`, contenu d'après 7.0 sur la carte `Kania`) : aucun déroulé serveur. Relevé du
17.0 : 295 ondes russes (`Voice_Kvator_*`, dont `Witches` 66, `Stump` 34, `Catorga` 22, `Fortress` 19,
`Castle` 16, `Village` 13, `Wedding` 12, `Start` 11 — le vol d'arrivée, `Kvator_Start_Fly_Cut_Muzhik` —,
`LeagueStart` 7) ; quatre buffs de caméra (`CameraTrackAction`) voisins de répliques de Kvatoh :
542594 (vol de Зайкина et du Мужик, 23 s, 3 points), 542607 (même vol, sans point), 544917 (mariage,
240 s, 7 trajets) et 545522 (discours de Светлана, 4 trajets sans durée) ; aucun `ShowSceneAction`
ni `GameViewScene` sur la carte. Le client ne relie aucune réplique à ces buffs et ne pose pas les
PNJ : une reconstruction demanderait un placement justifié par le manifeste (pilote), non tentée.

**Fins de chapitre** (`Inst_Liga1End`, `Inst_Liga3End`) : aucune scène moteur. Les quêtes qui y
mènent (`ZoneLeague1/Quest_13_01…05`, `Quest_14_01Heroic`) n'ont ni caméra, ni réplique doublée, ni
`ClientData` de dialogue (escorte `Quest_13_05` : un PNJ invoqué qui suit un chemin) ; leurs zones de
script ne portent que des téléportations, des invocations de boss et un anti-invisibilité ; aucune
onde `Voice_*` ne les nomme.

**Isa (14.0)** (arc `isa`, commun aux deux factions) : **aucune vidéo**. Le `Video.pak` du dernier client (mis à
jour le 23/09/2026), ceux des clients RU 17 du 13/09, FR 15.0 (fin de patch) et FR 16.0 n'ont pour la 14.0 que
`14_0Events/MainMenu/{Intro,MainMenu}.ogv` (logo et fond du menu, exclus) ; aucun autre pak du dernier client
ne contient de vidéo (`.ogv`, `.bik`, `.webm`, `.mp4`…). Les cinématiques d'Isa sont jouées par le moteur,
et l'arbre serveur 7.0 ne les connaît pas : tout vient du 17.0. Relevé : 204 voix `Cutscenes/Isa/*`
(19,2 min, toutes dans des `ClientData`, 16 seulement avec un sous-titre) ; presque toutes ont leur **texte
officiel** ailleurs, dans une bulle ou un message (appariement par reconnaissance vocale : 160 voix sur 204 à plus
de 0,8 de ressemblance, les autres sont surtout des cris courts) ; 15 buffs de caméra dans le bloc d'Isa, dont un seul script complet (la légende des pêcheurs) et
neuf caméras sans point (scènes vues par le joueur, avec voile noir). Six chapitres :

| Chapitre | Source | Carte | Durée |
|---|---|---|---|
| « La transe d’Unn » (`isa-unn-trance`, Olm) | voix + textes officiels ; vue du joueur (choix) | `Isa_Prologue` | 91 s |
| « L’arrivée sur Isa » (`isa-arrival`) | vue du joueur puis buff de caméra res:740170126 | `Isa` | 33 s |
| « La fosse aux combats » (`isa-fighting-pit`, Skalgard) | vue du joueur puis buff de caméra res:740170162 | `Isa` | 21 s |
| « La légende de Lyngbakr » (`isa-fishers-legend`, pilote) | script complet du buff res:740170090 | `Isa` | 44 s |
| « La Freya » (`isa-freya`) | voile du buff res:740171413 ; vue du joueur (choix) | `Isa` | 21 s |
| « Le journal du capitaine » (`isa-captain-journal`) | voix + textes officiels ; vue du joueur (choix) | `Isa` | 64 s |

- **Script d'un buff du 17.0** (`tools/cutscene_client.py`, `"buff_script": true` ou un moment de `"cameras"`) :
  l'arbre de `VisAction` du `BuffVisScripts` est rejoué avec les règles des fatalités — `VisActionList` en
  séquence (`play` 0) ou simultanée (1), bornée par son `playWhile` (`+0x70`, un `VisActionDelay`) ; un
  `CameraTrackAction` est un plan jusqu'à la borne de sa liste (durées des points en poids, règle 7.0) ;
  `Sound2DAction` (événement en `+0xA0`) d'un projet `Cutscenes/…` → voix off ; `PostEffectVisAction` →
  `UserPostEffect` (fondus `+0x28`/`+0x2C` en ms, carré noir en `+0x60`) → voile. La légende de Lyngbakr : voile
  2,5 s, six plans (la mer, la statue, puis sous l'eau, les épaves et les côtes du poisson-île au fond), voix du
  conteur à 3 s, six sous-titres rangés avec le buff (resourceId 740170091 à 096) dans l'ordre de la voix ; seul
  leur instant est mesuré sur la voix (horodatage mot à mot de faster-whisper, `timing.starts`).
- **Places des PNJ** : les `MobWorld` du 17.0 portent une `SpawnLocation` (`+0x70`, comme les stèles ; 7 911 PNJ),
  avec leur zone (`+0x40` → `ZoneResource`, que la base de carte cite) et la **case z** (`+0x38`, i32, 32 m) :
  un PNJ d'Isa en case z 2 à 40,57 m locaux est à 104,57 m, la hauteur du terrain sous lui (104,3 à 104,6). Pas
  de lacet : les caps sont un choix (vers l'interlocuteur ou ce que la scène montre), documenté. `stele_position`
  compte désormais la case z (nulle sur `Inst_EmpireStart` : rien n'y change).
- **Textes officiels hors sous-titre** : les répliques d'Isa ont leur texte dans une **bulle** du `ClientData`
  (`InterfaceAction` `ENUM_SHOW_BUBBLE`, indice du texte en `+0x78`), que `read_client_line` lit désormais, avec les
  voix rangées dans une `VisActionList` (`+0x48`) et le nom d'un `Sound2DAction` en `+0xA0` (`+0x78` pour un
  `Sound3DAction`) : avant, 39 voix d'Isa seulement sur 204 étaient lues. Une réplique du manifeste peut être
  `{ref, ru}` : le `ClientData` et le début de son texte russe, qui vérifie la bulle (et désigne la suite d'une
  réplique en plusieurs bulles). RU/EN du 17.0 à l'indice de la bulle ; FR du 16.0 par l'écart d'une paire de textes
  connus (`fr_pair`, désignée par son début russe et français : 7 285 au 24/09/2026, vérifié réplique par réplique sur
  tout le bloc d'Isa), qui sert aussi aux sous-titres que la voix ne relie pas au client FR. Plus robuste que
  `fr_blocks`, qui retient des indices du 17.0 (ils bougent d'une mise à jour à l'autre : +27 textes au 24/09).
- **Moments** (`"cameras"`) : une scène peut enchaîner plans de buffs de caméra du client (`buff`, à l'instant `t`)
  et points de vue fixes du manifeste (`p`, `look`) ; groupes de répliques à un instant (`timing.groups[].t`) ;
  animation du locuteur prise dans son `ClientData` (`line_animations`, `emoteTalkExcited`, `emoteFacepalm`…) ;
  stèle posée par le client comme effet (`spawns[].stele`, gabarit et place de la stèle).
- **La Freya** : l'épave du navire astral de Колль Фитилёк est dans le **décor** d'Isa
  (`AstralShipKaniaGroupBroken`, région 050_050/3_2, seul navire astral de la carte), entourée des pages de son
  journal (stèles `Offhand_Book_D_03`) et des places de Хаук et Герда. L'ancienne scène en attente suivait le buff de
  caméra res:740171462 (19 s), qui regarde le ciel au-dessus du plateau de Skalgard, à 1 km de l'épave : son
  rattachement à la Freya n'était pas établi, elle est remplacée.
- **Non repris** : le voile sous-marin (brouillard et teinte sous la surface de l'eau : aucune donnée décodée) ;
  Lyngbakr lui-même (absent du script) ; les animations de combat de la fosse ; l'apparition de Ratatosk (instant
  choisi). **Reste d'Isa** (voir `tools/film_plan.json`) : la saga récitée aux Держащие Нить (7 vers, 117 s), le défi
  de Харысхан (61 s, Харысхан n'est pas posé dans le client), le départ par la montagne (buff res:740171271, 17 s),
  la prophétie des os, la chasse à Lyngbakr, le cimetière (les ancêtres de Gerda, 64 s), la dimension du Destin
  (`Isa_Destiny` : la Toute-Mère et Unn, 29 s ; ses décors sont des stèles posées par le serveur), l'adieu de Gerda.

En attente, hors du film : `ferris-sarcophagus` (`Ferris_4_start`, carte `Ferris_indoor`) — la salle,
éclairée par le seul éclairage de zone du 17.0 (violet sombre, sans lumière ponctuelle), est presque
noire, et l'ouverture de la sphère (drapeau visuel) n'est pas reproduite. (`isa-freya`, qui y était, est
désormais dans le film : voir Isa ci-dessus.)

**Troisième source : les scènes du client** (`"source": "gameview"`) : une `GameViewScene` (place et
placement de caméra en doubles x, y, f32 lacet, double z ; PNJ par `VisualMob`) jouée par le
`GameViewScript` d'un `ShowSceneAction` : chaque créature joue l'animation que le script lui donne,
son animation de cinématique portant son déplacement ; caméra au placement du spectateur, à 2 m
au-dessus (vue de joueur, choix documenté). Caméra animée `CameraMovesAction` lue : groupes de 48 o
(`+0x04` délai, `+0x08` mouvements), mouvements de 120 o (pose en doubles x, y, z, f32 lacet, tangage,
roulis ; `+0x6C` durée) — recoupés au millième sur le `.xdb` 7.0 ; un groupe coupe le précédent. Le
sens du lacet n'est pas établi : la seule scène du 17.0 qui l'emploie (l'explosion du navire, déjà
dans le film en vidéo) montre un navire posé par une stèle (`DeviceVisActionChangeModel`) que le
client ne place pas, sans lequel les plans ne se vérifient pas (option `yaw_offset` du manifeste).

**Scènes d'après 7.0, constat** : le client 17.0 ne relie aucune réplique à son buff de caméra (aucune
ressource ne cite ces `ClientData` ; c'est le script serveur) et ne pose ni les PNJ ni les objets de
quête. Kanaan/Nayan et le sanatorium « Снежинка » sont des présentations de zone (survols de 16 à
32 s, une narration par lieu ; au sanatorium, la voix est un paramètre fictif, `CS_FR_PortalArch03`) ;
le mariage de Quator (ch. 5) est une caméra d'ambiance de 240 s sur un événement serveur (huit
répliques, dont l'attaque de Svetlana, sans ordre établi) ; Eden2 ne porte qu'une réplique.

**Dossiers** : chaque carte a son dossier commun `engine/maps/<carte>/` — décor (`decor.glb`, les
objets des zones de toutes ses scènes), sol (`terrain.glb`), textures, particules et leur atlas ;
chaque scène garde les siens : éclairage de sommets (`decor-light.bin`, qui dépend du temps de la
scène), ciel (`sky.glb`), effets, voix, sons, sous-titres. Les acteurs sont communs à tout le film :
un modèle par `MobWorld` (ou `VisualMob`) dans `engine/shared/actors/`, avec toutes les animations que
les scènes lui demandent (110 Mo pour les treize scènes). Si `data/Packs` du client est un
lien illisible depuis WSL, les outils lisent `data/Packs.adc-real`.

**Références robustes aux mises à jour du client.** L'identifiant de la table de hachage de `pack.bin`
(`PackDB.ids`) est un rang **volatil** : la mise à jour du client RU des 23 et 24/09/2026 l'a renuméroté (le buff
de caméra d'`isa-freya`, 521226, est devenu 521264, et 521226 un `ClientData` ; `ao12-prologue04` ne trouvait plus
son trajet). Le manifeste désigne donc chaque ressource par son **`resourceId` persistant** (tables de l'entête en
0x30/0x38, `PackDB.resource_ids`/`resource_id` ; ressources de mécanique : buffs, PNJ, `ClientData`, quêtes…),
écrit `"res:<resourceId>"`, ou, pour une scène du client (ressource visuelle, sans `resourceId`),
`"stele:res:<resourceId>"` : la `GameViewScene` que joue la stèle. Un entier nu est refusé
(`resolve_refs`, `resource_ref`). Les 18 références d'`ao12-prologue04`, `isa-freya` et `invasion-engineer-kania`
ont été converties par l'ancien et le nouveau `pack.bin` (types identiques des deux côtés). **Langue des
textes** : `load_textset` vérifie chaque `.loc` (le russe en cyrillique à plus de 50 %, les autres non) ; un
`pack.rus.loc` qui ne serait pas du russe est remplacé par un autre `.loc` russe du même pak, sinon par celui du
client RU antérieur (`sources.main.ru_fallback`), apparié texte à texte par l'anglais. Au 24/09 (paks de 16 h 13),
le `pack.rus.loc` est bien du russe (95 % de cyrillique).

    python3 tools/extract_engine_cutscene.py                      # toutes les scènes
    python3 tools/extract_engine_cutscene.py --only ferris-locus  # une scène
    python3 tools/extract_engine_cutscene.py --no-voices          # garde voix et sons extraits
    python3 tools/extract_engine_cutscene.py --tracks-only --only isa-arrival   # pistes et index seuls
    python3 tools/inventory_engine_cutscenes.py --client-only     # relevé du 17.0 (4 s)

**Répliques sans durée** (`fill_line_durations`) : une réplique dont le texte vient d'une bulle ou d'un
`ClientData` sans sous-titre (`delay_ms` nul : presque toutes celles d'Isa) n'avait ni repère VTT, ni piste
dans l'index, ni sous-titre dans le lecteur. Elle s'affiche désormais le temps de sa voix, sinon le temps de
lecture de son texte (15 caractères par seconde, au moins 1,5 s : choix, le client ne donne rien), bornée
par la réplique suivante et la fin de la scène. `--tracks-only` refait pistes et index depuis le
`scene.json` extrait, sans réextraire (utilisé pour les six scènes d'Isa le 24/09/2026).

**Réextraction du 24/09/2026** (les douze scènes moteur du film hors Isa, avec le pipeline commun à
jour ; relevé avant/après : caméra, répliques, voix inchangées) : lacets serveur tournés de +π/2 sur
`ferris-retrospective` (les trois PNJ se font désormais face, vers Негус Джиг, comme le veulent leurs
caps) et `ferris-awakening` ; textes officiels EN/FR manquants ajoutés (`ferris-order`, `ferris-locus`,
`ferris-locus-fall`) ; ambiance et musique de zone de la carte résolues par les `.bev` (`Ferris4` :
`Siege_warfare`, seule musique de zone de la carte, et `Ferris4_Outdoor` ; `FerrisRaid` : `Ferris_Winter1`,
dont le premier calque, `IceCrack_01`, est un craquement de 3 s qui crépitait en boucle : le manifeste garde
`FerrisWinter_drone`, `audio_layers`, choix documenté). Deux correctifs communs en sont sortis :

- **Invocations sans nom** (`find_creature_visual`) : les drones de Genera (`ferris-order`) et l'essaim
  (`ferris-swarm`, `ferris-power-of-order`) n'ont pas de nom ; depuis que `find_mob_by_name` refuse les
  noms vides, ils disparaissaient (avant, ils prenaient le premier PNJ sans nom : un golem de jade). Leur
  `VisualMob` 17.0 est retrouvée par la géométrie du gabarit de la `VisualMob` 7.0 et son échelle, sans
  tenue (une seule candidate chacune : `ArchitectBot` et `Colossus`, à 1,5).
- **Homonymes départagés par l'échelle** : entre plusieurs `MobWorld` au même nom, `find_mob_by_name`
  préfère celui dont la `VisualMob` a l'échelle de celle du 7.0 (même dossier et même échelle, puis même
  dossier, puis même échelle, puis le premier). « Негус Джиг » (cinq `MobWorld` au 17.0) prenait celui du
  boss du raid, à l'échelle 2, et sortait géant ; le boss du Locus prenait une copie à 1,5 (1 au 7.0) ;
  les Колосс de `ferris-portal`, `ferris-locus`, `ferris-locus-fall` et le Ваятель de `ferris-awakening`
  sont désormais ceux à 0,9 (`ColossusScout_CutScene_0.7`, 0,9 au 7.0). Toutes les échelles des acteurs
  Ferris concordent maintenant avec leur `VisualMob` 7.0 (avant la réextraction, aucune n'était appliquée).

Non repris : la dernière réplique de `ferris-locus-fall` (« Уходите. Возвращайтесь… ») nomme la voix
`Cutscenes/Ferris4/CS_FR_CarrierVayate13`, sans le « l » des autres (`CS_FR_CarrierVayatel13` est dans la
banque) ; le projet `Cutscenes` n'a pas de `.bev`, rien ne relie les deux noms, elle reste muette.

**Inventaire** (`engine_cutscenes` du manifeste) : arbre serveur 7.0 croisé avec le 17.0
(141 scènes) et 17.0 seul : 555 trajets de caméra (`CameraTrackAction`), dont 375 dans des
scripts de buff de cinématique ; 73 buffs ont, rangées à côté d'eux, des répliques
sous-titrées et doublées ; 36 `GameViewScene`, 37 `GameViewScript`, 60 `ShowSceneAction` ;
662 ressources de sous-titres.

**Deux sources de déroulé.** Le client ne sait ni quand ni par qui une réplique est dite :
c'est le serveur qui enchaîne les buffs.

- *Scènes de 7.0 et d'avant* (`"source": "xdb70"`, `tools/cutscene_xdb70.py`) : la chaîne de
  buffs est **rejouée depuis l'arbre serveur 7.0** — durée des buffs, `EffectOnBuffTimeout`,
  `EffectsDeferred`/`ImpactsDeferred`, `Switch`, `BuffAttacher`/`BuffDetacher` (un buff racine à
  durée dont le `Switch` retire la chaîne borne la scène) ; plans de caméra, fondus
  (`PostEffectVisAction`), temps (`WeatherCreatureVisAction` : ciel, lumière, brouillard,
  désaturation), musique et ambiance (`Sound2DAction`) ; répliques (`ImpactClientData[Params]`)
  avec leur locuteur ; PNJ placés (`ServerObjects` : `scriptID`, `center`, `yaw`) ou **invoqués**
  (`ImpactSummon` sur un repère `gameMechanics.map.Locator`, `ImpactGoTo` à la `walkSpeed` du
  `MobWorld`, `Disintegrate`) ; animations posées par buff (`CreatureAnimationAction`, `LOOP`
  ou une fois). Le résultat est rapporté au 17.0 : texte par la voix, PNJ par leur nom russe
  (départagé par le dossier de la `VisualMob` 7.0), voix par le nom d'événement. Aussi : PNJ des
  tables d'apparition posées sur la carte (`ImpactFindSpawnTable` → `SpawnLocus` des `ServerObjects`,
  couches `inst*` comprises) et leurs chemins (`GoThroughPath`).
- *Scènes d'après 7.0* (`"source"` absent : le pilote) : caméra et répliques du 17.0, place
  des acteurs et instant des répliques donnés par le manifeste, justifiés.

**Règles établies sur les données** (tests dans `tools/tests/test_engine_cutscene.py`) :

- durées des points de caméra : des **poids** étalés sur la durée du buff (la dernière ne
  compte pas) — seule lecture où `Cutscene_01` (12, 10 dans 12 s) et `Cutscene_03` (95, 10
  dans 10,5 s) couvrent leur buff ; sans durée de buff (pilote), des secondes. Un plan aux
  points nuls rend la vue au jeu : ignoré, le plan précédent tient ;
- `vertexBufferOffset` (élément de géométrie, `+0xAC`) : sommet de base des indices 16 bits.
  L'ignorer déchirait `FerrisRaid_Core` (87 009 sommets) en un rocher de 350 m qui cachait le
  laboratoire ; la valeur exacte remplace l'heuristique de pages de la création de personnage
  (même résultat sur 24 grandes géométries sur 27, corrige les 3 autres, dont `MountChopper`) ;
- rotation des objets posés `(0, tangage Y, roulis X, lacet Z)`, composée
  `Rz·Ry·Rx` : corrélation 1,000 avec l'éclairage précalculé des rochers inclinés de
  `Ferris4` (0,5 au mieux en lacet seul) ;
- octet 2 du `lightvrt` = `255 · Σ intensité · (1 − d/rayon)^atténuation · max(0, N·L)`, avec
  pivot et **rayon multipliés par l'échelle de l'objet** et des intensités négatives
  (lumières « d'ombre » à −100) : corrélation 1,000 sur le pilote et sur `Ferris4` ;
- locuteur d'une réplique posée sur le joueur : le PNJ invoqué présent dont le nom de modèle
  figure dans l'événement de voix (`FR_PreRaidRysina01` → `Rysina_CutScene`), le manifeste
  nommant les autres (`speakers` : le Ваятель est un Колосс, `Arch` le Cœur du Locus) ;
- voix rangées par groupe : `FerrisRaid602/FR_PreRaidRysina01` → onde `Rysina01` de
  `Voice_FerrisRaid602Pre_rus.bsb` (groupe dans le nom de banque, reste du nom pour départager) ;
- PNJ uniques (`Creatures/Rysina`, `Creatures/Mirianna` pour Marianne di Arder) : texture de
  géosets en relocation de genre 2, non résolue dans `pack.bin` → texture du dossier nommée
  comme la géométrie (`Rysina.(Texture).bin`).

- **sol** (`tools/allods_terrain.py`) : `terrainDump.bin` = maillage adaptatif par sous-carreau de
  8 m — sommets de 4 octets (normale, indice dans la grille 9 × 9), puis une hauteur `f32` par
  sommet, triangles `u8`, jeux de trois calques ; hauteurs identiques **au centimètre** à la carte
  de hauteurs de l'arbre serveur 7.0 (`terrain.bin`, carreaux 8 × 8 sur 33 × 33). Plusieurs couches
  superposées par région (`FerrisRaid`). Calques : `TerraLayers` (texture) ; toute texture de
  calque se répète tous les **8 m** : le vertex shader du terrain du client
  (`Material/terrain-dx11.bin`) écrit `TEXCOORD0 = −position · 0,125`, sans facteur par calque ; le
  flottant `+0x10` des calques (30, 40), lu autrefois comme une répétition en mètres, est
  l'exposant spéculaire `DirectionalExponent` (recoupé champ à champ avec le `layers.xdb` 7.0) ;
  poids des calques lus dans les `SplatMap` (voir « Sol mélangé ») ;
- décor opaque rendu **d'une seule face**, comme le jeu : l'ouverture de `ferris-locus-fall`, caméra
  sous la plateforme du Locus, montre alors le Cœur au-dessus ; les cristaux du portail
  (`ferris-portal`, 20 à 37 s) restent : le même objet `FerrisRaid_CoreBottom` est à la même place en
  7.0 et en 17.0, rien n'autorise à déplacer la caméra ;
- éclairage de zone : liste de `ZoneLights` (`+0x168`), ou éclairage unique en ligne (`+0x48`, cartes
  d'intérieur comme `Ferris_indoor`) ; dans l'élément, `PointLightColor` en `+0x4C` et
  `SelfIllumColor` en `+0x50` (le champ `+0x48`, lu auparavant, vaut −1 partout : recoupé sur les 26
  éléments 7.0 de six cartes) ; nuages de ciel « alpha » dont la texture n'a pas d'alpha
  rendus additifs.

**Rendu** : décor non éclairé, couleur de sommet = ambiante + soleil (`N·S`) + octet 2 ×
`PointLightColor` ; acteurs Lambert, émission = lumière locale ; soleil `DiffuseColor` ×
π (`LIGHT_SCALE` des fatalités) ; brouillard ; ciel `SkyMesh` (tous ses calques, suit la
caméra) ; particules et effets posés (`votInstances.ts`, commun avec les fatalités) ;
musique, ambiance et sons d'objets (atténués linéairement), voix ; voile noir des fondus,
désaturation des visions. Lecteur : `src/components/scene/EngineCutscene/`.

**Une seule musique à la fois** : le jeu joue la musique de la zone du joueur, qu'une action `Music`
du déroulé (`Sound2DAction` de type `Music`) remplace jusqu'à son `postAction`. L'extraction garde
donc la musique du déroulé quand il en a une, sinon **une** musique de zone de la carte (la première,
signalée quand la carte en a plusieurs). Un événement adaptatif à plusieurs calques joue son premier
calque, ou celui que nomme `audio_layers` au manifeste (choix justifié). `ferris-locus` partait d'un
buff enfant (`LastStart_CutScene`) et perdait ainsi la musique de sa racine `LastStart_CutScene_Main`
(posée par la zone `ZoneFR16`) : il superposait les deux musiques de zone de `FerrisRaid` (`Winter`,
`AC5_main`) et durait 162 s (60 s de `Cooldown_CarrierIntro`). Depuis la racine : `TepPyramidAdaptive`,
calque `TepPyramid_high` (la scène met le paramètre `action` à 2, maximum de sa plage 0–2 dans
`Music.bev` ; enveloppes non décodées), ambiance `Last_Start`, et 106 s, borne de la racine.

**Code commun** : `allods_packdb.py` (table des paks exacte, identifiants, bases de carte
liées), `allods_visdb.py`, `allods_characters.py` (habillage, corrigé : couleur de peau
`0x1B0`, un géoset caché par un objet l'emporte sur un géoset montré), `allods_gltf.py`,
`allods_fx.py`, `allods_scenes.py`, et côté lecteur `votInstances.ts`, partagés avec les
fatalités et la création de personnage.

**Éclairage des sommets du décor** (`lightvrt`, 4 octets par sommet) : octet 0 = visibilité du soleil
(ombre portée ; corrélation 0,81 avec des tirs de rayons sur le pilote, au soleil de la cuisson),
octet 1 = visibilité du ciel (`128 + 127 · v` ; 0,81 sur le pilote, 0,73 sur `Isa`), octet 2 = lumières
ponctuelles (1,000). Lumière = `AmbientColor · (f + (1 − f) · v) + DiffuseColor · max(0, N·S) · ombre +
ponctuelles`, `f` = `AmbientFactor`. Le soleil de la cuisson est celui de la zone du lieu (`Isa` : 225°),
pas toujours celui de la première zone de la carte.

**Sol mélangé** : `SplatMap_0…2` = atlas de blocs de 8 × 8 texels, un par passe de sous-carreau
(octets `c`, `d` de la passe), remplis dans l'ordre de dessin ; le dernier octet du jeu de calques de
la passe nomme son atlas (lu toujours dans le `_0`, 63 % des passes du `_1` de `FerrisRaid` mettaient
du poids sur un calque absent) ; texel `i` à `i·8/7` m du coin, bords partagés à l'identique entre
voisins ; R, G, B = poids des trois calques de la passe (deux passes somment à 1). Calques : les 256
entrées de `TerraLayers`, indexées directement, trous et entrée 0 compris (`Inst_ZoneContested12_Start`
nomme les calques 0 et 54 à 121). Le lecteur mélange jusqu'à six calques par sommet dans un tableau
de textures (`terrainMaterial`).

**Lumière cuite du sol** (`<région>_lightmap.bin`, 512² dont deux texels de bordure recopiés de la
voisine — 508 texels pour les 256 m —, axe Y retourné ;
`_lightmapDown.bin` pour la couche du dessous) : R = visibilité du ciel, G = soleil de la cuisson
(ombres portées), B = lumières ponctuelles ; même formule que le décor. Les cartes des régions sont
rangées dans un atlas (`terrain-light.png`, 4 096 px au plus) lu par l'attribut `_LIGHTUV`.

**Formats du sol** : les patterns ImHex de **Paulus** (`tools/reverse/terrain.hexpat` pour
`terrainDump.bin`, `tools/reverse/splatmap.hexpat` pour les `SplatMap`) ; leur offset d'entête
`0x08` compte l'entête `(niveau, taille)` que `read_chunks` retire. Tous les blocs sont lus
(`parse_terrain_extras`) : tampons de sommets (taille, « complexe »), occulteurs, herbe, eau.

**Herbe** (`tools/allods_terrain_extras.py`, lecteur `src/components/scene/vot/terrainExtras.ts`) :
carreaux de 32 m, un jeu de places au mètre par (calque du sol, touffe) — l'octet « type » est
l'entrée de `TerraLayers`, le « sous-type » sa touffe `foliage0…3` (bit 7 : jeu jumeau, mêmes places,
toujours ; non doublé). Les nombres de touffes suivent la `probability` des touffes (7 : 30 : 27 : 2 →
1 631 : 7 137 : 6 190 : 457 sur `Ferris4` 4_4). Touffe (72 o depuis `+0x48` de l'entrée de calque,
recoupé sur `layers.xdb` 7.0) : `bottom`/`top` (hauteur, décalage, largeur), `min`/`maxScale`,
`numLeaves`, `probability`, élément de l'atlas `Maps/<carte>/layers.(Texture)` (`TerraLayers +0x60`,
sources de 48 o : x `+0x14`, y `+0x20`, largeur `+0x10`, hauteur `+0x04`). Le shader du client
(`Material/grass-dx11.bin`, désassemblé, noms des constantes lus dans son `RDEF`) donne le reste :
couleur = texture × lumière du sommet, test d'alpha `a × fondu < 0,02`, vent = produit complexe
d'un coefficient par sommet (nul au pied) et d'un vecteur global. Rendu instancié (une touffe par
instance, 24 o par touffe, un carreau de 32 m par objet, masqué au-delà de 70 m), éclairé comme le
sol à son pied. **Choix du lecteur**, faute de données (le moteur les calcule) : répartition des
feuilles en étoile, lacet/échelle/phase tirés au hasard, amplitude et fréquence du vent, fondu à
45-70 m.

**Eau** : carreaux de 32 m, hauteur (`Vec4`, égale aux quatre coins partout), vitesses (nulles
partout), éléments de 8 m `(x, y, i, j)` : `(i, j)` = place dans le carreau, `(x, y)` = **bloc de
8 × 8 texels du `SplatMap_N`** (N = texture de son matériau d'eau), alloué à la suite des passes du
sol. Ses texels : B = 0,5 + profondeur/8, R, G = 0,5 + normale du fond/2 (corrélations 0,997 sur
`Ferris4`). Type d'eau = entrée de `TerraLayers.waterLayers` (`+0x90`, 136 o, recoupé sur 7.0) :
textures (relief, Fresnel), alpha, reflet, spéculaire, vitesse ; couleurs du dégradé et du
spéculaire dans l'éclairage de zone (`WaterGradientStart/End`, `SpecularWaterColor`). Le lecteur
porte le shader `StaticWater` du client (`Material/StaticWater-dx11.bin`) : relief défilant,
dégradé selon la profondeur, reflet (caméra miroir, demi-résolution), réfraction (copie de l'image),
Fresnel, alpha `sat(8B − 4)/(N·V + 0,01)`. Supposés : l'unité du temps
(`s × waterSpeedMultiply / 1000`) et les textures de repli (`WaterFresnel`, `WaterNoise`) des types
sans Fresnel ou sans relief (`Kania_River`, `Ferris4`). Aucune scène actuelle ne voit d'eau (la plus
proche est à 157 m de la caméra de `ferris-retrospective`) ; le décor des fatalités en a 52 carrés, loin du centre.

**Occulteurs** : un par carreau de 32 m (56 o) : `xmin` (4 hauteurs, à 96 % égales à une hauteur de
sommet du carreau), `xmax` (`−FLT_MAX` dans 89 % des cas), boîte haute de 1 024 m ; avec
`<région>_terrainDumpOcc.bin` (`extraOcclusion` de `TerrainPackInfo`), ce sont les données
d'occlusion du sol (culling). Invisibles, non rendus ni exploités : three.js ne fait que du
culling par frustum et nos décors sont petits.

**Événements FMOD** (`tools/allods_fev.py`) : les `SFX/**/*.bev` du client sont des projets FMOD
Designer 4.44 compilés (zlib, entête de 68 octets, `RIFF` `FEV ` version `0x00450000`), dont le
bloc `LGCY` garde l'ancien format `FEV1` et `STRR` les noms. On en lit les banques, les
définitions de sons (ondes : fichier source, banque, sous-piste, durée) et, pour chaque
événement (simple : l'indice de sa définition à `+0xA8` ; complexe : ses calques, puis ses sons
de 58 octets), la définition jouée : `Music/ZonesMusic/IE1_main` → `/Music/Conquer_high` →
`adaptivemusic/Conquer_high.wav`, sous-piste 2 de `Music_StartZones.fsb`. La sous-piste n'est
retenue que si la banque FSB lui donne le nom de l'onde (onze définitions du menu pointent des
ondes retirées) ; sinon, et pour un nom d'événement ambigu dans son projet, l'appariement par le
nom reste le repli (`match` : `bev` ou `name` dans `scene.json`). Un événement à plusieurs sons
joue le premier (les autres sont signalés : `4Layer_3Tier` en a trois, pilotés par un
paramètre) ; les voix (`Voice*.bev`, entête de projet différent) restent appariées par le nom.

**Manques** : `ferris-sarcophagus` reste sombre même lu en entier (zone violette, aucune lumière
ponctuelle ; octets 0-1 pleins) ; le fichier
d'événements FMOD `.bev` n'est lu que pour ses calques et définitions de sons (voir « Événements FMOD ») :
enveloppes, paramètres et effets DSP non interprétés ; les effets de
sort, de projectile ou de stèle (`CutScene_Boom`, jets des lance-flammes) et ce que montre
« Оглянитесь ! » ; les drapeaux visuels (`CreatureSetFlagVisAction`) ; les scènes faites de
`GameViewScene` (`Swarm_CutScene`) ; le joueur, absent.

### Ce qui manque

- **Cinématiques moteur** : vingt-neuf sont recréées (voir plus haut), dont six d'Isa. Liste dans
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

### Plan du film (page de développement)

`/dev/film` (serveur de développement seulement : route chargée sous `import.meta.env.DEV`, absente du
build) organise les scènes à recréer pour un film continu. **Source de vérité unique :
`tools/film_plan.json`**, versionné, que la page et les agents éditent tous deux :

- la page lit et enregistre le fichier par le greffon Vite `tools/vite/filmPlanPlugin.ts` (`apply: 'serve'`,
  route `/__film-plan`) : chaque écriture est validée (`validatePlan`, `src/screens/FilmPlanScreen/filmPlan.ts`),
  refusée si le fichier a changé depuis sa lecture (révision SHA-1), puis faite de façon atomique (fichier
  temporaire + `rename`) ; les modifications partent 0,6 s après la dernière action ;
- un agent édite le fichier directement (JSON indenté de deux espaces, fin de ligne finale ; le test
  `tools/vite/filmPlanFile.test.ts` vérifie validité et format) ; le greffon le surveille et la page se recharge
  (événement HMR `film-plan:changed`), ou signale le conflit si des modifications locales attendent ;
- le plan **ne modifie pas le film** : passer une scène en production reste une étape séparée
  (`tools/cinematics_manifest.json`, `extract_engine_cutscene.py`).

Contenu : `chapters`, la frise de l'histoire A → Z (ordre du tableau = ordre du film ; une vue de faction garde ses
chapitres et les communs), et `entries`, les scènes dans l'ordre du film : zone, version, type (vidéo, moteur,
libre), durée (mesurée pour les chapitres du site, sinon estimée : `durationEstimated`), statut (`film`,
`pending`, `todo`, `discarded`), priorité (`priorityProposed` : proposée par l'inventaire, pas décidée), note,
lien vers le chapitre du site (`/cinematics?faction=…&chapter=<id>`, que le lecteur ouvre directement) et
`source` (ressources qui attestent la scène). Un chapitre sans scène « dans le film » est un **trou**. Page :
vues Ligue / Empire / Tout, totaux (film actuel, film visé, objectif `targetMinutes`), filtres (statut, type,
priorité, texte, trous seulement), glisser-déposer ou flèches, menus de statut et de priorité, note, entrée
libre (fenêtre du jeu).

**Inventaire du 24/09/2026** (pré-remplissage) :

- **Vidéos** : les 18 clients lisibles (1.0 → 17.0, dont 7.0 ADC, Divinity et Revelation, 8.0, 9.0, 15.0 et 16.0 FR,
  Warp 11.0) et les arbres serveur 1.0, 3.0 et 7.0 (`Packs`, `Packs_old`, client personnalisé) ont 53 vidéos
  distinctes, identiques (CRC) d'un client à l'autre : les 34 cinématiques du site (dont les 4 vidéos 10.0
  retirées, du seul client Warp), 18 vidéos de menu (Intro/MainMenu 9.0 → 17.0) et le clip de test 7.2. Aucune
  cinématique vidéo ne manque. Les clients 1.x → 6.0 et 7.0 Revelation n'ont aucune vidéo.
- **Scènes moteur** : les 25 recréées (13 dans le film, 10 des zones de départ retenues, 2 en attente), les
  8 scènes refaites en vidéo HD (écartées, doublons), et les candidates non recréées relevées dans l'arbre 7.0
  (`engine_cutscenes.scenes`), les buffs de caméra du 17.0 voisins de répliques (`client_17`) et les événements
  vocaux du projet FMOD `VoiceDialogsCutScenes` (durées lues dans les `.bev`). Les zones d'avant Ferris (Kania,
  Xadagan, terres disputées, archipel, secrets, Umoir) n'ont aucune caméra ni `ShowSceneAction` scénarisés :
  ce sont les trous de l'histoire, relevés par les intrigues (`<plotline>`) de leurs quêtes.

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
16 de la boutique — sur les seize personnages jouables, dans une clairière des Prés bénis
(composition sur un vrai lieu, voir « Décor »).

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
    python3 tools/fatality_items.py                  # objets, noms, icônes, versions (≈ 5 min, 9 clients)

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

**Objets, noms officiels et apparition** (`tools/fatality_items.py`, `tools/fatality_items.json`).
Le script fusionne ces données dans `fatalities.json` : champs `name`, `items`, `itemLink` et
`since`. Pour chaque type de fatalité, la chaîne suit des pointeurs du `pack.bin` et ne devine
aucun nom :

1. `CreatureFatalityAbilityAction` porte le type (`fatalityType`, énumération 7.0
   `client.SLON.FatalityType`) dans son seul champ propre. Ce champ est à `+0x44` en 17.0 et à
   `+0x24` en 4.0 : on le repère comme le champ dont les valeurs sont toutes distinctes d'une action
   à l'autre ;
2. le `BuffVisScripts` qui contient cette action est le script d'un ou plusieurs **buffs**. Leur
   nom (`+0x68`) est le **nom en jeu de la fatalité** : « Rituel lunaire », « Géhenne »,
   « Peine de mort »… ;
3. pour les fatalités de boutique, l'icône du buff (`UISingleTexture`) est pointée aussi par une
   `UnlockResource` (la capacité apprise, « Guerrier lunaire »). Les dix fatalités de classe et la
   11 partagent l'icône générique `Fatality` et n'ont pas de capacité propre ;
4. un **objet** (`ItemResource`, nom en `+0x228`) apprend la fatalité quand une de ses conditions
   d'emploi (`PredicateUnlock`) pointe cette capacité. Un objet peut en apprendre plusieurs : la
   Collection du Carnifex apprend 11 et 12. Une fatalité peut venir de plusieurs objets : les
   versions boutique, échange et temporaire sont regroupées quand elles ont les mêmes nom et icône
   (`resourceIds`).

Aucun sort ni effet serveur (ceux qui posent les buffs) n'est dans le client. La fatalité 11
(« Carnage », chemin `Mechanics/Fatality/ClassFatalityWarlock` en 11.0) n'a ni icône ni capacité
propres. Elle est rattachée **par le nom** (`itemLink: "name"`, établi sur le russe) : le Code du
Carnifex apprend `Умение «Расправа»` (FR « Aptitude Fatalité », EN « Fatality ability »), et le buff
de la fatalité 11 s'appelle `Расправа` (FR « Carnage »). Chaque Discours « modifie l'effet visuel
de Fatalité » (description FR) : le Carnage est donc l'effet par défaut de l'aptitude.

Noms :

- russe et anglais : textes du client 17.0 (`pack.rus.loc`, `pack.eng_eu.loc`). Un anglais resté
  en cyrillique compte comme absent ;
- français : client FR 16.0, même objet d'un client à l'autre par le `resourceId` (table `0x30`
  de l'entête v2, `resource_keys`) ;
- icônes : fichiers `UITexture` du client 17.0, recadrés sur leur zone utile
  (`public/game/fatalities/icons/`).

La **version d'apparition** est le premier client archivé qui contient le type. `previous` est le
dernier client archivé vérifié sans lui. Clients lus : 3.0, 4.0.02.42, 7.0, 8.0.02.61.1, 9.0.01.89,
11.0.00.12.1, 15.0.03.23.2, 16.0.01.78.2 et 17.0.01.64. Les versions 5.0, 6.0, 10.0 et 12.0 à 14.0
ne sont pas vérifiables : leurs archives n'ont pas de `Bin/pack.bin` ou pas l'action de fatalité.
Une apparition « 15.0 » veut donc dire « entre 11.0 et 15.0 ».

La **date** n'est pas dans les données du client. Elle vient des pages d'actualité officielles
MY.GAMES des serveurs européens (`date` du manifeste, source citée). `announced` veut dire annoncé
comme nouveau. `attested` veut dire au plus tard : c'est la première liste de vente relevée qui
contient l'objet. Le serveur russe les reçoit plus tôt.

| Type | Fatalité (FR) | Objet (FR) | Icône | Version | Date (EU) |
|---|---|---|---|---|---|
| 1-9 | classe | — | — | 4.0 (absente de 3.0) | inconnue |
| 10 | Désintégration (Ingénieur) | — | — | 7.0 (absente de 4.0) | inconnue |
| 11 | Carnage | Code du Carnifex (+ Collection, Manuel du Carnifex) | `IMFatalityLotteryScroll_04` | 9.0 (absente de 8.0) | 26.03.2015, [annonce](https://allods.my.games/fr/news/sales/vente-cassette-radiante-du-carnifex) |
| 12 | Géhenne | Discours enflammé du Carnifex (+ Collection) | `Fatality` | 11.0 (absente de 9.0) | 12.07.2019, [annonce](https://allods.my.games/en/news/sales/sale-radiant-strongbox-carnifex-120719) |
| 13 | Mâchoires démoniaques | Discours impie du Carnifex | `FatalityDemonScroll` | 15.0 | 06.08.2020, [annonce](https://allods.my.games/fr/news/sales/vente-cassette-radiante-du-carnifex-060820) |
| 14 | Rituel impitoyable | Discours impitoyable du Carnifex | `FatalityBatScroll` | 15.0 | ≤ 22.07.2021 |
| 15 | Rituel astral | Discours sauvage du Carnifex | `MagicCirclesScroll` | 15.0 | 22.07.2021, [annonce](https://allods.my.games/en/news/sales/sale-radiant-strongbox-carnifex-220721) |
| 16 | Rituel lunaire | Discours lunaire du Carnifex | `Scroll_Fatality_Black_Hole` | 15.0 | ≤ 18.08.2023 |
| 17 | Rituel mortel | Discours mortel du Carnifex | `Scroll_Fatality_Banshee_2022` | 15.0 | ≤ 18.08.2023 |
| 18 | Rituel naturel | Discours florissant du Carnifex | `FatalityLotus_Scroll` | 15.0 | 24.02.2023, [annonce](https://allods.my.games/fr/news/sales/vente-cassette-radiante-du-carnifex-1) |
| 19 | Rituel enflammé | Discours incinérant du Carnifex | `FatalityPhoenix_Scroll` | 15.0 | 18.08.2023, [annonce](https://allods.my.games/en/news/sales/sale-radiant-strongbox-carnifex-1) |
| 20 | Rituel sidérant | Discours sidérant du Carnifex | `Fatality_FireFist_Scroll` | 15.0 | ≤ 24.02.2024 |
| 21 | Rituel spiritiste | Discours de spirite du Carnifex | `ScrollFatality_Skull24` | 15.0 | ≤ 09.08.2024 |
| 22 | Rituel fou | Discours fou / Discours béni du Carnifex | `Fatality_squirrel_scroll` | 15.0 | inconnue |
| 23 | Rituel squelettique | Discours squelettique du Carnifex | `ScrollFatality_Puppet24` | 15.0 | 01.08.2025, [annonce](https://allods.my.games/fr/news/sales/vente-cassette-radiante-du-carnifex-5) |
| 24 | Rituel abyssal | Discours abyssaux du Carnifex | `FatalityScroll_AnglerFish25` | 16.0 | 24.04.2026, [annonce](https://allods.my.games/fr/news/sales/vente-cassette-radiante-du-carnifex-6) |
| 25 | Rituel corrompu | Discours déformé du Carnifex | `FatalityScroll_Tree` | 16.0 | inconnue |
| 26 | *(RU seulement : Змеиный ритуал)* | *(Змеиные Речи Палача)* | `ScrollFatality_Snake26` | 17.0 | inconnue |

Les noms **non prouvés** gardent le libellé du site, en italique dans la liste :

- 26 n'a ni texte français ni texte anglais ;
- 24 et 25 n'ont pas de texte anglais (« Monkfish », « Tree (2025) ») ;
- le nom anglais de 24 dans l'encart retombe sur le français.

Les libellés du site (`label` : « Occultiste », « Phénix »…) restent les identifiants d'URL. La
Voix du Carnifex n'apprend pas de fatalité : elle apprend l'aptitude « Voix du Carnifex », un court
message envoyé sur la discussion à la mort de la proie.

L'écran montre ces données à deux endroits :

- la liste « Fatalités de la boutique » montre l'icône et le nom officiel de l'objet principal ;
  l'infobulle du jeu y ajoute le nom de la fatalité ;
- l'encart de droite (`FatalityInfo`, au cadre et aux couleurs de l'infobulle du jeu) montre le
  nom en jeu, les objets, la version et la date avec le lien vers sa source, ou « Date inconnue ».

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

**Personnages habillés.** Victime et tueur portent la **tenue de leur classe** : les modèles de la
création de personnage (`public/game/character/models/<Gabarit>.glb`, tous les géosets) et ses
tenues des trois niveaux (`growths` de `chargen.json` : départ, intermédiaire, supérieur), résolues
à l'exécution comme sur l'écran de création (`resolveLook`, `CharacterRig` : géosets, peau cuite
avec les pièces de tenue, armes et casques accrochés) — `FatalityViewer/dress.ts`. Panneau :
**Classe** de la victime (classes de sa race) et **Tenue** (niveau supérieur par défaut, URL `cl=`
et `t=`) ; le tueur prend la classe de la fatalité quand sa race le permet (sinon la première de
sa race), et le tueur par défaut est choisi parmi les races qui peuvent la prendre.
`characters/<id>.glb` ne porte plus que le **squelette et les clips** (`Idle01` et les animations
des scripts, victime et tueur) : même squelette, mêmes noms d'articulations que les modèles de la
création, les clips s'y lient tels quels. Les gibelins jouables sont un **trio** : trois corps au
même habit, jouant la même animation — **placement inventé**, repris de l'écran de création
(compagnons à ±0,75 m sur le côté, 0,45 m en arrière : le client le code sans le publier). Il leur
manque trois animations de sort demandées par certaines fatalités de boutique.

**Tueur** (`casterFxScript`) : `Fatality_Cast` accroché à son `Slot_BodyFX` et un **rayon**
(`CreatureChannelDirectAction` : gabarit `Fatality_Channel` modelé sur `fxLength` = 10 m le long de
−Y, étiré entre ses extrémités — racine + 1 m chez le tueur et chez la victime —, fondus 0,2 s /
0,1 s) ; le Phénix ajoute ses deux animations (`speed` 1,5) et un second rayon. Le script du client
n'a pas de fin propre : il s'éteint avec la victime ; le rayon, lui, meurt avec son clip (4 s à
`speed` 1,3 = 3,08 s, non bouclé), quand l'étincelle `Soul_Spark` qu'il porte (`Slot_Special01`, de
−9,4 m à 0) atteint le tueur, avec son `fadeOutMS` (0,5 s). Les ailes (`CreatureRunVisActionResource`, sous
drapeaux `FatalityWings*` achetés en boutique) ne sont pas jouées. Mise en scène (constantes du
lecteur) : le tueur se tient à **17 m** (distance de sort, 15 à 20 m, validée), à 55° de l'avant de la victime côté −X, posé sur le terrain et tourné vers elle ; le rayon s'étire donc à 1,7 fois sa longueur modelée, fondus inchangés ; le tueur n'entre pas dans le cadrage (voir « Lecteur ») ; il
se choisit dans le panneau (défaut : même sexe, première race de l'autre faction, URL `k=`).

**Décor** (`scene/scene.glb`) — **composition assumée sur un vrai lieu**, pas la reproduction d'une
scène du jeu (le client n'a pas d'arène de fatalité). Le site est une **clairière de bouleaux des
Prés bénis**, carte `Kania`, centre (13 452, 6 192), à 540 m de l'ancien pré. Il a été choisi par
balayage de la carte : grille de 8 m, distance au plus proche des 27 320 objets posés
(`MapRegion`), relief du `terrainDump` dans un disque de 30 m (plat) et dans les couronnes de
60 à 200 m et de 200 à 400 m (collines, montagnes). La clairière n'a **aucun objet à moins de
38 m**. Au sud et au sud-ouest, des montagnes culminent 100 à 200 m plus haut, à 200-300 m. Les
autres sites bien dégagés sont des places de village (fortin kanien) ou des pentes.

Ce qui vient du client :

- **sol** : `terrainDump` 17.0 sur 450 m, fin jusqu'à 90 m, grossier au-delà. Chaque sous-carreau
  prend le premier calque de sa première passe (le mélange du `SplatMap` n'est pas élucidé). Les
  22 calques de la zone sont `BM_Grass*`, `BM_Ground*`, `BM_Stone*`, `Mountain_*`, `Quarry_Sand*`,
  `Astral_Sand*`… ;
- **lumière cuite du sol** : `<région>_lightmap.bin` (R = ciel, G = soleil et ombres). Elle est
  appliquée en couleur de sommet, comme facteur `jeu / lecteur` de la formule
  `ambiante · (f + (1 − f) · ciel) + soleil · N·S · ombre` (`baked_light`), avec la lumière de la
  zone ;
- **herbe** du `terrainDump` jusqu'à 100 m, **eau** jusqu'à 450 m (52 carrés, loin du centre),
  rendues par `vot/terrainExtras.ts` ;
- **objets posés par la carte, à leur place** (position, orientation, échelle,
  `tools/allods_scenes.read_regions`, `site_decor`) jusqu'à 420 m. Cela fait 827 objets de 57
  géométries, chacune émise une fois et partagée par ses instances. Les plus nombreux :
  `BM_Birch_Big_01/02`, `BM_Birch_small_1/2/3` et `BM_Bush_*` (Prés bénis,
  `World/Kvatoh/BlessedMeadows`), `Elf_Crystal_*`, la carrière (`Quarry_WoodenTrunk`,
  `Quarry_Boarding01`, `Quarry_Stone*`, `Sawmill_*`), le camp kanien (`Kania_WarCamp_*`,
  `K_Fence_*`, `Kania_Hospital_Tent`), le lieu de résurrection kanien (`Kania_ResurrectPlace`),
  `Elf_House_02`, des rochers `BM_Rock_02/03` et des pins `BM_Pine_Small_*`, `BM_Fir_01` ;
- **ciel** `SkyMesh` `Sky01_Day*` (première partie `Kvatoh_Day`), dessiné avant tout le reste sans
  test de profondeur (ses nuages, à 100 m de la caméra, passaient devant les arbres lointains), et
  **lumière et brouillard** du
  `ZoneLights` 7.0 `BlessedMeadowsDefault` à midi (le `ZoneLights` compilé n'est pas lu par zone).

Ce qui est de la mise en scène (manifeste, `scene.terrain` et `scene.site`) :

- le **sol du centre est aplani** à l'altitude médiane du disque de 30 m, puis raccordé au relief
  réel par un fondu jusqu'à 50 m (`Flatten`). Le relief réel varie de 6 m sur ce disque. L'herbe,
  l'eau et les objets posés dans le fondu suivent le sol ;
- le **disque de 60 m est vidé** : 25 bouleaux et buissons entre 38 et 60 m sont retirés, ce qui
  ouvre la vue sur les collines. Seul le décor lointain est gardé ;
- au-delà de 200 m, seuls les objets d'au moins 5 m restent (333 petits buissons et fougères
  écartés) ;
- l'**herbe est rase au centre** : l'échelle des touffes y est multipliée par 0,35 jusqu'à 22 m,
  puis rendue entière à 40 m. Les touffes du pré montaient au genou et masquaient les pieds ;
- l'**orbite de la caméra est bornée à 45 m** (`site.orbit`, prop `orbitMax` du lecteur) : les
  couronnes des bouleaux commencent vers 50 m ;
- les textures des objets du site et des calques de sol lointains (au-delà de 90 m) sont à
  512 px. Le sol proche garde 1024 px.

Poids : `scene.glb` 10,6 Mo et 232 textures (26,2 Mo), soit **≈ 37 Mo** pour le décor, sous les
50 Mo (l'ancien pré faisait 3,4 Mo et une vingtaine de textures). Le lecteur découpe les objets du
site par le champ de la caméra (`frustumCulled`), contrairement aux effets. Ni l'herbe ni l'eau
n'arrêtent la caméra.

    python3 tools/extract_fatalities.py --no-fx --no-characters --no-sounds   # décor seul (≈ 2 min)

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

- **Vie propre de chaque gabarit** (`VotPart`, `votInstances.ts`, option `lifetimes`) : la racine
  et chaque composant accroché ont leur fenêtre — apparition au retard du `DelayComponent` avec son
  `fadeInMS`, fin à l'arrêt (`StopVisObjectComponents`) ou **au bout de son clip s'il ne boucle pas**
  (`SkeletalAnimation.looped` faux), avec son `fadeOutMS` (le rayon et son étincelle, ci-dessus).
  Avant, la dernière pose était tenue jusqu'à la fin de vie de l'instance : 67 gabarits figés dans
  25 fatalités (neuf `FatalityBard_Lines` du Barde, dôme `FatalityDruid_Explosion01` du
  Tribaliste, chauves-souris de l'Invocateur, rayon partout…). Trois précisions **établies sur la
  vidéo de référence** (voir « Comparaison à la vidéo ») :
  - un composant **meurt au plus tard avec son parent, mais s'efface à son propre rythme** : la
    fumée de `FatalityMage_Meteor` (`fadeOutMS` 3 500) survit au socle `FatalityMage` (vie 7,6 s,
    800 ms) et se voit jusqu'à 10 s ; l'ange `FatalityPriest` (1 200 ms) est effacé à 10 s, avant
    son socle `Fatality_Priest_Basis` (vie 8,8 s, 2 000 ms). Les fondus d'entrée, eux, se
    multiplient (le socle du Mage entre en 3 s avec son météore) ;
  - l'identifiant d'un composant est celui du `DelayComponent` qui le porte : **l'arrêter avant
    son échéance l'annule**. Seul cas : `MuseL` du Barde, arrêté à 7,85 s pour une apparition à
    7,87 s — la Muse de lumière (1,5 s de clip, dorée, à 2–5 m) n'apparaît jamais dans la vidéo ;
  - un matériau opaque passe en mélange le temps d'un fondu (sinon l'ange du Prêtre surgissait
    d'un bloc malgré ses 6,5 s d'entrée).

  Les cinématiques moteur gardent l'ancien comportement (règles non vérifiées sur leur décor) ;
- **Transparence des éléments** (`ElementTrack`, `tools/extract_menu_scene.py`) : le blob d'une
  `SkeletalAnimation` porte un **second jeu de pistes, une par élément de géométrie**, que rien ne
  lisait. L'entête est une suite de couples (pointeur auto-relatif, nombre) : +4 descripteurs des
  articulations, +12 leurs noms, +20 leur ordre, **+28 descripteurs des éléments, +36 leurs
  noms** ; descripteur de 20 octets comme ceux des articulations, masque `1` = transparence
  (1 canal), `2` et `4` = deux canaux chacun (décalages de texture, non lus) ; **un octet par canal
  et par image**, entrelacé, **0 = plein, 255 = caché**. Exporté en clés `elementAlpha` (secondes
  du clip à sa vitesse, clés redondantes retirées à 1/255 près) pour 157 gabarits ; le lecteur
  (`votInstances.ts`) en multiplie l'opacité des matériaux de l'élément au temps du clip de son
  gabarit, cache l'élément à 0 et passe un élément opaque en mélange le temps d'un fondu. Un
  gabarit non skinné qui porte de telles pistes prend la durée de son clip (dague du Paladin, feux
  du Guerrier, éclairs de l'Ingénieur). C'est la règle qui cachait en jeu les poses figées :
  instruments du Barde fondus à 5,7–5,9 s (la Muse prend le relais), météores du Mage cachés dans
  le ciel puis révélés un à un à leur chute (5,3 à 7,2 s), lianes du Tribaliste rentrées à
  l'explosion (3 s) et leur base à 4,7 s, dôme `FatalityDruid_Explosion` visible de 1 à 3 s
  seulement… **Vérifiée sur une vidéo 1080p60 du jeu** (les 11 fatalités de classe, temps recalé
  sur un repère commun : flash du Barde, explosion du Tribaliste) : les apparitions et
  disparitions tombent à l'image près des pistes (voir « Comparaison à la vidéo ») ;
- **cadrage** : aucune caméra de fatalité dans le client (seules des secousses, `CameraShakerComponent`,
  s'ajoutent à la caméra du joueur). Le cadrage initial vise l'effet principal et la victime :
  le gabarit posé ou accroché qui porte le son de la fatalité (`FatalityBard`, `FatalityDruid`… ;
  à défaut de son, tous ceux de la victime ; auras et fonds `Fatality_Back` écartés) et ses
  composants, chacun par la boîte de son animation dans le client (`SkeletalAnimation.aabb`,
  `+0x24`, à défaut celle de la géométrie ; `bounds` dans `fatalities.json`) à l'échelle et au
  décalage du script, sous-sol retiré (os sous le terrain : lianes du Tribaliste jusqu'à −16 m) ;
  la caméra se place de face, en légère plongée, à la distance qui fait tenir cette boîte dans le
  champ (`EFFECT_FRAME_MARGIN`) ; le tueur peut sortir du champ ;

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

**Teintes et secousses** (appliquées) : `CreatureColorAction` (couleur ARGB, mode, priorité,
`timeOn`) teinte la victime — la plus prioritaire, atteinte depuis le blanc en `timeOn` s (brûlé
rouge sombre du Guerrier, carbonisé de l'Ingénieur, pétrifié vert d'Avril 2024…) ; modes
`DEFAULT`/`MUL` multipliés, `ADD` ajouté, `OVERLAY` approché. `ShakeAction` : courbe
`cameraTranslate` des `AnimatedParameters` (61 clés, 30 i/s, `fps` vaut 0 dans le client) × amplitude,
amortie entre `minRadius` et `maxRadius` (Universelles 2022 et 2023) ; `timeScale` non interprété.

**Comparaison à la vidéo.** Une capture du jeu (1080p60, les 11 fatalités de classe à la suite,
non versionnée) a été comparée au lecteur image par image, caméra du lecteur recentrée sur la
victime. Le temps 0 du lecteur est recalé sur un repère net de chaque segment (colonne
`Fatality_Back`, flash du Barde à 7,5 s, explosion du Tribaliste à 3,5 s) ; l'onde de la fatalité
ne suffit pas (musique mêlée, corrélation faible sauf Tribaliste et Rôdeur). Toutes les
apparitions et disparitions tombent à ±0,25 s près, sauf mention :

| Classe | Vérifié sur la vidéo |
|---|---|
| Mage | météores absents du ciel jusqu'à leur chute (7 s), explosion à 7,5 s, fumée jusqu'à 10 s |
| Prêtre | ange entré en fondu (2,5–4 s), effacé à 10 s après le flash |
| Psionique | nuage, éclairs, tourbillon bleu (9–10 s) puis flash ; rien de figé |
| Paladin | vierge de fer : apparition 0,5 s, fermeture 3 s, dagues 4–8 s, ouverture 8,5 s, poussière 11 s |
| Guerrier | lames `FatalityWarrior_Bottom` de 2 à 8,5 s, feu au sol jusqu'à 11,5 s |
| Ingénieur | machine, rayon 4,5–7,5 s, poussière 8,5–9,5 s (écart ≈ 0,5 s, repère incertain) |
| Invocateur | colonne 0–6,5 s, tas au sol 7–10 s |
| Barde | instruments fondus à 5,7 s, Muse 4,5–7,8 s, jamais de Muse de lumière |
| Rôdeur | épées 4,5–7,5 s, feu 8–10,5 s, épées plantées jusqu'à 11 s |
| Occultiste | colonne et orbe (5,5 s), anneau jusqu'à 6,5 s, colonne jusqu'à 10 s |
| Tribaliste | lianes rentrées à l'explosion, base au sol jusqu'à 4,7 s, fleur 5–10 s |

**Manques.** `ProceduralEffect` (effet `Empty`) ignoré. Particules : `WorldSpaceEmitter` et `Z_BOX`
traités comme locales / face caméra. Pas de bloom : la géométrie douce a ramené le Prêtre d'un
blanc plein à des effets lisibles, un bloom le resaturerait. Effets des tenues de création
(`growths.fx`) non joués. La durée affichée est celle du script : certaines fatalités (11 Carnage,
23 Rituel squelettique) finissent par plusieurs secondes vides.

## Création de personnage (développement)

La page `/character` (entrée « Personnage » de l'accueil, désactivée et absente du build de
production : la route n'existe que si `import.meta.env.DEV`) reproduit l'écran de création du
**client 17.0** (`/mnt/h/MyGames/AllodsRU`), dans l'ordre du jeu : **faction** → **race et
classe** (avec sexe et niveau de tenue) → **apparence et nom** (familier des Pacificateurs, trio
des gibberlings), puis « Créer ». En développement, `?race=Elf&class=MAGE&sex=female&step=race`
ouvre directement une étape (captures comparées aux écrans du jeu).

    python3 tools/extract_character_creation.py          # tout (≈ 30 min)
    python3 tools/extract_character_creation.py --only Elf --no-scenes

**Sources, toutes dans le client 17** (`Bin/pack.bin`, lu par `tools/allods_packdb.py` ; paks
lus par `packs_path()`, qui passe par `Packs.adc-real` quand `Packs` est une jonction illisible) :

- interface : addon `CharacterGenerator` (arbre de widgets, placements, **visibilité initiale**
  — octet `+0x184` —, calques, textes fixes des `WidgetTextView`, textures de
  `Interface/Wrap/MainMenu/CharacterGenerator3`, icônes de races et de classes, textes RU/EN du
  `.loc`, FR relus par clé et par chemin de widget dans le client FR) et **bandeau bas** des écrans
  du menu (`BottomLine`, addon `Main`, 67 px pleine largeur) — `tools/chargen_ui.py` ;
- données : `CharacterRoot` → factions → races → classes → deux sexes (`Character` : trois tenues
  de création avec leurs animations `chargen<Classe>Start`/`chargen<Classe>` et leurs effets,
  familier), gabarits `VisCharacterTemplate` et `CharacterVariations` (visages, traits, coiffures,
  couleurs, peaux, teintes, signes, pierres des aèdes), **corpulence** (`ModelMorphSettings` du
  gabarit, `+0x148` : 15 commandes d'échelle d'os, 9 à 12 préréglages), `VisualItem` (géosets
  montrés/cachés, calques de peau, modèles accrochés et leurs effets), règles de nommage
  `NameRules` — `tools/allods_chargen.py`, effets `tools/chargen_fx.py` ;
- décors : la carte `MainMenu` (`Bin/Maps_MainMenu.bin`, liée à `pack.bin` par `open_map`),
  construite par la **chaîne commune des cinématiques moteur** (`build_decor`, `light_decor`,
  `build_sky`, `build_terrain`, `export_waves` de `tools/extract_engine_cutscene.py`) : gabarits
  posés, éclairage précalculé de chaque sommet (`lightvrt` : ambiante + soleil + lumières ponctuelles
  des lanternes et cristaux), **sol de la carte** (`terrainDump`, calques du SplatMap, lightmaps ;
  le sol des places kaniane et gibberling n'est que du terrain), particules (feuilles d'automne),
  animations, ciel, `ZoneLights` de la case, lumières ponctuelles qui atteignent la place, ambiance
  sonore ; place et caméra de `UICharacterScenes` (`CharacterSelect<Race>`) — `tools/chargen_scene.py`.

Sorties dans `public/game/character/` : `chargen.json` (index versionné, `schema: 1`),
`ui/layout.json` + textures, `models/<Gabarit>.glb` (tous les géosets, squelette, attente et
animations de création), `attach/` (casques, épaulières, armes), `fx/` + `particles/` (effets),
`textures/` (WebP), `maps/MainMenu/` (décor commun, textures, particules), `scenes/<Race>.json`
(+ `-light.bin`, `-sky.glb`), `sfx/` (ambiances, sons de l'interface `Chargen.bsb`).

**Règles établies sur les données** : tenue par défaut = corps nu (cache tous les géosets à
variantes) ; un objet porté montre ses formes et cache ses géosets, un géoset caché par un objet
l'emporte (le casque cache les cheveux) ; texture cuite = peau (`IndexedTexture`, teinte sous le
masque alpha) puis calques (visage, pilosité, signe, cuir chevelu teint de la couleur des cheveux,
sous-vêtements `bra`/`pants`, pièces de tenue), rectangles `x1 x2 y1 y2` avec V depuis le bas ;
indices 16 bits des grandes géométries relatifs au `vertexBufferOffset` de l'élément ; calques
additifs de l'interface (`WidgetLayer` +0x24 = 2) rendus en alpha (noir transparent) ; états des
boutons **par place** dans la variante (`+0x08` surbrillance, `+0x70` désactivé, `+0xA0` survolé,
`+0xD0` normal, `+0x100`/`+0x130` appuyé), la variante 1 étant le choix (bande claire de la race
et de la classe choisies) ; panneaux redimensionnés par les scripts (`SetPlacementPlain`) :
apparence `n × 68` px, noms `(1 + n) × 130` px, emplacements de nom remplis dans l'ordre ;
commandes d'apparence dans l'ordre `variationOrder` du script (`faces`, `facials`, `hairs`,
`hairColors`, `shoulderStones`, `additionals`, `skins`, `skinColors`, `morphPresets`), montrées
si leur plage compte plus d'une valeur ; l'objet de main secondaire se tient dans la main gauche,
l'arme à distance n'est pas tenue ; les matériaux transparents des personnages (ailes des elfes,
lueurs) sont sans éclairage ; `StaticLight` du 17 : champs par ordre alphabétique avec un mot
ajouté en `+0x48`, d'où `PointLightColor` en `+0x4C` et `SelfIllumColor` en `+0x50` (recoupé sur
les sept `ZoneLights/*_Chargen` de l'arbre 7.0) ; effets de tenue (`ChargenEffect`) : échelle en
`+0x24`, `runType` en `+0x20` (`KEY` joué une fois, `LOOP` en boucle), gabarit non bouclé effacé
à la fin de sa durée ; matériaux opaques des effets découpés à l'alpha 0,5 de leur texture (seuil
des pixel shaders du jeu, fougères du Tribaliste).

**Éclairage des personnages**, d'après les shaders du client désassemblés
(`Material/common_sm4-dx11.bin`, `pointLit-dx11.bin`) : passe principale `texture × (ambiante +
soleil · max(N·L, 0) + ¼ · min(N·L, 0)² · (⅔ · Σ soleil − soleil))`, sans lumière ponctuelle ;
une passe additive par lumière ponctuelle, par `N·L`, saturée à 2 × la texture. La couleur que le
moteur passe à cette passe n'est pas publiée : les personnages prennent la loi du décor
(`PointLightColor · min(1, Σ intensité · (1 − d/rayon)^atténuation · N·L)`) — `ActorLighting`
(`src/components/scene/CharacterCreation/actorLight.ts`).

**Repère** : sans miroir. Confronté aux écrans du 17.0, le repère du jeu (X, Y au sol, Z en haut)
se lit en main droite — méridienne à gauche du décor elfe, orbe du mage dans la main levée ; avec
le miroir X des autres lecteurs, décor et personnage sortaient inversés. L'export `.glb` tourne
seulement Z en haut → Y en haut (plus d'échelle négative).

**Caméra** : celle de la place (`UICharacterScenes`, champ horizontal 1,36 rad), **tangage compté
positif vers le bas** (−3° pour l'elfe : visée relevée, d'après le quaternion de la place 7.0),
reculée sur son axe de `preMissionAdditionalAway` du gabarit (0,5 m) : statues et estrade entières
comme à l'écran du jeu, même plan aux étapes race et apparence (le script n'a pas de caméra :
`preMissionCamera` du 7.0 ne porte que `cameraFullTime`). **Molette** et **pincement** (mobile) :
zoom de ce plan vers `preMissionFaceCameraAnchor` (hauteur du visage), jusqu'à 1,3 m ; le
glisser tourne toujours le personnage.

**Descripteur** (`src/data/character/descriptor.ts`, `kind: "allodex.character"`, `version: 1`) :
faction, race, sexe, classe, nom, indices d'apparence dans les listes du gabarit (corpulence
comprise), niveau de tenue, compagnons du trio, familier (gabarit, pelage, nom). Validé contre
`chargen.json` (`validateDescriptor`, utilisable côté serveur). Persistance derrière
`CharacterStore` (`src/data/character/store.ts`) : `LocalCharacterStore` (`localStorage`)
aujourd'hui, une implémentation HTTP demain sans toucher à l'écran.

**Export `.glb`** : côté navigateur (`GLTFExporter`), de ce qui est affiché — géosets visibles,
texture cuite composée, modèles accrochés, compagnons et familier en nœuds frères, clips de la
tenue et attente ; descripteur dans les `extras`.

**Décisions de l'utilisateur (septembre 2026)** : textures en **WebP sans réduction** (taille
d'origine, qualité 90) ; ambiances sonores de chaque décor branchées (événement FMOD → onde par son
nom, puis boucle `_lp` des banques d'ambiance dont le nom contient tous les mots de l'événement —
`SteppeWindy_AP` → `steppe_wind_lp` —, rien sinon) ; caméra de création décodée (voir « Caméra ») ;
ordre des étapes du jeu (faction → race et classe → apparence et nom).

**Écarts connus** : plages d'apparence envoyées par le serveur, reprises de l'écran de l'elfe
(« Qualité de peau » et « Caractéristiques additionnelles » fermées pour toutes les races) ;
ambiances sans onde retrouvable (`AI36` de l'elfe, `LoginScreen`, `SnowWindy_AP`…) muettes, le
projet d'événements FMOD des ambiances n'étant pas livré ; places du familier et des compagnons du
trio inventées (le client ne les publie pas) ; aèdes : estrade reprise du décor ; préréglage de
corpulence par défaut = le plus proche de l'échelle 1 ; un effet `KEY` part avec l'animation de
création (les clés d'animation qui le déclenchent peut-être ne sont pas décodées) ; loi des
lumières ponctuelles sur les personnages reprise du décor (voir « Éclairage des personnages »).

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

**Icônes vérifiées.** Chaque talent porte `iconSrc` (chemin `.bin` en 32 bits, entrée du pak
en 64 bits) ; `tools/talent_icons_check.py` le confronte à l'arbre serveur 7.0 (`<image>` du sort,
en remontant les `<Prototype>`, puis `<singleTexture>` et `<binaryFile>`) et compare d'une version
à l'autre les fichiers d'icône des talents de même nom. Correctif du 23/09/2026 : le cache
d'icônes de l'extracteur, commun à toutes les versions, avait pour clé « nom du pak#rang » ; or
`Interface.Mini.pak` existe dans les trois clients 64 bits avec un contenu différent : le 16.0 et
le 17.0 reprenaient l'icône du 15.0 au même rang (bon titre, mauvaise image : 195 icônes sur
1 055 en 16.0, 220 sur 1 058 en 17.0 ; aucune avant la 16.0). La clé est désormais le chemin
complet du pak. Après correction : 7.0 conforme à l'arbre serveur à 100 % (375/375 talents dont
l'arbre donne l'icône), 15.0 ↔ 16.0 : 99,8 % de fichiers identiques, 7.0 ↔ 17.0 : 80 % (les
écarts restants sont des icônes renouvelées, cohérentes avec le talent : « Merciless Storm » →
`RuthlessStorm`, « Summer Storm » → `DruidCallLightningUpgrade`). Table code → pak : le bloc 6
lu par `tools/packbin.py` est identique à `PackDB.pak_names` de `tools/allods_packdb.py` (309
paks) ; chemins des paks résolus par `packs_path()` (repli `Packs.adc-real`) ; `pack.bin` des
clients 64 bits décompressé dans le cache partagé et projeté en mémoire.

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
    non repris tels quels (les 91 / 80 de la 16.0 viennent de l'utilisateur). Le premier retire aussi un
    point par sort de départ, comme le script du jeu.
  - 16.0 : **91** points de talent (livre) et **80** rubis (grilles), valeur en jeu donnée par
    l'utilisateur. La fenêtre 16.0 (`ContextTalents`) n'affiche que les points libres, sans
    total ; ces valeurs sont retenues comme totaux **nets** des 3 points offerts (même convention
    que le compteur 17.0 `libres/(total − 3)` : un build 16.0 complet affiche 0/91 et 0/80). C'est
    aussi la convention du calculateur `alloder.pro`, dont la configuration f2p porte exactement
    91/80 et qui retire 1 point par sort de départ et ne compte pas la case centrale.
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
  récentes (Eden, Jigran, Xadagan, Quator, Isa, Suslanger, Airin…), le type est **déduit** de la
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
**79,7 %** des récents. Ce qui manque est surtout la 17.0 (Quator : « Сказ о Валирах », « Сказ о
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
blog, artbook) ne sont pas repris. **Toutes les images du corpus** (captures, cartes, concepts,
logos, interface, illustrations des `.docx`) sont reprises : l'auteur l'a autorisé (septembre 2026) ;
elles portent le même crédit (galerie ci-dessous).

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
| Atlas | les 318 allods de l'atlas de Makar Terentiev (données, descriptions pour 159 d'entre eux), 30 notes d'atlas (îles sans allod, sections techniques), 111 régions, 1 298 lieux du jeu | 1 757 |
| Library | 11 livres et séries (pages dans l'ordre), 10 récits et 3 notes communautaires, 143 documents, 507 lettres, 447 descriptions d'ambiance | 1 121 |
| Characters | 3 640 PNJ nommés (homonymes fusionnés) avec leurs dialogues, 403 factions/races/classes | 4 043 |
| World Secrets | 50 secrets, leurs étapes et les quêtes de chaque étape | 50 |
| Quests | 6 962 quêtes par région | 6 962 |
| Gallery | 169 albums de dossiers du corpus et 6 albums des documents de l'atlas : 3 319 images de Makar Terentiev | 175 |
| *(Dialogues)* | 10 517 répliques qu'aucun PNJ ne rattache : **sans onglet ni liste**, atteintes par la recherche et par le lien de leur quête (1 801 ont une quête) | 10 517 |

Les répliques non rattachées vivent dans une section cachée (`/lorebook/dialogues/<id>`) : leurs
blocs sont rangés par rid croissant et la page trouve le bon par dichotomie sur
`list/dialogues-index.json` (1 Ko, premier rid de chaque bloc), sans charger de liste. La liste des
personnages passe ainsi de 870 Ko (250 Ko gzip) à **192 Ko (61 Ko gzip)**.

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
de la section ouverte (`list/<langue>/`, 2 Ko à 340 Ko ; au plus 96 Ko gzip, pour les quêtes), le bloc
de l'entrée (~90 Ko) et, s'il manque un texte, le même bloc dans la langue de repli ; les listes
sont **virtualisées** (seules les lignes visibles existent dans le DOM). Poids total sur disque :
79 Mo (textes 51, index 19, répertoire 7, listes 3), dont rien n'est chargé d'un bloc.

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
  jeux classiques, îles mentionnées, allods du scénario) ; `atlas/atlas-section-3a|3b.json` et
  `atlas/atlas-sections-4-7.json` : le reste de l'atlas (îles astrales, autres îles, non classées,
  journal des modifications, sources) ; `atlas/astral-islands-*.json` : les quatre documents des îles
  astrales (AO 2.0+ parties 1 à 3, BETA) (≈ 41 000 mots russes) ;
- `community/secret-list.md`, `constellations-martyrs-patrons-dragons.md`,
  `reflection-bosses.md` : les notes (« sec list », « Созвездия », `boses.txt`), groupe
  « Community notes ».

Tout le matériel de Makar Terentiev est désormais traduit. Non repris : le billet de blog tiers
« Край мира с форума АО », l'artbook de Fardreamer et l'« Энциклопедия Сарнаута » (droits de tiers).

**Galerie** (section « Gallery », `/lorebook/gallery/<album>`) : toutes les images du corpus de
Makar Terentiev, avec son accord.

    python3 tools/build_lore_media.py   # ≈ 25 min la première fois (reprise incrémentale), écrit
                                        # public/game/lorebook-media/ et public/game/lore/media.json

L'outil lit les 3 330 fichiers image du corpus (PNG, JPEG, WebP, GIF, DDS, PSD, ORA recomposé
depuis ses calques, vignette pleine taille des `.pdn`) et les 987 illustrations des six `.docx` de
l'atlas, chacune rattachée au dernier intertitre qui la précède (« Раздел N » + numéro, ou titre gras
des documents des îles astrales). Il écrit une WebP de 1 600 px (4 096 px pour les cartes du monde
de 18 000 à 23 000 px) et une vignette de 480 px par image distincte (SHA-1 : **3 319 images,
353 Mo**) ; les cartes géantes (> 60 Mpx, ~4 Go de pic) sont converties seules dans le processus
principal, et un processus de conversion tué est repris image par image. `build_lorebook.py` en
fait :

- **175 albums** : un par dossier du corpus (titre anglais officiel de l'allod ou de la région du
  même nom, sinon `tools/lorebook/media-albums.json`), liés à leur album parent et à leurs
  sous-albums, groupés par dossier de premier niveau ; un par document `.docx`, par intertitre ;
- des **galeries sur 269 fiches de l'atlas** : images du dossier au nom de l'allod (ou d'un
  sous-dossier), des fichiers à son nom (« Чумной Город 2.jpg ») et des intertitres à son nom ;
  les **720 illustrations** des rubriques traduites de l'atlas s'affichent sous le texte de leur
  rubrique (même partie et même numéro, sinon même nom). Dans une fiche, une copie visuelle
  (empreinte dHash à 4 bits près : la même carte dans le dossier et dans le `.docx`) n'est montrée
  qu'une fois ; les albums gardent tout.

Vignettes à chargement différé (24 affichées, puis « Show all »), visionneuse plein écran (flèches,
Échap, lien vers l'image).

**Noms propres** : alignés sur le client anglais officiel (textes parallèles russe/anglais de
`public/game/lore/`). Quelques arbitrages, avec le nombre de textes du client qui les emploient :
Вероника Гипатская = **Klavdia** (Kalugina) (239 textes, contre 6 pour Veronika/Veronica) ;
Кватор = **Quator** (« Quator Knights' Helm »… ; « Casque des chevaliers de Quator » côté FR),
aussi dans les libellés du lecteur de musique ; Кватох = **Kania** (60, « Kanian Archipelago » 31,
« Kvatoh » 1) ; Ингос = **Lightwood** (17) ; Сонная дубрава = **Drowsy Woods**, Лумисаар =
**Lumix Isle**, Бухта Чёрных флагов = **Jolly Roger Bay** ; Остров головорезов = **Goblinball
Stadium** ; les boss et PNJ renommés par la version anglaise (Бузаги-бей = Minotaur, Змееликая =
Lamia Princess, Чёрная Вдова = Widixa…). Un contrôle systématique compare chaque nom du glossaire
présent dans un texte russe à sa traduction ; les écarts restants sont des mots communs
(« хлад », « застава », « галерея ») ou des paires du glossaire non confirmées par le client.

Crédit affiché : *Allods atlas and community lore material compiled by Makar Terentiev
(DarkyAndSparky), https://github.com/DarkyAndSparky/atlas-ao*.

## Référencement et audience (`server/`)

Un petit backend Node (`server/`, Hono) complète le site statique, avec une base **MySQL**
(5.7+ ou MariaDB 10.3+) via l'ORM **Drizzle**. Il servira aussi les fonctions à venir (comptes,
avatars). Le schéma est dans `server/src/schema.ts` ; après une modification,
`npm run db:generate` (dans `server/`) écrit la migration SQL suivante dans `server/drizzle/`,
appliquée automatiquement au démarrage. Ne jamais modifier une migration déjà publiée.

**Référencement.** `src/seo/meta.ts` décrit chaque page (titre, description, image Open Graph,
FR/EN) ; module pur partagé par le client et le serveur. Les robots des réseaux sociaux
n'exécutant pas le JavaScript, c'est le serveur qui écrit les balises dans `index.html`, entre
les marqueurs `<!--seo-->…<!--/seo-->` : titre, description, `canonical`, Open Graph et
Twitter, `hreflang`, JSON-LD (`WebSite` + recherche, fil d'Ariane, `Article` pour le Lorebook).
Au build, le bloc reçoit les balises de l'accueil : si le backend est arrêté, le site reste en
ligne avec celles-ci. Côté client, `PageHead` les met à jour à chaque navigation.

- Langue : `?lang=fr|en` pour l'interface (sans paramètre : `x-default`, langue du navigateur),
  `?text=fr|ru` pour le texte du Lorebook (anglais par défaut). Chaque variante est une URL
  distincte du plan du site, avec ses alternatives `hreflang`.
- Lorebook : le serveur lit `dist/game/lorebook/` au démarrage (≈ 15 400 entrées) et tire
  titre et extrait de chaque entrée de son texte ; une entrée inconnue répond 404. Les
  dialogues isolés et la recherche sont en `noindex`.
- `/robots.txt`, `/sitemap.xml` (index) et `/sitemaps/*.xml` (pages, puis une section du
  Lorebook par fichier) sont générés par le serveur.
- Images Open Graph (1200 × 630) : `public/og/<page>.jpg`, capturées sur le site par
  `node tools/capture_og.mjs --base http://localhost:<port>` (Vite lancé à part).
- Domaine canonique : `https://allodex.eu` (`SITE_URL` dans `src/seo/meta.ts`, variable
  `SITE_URL` du serveur). Les deux autres noms devraient rediriger en 301 vers lui.

**Mesure d'audience**, sans cookie ni service tiers (conditions de la CNIL pour une mesure
exemptée de consentement, décrites dans les CGU) : `src/analytics/tracker.ts` envoie une vue
à chaque changement de chemin, un ping toutes les 20 s tant que l'onglet est visible (présence
en direct, durée de lecture) et une fin de vue au départ (`navigator.sendBeacon` vers
`POST /api/collect`). Le visiteur est un condensat (sel du jour + IP + navigateur) dont le sel
est effacé chaque jour ; l'IP n'est jamais stockée ; la session est un identifiant aléatoire
de l'onglet (`sessionStorage`). Robots écartés, pages vues purgées après 13 mois. Contrat de
l'API : `src/analytics/api.ts`.

**Registre des builds de talents** (`server/src/talents/builds.ts`, tables `talent_builds` et
`talent_build_events`) : le calculateur (`src/data/talents.track.ts`) envoie à
`POST /api/talents/events` chaque build composé (quand l'édition se pose 6 s, au partage ou à la
fermeture de la page — pas les étapes intermédiaires), chaque lien copié et chaque ouverture d'un
build venu d'un lien. Le serveur vérifie le build contre `dist/game/talents/` avec les règles du
calculateur, puis l'écrit une fois par contenu : l'identifiant est un condensat de la version, de
la classe et des codes `b`/`b2`, si bien que le même build retombe toujours sur la même ligne. Les
compteurs (`generations`, `shares`, `views`) comptent un visiteur une fois par jour et par build ;
l'auteur qui rouvre son build le jour même n'ajoute pas de vue. La colonne `player_id` attend la
future table des joueurs (« build de X »). Les événements sont purgés après 13 mois, les builds
et leurs compteurs restent.

**Tableau de bord** : `/stats` (mot de passe `ADMIN_PASSWORD`, cookie signé de 30 jours ;
20 échecs par heure bloquent la connexion). Visiteurs, pages vues, sessions, durée, rebond et
leur évolution, courbe par heure ou par jour, pages les plus vues, rubriques, pages d'arrivée,
provenances, appareils, navigateurs, systèmes, langues, et le direct page par page (flux SSE
`GET /api/admin/live`, toutes les 2 s). Un clic sur une page filtre tout le tableau. En bas,
le calculateur de talents (`GET /api/admin/talents`) : builds composés, générations, partages et
vues sur la période et depuis le début, classement par classe et builds les plus vus.
En développement, `/stats?mock` affiche des données fictives sans backend.

**En local :**

    cd server && npm install && cp .env.example .env    # DATABASE_URL, ADMIN_PASSWORD
    npm run dev                                         # port 8787 ; Vite relaie /api

Les tests du serveur tournent sur une vraie base MySQL, jetable (vidée à chaque test) ; par
défaut `mysql://root:allodex@127.0.0.1:33406/allodex_test`, sinon `TEST_DATABASE_URL` :

    docker run -d --name allodex-mysql-test -p 127.0.0.1:33406:3306 -e MYSQL_ROOT_PASSWORD=allodex \
      -e MYSQL_DATABASE=allodex_test --tmpfs /var/lib/mysql mysql:8.4
    npm test

Le traceur n'envoie rien en développement, sauf avec `VITE_TRACK=1 npm run dev` à la racine.
Pour essayer le build complet sans nginx : `SERVE_STATIC=1 npm start` dans `server/`, puis
http://localhost:8787.

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

    # 2. reconstruire sur place (≈ 5 min : la copie de public/game pèse 2 Gio).
    #    NODE_ENV=production explicite : un NODE_ENV hérité du shell produirait un bundle de dev.
    ssh <utilisateur>@<serveur> 'cd /srv/node/allodex && NODE_ENV=production npm run build'

    # 3. backend : dépendances, puis redémarrage (relit l'index du Lorebook)
    ssh <utilisateur>@<serveur> 'cd /srv/node/allodex/server && npm ci --omit=dev && pm2 restart allodex-api'

**Première mise en place du backend** : créer la base et son utilisateur MySQL,

    CREATE DATABASE allodex CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
    CREATE USER 'allodex'@'localhost' IDENTIFIED BY '<mot de passe>';
    GRANT ALL PRIVILEGES ON allodex.* TO 'allodex'@'localhost';   -- les migrations créent et modifient les tables

puis `cd server && npm ci --omit=dev`, créer `server/.env` (`DATABASE_URL`, `ADMIN_PASSWORD`
long et unique ; voir `.env.example`), `pm2 start deploy/ecosystem.config.cjs
&& pm2 save`, puis fusionner `server/deploy/nginx.conf.example` dans le vhost (proxy de `/api/`,
de `/robots.txt` et des plans du site, pages via le serveur avec repli sur `index.html`) et
`nginx -t && systemctl reload nginx`. Penser à inclure la base `allodex` dans les sauvegardes MySQL.
Le vhost modèle redirige aussi `allodex.online` et `allodex.allods-developers.eu` vers
`https://allodex.eu` (domaine principal).

nginx sert `dist/` avec repli à page unique (`try_files $uri $uri/ /index.html`), cache d'un
an sur `/assets/` (noms hachés), de trente jours sur `/game/` et `/fonts/`, et `no-cache` sur
`index.html` — sans quoi un déploiement passerait inaperçu. Le vhost est
`/etc/nginx/sites-enabled/allodex.conf` ; les sauvegardes vivent dans `/root/nginx-backups/`
(**jamais** dans `sites-enabled/`, qui est inclus par joker : un `.bak` y est chargé et casse
la configuration pour cause de `listen` en double).

Le front n'a pas de `.env` : `vite build` fige `import.meta.env.PROD` à la construction. Seul
le backend en a un (`server/.env`, non versionné).

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
