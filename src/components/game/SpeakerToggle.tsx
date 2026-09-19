import { useGameAudio } from '@/lib/audio/useGameAudio';
import s from './SpeakerToggle.module.css';

/** Interrupteur son global (musique + SFX) : `.muted` sur les pistes, jamais de pause. */
export function SpeakerToggle({ className }: { className?: string }) {
  const { muted, toggleMuted } = useGameAudio();
  return (
    <button
      type="button"
      className={`${s.toggle} ${className ?? ''}`}
      onClick={toggleMuted}
      aria-pressed={muted}
      aria-label={muted ? 'Activer le son' : 'Couper le son'}
    >
      <svg viewBox="0 0 20 20" width="20" height="20" aria-hidden="true" focusable="false">
        <path d="M3 7.5v5h3.1l4.4 3.3V4.2L6.1 7.5H3z" fill="currentColor" />
        {muted ? (
          <path d="M13 7.2l4.4 5.6M17.4 7.2l-4.4 5.6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" fill="none" />
        ) : (
          <path d="M13.2 7.6c1.3 1 1.3 3.8 0 4.8M15.4 5.8c2.3 1.8 2.3 6.6 0 8.4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" fill="none" />
        )}
      </svg>
    </button>
  );
}
