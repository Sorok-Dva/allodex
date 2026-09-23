import { describe, expect, it } from 'vitest';
import { actorClipAt, argb, lineEnd, sampleKeys, subtitleAt, voiceAt, type EngineLine } from './timeline';

const line = (n: number, start: number, duration: number, speaker: string, voice: number | null, animations: string[] = []): EngineLine => ({
  n, start, duration, speaker, animations, text: { en: `line ${n}`, ru: `реплика ${n}` },
  voice: voice === null ? null : { event: `e${n}`, ogg: `voice/${n}.ogg`, mp3: `voice/${n}.mp3`, duration: voice },
});

describe('engine cutscene timeline', () => {
  it('interpolates camera keys linearly and holds the last one', () => {
    const keys = [{ t: 0, p: [0, 0, 0] as [number, number, number] }, { t: 10, p: [10, 20, 30] as [number, number, number] }];
    expect(sampleKeys(keys, 5)).toEqual([5, 10, 15]);
    expect(sampleKeys(keys, -1)).toEqual([0, 0, 0]);
    expect(sampleKeys(keys, 99)).toEqual([10, 20, 30]);
  });

  it('shows a subtitle until its client duration or the next line', () => {
    const lines = [line(1, 0, 5, 'a', 2), line(2, 3, 7, 'b', 4)];
    const scene = { lines, duration: 20 };
    expect(lineEnd(lines, 0, 20)).toBe(3);
    expect(subtitleAt(scene, 1, 'en')).toBe('line 1');
    expect(subtitleAt(scene, 4, 'ru')).toBe('реплика 2');
    expect(subtitleAt(scene, 11, 'en')).toBeNull();
    expect(subtitleAt(scene, 4, 'fr')).toBeNull();
    expect(subtitleAt(scene, 4, null)).toBeNull();
  });

  it('finds the voice playing at a given time with its offset', () => {
    const lines = [line(1, 1, 5, 'a', 2), line(2, 10, 7, 'b', null)];
    expect(voiceAt(lines, 2.5)).toEqual({ index: 0, offset: 1.5 });
    expect(voiceAt(lines, 3.5)).toBeNull();
    expect(voiceAt(lines, 11)).toBeNull();
  });

  it('plays the talk clip only on lines whose client data asks for an animation', () => {
    const actor = { id: 'a', idle: 'Idle', talk: 'EmoteSpeech' };
    const lines = [line(1, 2, 5, 'a', 3, ['emoteSpeech']), line(2, 8, 5, 'a', 3)];
    expect(actorClipAt(actor, lines, 3)).toEqual({ clip: 'EmoteSpeech', time: 1 });
    expect(actorClipAt(actor, lines, 9)).toEqual({ clip: 'Idle', time: 9 });
    expect(actorClipAt({ ...actor, id: 'b' }, lines, 3).clip).toBe('Idle');
  });

  it('decodes client ARGB colours', () => {
    expect(argb(0xff804000)).toEqual([128 / 255, 64 / 255, 0]);
    expect(argb(0xff808080, 4)).toEqual([1, 1, 1]);
  });
});

describe('engine cutscene paths, fades and sounds', () => {
  it('interpolates actor paths and reports movement', async () => {
    const { pathAt } = await import('./timeline');
    const path = [{ t: 0, p: [0, 0, 0] as [number, number, number], yaw: 0 }, { t: 10, p: [0, 0, 0] as [number, number, number], yaw: 0 },
      { t: 12, p: [4, 0, 2] as [number, number, number], yaw: 1 }];
    expect(pathAt(path, 5)).toEqual({ p: [0, 0, 0], yaw: 0, moving: false });
    expect(pathAt(path, 11)).toEqual({ p: [2, 0, 1], yaw: 0.5, moving: true });
    expect(pathAt(path, 20).p).toEqual([4, 0, 2]);
  });

  it('fades in from black and out to black', async () => {
    const { veilAt } = await import('./timeline');
    const post = [{ t: 0, kind: 'fadeIn' as const, duration: 2 }, { t: 10, kind: 'fadeOut' as const, duration: 1 }];
    expect(veilAt(post, 0)).toBe(1);
    expect(veilAt(post, 1)).toBe(0.5);
    expect(veilAt(post, 5)).toBe(0);
    expect(veilAt(post, 10.5)).toBe(0.5);
    expect(veilAt(post, 12)).toBe(1);
  });

  it('attenuates point sounds linearly with distance', async () => {
    const { falloff } = await import('./timeline');
    expect(falloff(0)).toBe(1);
    expect(falloff(30, 60)).toBe(0.5);
    expect(falloff(90, 60)).toBe(0);
  });
});
