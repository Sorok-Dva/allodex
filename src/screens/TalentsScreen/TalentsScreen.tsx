import { useCallback, useEffect, useMemo, useState } from 'react';
import { navigate, useRoute } from '@/lib/router';
import { sprite, T, tex, video } from '@/lib/assets';
import { useI18n } from '@/lib/i18n';
import { nineSlice } from '@/lib/nineSlice';
import { useGameAudio } from '@/lib/audio/useGameAudio';
import { GameStrip } from '@/components/ui/GameStrip';
import { GameDropdown } from '@/components/ui/GameDropdown';
import { GameTooltip } from '@/components/ui/GameTooltip';
import { SpeakerToggle } from '@/components/controls/SpeakerToggle';
import { useClassTalents, useTalentsIndex, useUiLayout } from '@/data/talents.api';
import { resolveSelection, textFor } from '@/data/talents.logic';
import type { TalentLang } from '@/data/talents.types';
import { TalentWindow, type Hover, type Page, type Skin } from './TalentWindow';
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

/**
 * Écran « Talents » : la fenêtre des talents du client 17.0 reconstruite depuis ses
 * ressources, remplie avec les données de la version et de la classe choisies. Le choix
 * vit dans l'URL (`/talents?v=9.0&c=warrior&p=field&f=1`).
 */
export function TalentsScreen() {
  const { t, lang } = useI18n();
  const tl = lang as TalentLang;
  const { query } = useRoute();
  const { playSfx } = useGameAudio();
  const index = useTalentsIndex();
  const ui = useUiLayout();
  const sel = useMemo(() => (index.data ? resolveSelection(index.data, query.get('v'), query.get('c')) : { version: null, slug: null }), [index.data, query]);
  const cls = useClassTalents(sel.version?.id ?? null, sel.slug);
  const page: Page = query.get('p') === 'field' ? 'field' : 'book';
  const field = Math.max(0, Number(query.get('f') ?? 0) || 0);
  const [skin, setSkin] = useState<Skin>('rage');
  const [hover, setHover] = useState<Hover>(null);
  const vp = useViewport();

  useEffect(() => { document.title = `Allodex — ${t('talents.title')}`; }, [t]);
  useEffect(() => { playSfx('medals-open'); }, [playSfx]);

  const update = useCallback((next: Record<string, string | null>) => {
    const params = new URLSearchParams(window.location.search);
    for (const [k, v] of Object.entries(next)) {
      if (v === null) params.delete(k); else params.set(k, v);
    }
    navigate(`/talents?${params.toString()}`, { replace: true });
  }, []);

  const handleClose = () => { playSfx('medals-close'); navigate('/'); };

  const versions = (index.data?.versions ?? []).filter(v => v.classes.length);
  const versionOptions = versions.map(v => ({ value: v.id, label: v.label === v.id ? v.id : `${v.id} (${v.label})` }));
  const classOptions = (sel.version?.classes ?? []).map(c => ({ value: c.slug, label: textFor(c.name, tl)?.text ?? c.code }));
  const bg = video('mainmenu');

  // Fenêtre 508 × 749 à l'échelle 1:1 quand la hauteur le permet, sinon réduite.
  const scale = Math.min(1, Math.max(0.55, (vp.h - 48) / 749));
  const data = cls.data && cls.data.version === sel.version?.id ? cls.data : null;

  return (
    <div className={s.screen}>
      <video className={s.bg} autoPlay muted loop playsInline poster={tex(`${T.main2}/Background_14_0_Temp`)}>
        <source src={bg.webm} type="video/webm" /><source src={bg.mp4} type="video/mp4" />
      </video>

      <div className={s.cartouche}>
        <div className={s.plate}>
          <GameStrip base="title-plate" cap={38} />
          <span className={s.plateTitle}>{t('talents.title')}</span>
        </div>
      </div>

      {index.error && (
        <div className={s.card} style={nineSlice('tooltip-frame', FRAME)}>
          <div className={s.cardTitle}>{t('talents.missing')}</div>
          <div className={s.cardHint}>{t('talents.missingHint')} <code>python3 tools/extract_talents.py</code></div>
        </div>
      )}

      {sel.version && (
        <aside className={s.panel} style={nineSlice('tooltip-frame', FRAME)} data-testid="talents-panel">
          <div className={s.field}>
            <span className={s.fieldLabel}>{t('talents.version')}</span>
            <GameDropdown value={sel.version.id} options={versionOptions} onChange={v => { playSfx('ui-click'); update({ v, f: null }); }} label={t('talents.version')} className={s.dropdown} />
          </div>
          <div className={s.field}>
            <span className={s.fieldLabel}>{t('talents.class')}</span>
            <GameDropdown value={sel.slug ?? ''} options={classOptions} onChange={c => { playSfx('ui-click'); update({ c, f: null }); }} label={t('talents.class')} className={s.dropdown} />
          </div>
          <div className={s.field}>
            <span className={s.fieldLabel}>{t('talents.skin')}</span>
            <GameDropdown value={skin} options={[{ value: 'rage', label: t('talents.skinRage') }, { value: 'mana', label: t('talents.skinMana') }]} onChange={v => setSkin(v as Skin)} label={t('talents.skin')} className={s.dropdown} />
          </div>
          <div className={s.details}>
            <div className={s.detailTitle}>{t('talents.source')}</div>
            <div>{sel.version.client}</div>
            <div className={s.detailTitle}>{t('talents.languages')}</div>
            <div>{sel.version.languages.length ? sel.version.languages.map(l => l.toUpperCase()).join(', ') : t('talents.noTexts')}</div>
            {data && (
              <>
                <div className={s.detailTitle}>{t('talents.systems')}</div>
                <div>{t('talents.systemBook', { layers: data.book.layers.length })}</div>
                {data.fields.length > 0 && (
                  <div>{t('talents.systemFields', { count: data.fields.length, rows: data.fields[0].rows.length, cols: Math.max(0, ...data.fields[0].rows.map(r => r.length)) })}</div>
                )}
                <div className={s.detailTitle}>{t('talents.count')}</div>
                <div>{Object.keys(data.talents).length}</div>
              </>
            )}
            {sel.version.languages.length === 0 && <div className={s.warn}>{t('talents.internalNames')}</div>}
            {data && data.fields.some(f => f.rows.length < 9 || f.rows.some(r => r.length < 9)) && <div className={s.warn}>{t('talents.centered')}</div>}
            {index.data && index.data.unavailable.length > 0 && (
              <details className={s.unavailable}>
                <summary>{t('talents.unavailable')}</summary>
                <ul>{index.data.unavailable.map(u => <li key={u.id}><b>{u.id}</b> — {u.reason}</li>)}</ul>
              </details>
            )}
          </div>
        </aside>
      )}

      <div className={s.stage} style={{ width: 508 * scale, height: 749 * scale }}>
        {ui.data && data && (
          <TalentWindow
            ui={ui.data}
            data={data}
            lang={tl}
            page={page}
            field={Math.min(field, Math.max(0, data.fields.length - 1))}
            skin={skin}
            scale={scale}
            setPage={p => { playSfx('ui-click'); update({ p }); }}
            setField={f => update({ f: String(f) })}
            onHover={setHover}
            onClose={handleClose}
          />
        )}
        {(cls.loading || ui.loading) && !data && <div className={s.loading}>{t('talents.loading')}</div>}
        {ui.error && <div className={s.loading}>{t('talents.uiMissing')}</div>}
      </div>

      {data && hover && (
        <GameTooltip anchor={hover.anchor} className={s.tooltip}>
          <TalentCard data={data} talentKey={hover.key} prereqs={hover.prereqs} lang={tl} />
        </GameTooltip>
      )}

      <button type="button" className={s.close} style={{ backgroundImage: `url(${sprite('close-button')})` }} onClick={handleClose} aria-label={t('common.close')} />
      <SpeakerToggle className={s.speaker} />
    </div>
  );
}
