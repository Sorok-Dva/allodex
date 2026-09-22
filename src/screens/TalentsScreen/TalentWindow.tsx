import { useState, type CSSProperties, type ReactNode, type MouseEvent as ReactMouseEvent, type FocusEvent } from 'react';
import type { ClassTalents, TalentLang, UiLayout, UiWidget } from '@/data/talents.types';
import { boardOffset, bookPrereqs, fieldPrereqs, iconFile, placeWidget, talentName, textFor, type Prereq } from '@/data/talents.logic';
import { tex } from '@/lib/assets';
import { useI18n } from '@/lib/i18n';
import s from './TalentWindow.module.css';

export type Page = 'book' | 'field';
export type Skin = 'mana' | 'rage';
export type Hover = { key: string; prereqs: Prereq[]; anchor: DOMRect } | null;

type Ctx = {
  ui: UiLayout;
  data: ClassTalents;
  lang: TalentLang;
  page: Page;
  field: number;
  skin: Skin;
  setPage: (p: Page) => void;
  setField: (f: number) => void;
  onHover: (h: Hover) => void;
  onClose: () => void;
  labels: { book: string; field: string; close: string; points: (n: number) => string };
};

/** Widgets du client sans rôle sur le site (actions de jeu : valider, réinitialiser, changer de classe…). */
const HIDDEN = new Set(['CommitButtonHolder', 'ResetButton', 'Activate', 'ActivateTips', 'ClassChange', 'LinkRageLeft', 'LinkRageRight', 'Recommended', 'IconBackReady', 'IconBackDone', 'Count', 'TalentsNotifier']);

function texUrl(ui: UiLayout, key: string | undefined, skin: Skin): string | null {
  if (!key) return null;
  const swapped = skin === 'mana' ? key.replace('Rage', 'Mana') : key.replace('Mana', 'Rage');
  const k = ui.textures[swapped]?.file ? swapped : key;
  const file = ui.textures[k]?.file;
  return file ? `/game/talents/ui/${file}` : null;
}

/**
 * Textures d'état des boutons du « Contextructor » : le client ne donne dans l'addon que le
 * calque de survol (`…/CornerCross/CornerCrossHighlight`) ; l'état normal est la texture
 * sœur du même dossier (`CornerCrossNormal`), déjà extraite du client dans `public/game/textures`.
 */
function siblingState(ui: UiLayout, w: UiWidget, state: 'Normal' | 'Selected'): string | null {
  const hl = w.highlight?.find(Boolean)?.texture;
  const path = hl ? ui.textures[hl]?.path : undefined;
  if (!path || !path.includes('Contextructor/')) return null;
  return tex(path.replace(/\.\(UITexture\)\.bin$/, '').replace(/Highlight(ed)?$/, state));
}

/** Ordre de tracé du client : `Priority` croissante, la plus haute par-dessus (ordre du fichier à égalité). */
function byPriority(list: UiWidget[] | undefined): UiWidget[] {
  return (list ?? []).map((w, i) => ({ w, i })).sort((a, b) => (a.w.priority ?? 0) - (b.w.priority ?? 0) || a.i - b.i).map(x => x.w);
}

function bg(url: string | null): CSSProperties {
  return url ? { backgroundImage: `url(${url})` } : {};
}

function Icon({ name }: { name?: string }) {
  if (!name) return null;
  return <img className={s.icon} src={iconFile(name)} alt="" draggable={false} />;
}

function Node({ w, pw, ph, ctx, children }: { w: UiWidget; pw: number; ph: number; ctx: Ctx; children?: ReactNode }) {
  const r = placeWidget(w.place, pw, ph);
  const name = w.name ?? '';
  const style: CSSProperties = { left: r.x, top: r.y, width: r.w, height: r.h, ...bg(texUrl(ctx.ui, w.back?.texture, ctx.skin)) };
  const kids = (w.children ?? []).map((c, i) => <Node key={i} w={c} pw={r.w} ph={r.h} ctx={ctx} />);
  return <div className={s.widget} style={style} data-widget={name}>{kids}{children}</div>;
}

/** Case du livre (BasePanel<ligne><colonne>) ou de la grille (FieldButton<ligne><colonne>). */
function Cell({ w, pw, ph, ctx, talentKey, prereqs, frame }: { w: UiWidget; pw: number; ph: number; ctx: Ctx; talentKey: string; prereqs: Prereq[]; frame: string | undefined }) {
  const [hover, setHover] = useState(false);
  const r = placeWidget(w.place, pw, ph);
  const talent = ctx.data.talents[talentKey];
  const hl = w.highlight?.find(Boolean)?.texture ?? w.children?.flatMap(c => c.highlight ?? []).find(Boolean)?.texture;
  const show = (e: ReactMouseEvent<HTMLButtonElement> | FocusEvent<HTMLButtonElement>) => {
    setHover(true);
    ctx.onHover({ key: talentKey, prereqs, anchor: e.currentTarget.getBoundingClientRect() });
  };
  const hide = () => { setHover(false); ctx.onHover(null); };
  const label = talentName(talent, ctx.lang).text;
  return (
    <button
      type="button"
      className={s.cell}
      style={{ left: r.x, top: r.y, width: r.w, height: r.h, ...bg(texUrl(ctx.ui, frame, ctx.skin)) }}
      onMouseEnter={show} onFocus={show} onMouseLeave={hide} onBlur={hide}
      aria-label={label}
      data-talent={talentKey}
    >
      {(w.children ?? []).map((c, i) => {
        if (HIDDEN.has(c.name ?? '')) return null;
        const cr = placeWidget(c.place, r.w, r.h);
        const inner = c.name === 'CurrentTalent' ? c.children ?? [] : [c];
        const box = c.name === 'CurrentTalent' ? cr : { x: 0, y: 0, w: r.w, h: r.h };
        return (
          <div key={i} className={s.widget} style={{ left: box.x, top: box.y, width: box.w, height: box.h }}>
            {inner.map((g, j) => {
              if (HIDDEN.has(g.name ?? '')) return null;
              const gr = placeWidget(g.place, box.w, box.h);
              const isIcon = g.name === 'Icon';
              return (
                <div key={j} className={s.widget} style={{ left: gr.x, top: gr.y, width: gr.w, height: gr.h, ...(isIcon ? {} : bg(texUrl(ctx.ui, g.back?.texture, ctx.skin))) }}>
                  {isIcon && <Icon name={talent?.icon} />}
                </div>
              );
            })}
          </div>
        );
      })}
      {hover && hl && <span className={s.highlight} style={bg(texUrl(ctx.ui, hl, ctx.skin))} />}
    </button>
  );
}

function ContextButton({ w, pw, ph, ctx, selected, label, onClick, disabled, iconOnly }: { w: UiWidget; pw: number; ph: number; ctx: Ctx; selected?: boolean; label?: string; onClick?: () => void; disabled?: boolean; iconOnly?: boolean }) {
  const r = placeWidget(w.place, pw, ph);
  const normal = siblingState(ctx.ui, w, selected ? 'Selected' : 'Normal');
  const hl = w.highlight?.find(Boolean)?.texture;
  return (
    <button
      type="button"
      className={`${s.button} ${selected ? s.selected : ''}`}
      style={{ left: r.x, top: r.y, width: r.w, height: r.h, ...bg(normal) }}
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      aria-pressed={selected}
    >
      {hl && <span className={s.buttonHl} style={bg(texUrl(ctx.ui, hl, ctx.skin))} />}
      {label && !iconOnly && <span className={s.buttonLabel}>{label}</span>}
    </button>
  );
}

function renderWidget(w: UiWidget, pw: number, ph: number, ctx: Ctx, key: number): ReactNode {
  const name = w.name ?? '';
  if (HIDDEN.has(name)) return null;
  const r = placeWidget(w.place, pw, ph);
  const { data, lang } = ctx;

  if (name === 'BaseWindow' && ctx.page !== 'book') return null;
  if (name === 'TalentWindow' && ctx.page !== 'field') return null;

  let m = /^BasePanel(\d{1,2})(\d)$/.exec(name);
  if (m) {
    // 10 couches × 4 colonnes : BasePanel11…BasePanel104 (ligne, colonne).
    const row = Number(m[1]) - 1;
    const col = Number(m[2]) - 1;
    const cell = data.book.layers[row]?.cells[col];
    if (!cell) return null;
    return <Cell key={key} w={w} pw={pw} ph={ph} ctx={ctx} talentKey={cell.talent} prereqs={bookPrereqs(data, row, col)} frame={w.back?.texture} />;
  }
  m = /^FieldButton(\d)(\d)$/.exec(name);
  if (m) {
    const f = data.fields[ctx.field];
    if (!f) return null;
    const [dr, dc] = boardOffset(f);
    const row = Number(m[1]) - 1 - dr;
    const col = Number(m[2]) - 1 - dc;
    const cell = f.rows[row]?.[col];
    if (!cell) return null;
    return <Cell key={key} w={w} pw={pw} ph={ph} ctx={ctx} talentKey={cell.talent} prereqs={fieldPrereqs(f, row, col)} frame={undefined} />;
  }
  if (name === 'HeaderText') {
    return <div key={key} className={`${s.widget} ${s.header}`} style={{ left: r.x, top: r.y, width: r.w, height: r.h }}>{textFor(data.name, lang)?.text ?? data.code}</div>;
  }
  if (name === 'FieldName') {
    const f = data.fields[ctx.field];
    const text = ctx.page === 'book' ? ctx.labels.book : (textFor(f?.name, lang)?.text ?? `${ctx.labels.field} ${ctx.field + 1}`);
    return <div key={key} className={`${s.widget} ${s.fieldName}`} style={{ left: r.x, top: r.y, width: r.w, height: r.h }}>{text}</div>;
  }
  if (name === 'TalentPoints') {
    const layers = data.book.layers;
    const max = layers.length ? layers[layers.length - 1].points : null;
    if (ctx.page !== 'book' || max === null) return null;
    return <div key={key} className={`${s.widget} ${s.points}`} style={{ left: r.x, top: r.y, width: r.w, height: r.h }}>{ctx.labels.points(max)}</div>;
  }
  m = /^ChooseField0(\d)$/.exec(name);
  if (m) {
    const i = Number(m[1]);
    const f = data.fields[i];
    if (!f) return null;
    const active = ctx.page === 'field' && ctx.field === i;
    const back = active ? 'BookmarkRageActive' : 'BookmarkRageInactive';
    const iconW = w.children?.find(c => c.name === (active ? 'ActiveIcon' : 'InactiveIcon'));
    const ir = iconW ? placeWidget(iconW.place, r.w, r.h) : null;
    const label = textFor(f.name, lang)?.text ?? `${ctx.labels.field} ${i + 1}`;
    return (
      <button key={key} type="button" className={s.bookmark} style={{ left: r.x, top: r.y, width: r.w, height: r.h, ...bg(texUrl(ctx.ui, back, ctx.skin)) }}
        onClick={() => { ctx.setField(i); ctx.setPage('field'); }} aria-label={label} aria-pressed={active} title={label}>
        {ir && f.icon && <img className={s.bookmarkIcon} style={{ left: ir.x, top: ir.y, width: ir.w, height: ir.h }} src={iconFile(f.icon)} alt="" />}
      </button>
    );
  }
  if (name === 'Tab01' || name === 'Tab02') {
    const page: Page = name === 'Tab01' ? 'book' : 'field';
    return <ContextButton key={key} w={w} pw={pw} ph={ph} ctx={ctx} selected={ctx.page === page} label={page === 'book' ? ctx.labels.book : ctx.labels.field} onClick={() => ctx.setPage(page)} disabled={page === 'field' && !data.fields.length} />;
  }
  if (name === 'Tab03') return null;
  if (name === 'CornerCross') {
    return <ContextButton key={key} w={w} pw={pw} ph={ph} ctx={ctx} label={ctx.labels.close} onClick={ctx.onClose} iconOnly />;
  }
  if (name === 'CornerQuestion') {
    return <ContextButton key={key} w={w} pw={pw} ph={ph} ctx={ctx} disabled />;
  }
  const style: CSSProperties = { left: r.x, top: r.y, width: r.w, height: r.h, ...bg(texUrl(ctx.ui, w.back?.texture, ctx.skin)) };
  return (
    <div key={key} className={s.widget} style={style} data-widget={name}>
      {byPriority(w.children).map((c, i) => renderWidget(c, r.w, r.h, ctx, i))}
    </div>
  );
}

/**
 * Fenêtre des talents du client 17.0 (addon `ContextTalents`), reconstruite widget par
 * widget depuis le `pack.bin` : placements, calques et textures viennent de
 * `public/game/talents/ui/context_talents.json`. Le formulaire racine est posé à l'origine
 * (sa position écran 15 × 120 est celle du jeu, pas celle du site).
 */
export function TalentWindow(props: Omit<Ctx, 'labels'> & { scale?: number }) {
  const { t } = useI18n();
  const ctx: Ctx = {
    ...props,
    labels: {
      book: t('talents.book'), field: t('talents.field'), close: t('common.close'),
      points: (n: number) => t('talents.pointsTotal', { points: n }),
    },
  };
  const root = props.ui.root;
  const size = placeWidget({ x: { ...root.place.x, pos: 0 }, y: { ...root.place.y, pos: 0 } }, 0, 0);
  return (
    <div className={s.window} style={{ width: size.w, height: size.h, transform: props.scale && props.scale !== 1 ? `scale(${props.scale})` : undefined }} data-testid="talent-window">
      {byPriority(root.children).map((c, i) => renderWidget(c, size.w, size.h, ctx, i))}
    </div>
  );
}

export { Node as WidgetNode };
