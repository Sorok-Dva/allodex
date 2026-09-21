import type * as THREE from 'three';

/**
 * Ordre de rendu natif de la 4.0 : `sortMode OFFSETS` dans `Animated_Background.(Geometry).xdb`.
 *
 * Le décor est un seul maillage dont les éléments sont rangés dans l'index buffer de
 * l'arrière vers l'avant par l'auteur : le dôme de ciel (Back2, Back3), les nuages du
 * fond, l'île, le soleil, le château, la brume, les oiseaux, puis les nuages de premier
 * plan. Le moteur les peint dans cet ordre, sans se soucier de leur profondeur : le soleil
 * (additif) est ainsi peint *avant* le château qui le recouvre, alors qu'il est plus près
 * de la caméra ; le dôme, qui entoure la caméra, passe en premier alors que sa profondeur
 * moyenne le placerait au-dessus de l'île — c'était le « voile » rose.
 *
 * L'exportateur conserve cet ordre : une primitive glTF par élément, dans l'ordre du
 * fichier, et `GLTFLoader` en fait autant de maillages enfants du même groupe. On pose
 * donc en `renderOrder` le rang de chaque maillage parmi ses frères, à la place du tri
 * par profondeur moyenne du lecteur générique.
 */
export function prepareV4Layers(root: THREE.Object3D): void {
  root.traverse(object => {
    const meshes = object.children.filter(child => (child as THREE.Mesh).isMesh);
    meshes.forEach((mesh, index) => { mesh.renderOrder = index; });
  });
}
