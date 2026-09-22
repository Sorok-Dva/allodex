import type { SceneHooks } from '../effects';
import { prepareV8Layers } from './v8SceneLayers';

/**
 * 8.0 « Immortality » : un seul maillage, aucun objet d'effet attaché. Tout ce que le
 * client anime — vapeurs, flammes, faisceau, nuages, halo du dôme — l'est par les
 * courbes du glTF et le défilement UV des matériaux natifs ; il n'y a rien à redessiner,
 * seulement l'ordre de peinture à respecter. Seul écart : le défilement **emprunté** des
 * trois grandes langues de feu des braseros (`BORROWED_FIRE_SPEEDS`, v8SceneLayers). Le `ZoneLights` du menu V8 déclare aussi
 * un bloom (seuil 0,12, puissance 3,5, contribution 0,75) et un brouillard : leur
 * formule exacte n'est pas connue et un essai d'`UnrealBloomPass` calé sur ces valeurs
 * saturait la scène (voir README, « Scène 8.0 ») — ils ne sont pas rejoués.
 */
export const hooks: SceneHooks = {
  prepareTexture(texture) {
    // Comme en 7.0 : les UV du client ont v = 0 en bas de l'image (corrélation z/v
    // positive sur tous les calques peints), le glTF les lit avec v = 0 en haut.
    texture.repeat.y = -1;
    texture.offset.y = 1;
  },
  createEffects(root) {
    const layers = prepareV8Layers(root);
    return {
      update(time, reduced = false) { layers.update(time, reduced); },
      dispose() { layers.dispose(); },
    };
  },
};
