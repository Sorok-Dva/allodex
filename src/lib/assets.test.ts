import { describe, it, expect, vi } from 'vitest';
import { tex, video, cursor, sprite, audioSrc, audioMeta, archiveEntries, archiveFile, latestArchiveEntry } from './assets';
import { loadManifest, musicTracks } from './assets';

describe('assets', () => {
  it('construit les URLs publiques', () => {
    expect(tex('Interface/Ingame/Medals/Textures/MedalFrame')).toBe('/game/textures/Interface/Ingame/Medals/Textures/MedalFrame.png');
    expect(video('intro')).toEqual({ webm: '/game/video/intro.webm', mp4: '/game/video/intro.mp4' });
    expect(cursor('Default')).toBe('/game/cursors/Default.cur');
  });

  it("construit l'URL d'un sprite découpé", () => {
    expect(sprite('pill-mid')).toBe('/game/sprites/pill-mid.png');
  });

  it("construit les URLs ogg/mp3 d'une piste audio, ogg d'abord", () => {
    expect(audioSrc('menu')).toEqual({ ogg: '/game/audio/menu.ogg', mp3: '/game/audio/menu.mp3' });
  });

  it("renvoie undefined pour les métadonnées audio tant que l'index n'est pas chargé", () => {
    expect(audioMeta('menu')).toBeUndefined();
  });

  it("construit l'URL d'un fichier de version archivée", () => {
    expect(archiveFile('8.0', 'background.png')).toBe('/game/archive/8.0/background.png');
    expect(archiveFile('16.0', 'theme.ogg')).toBe('/game/archive/16.0/theme.ogg');
  });

  it("renvoie une archive vide tant que l'index n'est pas chargé", () => {
    expect(archiveEntries()).toEqual([]);
    expect(latestArchiveEntry()).toBeUndefined();
  });

  it('résout automatiquement les vidéos et le thème de la dernière version du jeu', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => ({
      ok: true, status: 200,
      json: async () => {
        if (url.endsWith('/archive.json')) {
          return [
            { version: '16.0', label: '16.0', media: 'video', video: { webm: 'menu.webm', mp4: 'menu.mp4' }, intro: { webm: 'intro.webm', mp4: 'intro.mp4' }, theme: { name: 'theme16', duration: 160, ogg: 'theme.ogg', mp3: 'theme.mp3' } },
            { version: '17.0', label: '17.0', media: 'video', video: { webm: 'menu.webm', mp4: 'menu.mp4' }, intro: { webm: 'intro.webm', mp4: 'intro.mp4' }, theme: { name: 'MainMenu_TheBloodOfKings', duration: 186.4, ogg: 'theme.ogg', mp3: 'theme.mp3' } },
          ];
        }
        if (url.endsWith('/manifest.json')) return { textures: {} };
        return {};
      },
    })));
    try {
      await loadManifest();
      expect(latestArchiveEntry()?.version).toBe('17.0');
      expect(video('intro')).toEqual({ webm: '/game/archive/17.0/intro.webm', mp4: '/game/archive/17.0/intro.mp4' });
      expect(video('mainmenu')).toEqual({ webm: '/game/archive/17.0/menu.webm', mp4: '/game/archive/17.0/menu.mp4' });
      expect(audioSrc('menu')).toEqual({ ogg: '/game/archive/17.0/theme.ogg', mp3: '/game/archive/17.0/theme.mp3' });
      expect(audioMeta('menu')).toEqual({ duration: 186.4, loop: true });
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('tolère un index musical absent', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => ({
      ok: !url.endsWith('/music.json'), status: 404,
      json: async () => url.endsWith('/manifest.json') ? { textures: {} } : {},
    })));
    try { await loadManifest(); expect(musicTracks()).toEqual([]); }
    finally { vi.unstubAllGlobals(); }
  });
});
