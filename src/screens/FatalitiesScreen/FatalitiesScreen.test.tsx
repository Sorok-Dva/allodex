import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, act } from '@testing-library/react';
import type { FatalitiesIndex } from '@/lib/assets';
import { FatalitiesScreen, victimSummary } from './FatalitiesScreen';

const step = (anim: string, end: number, speed = 1) => ({ t: 0, end, anim, speed, mode: 'CLAMP' });
const timeline = (anim: string, end: number, speed = 1) => ({ end, victim: [step(anim, end, speed)], scale: [], alpha: [], spawns: [], attached: [] });
const INDEX: FatalitiesIndex = {
  races: { aed: { fr: 'Aède', en: 'Aed', faction: 'league' }, gibberling: { fr: 'Gibelin', en: 'Gibberling', faction: 'league' } },
  characters: [
    { id: 'aed-female', race: 'aed', sex: 'female', model: 'AedFemale', glb: 'characters/aed-female.glb', scale: 1.26, height: 2.29,
      animations: ['DeathFatality', 'DeathFatalityWarrior'], durations: { DeathFatality: 2.5, DeathFatalityWarrior: 11.7 } },
    { id: 'aed-male', race: 'aed', sex: 'male', model: 'AedMale', glb: 'characters/aed-male.glb', scale: 1.26, height: 2.56,
      animations: ['DeathFatality', 'DeathFatalityWarrior'], durations: { DeathFatality: 2.5, DeathFatalityWarrior: 11.7 } },
    { id: 'gibberling-male', race: 'gibberling', sex: 'male', model: 'GibberlingMale', glb: 'characters/gibberling-male.glb', scale: 1, height: 1.28,
      animations: ['DeathFatalityWarrior'], durations: { DeathFatalityWarrior: 10 } },
  ],
  fatalities: [
    { id: 'warrior', kind: 'class', label: { fr: 'Guerrier', en: 'Warrior' }, fx: 'fx/warrior.glb', fadeStart: 8.2, fadeDuration: 0.1,
      objects: {}, timelines: { 'aed-female': timeline('DeathFatalityWarrior', 11.7), 'aed-male': timeline('DeathFatalityWarrior', 11.7),
        'gibberling-male': timeline('DeathFatalityWarrior', 10) } },
    { id: 'phoenix', kind: 'shop', label: { fr: 'Phénix', en: 'Phoenix' }, fx: 'fx/phoenix.glb', objects: {},
      timelines: { 'aed-female': timeline('DeathFatalityPhoenix', 9, 0.6) } },
    { id: 'lotus', kind: 'shop', label: { fr: 'Lotus', en: 'Lotus' }, objects: {}, timelines: {} },
  ],
};

let index: FatalitiesIndex | null = INDEX;
vi.mock('@/lib/assets', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/assets')>();
  return { ...actual, fatalitiesIndex: () => index };
});

const playSfx = vi.fn();
vi.mock('@/lib/audio/useGameAudio', () => ({ useGameAudio: () => ({ playSfx }) }));

let webgl = false;
vi.mock('@/lib/webgl', () => ({ hasWebGL: () => webgl }));

const viewerProps = vi.fn();
vi.mock('@/components/scene/FatalityViewer', () => ({
  default: (props: Record<string, unknown>) => { viewerProps(props); return <canvas data-testid="fatality-viewer" />; },
}));

beforeEach(() => {
  index = INDEX;
  webgl = false;
  viewerProps.mockClear();
  window.history.replaceState(null, '', '/fatalities');
});

describe('victimSummary', () => {
  it('énumère les animations de la cible dans l’ordre du script, avec leur vitesse', () => {
    expect(victimSummary(INDEX.characters[0], INDEX.fatalities[0])).toBe('DeathFatalityWarrior');
    expect(victimSummary(INDEX.characters[0], INDEX.fatalities[1])).toBe('DeathFatalityPhoenix ×0.6');
    expect(victimSummary(INDEX.characters[2], INDEX.fatalities[2])).toBeNull();
  });
});

describe('FatalitiesScreen', () => {
  it('affiche la carte « non extraites » sans index', () => {
    index = null;
    const { getByText, queryByRole } = render(<FatalitiesScreen />);
    expect(getByText('Fatalités non extraites')).toBeTruthy();
    expect(queryByRole('listbox')).toBeNull();
  });

  it('liste les fatalités par groupe et signale WebGL absent', () => {
    const { getByText, getAllByRole } = render(<FatalitiesScreen />);
    expect(getByText('Fatalités de classe')).toBeTruthy();
    expect(getByText('Fatalités de la boutique')).toBeTruthy();
    expect(getAllByRole('option').map(o => o.textContent)).toEqual(['Guerrier', 'Phénix', 'Lotus']);
    expect(getByText(/WebGL indisponible/)).toBeTruthy();
  });

  it('met le choix dans l’URL et passe la chronologie de la cible au lecteur', async () => {
    webgl = true;
    window.history.replaceState(null, '', '/fatalities?c=gibberling-male&f=warrior');
    const { getByRole } = render(<FatalitiesScreen />);
    await act(async () => {});
    expect(viewerProps).toHaveBeenLastCalledWith(expect.objectContaining({
      characterUrl: '/game/fatalities/characters/gibberling-male.glb',
      fxUrl: '/game/fatalities/fx/warrior.glb',
      model: 'GibberlingMale',
      fadeStart: 8.2,
      timeline: INDEX.fatalities[0].timelines!['gibberling-male'],
    }));
    await act(async () => { fireEvent.click(getByRole('option', { name: /Lotus/ })); });
    expect(window.location.search).toBe('?c=gibberling-male&f=lotus');
    // Pas de chronologie pour ce personnage : le lecteur n'est pas monté.
    expect(getByRole('option', { name: /Lotus/ }).getAttribute('aria-selected')).toBe('true');
  });

  it('change de personnage par le menu Race sans perdre le sexe', async () => {
    webgl = true;
    window.history.replaceState(null, '', '/fatalities?c=aed-male&f=warrior');
    const { getByRole } = render(<FatalitiesScreen />);
    await act(async () => {});
    fireEvent.click(getByRole('combobox', { name: 'Race' }));
    await act(async () => { fireEvent.click(getByRole('option', { name: 'Gibelin' })); });
    expect(new URLSearchParams(window.location.search).get('c')).toBe('gibberling-male');
  });

  it('bascule lecture/pause au bouton et à la barre d’espace', async () => {
    webgl = true;
    const { getByRole } = render(<FatalitiesScreen />);
    await act(async () => {});
    expect(viewerProps).toHaveBeenLastCalledWith(expect.objectContaining({ playing: true }));
    await act(async () => { fireEvent.click(getByRole('button', { name: 'Pause' })); });
    expect(viewerProps).toHaveBeenLastCalledWith(expect.objectContaining({ playing: false }));
    await act(async () => { fireEvent.keyDown(window, { key: ' ' }); });
    expect(viewerProps).toHaveBeenLastCalledWith(expect.objectContaining({ playing: true }));
  });

  it('signale les effets absents', () => {
    window.history.replaceState(null, '', '/fatalities?f=lotus');
    const { getByText } = render(<FatalitiesScreen />);
    expect(getByText('Effet non extrait')).toBeTruthy();
  });
});
