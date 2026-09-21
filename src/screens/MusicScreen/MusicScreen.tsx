import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { musicTracks, sprite, T, tex, video, type MusicTrack } from '@/lib/assets';
import { navigate } from '@/lib/router';
import { pick, useI18n } from '@/lib/i18n';
import type { MessageKey } from '@/lib/i18n/messages';
import { useGameAudio } from '@/lib/audio/useGameAudio';
import { nineSlice } from '@/lib/nineSlice';
import { GameScrollbar } from '@/components/ui/GameScrollbar';
import { musicArchiveConfidence, musicArchiveNote, musicGroup, musicIntroducedIn, musicMaps, musicZone, musicSubcategories, musicQueueKey } from '@/data/music.logic';
import { MedalsWindow } from '@/screens/MedalsScreen/MedalsWindow';
import { Duration } from '@/screens/ChroniclesScreen/ThemePlayer';
import player from '@/screens/ChroniclesScreen/ThemePlayer.module.css';
import s from './MusicScreen.module.css';
import navStyles from '@/screens/MedalsScreen/MedalsNavigation.module.css';
import { MusicProgress } from './MusicProgress';

const GROUP_KEYS: Record<string, MessageKey> = {
  Menu: 'music.group.menu', Zones: 'music.group.zones', 'Zones de départ': 'music.group.start',
  Races: 'music.group.races', 'Instruments des races': 'music.group.instruments',
  Astral: 'music.group.astral', 'Donjons/Combat': 'music.group.combat',
  Eden: 'music.group.eden', Jigran: 'music.group.jigran', Kadagan: 'music.group.kadagan',
  Kvator: 'music.group.kvator', Isa: 'music.group.isa',
};

export function cleanMusicName(name: string): string {
  return name.replace(/\.(wav|mp3|ogg|fsb)$/i, '').replace(/(?:_NM|_?adaptive)+$/i, '').replace(/_/g, ' ').replace(/\bKadagan\b/gi, 'Xadagan').trim();
}
const normalizeSearch = (value: string) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/_/g, ' ');

const CONFIDENCE_LABELS = {
  fr: { confirmed: 'confirmée', probable: 'probable', inferred: 'déduite', unknown: 'inconnue' },
  en: { confirmed: 'confirmed', probable: 'probable', inferred: 'inferred', unknown: 'unknown' },
} as const;

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
  const groups = useMemo(() => [...new Set(tracks.map(musicGroup))], [tracks]);
  const zones = useMemo(() => musicSubcategories(tracks), [tracks]);
  const [group, setGroup] = useState(groups[0] ?? '');
  const [zonesOpen, setZonesOpen] = useState(false);
  const [zoneId, setZoneId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [current, setCurrent] = useState<MusicTrack | null>(null);
  const [pos, setPos] = useState(placement);
  const listRef = useRef<HTMLDivElement>(null);
  const navRef = useRef<HTMLDivElement>(null);
  const consumedEnd = useRef<string | null>(null);
  const { t, lang } = useI18n();
  const { playSfx, pauseMusic, resumeAmbient, playExternal, playing, external, ended } = useGameAudio();
  const groupLabel = (value: string) => GROUP_KEYS[value] ? t(GROUP_KEYS[value]) : value;
  const title = (track: MusicTrack) => pick(track.title ?? undefined, lang) ?? cleanMusicName(track.name);
  const metadataLine = (track: MusicTrack) => {
    const parts = [track.name];
    const maps = musicMaps(track);
    const introducedIn = musicIntroducedIn(track);
    if (maps.length) parts.push(maps.join(', '));
    if (introducedIn) parts.push(`v${introducedIn}`);
    return parts.join(' · ');
  };
  const metadataTooltip = (track: MusicTrack) => {
    const maps = musicMaps(track);
    const introducedIn = musicIntroducedIn(track);
    const confidence = musicArchiveConfidence(track);
    const note = musicArchiveNote(track);
    const lines = [track.name];
    if (maps.length) lines.push(`${lang === 'fr' ? 'Zone' : 'Map'}: ${maps.join(', ')}`);
    if (introducedIn) lines.push(`${lang === 'fr' ? 'Mise à jour' : 'Update'}: ${introducedIn}`);
    if (maps.length || introducedIn) lines.push(`${lang === 'fr' ? 'Confiance' : 'Confidence'}: ${CONFIDENCE_LABELS[lang][confidence]}`);
    if (note) lines.push(note);
    return lines.join('\n');
  };
  const search = normalizeSearch(query.trim());
  const visible = tracks.filter(track => search
    ? normalizeSearch(`${title(track)} ${track.name} ${musicMaps(track).join(' ')} ${musicIntroducedIn(track) ?? ''} ${pick(musicZone(track)?.title, lang) ?? ''}`).includes(search)
    : musicGroup(track) === group && (!zoneId || musicZone(track)?.id === zoneId));
  const heading = search ? t('music.results', { count: visible.length }) : pick(zones.find(zone => zone.id === zoneId)?.title, lang) ?? groupLabel(group);
  const bg = video('mainmenu');

  const play = useCallback((track: MusicTrack) => {
    setCurrent(track);
    playExternal(`music:${track.id}`, { ogg: track.ogg, mp3: track.mp3 }, { loop: false, crossfadeMs: 600 });
  }, [playExternal]);

  useEffect(() => {
    const previousTitle = document.title;
    document.title = `Allodex — ${t('music.title')}`;
    return () => { document.title = previousTitle; };
  }, [t]);

  useEffect(() => {
    playSfx('medals-open');
    if (tracks[0]) {
      play(tracks[0]);
    } else {
      pauseMusic();
    }
    return () => { pauseMusic(); resumeAmbient({ crossfadeMs: 600 }); };
  }, [playSfx, pauseMusic, resumeAmbient, tracks, play]);

  useEffect(() => {
    const resize = () => setPos(placement());
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, []);

  useEffect(() => {
    if (!ended) { consumedEnd.current = null; return; }
    if (!current || ended !== `music:${current.id}` || consumedEnd.current === ended) return;
    consumedEnd.current = ended;
    const queue = tracks.filter(track => musicQueueKey(track) === musicQueueKey(current));
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
          onClose={close} closeLabel={t('common.close')}
          nav={<nav className={s.column} aria-label={t('music.groups')}>
            <div className={navStyles.search}>
              <span className={navStyles.searchFrame} style={nineSlice('search-field', [5, 6, 5, 6], { fill: true })} aria-hidden="true" />
              <input type="search" className={navStyles.searchInput} value={query}
                placeholder={t('music.searchPlaceholder')} aria-label={t('music.search')} spellCheck={false}
                onChange={event => { setQuery(event.target.value); if (listRef.current) listRef.current.scrollTop = 0; }} />
            </div>
            <div className={s.navViewport} ref={navRef}>
              {groups.map(value => <div key={value}>
                <button type="button" className={`${s.group} ${value === 'Zones' ? s.foldable : ''}`}
                aria-pressed={!search && value === group}
                aria-expanded={value === 'Zones' ? zonesOpen : undefined}
                aria-controls={value === 'Zones' ? 'music-zones' : undefined}
                style={{ backgroundImage: `url(${sprite(!search && value === group ? 'pill-full-open' : 'pill-full')})` }}
                onClick={() => { setQuery(''); setGroup(value); setZoneId(null); if (value === 'Zones') setZonesOpen(open => !open); if (listRef.current) listRef.current.scrollTop = 0; }}>
                {groupLabel(value)}
                {value === 'Zones' && <span className={navStyles.medallion} aria-hidden="true" style={{ backgroundImage: `url(${sprite(zonesOpen ? 'medallion-minus' : 'medallion-plus')})` }} />}
              </button>
              {value === 'Zones' && zonesOpen && <div id="music-zones" className={navStyles.subWrap} style={{ height: zones.length * 23 + 27 }}>
                <span className={navStyles.parchment} aria-hidden="true" style={{ backgroundImage: `url(${tex(`${T.medals}/CategoryContent`)})` }} />
                <ul className={navStyles.subList}>
                  {zones.map((zone, index) => <li key={zone.id}>
                    <button type="button" className={`${navStyles.subRow} ${!search && zoneId === zone.id ? navStyles.subActive : ''}`}
                      style={{ top: 12 + index * 23 }} aria-pressed={!search && zoneId === zone.id}
                      onClick={() => { setQuery(''); setGroup('Zones'); setZoneId(zone.id); if (listRef.current) listRef.current.scrollTop = 0; }}>
                      {pick(zone.title, lang)} · {zone.tracks.length}
                    </button>
                  </li>)}
                </ul>
              </div>}
              </div>)}
            </div>
            <GameScrollbar targetRef={navRef} className={s.navScrollbar} />
          </nav>}
          content={<section className={`${s.column} ${s.withPlayer}`} aria-label={heading || t('music.title')}>
            {!tracks.length ? <p className={s.empty}>{t('music.missing')}</p> : <>
              <h1 className={s.heading}>{heading}</h1>
              <div className={s.viewport} ref={listRef}>
                {!visible.length && <p className={s.empty} role="status">{t('music.noResults')}</p>}
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
                      <div className={s.trackText}>
                        <div className={s.title} title={title(track)}>{title(track)}</div>
                        <div className={s.internal} title={metadataTooltip(track)}>{metadataLine(track)}</div>
                      </div>
                      <Duration seconds={track.duration} />
                    </li>;
                  })}
                </ul>
              </div>
              <GameScrollbar targetRef={listRef} className={s.scrollbar} />
            </>}
            <MusicProgress title={current ? title(current) : null} />
          </section>}
        />
      </div>
    </main>
  );
}
