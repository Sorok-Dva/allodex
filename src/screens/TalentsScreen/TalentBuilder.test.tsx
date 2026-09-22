import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render } from '@testing-library/react';
import { I18nProvider } from '@/lib/i18n';
import type { ClassTalents, UiLayer, UiLayout, UiWidget } from '@/data/talents.types';
import { addBook, emptyBuild, rulesFor, type Build, type Calc } from '@/data/talents.build';
import { TalentBuilder, layerStyle } from './TalentBuilder';
import { TalentCard } from './TalentCard';

const simple = (texture: string): UiLayer => ({ type: 'WidgetLayerSimpleTexture', color: 'ffffffff', texture });
const panel = (name: string, x: UiWidget['place']['x'], y: UiWidget['place']['y'], extra: Partial<UiWidget> = {}): UiWidget => ({ type: 'WidgetPanel', name, place: { x, y }, ...extra });
const buttonVariant = [{ normal: simple('ButtonRegularNormal'), highlight: simple('ButtonRegularHighlighted') }];

/** Arbre réduit de `TalentBuilder` (mêmes noms et placements que le client 17.0). */
const ui: UiLayout = {
  addon: 'TalentBuilder', version: '17.0', related: [], namedTextures: { BaseTalentNormal: 'BaseTalentBack' },
  textures: Object.fromEntries(['MainPanelBackground', 'TalentPanelBackActive', 'MilestoneChessPanelRed', 'MilestoneBackActive', 'BaseTalentBack', 'FieldTalent', 'FieldReady', 'LinkRageLeft', 'ButtonRegularNormal', 'ButtonRegularHighlighted', 'TalentBuiderHighlighted', 'Highlighted'].map(k => [k, { path: k, file: `${k}.png` }])),
  root: panel('MainForm', { align: 'both' }, { align: 'both' }, { children: [
    panel('TalentsBuilder', { align: 'low', pos: 10, size: 1810 }, { align: 'low', pos: 119, size: 701 }, {
      back: { type: 'WidgetLayerTiledTexture', color: 'ffffffff', texture: 'MainPanelBackground', slice: [65, 28, 90, 28], middle: [1440, 445], stretch: [1, 1] },
      children: [
        ...[1, 2, 3].map(i => panel(`MilestonePanel0${i}`, { align: 'low', size: 446 }, { align: 'center', size: 536.5 }, { back: simple('TalentPanelBackActive'), children: [
          panel('Chess', { align: 'center', size: 411 }, { align: 'center', size: 416 }, { back: simple('MilestoneChessPanelRed') }),
        ] })),
        panel('TalentsPanel', { align: 'low', pos: 19, size: 388 }, { align: 'center', size: 536.5 }, { back: simple('MilestoneBackActive') }),
        panel('BaseTalentsHeader', { align: 'center', pos: 11, size: 372 }, { align: 'low', pos: 27, size: 44 }, { children: [panel('Count', { align: 'center' }, { align: 'center', pos: 2, size: 18 })] }),
        panel('FieldTalentsHeader', { align: 'low', pos: 586, size: 1341 }, { align: 'low', pos: 27, size: 44 }, { children: [panel('Count', { align: 'center' }, { align: 'center', pos: 2, size: 18 })] }),
        panel('Controls', { align: 'both', pos: 19, high: 21 }, { align: 'high', high: 17, size: 41 }, { children: [
          { type: 'WidgetButton', name: 'ActivateBuild', place: { x: { align: 'center', pos: -27, size: 144 }, y: { align: 'center', size: 30 } }, variants: buttonVariant },
          panel('LearnSelected', { align: 'center', pos: -92, size: 105 }, { align: 'center', size: 30 }, { children: [
            { type: 'WidgetButton', name: 'CommitButton', place: { x: { align: 'low', size: 105 }, y: { align: 'low', size: 30 } }, variants: buttonVariant },
          ] }),
          { type: 'WidgetButton', name: 'ResetSelected', place: { x: { align: 'center', pos: 35, size: 105 }, y: { align: 'center', size: 30 } }, variants: buttonVariant },
          { type: 'WidgetButton', name: 'ChangeClass', place: { x: { align: 'low', pos: 205, size: 150 }, y: { align: 'center', size: 30 } }, variants: buttonVariant },
          { type: 'WidgetButton', name: 'SavedBuilds', place: { x: { align: 'low', pos: 7, size: 185 }, y: { align: 'center', size: 30 } }, variants: buttonVariant },
        ] }),
      ],
    }),
  ] }),
  templates: {
    BaseTalent: panel(null as unknown as string, { align: 'low', size: 59 }, { align: 'low', size: 59 }, { children: [
      { type: 'WidgetButton', name: 'Button', place: { x: { align: 'both' }, y: { align: 'both' } }, variants: [{ highlight: simple('Highlighted') }], children: [
        panel('Rank', { align: 'high', high: 4, size: 42 }, { align: 'high', high: 7, size: 18 }),
      ] },
    ] }),
    FieldTalentLearned: panel('IconBackDone', { align: 'center', size: 40 }, { align: 'center', size: 40 }, { back: simple('FieldTalent') }),
    FieldTalentReadyToLearn: panel('IconBackReady', { align: 'center', size: 36 }, { align: 'center', size: 36 }, { back: simple('FieldReady') }),
    FieldTalentHighlight: panel('Highlight', { align: 'both' }, { align: 'both' }, { back: simple('TalentBuiderHighlighted') }),
    BaseFieldLinkLeft: panel('LinkLeft', { align: 'low', size: 15 }, { align: 'low', size: 124 }, { back: { type: 'WidgetLayerTiledTexture', color: 'ffffffff', texture: 'LinkRageLeft', slice: [16, 0, 16, 16], middle: [0, 32], stretch: [0, 0] } }),
  },
  layout: {
    baseField: { SCALE: 0.9243724499999999, INTERVAL_Y: -3.6249899999999995, INTERVAL_X: 30.208249999999996, LEFT_BORDER: 42.291549999999994, UP_BORDER: 15.708289999999998, arrow: [14, 11, 24], side: { left: -9, right: 56 } },
    field: { INTERVAL_Y: 0, INTERVAL_X: 0, LEFT_BORDER: 36.2499, UP_BORDER: 79.74977999999999, SCALE: 1.1561180607 },
    builder: { fieldsInterval: 15, mainOffsetY: 117 },
    counts: { BASE_TALENTS_ROW_COUNT: 10, BASE_TALENTS_COL_COUNT: 4, FIELD_TALENTS_FIELD_COUNT: 3, FIELD_TALENTS_ROW_COUNT: 9, FIELD_TALENTS_COL_COUNT: 9 },
    rankCost: [1, 2, 3],
    fieldTalentSize: { main: 36, done: 40 },
    baseTalentSize: { main: 59, icon: 42 },
    fieldHighlight: { TALENT_HIGHLIGHT_FULL: [0.07, 0.48, 0.48, 1] },
    classColors: { WARRIOR: [0.56, 0.47, 0.29, 1] },
    classIcons: { WARRIOR: 'Warrior' },
  },
};

const three = [{ ref: 'a' }, { ref: 'b' }, { ref: 'c' }];
const data: ClassTalents = {
  version: '17.0', code: 'WARRIOR', ref: '#1', name: { fr: 'Guerrier' }, languages: ['fr'], format: 'v2',
  book: { ref: '#2', layers: [
    { points: 0, cells: [{ type: 'TalentSpell', talent: 't1' }, null, null, null] },
    { points: 1, cells: [{ type: 'TalentSpell', talent: 't3', parent: 't1' }, null, null, null] },
  ] },
  fields: [{ ref: '#3', name: { fr: 'Combattant' }, icon: null, rows: [[{ type: 'TalentAbility', talent: 't2' }]] }],
  talents: {
    t1: { kind: 'spell', ref: 'a', name: { fr: 'Frappe' }, icon: 'abc.png', description: { fr: 'Inflige <r name="v"/> dégâts.' }, ranks: [{ ref: 'a', vars: { v: { value: 3 } } }, { ref: 'b', vars: { v: { value: 6 } } }] },
    t2: { kind: 'ability', ref: 'c', name: { fr: 'Rage' }, ranks: [{ ref: 'c' }] },
    t3: { kind: 'spell', ref: 'd', name: { fr: 'Élan' }, ranks: three },
  },
};
const calc: Calc = { data, rules: rulesFor('17.0') };

function renderBuilder(build: Build = emptyBuild(calc)) {
  const props = {
    ui, calc, build, lang: 'fr' as const,
    onAdd: vi.fn(), onRemove: vi.fn(), onHover: vi.fn(), onClose: vi.fn(), onCopy: vi.fn(), onReset: vi.fn(), copied: false,
    versionMenu: { label: 'Version 17.0', value: '17.0', options: [{ value: '9.0', label: '9.0' }, { value: '17.0', label: '17.0' }], onChange: vi.fn() },
    classMenu: { label: 'Classe : Guerrier', value: 'warrior', options: [{ value: 'warrior', label: 'Guerrier' }], onChange: vi.fn() },
  };
  const utils = render(<I18nProvider storage={null} initial="fr"><TalentBuilder {...props} /></I18nProvider>);
  return { ...utils, props };
}

describe('TalentBuilder', () => {
  it('pose livre et grilles aux positions des scripts du client', () => {
    const { container } = renderBuilder();
    const book = container.querySelector('[data-talent="t1"]') as HTMLElement;
    expect(parseFloat(book.style.left)).toBeCloseTo(42.29, 1);          // LEFT_BORDER
    expect(parseFloat(book.style.width)).toBeCloseTo(54.54, 1);         // 59 × SCALE
    const panels = ['MilestonePanel01', 'MilestonePanel02', 'MilestonePanel03'].map(n => container.querySelector(`[data-widget="${n}"]`) as HTMLElement);
    expect(panels.map(p => p.style.left)).toEqual(['422px', '883px', '1344px']); // 19 + 388 + 15, pas de 446 + 15
    const cell = container.querySelector('[data-talent="t2"]') as HTMLElement;
    expect(parseFloat(cell.style.left)).toBeCloseTo(36.25 + 4 * 41.62, 1); // grille 1 × 1 centrée sur le 9 × 9
    expect(container.querySelector('[data-link="0:1"]')).toBeTruthy();
  });

  it('affiche les compteurs du jeu (libres/total) et l’état des cases', () => {
    const { getByTestId, container } = renderBuilder();
    expect(getByTestId('book-points').textContent).toBe('Points de compétence : 82/82');
    expect(getByTestId('field-points').textContent).toBe('Événements de développement : 77/77');
    const t1 = container.querySelector('[data-talent="t1"]') as HTMLElement;
    expect(t1.dataset.rank).toBe('1');                                   // sort de départ
    expect(t1.querySelector('img')?.className).not.toMatch(/disabled/);
    expect((container.querySelector('[data-talent="t3"]') as HTMLElement).dataset.state).toBe('available');
    expect((container.querySelector('[data-talent="t2"]') as HTMLElement).dataset.state).toBe('learned'); // départ de grille
  });

  it('met à jour les compteurs avec le build', () => {
    const b = addBook(calc, emptyBuild(calc), 0, 0)!;
    const { getByTestId } = renderBuilder(b);
    expect(getByTestId('book-points').textContent).toBe('Points de compétence : 80/82');
  });

  it('clic = +1, clic droit = −1, Maj = tout', () => {
    const { container, props } = renderBuilder();
    const cell = container.querySelector('[data-talent="t3"]') as HTMLElement;
    fireEvent.click(cell);
    expect(props.onAdd).toHaveBeenCalledWith({ kind: 'book', r: 1, c: 0 }, false);
    fireEvent.click(cell, { shiftKey: true });
    expect(props.onAdd).toHaveBeenLastCalledWith({ kind: 'book', r: 1, c: 0 }, true);
    fireEvent.contextMenu(cell);
    expect(props.onRemove).toHaveBeenCalledWith({ kind: 'book', r: 1, c: 0 }, false);
    fireEvent.keyDown(cell, { key: 'Delete' });
    expect(props.onRemove).toHaveBeenCalledTimes(2);
  });

  it('boutons du jeu : copier le lien, réinitialiser, listes version/classe', () => {
    const { getByRole, props } = renderBuilder();
    fireEvent.click(getByRole('button', { name: 'Copier le lien' }));
    expect(props.onCopy).toHaveBeenCalled();
    fireEvent.click(getByRole('button', { name: 'Réinitialiser' }));
    expect(props.onReset).toHaveBeenCalled();
    fireEvent.click(getByRole('button', { name: 'Version 17.0' }));
    fireEvent.click(getByRole('option', { name: '9.0' }));
    expect(props.versionMenu.onChange).toHaveBeenCalledWith('9.0');
  });

  it('signale le survol pour l’infobulle', () => {
    const { container, props } = renderBuilder();
    fireEvent.mouseEnter(container.querySelector('[data-talent="t1"]')!);
    expect(props.onHover).toHaveBeenCalledWith(expect.objectContaining({ talent: 't1', target: { kind: 'book', r: 0, c: 0 } }));
  });
});

describe('layerStyle', () => {
  it('texture découpée en neuf : tranches du client, réduites si le widget est plus petit', () => {
    const tiled = ui.templates.BaseFieldLinkLeft.back!;
    const st = layerStyle(ui, tiled, 8, 200);
    expect(st.borderImageSlice).toBe('16 0 16 16 fill');
    expect(st.borderImageWidth).toBe('8px 0px 8px 8px');
    expect(layerStyle(ui, simple('FieldTalent'), 10, 10).backgroundImage).toContain('/game/talents/ui/FieldTalent.png');
  });
});

describe('TalentCard', () => {
  it('affiche nom, état du build, description avec valeur brute et tableau des rangs', () => {
    const { getByText, container } = render(
      <I18nProvider storage={null} initial="fr"><TalentCard data={data} talentKey="t1" prereqs={[{ kind: 'points', points: 4 }]} lang="fr" status={<b>Rang 1/2</b>} /></I18nProvider>,
    );
    expect(getByText('Frappe')).toBeTruthy();
    expect(getByText('Rang 1/2')).toBeTruthy();
    expect(getByText('Requiert 4 points de talent dépensés')).toBeTruthy();
    expect(getByText('[3]')).toBeTruthy();
    expect(container.querySelectorAll('tbody td')).toHaveLength(2);
  });
});
