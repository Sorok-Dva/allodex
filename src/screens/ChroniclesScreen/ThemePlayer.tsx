import { nineSlice } from '@/lib/nineSlice';
import type { ArchiveEntry } from '@/lib/assets';
import s from './ThemePlayer.module.css';

/** Durée en `m:ss`, secondes tronquées comme les lecteurs de musique. */
export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const m = Math.floor(total / 60);
  return `${m}:${String(total - m * 60).padStart(2, '0')}`;
}

type Props = {
  entry: ArchiveEntry;
  playing: boolean;
  onToggle: () => void;
  className?: string;
};

/**
 * Lecteur du thème musical de la version affichée : nom de la piste, durée et bouton
 * lecture/pause. Le son lui-même est joué par le moteur audio du site (fondu croisé
 * d'une version à l'autre) ; ce composant n'est que la façade.
 */
export function ThemePlayer({ entry, playing, onToggle, className }: Props) {
  const theme = entry.theme;
  return (
    <div className={`${s.player} ${className ?? ''}`} style={nineSlice('tooltip-frame', [4, 4, 4, 4])}>
      {theme ? (
        <>
          <button
            type="button"
            className={s.button}
            onClick={onToggle}
            aria-label={playing ? 'Mettre le thème en pause' : 'Écouter le thème'}
          >
            <span className={s.buttonSkin} aria-hidden="true" style={nineSlice('pill-full', [0, 30, 0, 24], { fill: true })} />
            <svg className={s.glyph} viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
              {playing
                ? <path d="M4 2.5h3v11H4zM9 2.5h3v11H9z" fill="currentColor" />
                : <path d="M4.5 2.5 13 8l-8.5 5.5z" fill="currentColor" />}
            </svg>
          </button>

          <div className={s.text}>
            <div className={s.name}>{theme.name}</div>
            <div className={s.meta}>
              <span className={s.kind}>Thème du menu</span>
              <span className={s.duration}>{formatDuration(theme.duration)}</span>
            </div>
            {entry.theme_note && <div className={s.note}>{entry.theme_note}</div>}
          </div>
        </>
      ) : (
        <div className={s.text}><div className={s.missing}>Thème non extrait</div></div>
      )}
    </div>
  );
}
