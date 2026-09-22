import * as THREE from 'three';

/**
 * Ordre de peinture natif : `sortMode OFFSETS` dans les deux Geometry xdb de la 5.0 (relevé
 * dans `scene.json` par `tools/scenes/v5_0.py`). Comme en 4.0, le moteur peint les éléments
 * d'un objet dans l'ordre du fichier, sans tri par profondeur : coupole `Back6`, calques
 * de fond, rochers, tour, arbres, brumes, nuages de premier plan, lanternes et lueur de la
 * tour en dernier. Le tri par profondeur moyenne du lecteur générique ferait passer les
 * grandes nappes de brume (centrées loin derrière) sous la tour qu'elles doivent voiler.
 *
 * Chaque primitive reçoit son rang parmi ses frères ; l'objet suivant (le navire, attaché)
 * repart du rang de son propre groupe — `prepareV5Ship` le reclasse à chaque image.
 */
export function prepareV5Layers(root: THREE.Object3D): number {
  let count = 0;
  root.traverse(object => {
    const meshes = object.children.filter(child => (child as THREE.Mesh).isMesh);
    meshes.forEach((mesh, index) => { mesh.renderOrder = index; count += 1; });
  });
  return count;
}

/**
 * Défilement UV natif des matériaux 5.0 (`uTranslateSpeed`/`vTranslateSpeed` exportés en
 * `extras.uvScroll`) : lueur qui monte le long de la tour (`Tower_blink`), faisceaux des
 * phares (`Mayak_*`), éclairs (`lightning_*`, un tour de texture par seconde), rayons du
 * soleil, coupole de nuages (`Back6`, 0,005 tour/s), dômes et voiles du navire de raid.
 * Chaque matériau qui défile reçoit sa propre copie de texture : la texture `BackCloud`
 * est partagée par les nuages fixes et par la traînée du navire, elle ne doit pas bouger
 * pour tous.
 *
 * Les textures du client ont leur origine en bas (`prepareTexture` les retourne avec
 * `repeat.y = -1`) : un défilement V positif du xdb déplace donc l'`offset.y` de three.js
 * dans le sens de `repeat.y`.
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
        texture.offset.set(
          offset.x + Math.sign(texture.repeat.x || 1) * ((elapsed * speed.x) % 1),
          offset.y + Math.sign(texture.repeat.y || 1) * ((elapsed * speed.y) % 1),
        );
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
 * Le navire de raid est un objet attaché, hors de l'ordre de peinture du décor. Sa piste
 * le fait naître derrière la tour (X ≈ −73 à −87, la caméra étant en X = +27), balayer le
 * fond, puis revenir grandir au premier plan et croiser le plan de la caméra vers 80 s.
 * On le peint donc, à chaque image, juste **avant** la tour quand son articulation racine
 * est plus loin qu'elle, et **après** tout le décor quand elle est plus près — les deux
 * seuls cas que montrent les captures du client. L'ordre relatif de ses pièces (coque,
 * puis dômes et voiles additifs, traînées) est conservé.
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
  // Le décor : rang de sa première pièce de tour et rang de sa dernière primitive.
  const shipSet = new Set(meshes);
  let towerOrder = Infinity;
  let lastOrder = -Infinity;
  let towerDepth = 0;
  let towerSamples = 0;
  const point = new THREE.Vector3();
  root.updateMatrixWorld(true);
  root.traverse(object => {
    const mesh = object as THREE.Mesh;
    if (!mesh.isMesh || shipSet.has(mesh)) return;
    lastOrder = Math.max(lastOrder, mesh.renderOrder);
    if (!TOWER_ELEMENTS.has(mesh.geometry.userData.element as string)) return;
    towerOrder = Math.min(towerOrder, mesh.renderOrder);
    const position = mesh.geometry.getAttribute('position');
    for (let i = 0; i < position.count; i += 1) {
      towerDepth += point.fromBufferAttribute(position, i).applyMatrix4(mesh.matrixWorld).sub(eye).dot(forward);
      towerSamples += 1;
    }
  });
  towerDepth = towerSamples ? towerDepth / towerSamples : 0;
  if (!Number.isFinite(towerOrder)) towerOrder = lastOrder + 1;
  return {
    count: meshes.length,
    towerDepth,
    update() {
      if (!bone || !meshes.length) return;
      bone.updateWorldMatrix(true, false);
      const depth = point.setFromMatrixPosition(bone.matrixWorld).sub(eye).dot(forward);
      // Derrière : entre l'élément qui précède la tour et la tour ; devant : après tout.
      const behind = depth > towerDepth;
      const base = behind ? towerOrder - 0.5 : lastOrder + 1;
      const span = behind ? 0.5 : 1;
      for (const mesh of meshes) mesh.renderOrder = base + span * (rank.get(mesh) ?? 0);
    },
  };
}

/** Éléments du xdb qui forment la tour-phare (fûts, flèche, roue, cristal, base). */
export const TOWER_ELEMENTS = new Set(['Occlud', 'Tower_Up', 'Tower', 'Tower3', 'Tower_Crystall', 'Sabres', 'Cylinders']);

/** `GLTFLoader` retire les `/` des noms de nœuds (`Raid_Ship/Ship` → `Raid_ShipShip`). */
export function findByNodeName(root: THREE.Object3D, name: string) {
  return root.getObjectByName(name) ?? root.getObjectByName(THREE.PropertyBinding.sanitizeNodeName(name));
}
