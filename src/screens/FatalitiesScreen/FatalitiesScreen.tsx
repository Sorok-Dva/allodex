import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fatalitiesIndex, fatalityFile, sprite, type FatalityCharacter, type FatalityEntry } from '@/lib/assets';
import { navigate, useRoute } from '@/lib/router';
import { useGameAudio } from '@/lib/audio/useGameAudio';
import { pick, useI18n, type I18n } from '@/lib/i18n';
import type { Lang } from '@/lib/i18n/messages';
import { hasWebGL } from '@/lib/webgl';
import { nineSlice } from '@/lib/nineSlice';
import { GameStrip } from '@/components/ui/GameStrip';
import { GameDropdown } from '@/components/ui/GameDropdown';
import { GameTooltip } from '@/components/ui/GameTooltip';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { SpeakerToggle } from '@/components/controls/SpeakerToggle';
import { FullscreenToggle } from '@/components/controls/FullscreenToggle';
import { Duration, formatDuration } from '@/screens/ChroniclesScreen/ThemePlayer';
import type { FatalityViewerHandle } from '@/components/scene/FatalityViewer';
import type { ChargenData } from '@/data/character/chargen.types';
import { DEFAULT_TIER, TIERS, TIER_TEXTS, attackerClass, classesOf, dressFor, fatalityClass } from './outfits';
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
 * Nom affiché d'une fatalité de la liste : pour la boutique, le nom officiel de l'objet qui
 * l'apprend (premier de `items`) dans la langue de l'interface ; à défaut de texte officiel dans
 * cette langue (Serpent 2026 en français, Baudroie et Arbre en anglais), le libellé du site,
 * signalé par `official: false`.
 */
export function fatalityListName(f: FatalityEntry, lang: Lang): { text: string; official: boolean; icon: string | null } {
  const item = f.kind === 'shop' ? f.items?.[0] : undefined;
  const name = item?.name[lang];
  if (name) return { text: name, official: true, icon: item?.icon ?? null };
  return { text: pick(f.label, lang) ?? f.id, official: f.kind === 'class', icon: item?.icon ?? null };
}

/** Date ISO (`2023-08-18`) au format du jeu (`18.08.2023`). */
export function gameDate(iso: string): string {
  const [y, m, d] = iso.split('-');
  return d && m && y ? `${d}.${m}.${y}` : iso;
}

/**
 * Deuxième ligne de l'infobulle de la liste (verte, comme la date des infobulles du jeu) :
 * version d'apparition et date de l'actualité officielle quand elle est connue.
 */
export function sinceLine(fatality: FatalityEntry, t: I18n['t']): string | undefined {
  const since = fatality.since;
  if (!since) return undefined;
  const date = since.date;
  if (!date) return t('fatalities.tipSinceOnly', { version: since.version });
  return t(date.kind === 'attested' ? 'fatalities.tipSinceAttested' : 'fatalities.tipSince', { version: since.version, date: gameDate(date.value) });
}

/** Racine des fichiers de la création de personnage (modèles habillés, `chargen.json`). */
export const CHARGEN_BASE = '/game/character/';

/**
 * Tueur par défaut : le personnage du même sexe de la première race de l'autre faction (un
 * Kanien tombe sous les coups d'un Xadaganien, et inversement) ; parmi elles, de préférence une
 * race qui peut prendre la classe de la fatalité (`canCast`).
 */
export function defaultAttacker(characters: FatalityCharacter[], races: Record<string, { faction: string }>,
  victim: FatalityCharacter | undefined, canCast: (race: string) => boolean = () => true): FatalityCharacter | undefined {
  if (!victim) return undefined;
  const faction = races[victim.race]?.faction;
  const foes = characters.filter(c => races[c.race]?.faction && races[c.race]?.faction !== faction);
  const casters = foes.filter(c => canCast(c.race));
  return casters.find(c => c.sex === victim.sex) ?? foes.find(c => c.sex === victim.sex) ?? foes[0] ?? victim;
}

/**
 * Encart d'information de la fatalité choisie, au cadre d'infobulle du jeu (titre et date en
 * vert, description en jaune) : nom en jeu, objets qui l'apprennent (icône, nom officiel),
 * version d'apparition (premier client archivé qui la contient) et date d'une actualité
 * officielle quand elle est connue (lien vers la source).
 */
export function FatalityInfo({ fatality, lang }: { fatality: FatalityEntry; lang: Lang }) {
  const { t } = useI18n();
  const since = fatality.since;
  const title = pick(fatality.name, lang) ?? pick(fatality.label, lang) ?? fatality.id;
  const items = fatality.kind === 'shop' ? fatality.items ?? [] : [];
  const date = since?.date;
  return (
    <section className={`${s.info} ${s.hud}`} style={nineSlice('tooltip-frame', [4, 4, 4, 4])} aria-label={t('fatalities.info')}>
      <div className={s.infoTitle}>{title}</div>
      {fatality.kind === 'class' && fatality.name && <div className={s.infoSub}>{pick(fatality.label, lang)}</div>}
      {since && (
        <div className={s.infoDate}>
          {t('fatalities.since', { version: since.version })}
          {since.client && <span className={s.infoMuted}> ({t('fatalities.sinceClient', { client: since.client })}{since.previous ? `, ${t('fatalities.absentFrom', { version: since.previous })}` : ''})</span>}
        </div>
      )}
      <div className={s.infoDate}>
        {date
          ? <>{t(date.kind === 'attested' ? 'fatalities.dateAttested' : 'fatalities.date', { date: gameDate(date.value) })}{' '}
            <a className={s.infoLink} href={date.source} target="_blank" rel="noreferrer">({t('fatalities.dateSource')})</a></>
          : <span className={s.infoMuted}>{t('fatalities.dateUnknown')}</span>}
      </div>
      {items.length > 0 && (
        <>
          <div className={s.infoSep} />
          <div className={s.infoGroup}>{t(items.length > 1 ? 'fatalities.items' : 'fatalities.item')}</div>
          <ul className={s.infoItems}>
            {items.map(item => {
              const name = item.name[lang];
              return (
                <li key={item.resourceIds[0]} className={s.infoItem}>
                  {item.icon ? <img src={fatalityFile(item.icon)} alt="" width={32} height={32} /> : <span className={s.infoNoIcon} />}
                  <span className={name ? s.infoItemName : `${s.infoItemName} ${s.infoMuted}`} title={name ? undefined : t('fatalities.nameUnproven')}>
                    {name ?? pick(fatality.label, lang) ?? item.name.ru}
                  </span>
                </li>
              );
            })}
          </ul>
          {fatality.itemLink === 'name' && <div className={s.infoNote}>{t('fatalities.linkName')}</div>}
        </>
      )}
    </section>
  );
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

  // Tenues de classe : données de la création de personnage (chargées à part, 2 Mo).
  const [chargen, setChargen] = useState<ChargenData | null>(null);
  useEffect(() => {
    let alive = true;
    fetch(`${CHARGEN_BASE}chargen.json`).then(r => (r.ok ? r.json() as Promise<ChargenData> : null)).then(d => { if (alive) setChargen(d); })
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  const character = characters.find(c => c.id === query.get('c')) ?? characters[0];
  const fatality = fatalities.find(f => f.id === query.get('f')) ?? fatalities[0];
  const castClass = fatalityClass(chargen, fatality);
  const attacker = characters.find(c => c.id === query.get('k'))
    ?? defaultAttacker(characters, index?.races ?? {}, character, race => !castClass || classesOf(chargen, race).includes(castClass));
  const victimClasses = character ? classesOf(chargen, character.race) : [];
  const victimClass = victimClasses.find(c => c === query.get('cl')) ?? victimClasses[0] ?? null;
  const tierParam = Number(query.get('t'));
  const tier = (TIERS as readonly number[]).includes(tierParam) && query.get('t') !== null ? tierParam : DEFAULT_TIER;
  const killerClass = attacker ? attackerClass(chargen, attacker.race, fatality) : null;
  const victimDress = useMemo(() => dressFor(chargen, CHARGEN_BASE, character, victimClass, tier), [chargen, character, victimClass, tier]);
  const attackerDress = useMemo(() => dressFor(chargen, CHARGEN_BASE, attacker, killerClass, tier), [chargen, attacker, killerClass, tier]);
  const select = useCallback((next: { c?: string; f?: string; k?: string; cl?: string; t?: number }) => {
    const params = new URLSearchParams(window.location.search);
    if (next.c) { params.set('c', next.c); params.delete('cl'); }
    if (next.f) params.set('f', next.f);
    if (next.k) params.set('k', next.k);
    if (next.cl) params.set('cl', next.cl);
    if (next.t !== undefined) params.set('t', String(next.t));
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
  const attackers = useMemo(() => characters.map(c => ({
    value: c.id,
    label: `${pick(index?.races[c.race], lang) ?? c.race} (${t(c.sex === 'male' ? 'fatalities.male' : 'fatalities.female')})`,
  })), [characters, index, lang, t]);
  const classOptions = useMemo(() => victimClasses.map(c => ({ value: c, label: pick(chargen?.classes[c]?.name ?? undefined, lang) ?? c })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [victimClasses.join(','), chargen, lang]);
  const tierOptions = useMemo(() => TIERS.map(k => ({ value: String(k), label: pick(chargen?.texts[TIER_TEXTS[k]] ?? undefined, lang) ?? TIER_TEXTS[k] })),
    [chargen, lang]);
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
  useEffect(() => { setReady(false); }, [character?.id, attacker?.id, fxUrl, victimClass, tier]);

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

  // Survol d'une ligne de la liste : infobulle du jeu (nom complet de l'objet, de la fatalité).
  const [hover, setHover] = useState<{ id: string; anchor: DOMRect } | null>(null);
  const hovered = hover ? fatalities.find(f => f.id === hover.id) : undefined;

  const list = (kind: FatalityEntry['kind']) => fatalities.filter(f => f.kind === kind).map(f => {
    const current = f.id === fatality?.id;
    const shown = fatalityListName(f, lang);
    return (
      <li key={f.id} role="presentation">
        <button
          type="button"
          role="option"
          aria-selected={current}
          className={`${s.pill} ${current ? s.pillActive : ''}`}
          onClick={() => { playSfx('ui-click'); select({ f: f.id }); }}
          onMouseEnter={e => setHover({ id: f.id, anchor: e.currentTarget.getBoundingClientRect() })}
          onMouseLeave={() => setHover(null)}
        >
          <span className={s.pillSkin} aria-hidden="true" style={nineSlice(current ? 'pill-full-open' : 'pill-full', PILL_SLICE, { fill: true })} />
          {shown.icon && <img className={s.pillIcon} src={fatalityFile(shown.icon)} alt="" aria-hidden="true" width={20} height={20} />}
          <span className={`${s.pillLabel} ${shown.icon ? s.pillLabelIcon : ''} ${shown.official ? '' : s.pillLabelUnofficial}`}><span className={s.pillText}>{shown.text}</span></span>
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
            attackerUrl={attacker ? fatalityFile(attacker.glb) : null}
            attackerModel={attacker?.model ?? ''}
            victimDress={victimDress}
            attackerDress={attackerDress}
            fxUrl={fxUrl}
            timeline={timeline}
            objects={fatality.objects ?? {}}
            fadeStart={fatality.fadeStart ?? 0}
            fadeDuration={fatality.fadeDuration ?? 0}
            sceneUrl={sceneUrl}
            environment={index?.scene?.environment ?? null}
            orbitMax={index?.scene?.site?.orbit ?? null}
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
          {victimClass && (
            <div className={s.field}>
              <span className={s.fieldLabel}>{t('fatalities.class')}</span>
              <GameDropdown value={victimClass} options={classOptions} onChange={cl => { playSfx('ui-click'); select({ cl }); }} label={t('fatalities.class')} className={s.dropdown} />
            </div>
          )}
          {chargen && (
            <div className={s.field}>
              <span className={s.fieldLabel}>{t('fatalities.outfit')}</span>
              <GameDropdown value={String(tier)} options={tierOptions} onChange={v => { playSfx('ui-click'); select({ t: Number(v) }); }} label={t('fatalities.outfit')} className={s.dropdown} />
            </div>
          )}
          {attacker && (
            <div className={s.field}>
              <span className={s.fieldLabel}>{t('fatalities.attacker')}</span>
              <GameDropdown value={attacker.id} options={attackers} onChange={id => { playSfx('ui-click'); select({ k: id }); }} label={t('fatalities.attacker')} className={s.dropdown} />
            </div>
          )}
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

      {index && fatality && <FatalityInfo fatality={fatality} lang={lang} />}
      {hovered && hover && (
        <GameTooltip anchor={hover.anchor} align="cursor" title={fatalityListName(hovered, lang).text}
          date={sinceLine(hovered, t)} hint={pick(hovered.name, lang) ?? hovered.name?.ru} />
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
