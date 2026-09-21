import * as THREE from 'three';

/** Index, dans le squelette, de l'os « par défaut » des sommets sans influence (`joint5_joint6`). */
export const DEFAULT_JOINT = 0;

/**
 * Tout le décor 6.0 (ciel, montagnes, laboratoire, voie…) est skinné à poids 1 sur l'os 0,
 * une articulation du drapeau : un défaut d'export Maya (sommets sans influence rattachés
 * au premier os) qui ferait osciller le paysage entier au rythme du drapeau, alors que le
 * client montre un décor immobile. On fige donc chaque primitive dont **tous** les sommets
 * indexés ne dépendent que de cet os : copie rigide dans sa pose de départ (identique à la
 * géométrie stockée), rattachée au même parent, et l'original skinné est masqué. Drapeau,
 * arbres et train — skinnés sur leurs propres os — restent animés par le mixeur.
 */
export function freezeLandscape(root: THREE.Object3D) {
  const skinned: THREE.SkinnedMesh<THREE.BufferGeometry, THREE.Material>[] = [];
  root.traverse(object => {
    const mesh = object as THREE.SkinnedMesh<THREE.BufferGeometry, THREE.Material>;
    if (!mesh.isSkinnedMesh || !boundToDefaultJointOnly(mesh.geometry)) return;
    skinned.push(mesh);
  });
  root.updateMatrixWorld(true);
  const frozen: { mesh: THREE.SkinnedMesh; rigid: THREE.Mesh }[] = [];
  const vertex = new THREE.Vector3();
  for (const mesh of skinned) {
    const anchor = mesh.parent ?? root;
    mesh.skeleton.update(); // les matrices d'os ne sont calculées qu'au rendu
    const geometry = mesh.geometry.clone();
    geometry.deleteAttribute('skinIndex'); geometry.deleteAttribute('skinWeight');
    const position = geometry.getAttribute('position') as THREE.BufferAttribute;
    for (let i = 0; i < position.count; i += 1) {
      mesh.getVertexPosition(i, vertex);
      mesh.localToWorld(vertex);
      anchor.worldToLocal(vertex);
      position.setXYZ(i, vertex.x, vertex.y, vertex.z);
    }
    position.needsUpdate = true;
    geometry.computeBoundingBox(); geometry.computeBoundingSphere();
    const rigid = new THREE.Mesh(geometry, mesh.material);
    rigid.name = mesh.name; rigid.renderOrder = mesh.renderOrder; rigid.frustumCulled = false;
    anchor.add(rigid);
    mesh.visible = false;
    frozen.push({ mesh, rigid });
  }
  return {
    count: frozen.length,
    dispose() {
      for (const { mesh, rigid } of frozen) {
        rigid.removeFromParent(); rigid.geometry.dispose(); mesh.visible = true;
      }
    },
  };
}

/** `true` si chaque sommet référencé par l'index ne pèse que sur l'os par défaut. */
export function boundToDefaultJointOnly(geometry: THREE.BufferGeometry): boolean {
  const index = geometry.getAttribute('skinIndex');
  const weight = geometry.getAttribute('skinWeight');
  if (!index || !weight) return false;
  const used = geometry.index ? geometry.index.array : null;
  const count = used ? used.length : index.count;
  for (let k = 0; k < count; k += 1) {
    const i = used ? used[k] : k;
    for (let slot = 0; slot < 4; slot += 1) {
      if (weight.getComponent(i, slot) > 0 && index.getComponent(i, slot) !== DEFAULT_JOINT) return false;
    }
  }
  return true;
}
