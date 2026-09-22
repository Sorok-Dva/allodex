import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, act } from '@testing-library/react';
import type { FatalitiesIndex } from '@/lib/assets';
import { FatalitiesScreen, victimClip } from './FatalitiesScreen';

const INDEX: FatalitiesIndex = {
  races: { aed: { fr: 'Aède', en: 'Aed', faction: 'league' }, gibberling: { fr: 'Gibelin', en: 'Gibberling', faction: 'league' } },
  characters: [
    { id: 'aed-female', race: 'aed', sex: 'female', glb: 'characters/aed-female.glb', scale: 1.26, height: 2.29,
      animations: ['DeathFatality', 'DeathFatalityWarrior'], durations: { DeathFatality: 2.5, DeathFatalityWarrior: 11.7 } },
    { id: 'aed-male', race: 'aed', sex: 'male', glb: 'characters/aed-male.glb', scale: 1.26, height: 2.56,
      animations: ['DeathFatality', 'DeathFatalityWarrior'], durations: { DeathFatality: 2.5, DeathFatalityWarrior: 11.7 } },
    { id: 'gibberling-male', race: 'gibberling', sex: 'male', glb: 'characters/gibberling-male.glb', scale: 1, height: 1.28,
      animations: ['DeathFatalityWarrior01', 'DeathFatalityWarrior02'], durations: { DeathFatalityWarrior01: 10, DeathFatalityWarrior02: 10 } },
  ],
  fatalities: [
    { id: 'warrior', kind: 'class', label: { fr: 'Guerrier', en: 'Warrior' }, victim: 'DeathFatalityWarrior', fx: 'fx/warrior.glb' },
    { id: 'phoenix', kind: 'shop', label: { fr: 'Phénix', en: 'Phoenix' }, victim: 'DeathFatalityPhoenix', fx: 'fx/phoenix.glb', approx: true },
    { id: 'lotus', kind: 'shop', label: { fr: 'Lotus', en: 'Lotus' }, victim: 'DeathFatality' },
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

describe('victimClip', () => {
  it('prend le clip nommé par le manifeste, sinon la première variante qui commence pareil', () => {
    expect(victimClip(INDEX.characters[0], INDEX.fatalities[0])).toBe('DeathFatalityWarrior');
    expect(victimClip(INDEX.characters[2], INDEX.fatalities[0])).toBe('DeathFatalityWarrior01');
    expect(victimClip(INDEX.characters[2], INDEX.fatalities[2])).toBeNull();
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
    expect(getAllByRole('option').map(o => o.textContent)).toEqual(['Guerrier', 'Phénix≈', 'Lotus']);
    expect(getByText(/WebGL indisponible/)).toBeTruthy();
  });

  it('met le choix dans l’URL et passe le clip de la cible au lecteur', async () => {
    webgl = true;
    window.history.replaceState(null, '', '/fatalities?c=gibberling-male&f=warrior');
    const { getByRole } = render(<FatalitiesScreen />);
    await act(async () => {});
    expect(viewerProps).toHaveBeenLastCalledWith(expect.objectContaining({
      characterUrl: '/game/fatalities/characters/gibberling-male.glb',
      fxUrl: '/game/fatalities/fx/warrior.glb',
      clip: 'DeathFatalityWarrior01',
    }));
    await act(async () => { fireEvent.click(getByRole('option', { name: /Lotus/ })); });
    expect(window.location.search).toBe('?c=gibberling-male&f=lotus');
    // Le Gibelin n'a pas de clip `DeathFatality` : le lecteur n'est pas monté, la fiche l'annonce.
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

  it('signale les effets approximatifs ou absents', () => {
    window.history.replaceState(null, '', '/fatalities?f=phoenix');
    const { getByText, rerender } = render(<FatalitiesScreen />);
    expect(getByText(/Effet approximatif/)).toBeTruthy();
    window.history.replaceState(null, '', '/fatalities?f=lotus');
    window.dispatchEvent(new PopStateEvent('popstate'));
    rerender(<FatalitiesScreen />);
    expect(getByText('Effet non extrait')).toBeTruthy();
  });
});
