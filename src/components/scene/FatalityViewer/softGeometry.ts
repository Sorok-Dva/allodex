import * as THREE from 'three';

/**
 * « Géométrie douce » des effets du jeu : les matériaux dont la texture d'environnement est un
 * `SoftGeometryGrain*` (disque d'alpha, flou sur le bord) lisent cette texture à la normale vue
 * de la caméra (`n.xy · ½ + ½`, comme une carte sphérique) et en multiplient leur alpha. Une
 * surface vue de face garde son alpha, une surface vue par la tranche s'efface : les colonnes
 * et halos cylindriques (`Glow_Big` de l'Occultiste…) perdent leurs bords durs. Les variantes
 * `Contur` (anneau) et `Inverse` (bord seul) passent par le même calcul.
 */
export function applySoftGeometry(material: THREE.Material, mask: THREE.Texture): void {
  material.onBeforeCompile = shader => {
    shader.uniforms.softMask = { value: mask };
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vSoftNormal;')
      .replace('#include <project_vertex>', `#include <project_vertex>
#if defined( USE_ENVMAP ) || defined( USE_SKINNING )
  vSoftNormal = normalize( transformedNormal );
#else
  vSoftNormal = normalize( normalMatrix * normal );
#endif`);
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', '#include <common>\nuniform sampler2D softMask;\nvarying vec3 vSoftNormal;')
      .replace('#include <alphamap_fragment>', `#include <alphamap_fragment>
  vec3 softN = normalize( vSoftNormal );
  diffuseColor.a *= texture2D( softMask, softN.xy * 0.5 + 0.5 ).a;`);
  };
  material.customProgramCacheKey = () => 'soft-geometry';
  material.needsUpdate = true;
}

/** Charge (une fois par URL) les masques de géométrie douce. */
export class SoftMaskCache {
  private readonly cache = new Map<string, THREE.Texture>();
  private readonly loader = new THREE.TextureLoader();

  get(url: string): THREE.Texture {
    let texture = this.cache.get(url);
    if (!texture) {
      texture = this.loader.load(url);
      texture.colorSpace = THREE.NoColorSpace;
      this.cache.set(url, texture);
    }
    return texture;
  }

  dispose(): void {
    for (const texture of this.cache.values()) texture.dispose();
    this.cache.clear();
  }
}
