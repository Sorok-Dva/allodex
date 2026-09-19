import { useEffect, useMemo, useState } from 'react';
import mock from '@/data/medals.mock.json';
import { parseDataset } from '@/data/medals.logic';
import { T, tex, video } from '@/lib/assets';
import { navigate, useRoute } from '@/lib/router';
import { MedalsWindow } from './MedalsWindow';
import { MedalsNavigation } from './MedalsNavigation';
import { MedalsList } from './MedalsList';
import { useMedalsState } from './useMedalsState';
import s from './MedalsScreen.module.css';

const WIN_W = 886;
const WIN_H = 592;
/**
 * La fenêtre du jeu n'est pas exactement centrée : sur `refs/astral.png` (1920 × 1009)
 * elle occupe x 518→1404 et y 191→783, soit 1 px à droite du centre horizontal et
 * 17 px au-dessus du centre vertical. On reproduit ce décalage pour que la capture du
 * site se superpose à la référence. Le calcul est fait en JavaScript pour garantir des
 * coordonnées entières : un `calc(50% - …)` tomberait sur un demi-pixel dès que la vue
 * a une dimension impaire et flouterait tous les sprites.
 */
function place() {
  const w = typeof window === 'undefined' ? 1920 : window.innerWidth;
  const h = typeof window === 'undefined' ? 1009 : window.innerHeight;
  return {
    left: Math.max(0, Math.floor((w - WIN_W) / 2) + 1),
    top: Math.max(0, Math.floor((h - WIN_H) / 2) - 17),
  };
}

export function MedalsScreen() {
  const ds = useMemo(() => parseDataset(mock), []);
  const { query } = useRoute();
  const state = useMedalsState(ds, query.get('q') ?? '');
  const bg = video('mainmenu');
  const [pos, setPos] = useState(place);

  useEffect(() => {
    const onResize = () => setPos(place());
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  return (
    <div className={s.screen}>
      <video className={s.bg} autoPlay muted loop playsInline poster={tex(`${T.main2}/Background_14_0_Temp`)}>
        <source src={bg.webm} type="video/webm" /><source src={bg.mp4} type="video/mp4" />
      </video>

      <div className={s.holder} style={{ left: pos.left, top: pos.top }}>
        <MedalsWindow
          title="Succès"
          points={ds.totalScore}
          onClose={() => navigate('/')}
          nav={<MedalsNavigation ds={ds} state={state} />}
          content={<MedalsList state={state} />}
        />
      </div>
    </div>
  );
}
