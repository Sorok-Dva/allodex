import * as THREE from 'three';

/**
 * Brouillard du moteur. Tous les matériaux 5.0 portent `useFog: true` : dans le client,
 * la tour, l'arbre et les nappes de nuages se fondent avec la distance dans une brume
 * bleu-violet, et le fond de la coupole de nuages (`Back6`, 150 à 300 unités) s'unifie.
 * Sans lui, l'export montre des silhouettes noires et des facettes de polygones que le
 * jeu noie. La couleur et les distances ne sont pas dans les xdb (elles viennent du
 * client) : la couleur est celle du fond de scène du manifeste, les distances sont calées
 * sur la capture `refs/captures-ui/menu-5.0-frame1.png` — c'est un réglage, pas une donnée.
 *
 * Les matériaux additifs (halos, éclairs, faisceaux) ne reçoivent pas de brouillard :
 * Direct3D fond une lueur additive vers le noir, three.js l'éclaircirait vers la brume.
 */
export const FOG_NEAR = 30;
export const FOG_FAR = 450;

export function applyV5Fog(root: THREE.Object3D, color: THREE.ColorRepresentation) {
  const scene = root.parent as THREE.Scene | null;
  if (!scene || !(scene as THREE.Scene).isScene) return { count: 0, dispose() {} };
  const previous = scene.fog;
  scene.fog = new THREE.Fog(color, FOG_NEAR, FOG_FAR);
  const touched: THREE.MeshBasicMaterial[] = [];
  root.traverse(object => {
    const mesh = object as THREE.Mesh;
    if (!mesh.isMesh || Array.isArray(mesh.material)) return;
    const material = mesh.material as THREE.MeshBasicMaterial;
    if (material.blending === THREE.AdditiveBlending || material.fog) return;
    material.fog = true;
    material.needsUpdate = true;
    touched.push(material);
  });
  return {
    count: touched.length,
    dispose() {
      for (const material of touched) { material.fog = false; material.needsUpdate = true; }
      scene.fog = previous;
    },
  };
}

/**
 * Sommets à alpha nul. Les seize pièces de la coque du navire de raid et les rochers
 * flottants (`Allods*`) portent une couleur de sommet dont l'alpha vaut 0 partout : le
 * client ne mélange pas ces matériaux (`transparent: false` pour la coque) et ignore cette
 * composante ; le lecteur générique — tout en mélange alpha, couleurs de sommet actives —
 * les rendrait invisibles. On coupe la couleur de sommet (leur teinte est blanche) et on
 * les rend opaques, avec le tampon de profondeur pour trier les pièces de la coque entre elles.
 */
export function restoreOpaqueVertexAlpha(root: THREE.Object3D) {
  const restored: THREE.MeshBasicMaterial[] = [];
  root.traverse(object => {
    const mesh = object as THREE.Mesh;
    if (!mesh.isMesh || Array.isArray(mesh.material)) return;
    const color = mesh.geometry.getAttribute('color');
    if (!color || color.itemSize < 4) return;
    const index = mesh.geometry.getIndex();
    const count = index ? index.count : color.count;
    let visible = false;
    for (let i = 0; i < count && !visible; i += 1) {
      visible = color.getW(index ? index.getX(i) : i) > 0;
    }
    if (visible) return;
    const material = mesh.material as THREE.MeshBasicMaterial;
    material.vertexColors = false;
    material.transparent = false;
    material.depthTest = true;
    material.depthWrite = true;
    material.needsUpdate = true;
    restored.push(material);
  });
  return {
    count: restored.length,
    dispose() {
      for (const material of restored) {
        material.vertexColors = true; material.transparent = true;
        material.depthTest = false; material.depthWrite = false; material.needsUpdate = true;
      }
    },
  };
}
