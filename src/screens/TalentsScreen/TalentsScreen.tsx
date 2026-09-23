import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { navigate, useRoute } from '@/lib/router';
import { T, tex, video } from '@/lib/assets';
import { useI18n } from '@/lib/i18n';
import { nineSlice } from '@/lib/nineSlice';
import { useGameAudio } from '@/lib/audio/useGameAudio';
import { GameTooltip } from '@/components/ui/GameTooltip';
import { SpeakerToggle } from '@/components/controls/SpeakerToggle';
import { useClassTalents, useTalentsIndex, useUiLayout } from '@/data/talents.api';
import { bookPrereqs, fieldPrereqs, resolveSelection, talentName, textFor } from '@/data/talents.logic';
import {
  addBook, addField, bookBlock, bookCell, checkShared, decodeBuilds, encodeBuilds, fieldBlock, fieldStart,
  fieldTalentRank, autoStart, linkedTalents, maxRank, minRank, removeBook, removeField, rulesFor, spentBeforeRow,
  type Build, type Builds, type Calc,
} from '@/data/talents.build';
import { createBuildTracker, type TrackedBuild } from '@/data/talents.track';
import { postBeacon, TRACKING_ENABLED } from '@/analytics/tracker';
import { toRoman } from '@/lib/roman';
import type { TalentLang } from '@/data/talents.types';
import { TalentBuilder, type Hover, type Target } from './TalentBuilder';
import { TalentCard } from './TalentCard';
import s from './TalentsScreen.module.css';

const FRAME: [number, number, number, number] = [4, 4, 4, 4];

/**
 * Registre des builds (`/api/talents/events`) : vue d'un build venu d'un lien, build composé
 * quand l'édition se pose, lien copié. Renvoie la fonction à appeler au partage.
 */
function useBuildTracking(current: TrackedBuild | null, fromLink: boolean, lang: string) {
  const langRef = useRef(lang);
  langRef.current = lang;
  const tracker = useMemo(() => createBuildTracker(e => { if (TRACKING_ENABLED) postBeacon('/api/talents/events', e); }, () => langRef.current), []);
  const started = useRef(false);
  const key = current ? `${current.v}|${current.c}|${current.b ?? ''}|${current.b2 ?? ''}` : null;
  useEffect(() => {
    if (!current) return;
    if (!started.current) { started.current = true; tracker.landed(current, fromLink); }
    else tracker.changed(current);
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps -- le contenu du build suffit
  useEffect(() => {
    const onHide = () => tracker.flush();
    const onVisibility = () => { if (document.visibilityState === 'hidden') tracker.flush(); };
    window.addEventListener('pagehide', onHide);
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      window.removeEventListener('pagehide', onHide);
      document.removeEventListener('visibilitychange', onVisibility);
      tracker.flush();
    };
  }, [tracker]);
  return () => { if (current) tracker.shared(current); };
}

function useViewport() {
  const read = () => ({ w: typeof window === 'undefined' ? 1920 : window.innerWidth, h: typeof window === 'undefined' ? 1080 : window.innerHeight });
  const [vp, setVp] = useState(read);
  useEffect(() => {
    const on = () => setVp(read());
    window.addEventListener('resize', on);
    return () => window.removeEventListener('resize', on);
  }, []);
  return vp;
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const area = document.createElement('textarea');
    area.value = text;
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand?.('copy') ?? false;
    area.remove();
    return ok;
  }
}

/**
 * Écran « Talents » : la fenêtre des talents du client 17.0 (addon `TalentBuilder`), remplie
 * avec la version et la classe choisies, et calculateur de build. Tout l'état vit dans l'URL
 * (`/talents?v=17.0&c=druid&b=1.2331…`) : un lien partagé restitue le build exact.
 */
export function TalentsScreen() {
  const { t, lang } = useI18n();
  const tl = lang as TalentLang;
  const { query } = useRoute();
  const { playSfx } = useGameAudio();
  const index = useTalentsIndex();
  const ui = useUiLayout();
  const qv = query.get('v'), qc = query.get('c'), qb = query.get('b'), qb2 = query.get('b2');
  const slot: 0 | 1 = query.get('s') === '2' ? 1 : 0;
  const sel = useMemo(() => (index.data ? resolveSelection(index.data, qv, qc) : { version: null, slug: null }), [index.data, qv, qc]);
  const shareError = index.data && (qv || qc || qb || qb2) ? checkShared(index.data, qv, qc) : null;
  const cls = useClassTalents(sel.version?.id ?? null, sel.slug);
  const data = cls.data && cls.data.version === sel.version?.id && cls.data.code.toLowerCase() === sel.slug ? cls.data : null;
  const points = sel.version?.points ?? null;
  const calc: Calc | null = useMemo(() => (data && ui.data ? { data, rules: rulesFor(points, ui.data.layout.rankCost) } : null), [data, ui.data, points]);
  // Deux builds (I : `b`, II : `b2`) ; un lien refusé (version/classe inconnue) n'en charge aucun.
  const shared = useMemo(() => (calc ? decodeBuilds(calc, shareError ? null : qb, shareError ? null : qb2) : null), [calc, qb, qb2, shareError]);
  const build: Build | null = shared ? shared.builds[slot] : null;
  const [hover, setHover] = useState<Hover>(null);
  const [copied, setCopied] = useState(false);
  const copyTimer = useRef<number | null>(null);
  const vp = useViewport();
  // Build affiché, recodé depuis l'état décodé (forme normale) ; aucun si le lien est refusé.
  const landedWithBuild = useRef(Boolean(qb || qb2));
  const codes = calc && shared && !shareError && sel.version && sel.slug ? encodeBuilds(calc, shared.builds) : null;
  const current: TrackedBuild | null = codes && sel.version && sel.slug ? { v: sel.version.id, c: sel.slug, ...codes } : null;
  const fromLink = landedWithBuild.current && Boolean(shared && !shared.errors.some(Boolean));
  const trackShare = useBuildTracking(current, fromLink, lang);

  useEffect(() => { document.title = `Allodex — ${t('talents.title')}`; }, [t]);
  useEffect(() => { playSfx('medals-open'); }, [playSfx]);
  useEffect(() => () => { if (copyTimer.current !== null) window.clearTimeout(copyTimer.current); }, []);

  const update = useCallback((next: Record<string, string | null>) => {
    const params = new URLSearchParams(window.location.search);
    for (const [k, v] of Object.entries(next)) {
      if (v === null) params.delete(k); else params.set(k, v);
    }
    for (const legacy of ['p', 'f']) params.delete(legacy);
    const q = params.toString();
    navigate(`/talents${q ? `?${q}` : ''}`, { replace: true });
  }, []);

  const commit = useCallback((next: Build | null) => {
    if (!calc || !shared || !next || !sel.version || !sel.slug) return;
    playSfx('ui-click');
    const builds: Builds = slot === 0 ? [next, shared.builds[1]] : [shared.builds[0], next];
    const codes = encodeBuilds(calc, builds);
    update({ v: sel.version.id, c: sel.slug, b: codes.b, b2: codes.b2 });
  }, [calc, shared, slot, sel, update, playSfx]);

  const onAdd = (target: Target, all: boolean) => {
    if (!calc || !build) return;
    commit(target.kind === 'book' ? addBook(calc, build, target.r, target.c, all) : addField(calc, build, target.f, target.r, target.c, all));
  };
  const onRemove = (target: Target, all: boolean) => {
    if (!calc || !build) return;
    commit(target.kind === 'book' ? removeBook(calc, build, target.r, target.c, all) : removeField(calc, build, target.f, target.r, target.c, all));
  };
  const onCopy = async () => {
    if (await copyText(window.location.href)) {
      trackShare();
      setCopied(true);
      if (copyTimer.current !== null) window.clearTimeout(copyTimer.current);
      copyTimer.current = window.setTimeout(() => setCopied(false), 1600);
    }
  };
  const handleClose = () => { playSfx('medals-close'); navigate('/'); };

  const versions = (index.data?.versions ?? []).filter(v => v.classes.length);
  // Nom de classe dans la langue du site ; le client 17.0 n'a pas de textes français : on
  // reprend alors le nom de la même classe dans la version la plus récente qui en a.
  const classLabel = (code: string, name: Partial<Record<TalentLang, string>>) => {
    if (name[tl]) return name[tl]!;
    for (const v of [...versions].reverse()) {
      const other = v.classes.find(x => x.code === code)?.name[tl];
      if (other) return other;
    }
    return textFor(name, tl)?.text ?? code;
  };
  const className = (slug: string) => {
    const c = sel.version?.classes.find(x => x.slug === slug);
    return c ? classLabel(c.code, c.name) : slug;
  };
  const pointsSource = points?.source;
  const versionMenu = {
    label: t('talents.versionButton', { v: sel.version?.id ?? '' }),
    value: sel.version?.id ?? '',
    options: versions.map(v => ({ value: v.id, label: v.label === v.id ? v.id : `${v.id} (${v.label})` })),
    onChange: (v: string) => {
      playSfx('ui-click');
      const next = versions.find(x => x.id === v);
      const c = next?.classes.some(x => x.slug === sel.slug) ? sel.slug : next?.classes[0]?.slug ?? null;
      update({ v, c, b: null, b2: null, s: null });
    },
  };
  const classMenu = {
    label: t('talents.classButton', { name: sel.slug ? className(sel.slug) : '' }),
    value: sel.slug ?? '',
    options: (sel.version?.classes ?? []).map(c => ({ value: c.slug, label: classLabel(c.code, c.name) })).sort((a, b) => a.label.localeCompare(b.label, lang)),
    onChange: (c: string) => { playSfx('ui-click'); update({ v: sel.version?.id ?? null, c, b: null, b2: null, s: null }); },
  };

  // Note en pied de fenêtre : lien refusé, sinon particularités de la version.
  let note: { text: string; tone: 'info' | 'error' } | null = null;
  if (shareError === 'version') note = { text: t('talents.errVersion', { v: qv ?? '—' }), tone: 'error' };
  else if (shareError === 'class') note = { text: t('talents.errClass', { c: qc ?? '—' }), tone: 'error' };
  else if (shared && shared.errors.some(Boolean)) {
    const parts = shared.errors.flatMap((e, i) => (e ? [t('talents.errBuild', { n: toRoman(i + 1), reason: t(`talents.err.${e}`) })] : []));
    note = { text: parts.join(' '), tone: 'error' };
  }
  else if (calc) {
    const info: string[] = [];
    if (calc.rules.bookPoints === null) info.push(t('talents.noteLimits'));
    if (calc.data.fields.some(f => f.rows.length < 9 || f.rows.some(r => r.length < 9))) info.push(t('talents.centered'));
    if (sel.version && sel.version.languages.length === 0) info.push(t('talents.internalNames'));
    if (info.length) note = { text: info.join(' '), tone: 'info' };
  }

  const main = ui.data?.root.children?.find(c => c.name === 'TalentsBuilder');
  const W = main?.place.x.size ?? 1810;
  const H = main?.place.y.size ?? 701;
  const fit = Math.min(1, (vp.w - 16) / W, (vp.h - 16) / H);
  // Écran étroit : pas en dessous de 0,5 (cases encore touchables), la page défile.
  const scale = vp.w < 900 ? Math.max(0.5, fit) : Math.max(0.3, fit);
  const bg = video('mainmenu');

  const status = (() => {
    if (!hover || !calc || !build) return null;
    const tg = hover.target;
    const linked = [...linkedTalents(calc.data, hover.talent)].map(k => talentName(calc.data.talents[k], tl).text);
    const linkLine = linked.length ? <><br />{t('talents.linked', { names: linked.slice(0, 6).join(', ') + (linked.length > 6 ? '…' : '') })}</> : null;
    if (tg.kind === 'book') {
      const rank = build.book[tg.r][tg.c];
      const max = maxRank(calc.data, tg.r, tg.c);
      const block = bookBlock(calc, build, tg.r, tg.c);
      const layer = calc.data.book.layers[tg.r];
      const cell = bookCell(calc.data, tg.r, tg.c);
      let why: string | null = null;
      if (block === 'threshold') why = t('talents.blockThreshold', { missing: (layer.points ?? 0) - spentBeforeRow(calc, build, tg.r) });
      else if (block === 'parent' && cell?.parent) why = t('talents.blockParent', { name: talentName(calc.data.talents[cell.parent], tl).text, rank: rank + 1 });
      else if (block === 'points') why = t('talents.blockPoints');
      return (
        <>
          <b>{t('talents.rankOf', { current: rank, total: max })}</b>
          {minRank(calc, tg.r, tg.c) > 0 && <> · {t('talents.startRank')}</>}
          {why && <><br /><em>{why}</em></>}
          {linkLine}
          <br />{t('talents.clickHint')}
        </>
      );
    }
    const field = calc.data.fields[tg.f];
    const cell = field.rows[tg.r][tg.c]!;
    const rank = fieldTalentRank(field, build.fields[tg.f], cell.talent);
    const [sr, sc] = fieldStart(field);
    const isStart = autoStart(field) && sr === tg.r && sc === tg.c;
    const block = build.fields[tg.f][tg.r][tg.c] ? null : fieldBlock(calc, build, tg.f, tg.r, tg.c);
    const why = block === 'isolated' ? t('talents.blockIsolated') : block === 'points' ? t('talents.blockPoints') : null;
    return (
      <>
        <b>{t('talents.rankOf', { current: rank.current, total: rank.total })}</b>
        {isStart && <> · {t('talents.startCell')}</>}
        {why && <><br /><em>{why}</em></>}
        {linkLine}
        <br />{t('talents.clickHint')}
      </>
    );
  })();

  return (
    <div className={s.screen}>
      <video className={s.bg} autoPlay muted loop playsInline poster={tex(`${T.main2}/Background_14_0_Temp`)}>
        <source src={bg.webm} type="video/webm" /><source src={bg.mp4} type="video/mp4" />
      </video>

      {index.error && (
        <div className={s.card} style={nineSlice('tooltip-frame', FRAME)}>
          <div className={s.cardTitle}>{t('talents.missing')}</div>
          <div className={s.cardHint}>{t('talents.missingHint')} <code>python3 tools/extract_talents.py</code></div>
        </div>
      )}

      <div className={s.stage}>
        <div className={s.frame} style={{ width: W * scale, height: H * scale }}>
          {ui.data && calc && build && (
            <div style={{ transform: scale !== 1 ? `scale(${scale})` : undefined, transformOrigin: 'top left', width: W, height: H }}>
              <TalentBuilder
                ui={ui.data} calc={calc} build={build} lang={tl}
                onAdd={onAdd} onRemove={onRemove} onHover={setHover}
                onClose={handleClose} onCopy={onCopy} onReset={() => { playSfx('ui-click'); update(slot === 0 ? { b: null } : { b2: null }); }}
                slot={slot} onSlot={i => { playSfx('ui-click'); setHover(null); update({ s: i === 1 ? '2' : null }); }}
                copied={copied} versionMenu={versionMenu} classMenu={classMenu} note={note}
                classLabel={className(sel.slug ?? '')} pointsSource={pointsSource}
              />
            </div>
          )}
          {(cls.loading || ui.loading) && !calc && <div className={s.loading}>{t('talents.loading')}</div>}
          {ui.error && <div className={s.loading}>{t('talents.uiMissing')}</div>}
        </div>
      </div>

      {calc && hover && (
        <GameTooltip anchor={hover.anchor} className={s.tooltip}>
          <TalentCard
            data={calc.data} talentKey={hover.talent} lang={tl} status={status}
            prereqs={hover.target.kind === 'book' ? bookPrereqs(calc.data, hover.target.r, hover.target.c) : fieldPrereqs(calc.data.fields[hover.target.f], hover.target.r, hover.target.c)}
          />
        </GameTooltip>
      )}

      <SpeakerToggle className={s.speaker} />
    </div>
  );
}
