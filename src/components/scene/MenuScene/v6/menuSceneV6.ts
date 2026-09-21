import type * as THREE from 'three';
import type { SceneEffects } from '../effects';
import { applyNativeDrawOrder } from './v6SceneLayers';
import { freezeLandscape } from './v6Landscape';
import { restoreOpaqueVertexAlpha } from './v6Sky';

/**
 * 6.0 « Broken Chains » : rien n'est ajouté au `.glb`. Le drapeau, les arbres et le
 * balancement du train sont l'animation native jouée par le mixeur ; aucun matériau ne
 * défile et le VisObjectTemplate n'attache aucun effet. Il reste à peindre dans l'ordre
 * du client, à rendre visible le dôme de fond (alpha de sommet nul, ignoré par le jeu) et
 * à figer le décor que l'export Maya a rattaché à l'os du drapeau. L'ordre et le matériau
 * sont posés d'abord : les copies rigides héritent du `renderOrder` et du matériau de
 * l'original.
 */
export function createV6Effects(root: THREE.Object3D): SceneEffects {
  applyNativeDrawOrder(root);
  restoreOpaqueVertexAlpha(root);
  const landscape = freezeLandscape(root);
  return {
    update() { /* tout le mouvement 6.0 vient du mixeur */ },
    dispose() { landscape.dispose(); },
  };
}
