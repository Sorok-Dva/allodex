import * as THREE from 'three';
import type { SceneHooks } from '../effects';
import { createV7Effects, type CannonTextures } from './menuSceneV7';

export const hooks: SceneHooks = {
  prepareTexture(texture) {
    // UV verticales inversées par le lecteur du client 7.0.
    texture.repeat.y = -1;
    texture.offset.y = 1;
  },
  // Cette piste ne décode pas encore la chute des coques : la séquence cohérente
  // coque + feu + réacteurs est pilotée par v7Intro ; AMM_Shot01 est une bibliothèque.
  skipClip: name => ['AMM_7_0_Ships_Destroyed', 'AMM_Shot01'].includes(name),
  createEffects(root, meta, loadTexture) {
    const cannonTextures: CannonTextures = {};
    for (const [key, file] of Object.entries(meta.cannonTextures ?? {})) {
      const texture = loadTexture(file);
      texture.wrapS = texture.wrapT = THREE.ClampToEdgeWrapping;
      cannonTextures[key as keyof CannonTextures] = texture;
    }
    return createV7Effects(root, cannonTextures);
  },
};
