import type { SceneHooks } from '../effects';
import { createV5Effects } from './menuSceneV5';

export const hooks: SceneHooks = {
  createEffects(root, meta) {
    // Le brouillard du client se fond dans le fond de scène : même couleur que lui.
    return createV5Effects(root, meta.camera, meta.background ?? '#3d4da9');
  },
};
