import { useMemo } from 'react';
import mock from '@/data/medals.mock.json';
import { parseDataset } from '@/data/medals.logic';
import { T, tex, video } from '@/lib/assets';
import { navigate, useRoute } from '@/lib/router';
import { GameFrame } from '@/components/game/GameFrame';
import { GameButton } from '@/components/game/GameButton';
import { MedalsNavigation } from './MedalsNavigation';
import { MedalsList } from './MedalsList';
import { useMedalsState } from './useMedalsState';
import s from './MedalsScreen.module.css';

export function MedalsScreen() {
  const ds = useMemo(() => parseDataset(mock), []);
  const { query } = useRoute();
  const state = useMedalsState(ds, query.get('q') ?? '');
  const bg = video('mainmenu');

  return (
    <div className={s.screen}>
      <video className={s.bg} autoPlay muted loop playsInline poster={tex(`${T.main2}/Background_14_0_Temp`)}>
        <source src={bg.webm} type="video/webm" /><source src={bg.mp4} type="video/mp4" />
      </video>

      <GameFrame texture={`${T.medals}/FrameContent`} slice={{ top: 70, right: 22, bottom: 32, left: 14 }} className={s.window}>
        <header className={s.header}>
          <h1 className={s.title}>Succès</h1>
          <GameButton base={T.cross} hoverState="Highlight" width={28} height={28} title="Fermer" onClick={() => navigate('/')} className={s.close} />
        </header>
        <div className={s.points}>{ds.totalScore.toLocaleString('fr-FR')} points de succès</div>
        <div className={s.columns}>
          <MedalsNavigation ds={ds} state={state} />
          <MedalsList state={state} />
        </div>
      </GameFrame>
    </div>
  );
}
