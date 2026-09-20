import { useCallback, useEffect, useState } from 'react';

export type Phase = 'intro' | 'fading' | 'menu';

/** Durée de la cinématique (vidéo + animation du logo) avant le fondu vers le menu. */
export const INTRO_MS = 4600;
/** Durée du fondu enchaîné intro → menu (doit correspondre à `.introLayerOut` en CSS). */
export const FADE_MS = 1100;

// L'intro se rejoue à chaque chargement de la page (URL saisie, F5…) mais pas quand on
// revient sur l'accueil par la navigation interne : mémoire de module, jamais persistée.
let playedThisLoad = false;

export function initialPhase(forceMenu = false, alreadyPlayed = playedThisLoad): Phase {
  return forceMenu || alreadyPlayed ? 'menu' : 'intro';
}

/** Réservé aux tests : oublie que l'intro a déjà été jouée dans ce chargement. */
export function resetIntroMemory() { playedThisLoad = false; }

export function useIntroState(forceMenu = false) {
  const [phase, setPhase] = useState<Phase>(() => initialPhase(forceMenu || window.location.search.includes('skipIntro')));

  useEffect(() => {
    if (phase === 'intro') {
      playedThisLoad = true;
      const id = window.setTimeout(() => setPhase('fading'), INTRO_MS);
      return () => window.clearTimeout(id);
    }
    if (phase === 'fading') {
      const id = window.setTimeout(() => setPhase('menu'), FADE_MS);
      return () => window.clearTimeout(id);
    }
  }, [phase]);

  const skipIntro = useCallback(() => setPhase(p => (p === 'intro' ? 'fading' : p)), []);
  const replayIntro = useCallback(() => setPhase('intro'), []);
  return { phase, skipIntro, replayIntro };
}
