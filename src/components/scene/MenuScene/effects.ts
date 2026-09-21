import type * as THREE from 'three';
import type { SceneMeta } from '@/lib/assets';
import { hooks as v7 } from './v7/hooks';
import { hooks as v8 } from './v8/hooks';

/** Effets rejoués par-dessus le `.glb` (tirs, jets, brume…), mis à jour à chaque image. */
export type SceneEffects = {
  update(time: number, reduced?: boolean): void;
  dispose(): void;
};

/**
 * Particularités d'une version de scène. `MenuScene` reste générique : il charge le
 * glTF, monte la caméra et joue les animations ; chaque version branche ici ce qui
 * n'est vrai que d'elle. Tous les crochets sont optionnels.
 */
export type SceneHooks = {
  /** Retouche d'une texture de matériau après chargement (orientation des UV, filtrage…). */
  prepareTexture?(texture: THREE.Texture): void;
  /** `true` pour ne pas jouer une piste d'animation du glTF (rejouée autrement). */
  skipClip?(name: string): boolean;
  /**
   * Construit les effets de la version. `loadTexture` charge une image déposée à côté de
   * `scene.json` (chemin relatif tel qu'écrit dans le méta) et l'inscrit au démontage.
   */
  createEffects?(root: THREE.Object3D, meta: SceneMeta, loadTexture: (file: string) => THREE.Texture): SceneEffects | null;
};

/** Une version sans module n'a aucun crochet. Ajouter ici chaque version scénarisée. */
const HOOKS: Record<string, SceneHooks> = {
  '7.0': v7,
  '8.0': v8,
};

export function hooksFor(version: string | undefined): SceneHooks {
  return (version && HOOKS[version]) || {};
}
