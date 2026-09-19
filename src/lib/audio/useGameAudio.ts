import { useContext } from 'react';
import { AudioContext, type GameAudio } from './AudioProvider';

/** Accès au moteur audio unique monté par `<AudioProvider>` dans `App`. */
export function useGameAudio(): GameAudio {
  const ctx = useContext(AudioContext);
  if (!ctx) throw new Error('useGameAudio doit être utilisé sous <AudioProvider>');
  return ctx;
}
