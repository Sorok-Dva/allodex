import { useContext } from 'react';
import { AudioProgressContext } from '@/lib/audio/AudioProvider';
import { useGameAudio } from '@/lib/audio/useGameAudio';
import { useI18n } from '@/lib/i18n';
import { ProgressBar } from '@/components/game/ProgressBar';
import { Duration, formatDuration } from '@/screens/ChroniclesScreen/ThemePlayer';
import s from './MusicScreen.module.css';

export function MusicProgress({ title }: { title: string }) {
  const { position, duration } = useContext(AudioProgressContext);
  const { seekMusic } = useGameAudio();
  const { t } = useI18n();
  return <div className={s.transport}>
    <div className={s.transportTitle} title={title}>{title}</div>
    <div className={s.timeline}>
      <Duration seconds={position} />
      <div className={s.seek}>
        <ProgressBar value={position} max={duration} label="" />
        <input type="range" min={0} max={duration || 0} step={0.1}
          value={Math.min(position, duration)} disabled={duration <= 0}
          aria-label={t('music.seek')} aria-valuetext={`${formatDuration(position)} / ${formatDuration(duration)}`}
          onChange={event => seekMusic(Number(event.target.value))} />
      </div>
      <Duration seconds={duration} />
    </div>
  </div>;
}
