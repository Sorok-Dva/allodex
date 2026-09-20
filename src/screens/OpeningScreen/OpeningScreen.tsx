import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { archiveFile, gameLogo, latestArchiveEntry, T, tex, video, type ArchiveEntry } from '@/lib/assets';
import { hasWebGL } from '@/lib/webgl';
import { Link, navigate } from '@/lib/router';
import { LanguageSwitcher } from '@/components/game/LanguageSwitcher';
import { useGameAudio } from '@/lib/audio/useGameAudio';
import { useI18n } from '@/lib/i18n';
import { GameActionBar, type ActionItem } from '@/components/game/GameActionBar';
import { SpeakerToggle } from '@/components/game/SpeakerToggle';
import { useIntroState } from './useIntroState';
import s from './OpeningScreen.module.css';

const MenuScene = lazy(() => import('@/components/game/MenuScene').then(m => ({ default: m.MenuScene })));

function Video({ name, loop, onEnded, onError, className }: { name: 'intro' | 'mainmenu'; loop?: boolean; onEnded?: () => void; onError?: () => void; className?: string }) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    v.play().catch(() => onError?.());   // autoplay refusé → on passe au menu
  }, [name, onError]);
  const src = video(name);
  return (
    <video ref={ref} className={className} muted playsInline loop={loop} onEnded={onEnded} onError={onError} poster={tex(`${T.main2}/Background_14_0_Temp`)}>
      <source src={src.webm} type="video/webm" />
      <source src={src.mp4} type="video/mp4" />
    </video>
  );
}

function MainMedia({ latest }: { latest?: ArchiveEntry }) {
  const [sceneReady, setSceneReady] = useState(false);
  const scene = latest?.media === 'image' && latest.scene && hasWebGL() ? latest.scene : null;

  if (latest?.media === 'image' && latest.background) {
    const still = (
      <img
        className={`${s.video} ${s.fadeIn} ${scene && sceneReady ? s.mediaBehind : ''}`}
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

  return <Video key="mainmenu" name="mainmenu" loop className={`${s.video} ${s.fadeIn}`} />;
}

export function OpeningScreen() {
  const { t } = useI18n();
  useEffect(() => { document.title = 'Allodex'; }, []);
  const items: ActionItem[] = [
    { id: 'medals', base: `${T.pinMenu}/ButtonMedals`, label: t('home.medals'), onClick: () => navigate('/achievements') },
    { id: 'chronicles', base: `${T.pinMenu}/ButtonQuestlog`, label: t('home.chronicles'), hint: t('home.chroniclesHint'), onClick: () => navigate('/chronicles') },
    { id: 'music', base: `${T.pinMenu}/ButtonMedals`, image: 'Official/media_player',
      label: t('music.title'), onClick: () => navigate('/music') },
    { id: 'equipment', base: `${T.pinMenu}/ButtonEquipment`, label: t('home.character'), hint: t('home.characterHint') },
  ];
  const latest = latestArchiveEntry();
  const hasIntro = latest ? Boolean(latest.intro) : true;
  const { phase, skipIntro, replayIntro } = useIntroState(undefined, !hasIntro);
  const { track, setTrack, playSfx } = useGameAudio();
  const firstInteractionRef = useRef(false);

  // Demandé dès le montage, intro comprise : la piste `menu` ne joue vraiment qu'après
  // le premier geste utilisateur (politique d'autoplay gérée par le moteur audio).
  useEffect(() => { if (track === null) setTrack('menu'); }, [track, setTrack]);

  const handleItemInteract = useCallback(() => {
    if (firstInteractionRef.current) return;
    firstInteractionRef.current = true;
    setTrack('ambient');
    playSfx('ui-click');
  }, [setTrack, playSfx]);

  useEffect(() => {
    if (phase !== 'intro') return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === ' ' || e.key === 'Enter') e.preventDefault();
      if (e.key === ' ' || e.key === 'Escape' || e.key === 'Enter') skipIntro();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [phase, skipIntro]);

  if (phase === 'intro' && hasIntro) {
    return (
      <div className={s.screen} onClick={skipIntro}>
        <Video key="intro" name="intro" className={s.video} onEnded={skipIntro} onError={skipIntro} />
        <span className={s.skipHint}>{t('home.skip')}</span>
      </div>
    );
  }

  return (
    <div className={s.screen}>
      <MainMedia latest={latest} />
      <div className={s.vignette} />

      <div className={s.title}>
        <img
          className={s.logo}
          src={gameLogo()}
          alt="Allodex"
          data-testid="game-logo"
        />
      </div>

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
    </div>
  );
}
