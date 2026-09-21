import { useEffect, useState, type CSSProperties, type MouseEvent as ReactMouseEvent } from 'react';
import type { Medal } from '@/data/medals.types';
import { currentRankOf, isComplete } from '@/data/medals.logic';
import { T, sprite, tex } from '@/lib/assets';
import { nineSlice } from '@/lib/nineSlice';
import { MedalBadge } from '@/components/ui/MedalBadge';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { GameTooltip } from '@/components/ui/GameTooltip';
import { formatGameDate, formatGameDateTime } from '@/lib/dates';
import { toRoman } from '@/lib/roman';
import s from './MedalEntry.module.css';

/**
 * Hauteurs du parchemin relevées sur `refs/astral.png` (bords de la texture, x 1340) :
 * « Connecté avec les étoiles » y 315→420 (106 px) et « Propriétaire » y 426→530 (105) :
 * 105,5 px reproduit le pas relevé (111 puis 110). « Parfait ! » y 536→694
 * (159 px, avec la série). Les entrées sans barre ni série n'apparaissent pas en entier
 * dans la capture : 84 px = bas de la description (63) + les 21 px de marge basse mesurés
 * sous la barre. Écart constant de 5 px entre deux parchemins (pas de 111 px).
 */
const H_PLAIN = 84;
/** Parchemin avec barre seule, puis avec série seule : les deux blocs s'ajoutent. */
const H_BAR = 105.5;
const H_SERIES = 159;
/** Hauteur propre du bloc « barre » (21,5 px) et du bloc « série » (75 px). */
const BLOCK_BAR = H_BAR - H_PLAIN;
const BLOCK_SERIES = H_SERIES - H_PLAIN;
/** La texture MedalPaper fait 520 × 120 mais n'est opaque que sur 117 lignes. */
const PAPER_RATIO = 120 / 117;
/** Pas mesuré entre deux cases de la série : 1012, 1050, 1087, 1124, 1162, 1199. */
const SLOT = 35;
const SLOT_GAP = 2.4;

export type MedalEntryProps = {
  medal: Medal;
  onTrack?: (medalId: string, value: boolean) => void;
};

export function MedalEntry({ medal, onTrack }: MedalEntryProps) {
  const complete = isComplete(medal);
  const rank = currentRankOf(medal);
  const series = medal.medalCollection ?? [];
  const showBar = rank.completeProgress > 1;
  const showSeries = series.length > 0;
  const value = complete ? rank.completeProgress : medal.progress?.value ?? 0;
  // Spec § 7.3 : la barre et la série sont indépendantes ; un succès qui porte les deux
  // empile les deux blocs, et la série descend de la hauteur du bloc « barre ».
  const height = H_PLAIN + (showBar ? BLOCK_BAR : 0) + (showSeries ? BLOCK_SERIES : 0);
  const seriesShift = showBar && showSeries ? BLOCK_BAR : 0;
  const [cursor, setCursor] = useState<DOMRect | null>(null);

  // L'infobulle du jeu suit le pointeur (coin haut-gauche à +9, +11 : relevé en comparant
  // `refs/tooltip.png` à `refs/astral.png`), pas le centre de l'élément survolé.
  const track = (e: ReactMouseEvent) => {
    const { clientX: x, clientY: y } = e;
    setCursor({ x, y, left: x, top: y, right: x, bottom: y, width: 0, height: 0, toJSON: () => ({}) });
  };
  const hover = { onMouseEnter: track, onMouseMove: track, onMouseLeave: () => setCursor(null) };

  // Le pointeur ne bouge pas quand on défile à la molette : sans cela l'infobulle resterait
  // affichée au même endroit alors que son entrée a glissé. On n'écoute que tant qu'elle est
  // visible, et en phase de capture pour attraper le défilement de la liste, qui ne remonte pas.
  const shown = cursor !== null;
  useEffect(() => {
    if (!shown) return;
    const hide = () => setCursor(null);
    window.addEventListener('scroll', hide, true);
    return () => window.removeEventListener('scroll', hide, true);
  }, [shown]);

  return (
    <article className={s.entry} style={{ height, '--series-shift': `${seriesShift}px` } as CSSProperties}>
      <div
        className={s.paper}
        data-testid="medal-paper"
        data-complete={complete ? 'true' : 'false'}
        style={{
          backgroundImage: `url(${tex(`${T.medals}/MedalPaper${complete ? 'Complete' : ''}`)})`,
          backgroundSize: `100% ${height * PAPER_RATIO}px`,
        }}
      />

      <div className={s.badgeZone} {...hover}>
        <MedalBadge score={rank.score} icon={rank.image ?? medal.icon} complete={complete} />
      </div>

      <h3 className={`${s.name} ${complete ? s.done : ''}`} {...hover}>{medal.name}</h3>

      {complete && medal.finishDate ? (
        <time className={`${s.date} ${s.done}`} dateTime={medal.finishDate}>{formatGameDate(medal.finishDate)}</time>
      ) : (
        <button
          type="button"
          className={s.checkbox}
          role="checkbox"
          aria-checked={!!medal.tracked}
          aria-label={`Suivre « ${medal.name} »`}
          style={{ backgroundImage: `url(${sprite(medal.tracked ? 'checkbox-on' : 'checkbox-off')})` }}
          onClick={() => onTrack?.(medal.id, !medal.tracked)}
        />
      )}

      <p className={s.desc}>{rank.description}</p>

      {showBar && <ProgressBar className={s.bar} value={value} max={rank.completeProgress} />}

      {showSeries && (
        <>
          <p className={s.seriesLabel}>Série de succès :</p>
          <ul className={s.series} data-testid="medal-series" style={{ gap: `${SLOT_GAP}px` }}>
            {series.map(item => (
              <li
                key={item.medalId}
                className={s.slot}
                style={{ width: SLOT, height: SLOT, ...nineSlice('series-slot', [3, 3, 3, 3]) }}
              >
                <img
                  className={`${s.slotIcon} ${item.success ? '' : s.locked}`}
                  src={tex(item.icon)}
                  alt=""
                  draggable={false}
                />
                <span className={s.slotRank}>{toRoman(item.rank)}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      <GameTooltip
        anchor={cursor}
        align="cursor"
        title={medal.name}
        date={complete && medal.finishDate ? `Date : ${formatGameDateTime(medal.finishDate)}` : undefined}
        hint="Shift + clic : Lien vers les succès"
      >
        {rank.description}
      </GameTooltip>
    </article>
  );
}
