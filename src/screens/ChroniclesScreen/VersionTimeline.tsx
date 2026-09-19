import { useEffect, useRef } from 'react';
import { sprite, type ArchiveEntry } from '@/lib/assets';
import { nineSlice } from '@/lib/nineSlice';
import { useI18n } from '@/lib/i18n';
import s from './VersionTimeline.module.css';

/**
 * Tranches de la pilule du jeu (`pill-full`, 242 × 28) : les 24 px de gauche et les
 * 30 px de droite portent les ornements (liseré, chevron), le ventre est uniforme et
 * supporte donc l'étirement. Le sprite n'a pas d'entrée `slice` dans `sprites.json`
 * (il est découpé d'un bloc), ces valeurs sont mesurées sur l'image.
 */
const PILL_SLICE: [number, number, number, number] = [0, 30, 0, 24];

type Props = {
  entries: ArchiveEntry[];
  /** Version affichée, en surbrillance dans la frise. */
  active: string;
  onSelect: (version: string) => void;
  className?: string;
};

/**
 * Frise horizontale des versions : une pilule du jeu par version, encadrée des deux
 * flèches d'ascenseur du jeu (`scroll-up`/`scroll-down` pivotées d'un quart de tour).
 * La frise défile horizontalement quand les pilules ne tiennent pas dans la largeur ;
 * la version active y est toujours ramenée.
 */
export function VersionTimeline({ entries, active, onSelect, className }: Props) {
  const { t } = useI18n();
  const railRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLButtonElement>(null);
  const index = entries.findIndex(e => e.version === active);

  useEffect(() => {
    // `scrollIntoView` n'existe pas dans jsdom : l'appel reste optionnel.
    activeRef.current?.scrollIntoView?.({ block: 'nearest', inline: 'center', behavior: 'smooth' });
  }, [active]);

  const step = (delta: number) => {
    const next = entries[index + delta];
    if (next) onSelect(next.version);
  };

  return (
    <div className={`${s.timeline} ${className ?? ''}`}>
      <button
        type="button"
        className={s.arrow}
        aria-label={t('chronicles.previous')}
        disabled={index <= 0}
        style={{ backgroundImage: `url(${sprite(index <= 0 ? 'scroll-up-off' : 'scroll-up')})` }}
        onClick={() => step(-1)}
      />

      <div className={s.rail} ref={railRef}>
        <ul className={s.list}>
          {entries.map(entry => {
            const current = entry.version === active;
            return (
              <li key={entry.version}>
                <button
                  type="button"
                  ref={current ? activeRef : undefined}
                  className={`${s.pill} ${current ? s.pillActive : ''}`}
                  data-testid="version-pill"
                  aria-current={current ? 'true' : undefined}
                  aria-label={entry.label}
                  title={entry.label}
                  onClick={() => onSelect(entry.version)}
                >
                  <span
                    className={s.pillSkin}
                    aria-hidden="true"
                    style={nineSlice(current ? 'pill-full-open' : 'pill-full', PILL_SLICE, { fill: true })}
                  />
                  <span className={s.pillLabel}>{entry.version}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      <button
        type="button"
        className={s.arrow}
        aria-label={t('chronicles.next')}
        disabled={index < 0 || index >= entries.length - 1}
        style={{ backgroundImage: `url(${sprite(index >= entries.length - 1 ? 'scroll-down-off' : 'scroll-down')})` }}
        onClick={() => step(1)}
      />
    </div>
  );
}
