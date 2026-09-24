import { useCallback, useEffect, useMemo, useState } from 'react';
import { T, tex, video } from '@/lib/assets';
import { navigate, useRoute } from '@/lib/router';
import { pick, useI18n } from '@/lib/i18n';
import { useGameAudio } from '@/lib/audio/useGameAudio';
import { GameWindow, WINDOW_HEIGHT, WINDOW_MIN_WIDTH } from '@/components/ui/GameWindow';
import {
  FACTIONS, defaultSubtitleLang, filmDuration, filmFor, formatDuration, isFaction, loadCinematics, splitBonus,
  type CinematicsIndex, type Faction,
} from '@/lib/cinematics';
import { FilmPlayer } from './FilmPlayer';
import s from './CinematicsScreen.module.css';

/** Largeur de la fenêtre : celle de l'hôtel des ventes (857), réduite à 453 sur petit écran. */
const WIDE = 857;
/** Petit écran : fenêtre étroite, bannières empilées dans un corps qui défile. */
const NARROW_BELOW = 700;

function windowPlacement() {
  const vw = typeof window === 'undefined' ? 1920 : window.innerWidth;
  const vh = typeof window === 'undefined' ? 1080 : window.innerHeight;
  const narrow = vw < NARROW_BELOW;
  const width = narrow ? WINDOW_MIN_WIDTH : WIDE;
  // la plaque de titre dépasse de 14 px au-dessus du cadre
  const scale = Math.min(1, (vw - 16) / width, (vh - 32) / (WINDOW_HEIGHT + 14));
  return { narrow, width, scale };
}

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
  const [place, setPlace] = useState(windowPlacement);
  useEffect(() => {
    const resize = () => setPlace(windowPlacement());
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, []);
  const faction = isFaction(query.get('faction')) ? (query.get('faction') as Faction) : null;

  useEffect(() => {
    let alive = true;
    loader().then(data => { if (alive) setIndex(data); });
    return () => { alive = false; };
  }, [loader]);


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
          initialLang={defaultSubtitleLang(films[faction], lang)} initialChapter={query.get('chapter')} onBack={back} onClose={close} />
      </main>
    );
  }

  const bg = video('mainmenu');
  return (
    <main className={s.screen} aria-label={t('cinematics.title')}>
      <video className={s.bg} autoPlay muted loop playsInline poster={tex(`${T.main2}/Background_14_0_Temp`)}>
        <source src={bg.webm} type="video/webm" /><source src={bg.mp4} type="video/mp4" />
      </video>
      <div className={s.holder} style={{ transform: `translate(-50%, -50%) scale(${place.scale})` }}>
        <GameWindow title={t('cinematics.title')} onClose={close} closeLabel={t('legal.back')} width={place.width}
          className={place.narrow ? s.narrow : undefined}
          header={<p className={s.lead}>{t('cinematics.choose')}</p>}
          footer={<p className={s.footnote}>{t('cinematics.footnote')}</p>}>
          {!index || !index.cinematics.length ? (
            <p className={s.empty} role="status">{t('cinematics.missing')}</p>
          ) : (
            <div className={s.banners}>
              {FACTIONS.map(value => {
                const film = films[value];
                const { main, bonus } = splitBonus(film);
                const arcs = [...new Set(main.map(c => c.arc))];
                return (
                  <div key={value} className={s.bannerSlot}>
                    <button type="button" className={s.banner} data-faction={value}
                      onClick={() => choose(value)} disabled={!film.length} data-testid={`faction-${value}`}
                      aria-label={`${t(value === 'league' ? 'cinematics.league' : 'cinematics.empire')} — ${t('cinematics.watch')}`}
                      style={{ backgroundImage: `url(${tex(BANNER[value])})` }}>
                      <span className={s.bannerName}>{t(value === 'league' ? 'cinematics.league' : 'cinematics.empire')}</span>
                      <span className={s.parchment}>
                        <span className={s.summary}>
                          {t('cinematics.summary', { count: main.length, duration: formatDuration(filmDuration(main)) })}
                        </span>
                        {bonus.length > 0 && (
                          <span className={s.bonus}>{t('cinematics.bonusSummary', { count: bonus.length, duration: formatDuration(filmDuration(bonus)) })}</span>
                        )}
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
                  </div>
                );
              })}
            </div>
          )}
        </GameWindow>
      </div>
    </main>
  );
}
