import * as THREE from 'three';

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
  // vapeurs de la cascade et de la statue, flammes des braseros, faisceau, nuages. Un
  // matériau partagé par plusieurs éléments ne défile qu'une fois ; la texture est
  // clonée pour ne pas entraîner les éléments qui partagent l'image sans défiler.
  const scrolling: { texture: THREE.Texture; original: THREE.Texture; material: THREE.MeshBasicMaterial;
    offset: THREE.Vector2; speed: THREE.Vector2 }[] = [];
  const animated = new Set<THREE.Material>();
  for (const mesh of meshes) {
    const speed = mesh.geometry.userData.uvScroll as number[] | undefined;
    const material = mesh.material;
    if (!material.map || !speed || (!speed[0] && !speed[1]) || animated.has(material)) continue;
    animated.add(material);
    const original = material.map;
    const texture = original.clone();
    texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
    texture.needsUpdate = true;
    material.map = texture;
    scrolling.push({ texture, original, material, offset: texture.offset.clone(), speed: new THREE.Vector2(speed[0], speed[1]) });
  }
  return {
    count: meshes.length,
    update(time: number, reduced: boolean) {
      const elapsed = reduced ? 0 : time;
      // `uv += vitesse × t`. Sens de v : toutes les vapeurs (cascade 0,2, statue 0,04 et
      // 0,05) et les braises (0,3) ont une vitesse v positive dans le xdb, réglée par
      // les artistes pour monter dans le client ; avec la texture retournée par
      // `prepareTexture` (repeat.y = -1), un contenu qui monte correspond à un
      // décalage v croissant. Le sens de u (nuages, faisceau, cascade aux UV
      // tournées) n'est pas vérifiable sans capture animée du client.
      for (const { texture, offset, speed } of scrolling) {
        texture.offset.set(offset.x + (elapsed * speed.x) % 1, offset.y + (elapsed * speed.y) % 1);
      }
    },
    dispose() {
      for (const { texture, original, material } of scrolling) {
        material.map = original;
        texture.dispose();
      }
    },
  };
}
