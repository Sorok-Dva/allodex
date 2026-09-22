import type * as THREE from 'three';
import type { SceneEffects } from '../effects';
import { applyNativeDrawOrder } from './v6SceneLayers';
import { restoreOpaqueVertexAlpha } from './v6Sky';

/**
 * 6.0 « Broken Chains » : rien n'est ajouté au `.glb`. Le drapeau, les arbres et le
 * balancement du train sont l'animation native jouée par le mixeur ; aucun matériau ne
 * défile et le VisObjectTemplate n'attache aucun effet. Il reste à peindre dans l'ordre
 * du client et à rendre visible le dôme de fond (alpha de sommet nul, ignoré par le jeu).
 * Le décor peint (`skinIndex` −1 dans le xdb) est rattaché par l'export à une articulation
 * immobile : plus rien à figer côté lecteur.
 */
export function createV6Effects(_root: THREE.Object3D): SceneEffects {
  applyNativeDrawOrder(_root);
  restoreOpaqueVertexAlpha(_root);
  return {
    update() { /* tout le mouvement 6.0 vient du mixeur */ },
    dispose() { /* rien d'alloué */ },
  };
}
