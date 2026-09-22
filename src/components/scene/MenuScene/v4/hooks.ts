import type { SceneHooks } from '../effects';
import { prepareV4Layers } from './v4SceneLayers';
import { createV4Fog } from './v4Fog';

/** 4.0 « Lords of Destiny » : l'île au château, ses oiseaux et son dôme de ciel. */
export const hooks: SceneHooks = {
  prepareTexture(texture) {
    // Comme en 7.0 : les V des sommets croissent vers le haut de l'objet (château, île),
    // l'origine des textures du client est donc en bas ; glTF la met en haut.
    texture.repeat.y = -1;
    texture.offset.y = 1;
  },
  createEffects(root, meta) {
    // `sortMode` relevé dans le Geometry xdb par tools/scenes/v4_0.py : `OFFSETS` = le
    // moteur peint les éléments dans l'ordre du fichier, sans tri par profondeur.
    if ((meta as { sortMode?: string }).sortMode === 'OFFSETS') prepareV4Layers(root);
    // Oiseaux et cristaux viennent de l'animation squelettique du glTF (mixeur générique) ;
    // seule la dérive des nappes de brume est rejouée ici (vitesses empruntées à la 7.0).
    return createV4Fog(root);
  },
};
