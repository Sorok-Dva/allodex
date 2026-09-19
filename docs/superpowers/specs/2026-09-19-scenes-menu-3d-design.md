# Scènes de menu animées (4.0 → 8.0) en three.js

Date : 2026-09-19 · Statut : validé en discussion (« passe directement aux scènes animées en three.js »).

## 1. Objectif
Remplacer, dans les Chroniques, le fond fixe des versions 4.0 à 8.0 par la **scène animée du menu
du jeu** rendue dans le navigateur : décor en calques 3D, couleurs de sommet, navires animés (7.0),
drapeaux, pierres flottantes. Fidélité visée : celle d'une capture du menu, sans l'interface. Les
particules (tirs, explosions) sont hors périmètre v1.

## 2. Sources
- Arbre serveur décompressé : `F:\ALLODS ONLINE SERVER\Allods 7.0\game\data\World\MainMenu\Animated_Background{,_5_0,_6_0,_7_0,_8_0}\` (chemin WSL `/mnt/f/...`) — `.xdb` XML : `(Geometry)` (modelElements → plages d'index/sommets + `material/diffuseTexture` + `BlendEffect`), `(Texture)` (dimensions, `.bin`/`.hi.bin`, `wrap`), `(VisObjectTemplate)` (géométrie, `states/animation`, `visObjComponents` : `AttachedVisObjectComponent` à un `locatorName` avec offset/rotation/scale, `DelayComponent` = spawn aléatoire → ignoré v1), `(StaticObject)`, `(SkeletalAnimation)` (fps, startFrame/endFrame, looped, blob `.bin`).
- Binaires `.bin` (là où l'arbre serveur ne les a pas : packs `World_MainMenu_Animated_Background*.pak` des clients 7.0 `/mnt/f/ALLODS ONLINE SERVER/Clients/Allods Revelation 7.0` et 8.0 `/mnt/i/Backups/GameClients/AllodsClient/MyGames/Allods Online FR 8.0`). Format (spike `.superpowers/amm-spike/`, README-textured.md) : `zlib(chunks (u32 localID, u32 size, payload))`, localID 0 = vertex buffer (stride 28/32/36 : pos f32×3, uv f32×2, normale u8×4 @20, couleur RGBA u8 @24, tangentes si 36), 1 = index buffer u16, 3 = collision (ignoré). Textures : même conteneur, clé = niveau de mip, DXT1/DXT5. Couleur de sommet ×2 (overbright), `(0,0,0)` = sans teinte.
- Racine (4.0) : `Animated_Background/` ; axes : profondeur X (4.0–6.0) ou Y (7.0/8.0), Z vertical.

## 3. Pipeline : `tools/extract_menu_scene.py` + `tools/scenes_manifest.json`
- Par version : lit les xdb, résout la hiérarchie (racine `AMM_<v>` + attaches), exporte **un glTF binaire** `public/game/archive/<v>/scene.glb` (KHR_materials_unlit, COLOR_0 pré-multiplié ×2 clampé, textures PNG intégrées, `alphaMode` BLEND/OPAQUE, extras `{ blend: "add" }` pour `BLEND_EFFECT_ADD`, `doubleSided` selon le matériau) et un `scene.json` (caméra : position, cible, fov ; axe « haut » ; fond ; liste des animations).
- Animations : décoder `(SkeletalAnimation).bin` (courbes par joint : rotation quaternion + translation, 30 fps, N images) → animations glTF sur les nœuds des joints ; si le décodage échoue pour un fichier, l'exporter sans animation et le signaler dans le rapport (jamais bloquant).
- Caméra : inconnue dans les données (codée dans le client). `scenes_manifest.json` porte une caméra **par version** (valeurs initiales = celles du spike, à caler sur une capture du menu 7.0 fournie par l'utilisateur quand elle arrive). L'outil ne fait aucune estimation cachée : ce qui est affiché vient du manifeste.
- `archive.json` : l'entrée gagne `scene: { glb: "scene.glb", meta: "scene.json" }` en plus de `background` (repli). Tests pytest : parseur xdb (modelElements→matériaux), lecture des chunks, décodage d'un vertex buffer synthétique, écriture glTF valide (validation structurelle : bufferViews/accessors cohérents), courbes d'animation sur un blob synthétique une fois le format connu.

## 4. Front : `MenuScene` (three.js, `three` ≥ 0.186 en dépendance)
- Dans `ChroniclesScreen`, `MediaLayer` rend `<MenuScene>` quand `entry.scene` existe et que WebGL est disponible ; sinon l'image de fond actuelle. Chargement `GLTFLoader`, matériaux `MeshBasicMaterial` (vertexColors, map, transparent, `AdditiveBlending` si extras.blend = add, depthWrite false pour les transparents), tri par distance pour les transparents, `AnimationMixer` en boucle, caméra depuis `scene.json`, redimensionnement plein écran (`cover` : fov vertical constant), `prefers-reduced-motion` → mixer à l'arrêt sur la première image.
- Fondu croisé version → version inchangé (la couche est un `<canvas>` opaque). Démontage propre (renderer.dispose, textures). Tests Testing Library avec three mocké (le composant reçoit un loader injectable) : monte un canvas, appelle la boucle, dispose au démontage ; repli image sans WebGL.

## 5. Vérification
Captures 1920×1009 des cinq versions (Playwright, WebGL logiciel via `--use-gl=swiftshader` ou `--enable-unsafe-swiftshader`), comparaison à l'œil avec les rendus du spike et, pour la 7.0, avec la capture du menu de l'utilisateur ; gates habituels ; README section « Scènes de menu » (comment recaler une caméra dans `scenes_manifest.json`).
