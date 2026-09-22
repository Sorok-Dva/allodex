import * as THREE from 'three';

/** Drapeaux de matériau d'une primitive, relevés dans le Geometry xdb par `tools/scenes/v5_0.py`. */
export type V5Material = { element: string; blend: 'alpha' | 'add'; transparent: boolean };

/**
 * Seuil du test d'alpha des matériaux non mélangés. Le xdb ne porte pas la référence du
 * test (`alphaTex: true` sur la texture, sans valeur) : la moitié est un réglage.
 */
export const ALPHA_TEST = 0.5;

/**
 * Matériaux **non mélangés** du client. Le lecteur générique rend tout en mélange alpha,
 * sans tampon de profondeur ; or le xdb distingue les matériaux `transparent` (nuages,
 * feuillages, halos : mélange alpha ou additif, alpha de sommet actif) des autres — fûts
 * et flèche de la tour (`Tower_01`), sabres, bielles, écorces, coque du navire de raid,
 * coupole `Back6` — que le client peint sans mélange : la texture est découpée par son
 * canal alpha (test), la couleur de sommet ne module que le RGB, et la profondeur est
 * écrite (les seize pièces de la coque se recouvrent correctement entre elles). Sans
 * cela, l'alpha de sommet nul de la coque la rendrait invisible et les fûts de la tour
 * se mélangeraient aux nuages qu'ils masquent.
 *
 * Les primitives d'un objet sont retrouvées par leur rang parmi les enfants du groupe
 * `<objet>_mesh` de `GLTFLoader`, dans l'ordre du fichier — le même que `read_materials`.
 */
export function applyV5Materials(root: THREE.Object3D, materials: Record<string, V5Material[]> | undefined) {
  const touched: THREE.MeshBasicMaterial[] = [];
  for (const [object, flags] of Object.entries(materials ?? {})) {
    const group = root.getObjectByName(`${object}_mesh`);
    if (!group) continue;
    const meshes = group.children.filter(child => (child as THREE.Mesh).isMesh) as THREE.Mesh[];
    if (meshes.length !== flags.length) continue; // export et méta désaccordés : on ne devine pas
    meshes.forEach((mesh, index) => {
      if (Array.isArray(mesh.material)) return;
      const material = mesh.material as THREE.MeshBasicMaterial;
      if (flags[index].transparent) {
        // Mélangé : comme Direct3D, testé contre la profondeur écrite par les matériaux
        // opaques (la sphère de fumée du navire, peinte après sa coque, reste derrière elle),
        // sans l'écrire.
        material.depthTest = true;
        material.needsUpdate = true;
        touched.push(material);
        return;
      }
      material.transparent = false;
      material.blending = THREE.NormalBlending;
      material.alphaTest = ALPHA_TEST;
      material.depthTest = true;
      material.depthWrite = true;
      material.onBeforeCompile = shader => { shader.fragmentShader = ignoreVertexAlpha(shader.fragmentShader); };
      material.customProgramCacheKey = () => 'v5-unblended';
      material.needsUpdate = true;
      touched.push(material);
    });
  }
  return {
    count: touched.length,
    dispose() {
      for (const material of touched) {
        material.transparent = true; material.alphaTest = 0;
        material.depthTest = false; material.depthWrite = false;
        material.onBeforeCompile = () => {}; material.customProgramCacheKey = () => '';
        material.needsUpdate = true;
      }
    },
  };
}

/** Le bloc `color_fragment` de three.js réécrit pour ne multiplier que le RGB (comme en 6.0). */
export const RGB_ONLY_COLOR_FRAGMENT =
  '#if defined( USE_COLOR_ALPHA ) || defined( USE_COLOR )\n\tdiffuseColor.rgb *= vColor.rgb;\n#endif';

export function ignoreVertexAlpha(fragmentShader: string): string {
  return fragmentShader
    .replace('#include <color_fragment>', RGB_ONLY_COLOR_FRAGMENT)
    .replace(/#if defined\( USE_COLOR_ALPHA \)\s*diffuseColor \*= vColor;\s*#elif defined\( USE_COLOR \)\s*diffuseColor\.rgb \*= vColor;\s*#endif/,
      RGB_ONLY_COLOR_FRAGMENT);
}
