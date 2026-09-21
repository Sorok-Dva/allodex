import type * as THREE from 'three';
import type { SceneEffects } from '../effects';
import { applyV5Fog, restoreOpaqueVertexAlpha } from './v5Atmosphere';
import { prepareV5Scroll, prepareV5Ship, type FixedCamera } from './v5SceneLayers';

/**
 * Scène 5.0 : tout vient du `.glb` (géométries, textures, matériaux et les deux animations
 * squelettiques natives — décor et navire de raid). Le lecteur n'ajoute que ce que le
 * client calcule à l'exécution : le brouillard, le défilement UV, l'ordre de rendu du
 * navire mobile, et la remise à l'opaque des sommets à alpha nul.
 */
export function createV5Effects(root: THREE.Object3D, camera: FixedCamera, fogColor: THREE.ColorRepresentation): SceneEffects {
  const opaque = restoreOpaqueVertexAlpha(root);
  const fog = applyV5Fog(root, fogColor);
  const scroll = prepareV5Scroll(root);
  const ship = prepareV5Ship(root, camera);
  return {
    update(time: number, reduced = false) {
      scroll.update(time, reduced);
      ship.update();
    },
    dispose() {
      scroll.dispose();
      fog.dispose();
      opaque.dispose();
    },
  };
}
