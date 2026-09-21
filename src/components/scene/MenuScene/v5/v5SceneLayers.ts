import * as THREE from 'three';

/**
 * Défilement UV natif des matériaux 5.0 (`uTranslateSpeed`/`vTranslateSpeed` exportés en
 * `extras.uvScroll`) : lueur qui monte le long de la tour (`Tower_blink`), faisceaux des
 * phares (`Mayak_*`), éclairs (`lightning_*`, un tour de texture par seconde), rayons du
 * soleil, dômes et voiles du navire de raid. Chaque matériau qui défile reçoit sa propre
 * copie de texture : la texture `BackCloud` est partagée par les nuages fixes et par la
 * traînée du navire, elle ne doit pas bouger pour tous.
 *
 * Le sens du défilement suit les UV du fichier (pas d'inversion V dans le lecteur 5.0).
 */
export function prepareV5Scroll(root: THREE.Object3D) {
  const scrolling: { texture: THREE.Texture; original: THREE.Texture; material: THREE.MeshBasicMaterial;
    offset: THREE.Vector2; speed: THREE.Vector2 }[] = [];
  const animated = new Set<THREE.Material>(); // un matériau partagé ne défile qu'une fois
  root.traverse(object => {
    const mesh = object as THREE.Mesh;
    if (!mesh.isMesh || Array.isArray(mesh.material)) return;
    const speed = mesh.geometry.userData.uvScroll as number[] | undefined;
    const material = mesh.material as THREE.MeshBasicMaterial;
    if (!material.map || !speed || (!speed[0] && !speed[1]) || animated.has(material)) return;
    animated.add(material);
    const original = material.map;
    const texture = original.clone();
    texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
    texture.needsUpdate = true;
    material.map = texture;
    scrolling.push({ texture, original, material, offset: texture.offset.clone(),
      speed: new THREE.Vector2(speed[0], speed[1]) });
  });
  return {
    count: scrolling.length,
    update(time: number, reduced: boolean) {
      const elapsed = reduced ? 0 : time;
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

/** Caméra fixe du méta : origine et direction de visée, pour mesurer une profondeur. */
export type FixedCamera = { position: number[]; target: number[] };

/**
 * Le navire de raid traverse toute la scène : devant la tour à son premier passage, loin
 * derrière elle au second. Or le lecteur classe les primitives une fois pour toutes, à
 * t = 0, quand le navire n'est encore qu'un point sur son locator. On recalcule donc à
 * chaque image son rang de rendu d'après la profondeur courante de son articulation
 * racine — le même critère (`-profondeur`) que `sortByDepth`, pour rester classé parmi
 * les autres primitives. L'ordre relatif de ses pièces (coque, puis dômes et voiles
 * additifs, traînées) est conservé.
 */
export function prepareV5Ship(root: THREE.Object3D, camera: FixedCamera) {
  const ship = root.getObjectByName('Raid_Ship');
  const bone = findByNodeName(root, 'Raid_Ship/Ship');
  const eye = new THREE.Vector3().fromArray(camera.position);
  const forward = new THREE.Vector3().fromArray(camera.target).sub(eye).normalize();
  const meshes: THREE.Mesh[] = [];
  ship?.traverse(object => {
    const mesh = object as THREE.Mesh;
    if (mesh.isMesh) meshes.push(mesh);
  });
  meshes.sort((a, b) => a.renderOrder - b.renderOrder);
  const rank = new Map(meshes.map((mesh, index) => [mesh, index / Math.max(meshes.length, 1)]));
  const point = new THREE.Vector3();
  return {
    count: meshes.length,
    update() {
      if (!bone || !meshes.length) return;
      bone.updateWorldMatrix(true, false);
      const depth = point.setFromMatrixPosition(bone.matrixWorld).sub(eye).dot(forward);
      for (const mesh of meshes) mesh.renderOrder = -depth + (rank.get(mesh) ?? 0);
    },
  };
}

/** `GLTFLoader` retire les `/` des noms de nœuds (`Raid_Ship/Ship` → `Raid_ShipShip`). */
export function findByNodeName(root: THREE.Object3D, name: string) {
  return root.getObjectByName(name) ?? root.getObjectByName(THREE.PropertyBinding.sanitizeNodeName(name));
}
