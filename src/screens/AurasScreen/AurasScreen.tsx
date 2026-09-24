import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { auraFile, fatalitiesIndex, fatalityFile, sprite, type AuraEntry, type AurasIndex } from '@/lib/assets';
import { navigate, useRoute } from '@/lib/router';
import { useGameAudio } from '@/lib/audio/useGameAudio';
import { pick, useI18n, type I18n } from '@/lib/i18n';
import type { Lang } from '@/lib/i18n/messages';
import { hasWebGL } from '@/lib/webgl';
import { nineSlice } from '@/lib/nineSlice';
import { GameStrip } from '@/components/ui/GameStrip';
import { GameDropdown } from '@/components/ui/GameDropdown';
import { GameTooltip } from '@/components/ui/GameTooltip';
import { SpeakerToggle } from '@/components/controls/SpeakerToggle';
import { FullscreenToggle } from '@/components/controls/FullscreenToggle';
import type { AuraViewerHandle } from '@/components/scene/AuraViewer';
import type { ChargenData, Sex } from '@/data/character/chargen.types';
import { CHARGEN_BASE } from '@/screens/FatalitiesScreen/FatalitiesScreen';
import { DEFAULT_TIER, TIERS, TIER_TEXTS, classesOf } from '@/screens/FatalitiesScreen/outfits';
import { avatarDress, avatarHeight, avatarRaces, isExoskeleton, officialText, sinceParts, type AuraChoice } from './auras';
import s from '@/screens/FatalitiesScreen/FatalitiesScreen.module.css';
import a from './AurasScreen.module.css';

// `three` n'est chargé que sur les écrans 3D.
const AuraViewer = lazy(() => import('@/components/scene/AuraViewer'));

const PILL_SLICE: [number, number, number, number] = [0, 30, 0, 24];
const SPEEDS = ['0.25', '0.5', '1', '2'] as const;
type Speed = (typeof SPEEDS)[number];

/**
 * Hauteur du modèle d'une apparence (m) : haut de la boîte de son animation dans le client
 * (`bounds` du gabarit), pour cadrer l'exosquelette entier ; 2,4 m à défaut.
 */
export function appearanceHeight(choice: AuraChoice | undefined): number {
  if (choice?.kind !== 'appearance' || !choice.entry.model) return 2.4;
  const b = choice.entry.model.objects[choice.entry.model.vot]?.bounds;
  return b ? Math.max(1, b[2] + b[5]) : 2.4;
}

/** Une apparence remplace l'avatar (modèle de monture ou de carapace) : pas de marche. */
function appearanceOf(choice: AuraChoice | undefined): boolean {
  return choice?.kind === 'appearance' && !!choice.entry.model;
}

/** Ligne verte de l'infobulle de la liste : version d'apparition, date inconnue. */
export function auraSinceLine(choice: AuraChoice, t: I18n['t']): string | undefined {
  const since = sinceParts(choice.entry.since);
  return since ? t('auras.tipSince', { version: since.version }) : t('auras.sinceUnknown');
}

/** Nom affiché d'une entrée (officiel dans la langue, sinon celui d'une autre langue du client). */
export function choiceName(choice: AuraChoice, lang: Lang): { text: string; official: boolean } {
  return officialText(choice.entry.name, lang) ?? { text: choice.entry.id, official: false };
}

/**
 * Encart d'information de l'aura choisie, au cadre de l'infobulle du jeu : nom, description de la
 * garde-robe, version d'apparition, obtention (texte du client), objets ; pour une apparence, son
 * modèle et les auras qu'elle donne.
 */
export function AuraInfo({ choice, lang, auras }: { choice: AuraChoice; lang: Lang; auras: AuraEntry[] }) {
  const { t } = useI18n();
  const entry = choice.entry;
  const name = choiceName(choice, lang);
  const desc = officialText(entry.description, lang);
  const obtain = officialText(entry.obtain, lang);
  const since = sinceParts(entry.since);
  const items = choice.kind === 'aura' ? choice.entry.items ?? [] : [];
  const given = choice.kind === 'appearance' ? choice.entry.auras.map(id => auras.find(x => x.id === id)).filter((x): x is AuraEntry => !!x) : [];
  return (
    <section className={`${s.info} ${s.hud}`} style={nineSlice('tooltip-frame', [4, 4, 4, 4])} aria-label={t('auras.info')}>
      <div className={`${s.infoTitle} ${name.official ? '' : a.unofficial}`} title={name.official ? undefined : t('auras.nameUnproven')}>{name.text}</div>
      {choice.kind === 'appearance' && (
        <div className={s.infoSub}>
          {choice.entry.kind === 'exoskin'
            ? `${t('auras.exoskin')} — ${officialText(choice.entry.skin?.mount, lang)?.text ?? ''}`
            : choice.entry.kind === 'mount'
            ? `${t(isExoskeleton(choice.entry.model?.vot) ? 'auras.exoskeleton' : 'auras.mount')} — ${(officialText(choice.entry.skin?.mount, lang) ?? officialText(choice.entry.skin?.name, lang))?.text ?? ''}`
            : t('auras.costume')}
        </div>
      )}
      <div className={s.infoDate}>
        {since
          ? <>{t('auras.since', { version: since.version })}
            <span className={s.infoMuted}> ({[since.client && t('auras.sinceClient', { client: since.client }), since.previous && t('auras.absentFrom', { version: since.previous }), since.byIcon && t('auras.sinceIcon')].filter(Boolean).join(', ')})</span></>
          : <span className={s.infoMuted}>{t('auras.sinceUnknown')}</span>}
      </div>
      <div className={s.infoDate}><span className={s.infoMuted}>{t('auras.dateUnknown')}</span></div>
      {desc && <div className={`${a.desc} ${desc.official ? '' : a.unofficial}`}>{desc.text}</div>}
      <div className={`${a.obtain} ${obtain && !obtain.official ? a.unofficial : ''}`}>{obtain ? t('auras.obtain', { text: obtain.text }) : t('auras.obtainUnknown')}</div>
      {choice.kind === 'aura' && choice.entry.visual === false && <div className={s.infoNote}>{t('auras.noVisual')}</div>}
      {choice.kind === 'appearance' && choice.entry.kind === 'costume' && <div className={s.infoNote}>{t('auras.costumeNote')}</div>}
      {choice.kind === 'appearance' && choice.entry.kind === 'exoskin' && <div className={s.infoNote}>{t('auras.exoskinNote')}</div>}
      {(items.length > 0 || given.length > 0) && (
        <>
          <div className={s.infoSep} />
          <div className={s.infoGroup}>{given.length ? t('auras.gives') : t(items.length > 1 ? 'auras.items' : 'auras.item')}</div>
          <ul className={s.infoItems}>
            {(given.length ? given.map(g => ({ key: g.id, name: g.name, icon: g.icon })) : items.map(i => ({ key: String(i.resourceIds[0]), name: i.name, icon: i.icon })))
              .map(item => {
                const n = officialText(item.name, lang);
                return (
                  <li key={item.key} className={s.infoItem}>
                    {item.icon ? <img src={auraFile(item.icon)} alt="" width={32} height={32} /> : <span className={s.infoNoIcon} />}
                    <span className={`${s.infoItemName} ${n?.official ? '' : a.unofficial}`}>{n?.text}</span>
                  </li>
                );
              })}
          </ul>
        </>
      )}
    </section>
  );
}

/**
 * Écran « Auras » : l'avatar choisi (race, sexe, classe, tenue) debout dans la clairière des
 * fatalités, l'aura de la garde-robe à ses pieds, en boucle ; ou le modèle d'une apparence (peau
 * d'exosquelette, de monture) avec son aura. Le choix vit dans l'URL (`/auras?a=a740017040`).
 */
export function AurasScreen() {
  const { t, lang } = useI18n();
  const { query } = useRoute();
  const { playSfx, muted, volume } = useGameAudio();
  const [index, setIndex] = useState<AurasIndex | null | undefined>(undefined);
  const [chargen, setChargen] = useState<ChargenData | null>(null);
  useEffect(() => { document.title = `Allodex — ${t('auras.title')}`; }, [t]);
  useEffect(() => { playSfx('medals-open'); }, [playSfx]);
  useEffect(() => {
    let alive = true;
    fetch(auraFile('auras.json')).then(r => (r.ok ? r.json() as Promise<AurasIndex> : null)).then(d => { if (alive) setIndex(d && Array.isArray(d.auras) ? d : null); })
      .catch(() => { if (alive) setIndex(null); });
    fetch(`${CHARGEN_BASE}chargen.json`).then(r => (r.ok ? r.json() as Promise<ChargenData> : null)).then(d => { if (alive) setChargen(d); }).catch(() => {});
    return () => { alive = false; };
  }, []);
  const scene = fatalitiesIndex()?.scene ?? null;

  const choices = useMemo<AuraChoice[]>(() => [
    ...(index?.auras ?? []).map(entry => ({ kind: 'aura' as const, entry })),
    ...(index?.appearances ?? []).map(entry => ({ kind: 'appearance' as const, entry })),
  ], [index]);
  const choice = choices.find(c => c.entry.id === query.get('a')) ?? choices[0];

  // Avatar : race et sexe de la création, classe de la race, niveau de tenue.
  const races = useMemo(() => avatarRaces(chargen), [chargen]);
  const race = races.find(r => r.race === query.get('r'))?.race ?? races[0]?.race ?? null;
  const sexes = races.find(r => r.race === race)?.sexes ?? [];
  const sex: Sex = (sexes.find(x => x === query.get('s')) ?? sexes[0] ?? 'male');
  const classes = race ? classesOf(chargen, race) : [];
  const cls = classes.find(c => c === query.get('cl')) ?? classes[0] ?? null;
  const tierParam = Number(query.get('t'));
  const tier = (TIERS as readonly number[]).includes(tierParam) && query.get('t') !== null ? tierParam : DEFAULT_TIER;
  const dress = useMemo(() => avatarDress(chargen, CHARGEN_BASE, race, sex, cls, tier), [chargen, race, sex, cls, tier]);
  const height = avatarHeight(chargen, dress);

  const select = useCallback((next: { a?: string; r?: string; s?: string; cl?: string; t?: number }) => {
    const params = new URLSearchParams(window.location.search);
    if (next.a) params.set('a', next.a);
    if (next.r) { params.set('r', next.r); params.delete('cl'); }
    if (next.s) params.set('s', next.s);
    if (next.cl) params.set('cl', next.cl);
    if (next.t !== undefined) params.set('t', String(next.t));
    navigate(`/auras?${params.toString()}`, { replace: true });
  }, []);

  const raceOptions = useMemo(() => races.map(r => ({ value: r.race, label: pick(chargen?.races[r.race]?.name ?? undefined, lang) ?? r.race })), [races, chargen, lang]);
  const sexOptions = useMemo(() => sexes.map(x => ({ value: x, label: t(x === 'male' ? 'auras.male' : 'auras.female') })), [sexes, t]);
  const classOptions = useMemo(() => classes.map(c => ({ value: c, label: pick(chargen?.classes[c]?.name ?? undefined, lang) ?? c })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [classes.join(','), chargen, lang]);
  const tierOptions = useMemo(() => TIERS.map(k => ({ value: String(k), label: pick(chargen?.texts[TIER_TEXTS[k]] ?? undefined, lang) ?? TIER_TEXTS[k] })), [chargen, lang]);

  const viewer = useRef<AuraViewerHandle>(null);
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState<Speed>('1');
  const [showFx, setShowFx] = useState(true);
  const [ready, setReady] = useState(false);
  // Effets montrés : ceux de l'aura, ceux de la couleur de robe elle-même, ou la première aura du lot.
  const aura: Pick<AuraEntry, 'fx' | 'objects' | 'timeline'> | undefined = choice?.kind === 'aura' ? choice.entry
    : choice?.entry.kind === 'exoskin' ? choice.entry
      : choice ? index?.auras.find(x => x.id === choice.entry.auras[0]) : undefined;
  // Marche : active d'office pour les auras qui ne se voient qu'en marchant (empreintes).
  const walkMeta = !appearanceOf(choice) && dress ? index?.walks?.[dress.template] : undefined;
  const walk = useMemo(() => (walkMeta ? { url: auraFile(walkMeta.glb), clips: walkMeta.clips, speed: walkMeta.speed } : null), [walkMeta]);
  const walkDefault = !!aura?.timeline?.stateAttached?.length;
  const [walking, setWalking] = useState(walkDefault);
  useEffect(() => { setWalking(walkDefault); }, [choice?.entry.id, walkDefault]);
  const appearance = choice?.kind === 'appearance' && choice.entry.model
    ? { url: auraFile(choice.entry.model.glb), vot: choice.entry.model.vot, objects: choice.entry.model.objects } : null;
  const fxUrl = aura?.fx ? auraFile(aura.fx) : null;
  const sceneUrl = scene ? fatalityFile(scene.glb) : null;
  useEffect(() => { setReady(false); }, [fxUrl, appearance?.url, dress?.template, dress?.tier, cls]);

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
      if (e.key === ' ') { e.preventDefault(); setPlaying(p => !p); }
      else if (e.key === 'f' || e.key === 'F') { e.preventDefault(); toggleFullscreen(); }
      else if (e.key === 'r' || e.key === 'R') { e.preventDefault(); viewer.current?.resetView(); }
      else if (e.key === 'Escape' && fullscreen) { e.preventDefault(); toggleFullscreen(); }
      else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
        const i = choices.findIndex(c => c.entry.id === choice?.entry.id);
        const next = choices[i + (e.key === 'ArrowDown' ? 1 : -1)];
        if (next) { e.preventDefault(); select({ a: next.entry.id }); }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [toggleFullscreen, fullscreen, choices, choice, select]);

  const handleClose = () => { playSfx('medals-close'); navigate('/'); };
  const webgl = hasWebGL();
  const [hover, setHover] = useState<{ id: string; anchor: DOMRect } | null>(null);
  const hovered = hover ? choices.find(c => c.entry.id === hover.id) : undefined;

  const group = (c: AuraChoice): 'aura' | 'appearance' | 'exoskin' => (c.kind === 'aura' ? 'aura' : c.entry.kind === 'exoskin' ? 'exoskin' : 'appearance');
  const list = (kind: 'aura' | 'appearance' | 'exoskin') => choices.filter(c => group(c) === kind).map(c => {
    const current = c.entry.id === choice?.entry.id;
    const shown = choiceName(c, lang);
    return (
      <li key={c.entry.id} role="presentation">
        <button
          type="button" role="option" aria-selected={current}
          className={`${s.pill} ${current ? s.pillActive : ''}`}
          onClick={() => { playSfx('ui-click'); select({ a: c.entry.id }); }}
          onMouseEnter={e => setHover({ id: c.entry.id, anchor: e.currentTarget.getBoundingClientRect() })}
          onMouseLeave={() => setHover(null)}
        >
          <span className={s.pillSkin} aria-hidden="true" style={nineSlice(current ? 'pill-full-open' : 'pill-full', PILL_SLICE, { fill: true })} />
          {c.entry.icon && <img className={s.pillIcon} src={auraFile(c.entry.icon)} alt="" aria-hidden="true" width={20} height={20} />}
          <span className={`${s.pillLabel} ${c.entry.icon ? s.pillLabelIcon : ''} ${shown.official ? '' : s.pillLabelUnofficial}`}><span className={s.pillText}>{shown.text}</span></span>
        </button>
      </li>
    );
  });

  const showViewer = !!choice && webgl && !!chargen && (appearance || dress);
  return (
    <div className={`${s.screen} ${fullscreen ? s.hudHidden : ''}`}>
      {showViewer && (
        <Suspense fallback={null}>
          <AuraViewer
            ref={viewer}
            dress={appearance ? null : dress}
            appearance={appearance}
            fxUrl={fxUrl}
            objects={aura?.objects ?? {}}
            timeline={aura?.timeline ?? null}
            sceneUrl={sceneUrl}
            environment={scene?.environment ?? null}
            orbitMax={scene?.site?.orbit ?? null}
            height={appearance ? appearanceHeight(choice) : height}
            playing={playing}
            speed={Number(speed)}
            showFx={showFx}
            walking={walking && !!walk}
            walk={walk}
            assetUrl={auraFile}
            particleAtlas={index?.particleAtlas ?? null}
            soundUrl={muted ? null : auraFile}
            volume={volume}
            onReady={() => setReady(true)}
          />
        </Suspense>
      )}
      {choice && !ready && webgl && <div className={s.loading}>{t('auras.loading')}</div>}

      <div className={`${s.cartouche} ${s.hud}`}>
        <div className={s.plate}>
          <GameStrip base="title-plate" cap={38} />
          <span className={s.plateTitle}>{t('auras.title')}</span>
        </div>
      </div>

      {index === null && (
        <div className={`${s.card} ${s.hud}`} style={nineSlice('tooltip-frame', [4, 4, 4, 4])}>
          <div className={s.cardTitle}>{t('auras.missing')}</div>
          <div className={s.cardHint}>{t('auras.missingHint')} <code>python3 tools/extract_auras.py</code></div>
        </div>
      )}

      {index && choice && (
        <aside className={`${s.panel} ${s.hud}`} style={nineSlice('tooltip-frame', [4, 4, 4, 4])}>
          {race && (
            <div className={s.field}>
              <span className={s.fieldLabel}>{t('auras.race')}</span>
              <GameDropdown value={race} options={raceOptions} onChange={r => { playSfx('ui-click'); select({ r }); }} label={t('auras.race')} className={s.dropdown} />
            </div>
          )}
          {sexOptions.length > 0 && (
            <div className={s.field}>
              <span className={s.fieldLabel}>{t('auras.sex')}</span>
              <GameDropdown value={sex} options={sexOptions} onChange={x => { playSfx('ui-click'); select({ s: x }); }} label={t('auras.sex')} className={s.dropdown} />
            </div>
          )}
          {cls && (
            <div className={s.field}>
              <span className={s.fieldLabel}>{t('auras.class')}</span>
              <GameDropdown value={cls} options={classOptions} onChange={c => { playSfx('ui-click'); select({ cl: c }); }} label={t('auras.class')} className={s.dropdown} />
            </div>
          )}
          {chargen && (
            <div className={s.field}>
              <span className={s.fieldLabel}>{t('auras.outfit')}</span>
              <GameDropdown value={String(tier)} options={tierOptions} onChange={v => { playSfx('ui-click'); select({ t: Number(v) }); }} label={t('auras.outfit')} className={s.dropdown} />
            </div>
          )}
          <div className={s.lists} role="listbox" aria-label={t('auras.list')}>
            <div className={s.group}>{t('auras.wardrobe')}</div>
            <ul className={s.list}>{list('aura')}</ul>
            {choices.some(c => group(c) === 'exoskin') && <div className={s.group}>{t('auras.exoskins')}</div>}
            <ul className={s.list}>{list('exoskin')}</ul>
          </div>
        </aside>
      )}

      {index && choice && <AuraInfo choice={choice} lang={lang} auras={index.auras} />}
      {hovered && hover && (
        <GameTooltip anchor={hover.anchor} align="cursor" title={choiceName(hovered, lang).text}
          date={auraSinceLine(hovered, t)} hint={officialText(hovered.entry.description, lang)?.text} />
      )}

      {index && choice && (
        <div className={`${s.transport} ${a.transport} ${s.hud}`} style={nineSlice('tooltip-frame', [4, 4, 4, 4])}>
          <button type="button" className={s.button} onClick={() => { playSfx('ui-click'); setPlaying(p => !p); }} aria-label={playing ? t('auras.pause') : t('auras.play')}>
            <span className={s.buttonSkin} aria-hidden="true" style={nineSlice('pill-full', [0, 24, 0, 24], { fill: true })} />
            <svg className={s.glyph} viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
              {playing ? <path d="M4 2.5h3v11H4zM9 2.5h3v11H9z" fill="currentColor" /> : <path d="M4.5 2.5 13 8l-8.5 5.5z" fill="currentColor" />}
            </svg>
          </button>
          <button type="button" className={s.button} onClick={() => { playSfx('ui-click'); viewer.current?.resetView(); }} aria-label={t('auras.resetView')}>
            <span className={s.buttonSkin} aria-hidden="true" style={nineSlice('pill-full', [0, 24, 0, 24], { fill: true })} />
            <svg className={s.glyph} viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
              <path d="M8 2a6 6 0 1 0 6 6h-2a4 4 0 1 1-4-4V2zM8 0l3 3-3 3z" fill="currentColor" />
            </svg>
          </button>
          <label className={`${s.check} ${!aura?.fx ? s.checkOff : ''}`}>
            <span className={s.checkbox} style={{ backgroundImage: `url(${sprite(showFx && aura?.fx ? 'checkbox-on' : 'checkbox-off')})` }} aria-hidden="true" />
            <input type="checkbox" checked={showFx} disabled={!aura?.fx} onChange={e => { playSfx('ui-click'); setShowFx(e.target.checked); }} />
            {t('auras.fx')}
          </label>
          <label className={`${s.check} ${!walk ? s.checkOff : ''}`} title={walk ? undefined : t('auras.walkOff')}>
            <span className={s.checkbox} style={{ backgroundImage: `url(${sprite(walking && walk ? 'checkbox-on' : 'checkbox-off')})` }} aria-hidden="true" />
            <input type="checkbox" checked={walking && !!walk} disabled={!walk} onChange={e => { playSfx('ui-click'); setWalking(e.target.checked); }} />
            {t('auras.walk')}
          </label>
          <div className={s.speed}>
            <span className={s.fieldLabel}>{t('auras.speed')}</span>
            <GameDropdown value={speed} options={SPEEDS.map(v => ({ value: v, label: `×${v}` }))} onChange={setSpeed} width={62} label={t('auras.speed')} className={s.dropdown} />
          </div>
        </div>
      )}

      {index && webgl && <div className={`${s.hint} ${s.hud}`}>{t('auras.hint')}</div>}
      <button type="button" className={`${s.close} ${s.hud}`} style={{ backgroundImage: `url(${sprite('close-button')})` }} onClick={handleClose} aria-label={t('common.close')} />
      <SpeakerToggle className={`${s.speaker} ${s.hud}`} />
      <FullscreenToggle className={`${s.fullscreen} ${s.hud}`} fullscreen={fullscreen} onToggle={toggleFullscreen} />
    </div>
  );
}

export default AurasScreen;
