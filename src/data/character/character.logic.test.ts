import { describe, expect, it } from 'vitest';
import type { ChargenData } from './chargen.types';
import {
  checkName, clampAppearance, defaultAppearance, newDescriptor, parseDescriptor, randomAppearance, serialize,
  shiftAppearance, templateFor, validateDescriptor, withSelection, DESCRIPTOR_KIND, DESCRIPTOR_VERSION,
} from './descriptor';
import { resolveLook } from './look';
import { findWidget, gameText, parseGameMarkup, placeAxis, placeWidget, uiScale } from './layout';
import { LocalCharacterStore } from './store';

/** Données réduites au format de `chargen.json` : deux races, une classe à familier. */
function data(): ChargenData {
  const tpl = (gender: 'male' | 'female') => ({
    gender, glb: `models/Kania${gender}.glb`, elements: ['body_0', 'face_0', 'face_1', 'hair_0', 'hair_1', 'robe_0', 'skirt_0'],
    hairColored: ['hair_1'], defaultDress: 'idress', underwear: 'iunder', baked: 'textures/skin.png',
    variations: {
      faces: ['iface0', 'iface1'], hairs: ['ihair1'], hairColors: ['#ffffff', '#5a369c', '#6b46b9'],
      skins: ['textures/skinA.png'], skinColors: ['#ffffff', '#fcf8eb'], default: { faces: 0, hairColors: 0, skinColors: 0 },
    },
  });
  return {
    schema: 1, client: 'test', texts: {}, progress: {}, raceOrder: ['Kania', 'Elf'], classOrder: ['DRUID', 'MAGE'],
    nameRules: [{ pattern: '[A-Za-z]+', min: 4, max: 13 }, { pattern: '[А-Яа-яЁё]+', min: 3, max: 14 }],
    factions: [{ id: 'League', name: null, races: ['Kania', 'Elf'] }],
    races: {
      Kania: { faction: 'League', name: { ru: 'Канийцы', en: 'Kanians', fr: 'Kanians' }, sexNames: {}, motto: null, desc: null, classes: ['DRUID', 'MAGE'], scene: 'Kania', pets: ['Lynx', 'Bear'] },
      Elf: { faction: 'League', name: null, sexNames: {}, motto: null, desc: null, classes: ['MAGE'], scene: 'Elf' },
    },
    classes: { DRUID: { name: null, label: null }, MAGE: { name: null, label: null } },
    combos: {
      'Kania/DRUID': { race: 'Kania', class: 'DRUID', name: null, title: null, desc: null, sexes: {
        male: { template: 'KaniaMale', pet: 'Lynx', growths: [{ start: 'chargenDruidStart', loop: 'chargenDruid', items: [{ slot: 'HELM', item: 'ihelm' }, { slot: 'ARMOR', item: 'iarmor' }], fx: [] }] },
        female: { template: 'KaniaFemale', pet: 'Bear', growths: [] } } },
      'Kania/MAGE': { race: 'Kania', class: 'MAGE', name: null, title: null, desc: null, sexes: { male: { template: 'KaniaMale', growths: [] } } },
      'Elf/MAGE': { race: 'Elf', class: 'MAGE', name: null, title: null, desc: null, sexes: { female: { template: 'KaniaFemale', growths: [] } } },
    },
    templates: { KaniaMale: tpl('male'), KaniaFemale: tpl('female') },
    pets: { Lynx: { gender: 'none', variations: { faces: ['ip1', 'ip2', 'ip3'] } }, Bear: { gender: 'none', variations: { faces: ['ip1'] } } },
    items: {
      idress: { hidden: { unisex: ['face_0', 'face_1', 'hair_0', 'hair_1', 'robe_0', 'skirt_0'] } },
      iunder: { patches: { male: [{ rect: [0, 0.5, 0.5, 1], texture: 'textures/under.png' }] } },
      iface0: { shapes: { unisex: [{ geoset: 'face_0' }] }, patches: { unisex: [{ rect: [0, 0.5, 0, 0.25], texture: 'textures/face0.png' }] } },
      iface1: { shapes: { unisex: [{ geoset: 'face_1' }] } },
      ihair1: { shapes: { unisex: [{ geoset: 'hair_1', texture: 'textures/hair1.png' }] }, patches: { unisex: [{ rect: [0, 0.5, 0.25, 0.375], texture: 'textures/scalp.png' }] } },
      ihelm: { shapes: { unisex: [{ model: 'attach/Helm.glb', locator: 'Head' }] }, hidden: { unisex: ['hair_1'] } },
      iarmor: { shapes: { unisex: [{ geoset: 'robe_0' }] }, underwear: 3, patches: { male: [{ rect: [0.5, 1, 0, 0.5], texture: 'textures/armor.png' }] } },
      ip1: {}, ip2: {}, ip3: {},
    },
    slots: ['HELM', 'ARMOR'],
  };
}

describe('descripteur de personnage', () => {
  it('crée un descripteur valide et versionné, familier compris', () => {
    const d = newDescriptor(data(), 'Kania');
    expect(d.kind).toBe(DESCRIPTOR_KIND);
    expect(d.version).toBe(DESCRIPTOR_VERSION);
    expect(d.class).toBe('DRUID');
    expect(d.pet?.template).toBe('Lynx');
    expect(validateDescriptor(data(), { ...d, name: 'Arwen' })).toEqual([]);
  });

  it('garde ce qui reste valable en changeant de classe et ramène l’apparence aux bornes', () => {
    const d0 = { ...newDescriptor(data(), 'Kania'), appearance: { faces: 1, hairColors: 2 } };
    const d1 = withSelection(data(), d0, { class: 'MAGE' });
    expect(d1.class).toBe('MAGE');
    expect(d1.appearance).toEqual({ faces: 1, hairs: 0, hairColors: 2, skins: 0, skinColors: 0 });
    expect(d1.pet).toBeNull();
    const d2 = withSelection(data(), d0, { race: 'Elf' });
    expect(d2.sex).toBe('female');
    expect(d2.class).toBe('MAGE');
  });

  it('décale en boucle, tire au hasard dans les bornes', () => {
    const tpl = templateFor(data(), 'Kania', 'DRUID', 'male');
    expect(shiftAppearance(tpl, { faces: 1 }, 'faces', 1).faces).toBe(0);
    expect(shiftAppearance(tpl, { hairColors: 0 }, 'hairColors', -1).hairColors).toBe(2);
    const r = randomAppearance(tpl, () => 0.999);
    expect(r).toEqual({ faces: 1, hairs: 0, hairColors: 2, skins: 0, skinColors: 1 });
    expect(clampAppearance(tpl, { faces: 9 }).faces).toBe(0);
    expect(defaultAppearance(tpl).faces).toBe(0);
  });

  it('applique les règles de nommage du client (un seul alphabet, longueurs)', () => {
    const d = data();
    expect(checkName(d, 'Arwen').ok).toBe(true);
    expect(checkName(d, 'Ива').ok).toBe(true);
    expect(checkName(d, 'Ab').reason).toBe('short');
    expect(checkName(d, 'Abcdefghijklmn').reason).toBe('long');
    expect(checkName(d, 'Arwenа').reason).toBe('mixed');
    expect(checkName(d, '1234').reason).toBe('alphabet');
    expect(checkName(d, '').reason).toBe('empty');
  });

  it('refuse les combinaisons et valeurs hors des données', () => {
    const d = { ...newDescriptor(data(), 'Kania'), name: 'Arwen' };
    const errors = validateDescriptor(data(), { ...d, class: 'WARRIOR', appearance: { faces: 7 }, version: 2 });
    expect(errors.map(e => e.path).sort()).toEqual(['appearance.faces', 'class', 'pet.template', 'sex', 'version']);
    expect(validateDescriptor(data(), { ...d, faction: 'Empire' })[0].path).toBe('faction');
  });

  it('se sérialise et se relit', () => {
    const d = { ...newDescriptor(data(), 'Kania'), name: 'Arwen' };
    const back = parseDescriptor(data(), serialize(d));
    expect(back.errors).toEqual([]);
    expect(back.descriptor).toEqual(d);
    expect(parseDescriptor(data(), '{').errors[0].message).toBe('invalid JSON');
  });
});

describe('apparence résolue', () => {
  it('montre visage et coiffure choisis, cache ce que la tenue par défaut cache', () => {
    const d = data();
    const look = resolveLook(d, 'KaniaMale', d.templates.KaniaMale, 'male', { faces: 1, hairColors: 1 }, [], { equipment: null, helmet: true });
    expect([...look.visible].sort()).toEqual(['body_0', 'face_1', 'hair_1']);
    expect(look.textures.hair_1).toBe('textures/hair1.png');
    expect(look.colors.hair_1).toBe('#5a369c');
    // Peau teinte, puis scalp teint de la couleur des cheveux, puis sous-vêtements.
    expect(look.bake.map(b => b.texture)).toEqual(['textures/skinA.png', 'textures/scalp.png', 'textures/under.png']);
    expect(look.bake[1].tint).toBe('#5a369c');
  });

  it('habille : le casque cache les cheveux et s’accroche à la tête, l’armure retire les sous-vêtements', () => {
    const d = data();
    const items = d.combos['Kania/DRUID'].sexes.male!.growths[0].items;
    const look = resolveLook(d, 'KaniaMale', d.templates.KaniaMale, 'male', {}, items, { equipment: 0, helmet: true });
    expect(look.visible.has('hair_1')).toBe(false);
    expect(look.visible.has('robe_0')).toBe(true);
    expect(look.attachments).toEqual([{ model: 'attach/Helm.glb', locator: 'Head', template: 'KaniaMale' }]);
    expect(look.bake.map(b => b.texture)).toContain('textures/armor.png');
    expect(look.bake.map(b => b.texture)).not.toContain('textures/under.png');
    const bare = resolveLook(d, 'KaniaMale', d.templates.KaniaMale, 'male', {}, items, { equipment: 0, helmet: false });
    expect(bare.visible.has('hair_1')).toBe(true);
    expect(bare.attachments).toEqual([]);
  });

  it('ne dessine pas un géoset sans texture', () => {
    const d = data();
    const look = resolveLook(d, 'KaniaMale', d.templates.KaniaMale, 'male', {}, [], { equipment: null, helmet: true }, new Set(['body_0', 'face_0']));
    expect(look.visible.has('hair_1')).toBe(true);           // texture apportée par la coiffure
    expect(look.visible.has('skirt_0')).toBe(false);
  });
});

describe('placement des widgets du client', () => {
  it('calcule les quatre alignements', () => {
    expect(placeAxis({ align: 'low', pos: 20, size: 380 }, 1000)).toEqual([20, 380]);
    expect(placeAxis({ align: 'high', high: 64, size: 132 }, 1000)).toEqual([804, 132]);
    expect(placeAxis({ align: 'center', pos: -130, size: 259 }, 1000)).toEqual([240.5, 259]);
    expect(placeAxis({ align: 'both', pos: 12, high: 8 }, 100)).toEqual([12, 80]);
    expect(placeAxis({ align: 'center', pos: -6 }, 150)).toEqual([-6, 150]);
    expect(placeWidget({ place: { x: { align: 'low', pos: 1, size: 2 }, y: { align: 'high', size: 10 } } }, 100, 50)).toEqual({ x: 1, y: 40, w: 2, h: 10 });
  });

  it('retrouve un widget par son chemin et réduit l’interface sur les petits écrans', () => {
    const root = { type: 'Form', name: 'MainForm', priority: 0, place: { x: { align: 'both' as const }, y: { align: 'both' as const } },
      children: [{ type: 'Panel', name: 'A', priority: 0, place: { x: { align: 'both' as const }, y: { align: 'both' as const } } }] };
    expect(findWidget(root, 'A')?.name).toBe('A');
    expect(findWidget(root, 'B')).toBeNull();
    expect(uiScale(1920, 1080)).toBe(1);
    expect(uiScale(1600, 900)).toBeCloseTo(900 / 1080);
  });

  it('lit le balisage des textes du client', () => {
    const spans = parseGameMarkup('<html><tip_white>Тип брони:</tip_white> <tip_green>ткань</tip_green><br/>\r\nfin</html>');
    expect(spans).toEqual([
      { text: 'Тип брони:', cls: 'tip_white' }, { text: ' ', cls: undefined }, { text: 'ткань', cls: 'tip_green' },
      { text: '', br: true }, { text: ' fin', cls: undefined },
    ]);
    expect(parseGameMarkup('min <r name="minSize"/>', { minSize: 4 })).toEqual([{ text: 'min ' }, { text: '4', cls: undefined }]);
    expect(gameText({ ru: 'Лига', en: 'League' }, 'fr')).toBe('League');
  });
});

describe('CharacterStore local', () => {
  function memory(): Storage {
    const map = new Map<string, string>();
    return {
      get length() { return map.size; }, clear: () => map.clear(), key: i => [...map.keys()][i] ?? null,
      getItem: k => map.get(k) ?? null, setItem: (k, v) => { map.set(k, v); }, removeItem: k => { map.delete(k); },
    };
  }

  it('crée, relit, remplace et supprime', async () => {
    const store = new LocalCharacterStore(memory());
    const d = { ...newDescriptor(data(), 'Kania'), name: 'Arwen' };
    const saved = await store.save(d);
    expect(saved.descriptor.createdAt).toBeTruthy();
    expect((await store.list()).length).toBe(1);
    await store.save({ ...d, name: 'Arwena' }, saved.id);
    expect((await store.get(saved.id))?.descriptor.name).toBe('Arwena');
    expect((await store.list()).length).toBe(1);
    await store.remove(saved.id);
    expect(await store.list()).toEqual([]);
  });

  it('ignore un stockage corrompu', async () => {
    const storage = memory();
    storage.setItem('allodex:characters', '{oops');
    expect(await new LocalCharacterStore(storage).list()).toEqual([]);
  });
});
