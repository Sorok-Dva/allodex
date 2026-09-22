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
  addBook, addField, bookBlock, bookCell, checkShared, decodeBuild, emptyBuild, encodeBuild, fieldBlock, fieldStart,
  fieldTalentRank, autoStart, maxRank, minRank, removeBook, removeField, rulesFor, spentBeforeRow,
  type Build, type Calc,
} from '@/data/talents.build';
import type { TalentLang } from '@/data/talents.types';
import { TalentBuilder, type Hover, type Target } from './TalentBuilder';
import { TalentCard } from './TalentCard';
import s from './TalentsScreen.module.css';

const FRAME: [number, number, number, number] = [4, 4, 4, 4];

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
  const qv = query.get('v'), qc = query.get('c'), qb = query.get('b');
  const sel = useMemo(() => (index.data ? resolveSelection(index.data, qv, qc) : { version: null, slug: null }), [index.data, qv, qc]);
  const shareError = index.data && (qv || qc || qb) ? checkShared(index.data, qv, qc) : null;
  const cls = useClassTalents(sel.version?.id ?? null, sel.slug);
  const data = cls.data && cls.data.version === sel.version?.id && cls.data.code.toLowerCase() === sel.slug ? cls.data : null;
  const calc: Calc | null = useMemo(() => (data && ui.data ? { data, rules: rulesFor(data.version, ui.data.layout.rankCost) } : null), [data, ui.data]);
  const decoded = useMemo(() => (calc && qb && !shareError ? decodeBuild(calc, qb) : null), [calc, qb, shareError]);
  const build: Build | null = useMemo(() => (calc ? (decoded?.ok ? decoded.build : emptyBuild(calc)) : null), [calc, decoded]);
  const [hover, setHover] = useState<Hover>(null);
  const [copied, setCopied] = useState(false);
  const copyTimer = useRef<number | null>(null);
  const vp = useViewport();

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
    if (!calc || !next || !sel.version || !sel.slug) return;
    playSfx('ui-click');
    update({ v: sel.version.id, c: sel.slug, b: encodeBuild(calc, next) });
  }, [calc, sel, update, playSfx]);

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
  const versionMenu = {
    label: t('talents.versionButton', { v: sel.version?.id ?? '' }),
    value: sel.version?.id ?? '',
    options: versions.map(v => ({ value: v.id, label: v.label === v.id ? v.id : `${v.id} (${v.label})` })),
    onChange: (v: string) => {
      playSfx('ui-click');
      const next = versions.find(x => x.id === v);
      const c = next?.classes.some(x => x.slug === sel.slug) ? sel.slug : next?.classes[0]?.slug ?? null;
      update({ v, c, b: null });
    },
  };
  const classMenu = {
    label: t('talents.classButton', { name: sel.slug ? className(sel.slug) : '' }),
    value: sel.slug ?? '',
    options: (sel.version?.classes ?? []).map(c => ({ value: c.slug, label: classLabel(c.code, c.name) })).sort((a, b) => a.label.localeCompare(b.label, lang)),
    onChange: (c: string) => { playSfx('ui-click'); update({ v: sel.version?.id ?? null, c, b: null }); },
  };

  // Note en pied de fenêtre : lien refusé, sinon particularités de la version.
  let note: { text: string; tone: 'info' | 'error' } | null = null;
  if (shareError === 'version') note = { text: t('talents.errVersion', { v: qv ?? '—' }), tone: 'error' };
  else if (shareError === 'class') note = { text: t('talents.errClass', { c: qc ?? '—' }), tone: 'error' };
  else if (decoded && !decoded.ok) note = { text: t('talents.errBuild', { reason: t(`talents.err.${decoded.error}`) }), tone: 'error' };
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
                onClose={handleClose} onCopy={onCopy} onReset={() => { playSfx('ui-click'); update({ b: null }); }}
                copied={copied} versionMenu={versionMenu} classMenu={classMenu} note={note}
                classLabel={className(sel.slug ?? '')}
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
