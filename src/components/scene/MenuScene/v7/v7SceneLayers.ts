import * as THREE from 'three';

/** Le décor est peint en calques : la profondeur moyenne de ses polygones ne
 * représente pas le plan narratif du navire ou du halo qui leur appartient. */
/** Le jet d'énergie d'Engine_Direct est une nappe de fumée qui boucle. Le client
 * l'exporte à un tour de texture par seconde : ses taches traversent le réacteur
 * en saccades. Ramenée au rythme du brouillard (0,01 à 0,05 tuile/s), la même
 * texture donne une poussée continue qui sort du réacteur sans varier de forme. */
export const ENGINE_SCROLL_FACTOR = .15;

export function prepareV7Layers(root: THREE.Object3D) {
  const front = root.getObjectByName('AMM_7_0_FrontShips');
  const distant = root.getObjectByName('AMM_7_0_Ships_Attack');
  const stones = ['AMM_7_0_Stones_01', 'AMM_7_0_Stones_02'].map(name => root.getObjectByName(name));
  if (distant) {
    distant.scale.multiplyScalar(.82);
    distant.position.y -= 50;
  }
  const groups = new Map<number, THREE.Mesh[]>();
  const scrolling: { texture: THREE.Texture; original: THREE.Texture; material: THREE.MeshBasicMaterial;
    offset: THREE.Vector2; speed: THREE.Vector2 }[] = [];
  const animated = new Set<THREE.Material>(); // un matériau partagé ne défile qu'une fois
  function belongsTo(object: THREE.Object3D, parent: THREE.Object3D | undefined) {
    if (!parent) return false;
    for (let current: THREE.Object3D | null = object; current; current = current.parent) {
      if (current === parent) return true;
    }
    return false;
  }
  root.traverse(object => {
    const mesh = object as THREE.Mesh;
    if (!mesh.isMesh || Array.isArray(mesh.material)) return;
    const element = String(mesh.geometry.userData.element ?? '');
    const engine = element.startsWith('Engine_');
    const rearGlow = element.startsWith('Engine_Back');
    const mist = element.startsWith('Front_Myst');
    let band = 0;
    if (belongsTo(mesh, distant)) band = rearGlow ? 180 : engine ? 240 : 200;
    else if (belongsTo(mesh, front)) band = rearGlow ? 280 : engine ? 340 : mist ? 330 : 300;
    else if (stones.some(parent => belongsTo(mesh, parent))) band = 150;
    const group = groups.get(band) ?? [];
    group.push(mesh); groups.set(band, group);

    const speed = mesh.geometry.userData.uvScroll as number[] | undefined;
    const material = mesh.material as THREE.MeshBasicMaterial;
    if (!material.map || !speed || (!speed[0] && !speed[1]) || animated.has(material)) return;
    animated.add(material);
    // Les calques partagent souvent une image, mais pas leur vitesse de défilement.
    // Une texture indépendante évite d'entraîner le paysage ou de cumuler les offsets.
    const original = material.map;
    const texture = original.clone();
    texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
    texture.needsUpdate = true;
    material.map = texture;
    const factor = engine ? ENGINE_SCROLL_FACTOR : 1;
    scrolling.push({ texture, original, material, offset: texture.offset.clone(),
      speed: new THREE.Vector2(speed[0] * factor, speed[1] * factor) });
  });
  for (const [band, meshes] of groups) {
    meshes.sort((a, b) => a.renderOrder - b.renderOrder);
    meshes.forEach((mesh, index) => { mesh.renderOrder = band + index / Math.max(meshes.length, 1) * 20; });
  }
  return {
    update(time: number, reduced: boolean) {
      const elapsed = reduced ? 0 : time;
      for (const { texture, offset, speed } of scrolling) {
        texture.offset.set(offset.x + (elapsed * speed.x) % 1,
          offset.y - (elapsed * speed.y) % 1); // UV verticales inversées par le lecteur V7
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
