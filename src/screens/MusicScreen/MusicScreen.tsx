import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { musicTracks, sprite, T, tex, video, type MusicTrack } from '@/lib/assets';
import { navigate } from '@/lib/router';
import { pick, useI18n } from '@/lib/i18n';
import type { MessageKey } from '@/lib/i18n/messages';
import { useGameAudio } from '@/lib/audio/useGameAudio';
import { nineSlice } from '@/lib/nineSlice';
import { GameScrollbar } from '@/components/game/GameScrollbar';
import { SpeakerToggle } from '@/components/game/SpeakerToggle';
import { MedalsWindow } from '@/screens/MedalsScreen/MedalsWindow';
import { Duration } from '@/screens/ChroniclesScreen/ThemePlayer';
import player from '@/screens/ChroniclesScreen/ThemePlayer.module.css';
import s from './MusicScreen.module.css';

const GROUP_KEYS: Record<string, MessageKey> = {
  Menu: 'music.group.menu', Zones: 'music.group.zones', 'Zones de départ': 'music.group.start',
  Peuples: 'music.group.races', 'Instruments des peuples': 'music.group.instruments',
  Astral: 'music.group.astral', 'Donjons/Combat': 'music.group.combat',
  Eden: 'music.group.eden', Jigran: 'music.group.jigran', Kadagan: 'music.group.kadagan',
  Kvator: 'music.group.kvator', Isa: 'music.group.isa',
};

export function cleanMusicName(name: string): string {
  return name.replace(/\.(wav|mp3|ogg|fsb)$/i, '').replace(/(?:_NM|_?adaptive)+$/i, '').replace(/_/g, ' ').trim();
}

function placement() {
  const scale = Math.min(1, (window.innerWidth - 12) / 890, (window.innerHeight - 76) / 592);
  return {
    left: Math.max(6, Math.floor((window.innerWidth - 886 * scale) / 2) + 1),
    top: Math.max(64, Math.floor((window.innerHeight - 592 * scale) / 2) - 17),
    transform: `scale(${Math.max(0.1, scale)})`,
  };
}

export function MusicScreen() {
  const tracks = useMemo(() => musicTracks(), []);
  const groups = useMemo(() => [...new Set(tracks.map(track => track.group))], [tracks]);
  const [group, setGroup] = useState(groups[0] ?? '');
  const [current, setCurrent] = useState<MusicTrack | null>(null);
  const [pos, setPos] = useState(placement);
  const listRef = useRef<HTMLDivElement>(null);
  const navRef = useRef<HTMLDivElement>(null);
  const consumedEnd = useRef<string | null>(null);
  const { t, lang } = useI18n();
  const { playSfx, pauseMusic, resumeAmbient, playExternal, playing, external, ended } = useGameAudio();
  const visible = tracks.filter(track => track.group === group);
  const groupLabel = (value: string) => GROUP_KEYS[value] ? t(GROUP_KEYS[value]) : value;
  const title = (track: MusicTrack) => pick(track.title ?? undefined, lang) ?? cleanMusicName(track.name);
  const bg = video('mainmenu');

  useEffect(() => {
    const previousTitle = document.title;
    document.title = `Allodex — ${t('music.title')}`;
    return () => { document.title = previousTitle; };
  }, [t]);

  useEffect(() => {
    playSfx('medals-open');
    pauseMusic();
    return () => { pauseMusic(); resumeAmbient({ crossfadeMs: 600 }); };
  }, [playSfx, pauseMusic, resumeAmbient]);

  useEffect(() => {
    const resize = () => setPos(placement());
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, []);

  const play = useCallback((track: MusicTrack) => {
    setCurrent(track);
    playExternal(`music:${track.id}`, { ogg: track.ogg, mp3: track.mp3 }, { loop: false, crossfadeMs: 600 });
  }, [playExternal]);

  useEffect(() => {
    if (!ended) { consumedEnd.current = null; return; }
    if (!current || ended !== `music:${current.id}` || consumedEnd.current === ended) return;
    consumedEnd.current = ended;
    const queue = tracks.filter(track => track.group === current.group);
    const next = queue[(queue.findIndex(track => track.id === current.id) + 1) % queue.length];
    if (next && next.id !== current.id) play(next);
  }, [ended, current, tracks, play]);

  const close = () => { playSfx('medals-close'); navigate('/'); };

  return (
    <main className={s.screen} aria-label={t('music.title')}>
      <video className={s.bg} autoPlay muted loop playsInline poster={tex(`${T.main2}/Background_14_0_Temp`)}>
        <source src={bg.webm} type="video/webm" /><source src={bg.mp4} type="video/mp4" />
      </video>
      <div className={s.holder} style={pos}>
        <MedalsWindow title={t('music.title')} subtitle={t('music.count', { count: tracks.length })}
          onClose={close} externalClose
          nav={<nav className={s.column} aria-label={t('music.groups')}>
            <div className={s.navViewport} ref={navRef}>
              {groups.map(value => <button key={value} type="button" className={s.group}
                aria-pressed={value === group}
                style={{ backgroundImage: `url(${sprite(value === group ? 'pill-full-open' : 'pill-full')})` }}
                onClick={() => { setGroup(value); if (listRef.current) listRef.current.scrollTop = 0; }}>
                {groupLabel(value)}
              </button>)}
            </div>
            <GameScrollbar targetRef={navRef} className={s.navScrollbar} />
          </nav>}
          content={<section className={s.column} aria-label={groupLabel(group) || t('music.title')}>
            {!tracks.length ? <p className={s.empty}>{t('music.missing')}</p> : <>
              <h1 className={s.heading}>{groupLabel(group)}</h1>
              <div className={s.viewport} ref={listRef}>
                <ul className={s.list}>
                  {visible.map(track => {
                    const active = external === `music:${track.id}`;
                    const isPlaying = active && playing;
                    return <li key={track.id} className={s.row} aria-current={active ? 'true' : undefined}>
                      {active && <span className={s.activeSkin} aria-hidden="true" style={nineSlice('pill-full-open', [0, 24, 0, 24], { fill: true })} />}
                      <button type="button" className={player.button}
                        aria-label={t(isPlaying ? 'music.pause' : 'music.play', { title: title(track) })}
                        onClick={() => { if (isPlaying) pauseMusic(); else play(track); }}>
                        <span className={player.buttonSkin} aria-hidden="true" style={nineSlice('pill-full', [0, 24, 0, 24], { fill: true })} />
                        <svg className={player.glyph} viewBox="0 0 16 16" aria-hidden="true">
                          <path d={isPlaying ? 'M4 2.5h3v11H4zM9 2.5h3v11H9z' : 'M4.5 2.5 13 8l-8.5 5.5z'} fill="currentColor" />
                        </svg>
                      </button>
                      <div className={s.trackText}><div className={s.title} title={title(track)}>{title(track)}</div><div className={s.internal} title={track.name}>{track.name}</div></div>
                      <Duration seconds={track.duration} />
                    </li>;
                  })}
                </ul>
              </div>
              <GameScrollbar targetRef={listRef} className={s.scrollbar} />
            </>}
          </section>}
        />
      </div>
      <button type="button" className={s.close} aria-label={t('common.close')}
        style={{ backgroundImage: `url(${sprite('close-button')})` }} onClick={close} />
      <SpeakerToggle className={s.speaker} />
    </main>
  );
}
