import { describe, it, expect } from 'vitest';
import { tex, video, cursor, sprite, audioSrc, audioMeta, archiveEntries, archiveFile } from './assets';

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
  });
});
