import * as THREE from 'three';

/**
 * `Sky_Back`, le dôme de fond, est un matériau **non transparent** du xdb dont toutes les
 * couleurs de sommet ont un alpha nul : le client ignore l'alpha de ces matériaux et ne
 * garde que la teinte (gris-vert sombre au ras du sol, rose et bleu en hauteur — c'est ce
 * fond de vallée pâle que montre la capture du menu). three.js, lui, multiplie l'alpha du
 * fragment par celui de `COLOR_0` : le dôme disparaîtrait et la couleur de fond du canvas
 * apparaîtrait entre les nappes de prairie. On ne modifie que le shader des primitives
 * dont **tous** les sommets indexés ont un alpha nul — un élément entièrement invisible
 * n'a pas été peint pour l'être — en n'appliquant plus que le RGB de la couleur de sommet.
 *
 * Renvoie le nombre de primitives corrigées.
 */
export function restoreOpaqueVertexAlpha(root: THREE.Object3D): number {
  let count = 0;
  root.traverse(object => {
    const mesh = object as THREE.Mesh;
    if (!mesh.isMesh || Array.isArray(mesh.material) || !hasZeroVertexAlpha(mesh.geometry)) return;
    // Le matériau peut être partagé avec un élément qui garde son alpha : on le clone.
    const material = (mesh.material as THREE.MeshBasicMaterial).clone();
    material.onBeforeCompile = shader => { shader.fragmentShader = ignoreVertexAlpha(shader.fragmentShader); };
    material.customProgramCacheKey = () => 'v6-opaque-vertex-alpha';
    material.needsUpdate = true;
    mesh.material = material;
    count += 1;
  });
  return count;
}

/** Le bloc `color_fragment` de three.js réécrit pour ne multiplier que le RGB. */
export const RGB_ONLY_COLOR_FRAGMENT =
  '#if defined( USE_COLOR_ALPHA ) || defined( USE_COLOR )\n\tdiffuseColor.rgb *= vColor.rgb;\n#endif';

/** Remplace, dans le fragment shader de three.js, la multiplication par `vColor` (vec4) par sa
 * seule partie RGB. `onBeforeCompile` reçoit le shader avant l'expansion des `#include` : c'est
 * l'include qu'on remplace ; la forme déjà expansée est couverte aussi. */
export function ignoreVertexAlpha(fragmentShader: string): string {
  return fragmentShader
    .replace('#include <color_fragment>', RGB_ONLY_COLOR_FRAGMENT)
    .replace('diffuseColor *= vColor;', 'diffuseColor.rgb *= vColor.rgb;');
}

/** `true` si la géométrie porte une couleur à 4 composantes dont l'alpha est nul sur chaque
 * sommet référencé par l'index. */
export function hasZeroVertexAlpha(geometry: THREE.BufferGeometry): boolean {
  const color = geometry.getAttribute('color');
  if (!color || color.itemSize < 4) return false;
  const used = geometry.index ? geometry.index.array : null;
  const count = used ? used.length : color.count;
  if (count === 0) return false;
  for (let k = 0; k < count; k += 1) {
    if (color.getW(used ? used[k] : k) !== 0) return false;
  }
  return true;
}
