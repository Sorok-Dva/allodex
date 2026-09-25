import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, fireEvent, act } from '@testing-library/react';
import type { AurasIndex } from '@/lib/assets';
import { AurasScreen } from './AurasScreen';
import { avatarRaces, isExoskeleton, officialText, sinceParts } from './auras';

const INDEX: AurasIndex = {
  schema: 1,
  client: '17.0',
  auras: [
    { id: 'a740017009', resourceId: 740017009, name: { fr: 'Aura de Saint Patron', en: 'Patron’s Aura', ru: 'Аура Покровителя' },
      description: { fr: 'Recevez une aura spéciale.' }, icon: 'icons/PremiumTrace01.webp', visual: false,
      obtain: { fr: 'Un objet unique pour les utilisateurs Premium.' }, since: { version: '8.0', client: '8.0.02.61.1', previous: '7.0', method: 'icon' } },
    { id: 'a740017040', resourceId: 740017040, name: { fr: "Rune de l'esclavagiste", ru: 'Пурпурная руна Чемпиона' },
      description: { fr: "Vous confère l'effet Rune de l'Esclavagiste.\nUtilisez à nouveau pour annuler l'effet." },
      icon: 'icons/HeroHalo06.webp', visual: true, fx: 'fx/a740017040.glb', objects: {},
      timeline: { attached: [{ t: 0, vot: 'HeroesArena_Aura04', locator: 'Global', scale: 1 }], spawns: [] },
      obtain: { fr: "Obtenu pour avoir participé aux épreuves de l'Arène des héros." },
      items: [{ name: { fr: "Halo de l'esclavagiste" }, icon: 'icons/HeroHalo06.webp', resourceIds: [1] }],
      since: { version: '15.0', client: '15.0.03.23.2', previous: '11.0', method: 'resourceId' } },
    { id: 'a740249438', resourceId: 740249438, name: { ru: 'Аура Трувера' }, description: {}, icon: null, obtain: {}, visual: true, fx: 'fx/a740249438.glb',
      objects: {}, timeline: { attached: [], spawns: [] } },
  ],
  appearances: [
    { id: 's740178049', resourceId: 740178049, kind: 'exoskin', name: { fr: 'Néphalion' },
      description: { fr: "Couleur de robe spéciale pour la Carapace d'assaut Angelion." }, icon: null, auras: [],
      obtain: { fr: 'Sentier des incarnations, Tournoi du sang, été 2023' },
      skin: { resourceId: 740178049, name: { fr: 'Néphalion' }, mount: { fr: "Carapace d'assaut Angelion" } },
      model: { glb: 'models/s740178049.glb', vot: 'KaniaMale', objects: {} },
      visual: true, fx: 'fx/s740178049.glb', objects: {}, timeline: { attached: [{ t: 0, vot: 'MEV16Hunter_Dec', locator: 'Slot_Global', scale: 1 }], spawns: [] } },
  ],
  walks: { KaniaMale: { glb: 'walk/KaniaMale.glb', clips: { walk: 1, run: 0.6 }, speed: 2.1, runSpeed: 3.5 } },
};
const CHARGEN = {
  schema: 1, client: '17.0', texts: { Low: { fr: 'Départ' }, Medium: { fr: 'Intermédiaire' }, High: { fr: 'Supérieur' } },
  raceOrder: ['Kania', 'Elf'], classOrder: ['WARRIOR', 'MAGE'],
  races: { Kania: { faction: 'League', name: { fr: 'Kanians' }, classes: ['WARRIOR'] }, Elf: { faction: 'League', name: { fr: 'Elfes' }, classes: ['MAGE'] } },
  classes: { WARRIOR: { name: { fr: 'Guerrier' } }, MAGE: { name: { fr: 'Mage' } } },
  combos: {
    'Kania/WARRIOR': { race: 'Kania', class: 'WARRIOR', sexes: { male: { template: 'KaniaMale', growths: [{ items: [] }, { items: [] }, { items: [{ slot: 'Chest', item: 'X' }] }] } } },
    'Elf/MAGE': { race: 'Elf', class: 'MAGE', sexes: { female: { template: 'ElfFemale', growths: [{ items: [] }] } } },
  },
  templates: { KaniaMale: { glb: 'models/KaniaMale.glb', height: 1.867 }, ElfFemale: { glb: 'models/ElfFemale.glb', height: 2.2 } },
};

const playSfx = vi.fn();
vi.mock('@/lib/audio/useGameAudio', () => ({ useGameAudio: () => ({ playSfx, muted: false, volume: 1 }) }));
let webgl = false;
vi.mock('@/lib/webgl', () => ({ hasWebGL: () => webgl }));
vi.mock('@/lib/assets', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/assets')>();
  return { ...actual, fatalitiesIndex: () => ({ races: {}, characters: [], fatalities: [], scene: { glb: 'scene/scene.glb', site: { map: 'Kania', center: [0, 0], clear: 38, orbit: 45 } } }) };
});
const viewerProps = vi.fn();
vi.mock('@/components/scene/AuraViewer', () => ({
  default: (props: Record<string, unknown>) => { viewerProps(props); return <canvas data-testid="aura-viewer" />; },
}));

let index: AurasIndex | null = INDEX;
beforeEach(() => {
  index = INDEX;
  webgl = false;
  viewerProps.mockClear();
  window.history.replaceState(null, '', '/auras');
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const body = url.includes('auras.json') ? index : url.includes('chargen.json') ? CHARGEN : null;
    return { ok: body !== null, json: async () => body } as Response;
  }));
});
afterEach(() => { vi.unstubAllGlobals(); });

describe('helpers', () => {
  it('garde le texte officiel de la langue, sinon celui du client signalé', () => {
    expect(officialText({ fr: 'Rune' }, 'fr')).toEqual({ text: 'Rune', official: true });
    expect(officialText({ ru: 'Руна' }, 'fr')).toEqual({ text: 'Руна', official: false });
    expect(officialText({}, 'fr')).toBeNull();
  });
  it('reconnaît les gabarits d’exosquelette et lit la version', () => {
    expect(isExoskeleton('MountExo9')).toBe(true);
    expect(isExoskeleton('MEV13_Com')).toBe(true);
    expect(isExoskeleton('MountChopper')).toBe(false);
    expect(sinceParts({ version: '8.0', previous: '7.0', method: 'icon' })).toEqual({ version: '8.0', previous: '7.0', client: undefined, byIcon: true });
  });
  it('liste les races de la création avec leurs sexes', () => {
    expect(avatarRaces(CHARGEN as never)).toEqual([{ race: 'Kania', sexes: ['male'] }, { race: 'Elf', sexes: ['female'] }]);
  });
});

describe('AurasScreen', () => {
  it('affiche la carte « non extraites » sans index', async () => {
    index = null;
    const { getByText } = render(<AurasScreen />);
    await act(async () => {});
    expect(getByText('Auras non extraites')).toBeTruthy();
  });

  it('liste les auras de la garde-robe puis les couleurs de robe, noms officiels ou signalés', async () => {
    const { getByText, getAllByRole } = render(<AurasScreen />);
    await act(async () => {});
    expect(getByText('Cadeaux — Auras')).toBeTruthy();
    expect(getAllByRole('option').map(o => o.textContent)).toEqual([
      'Aura de Saint Patron', "Rune de l'esclavagiste", 'Аура Трувера', 'Néphalion']);
    expect(getByText('Carapaces : couleurs de robe')).toBeTruthy();
  });

  it('montre l’encart : description, version, obtention', async () => {
    window.history.replaceState(null, '', '/auras?a=a740017040');
    const { getByRole } = render(<AurasScreen />);
    await act(async () => {});
    const info = getByRole('region', { name: "Fiche de l'aura" });
    expect(info.textContent).toContain("Vous confère l'effet Rune de l'Esclavagiste.");
    expect(info.textContent).toContain('Apparition : version 15.0');
    expect(info.textContent).toContain('absente de la 11.0');
    expect(info.textContent).toContain("Obtention : Obtenu pour avoir participé aux épreuves de l'Arène des héros.");
    expect(info.textContent).toContain("Halo de l'esclavagiste");
  });

  it('dit « Source inconnue » et l’absence d’effet quand le client ne dit rien', async () => {
    window.history.replaceState(null, '', '/auras?a=a740249438');
    const first = render(<AurasScreen />);
    await act(async () => {});
    expect(first.getByRole('region', { name: "Fiche de l'aura" }).textContent).toContain('Obtention : Source inconnue');
    first.unmount();
    window.history.replaceState(null, '', '/auras?a=a740017009');
    const second = render(<AurasScreen />);
    await act(async () => {});
    expect(second.getByRole('region', { name: "Fiche de l'aura" }).textContent).toContain('Aucun effet visuel');
  });

  it('passe l’avatar habillé et l’aura au lecteur', async () => {
    webgl = true;
    window.history.replaceState(null, '', '/auras?a=a740017040');
    render(<AurasScreen />);
    await act(async () => {});
    expect(viewerProps).toHaveBeenLastCalledWith(expect.objectContaining({
      fxUrl: '/game/auras/fx/a740017040.glb',
      appearance: null,
      sceneUrl: '/game/fatalities/scene/scene.glb',
      orbitMax: 45,
      dress: expect.objectContaining({ template: 'KaniaMale', tier: 2 }),
    }));
  });

  it('montre la couleur de robe avec sa propre aura, et fait marcher l’avatar des auras à empreintes', async () => {
    webgl = true;
    window.history.replaceState(null, '', '/auras?a=s740178049');
    const first = render(<AurasScreen />);
    await act(async () => {});
    expect(viewerProps).toHaveBeenLastCalledWith(expect.objectContaining({
      appearance: expect.objectContaining({ url: '/game/auras/models/s740178049.glb' }),
      fxUrl: '/game/auras/fx/s740178049.glb', walk: null, walking: false,
    }));
    expect(first.getByRole('region', { name: "Fiche de l'aura" }).textContent).toContain("Couleur de robe de carapace — Carapace d'assaut Angelion");
    first.unmount();
    index = { ...INDEX, auras: INDEX.auras.map(a => (a.id === 'a740017009' ? { ...a, visual: true, fx: 'fx/a740017009.glb',
      timeline: { attached: [], spawns: [], stateAttached: [{ vot: 'PremiumTrace_Step_01All', locator: 'Global', scale: 1, states: ['run'] }] } } : a)) };
    window.history.replaceState(null, '', '/auras?a=a740017009');
    const second = render(<AurasScreen />);
    await act(async () => {});
    expect(viewerProps).toHaveBeenLastCalledWith(expect.objectContaining({
      walking: true, walk: { url: '/game/auras/walk/KaniaMale.glb', clips: { walk: 1, run: 0.6 }, speed: 3.5 },
    }));
    await act(async () => { fireEvent.click(second.getByRole('checkbox', { name: 'Marcher' })); });
    expect(viewerProps).toHaveBeenLastCalledWith(expect.objectContaining({ walking: false }));
  });

  it('coupe les effets à la case et met en pause à la barre d’espace', async () => {
    webgl = true;
    window.history.replaceState(null, '', '/auras?a=a740017040');
    const { getByRole } = render(<AurasScreen />);
    await act(async () => {});
    await act(async () => { fireEvent.click(getByRole('checkbox', { name: 'Effets' })); });
    expect(viewerProps).toHaveBeenLastCalledWith(expect.objectContaining({ showFx: false }));
    await act(async () => { fireEvent.keyDown(window, { key: ' ' }); });
    expect(viewerProps).toHaveBeenLastCalledWith(expect.objectContaining({ playing: false }));
  });
});
