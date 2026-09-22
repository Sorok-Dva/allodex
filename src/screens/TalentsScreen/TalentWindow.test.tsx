import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render } from '@testing-library/react';
import { I18nProvider } from '@/lib/i18n';
import type { ClassTalents, UiLayout, UiWidget } from '@/data/talents.types';
import { TalentWindow } from './TalentWindow';
import { TalentCard } from './TalentCard';

const cellChildren: UiWidget[] = [
  { type: 'WidgetPanel', name: 'IconBackDone', place: { x: { align: 'center', size: 40 }, y: { align: 'center', size: 40 } }, back: { type: 'WidgetLayerSimpleTexture', color: 'ffffffff', texture: 'FieldTalent' } },
  { type: 'WidgetPanel', name: 'Icon', place: { x: { align: 'center', size: 36 }, y: { align: 'center', size: 36 } } },
];

const ui: UiLayout = {
  addon: 'ContextTalents', version: '17.0', related: [],
  textures: {
    BaseTalentsRage: { path: 'Interface/Ingame/ContextTalents/RelatedTextures/BaseTalentsRage.(UITexture).bin', file: 'BaseTalentsRage.png' },
    BaseTalentsMana: { path: 'x', file: 'BaseTalentsMana.png' },
    FieldTalent: { path: 'y', file: 'FieldTalent.png' },
  },
  root: {
    type: 'WidgetForm', name: 'MainForm', place: { x: { align: 'low', pos: 15, size: 508 }, y: { align: 'low', pos: 120, size: 749 } },
    children: [{
      type: 'WidgetPanel', name: 'Parent', place: { x: { align: 'both' }, y: { align: 'both' } },
      children: [
        { type: 'WidgetPanel', name: 'WindowHeader', priority: 250, place: { x: { align: 'center', pos: -20, size: 270 }, y: { align: 'low', size: 44 } }, children: [
          { type: 'WidgetTextView', name: 'HeaderText', place: { x: { align: 'both', pos: 48, high: 45 }, y: { align: 'low', pos: 8, size: 22 } } },
        ] },
        { type: 'WidgetPanel', name: 'BaseWindow', priority: 50, place: { x: { align: 'low', size: 468 }, y: { align: 'low', pos: 13, size: 715 } }, back: { type: 'WidgetLayerSimpleTexture', color: 'ffffffff', texture: 'BaseTalentsRage' }, children: [
          { type: 'WidgetPanel', name: 'BasePanel11', place: { x: { align: 'low', pos: 89, size: 59 }, y: { align: 'low', pos: 85, size: 59 } }, children: [
            { type: 'WidgetButton', name: 'CurrentTalent', place: { x: { align: 'both' }, y: { align: 'both' } }, children: cellChildren },
          ] },
          { type: 'WidgetPanel', name: 'BasePanel12', place: { x: { align: 'low', pos: 167, size: 59 }, y: { align: 'low', pos: 85, size: 59 } } },
        ] },
        { type: 'WidgetPanel', name: 'TalentWindow', priority: 50, place: { x: { align: 'low', size: 468 }, y: { align: 'low', pos: 13, size: 715 } }, children: [
          { type: 'WidgetButton', name: 'FieldButton55', place: { x: { align: 'low', pos: 200, size: 36 }, y: { align: 'low', pos: 300, size: 36 } }, children: cellChildren },
          { type: 'WidgetButton', name: 'FieldButton11', place: { x: { align: 'low', pos: 56, size: 36 }, y: { align: 'low', pos: 179, size: 36 } }, children: cellChildren },
        ] },
        { type: 'WidgetPanel', name: 'Tabs', priority: 300, place: { x: { align: 'center', size: 216 }, y: { align: 'high', size: 40 } }, children: [
          { type: 'WidgetButton', name: 'Tab01', place: { x: { align: 'low', size: 72 }, y: { align: 'high', size: 39 } } },
          { type: 'WidgetButton', name: 'Tab02', place: { x: { align: 'low', pos: 72, size: 72 }, y: { align: 'high', size: 39 } } },
        ] },
        { type: 'WidgetPanel', name: 'ResetButton', priority: 250, place: { x: { align: 'low', size: 10 }, y: { align: 'low', size: 10 } } },
      ],
    }],
  },
};

const data: ClassTalents = {
  version: '9.9', code: 'WARRIOR', ref: '#1', name: { fr: 'Guerrier' }, languages: ['fr'], format: 'v1',
  book: { ref: '#2', layers: [{ points: 0, cells: [{ type: 'TalentSpell', talent: 't1' }, null, null, null] }] },
  fields: [{ ref: '#3', name: { fr: 'Combattant' }, icon: null, rows: [[{ type: 'TalentAbility', talent: 't2' }]] }],
  talents: {
    t1: { kind: 'spell', ref: 'a', name: { fr: 'Frappe' }, icon: 'abc.png', description: { fr: 'Inflige <r name="v"/> dégâts.' }, ranks: [{ ref: 'a', vars: { v: { value: 3 } } }, { ref: 'b', vars: { v: { value: 6 } } }] },
    t2: { kind: 'ability', ref: 'c', name: { fr: 'Rage' }, ranks: [{ ref: 'c' }] },
  },
};

function renderWindow(page: 'book' | 'field', extra: Partial<Parameters<typeof TalentWindow>[0]> = {}) {
  const props = {
    ui, data, lang: 'fr' as const, page, field: 0, skin: 'rage' as const,
    setPage: vi.fn(), setField: vi.fn(), onHover: vi.fn(), onClose: vi.fn(), ...extra,
  };
  const utils = render(<I18nProvider storage={null} initial="fr"><TalentWindow {...props} /></I18nProvider>);
  return { ...utils, props };
}

describe('TalentWindow', () => {
  it('pose le livre avec les textures et les placements du client', () => {
    const { container, getByText } = renderWindow('book');
    const base = container.querySelector('[data-widget="BaseWindow"]') as HTMLElement;
    expect(base.style.backgroundImage).toContain('/game/talents/ui/BaseTalentsRage.png');
    expect(base.style.top).toBe('13px');
    const cell = container.querySelector('[data-talent="t1"]') as HTMLElement;
    expect(cell.style.left).toBe('89px');
    expect(cell.querySelector('img')?.getAttribute('src')).toBe('/game/talents/icons/abc.png');
    // case vide (BasePanel12) non dessinée, grille masquée, widget d'action caché
    expect(container.querySelectorAll('[data-talent]')).toHaveLength(1);
    expect(container.querySelector('[data-widget="TalentWindow"]')).toBeNull();
    expect(container.querySelector('[data-widget="ResetButton"]')).toBeNull();
    expect(getByText('Guerrier')).toBeTruthy();
  });

  it('respecte la priorité de tracé (en-tête au-dessus du livre)', () => {
    const { container } = renderWindow('book');
    const order = Array.from(container.querySelectorAll('[data-widget="Parent"] > *')).map(e => (e as HTMLElement).dataset.widget ?? e.textContent);
    expect(order.indexOf('BaseWindow')).toBeLessThan(order.indexOf('WindowHeader'));
  });

  it('centre une grille 1 × 1 sur le damier et bascule d’onglet', () => {
    const { container, getByRole, props } = renderWindow('field');
    const cell = container.querySelector('[data-talent="t2"]') as HTMLElement;
    expect(cell.style.left).toBe('200px');           // FieldButton55 = centre du 9 × 9
    fireEvent.click(getByRole('button', { name: 'Livre' }));
    expect(props.setPage).toHaveBeenCalledWith('book');
  });

  it('change d’habillage (mana ↔ rage) quand la texture sœur existe', () => {
    const { container } = renderWindow('book', { skin: 'mana' });
    const base = container.querySelector('[data-widget="BaseWindow"]') as HTMLElement;
    expect(base.style.backgroundImage).toContain('BaseTalentsMana.png');
  });

  it('signale le survol pour l’infobulle', () => {
    const { container, props } = renderWindow('book');
    fireEvent.mouseEnter(container.querySelector('[data-talent="t1"]')!);
    expect(props.onHover).toHaveBeenCalledWith(expect.objectContaining({ key: 't1', prereqs: [] }));
  });
});

describe('TalentCard', () => {
  it('affiche nom, rangs, description avec valeur brute et tableau des rangs', () => {
    const { getByText, container } = render(
      <I18nProvider storage={null} initial="fr"><TalentCard data={data} talentKey="t1" prereqs={[{ kind: 'points', points: 4 }]} lang="fr" /></I18nProvider>,
    );
    expect(getByText('Frappe')).toBeTruthy();
    expect(getByText('Requiert 4 points de talent dépensés')).toBeTruthy();
    expect(getByText('[3]')).toBeTruthy();
    expect(container.querySelectorAll('tbody td')).toHaveLength(2);
  });
});
