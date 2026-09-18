import { useRef, useState } from 'react';
import type { Medal } from '@/data/medals.types';
import { currentRankOf, isComplete } from '@/data/medals.logic';
import { T, tex } from '@/lib/assets';
import { MedalBadge } from '@/components/game/MedalBadge';
import { ProgressBar } from '@/components/game/ProgressBar';
import { formatGameDate } from './formatDate';
import s from './MedalEntry.module.css';

type TipPos = { left: number; top: number };

export function MedalEntry({ medal }: { medal: Medal }) {
  const complete = isComplete(medal);
  const rank = currentRankOf(medal);
  const articleRef = useRef<HTMLElement>(null);
  const [tip, setTip] = useState<TipPos | null>(null);
  const conditions = [...(medal.dressCollection ?? []), ...(medal.medalCollection ?? [])];
  const showBar = rank.completeProgress > 1;
  const value = complete ? rank.completeProgress : medal.progress?.value ?? 0;

  // Le panneau Succès est dans une liste `overflow-y: auto` (voir MedalsList.module.css)
  // qui rognerait un tooltip positionné en `absolute` dès qu'une entrée est proche du
  // bord de la fenêtre de défilement. On calcule donc des coordonnées viewport via
  // `getBoundingClientRect()` sur l'entrée survolée et on affiche le tooltip en
  // `position: fixed` (voir .tooltip), ce qui l'affranchit du clipping du conteneur.
  const showTip = () => {
    const el = articleRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    // hauteur estimée du tooltip (une ligne de ~24px par palier + le padding) pour
    // décider de l'afficher au-dessus si le bas de l'écran est trop proche.
    const estimatedHeight = medal.ranks.length * 24 + 24;
    const below = rect.bottom - 4;
    const top = below + estimatedHeight > window.innerHeight ? rect.top - estimatedHeight : below;
    setTip({ left: rect.left + 72, top }); // 72 = 64px de badge + 8px de gap (.entry { gap: 8px })
  };

  return (
    <article
      ref={articleRef}
      className={`${s.entry} ${complete ? s.complete : ''}`}
      onMouseEnter={showTip}
      onMouseLeave={() => setTip(null)}
    >
      <div className={s.badge}><MedalBadge score={rank.score} icon={medal.icon} complete={complete} /></div>
      <div className={s.paper} style={{ backgroundImage: `url(${tex(`${T.medals}/MedalPaper${complete ? 'Complete' : ''}`)})` }}>
        <header className={s.head}>
          <h3 className={s.name}>{medal.name}</h3>
          {medal.finishDate && <time className={s.date}>{formatGameDate(medal.finishDate)}</time>}
        </header>
        <p className={s.desc}>{rank.description}</p>
        {showBar && <div className={s.bar}><ProgressBar value={value} max={rank.completeProgress} /></div>}
        {conditions.length > 0 && (
          <ul className={s.conditions}>
            {conditions.map((c, i) => (
              <li key={i} className={c.success ? s.ok : s.ko}><span className={s.check}>✔</span>{c.description}</li>
            ))}
          </ul>
        )}
      </div>
      {tip && medal.ranks.length > 1 && (
        <div className={s.tooltip} style={{ left: tip.left, top: tip.top }}>
          {medal.ranks.map((r, i) => (
            <div key={i} className={`${s.tipRank} ${i < medal.currentRank ? s.tipDone : ''}`}>
              <span className={s.tipScore}>{r.score}</span>
              <span>{r.description}</span>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}
