import { useEffect, useRef, useState, type CSSProperties, type ReactNode, type KeyboardEvent as ReactKeyboardEvent, type MouseEvent as ReactMouseEvent, type PointerEvent as ReactPointerEvent } from 'react';
import type { ClassTalents, Rgba, TalentLang, UiLayer, UiLayout, UiVariant, UiWidget } from '@/data/talents.types';
import { boardOffset, iconFile, placeAxis, placeWidget, textFor } from '@/data/talents.logic';
import {
  BOOK_COLS, bookBlock, bookSpent, fieldBlock, fieldSpent, maxRank,
  type Build, type Calc,
} from '@/data/talents.build';
import { nineSlice } from '@/lib/nineSlice';
import { toRoman } from '@/lib/roman';
import { useI18n } from '@/lib/i18n';
import s from './TalentBuilder.module.css';

/** Case survolée : livre (`f` absent) ou grille `f`. */
export type Target = { kind: 'book'; r: number; c: number } | { kind: 'field'; f: number; r: number; c: number };
export type Hover = { target: Target; talent: string; anchor: DOMRect } | null;
export type Menu = { label: string; value: string; options: { value: string; label: string }[]; onChange: (v: string) => void };

type Props = {
  ui: UiLayout;
  calc: Calc;
  build: Build;
  lang: TalentLang;
  /** +1 / −1 sur une case ; `all` : Maj (tous les rangs, toutes les cases du talent). */
  onAdd: (t: Target, all: boolean) => void;
  onRemove: (t: Target, all: boolean) => void;
  onHover: (h: Hover) => void;
  onClose: () => void;
  onCopy: () => void;
  onReset: () => void;
  copied: boolean;
  versionMenu: Menu;
  classMenu: Menu;
  note?: { text: string; tone: 'info' | 'error' } | null;
  /** Nom de la classe affiché sous le titre (repli sur les données de la version). */
  classLabel?: string;
};

const LONG_PRESS_MS = 450;

function texUrl(ui: UiLayout, key: string | undefined): string | null {
  const file = key ? ui.textures[key]?.file : undefined;
  return file ? `/game/talents/ui/${file}` : null;
}

function rgba([r, g, b, a]: Rgba): string {
  return `rgba(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)}, ${a})`;
}

/**
 * Style d'un calque du client : texture simple étirée sur le widget, ou texture découpée en
 * neuf (`WidgetLayerTiledTexture`) posée en `border-image` avec ses tranches en pixels,
 * réduites si le widget est plus petit que les bords.
 */
export function layerStyle(ui: UiLayout, layer: UiLayer | undefined | null, w: number, h: number): CSSProperties {
  const url = texUrl(ui, layer?.texture);
  if (!layer || !url) return {};
  if (!layer.slice) return { backgroundImage: `url(${url})`, backgroundSize: '100% 100%' };
  const [t, r, b, l] = layer.slice;
  const k = Math.min(1, l + r > 0 ? w / (l + r) : 1, t + b > 0 ? h / (t + b) : 1);
  const [sx, sy] = layer.stretch ?? [0, 0];
  const width = `${t * k}px ${r * k}px ${b * k}px ${l * k}px`;
  return {
    boxSizing: 'border-box', borderStyle: 'solid', borderColor: 'transparent', borderWidth: width,
    borderImageSource: `url(${url})`, borderImageSlice: `${t} ${r} ${b} ${l} fill`, borderImageWidth: width,
    borderImageRepeat: `${sx ? 'stretch' : 'round'} ${sy ? 'stretch' : 'round'}`,
  };
}

/** Calque de fond d'un widget, à part : les bords d'un `border-image` décaleraient les enfants. */
function Back({ ui, layer, w, h }: { ui: UiLayout; layer: UiLayer | undefined | null; w: number; h: number }) {
  const style = layerStyle(ui, layer, w, h);
  if (!style.backgroundImage && !style.borderImageSource) return null;
  return <span className={s.back} style={{ ...style, width: w, height: h }} />;
}

function box(x: number, y: number, w: number, h: number): CSSProperties {
  return { left: x, top: y, width: w, height: h };
}

function byPriority(list: UiWidget[] | undefined): UiWidget[] {
  return (list ?? []).map((w, i) => ({ w, i })).sort((a, b) => (a.w.priority ?? 0) - (b.w.priority ?? 0) || a.i - b.i).map(x => x.w);
}

function find(w: UiWidget | undefined, name: string): UiWidget | undefined {
  if (!w) return undefined;
  if (w.name === name) return w;
  for (const c of w.children ?? []) {
    const hit = find(c, name);
    if (hit) return hit;
  }
  return undefined;
}

/** Bouton du client : calque normal, survol (`highlight`), enfoncé, désactivé — ceux de ses variantes. */
function GameButton({ ui, variant, rect, label, onClick, disabled, children, title, pressed, className }: {
  ui: UiLayout; variant: UiVariant | undefined; rect: { x: number; y: number; w: number; h: number };
  label?: string; onClick?: () => void; disabled?: boolean; children?: ReactNode; title?: string; pressed?: boolean; className?: string;
}) {
  const layer = disabled ? variant?.disabled ?? variant?.normal : variant?.normal;
  return (
    <button
      type="button"
      className={`${s.button} ${className ?? ''}`}
      style={box(rect.x, rect.y, rect.w, rect.h)}
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      aria-pressed={pressed}
      title={title}
    >
      <Back ui={ui} layer={layer} w={rect.w} h={rect.h} />
      {variant?.pressed && <span className={s.pressed} style={{ ...layerStyle(ui, variant.pressed, rect.w, rect.h), width: rect.w, height: rect.h }} />}
      {variant?.highlight && <span className={s.hl} style={{ ...layerStyle(ui, variant.highlight, rect.w, rect.h), width: rect.w, height: rect.h }} />}
      {children}
    </button>
  );
}

/** Bouton du client qui ouvre une liste (version, classe) au-dessus de lui. */
function MenuButton({ ui, variant, rect, menu }: { ui: UiLayout; variant: UiVariant | undefined; rect: { x: number; y: number; w: number; h: number }; menu: Menu }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', esc);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc); };
  }, [open]);
  return (
    <div ref={ref} className={s.menuRoot} style={box(rect.x, rect.y, rect.w, rect.h)}>
      <GameButton ui={ui} variant={variant} rect={{ x: 0, y: 0, w: rect.w, h: rect.h }} onClick={() => setOpen(o => !o)} label={menu.label}>
        <span className={s.buttonLabel} aria-hidden>{menu.label}</span>
      </GameButton>
      {open && (
        <ul className={s.menu} role="listbox" aria-label={menu.label} style={nineSlice('dropdown-frame', [4, 4, 4, 4])}>
          {menu.options.map(o => (
            <li key={o.value} role="presentation">
              <button
                type="button" role="option" aria-selected={o.value === menu.value}
                className={`${s.option} ${o.value === menu.value ? s.optionActive : ''}`}
                onClick={() => { setOpen(false); menu.onChange(o.value); }}
              >{o.label}</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Gestes d'une case : clic (ou Entrée) = +1, clic droit (ou Suppr, Retour, « - ») = −1,
 * Maj = tous les rangs ; au toucher, appui long = −1 (menu contextuel neutralisé).
 */
function useCellGestures(target: Target, props: Props) {
  const timer = useRef<number | null>(null);
  const longPressed = useRef(false);
  const clear = () => { if (timer.current !== null) { window.clearTimeout(timer.current); timer.current = null; } };
  return {
    onClick: (e: ReactMouseEvent) => {
      if (longPressed.current) { longPressed.current = false; return; }
      props.onAdd(target, e.shiftKey);
    },
    onContextMenu: (e: ReactMouseEvent) => {
      e.preventDefault();
      if (longPressed.current) return;
      props.onRemove(target, e.shiftKey);
    },
    onPointerDown: (e: ReactPointerEvent) => {
      longPressed.current = false;
      if (e.pointerType !== 'touch') return;
      clear();
      timer.current = window.setTimeout(() => { longPressed.current = true; props.onRemove(target, false); }, LONG_PRESS_MS);
    },
    onKeyDown: (e: ReactKeyboardEvent) => {
      if (e.key === 'Delete' || e.key === 'Backspace' || e.key === '-') { e.preventDefault(); props.onRemove(target, e.shiftKey); }
    },
    onPointerUp: clear,
    onPointerLeave: clear,
    onPointerCancel: clear,
  };
}

function BookCell(props: Props & { r: number; c: number; x: number; y: number; size: number; hovered: string | null; setHovered: (k: string | null) => void }) {
  const { ui, calc, build, r, c, x, y, size, hovered } = props;
  const cell = calc.data.book.layers[r]?.cells[c];
  const target: Target = { kind: 'book', r, c };
  const gestures = useCellGestures(target, props);
  if (!cell) return null;
  const tpl = ui.templates.BaseTalent;
  const btn = find(tpl, 'Button');
  const rankW = find(tpl, 'Rank');
  const scale = size / ui.layout.baseTalentSize.main;
  const iconSize = ui.layout.baseTalentSize.icon * scale;
  const talent = calc.data.talents[cell.talent];
  const rank = build.book[r][c];
  const max = maxRank(calc.data, r, c);
  const rr = rankW ? placeWidget(rankW.place, size, size) : null;
  const name = textFor(talent?.name, props.lang)?.text ?? cell.talent;
  const blocked = bookBlock(calc, build, r, c);
  const same = hovered === cell.talent;
  const show = (e: { currentTarget: HTMLElement }) => {
    props.setHovered(cell.talent);
    props.onHover({ target, talent: cell.talent, anchor: e.currentTarget.getBoundingClientRect() });
  };
  const hide = () => { props.setHovered(null); props.onHover(null); };
  return (
    <button
      type="button"
      className={s.cell}
      style={{ ...box(x, y, size, size), ...layerStyle(ui, { type: 'WidgetLayerSimpleTexture', color: 'ffffffff', texture: ui.namedTextures.BaseTalentNormal }, size, size) }}
      aria-label={`${name} ${rank}/${max}`}
      data-talent={cell.talent}
      data-rank={rank}
      data-state={rank > 0 ? 'learned' : blocked ? 'locked' : 'available'}
      onMouseEnter={show} onFocus={show} onMouseLeave={hide} onBlur={hide}
      {...gestures}
    >
      {talent?.icon && (
        <img
          className={`${s.icon} ${rank > 0 ? '' : s.disabled}`}
          style={box((size - iconSize) / 2, (size - iconSize) / 2, iconSize, iconSize)}
          src={iconFile(talent.icon)} alt="" draggable={false}
        />
      )}
      {rank > 0 && rr && (
        <span className={`${s.rank} ${rank >= max ? s.rankMax : ''}`} style={box(rr.x, rr.y, rr.w, rr.h)}>{rank}</span>
      )}
      {btn?.variants?.[0]?.highlight && <span className={`${s.hl} ${same ? s.on : ''}`} style={layerStyle(ui, btn.variants[0].highlight, size, size)} />}
    </button>
  );
}

function FieldCell(props: Props & { f: number; r: number; c: number; x: number; y: number; size: number; hovered: string | null; setHovered: (k: string | null) => void }) {
  const { ui, calc, build, f, r, c, x, y, size, hovered } = props;
  const field = calc.data.fields[f];
  const cell = field.rows[r]?.[c];
  const target: Target = { kind: 'field', f, r, c };
  const gestures = useCellGestures(target, props);
  if (!cell) return null;
  const { main, done } = ui.layout.fieldTalentSize;
  const k = size / main;
  const talent = calc.data.talents[cell.talent];
  const learned = build.fields[f][r][c];
  const ready = !learned && !fieldBlock(calc, build, f, r, c);
  const doneSize = done * k;
  const same = hovered === cell.talent;
  const hlColor = ui.layout.fieldHighlight.TALENT_HIGHLIGHT_FULL;
  const hlTex = texUrl(ui, ui.templates.FieldTalentHighlight?.back?.texture);
  const name = textFor(talent?.name, props.lang)?.text ?? cell.talent;
  const show = (e: { currentTarget: HTMLElement }) => {
    props.setHovered(cell.talent);
    props.onHover({ target, talent: cell.talent, anchor: e.currentTarget.getBoundingClientRect() });
  };
  const hide = () => { props.setHovered(null); props.onHover(null); };
  return (
    <button
      type="button"
      className={s.cell}
      style={box(x, y, size, size)}
      aria-label={name}
      aria-pressed={learned}
      data-talent={cell.talent}
      data-state={learned ? 'learned' : ready ? 'available' : 'locked'}
      onMouseEnter={show} onFocus={show} onMouseLeave={hide} onBlur={hide}
      {...gestures}
    >
      {learned && (
        <span className={s.layer} style={{ ...box((size - doneSize) / 2, (size - doneSize) / 2, doneSize, doneSize), ...layerStyle(ui, ui.templates.FieldTalentLearned?.back, doneSize, doneSize) }} />
      )}
      {talent?.icon && <img className={`${s.icon} ${learned ? '' : s.disabled}`} style={box(0, 0, size, size)} src={iconFile(talent.icon)} alt="" draggable={false} />}
      {ready && <span className={s.layer} style={{ ...box(0, 0, size, size), ...layerStyle(ui, ui.templates.FieldTalentReadyToLearn?.back, size, size) }} />}
      {same && hlTex && (
        <span className={s.tint} style={{ ...box(0, 0, size, size), backgroundColor: rgba(hlColor), maskImage: `url(${hlTex})`, WebkitMaskImage: `url(${hlTex})` }} />
      )}
    </button>
  );
}

/** Liens parent → enfant du livre (même colonne), placés comme `ClassBaseField.PlaceArrows`. */
function bookLinks(calc: Calc): { col: number; from: number; to: number; right: boolean }[] {
  const pos = new Map<string, [number, number]>();
  calc.data.book.layers.forEach((l, r) => l.cells.forEach((cell, c) => { if (cell) pos.set(cell.talent, [r, c]); }));
  const pairs: { col: number; from: number; to: number }[] = [];
  calc.data.book.layers.forEach((l, r) => l.cells.forEach((cell, c) => {
    const p = cell?.parent ? pos.get(cell.parent) : undefined;
    if (p && p[1] === c && p[0] < r) pairs.push({ col: c, from: p[0], to: r });
  }));
  // Le jeu parcourt colonne par colonne, ligne par ligne ; le 2e lien d'une colonne passe à droite.
  pairs.sort((a, b) => a.col - b.col || a.from - b.from);
  const used = new Set<number>();
  return pairs.map(p => {
    if (used.has(p.col)) { used.add(p.col + 1); return { ...p, right: true }; }
    used.add(p.col);
    return { ...p, right: false };
  });
}

/**
 * Fenêtre « Talents » du client 17.0 (addon `TalentBuilder`) : le livre et les trois grilles
 * côte à côte, compteurs de points en tête, commandes en pied. Gabarits, textures et placements
 * viennent de `public/game/talents/ui/talent_builder.json` ; ce que le jeu calcule en script
 * (position des panneaux, des cases et des liens) suit les constantes lues dans son bytecode.
 */
export function TalentBuilder(props: Props) {
  const { t } = useI18n();
  const { ui, calc, build, lang } = props;
  const [hovered, setHovered] = useState<string | null>(null);
  const L = ui.layout;
  const main = ui.root.children?.find(c => c.name === 'TalentsBuilder') ?? ui.root;
  const W = main.place.x.size ?? 1810;
  const H = main.place.y.size ?? 701;
  const data: ClassTalents = calc.data;

  const talentsPanel = find(main, 'TalentsPanel');
  const panelW = talentsPanel?.place.x.size ?? 0;
  const firstPanelX = (talentsPanel?.place.x.pos ?? 0) + panelW + L.builder.fieldsInterval;

  const bookFree = calc.rules.bookPoints === null ? null : calc.rules.bookPoints - bookSpent(calc, build);
  const fieldFree = calc.rules.fieldPoints === null ? null : calc.rules.fieldPoints - fieldSpent(calc, build);
  const counters: Record<string, string> = {
    BaseTalentsHeader: bookFree === null
      ? t('talents.bookPointsSpent', { spent: bookSpent(calc, build) })
      : t('talents.bookPoints', { free: bookFree, total: calc.rules.bookPoints! }),
    FieldTalentsHeader: fieldFree === null
      ? t('talents.fieldPointsSpent', { spent: fieldSpent(calc, build) })
      : t('talents.fieldPoints', { free: fieldFree, total: calc.rules.fieldPoints! }),
  };

  const renderBook = () => {
    const B = L.baseField;
    const size = L.baseTalentSize.main * B.SCALE;
    const pos = (r: number, c: number) => [B.LEFT_BORDER + c * (size + B.INTERVAL_X), B.UP_BORDER + r * (size + B.INTERVAL_Y)] as const;
    const left = ui.templates.BaseFieldLinkLeft?.back;
    const right = ui.templates.BaseFieldLinkRight?.back;
    const links = bookLinks(calc).map((l, i) => {
      const [fx, fy] = pos(l.from, l.col);
      const [, ty] = pos(l.to, l.col);
      const lw = B.arrow[0] * B.SCALE;
      const lh = ty - fy + B.arrow[1] * B.SCALE;
      const lx = fx + (l.right ? B.side.right : B.side.left) * B.SCALE;
      const ly = fy + B.arrow[2] * B.SCALE;
      return <div key={`l${i}`} className={s.widget} style={box(lx, ly, lw, lh)} data-link={`${l.from}:${l.to}`}><Back ui={ui} layer={l.right ? right : left} w={lw} h={lh} /></div>;
    });
    const cells: ReactNode[] = [];
    data.book.layers.forEach((_, r) => {
      for (let c = 0; c < BOOK_COLS; c++) {
        const [x, y] = pos(r, c);
        cells.push(<BookCell key={`b${r}-${c}`} {...props} r={r} c={c} x={x} y={y} size={size} hovered={hovered} setHovered={setHovered} />);
      }
    });
    return <>{links}{cells}</>;
  };

  const renderField = (f: number) => {
    const field = data.fields[f];
    if (!field) return null;
    const F = L.field;
    const size = L.fieldTalentSize.main * F.SCALE;
    const [dr, dc] = boardOffset(field, L.counts.FIELD_TALENTS_ROW_COUNT);
    const cells: ReactNode[] = [];
    field.rows.forEach((row, r) => row.forEach((_, c) => {
      const x = F.LEFT_BORDER + (c + dc) * (size + F.INTERVAL_X);
      const y = F.UP_BORDER + (r + dr) * (size + F.INTERVAL_Y);
      cells.push(<FieldCell key={`f${f}-${r}-${c}`} {...props} f={f} r={r} c={c} x={x} y={y} size={size} hovered={hovered} setHovered={setHovered} />);
    }));
    return cells;
  };

  const renderChildren = (list: UiWidget[] | undefined, pw: number, ph: number): ReactNode[] => byPriority(list).map((w, i) => renderWidget(w, pw, ph, i));

  function renderWidget(w: UiWidget, pw: number, ph: number, key: number): ReactNode {
    const name = w.name ?? '';
    let rect = placeWidget(w.place, pw, ph);
    const m = /^MilestonePanel0(\d)$/.exec(name);
    if (m) {
      // `ClassBuilder.SetScale` : panneaux posés après le livre, espacés de `fieldsInterval`.
      const i = Number(m[1]) - 1;
      const [, size] = placeAxis(w.place.x, pw);
      rect = { ...rect, x: firstPanelX + i * (size + L.builder.fieldsInterval) };
      return (
        <div key={key} className={s.widget} style={box(rect.x, rect.y, rect.w, rect.h)} data-widget={name}>
          <Back ui={ui} layer={w.back} w={rect.w} h={rect.h} />
          {renderChildren(w.children, rect.w, rect.h)}
          {renderField(i)}
        </div>
      );
    }
    const style = box(rect.x, rect.y, rect.w, rect.h);
    const back = <Back ui={ui} layer={w.back} w={rect.w} h={rect.h} />;
    switch (name) {
      case 'TalentsPanel':
        return <div key={key} className={s.widget} style={style} data-widget={name}>{back}{renderBook()}</div>;
      case 'BaseTalentsHeader':
      case 'FieldTalentsHeader': {
        const count = find(w, 'Count');
        const cr = count ? placeWidget(count.place, rect.w, rect.h) : rect;
        return (
          <div key={key} className={s.widget} style={style} data-widget={name}>{back}
            <div className={`${s.widget} ${s.counter}`} style={box(0, cr.y, rect.w, cr.h || rect.h)} data-testid={name === 'BaseTalentsHeader' ? 'book-points' : 'field-points'}>{counters[name]}</div>
          </div>
        );
      }
      case 'WindowHeader': {
        const text = find(w, 'HeaderText');
        const tr = text ? placeWidget(text.place, rect.w, rect.h) : rect;
        return (
          <div key={key} className={s.widget} style={style} data-widget={name}>{back}
            <div className={`${s.widget} ${s.title}`} style={box(tr.x, tr.y, tr.w, tr.h)}>{t('talents.title')}</div>
          </div>
        );
      }
      case 'BuildPanel': {
        // `ClassBuilder` : panneau centré sur sa position (posX − largeur/2), icône teintée de la couleur de classe.
        const icon = find(w, 'Icon');
        const iconSize = icon?.place.x.size ?? 25;
        const tex = texUrl(ui, L.classIcons?.[data.code]);
        const color = L.classColors[data.code];
        const label = props.classLabel || (textFor(data.name, lang)?.text ?? data.code);
        return (
          <div key={key} className={`${s.widget} ${s.buildPanel}`} style={box(rect.x - 200, rect.y, 400, rect.h)} data-widget={name}>
            {tex && <span className={s.classIcon} style={{ width: iconSize, height: iconSize, backgroundColor: color ? rgba(color) : '#fff', maskImage: `url(${tex})`, WebkitMaskImage: `url(${tex})` }} />}
            <span className={s.className}>{label}</span>
          </div>
        );
      }
      case 'GoldenCorner':
      case 'QuestionCorner': {
        const btn = w.children?.[0];
        const br = btn ? placeWidget(btn.place, rect.w, rect.h) : null;
        const close = name === 'GoldenCorner';
        return (
          <div key={key} className={s.widget} style={style} data-widget={name}>{back}
            {btn && br && (
              <GameButton
                ui={ui} variant={btn.variants?.[0]} rect={br}
                label={close ? t('common.close') : t('talents.help')}
                title={close ? undefined : t('talents.helpText')}
                onClick={close ? props.onClose : undefined}
                className={close ? undefined : s.help}
              />
            )}
          </div>
        );
      }
      case 'Controls':
        return (
          <div key={key} className={s.widget} style={style} data-widget={name}>{back}
            {byPriority(w.children).map((c, i) => renderControl(c, rect.w, rect.h, i))}
          </div>
        );
      case 'ActiveBuildSelector': {
        // Deux builds dans le jeu ; le calculateur n'en édite qu'un : « I » actif, « II » inerte.
        const tpl = ui.templates.ActiveBuildSelectorVariant;
        if (!tpl) return null;
        return (
          <div key={key} className={s.widget} style={style} data-widget={name}>{back}
            {[0, 1].map(i => {
              const vr = placeWidget(tpl.place, rect.w, rect.h);
              const x = rect.w - (2 - i) * vr.w;
              const variant = tpl.variants?.[i === 0 ? 1 : 0];
              return (
                <div key={i} className={`${s.widget} ${s.buildVariant}`} style={box(x, vr.y, vr.w, vr.h)} title={t('talents.buildSlot', { n: toRoman(i + 1) })}>
                  <Back ui={ui} layer={variant?.normal} w={vr.w} h={vr.h} />
                  <span className={i === 0 ? s.buildActive : s.buildInactive}>{toRoman(i + 1)}</span>
                </div>
              );
            })}
          </div>
        );
      }
      default:
        return (
          <div key={key} className={s.widget} style={style} data-widget={name}>{back}
            {renderChildren(w.children, rect.w, rect.h)}
          </div>
        );
    }
  }

  function renderControl(w: UiWidget, pw: number, ph: number, key: number): ReactNode {
    const r = placeWidget(w.place, pw, ph);
    switch (w.name) {
      case 'SavedBuilds':
        return <MenuButton key={key} ui={ui} variant={w.variants?.[0]} rect={r} menu={props.versionMenu} />;
      case 'ChangeClass':
        return <MenuButton key={key} ui={ui} variant={w.variants?.[0]} rect={r} menu={props.classMenu} />;
      case 'LearnSelected': {
        const btn = find(w, 'CommitButton');
        return (
          <GameButton key={key} ui={ui} variant={btn?.variants?.[0]} rect={r} onClick={props.onCopy} label={t('talents.copyLink')}>
            <span className={s.buttonLabel} aria-hidden>{props.copied ? t('talents.copied') : t('talents.copyLink')}</span>
          </GameButton>
        );
      }
      case 'ResetSelected':
        return (
          <GameButton key={key} ui={ui} variant={w.variants?.[0]} rect={r} onClick={props.onReset} label={t('talents.reset')}>
            <span className={s.buttonLabel} aria-hidden>{t('talents.reset')}</span>
          </GameButton>
        );
      default:
        return null; // Activer le build, messages d'échec : actions du jeu sans objet ici.
    }
  }

  return (
    <div className={s.window} style={{ width: W, height: H }} data-testid="talent-builder" onContextMenu={e => e.preventDefault()}>
      <Back ui={ui} layer={main.back} w={W} h={H} />
      {renderChildren(main.children, W, H)}
      {props.note && (
        <div className={`${s.note} ${props.note.tone === 'error' ? s.noteError : ''}`} role={props.note.tone === 'error' ? 'alert' : undefined}>{props.note.text}</div>
      )}
    </div>
  );
}

