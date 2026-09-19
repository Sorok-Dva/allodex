import { useState } from 'react';
import { sprite, tex } from '@/lib/assets';
import { useGameAudio } from '@/lib/audio/useGameAudio';
import { useI18n } from '@/lib/i18n';
import s from './SpeakerToggle.module.css';

/** Halo vert des boutons ronds du jeu (DXT1 sans alpha : posé en fondu « screen »). */
const GLOW = 'Interface/Ingame/Contextructor/CornerQuestion/CornerQuestionHighlight';

/**
 * Interrupteur son global (musique + SFX) : `.muted` sur les pistes, jamais de pause.
 * Habillé comme les boutons ronds du jeu : médaillon vierge (`medallion-normal`,
 * dérivé du bouton « ? » des fenêtres), enfoncé au clic, halo au survol, glyphe or.
 */
export function SpeakerToggle({ className }: { className?: string }) {
  const { muted, toggleMuted } = useGameAudio();
  const { t } = useI18n();
  const [pressed, setPressed] = useState(false);
  return (
    <button
      type="button"
      className={`${s.toggle} ${className ?? ''}`}
      onClick={toggleMuted}
      onPointerDown={() => setPressed(true)}
      onPointerUp={() => setPressed(false)}
      onPointerLeave={() => setPressed(false)}
      aria-pressed={muted}
      aria-label={muted ? t('audio.unmute') : t('audio.mute')}
    >
      <span className={s.base} style={{ backgroundImage: `url(${sprite(pressed ? 'medallion-pressed' : 'medallion-normal')})` }} />
      <span className={s.glow} style={{ backgroundImage: `url(${tex(GLOW)})` }} />
      <svg className={`${s.glyph} ${muted ? s.glyphMuted : ''}`} viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" focusable="false">
        <path d="M3 7.5v5h3.1l4.4 3.3V4.2L6.1 7.5H3z" fill="currentColor" />
        {muted ? (
          <path d="M13 7.2l4.4 5.6M17.4 7.2l-4.4 5.6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" fill="none" />
        ) : (
          <path d="M13.2 7.6c1.3 1 1.3 3.8 0 4.8M15.4 5.8c2.3 1.8 2.3 6.6 0 8.4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" fill="none" />
        )}
      </svg>
    </button>
  );
}
