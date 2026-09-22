import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fatalitiesIndex, fatalityFile, sprite, type FatalityCharacter, type FatalityEntry } from '@/lib/assets';
import { navigate, useRoute } from '@/lib/router';
import { useGameAudio } from '@/lib/audio/useGameAudio';
import { pick, useI18n } from '@/lib/i18n';
import { hasWebGL } from '@/lib/webgl';
import { nineSlice } from '@/lib/nineSlice';
import { GameStrip } from '@/components/ui/GameStrip';
import { GameDropdown } from '@/components/ui/GameDropdown';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { SpeakerToggle } from '@/components/controls/SpeakerToggle';
import { FullscreenToggle } from '@/components/controls/FullscreenToggle';
import { Duration, formatDuration } from '@/screens/ChroniclesScreen/ThemePlayer';
import type { FatalityViewerHandle } from '@/components/scene/FatalityViewer';
import s from './FatalitiesScreen.module.css';

// `three` n'est chargé que sur cet écran (et les Chroniques), jamais à l'accueil.
const FatalityViewer = lazy(() => import('@/components/scene/FatalityViewer'));

/** Tranches de la pilule du jeu (`pill-full`, 242 × 28), comme la frise des Chroniques. */
const PILL_SLICE: [number, number, number, number] = [0, 30, 0, 24];
const SPEEDS = ['0.25', '0.5', '1', '2'] as const;
type Speed = (typeof SPEEDS)[number];

/** Animations jouées par la cible, dans l'ordre du script, avec leur vitesse (`DeathFatalityMage ×0.6 → DeathFatality`). */
export function victimSummary(character: FatalityCharacter, fatality: FatalityEntry): string | null {
  const steps = fatality.timelines?.[character.id]?.victim ?? [];
  const names = steps.filter(step => step.anim).map(step => (step.speed && step.speed !== 1 ? `${step.anim} ×${+step.speed.toFixed(2)}` : step.anim!));
  return names.length ? names.join(' → ') : null;
}

/**
 * Écran « Fatalités » : une scène 3D en plein écran où la cible choisie (race, sexe)
 * subit la fatalité choisie (de classe ou de la boutique), avec l'effet du jeu à ses
 * pieds ; la caméra tourne librement autour. Le choix vit dans l'URL
 * (`/fatalities?c=aed-female&f=warrior`), partageable.
 */
export function FatalitiesScreen() {
  const { t, lang } = useI18n();
  const { query } = useRoute();
  const { playSfx, muted, volume } = useGameAudio();
  const index = useMemo(() => fatalitiesIndex(), []);
  const characters = index?.characters ?? [];
  const fatalities = index?.fatalities ?? [];

  useEffect(() => { document.title = `Allodex — ${t('fatalities.title')}`; }, [t]);
  useEffect(() => { playSfx('medals-open'); }, [playSfx]);

  const character = characters.find(c => c.id === query.get('c')) ?? characters[0];
  const fatality = fatalities.find(f => f.id === query.get('f')) ?? fatalities[0];
  const select = useCallback((next: { c?: string; f?: string }) => {
    const params = new URLSearchParams(window.location.search);
    if (next.c) params.set('c', next.c);
    if (next.f) params.set('f', next.f);
    navigate(`/fatalities?${params.toString()}`, { replace: true });
  }, []);

  const races = useMemo(() => {
    const seen: string[] = [];
    for (const c of characters) if (!seen.includes(c.race)) seen.push(c.race);
    return seen.map(race => ({ value: race, label: pick(index?.races[race], lang) ?? race }));
  }, [characters, index, lang]);
  const sexes = useMemo(() => (['male', 'female'] as const)
    .filter(sex => characters.some(c => c.race === character?.race && c.sex === sex))
    .map(sex => ({ value: sex, label: t(sex === 'male' ? 'fatalities.male' : 'fatalities.female') })), [characters, character, t]);
  const pickCharacter = (race: string, sex: string) => {
    const found = characters.find(c => c.race === race && c.sex === sex) ?? characters.find(c => c.race === race);
    if (found) { playSfx('ui-click'); select({ c: found.id }); }
  };

  // Lecture : temps piloté par le lecteur, l'écran n'en garde que l'affichage.
  const viewer = useRef<FatalityViewerHandle>(null);
  const [playing, setPlaying] = useState(true);
  const [loop, setLoop] = useState(true);
  const [speed, setSpeed] = useState<Speed>('1');
  const [showFx, setShowFx] = useState(true);
  const [progress, setProgress] = useState({ time: 0, duration: 0 });
  const [ready, setReady] = useState(false);
  const summary = character && fatality ? victimSummary(character, fatality) : null;
  const timeline = character && fatality ? fatality.timelines?.[character.id] ?? null : null;
  const fxUrl = fatality?.fx ? fatalityFile(fatality.fx) : null;
  const sceneUrl = index?.scene ? fatalityFile(index.scene.glb) : null;
  useEffect(() => { setPlaying(true); setProgress({ time: 0, duration: 0 }); }, [character?.id, fatality?.id]);
  useEffect(() => { setReady(false); }, [character?.id, fxUrl]);

  const togglePlay = useCallback(() => {
    playSfx('ui-click');
    setPlaying(p => {
      if (!p && progress.duration > 0 && progress.time >= progress.duration) viewer.current?.seek(0);
      return !p;
    });
  }, [playSfx, progress]);
  const restart = useCallback(() => { playSfx('ui-click'); viewer.current?.seek(0); setPlaying(true); }, [playSfx]);

  // Plein écran (masque l'interface), comme les Chroniques.
  const [fullscreen, setFullscreen] = useState(false);
  const toggleFullscreen = useCallback(() => {
    playSfx('ui-click');
    setFullscreen(fs => {
      const next = !fs;
      if (next && !document.fullscreenElement) document.documentElement.requestFullscreen?.().catch(() => {});
      if (!next && document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
      return next;
    });
  }, [playSfx]);
  useEffect(() => {
    const onChange = () => { if (!document.fullscreenElement) setFullscreen(false); };
    document.addEventListener('fullscreenchange', onChange);
    return () => document.removeEventListener('fullscreenchange', onChange);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLButtonElement) return;
      if (e.key === ' ') { e.preventDefault(); togglePlay(); }
      else if (e.key === 'f' || e.key === 'F') { e.preventDefault(); toggleFullscreen(); }
      else if (e.key === 'r' || e.key === 'R') { e.preventDefault(); viewer.current?.resetView(); }
      else if (e.key === 'Escape' && fullscreen) { e.preventDefault(); toggleFullscreen(); }
      else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
        const i = fatalities.findIndex(f => f.id === fatality?.id);
        const next = fatalities[i + (e.key === 'ArrowDown' ? 1 : -1)];
        if (next) { e.preventDefault(); select({ f: next.id }); }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [togglePlay, toggleFullscreen, fullscreen, fatalities, fatality, select]);

  const handleClose = () => { playSfx('medals-close'); navigate('/'); };
  const webgl = hasWebGL();

  const list = (kind: FatalityEntry['kind']) => fatalities.filter(f => f.kind === kind).map(f => {
    const current = f.id === fatality?.id;
    return (
      <li key={f.id} role="presentation">
        <button
          type="button"
          role="option"
          aria-selected={current}
          className={`${s.pill} ${current ? s.pillActive : ''}`}
          onClick={() => { playSfx('ui-click'); select({ f: f.id }); }}
        >
          <span className={s.pillSkin} aria-hidden="true" style={nineSlice(current ? 'pill-full-open' : 'pill-full', PILL_SLICE)} />
          <span className={s.pillLabel}>{pick(f.label, lang) ?? f.id}</span>
        </button>
      </li>
    );
  });

  return (
    <div className={`${s.screen} ${fullscreen ? s.hudHidden : ''}`}>
      {character && fatality && timeline && webgl && (
        <Suspense fallback={null}>
          <FatalityViewer
            ref={viewer}
            characterUrl={fatalityFile(character.glb)}
            model={character.model}
            fxUrl={fxUrl}
            timeline={timeline}
            objects={fatality.objects ?? {}}
            fadeStart={fatality.fadeStart ?? 0}
            fadeDuration={fatality.fadeDuration ?? 0}
            sceneUrl={sceneUrl}
            environment={index?.scene?.environment ?? null}
            soundUrl={muted ? null : fatalityFile}
            assetUrl={fatalityFile}
            particleAtlas={index?.particleAtlas ?? null}
            volume={volume}
            height={character.height}
            playing={playing}
            loop={loop}
            speed={Number(speed)}
            showFx={showFx}
            onProgress={(time, duration) => setProgress(prev => (prev.time === time && prev.duration === duration ? prev : { time, duration }))}
            onEnded={() => setPlaying(false)}
            onReady={() => setReady(true)}
          />
        </Suspense>
      )}
      {character && !ready && webgl && <div className={s.loading}>{t('fatalities.loading')}</div>}

      <div className={`${s.cartouche} ${s.hud}`}>
        <div className={s.plate}>
          <GameStrip base="title-plate" cap={38} />
          <span className={s.plateTitle}>{t('fatalities.title')}</span>
        </div>
      </div>

      {!index && (
        <div className={`${s.card} ${s.hud}`} style={nineSlice('tooltip-frame', [4, 4, 4, 4])}>
          <div className={s.cardTitle}>{t('fatalities.missing')}</div>
          <div className={s.cardHint}>{t('fatalities.missingHint')} <code>python3 tools/extract_fatalities.py</code></div>
        </div>
      )}
      {index && !webgl && (
        <div className={`${s.card} ${s.hud}`} style={nineSlice('tooltip-frame', [4, 4, 4, 4])}>
          <div className={s.cardTitle}>{t('fatalities.noWebGL')}</div>
        </div>
      )}

      {index && character && fatality && (
        <aside className={`${s.panel} ${s.hud}`} style={nineSlice('tooltip-frame', [4, 4, 4, 4])}>
          <div className={s.field}>
            <span className={s.fieldLabel}>{t('fatalities.race')}</span>
            <GameDropdown value={character.race} options={races} onChange={race => pickCharacter(race, character.sex)} label={t('fatalities.race')} className={s.dropdown} />
          </div>
          <div className={s.field}>
            <span className={s.fieldLabel}>{t('fatalities.sex')}</span>
            <GameDropdown value={character.sex} options={sexes} onChange={sex => pickCharacter(character.race, sex)} label={t('fatalities.sex')} className={s.dropdown} />
          </div>
          <div className={s.lists} role="listbox" aria-label={t('fatalities.list')}>
            <div className={s.group}>{t('fatalities.classes')}</div>
            <ul className={s.list}>{list('class')}</ul>
            <div className={s.group}>{t('fatalities.shop')}</div>
            <ul className={s.list}>{list('shop')}</ul>
          </div>
          <div className={s.details}>
            {summary && <div>{t('fatalities.victim', { name: summary })}</div>}
            {!fatality.fx && <div className={s.warn}>{t('fatalities.fxMissing')}</div>}
            {fatality.note && <div className={s.warn}>{pick(fatality.note, lang)}</div>}
          </div>
        </aside>
      )}

      {index && character && fatality && (
        <div className={`${s.transport} ${s.hud}`} style={nineSlice('tooltip-frame', [4, 4, 4, 4])}>
          <button type="button" className={s.button} onClick={togglePlay} aria-label={playing ? t('fatalities.pause') : t('fatalities.play')}>
            <span className={s.buttonSkin} aria-hidden="true" style={nineSlice('pill-full', [0, 24, 0, 24], { fill: true })} />
            <svg className={s.glyph} viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
              {playing ? <path d="M4 2.5h3v11H4zM9 2.5h3v11H9z" fill="currentColor" /> : <path d="M4.5 2.5 13 8l-8.5 5.5z" fill="currentColor" />}
            </svg>
          </button>
          <button type="button" className={s.button} onClick={restart} aria-label={t('fatalities.restart')}>
            <span className={s.buttonSkin} aria-hidden="true" style={nineSlice('pill-full', [0, 24, 0, 24], { fill: true })} />
            <svg className={s.glyph} viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
              <path d="M3 2.5h2v11H3zM13 2.5 6 8l7 5.5z" fill="currentColor" />
            </svg>
          </button>
          <Duration seconds={progress.time} />
          <div className={s.seek}>
            <ProgressBar value={progress.time} max={progress.duration} label="" />
            <input
              type="range" min={0} max={progress.duration || 0} step={0.01}
              value={Math.min(progress.time, progress.duration)} disabled={progress.duration <= 0}
              aria-label={t('fatalities.seek')}
              aria-valuetext={`${formatDuration(progress.time)} / ${formatDuration(progress.duration)}`}
              onChange={event => { const time = Number(event.target.value); viewer.current?.seek(time); setProgress(p => ({ ...p, time })); }}
            />
          </div>
          <Duration seconds={progress.duration} />
          <label className={s.check}>
            <span className={s.checkbox} style={{ backgroundImage: `url(${sprite(loop ? 'checkbox-on' : 'checkbox-off')})` }} aria-hidden="true" />
            <input type="checkbox" checked={loop} onChange={e => { playSfx('ui-click'); setLoop(e.target.checked); }} />
            {t('fatalities.loop')}
          </label>
          <label className={`${s.check} ${!fatality.fx ? s.checkOff : ''}`}>
            <span className={s.checkbox} style={{ backgroundImage: `url(${sprite(showFx && fatality.fx ? 'checkbox-on' : 'checkbox-off')})` }} aria-hidden="true" />
            <input type="checkbox" checked={showFx} disabled={!fatality.fx} onChange={e => { playSfx('ui-click'); setShowFx(e.target.checked); }} />
            {t('fatalities.fx')}
          </label>
          <div className={s.speed}>
            <span className={s.fieldLabel}>{t('fatalities.speed')}</span>
            <GameDropdown value={speed} options={SPEEDS.map(v => ({ value: v, label: `×${v}` }))} onChange={setSpeed} width={62} label={t('fatalities.speed')} className={s.dropdown} />
          </div>
        </div>
      )}

      {index && webgl && <div className={`${s.hint} ${s.hud}`}>{t('fatalities.hint')}</div>}

      <button type="button" className={`${s.close} ${s.hud}`} style={{ backgroundImage: `url(${sprite('close-button')})` }} onClick={handleClose} aria-label={t('common.close')} />
      <SpeakerToggle className={`${s.speaker} ${s.hud}`} />
      <FullscreenToggle className={`${s.fullscreen} ${s.hud}`} fullscreen={fullscreen} onToggle={toggleFullscreen} />
    </div>
  );
}

export default FatalitiesScreen;
