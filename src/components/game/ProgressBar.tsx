import { T, tex } from '@/lib/assets';
import s from './ProgressBar.module.css';

export function ProgressBar({ value, max, label }: { value: number; max: number; label?: string }) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  return (
    <div className={s.bar} style={{ backgroundImage: `url(${tex(`${T.medals}/ProgressBar`)})` }}>
      <div className={s.gauge} style={{ width: `${pct}%`, backgroundImage: `url(${tex(`${T.medals}/ProgressBarGauge`)})` }} />
      <span className={s.text}>{label ?? `${value.toLocaleString('fr-FR')} sur ${max.toLocaleString('fr-FR')}`}</span>
    </div>
  );
}
