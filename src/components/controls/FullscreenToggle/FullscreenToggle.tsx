import { useState } from 'react';
import { sprite, tex } from '@/lib/assets';
import { useI18n } from '@/lib/i18n';
import s from './FullscreenToggle.module.css';

const GLOW = 'Interface/Ingame/Contextructor/CornerQuestion/CornerQuestionHighlight';

export function FullscreenToggle({
  className,
  fullscreen,
  onToggle,
  labels,
}: {
  className?: string;
  fullscreen: boolean;
  onToggle: () => void;
  /** Libellés propres à l'écran (par défaut ceux des Chroniques). */
  labels?: { enter: string; exit: string };
}) {
  const { t } = useI18n();
  const label = fullscreen ? labels?.exit ?? t('chronicles.exitFullscreen') : labels?.enter ?? t('chronicles.fullscreen');
  const [pressed, setPressed] = useState(false);

  return (
    <button
      type="button"
      className={`${s.toggle} ${className ?? ''}`}
      onClick={(e) => {
        e.stopPropagation();
        onToggle();
      }}
      onPointerDown={() => setPressed(true)}
      onPointerUp={() => setPressed(false)}
      onPointerLeave={() => setPressed(false)}
      aria-pressed={fullscreen}
      aria-label={label}
      title={label}
    >
      <span className={s.base} style={{ backgroundImage: `url(${sprite(pressed ? 'medallion-pressed' : 'medallion-normal')})` }} />
      <span className={s.glow} style={{ backgroundImage: `url(${tex(GLOW)})` }} />
      <svg className={s.glyph} viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" focusable="false">
        {fullscreen ? (
          <path d="M7 3v4H3M13 3v4h4M7 17v-4H3M13 17v-4h4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        ) : (
          <path d="M3 7V3h4M17 7V3h-4M3 13v4h4M17 13v4h-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        )}
      </svg>
    </button>
  );
}
