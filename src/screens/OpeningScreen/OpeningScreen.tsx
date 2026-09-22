import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { archiveFile, gameLogo, latestArchiveEntry, T, tex, video, type ArchiveEntry } from '@/lib/assets';
import { hasWebGL } from '@/lib/webgl';
import { Link, navigate } from '@/lib/router';
import { LanguageSwitcher } from '@/components/controls/LanguageSwitcher';
import { useGameAudio } from '@/lib/audio/useGameAudio';
import { useI18n } from '@/lib/i18n';
import { GameActionBar, type ActionItem } from '@/components/ui/GameActionBar';
import { SpeakerToggle } from '@/components/controls/SpeakerToggle';
import { useIntroState } from './useIntroState';
import s from './OpeningScreen.module.css';

const MenuScene = lazy(() => import('@/components/scene/MenuScene').then(m => ({ default: m.MenuScene })));

function Video({ name, loop, onEnded, onError, className, testId }: { name: 'intro' | 'mainmenu'; loop?: boolean; onEnded?: () => void; onError?: () => void; className?: string; testId?: string }) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    v.play().catch(() => onError?.());   // autoplay refusé → laissé au parent (rien pour l'intro : le logo s'anime sur fond noir)
  }, [name, onError]);
  const src = video(name);
  return (
    <video ref={ref} className={className} muted playsInline loop={loop} onEnded={onEnded} onError={onError} poster={tex(`${T.main2}/Background_14_0_Temp`)} data-testid={testId}>
      <source src={src.webm} type="video/webm" />
      <source src={src.mp4} type="video/mp4" />
    </video>
  );
}

// `fade` : fondu depuis le noir quand le menu s'affiche directement ; inutile (et
// visible comme un creux sombre) quand la couche intro se fond déjà par-dessus.
function MainMedia({ latest, fade }: { latest?: ArchiveEntry; fade: boolean }) {
  const [sceneReady, setSceneReady] = useState(false);
  const scene = latest?.media === 'image' && latest.scene && hasWebGL() ? latest.scene : null;
  const fadeClass = fade ? s.fadeIn : '';

  if (latest?.media === 'image' && latest.background) {
    const still = (
      <img
        className={`${s.video} ${fadeClass} ${scene && sceneReady ? s.mediaBehind : ''}`}
        src={archiveFile(latest.version, latest.background)}
        alt=""
        aria-hidden="true"
      />
    );
    if (!scene) return still;
    return (
      <>
        {still}
        <Suspense fallback={null}>
          <MenuScene
            glbUrl={archiveFile(latest.version, scene.glb)}
            metaUrl={archiveFile(latest.version, scene.meta)}
            onReady={() => setSceneReady(true)}
          />
        </Suspense>
      </>
    );
  }

  return <Video key="mainmenu" name="mainmenu" loop className={`${s.video} ${fadeClass}`} />;
}

/* Animation d'ouverture du logo : matérialisation au centre de l'écran, halo, rayons
   et reflet balayant le logo ; au fondu, le logo glisse vers sa place du menu. */
function IntroLogoEffects({ src }: { src: string }) {
  const mask = { WebkitMaskImage: `url(${src})`, maskImage: `url(${src})` };
  return (
    <>
      <div className={s.logoHalo} aria-hidden="true" />
      <div className={s.logoRays} aria-hidden="true" />
      <div className={s.logoShine} style={mask} aria-hidden="true" />
      <div className={s.logoFlash} style={mask} aria-hidden="true" />
    </>
  );
}

export function OpeningScreen() {
  const { t } = useI18n();
  useEffect(() => { document.title = 'Allodex'; }, []);
  const items: ActionItem[] = [
    { id: 'chronicles', base: `${T.pinMenu}/ButtonQuestlog`, label: t('home.chronicles'), hint: t('home.chroniclesHint'), onClick: () => navigate('/chronicles') },
    { id: 'music', base: `${T.pinMenu}/ButtonMedals`, image: 'Official/media_player', label: t('music.title'), hint: t('home.musicHint'), onClick: () => navigate('/music') },
    { id: 'fatalities', base: T.spells, image: `${T.spells}/FatalityLotus`, label: t('home.fatalities'), hint: t('home.fatalitiesHint'), disabled: import.meta.env.PROD, onClick: () => navigate('/fatalities') },
    { id: 'talents', base: `${T.pinMenu}/ButtonTalents`, label: t('home.talents'), hint: t('home.talentsHint'), onClick: () => navigate('/talents') },
    { id: 'medals', base: `${T.pinMenu}/ButtonMedals`, label: t('home.medals'), hint: t('home.medalsHint'), onClick: () => navigate('/achievements') },
    { id: 'equipment', base: `${T.pinMenu}/ButtonEquipment`, label: t('home.character'), hint: t('home.characterHint'), disabled: true },
  ];
  const latest = latestArchiveEntry();
  const hasIntro = latest ? Boolean(latest.intro) : true;
  const { phase, skipIntro, replayIntro } = useIntroState(!hasIntro);
  const { track, setTrack, playSfx } = useGameAudio();
  const firstInteractionRef = useRef(false);
  const introRanRef = useRef(false);
  if (phase === 'intro') introRanRef.current = true;
  const inIntro = phase === 'intro';
  const introLayerVisible = hasIntro && phase !== 'menu';

  // Demandé dès le montage, intro comprise : la piste `menu` ne joue vraiment qu'après
  // le premier geste utilisateur (politique d'autoplay gérée par le moteur audio).
  useEffect(() => { if (track === null) setTrack('menu'); }, [track, setTrack]);

  const handleItemInteract = useCallback((id: string) => {
    if (firstInteractionRef.current) return;
    firstInteractionRef.current = true;
    if (id !== 'chronicles') {
      setTrack('ambient');
    }
    playSfx('ui-click');
  }, [setTrack, playSfx]);

  const handleSkip = useCallback(() => {
    playSfx('ui-click');
    skipIntro();
  }, [playSfx, skipIntro]);

  useEffect(() => {
    if (phase !== 'intro') return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === ' ' || e.key === 'Enter') e.preventDefault();
      if (e.key === ' ' || e.key === 'Escape' || e.key === 'Enter') handleSkip();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [phase, handleSkip]);

  /* Un seul arbre pour les trois phases : la vidéo d'intro et le logo gardent leur
     identité DOM pendant le fondu (pas de redémarrage, pas de saut), le menu se monte
     dessous dès la phase `fading` et la couche intro s'efface par-dessus. */
  return (
    <div className={s.screen} data-phase={phase}>
      {!inIntro && <MainMedia latest={latest} fade={!introRanRef.current} />}
      {!inIntro && <div className={s.vignette} />}

      {introLayerVisible && (
        <Video
          key="intro"
          name="intro"
          className={`${s.video} ${s.introLayer} ${phase === 'fading' ? s.introLayerOut : ''}`}
          testId="intro-video"
        />
      )}

      <div className={s.title}>
        <div className={`${s.logoStage} ${inIntro ? s.logoStageIntro : ''}`}>
          <div className={`${s.logoReveal} ${introLayerVisible ? s.logoRevealIntro : ''}`}>
            {introLayerVisible && <IntroLogoEffects src={gameLogo()} />}
            <img
              className={s.logo}
              src={gameLogo()}
              alt="Allodex"
              data-testid="game-logo"
            />
          </div>
        </div>
      </div>

      {inIntro ? (
        <button
          type="button"
          className={s.skipButton}
          onClick={handleSkip}
          data-testid="skip-button"
          aria-label={t('home.skip')}
          title={t('home.skip')}
        />
      ) : (
        <>
          <GameActionBar items={items} className={s.actionBar} onItemInteract={handleItemInteract} />

          {/* Le jeu rejoue sa cinématique depuis le menu ; ici un simple lien texte,
              posé au-dessus du bandeau légal pour ne pas empiéter dessus. */}
          {hasIntro && <button type="button" className={s.replay} onClick={replayIntro}>{t('home.replay')}</button>}

          <div className={s.bottomLine} style={{ backgroundImage: `url(${tex(`${T.main2}/BottomLine`)})` }}>
            <LanguageSwitcher className={s.language} />
            <div className={s.credits}>
              <span>{t('home.disclaimer')}</span>
              <span>{t('home.copyright', { year: new Date().getFullYear() })} <a href="https://p-42.fr/allodex-developer" target="_blank" rel="noopener noreferrer">Sorok-Dva</a> · <Link to="/terms">{t('legal.shortTitle')}</Link></span>
            </div>
            <SpeakerToggle className={s.speaker} />
          </div>
        </>
      )}
    </div>
  );
}
