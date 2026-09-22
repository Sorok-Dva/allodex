import * as THREE from 'three';

/**
 * **Emprunt non natif** (demandé par l'utilisateur, sept. 2026) : défilement des trois
 * grandes langues de feu des braseros. Le xdb ne leur donne aucune vitesse — ce n'est pas un
 * trou de données (voir README, « Scène 8.0 ») : dans le client, seul le cœur du brasero
 * remue. Comme pour l'emprunt des vitesses 7.0 de la 4.0 (`v4/v4Fog.ts`) ou l'amplification
 * du manarail 6.0, on assume ici un écart pour que les flammes vivent.
 *
 * - **Grandeur** empruntée au voisin natif `fire_spots` (0,3 tuile/s, même brasero), désynchronisée
 *   d'une couche à l'autre : 0,30 / 0,24 / 0,18.
 * - **Axe u, pas v** : ces trois couches tuilent leurs UV le long de u (`group3_Fire2`
 *   1,40 → 3,73 ; `group3_Fire3` −1,76 → −1,28 ; `group3_Fire4` 0,10 → 0,86), et c'est u qui
 *   suit la hauteur de la flamme — +u pointe vers le **bas** à l'écran sur 88 à 100 % de leur
 *   surface, alors que v y est surtout horizontal (un défilement v ferait glisser le feu de
 *   côté). C'est aussi l'axe que l'auteur a choisi pour la seule flamme qu'il anime,
 *   `group3_Fire1` (u 0,02).
 * - **Signe négatif** : le contenu avance dans le sens de la vitesse (voir `update`), donc
 *   vers −u, c'est-à-dire vers le haut.
 *
 * `group3_FireGlow` et `glow_add` restent figés (vignettes posées une fois, UV dans [0 ; 1]) ;
 * `group3_Fire1` garde sa vitesse native. À retirer si une vitesse native apparaît.
 */
export const BORROWED_FIRE_SPEEDS: Readonly<Record<string, readonly [number, number]>> = {
  group3_Fire2: [-0.30, 0],
  group3_Fire3: [-0.24, 0],
  group3_Fire4: [-0.18, 0],
};

/** Vitesse de défilement (tuiles/s) d'un élément : l'emprunt s'il y en a un, sinon la vitesse native du glb. */
export function scrollSpeedOf(element: string, native: readonly number[] | undefined): readonly number[] | undefined {
  return BORROWED_FIRE_SPEEDS[element] ?? native;
}

/**
 * Le décor 8.0 est un seul maillage dont le xdb déclare `sortMode = OFFSETS` : le
 * client peint ses éléments **dans l'ordre du fichier** (ciel, nuages lointains, cité,
 * faisceau, cascade, premier plan droit puis gauche, statue, colonnes, herbe, arbres
 * d'amorce, nuages et brume de premier plan, feux). Les calques étant des arcs
 * concentriques autour de la caméra, leur profondeur moyenne ne dit rien de cet ordre
 * — le tri générique faisait passer les nuages de fond devant la statue. On reprend
 * donc l'ordre natif : `GLTFLoader` crée un maillage par primitive dans l'ordre du
 * glTF, lui-même celui du xdb, et `traverse` les visite dans cet ordre.
 */
export function prepareV8Layers(root: THREE.Object3D) {
  const meshes: THREE.Mesh<THREE.BufferGeometry, THREE.MeshBasicMaterial>[] = [];
  root.traverse(object => {
    const mesh = object as THREE.Mesh<THREE.BufferGeometry, THREE.MeshBasicMaterial>;
    if (mesh.isMesh && !Array.isArray(mesh.material) && mesh.geometry.userData.element !== undefined) meshes.push(mesh);
  });
  meshes.forEach((mesh, index) => { mesh.renderOrder = index; });

  // Défilement UV natif (`uTranslateSpeed`/`vTranslateSpeed`, en tuiles par seconde) :
  // vapeurs de la cascade et de la statue, flammes des braseros, faisceau, nuages. La
  // vitesse est une propriété de l'**élément** du xdb, mais l'exportateur ne distingue
  // les matériaux glTF que par texture et mode de fusion : `Noise03White03` additif est
  // ainsi partagé par `Statue_glow` (0,1 ; 0,1), `fire_spots` (0 ; 0,3) et `group3_Fire1`
  // (0,02 ; 0), `BackCloud` par les nuages (0,01 ; 0) et la vapeur de la cascade (0 ; 0,2).
  // Ne faire défiler qu'une fois le matériau partagé figeait braises et cascade : on
  // clone le matériau (et sa texture) par vitesse distincte, et les éléments de même
  // vitesse continuent de partager le même clone.
  const scrolling: { texture: THREE.Texture; original: THREE.Texture; material: THREE.MeshBasicMaterial;
    offset: THREE.Vector2; speed: THREE.Vector2 }[] = [];
  const variantsOf = new Map<THREE.MeshBasicMaterial, { speed: THREE.Vector2; material: THREE.MeshBasicMaterial }[]>();
  const originals = new Map<THREE.MeshBasicMaterial, THREE.Texture>();
  const reassigned: { mesh: THREE.Mesh; source: THREE.MeshBasicMaterial }[] = [];
  const clones: THREE.MeshBasicMaterial[] = [];
  for (const mesh of meshes) {
    const speed = scrollSpeedOf(String(mesh.geometry.userData.element),
      mesh.geometry.userData.uvScroll as number[] | undefined);
    const source = mesh.material;
    if (!source.map || !speed || (!speed[0] && !speed[1])) continue;
    const velocity = new THREE.Vector2(speed[0], speed[1]);
    const variants = variantsOf.get(source) ?? [];
    const existing = variants.find(v => v.speed.equals(velocity));
    if (existing) {
      if (existing.material !== source) { mesh.material = existing.material; reassigned.push({ mesh, source }); }
      continue;
    }
    const original = originals.get(source) ?? source.map; // avant toute retouche, `map` est l'image d'origine
    originals.set(source, original);
    let material = source;
    if (variants.length) {
      material = source.clone(); // deuxième vitesse sur le même matériau : copie indépendante
      clones.push(material);
      mesh.material = material;
      reassigned.push({ mesh, source });
    }
    const texture = original.clone();
    texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
    texture.needsUpdate = true;
    material.map = texture;
    variants.push({ speed: velocity, material });
    variantsOf.set(source, variants);
    scrolling.push({ texture, original, material, offset: texture.offset.clone(), speed: velocity });
  }
  return {
    count: meshes.length,
    update(time: number, reduced: boolean) {
      const elapsed = reduced ? 0 : time;
      // Loi du client, la même sur les deux axes : le **contenu avance dans le sens de la
      // vitesse** dans l'espace UV de la géométrie (on échantillonne `uv − vitesse × t`).
      // Tous les calques dont le mouvement se voit la confirment : vapeurs de la cascade
      // (v 0,2) et de la statue (v 0,04 / 0,05), braises `fire_spots` (v 0,3) et brume de
      // rivière `river_steam_01` (u 0,02) ont leur axe positif tourné vers le haut et
      // montent ; la cascade `waterfall_water` (u 0,5) a +u tourné vers le bas et tombe.
      // three.js échantillonne `repeat × uv + offset` : le décalage vaut donc
      // `−repeat × vitesse × t`, soit +v × t sur la texture retournée par `prepareTexture`
      // (repeat.y = −1) et −u × t en horizontal. Jusqu'en sept. 2026 le signe de u était
      // l'inverse de celui de v : la cascade remontait.
      for (const { texture, offset, speed } of scrolling) {
        texture.offset.set(offset.x - texture.repeat.x * ((elapsed * speed.x) % 1),
          offset.y - texture.repeat.y * ((elapsed * speed.y) % 1));
      }
    },
    dispose() {
      for (const { texture, original, material } of scrolling) {
        material.map = original;
        texture.dispose();
      }
      for (const { mesh, source } of reassigned) mesh.material = source;
      for (const clone of clones) clone.dispose();
    },
  };
}
