import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render } from '@testing-library/react';
import { MusicScreen, cleanMusicName } from './MusicScreen';
import type { MusicTrack } from '@/lib/assets';
import { I18nProvider } from '@/lib/i18n';

const fixture: MusicTrack[] = [
  { id: 'a', name: 'MainMenu_A_NM', title: { fr: 'Premier thème', en: 'First theme' }, bank: 'Music_Menu', group: 'Menu', duration: 123, ogg: '/game/music/a.ogg', mp3: '/game/music/a.mp3', client: '16.0' },
  { id: 'b', name: 'Menu_B_Adaptive', title: null, bank: 'Music_Menu', group: 'Menu', duration: 64, ogg: '/game/music/b.ogg', mp3: '/game/music/b.mp3', client: '17.0' },
  { id: 'c', name: 'Zone_C', title: null, bank: 'Music_Zone', group: 'Zones', duration: 180, ogg: '/game/music/c.ogg', mp3: '/game/music/c.mp3', client: '16.0' },
];
let tracks = fixture;
const audio = { playSfx: vi.fn(), playExternal: vi.fn(), pauseMusic: vi.fn(), resumeAmbient: vi.fn(), playing: false, external: null as string | null, ended: null as string | null, muted: false, toggleMuted: vi.fn() };
vi.mock('@/lib/assets', async original => ({ ...await original<typeof import('@/lib/assets')>(), musicTracks: () => tracks }));
vi.mock('@/lib/audio/useGameAudio', () => ({ useGameAudio: () => audio }));
vi.mock('@/lib/router', () => ({ navigate: vi.fn() }));
import { navigate } from '@/lib/router';

beforeEach(() => { vi.clearAllMocks(); tracks = fixture; audio.playing = false; audio.external = null; audio.ended = null; });
afterEach(cleanup);

describe('MusicScreen', () => {
  it('nettoie les noms sans inventer de titre', () => {
    expect(cleanMusicName('AC5_Main_NM')).toBe('AC5 Main');
    expect(cleanMusicName('MainMenu_Adaptive.wav')).toBe('MainMenu');
    expect(cleanMusicName('JungleAdaptive')).toBe('Jungle');
  });
  it('affiche les catégories, les pistes et leur durée', () => {
    const page = render(<MusicScreen />);
    expect(page.getByText('Premier thème')).toBeTruthy();
    expect(page.getByText('MainMenu_A_NM')).toBeTruthy();
    expect(page.getAllByTestId('theme-duration')[0].textContent).toBe('2:03');
    fireEvent.click(page.getByRole('button', { name: 'Zones' }));
    expect(page.getByText('Zone C')).toBeTruthy();
    expect(page.queryByText('Premier thème')).toBeNull();
  });
  it('lit la bonne source, met en pause et reprend via le même identifiant', () => {
    const page = render(<MusicScreen />);
    expect(audio.pauseMusic).toHaveBeenCalledOnce();
    fireEvent.click(page.getByRole('button', { name: 'Lire Premier thème' }));
    expect(audio.playExternal).toHaveBeenCalledWith('music:a', { ogg: fixture[0].ogg, mp3: fixture[0].mp3 }, { loop: false, crossfadeMs: 600 });
    audio.external = 'music:a'; audio.playing = true;
    page.rerender(<MusicScreen />);
    fireEvent.click(page.getByRole('button', { name: 'Mettre Premier thème en pause' }));
    expect(audio.pauseMusic).toHaveBeenCalledTimes(2);
    audio.playing = false; page.rerender(<MusicScreen />);
    fireEvent.click(page.getByRole('button', { name: 'Lire Premier thème' }));
    expect(audio.playExternal).toHaveBeenCalledTimes(2);
  });
  it('enchaîne dans le groupe joué même pendant la consultation d’un autre groupe', () => {
    const page = render(<MusicScreen />);
    fireEvent.click(page.getByRole('button', { name: 'Lire Premier thème' }));
    fireEvent.click(page.getByRole('button', { name: 'Zones' }));
    audio.ended = 'music:a'; page.rerender(<MusicScreen />);
    expect(audio.playExternal).toHaveBeenLastCalledWith('music:b', { ogg: fixture[1].ogg, mp3: fixture[1].mp3 }, { loop: false, crossfadeMs: 600 });
    audio.ended = null; page.rerender(<MusicScreen />);
    audio.ended = 'music:b'; page.rerender(<MusicScreen />);
    expect(audio.playExternal).toHaveBeenLastCalledWith('music:a', expect.anything(), expect.anything());
  });
  it('ferme vers l’accueil avec le son et restaure l’ambiance au démontage', () => {
    const page = render(<MusicScreen />);
    expect(audio.playSfx).toHaveBeenCalledWith('medals-open');
    fireEvent.click(page.getByRole('button', { name: 'Fermer' }));
    expect(navigate).toHaveBeenCalledWith('/');
    expect(audio.playSfx).toHaveBeenCalledWith('medals-close');
    page.unmount();
    expect(audio.resumeAmbient).toHaveBeenCalledWith({ crossfadeMs: 600 });
  });
  it('tolère les musiques absentes', () => {
    tracks = [];
    const page = render(<MusicScreen />);
    expect(page.getByText('Musiques non extraites')).toBeTruthy();
    expect(page.queryByRole('button', { name: /^Lire / })).toBeNull();
  });
  it('traduit les titres, contrôles et catégories en anglais', () => {
    const page = render(<I18nProvider initial="en"><MusicScreen /></I18nProvider>);
    expect(page.getByRole('button', { name: 'Play First theme' })).toBeTruthy();
    expect(page.getByRole('button', { name: 'Close' })).toBeTruthy();
    expect(page.getAllByRole('button', { name: 'Scroll down' })).toHaveLength(2);
  });
});
