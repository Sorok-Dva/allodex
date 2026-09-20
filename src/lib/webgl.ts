/**
 * Sonde WebGL : les scènes de menu en 3D n'ont de sens que si le navigateur sait les
 * rendre. Créer un contexte est coûteux (et certains navigateurs en limitent le nombre) :
 * le résultat est mis en cache pour toute la session.
 */
let supported: boolean | null = null;

/** Vrai si un contexte `webgl2` ou `webgl` peut être créé. Résultat mémorisé. */
export function hasWebGL(): boolean {
  if (supported === null) {
    try {
      const canvas = document.createElement('canvas');
      supported = !!(canvas.getContext('webgl2') ?? canvas.getContext('webgl'));
    } catch {
      supported = false;
    }
  }
  return supported;
}

/** Oublie le résultat de la sonde. Réservé aux tests (jsdom n'a pas de WebGL). */
export function resetWebGLProbe(): void {
  supported = null;
}
