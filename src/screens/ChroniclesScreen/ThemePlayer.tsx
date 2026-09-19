import { nineSlice } from '@/lib/nineSlice';
import type { ArchiveEntry } from '@/lib/assets';
import { useI18n } from '@/lib/i18n';
import s from './ThemePlayer.module.css';

/**
 * Durée en `m:ss`, secondes tronquées comme les lecteurs de musique. Le rendu détache
 * le deux-points (voir `Duration`) : dans la police du jeu, à cette taille, « 3:02 » se
 * lisait « 302 » sur les captures.
 */
export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const m = Math.floor(total / 60);
  return `${m}:${String(total - m * 60).padStart(2, '0')}`;
}

/** `3:02` avec un deux-points un peu plus grand et aéré, sinon illisible à 13 px. */
export function Duration({ seconds }: { seconds: number }) {
  const [minutes, rest] = formatDuration(seconds).split(':');
  return (
    <span className={s.duration} data-testid="theme-duration">
      {minutes}<span className={s.colon}>:</span>{rest}
    </span>
  );
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
 *
 * Sans thème, le lecteur reste en place, bouton grisé : « Thème non disponible »
 * quand aucun client archivé ne le conserve (`theme_note` du manifeste), « Thème non
 * extrait » quand c'est l'extraction qui n'a rien produit (disque non monté). Le détail
 * de la note reste dans l'index, il n'est pas affiché.
 */
export function ThemePlayer({ entry, playing, onToggle, className }: Props) {
  const theme = entry.theme;
  const { t } = useI18n();
  return (
    <div className={`${s.player} ${className ?? ''}`} style={nineSlice('tooltip-frame', [4, 4, 4, 4])}>
      {!theme && (
        <button type="button" className={`${s.button} ${s.buttonOff}`} disabled aria-label={t('theme.unavailable')}>
          <span className={s.buttonSkin} aria-hidden="true" style={nineSlice('pill-full', [0, 24, 0, 24], { fill: true })} />
          <svg className={s.glyph} viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
            <path d="M4.5 2.5 13 8l-8.5 5.5z" fill="currentColor" />
          </svg>
        </button>
      )}
      {theme ? (
        <>
          <button
            type="button"
            className={s.button}
            onClick={onToggle}
            aria-label={playing ? t('theme.pause') : t('theme.play')}
          >
            <span className={s.buttonSkin} aria-hidden="true" style={nineSlice('pill-full', [0, 24, 0, 24], { fill: true })} />
            <svg className={s.glyph} viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
              {playing
                ? <path d="M4 2.5h3v11H4zM9 2.5h3v11H9z" fill="currentColor" />
                : <path d="M4.5 2.5 13 8l-8.5 5.5z" fill="currentColor" />}
            </svg>
          </button>

          <div className={s.text}>
            <div className={s.name}>{theme.name}</div>
            <div className={s.meta}>
              <span className={s.kind}>{t('theme.kind')}</span>
              <Duration seconds={theme.duration} />
            </div>
          </div>
        </>
      ) : (
        <div className={s.text}>
          <div className={s.missing}>{entry.theme_note ? t('theme.notAvailable') : t('theme.notExtracted')}</div>
        </div>
      )}
    </div>
  );
}
