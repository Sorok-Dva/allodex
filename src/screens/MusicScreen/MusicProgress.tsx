import { useContext, useEffect, useRef, useState } from 'react';
import { AudioProgressContext } from '@/lib/audio/AudioProvider';
import { useGameAudio } from '@/lib/audio/useGameAudio';
import { useI18n } from '@/lib/i18n';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { Duration, formatDuration } from '@/screens/ChroniclesScreen/ThemePlayer';
import s from './MusicScreen.module.css';
import { SpeakerToggle } from '@/components/controls/SpeakerToggle';

export function MusicProgress({ title }: { title: string | null }) {
  const progress = useContext(AudioProgressContext);
  const position = title ? progress.position : 0;
  const duration = title ? progress.duration : 0;
  const { seekMusic, volume, setVolume, muted, toggleMuted } = useGameAudio();
  const { t } = useI18n();
  const [volumeOpen, setVolumeOpen] = useState(false);
  const volumeRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!volumeOpen) return;
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !volumeRef.current?.contains(event.target)) setVolumeOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setVolumeOpen(false); volumeRef.current?.querySelector('button')?.focus(); }
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape); };
  }, [volumeOpen]);
  return <div className={s.transport}>
    <div className={s.playback}>
    <div className={s.transportTitle} title={title ?? undefined}>{title ?? t('music.chooseTrack')}</div>
    <div className={s.timeline}>
      <Duration seconds={position} />
      <div className={s.seek}>
        <ProgressBar value={position} max={duration} label="" />
        <input type="range" min={0} max={duration || 0} step={0.1}
          value={Math.min(position, duration)} disabled={!title || duration <= 0}
          aria-label={t('music.seek')} aria-valuetext={`${formatDuration(position)} / ${formatDuration(duration)}`}
          onChange={event => seekMusic(Number(event.target.value))} />
      </div>
      <Duration seconds={duration} />
    </div>
    </div>
    <div className={s.volumeControl} ref={volumeRef}>
      <SpeakerToggle onClick={() => setVolumeOpen(open => !open)} expanded={volumeOpen} controls="music-volume-controls" label={t('audio.adjustVolume')} />
      <div className={`${s.volumeReveal} ${volumeOpen ? s.volumeOpen : ''}`} inert={!volumeOpen} aria-hidden={!volumeOpen} id="music-volume-controls">
      <div className={s.volumeSlider}>
        <label htmlFor="music-volume">{t('audio.volume')} <span>{Math.round((muted ? 0 : volume) * 100)} %</span></label>
        <div className={s.seek}>
          <ProgressBar value={muted ? 0 : volume} max={1} label="" />
          <input id="music-volume" type="range" min={0} max={100} step={1} value={Math.round((muted ? 0 : volume) * 100)}
            aria-label={t('audio.volume')} aria-valuetext={`${Math.round((muted ? 0 : volume) * 100)} %`}
            onChange={event => { const next = Number(event.target.value) / 100; setVolume(next); if (muted && next > 0) toggleMuted(); }} />
        </div>
      </div>
      </div>
    </div>
  </div>;
}
