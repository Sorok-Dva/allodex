import * as THREE from 'three';

/** Les halos et traînées des réacteurs sont exportés en maillages skinnés : le
 * squelette animé des navires les déforme à chaque image, alors que dans le client
 * la lueur est un aplat continu qui suit la coque sans changer de forme. On fige
 * chaque couche `Engine_` dans sa pose de départ et on la rattache en bloc au nœud
 * racine de son navire, qui porte le tangage de la coque. */
export function freezeEngineTrails(root: THREE.Object3D) {
  const destroyed = root.getObjectByName('AMM_7_0_Ships_Destroyed');
  const skinned: THREE.SkinnedMesh<THREE.BufferGeometry, THREE.Material>[] = [];
  root.traverse(object => {
    const mesh = object as THREE.SkinnedMesh<THREE.BufferGeometry, THREE.Material>;
    if (!mesh.isSkinnedMesh || !String(mesh.geometry.userData.element ?? '').startsWith('Engine_')) return;
    if (destroyed && belongsTo(mesh, destroyed)) return; // l'intro reconstruit déjà ces coques
    if (!mesh.geometry.getAttribute('skinIndex')) return;
    skinned.push(mesh);
  });
  root.updateMatrixWorld(true);
  const frozen: { mesh: THREE.SkinnedMesh; rigid: THREE.Mesh }[] = [];
  for (const mesh of skinned) {
    const anchor = shipRoot(dominantBone(mesh), root);
    mesh.skeleton.update(); // les matrices d'os ne sont calculées qu'au rendu
    const geometry = mesh.geometry.clone();
    geometry.deleteAttribute('skinIndex'); geometry.deleteAttribute('skinWeight');
    const position = geometry.getAttribute('position') as THREE.BufferAttribute;
    const vertex = new THREE.Vector3();
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

function belongsTo(object: THREE.Object3D, parent: THREE.Object3D) {
  for (let current: THREE.Object3D | null = object; current; current = current.parent) if (current === parent) return true;
  return false;
}

/** L'os qui pèse le plus sur la couche ; la racine du navire en découle. Les
 * primitives d'un même maillage glTF partagent leurs tampons de sommets : seuls
 * ceux que l'index de la couche référence comptent. */
function dominantBone(mesh: THREE.SkinnedMesh) {
  const index = mesh.geometry.getAttribute('skinIndex');
  const weight = mesh.geometry.getAttribute('skinWeight');
  const used = mesh.geometry.index ? new Set(Array.from(mesh.geometry.index.array)) : null;
  const totals = new Map<number, number>();
  for (let i = 0; i < index.count; i += 1) {
    if (used && !used.has(i)) continue;
    for (let k = 0; k < 4; k += 1) {
      const w = weight.getComponent(i, k);
      if (w > 0) totals.set(index.getComponent(i, k), (totals.get(index.getComponent(i, k)) ?? 0) + w);
    }
  }
  let best = 0, bestWeight = -1;
  for (const [bone, total] of totals) if (total > bestWeight) { best = bone; bestWeight = total; }
  return mesh.skeleton.bones[best] ?? mesh;
}

/** Remonte jusqu'au nœud du navire (enfant direct de `VisualSceneNode` ou du groupe). */
function shipRoot(node: THREE.Object3D, root: THREE.Object3D) {
  let current = node;
  while (current.parent && current.parent !== root && !/VisualSceneNode$/.test(current.parent.name)
    && !/^AMM_7_0_[A-Za-z]+$/.test(current.parent.name.split('/').pop() ?? '')) current = current.parent;
  return current;
}
