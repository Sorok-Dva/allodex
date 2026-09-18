import { describe, it, expect } from 'vitest';
import { tex, video, cursor } from './assets';

describe('assets', () => {
  it('construit les URLs publiques', () => {
    expect(tex('Interface/Ingame/Medals/Textures/MedalFrame')).toBe('/game/textures/Interface/Ingame/Medals/Textures/MedalFrame.png');
    expect(video('intro')).toEqual({ webm: '/game/video/intro.webm', mp4: '/game/video/intro.mp4' });
    expect(cursor('Default')).toBe('/game/cursors/Default.cur');
  });
});
