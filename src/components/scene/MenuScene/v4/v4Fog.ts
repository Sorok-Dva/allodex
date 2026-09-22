import type * as THREE from 'three';
import { createUvScroll } from '../uvScroll';

/**
 * Mouvement de la brume et des nuages de la 4.0.
 *
 * Le xdb `Animated_Background.(Geometry).xdb` déclare `scrollRGB`/`scrollAlpha` sur toutes
 * ses nappes mais n'en donne aucune vitesse — dans toutes les copies disponibles (serveur
 * 7.0, éditeur 7.0, dump du client V8). Le client 4.0 les fait pourtant dériver. En attendant
 * un dump du xdb d'époque, les vitesses sont **empruntées à la 7.0** (`AMM_7_0.(Geometry).xdb`),
 * dont les nappes équivalentes portent des vitesses natives : brume `Noise03White` comme les
 * `*_Myst` (−0,05 / 0,05 / 0,02 / 0,01 tuile/s), calques de nuages comme les `Back_Cloud_*`
 * et `Front_Cloud_*` (0,01 à 0,02). Emprunt validé par l'utilisateur ; à remplacer par les
 * valeurs natives dès qu'elles existent.
 */
export const BORROWED_SPEEDS: Record<string, readonly [number, number]> = {
  fog: [0.05, 0],          // Front_Myst_01
  fog1: [-0.02, 0],        // Back_Myst, sens opposé pour le croisement des nappes
  Clouds_037: [0.01, 0],   // Front_Myst_03
  Arc_Clouds_01: [0.02, 0], Arc_Clouds_02: [0.02, 0], Arc_Clouds_03: [0.02, 0], // Front_Cloud_*
};
/** Les autres calques de nuages dérivent au rythme des `Back_Cloud_*` de la 7.0. */
export const CLOUD_SPEED: readonly [number, number] = [0.01, 0];

export function fogSpeed(element: string): readonly [number, number] | undefined {
  if (element in BORROWED_SPEEDS) return BORROWED_SPEEDS[element];
  if (/^(Clouds_|Water_Clouds_|Back3$)/.test(element)) return CLOUD_SPEED;
  return undefined;
}

export function createV4Fog(root: THREE.Object3D) {
  return createUvScroll(root, (_mesh, element) => fogSpeed(element));
}
