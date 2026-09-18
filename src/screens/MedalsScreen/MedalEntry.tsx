import { useState } from 'react';
import type { Medal } from '@/data/medals.types';
import { currentRankOf, isComplete } from '@/data/medals.logic';
import { T, tex } from '@/lib/assets';
import { MedalBadge } from '@/components/game/MedalBadge';
import { ProgressBar } from '@/components/game/ProgressBar';
import { formatGameDate } from './formatDate';
import s from './MedalEntry.module.css';

export function MedalEntry({ medal }: { medal: Medal }) {
  const complete = isComplete(medal);
  const rank = currentRankOf(medal);
  const [tip, setTip] = useState(false);
  const conditions = [...(medal.dressCollection ?? []), ...(medal.medalCollection ?? [])];
  const showBar = rank.completeProgress > 1;
  const value = complete ? rank.completeProgress : medal.progress?.value ?? 0;

  return (
    <article className={`${s.entry} ${complete ? s.complete : ''}`} onMouseEnter={() => setTip(true)} onMouseLeave={() => setTip(false)}>
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
        <div className={s.tooltip}>
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
