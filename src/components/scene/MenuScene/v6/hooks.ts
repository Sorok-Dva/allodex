import type { SceneHooks } from '../effects';
import { createV6Effects } from './menuSceneV6';

export const hooks: SceneHooks = {
  prepareTexture(texture) {
    // Comme en 7.0 et 8.0 : les UV du client ont v = 0 en bas de l'image (corrélation
    // z/v positive sur 37 des 41 calques peints du xdb ; la coupole du laboratoire est
    // en v = 1, la base des maisons en v = 0), le glTF les lit avec v = 0 en haut. Sans
    // ce retournement la coupole pend sous le laboratoire et les prairies montrent leur
    // ciel découpé vers le bas.
    texture.repeat.y = -1;
    texture.offset.y = 1;
  },
  createEffects(root) {
    return createV6Effects(root);
  },
};
