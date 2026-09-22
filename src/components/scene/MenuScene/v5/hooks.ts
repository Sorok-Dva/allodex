import type { SceneHooks } from '../effects';
import { createV5Effects, type V5Meta } from './menuSceneV5';

/** 5.0 « Heart of the World » : la tour-phare, le grand arbre et le navire de raid. */
export const hooks: SceneHooks = {
  prepareTexture(texture) {
    // Comme en 4.0 et 7.0 : l'origine des textures du client est en bas (la pointe de la
    // flèche de la tour, en haut de `Tower_01`, porte V = 0,99 ; corrélation Z/V = +1),
    // glTF la met en haut.
    texture.repeat.y = -1;
    texture.offset.y = 1;
  },
  createEffects(root, meta) {
    return createV5Effects(root, meta as V5Meta);
  },
};
