import { useCallback, useEffect, useMemo, useState } from 'react';
import { T, tex, video } from '@/lib/assets';
import { navigate, useRoute } from '@/lib/router';
import { pick, useI18n } from '@/lib/i18n';
import { useGameAudio } from '@/lib/audio/useGameAudio';
import { GameStrip } from '@/components/ui/GameStrip';
import {
  FACTIONS, defaultSubtitleLang, filmDuration, filmFor, formatDuration, isFaction, loadCinematics,
  type CinematicsIndex, type Faction,
} from '@/lib/cinematics';
import { FilmPlayer } from './FilmPlayer';
import s from './CinematicsScreen.module.css';

/** Textures de l'écran de choix de faction du jeu (`Interface/Ingame/ChoiceFaction`). */
const BANNER: Record<Faction, string> = {
  league: `${T.choiceFaction}/ChoiceFactionBackLeague`,
  empire: `${T.choiceFaction}/ChoiceFactionBackEmpire`,
};

export function CinematicsScreen({ loader = loadCinematics }: { loader?: () => Promise<CinematicsIndex | null> }) {
  const { t, lang } = useI18n();
  const { query } = useRoute();
  const { playSfx, pauseMusic, resumeAmbient } = useGameAudio();
  const [index, setIndex] = useState<CinematicsIndex | null | undefined>(undefined);
  const faction = isFaction(query.get('faction')) ? (query.get('faction') as Faction) : null;

  useEffect(() => {
    let alive = true;
    loader().then(data => { if (alive) setIndex(data); });
    return () => { alive = false; };
  }, [loader]);

  useEffect(() => {
    const previous = document.title;
    document.title = `Allodex — ${t('cinematics.title')}`;
    return () => { document.title = previous; };
  }, [t]);

  // Le film a sa propre bande son : la musique du site se tait pendant la lecture.
  useEffect(() => {
    if (!faction) return;
    pauseMusic();
    return () => resumeAmbient({ crossfadeMs: 600 });
  }, [faction, pauseMusic, resumeAmbient]);

  const films = useMemo(() => {
    const all = index?.cinematics ?? [];
    return { league: filmFor(all, 'league'), empire: filmFor(all, 'empire') };
  }, [index]);

  const choose = useCallback((value: Faction) => {
    playSfx('ui-click');
    navigate(`/cinematics?faction=${value}`);
  }, [playSfx]);
  const back = useCallback(() => navigate('/cinematics'), []);
  const close = useCallback(() => { playSfx('medals-close'); navigate('/'); }, [playSfx]);

  if (index === undefined) return <main className={s.screen} aria-busy="true" />;

  if (faction && index && films[faction].length) {
    return (
      <main className={s.screen} aria-label={t('cinematics.title')}>
        <FilmPlayer key={faction} film={films[faction]} arcs={index.arcs} faction={faction}
          initialLang={defaultSubtitleLang(films[faction], lang)} onBack={back} onClose={close} />
      </main>
    );
  }

  const bg = video('mainmenu');
  return (
    <main className={s.screen} aria-label={t('cinematics.title')}>
      <video className={s.bg} autoPlay muted loop playsInline poster={tex(`${T.main2}/Background_14_0_Temp`)}>
        <source src={bg.webm} type="video/webm" /><source src={bg.mp4} type="video/mp4" />
      </video>
      <div className={s.plate}>
        <GameStrip base="title-plate" cap={38} />
        <h1 className={s.title}>{t('cinematics.title')}</h1>
      </div>
      <p className={s.lead}>{t('cinematics.choose')}</p>
      {!index || !index.cinematics.length ? (
        <p className={s.empty} role="status">{t('cinematics.missing')}</p>
      ) : (
        <div className={s.banners}>
          {FACTIONS.map(value => {
            const film = films[value];
            const arcs = [...new Set(film.map(c => c.arc))];
            return (
              <button key={value} type="button" className={s.banner} data-faction={value}
                onClick={() => choose(value)} disabled={!film.length} data-testid={`faction-${value}`}
                aria-label={`${t(value === 'league' ? 'cinematics.league' : 'cinematics.empire')} — ${t('cinematics.watch')}`}
                style={{ backgroundImage: `url(${tex(BANNER[value])})` }}>
                <span className={s.bannerName}>{t(value === 'league' ? 'cinematics.league' : 'cinematics.empire')}</span>
                <span className={s.parchment}>
                  <span className={s.summary}>
                    {t('cinematics.summary', { count: film.length, duration: formatDuration(filmDuration(film)) })}
                  </span>
                  <span className={s.arcs}>
                    {arcs.map(arc => (
                      <span key={arc} className={s.arcLine}>
                        <span>{pick(index.arcs[arc]?.title, lang) ?? arc}</span>
                        <span className={s.arcVersion}>{index.arcs[arc]?.version}</span>
                      </span>
                    ))}
                  </span>
                  <span className={s.watch}>{t('cinematics.watch')}</span>
                </span>
              </button>
            );
          })}
        </div>
      )}
      <p className={s.footnote}>{t('cinematics.footnote')}</p>
      <button type="button" className={s.home} onClick={close}>{t('legal.back')}</button>
    </main>
  );
}
