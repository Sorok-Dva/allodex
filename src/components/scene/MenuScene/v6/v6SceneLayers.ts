import type * as THREE from 'three';

/** Premier `renderOrder` attribué : au-dessus des valeurs de `sortByDepth` (négatives). */
export const NATIVE_ORDER_BASE = 0;

/**
 * La 6.0 est un unique maillage dont les `modelElements` sont rangés dans le xdb du fond
 * vers l'avant : ciel, nuages, montagnes, pylônes, rochers, versant `Mountains_04`,
 * laboratoire, voie, maisons, rayons, train, arbres. C'est cet ordre-là que le client
 * peint — le tri par profondeur moyenne mettrait le versant (qui s'étend en avant du
 * laboratoire) par-dessus la coupole. L'export garde cet ordre dans les primitives du
 * glTF, `GLTFLoader` dans les enfants du groupe : on le pose en `renderOrder`.
 *
 * Renvoie le nombre de primitives ordonnées.
 */
export function applyNativeDrawOrder(root: THREE.Object3D): number {
  let count = 0;
  root.traverse(object => {
    const primitives = object.children.filter(child => {
      const mesh = child as THREE.Mesh;
      return mesh.isMesh && mesh.geometry?.userData?.element !== undefined;
    });
    if (primitives.length < 2) return;
    primitives.forEach((mesh, index) => { mesh.renderOrder = NATIVE_ORDER_BASE + index; });
    count += primitives.length;
  });
  return count;
}
