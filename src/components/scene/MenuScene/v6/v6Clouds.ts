import type * as THREE from 'three';
import { createUvScroll } from '../uvScroll';

/**
 * Dérive des nuages, de la brume et des rayons de la 6.0.
 *
 * `Animated_Background_6_0.(Geometry).xdb` déclare `scrollRGB`/`scrollAlpha` sur ses 46
 * matériaux — donc le défilement UV est bien armé — mais **aucun** `uTranslateSpeed` ni
 * `vTranslateSpeed` : pas une seule balise de vitesse dans le fichier. C'est exactement le
 * cas de la 4.0 (voir `v4Fog.ts`). En attendant un dump d'époque, les vitesses sont
 * **empruntées à la 7.0** (`AMM_7_0.(Geometry).xdb`), seule version dont les nappes
 * équivalentes portent des vitesses natives : `Back_Cloud_01/02/04/05/07/08` 0,01,
 * `Back_Cloud_03/06` et `Front_Cloud_01/02` 0,02, `Back_Myst` −0,05, `Ground_lights` 0,04
 * (tuiles par seconde). Emprunt validé par l'utilisateur pour la 4.0, repris tel quel ici ;
 * à remplacer par les valeurs natives dès qu'elles existent.
 *
 * Deux contraintes de la 6.0 :
 *
 * * **l'export ne distingue les matériaux que par (nom, texture, fusion, transparence)** :
 *   les six nappes `BackClouds_01`, les quatre `Ferris01_Clouds_Up` et les deux
 *   `MidClouds_01` partagent chacune un seul matériau three.js. La table donne donc la
 *   même vitesse à tous les éléments d'une même famille — sans quoi le résultat
 *   dépendrait de l'ordre de traversée. `Lab_Add` partage le `Noise01White` **additif**
 *   de `Sun_Rays_Add` : il prend forcément la vitesse des rayons.
 * * **l'axe qui porte le motif change selon la nappe.** Les nuages sont tuilés en u
 *   (u de -3,5 à 2,8 sur les anneaux) : ils défilent en u. Les rayons `Noise01White` ont
 *   un u constant (0,51 sur `Sun_Rays_01`) et une plage de v de 1,03 : leurs stries
 *   courent le long de v, c'est donc v qui défile. La vitesse empruntée est la même,
 *   seul l'axe suit les données.
 *
 * Sens de défilement : le crochet 6.0 retourne les textures (`repeat.y = -1`,
 * `offset.y = 1`, les UV du client ayant v = 0 en bas). `createUvScroll` avance
 * `offset.x` de `+t·u` et `offset.y` de `-t·v` ; comme l'axe V est déjà inversé par le
 * retournement, la coordonnée échantillonnée vaut `u + t·u` et `(1 - v) - t·v`, c'est-à-dire
 * exactement le `(u + t·u, v + t·v)` du client. Les vitesses ci-dessous sont donc à lire
 * dans le repère du client, sans changement de signe.
 */
export const BORROWED_SPEEDS: Record<string, readonly [number, number]> = {
  // Anneaux de nuages du fond (coques concentriques autour de la caméra) → Back_Cloud_01.
  Clouds_Ring_01: [0.01, 0],       // BackClouds_03
  Clouds_Ring_02: [0.01, 0],       // Ferris01_Clouds_Ring
  // Famille Ferris01_Clouds_Up / _Down, les nappes hautes et sombres → Back_Cloud_03/06.
  Clouds_Ring_05: [0.02, 0],
  Clouds_Dark_01: [0.02, 0],
  Clouds_Dark_06: [0.02, 0],       // Ferris01_Clouds_Down
  Clouds_Front_Rays: [0.02, 0],
  Clouds_Front_Rays2: [0.02, 0],
  // Famille BackClouds_01 : nuages sombres et nuages accrochés aux crêtes → Back_Cloud_01.
  Clouds_Dark_02: [0.01, 0],
  Clouds_Dark_03: [0.01, 0],
  Clouds_Dark_05: [0.01, 0],
  Clouds_Front_Rays1: [0.01, 0],
  Mountain_Clouds_01: [0.01, 0],
  Mountain_Clouds_02: [0.01, 0],
  // Brume de la vallée (MidClouds_01), la nappe qui croise les autres → Back_Myst, mais
  // à la vitesse des nuages de la table 7.0 : à −0,05 elle traversait trop vite (choix
  // de l'utilisateur, 22/09/2026).
  Clouds_Mid: [-0.02, 0],
  Clouds_Mid1: [-0.02, 0],
  // Rayons Noise01White, stries le long de v → Ground_lights.
  Sun_Rays_01: [0, 0.04],
  Sun_Rays_Add: [0, 0.04],
  Lab_Add: [0, 0.04],
};

export function cloudSpeed(element: string): readonly [number, number] | undefined {
  return BORROWED_SPEEDS[element];
}

export function createV6Clouds(root: THREE.Object3D) {
  return createUvScroll(root, (_mesh, element) => cloudSpeed(element));
}
