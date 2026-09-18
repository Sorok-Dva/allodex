import { T, tex } from '@/lib/assets';
import { frameForScore } from '@/data/medals.logic';
import s from './MedalBadge.module.css';

export function MedalBadge({ score, icon, complete }: { score: number; icon: string; complete: boolean }) {
  const frame = `${T.medals}/MedalFrame${complete ? 'Complete' : ''}${frameForScore(score)}`;
  return (
    <div className={s.badge} style={{ backgroundImage: `url(${tex(frame)})` }}>
      <img className={s.icon} src={tex(icon)} alt="" draggable={false} />
      <span className={s.score}>{score}</span>
    </div>
  );
}
