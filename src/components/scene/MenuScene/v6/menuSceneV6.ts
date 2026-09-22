import type * as THREE from 'three';
import type { SceneEffects } from '../effects';
import { applyNativeDrawOrder } from './v6SceneLayers';
import { restoreOpaqueVertexAlpha } from './v6Sky';
import { createV6Clouds } from './v6Clouds';

/**
 * 6.0 « Broken Chains » : rien n'est ajouté au `.glb`. Le drapeau du laboratoire, les
 * arbres et le balancement du manatrain sont l'animation native jouée par le mixeur — et
 * c'est tout ce que les données font bouger de la géométrie (le manatrain ne parcourt pas
 * son câble : voir `tools/scenes/v6_0.py`). Le VisObjectTemplate n'attache aucun effet.
 * Reste, côté lecteur : peindre dans l'ordre du client, rendre visible le dôme de fond
 * (alpha de sommet nul, ignoré par le jeu) et faire dériver les nappes de nuages, de brume
 * et de rayons, dont le xdb arme le défilement UV sans en donner la vitesse (`v6Clouds`).
 * Le décor peint (`skinIndex` −1 dans le xdb) est rattaché par l'export à une articulation
 * immobile : plus rien à figer côté lecteur.
 */
export function createV6Effects(root: THREE.Object3D): SceneEffects {
  applyNativeDrawOrder(root);
  restoreOpaqueVertexAlpha(root);
  const clouds = createV6Clouds(root);
  return {
    update(time, reduced) { clouds.update(time, reduced); },
    dispose() { clouds.dispose(); },
  };
}
