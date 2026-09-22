import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, waitFor, within } from '@testing-library/react';
import { I18nProvider } from '@/lib/i18n';
import type { Cinematic, CinematicsIndex } from '@/lib/cinematics';
import { CinematicsScreen } from './CinematicsScreen';

const audio = { playSfx: vi.fn(), pauseMusic: vi.fn(), resumeAmbient: vi.fn() };
vi.mock('@/lib/audio/useGameAudio', () => ({ useGameAudio: () => audio }));
let search = '';
vi.mock('@/lib/router', () => ({
  navigate: vi.fn(),
  useRoute: () => ({ path: '/cinematics', query: new URLSearchParams(search) }),
}));
import { navigate } from '@/lib/router';

function cine(id: string, over: Partial<Cinematic> = {}): Cinematic {
  return {
    id, title: { fr: `Titre ${id}`, en: `Title ${id}` }, faction: 'common', order: 100, arc: 'invasion',
    version: '7.0', duration: 30,
    files: { webm: `${id}/video.webm`, mp4: `${id}/video.mp4`, poster: `${id}/poster.jpg` },
    tracks: [{ lang: 'fr', label: 'Français', src: `${id}/fr.vtt`, lines: 2 }, { lang: 'ru', label: 'Русский', src: `${id}/ru.vtt`, lines: 2 }],
    audio: { language: 'ru' }, subtitles: { status: 'official', lines: 2, timing: 'measured' },
    source: { client: '17.0', pak: 'data/Packs/Video.pak', entry: `Video/${id}.ogv`, event: `x/${id}` },
    chronology: 'test', ...over,
  };
}

const INDEX: CinematicsIndex = {
  arcs: {
    prologue: { title: { fr: 'Prologue de faction', en: 'Faction prologue' }, version: '16.0' },
    invasion: { title: { fr: 'L’Invasion', en: 'The Invasion' }, version: '7.0' },
  },
  cinematics: [
    cine('league-intro', { faction: 'league', arc: 'prologue', order: 100, version: '16.0' }),
    cine('empire-intro', { faction: 'empire', arc: 'prologue', order: 100, version: '16.0' }),
    cine('plague', { order: 200, tracks: [], audio: { language: null }, subtitles: { status: 'none', lines: 0, timing: null } }),
    cine('bridge', { order: 210 }),
  ],
};

const loader = () => Promise.resolve(INDEX);
const renderScreen = () => render(<I18nProvider storage={null} initial="fr"><CinematicsScreen loader={loader} /></I18nProvider>);

beforeAll(() => {
  // jsdom ne joue pas de média : lecture et pause deviennent des espions.
  Object.defineProperty(HTMLMediaElement.prototype, 'play', { configurable: true, value: vi.fn(() => Promise.resolve()) });
  Object.defineProperty(HTMLMediaElement.prototype, 'pause', { configurable: true, value: vi.fn() });
});
beforeEach(() => { vi.clearAllMocks(); search = ''; });
afterEach(cleanup);

describe('CinematicsScreen — choix de la faction', () => {
  it('présente les deux films avec leur nombre de cinématiques et leur durée', async () => {
    const page = renderScreen();
    const league = await page.findByTestId('faction-league');
    expect(league.textContent).toContain('Ligue');
    expect(league.textContent).toContain('3 cinématiques · 1:30');
    expect(league.textContent).toContain('L’Invasion');
    fireEvent.click(league);
    expect(navigate).toHaveBeenCalledWith('/cinematics?faction=league');
  });
});

describe('CinematicsScreen — film', () => {
  it('enchaîne les chapitres en préchargeant le suivant dans le second lecteur', async () => {
    search = 'faction=empire';
    const page = renderScreen();
    const v0 = await page.findByTestId('film-video-0') as HTMLVideoElement;
    const v1 = page.getByTestId('film-video-1') as HTMLVideoElement;
    expect(v0.dataset.chapter).toBe('empire-intro');
    expect(v1.dataset.chapter).toBe('plague');              // préchargé, caché
    expect(v1.getAttribute('aria-hidden')).toBe('true');
    expect(audio.pauseMusic).toHaveBeenCalled();
    // pistes du chapitre, français (langue de l'interface) par défaut
    const tracks = v0.querySelectorAll('track');
    expect([...tracks].map(t => t.getAttribute('srclang'))).toEqual(['fr', 'ru']);
    expect((tracks[0] as HTMLTrackElement).default).toBe(true);

    act(() => { fireEvent.ended(v0); });
    // le lecteur qui attendait devient visible, l'autre charge le chapitre d'après
    await waitFor(() => expect(v1.getAttribute('aria-hidden')).toBe('false'));
    expect(v1.dataset.chapter).toBe('plague');
    expect(v0.dataset.chapter).toBe('bridge');
    expect(page.getByTestId('chapter-plague').getAttribute('aria-current')).toBe('true');
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
  });

  it('saute à un chapitre choisi dans la liste et termine sur l’écran de fin', async () => {
    search = 'faction=league';
    const page = renderScreen();
    await page.findByTestId('film-video-0');
    fireEvent.click(page.getByTestId('chapter-bridge'));
    const visible = () => page.getAllByTestId(/film-video-/).find(v => v.getAttribute('aria-hidden') === 'false') as HTMLVideoElement;
    await waitFor(() => expect(visible().dataset.chapter).toBe('bridge'));
    expect(page.getByTestId('chapter-bridge').getAttribute('aria-current')).toBe('true');
    act(() => { fireEvent.ended(visible()); });
    const end = await page.findByRole('dialog', { name: 'Fin' });
    fireEvent.click(within(end).getByRole('button', { name: 'Changer de faction' }));
    expect(navigate).toHaveBeenCalledWith('/cinematics');
  });

  it('change la langue des sous-titres ou les coupe', async () => {
    search = 'faction=league';
    const page = renderScreen();
    const v0 = await page.findByTestId('film-video-0') as HTMLVideoElement;
    fireEvent.click(page.getByRole('button', { name: 'RU' }));
    const ru = [...v0.querySelectorAll('track')].find(t => t.getAttribute('srclang') === 'ru') as HTMLTrackElement;
    expect(ru.default).toBe(true);
    fireEvent.click(page.getByRole('button', { name: 'Aucun' }));
    expect([...v0.querySelectorAll('track')].some(t => (t as HTMLTrackElement).default)).toBe(false);
  });
});
