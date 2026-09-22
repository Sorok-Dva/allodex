import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { sprite } from '@/lib/assets';
import { pick, useI18n } from '@/lib/i18n';
import { nineSlice } from '@/lib/nineSlice';
import { ProgressBar } from '@/components/ui/ProgressBar';
import {
  chapterAt, chaptersOf, cinematicFile, filmDuration, filmTime, formatDuration, groupByArc, nextIndex,
  subtitleLangs, trackFor, type Cinematic, type CinematicArc, type Faction, type SubtitleLang,
} from '@/lib/cinematics';
import s from './FilmPlayer.module.css';

type Props = {
  film: Cinematic[];
  arcs: Record<string, CinematicArc>;
  faction: Faction;
  initialLang: SubtitleLang | null;
  onBack: () => void;
  onClose: () => void;
};

/** Format lu par ce navigateur : WebM (VP9/Opus) s'il sait, sinon MP4 (H.264/AAC). */
function preferredFormat(): 'webm' | 'mp4' {
  if (typeof document === 'undefined') return 'mp4';
  const probe = document.createElement('video');
  return typeof probe.canPlayType === 'function' && probe.canPlayType('video/webm; codecs="vp9, opus"') ? 'webm' : 'mp4';
}

const TITLE_CARD_MS = 4200;

/**
 * Lecture « film complet » : deux lecteurs vidéo se relaient. Pendant qu'un chapitre joue,
 * l'autre lecteur, caché et muet, précharge le suivant ; à la fin, on bascule de l'un à
 * l'autre sans temps de chargement, puis le lecteur libéré précharge le chapitre d'après.
 */
export function FilmPlayer({ film, arcs, faction, initialLang, onBack, onClose }: Props) {
  const { t, lang } = useI18n();
  const chapters = useMemo(() => chaptersOf(film), [film]);
  const total = useMemo(() => filmDuration(film), [film]);
  const langs = useMemo(() => subtitleLangs(film), [film]);
  const format = useMemo(preferredFormat, []);

  // slots[k] = index du chapitre chargé dans le lecteur k ; `active` = lecteur visible.
  const [slots, setSlots] = useState<[number | null, number | null]>([0, nextIndex(film, 0)]);
  const [active, setActive] = useState<0 | 1>(0);
  const [time, setTime] = useState(0);
  const [paused, setPaused] = useState(false);
  const [ended, setEnded] = useState(false);
  const [subLang, setSubLang] = useState<SubtitleLang | null>(initialLang);
  const [panelOpen, setPanelOpen] = useState(true);
  const [card, setCard] = useState(0);
  const video0 = useRef<HTMLVideoElement>(null);
  const video1 = useRef<HTMLVideoElement>(null);
  const videos = useMemo(() => [video0, video1] as const, []);
  const pendingSeek = useRef<number | null>(null);

  const current = slots[active] ?? 0;
  const cinematic = film[current];

  const play = useCallback((video: HTMLVideoElement | null) => {
    if (!video) return;
    const p = video.play?.();
    if (p && typeof p.catch === 'function') p.catch(() => setPaused(true));
  }, []);

  /** Affiche le chapitre `index` : bascule sur le lecteur qui l'a préchargé, sinon charge. */
  const goTo = useCallback((index: number, at = 0) => {
    setEnded(false);
    setPaused(false);
    setCard(c => c + 1);
    setTime(at);
    const other: 0 | 1 = active === 0 ? 1 : 0;
    const next = nextIndex(film, index);
    const out: [number | null, number | null] = [null, null];
    pendingSeek.current = at || null;
    videos[active].current?.pause();
    if (slots[other] === index) {
      // Le chapitre attendait, préchargé : on montre ce lecteur et l'autre prend la suite.
      out[other] = index;
      out[active] = next;
      setActive(other);
      const video = videos[other].current;
      if (video) {
        if (at) { video.currentTime = at; pendingSeek.current = null; }
        play(video);
      }
    } else {
      out[active] = index;
      out[other] = next;
    }
    setSlots(out);
  }, [active, slots, film, play, videos]);

  // Chapitre chargé dans le lecteur visible : lecture (dès les métadonnées si besoin).
  useEffect(() => {
    const video = videos[active].current;
    if (!video) return;
    if (video.readyState >= 1 && pendingSeek.current !== null) {
      video.currentTime = pendingSeek.current;
      pendingSeek.current = null;
    }
    if (!ended) play(video);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slots, active]);

  // Pistes de sous-titres : seule la langue choisie s'affiche, sur les deux lecteurs ; le
  // lecteur caché reste muet (propriété `muted`, que React ne met pas à jour après le montage).
  useEffect(() => {
    videos.forEach((ref, k) => { if (ref.current) ref.current.muted = k !== active; });
    for (const ref of videos) {
      const tracks = ref.current?.textTracks;
      if (!tracks) continue;
      for (let i = 0; i < tracks.length; i++) {
        tracks[i].mode = subLang && tracks[i].language === subLang ? 'showing' : 'disabled';
      }
    }
  });

  // Carton de titre au début de chaque chapitre.
  const [cardVisible, setCardVisible] = useState(true);
  useEffect(() => {
    setCardVisible(true);
    const timer = window.setTimeout(() => setCardVisible(false), TITLE_CARD_MS);
    return () => window.clearTimeout(timer);
  }, [card]);

  const onEnded = useCallback(() => {
    const next = nextIndex(film, current);
    if (next === null) { setEnded(true); setPaused(true); return; }
    goTo(next);
  }, [film, current, goTo]);

  const togglePlay = useCallback(() => {
    const video = videos[active].current;
    if (!video) return;
    if (ended) { goTo(0); return; }
    if (video.paused) { play(video); setPaused(false); } else { video.pause(); setPaused(true); }
  }, [active, ended, goTo, play, videos]);

  const seekFilm = useCallback((t: number) => {
    const index = chapterAt(chapters, t);
    const at = Math.max(0, t - chapters[index].start);
    if (index === current) {
      const video = videos[active].current;
      if (video) video.currentTime = at;
      setTime(at);
    } else {
      goTo(index, at);
    }
  }, [active, chapters, current, goTo, videos]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement && event.target.type !== 'range') return;
      if (event.key === ' ') { event.preventDefault(); togglePlay(); }
      else if (event.key === 'ArrowRight' && event.shiftKey) { const n = nextIndex(film, current); if (n !== null) goTo(n); }
      else if (event.key === 'ArrowLeft' && event.shiftKey) { goTo(Math.max(0, current - 1)); }
      else if (event.key === 'Escape') onBack();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [togglePlay, goTo, film, current, onBack]);

  const position = filmTime(chapters, current, time);
  const arcTitle = (id: string) => pick(arcs[id]?.title, lang) ?? id;
  const title = (c: Cinematic) => pick(c.title, lang) ?? c.id;

  return (
    <div className={s.player} data-faction={faction}>
      <div className={s.stage}>
        {([0, 1] as const).map(k => {
          const index = slots[k];
          const c = index === null ? null : film[index];
          const visible = k === active;
          return (
            <video
              key={k}
              ref={videos[k]}
              className={`${s.video} ${visible ? s.visible : s.hidden}`}
              src={c?.files ? cinematicFile(c.files[format]) : undefined}
              poster={c?.files ? cinematicFile(c.files.poster) : undefined}
              preload={visible ? 'auto' : c ? 'auto' : 'none'}
              muted={!visible}
              playsInline
              data-testid={`film-video-${k}`}
              data-chapter={c?.id ?? ''}
              aria-hidden={!visible}
              onClick={visible ? togglePlay : undefined}
              onLoadedMetadata={visible ? event => {
                if (pendingSeek.current !== null) { event.currentTarget.currentTime = pendingSeek.current; pendingSeek.current = null; }
              } : undefined}
              onTimeUpdate={visible ? event => setTime(event.currentTarget.currentTime) : undefined}
              onEnded={visible ? onEnded : undefined}
              onPlay={visible ? () => setPaused(false) : undefined}
              onPause={visible ? () => setPaused(true) : undefined}
            >
              {c?.tracks.map(track => (
                <track key={`${c.id}-${track.lang}`} kind="subtitles" srcLang={track.lang} label={track.label}
                  src={cinematicFile(track.src)} default={track.lang === subLang} />
              ))}
            </video>
          );
        })}

        {cinematic && !ended && (
          <div className={`${s.card} ${cardVisible ? s.cardIn : s.cardOut}`} aria-live="polite" data-testid="title-card">
            <span className={s.cardArc}>{arcTitle(cinematic.arc)} · {cinematic.version}</span>
            <span className={s.cardTitle}>{title(cinematic)}</span>
          </div>
        )}

        {ended && (
          <div className={s.end} role="dialog" aria-label={t('cinematics.end')}>
            <span className={s.endTitle}>{t('cinematics.end')}</span>
            <div className={s.endActions}>
              <button type="button" className={s.pill} style={nineSlice('pill-full', [0, 24, 0, 24], { fill: true })} onClick={() => goTo(0)}>{t('cinematics.replay')}</button>
              <button type="button" className={s.pill} style={nineSlice('pill-full', [0, 24, 0, 24], { fill: true })} onClick={onBack}>{t('cinematics.back')}</button>
            </div>
          </div>
        )}
      </div>

      <aside className={`${s.panel} ${panelOpen ? s.panelOpen : ''}`} aria-label={t('cinematics.chapters')} inert={!panelOpen}>
        <h2 className={s.panelTitle}>{t('cinematics.chapters')}</h2>
        <div className={s.panelScroll}>
          {groupByArc(chapters).map(group => (
            <section key={`${group.arc}-${group.items[0].index}`} className={s.arc}>
              <h3 className={s.arcTitle}>{arcTitle(group.arc)} <span>{arcs[group.arc]?.version}</span></h3>
              <ol className={s.chapterList} start={group.items[0].index + 1}>
                {group.items.map(({ chapter, index }) => {
                  const c = chapter.cinematic;
                  const isCurrent = index === current;
                  return (
                    <li key={c.id}>
                      <button type="button" className={s.chapter} aria-current={isCurrent ? 'true' : undefined}
                        onClick={() => goTo(index)} data-testid={`chapter-${c.id}`}>
                        {isCurrent && <span className={s.chapterSkin} aria-hidden="true" style={nineSlice('pill-full-open', [0, 24, 0, 24], { fill: true })} />}
                        {c.files && <img className={s.thumb} src={cinematicFile(c.files.poster)} alt="" loading="lazy" />}
                        <span className={s.chapterText}>
                          <span className={s.chapterTitle}>{index + 1}. {title(c)}</span>
                          <span className={s.chapterMeta}>
                            {formatDuration(c.duration)}
                            {c.subtitles.status === 'official' ? '' : ` · ${c.audio.language ? t('cinematics.noSubtitles') : t('cinematics.noDialogue')}`}
                          </span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ol>
            </section>
          ))}
        </div>
      </aside>

      <div className={s.controls}>
        <button type="button" className={s.medallion} onClick={() => goTo(Math.max(0, current - 1))}
          aria-label={t('cinematics.previous')} title={t('cinematics.previous')} disabled={current === 0}
          style={{ backgroundImage: `url(${sprite('medallion-normal')})` }}>
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 2.5h2v11H3zM13 2.5v11L5.5 8z" fill="currentColor" /></svg>
        </button>
        <button type="button" className={`${s.medallion} ${s.big}`} onClick={togglePlay}
          aria-label={paused ? t('cinematics.play') : t('cinematics.pause')} title={paused ? t('cinematics.play') : t('cinematics.pause')}
          style={{ backgroundImage: `url(${sprite('medallion-normal')})` }} data-testid="film-toggle">
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path d={paused ? 'M4.5 2.5 13 8l-8.5 5.5z' : 'M4 2.5h3v11H4zM9 2.5h3v11H9z'} fill="currentColor" />
          </svg>
        </button>
        <button type="button" className={s.medallion} onClick={() => { const n = nextIndex(film, current); if (n !== null) goTo(n); }}
          aria-label={t('cinematics.next')} title={t('cinematics.next')} disabled={nextIndex(film, current) === null}
          style={{ backgroundImage: `url(${sprite('medallion-normal')})` }}>
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M11 2.5h2v11h-2zM3 2.5v11L10.5 8z" fill="currentColor" /></svg>
        </button>

        <div className={s.timeline}>
          <div className={s.nowPlaying}>
            <span className={s.nowArc}>{cinematic && arcTitle(cinematic.arc)}</span>
            <span className={s.nowTitle}>{cinematic && title(cinematic)}</span>
          </div>
          <div className={s.seekRow}>
            <span className={s.time}>{formatDuration(position)}</span>
            <div className={s.seek}>
              <ProgressBar value={position} max={total} label="" />
              {chapters.slice(1).map(ch => (
                <span key={ch.cinematic.id} className={s.tick} style={{ left: `${(ch.start / total) * 100}%` }} aria-hidden="true" />
              ))}
              <input type="range" min={0} max={total} step={0.5} value={Math.min(position, total)}
                aria-label={t('cinematics.seek')} aria-valuetext={`${formatDuration(position)} / ${formatDuration(total)}`}
                onChange={event => seekFilm(Number(event.target.value))} />
            </div>
            <span className={s.time}>{formatDuration(total)}</span>
          </div>
        </div>

        <div className={s.subtitles} role="group" aria-label={t('cinematics.subtitles')}>
          <span className={s.subtitlesLabel}>{t('cinematics.subtitles')}</span>
          {langs.map(l => (
            <button key={l} type="button" className={s.langButton} aria-pressed={subLang === l}
              onClick={() => setSubLang(l)}>{l.toUpperCase()}</button>
          ))}
          <button type="button" className={s.langButton} aria-pressed={subLang === null} onClick={() => setSubLang(null)}>
            {t('cinematics.subtitlesOff')}
          </button>
        </div>

        <button type="button" className={s.pill} style={nineSlice(panelOpen ? 'pill-full-open' : 'pill-full', [0, 24, 0, 24], { fill: true })}
          aria-pressed={panelOpen} onClick={() => setPanelOpen(open => !open)}>{t('cinematics.chapters')}</button>
        <button type="button" className={s.pill} style={nineSlice('pill-full', [0, 24, 0, 24], { fill: true })} onClick={onBack}>
          {t('cinematics.back')}
        </button>
        <button type="button" className={s.close} onClick={onClose} aria-label={t('common.close')} title={t('common.close')}
          style={{ backgroundImage: `url(${sprite('close-button')})` }} />
      </div>

      {cinematic && trackFor(cinematic, subLang) === null && cinematic.audio.language && subLang && (
        <p className={s.notice} role="status">{t('cinematics.noSubtitles')}</p>
      )}
    </div>
  );
}
