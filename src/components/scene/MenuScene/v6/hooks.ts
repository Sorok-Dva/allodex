import type { SceneHooks } from '../effects';
import { createV6Effects } from './menuSceneV6';

export const hooks: SceneHooks = {
  createEffects(root) {
    return createV6Effects(root);
  },
};
