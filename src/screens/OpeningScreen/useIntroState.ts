import { useCallback, useState } from 'react';

export const INTRO_SEEN_KEY = 'allods.introSeen';
export type Phase = 'intro' | 'menu';

export function initialPhase(storage: Storage, forceMenu = false): Phase {
  if (forceMenu) return 'menu';
  try { return storage.getItem(INTRO_SEEN_KEY) === '1' ? 'menu' : 'intro'; } catch { return 'menu'; }
}

export function useIntroState(storage: Storage = window.localStorage, forceMenu = false) {
  const [phase, setPhase] = useState<Phase>(() => initialPhase(storage, forceMenu || window.location.search.includes('skipIntro')));
  const skipIntro = useCallback(() => {
    try { storage.setItem(INTRO_SEEN_KEY, '1'); } catch { /* stockage indisponible */ }
    setPhase('menu');
  }, [storage]);
  const replayIntro = useCallback(() => setPhase('intro'), []);
  return { phase, skipIntro, replayIntro };
}
