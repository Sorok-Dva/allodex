import type * as THREE from 'three';
import type { SceneMeta } from '@/lib/assets';
import type { SceneEffects } from '../effects';
import { applyV5Materials, type V5Material } from './v5Materials';
import { prepareV5Layers, prepareV5Scroll, prepareV5Ship } from './v5SceneLayers';

/** `scene.json` de la 5.0 : le méta générique plus ce que dépose `tools/scenes/v5_0.py`. */
export type V5Meta = SceneMeta & { sortMode?: string; materials?: Record<string, V5Material[]> };

/**
 * Scène 5.0 : tout vient du `.glb` (géométries, textures, matériaux et les deux animations
 * squelettiques natives — décor et navire de raid) et du `scene.json` (ordre de peinture et
 * drapeaux de matériau du xdb). Le lecteur n'ajoute que ce que le client calcule à
 * l'exécution : le défilement UV et le rang de rendu du navire mobile.
 */
export function createV5Effects(root: THREE.Object3D, meta: V5Meta): SceneEffects {
  const materials = applyV5Materials(root, meta.materials);
  if (meta.sortMode === 'OFFSETS') prepareV5Layers(root);
  const scroll = prepareV5Scroll(root);
  const ship = prepareV5Ship(root, meta.camera);
  return {
    update(time: number, reduced = false) {
      scroll.update(time, reduced);
      ship.update();
    },
    dispose() {
      scroll.dispose();
      materials.dispose();
    },
  };
}
