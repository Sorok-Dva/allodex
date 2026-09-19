import { useCallback, useEffect, useRef } from 'react';
import { T, tex, video } from '@/lib/assets';
import { navigate } from '@/lib/router';
import { useGameAudio } from '@/lib/audio/useGameAudio';
import { useI18n } from '@/lib/i18n';
import { GameActionBar, type ActionItem } from '@/components/game/GameActionBar';
import { SpeakerToggle } from '@/components/game/SpeakerToggle';
import { useIntroState } from './useIntroState';
import s from './OpeningScreen.module.css';

const ACTION_ITEMS: ActionItem[] = [
  { id: 'medals', base: `${T.pinMenu}/ButtonMedals`, label: 'Succès', onClick: () => navigate('/succes') },
  { id: 'chronicles', base: `${T.pinMenu}/ButtonQuestlog`, label: 'Chroniques', hint: "Les écrans de lancement du jeu, version par version", onClick: () => navigate('/chroniques') },
  { id: 'equipment', base: `${T.pinMenu}/ButtonEquipment`, label: 'Personnage', hint: 'Mon compte — bientôt' },
];

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

export function OpeningScreen() {
  const { t } = useI18n();
  const items: ActionItem[] = [
    ...ACTION_ITEMS.slice(0, 2),
    { id: 'music', base: `${T.pinMenu}/ButtonMedals`, spriteBase: 'music-action',
      icon: 'Interface/Icons/Special/Emotions/PlayedTrumpet', label: t('music.title'), onClick: () => navigate('/musiques') },
    ...ACTION_ITEMS.slice(2),
  ];
  const { phase, skipIntro, replayIntro } = useIntroState();
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

  if (phase === 'intro') {
    return (
      <div className={s.screen} onClick={skipIntro}>
        <Video key="intro" name="intro" className={s.video} onEnded={skipIntro} onError={skipIntro} />
        <span className={s.skipHint}>Cliquez pour passer</span>
      </div>
    );
  }

  return (
    <div className={s.screen}>
      <Video key="mainmenu" name="mainmenu" loop className={`${s.video} ${s.fadeIn}`} />
      <div className={s.vignette} />

      <GameActionBar items={items} className={s.actionBar} onItemInteract={handleItemInteract} />

      {/* Le jeu rejoue sa cinématique depuis le menu ; ici un simple lien texte,
          posé au-dessus du bandeau légal pour ne pas empiéter dessus. */}
      <button type="button" className={s.replay} onClick={replayIntro}>Rejouer l'intro</button>

      <div className={s.bottomLine} style={{ backgroundImage: `url(${tex(`${T.main2}/BottomLine`)})` }}>
        <span>Site fan non officiel. Allods Online, ses images et vidéos sont la propriété de My.Games.</span>
        <SpeakerToggle className={s.speaker} />
      </div>
    </div>
  );
}
