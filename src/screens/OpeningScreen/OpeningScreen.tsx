import { useEffect, useRef, useState, type FormEvent } from 'react';
import { T, tex, video } from '@/lib/assets';
import { navigate } from '@/lib/router';
import { GameButton } from '@/components/game/GameButton';
import { useIntroState } from './useIntroState';
import s from './OpeningScreen.module.css';

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
  const { phase, skipIntro, replayIntro } = useIntroState();
  const [query, setQuery] = useState('');

  useEffect(() => {
    if (phase !== 'intro') return;
    const onKey = (e: KeyboardEvent) => { if (e.key === ' ' || e.key === 'Escape' || e.key === 'Enter') skipIntro(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [phase, skipIntro]);

  const goMedals = (e?: FormEvent) => {
    e?.preventDefault();
    navigate(query.trim() ? `/succes?q=${encodeURIComponent(query.trim())}` : '/succes');
  };

  if (phase === 'intro') {
    return (
      <div className={s.screen} onClick={skipIntro}>
        <Video name="intro" className={s.video} onEnded={skipIntro} onError={skipIntro} />
        <span className={s.skipHint}>Cliquez pour passer</span>
      </div>
    );
  }

  return (
    <div className={s.screen}>
      <Video name="mainmenu" loop className={`${s.video} ${s.fadeIn}`} />
      <div className={s.vignette} />

      <form className={s.loginPanel} onSubmit={goMedals}>
        <label className={s.field} style={{ backgroundImage: `url(${tex(`${T.login}/EditlineFrame`)})` }}>
          <input
            className={s.input} value={query} onChange={e => setQuery(e.target.value)}
            placeholder="Recherche de succès..." autoFocus spellCheck={false}
          />
        </label>
        <GameButton base={`${T.login}/ButtonLogin`} width={220} height={64} label="Succès" onClick={() => goMedals()} className={s.mainButton} />
        <div className={s.roundRow}>
          <GameButton base={`${T.login}/ButtonOptions`} width={56} height={56} title="Mon compte (bientôt)" disabled />
          <GameButton base={`${T.login}/ButtonKeyboard`} width={56} height={56} title="Addon d'export (bientôt)" disabled />
          <GameButton base={`${T.login}/ButtonCredits`} width={56} height={56} title="Rejouer l'intro" onClick={replayIntro} />
        </div>
      </form>

      <div className={s.bottomLine} style={{ backgroundImage: `url(${tex(`${T.main2}/BottomLine`)})` }}>
        <span>Site fan non officiel. Allods Online, ses images et vidéos sont la propriété de My.Games.</span>
      </div>
    </div>
  );
}
