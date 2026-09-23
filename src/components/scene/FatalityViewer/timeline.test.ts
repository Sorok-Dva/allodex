import { describe, it, expect } from 'vitest';
import {
  objectClipTime, shakeOffsetAt, spawnOpacity, stepAt, timelineDuration, victimTintAt, timelineSounds, victimClipTime, victimOpacityAt, victimScaleAt,
  victimStepAt, type FatalityTimeline,
} from './timeline';
import { parseParticles, particleFrame, sampleChannel, maxAlive } from './particles';

const TL: FatalityTimeline = {
  end: 10,
  victim: [
    { t: 0, end: 8, anim: 'DeathFatalityMage', speed: 0.5, mode: 'LOOP' },
    { t: 6, end: 7, anim: 'SpellCastOmniCure', speed: 1, mode: 'CLAMP' },
  ],
  scale: [{ t: 0, scale: 1.3 }],
  alpha: [{ t: 5, value: 0, fadeMult: 1, priority: 1 }],
  spawns: [{ t: 1, vot: 'A', lifeTime: 3, scale: 1 }],
  attached: [],
};

describe('chronologie de la victime', () => {
  it('rend la main à la boucle quand l’animation jouée par-dessus est finie', () => {
    expect(victimStepAt(TL, 3)?.anim).toBe('DeathFatalityMage');
    expect(victimStepAt(TL, 6.5)?.anim).toBe('SpellCastOmniCure');
    expect(victimStepAt(TL, 7.5)?.anim).toBe('DeathFatalityMage');
    expect(victimStepAt(TL, 9)?.anim).toBe('SpellCastOmniCure');   // tout est fini : dernière commencée
  });

  it('applique la vitesse, boucle ou tient la dernière pose', () => {
    expect(victimClipTime(TL.victim[0], 3, 1)).toBeCloseTo(0.5, 5);   // 1,5 s de clip à ×0,5, modulo 1 s
    expect(victimClipTime({ ...TL.victim[1] }, 9, 0.5)).toBeCloseTo(0.5 - 1e-4, 5);
  });

  it('échelle et opacité suivent les actions du script puis le fondu final', () => {
    expect(victimScaleAt(TL, 0.1)).toBe(1.3);
    expect(victimOpacityAt(TL, 4, 0, 0)).toBe(1);
    expect(victimOpacityAt(TL, 5.5, 0, 0)).toBeCloseTo(0.5, 5);
    expect(victimOpacityAt(TL, 3, 2, 2)).toBeCloseTo(0.5, 5);
  });
});

describe('objets d’effet', () => {
  it('enveloppe d’opacité : entrée, vie, sortie', () => {
    expect(spawnOpacity(0.25, 3, 0.5, 1)).toBeCloseTo(0.5, 5);
    expect(spawnOpacity(2, 3, 0.5, 1)).toBe(1);
    expect(spawnOpacity(3.5, 3, 0.5, 1)).toBeCloseTo(0.5, 5);
    expect(spawnOpacity(4.5, 3, 0.5, 1)).toBe(0);
  });

  it('temps d’animation en boucle ou tenu', () => {
    expect(objectClipTime(5, 2, true)).toBeCloseTo(1, 5);
    expect(objectClipTime(5, 2, false)).toBeCloseTo(2 - 1e-4, 5);
  });

  it('durée totale et sons déclenchés avec leur objet (composants compris)', () => {
    const objects = { A: { fadeIn: 0, fadeOut: 1, scale: 1, duration: 2, loop: false, sfx: 'sfx/A', components: [{ vot: 'B', locator: '' }] },
      B: { fadeIn: 0, fadeOut: 0, scale: 1, duration: 1, loop: false, sfx: 'sfx/B' } };
    expect(timelineDuration(TL, objects, 9, 2)).toBe(11);
    expect(timelineSounds(TL, objects)).toEqual([{ t: 1, sfx: 'sfx/A' }, { t: 1, sfx: 'sfx/B' }]);
  });

  it('le script du tueur : ses animations, et les sons de ses effets et de ses rayons', () => {
    const objects = { C: { fadeIn: 0, fadeOut: 0, scale: 1, duration: 1, loop: false, sfx: 'sfx/C' },
      R: { fadeIn: 0, fadeOut: 0, scale: 1, duration: 1, loop: true, sfx: 'sfx/R' } };
    const caster = {
      anims: [{ t: 0, end: 2, anim: 'LevelUp', speed: 1.5, mode: 'DIE' }],
      attached: [{ t: 0, vot: 'C', locator: 'Slot_BodyFX', scale: 1, fadeIn: 0, fadeOut: 0, until: 9 }],
      channels: [{ t: 1.2, until: 3.5, vot: 'R', fadeIn: 0.2, fadeOut: 0.1, length: 10 }],
    };
    expect(stepAt(caster.anims, 1)?.anim).toBe('LevelUp');
    expect(stepAt(caster.anims, 5)?.anim).toBe('LevelUp');
    expect(timelineSounds({ ...TL, spawns: [], attached: [], caster }, objects)).toEqual([{ t: 0, sfx: 'sfx/C' }, { t: 1.2, sfx: 'sfx/R' }]);
  });
});

describe('particules', () => {
  /** Fichier d'un émetteur, une particule née à l'image 2, vivant 4 images, canaux à deux clés. */
  function file(): ArrayBuffer {
    const bytes: number[] = [];
    const u32 = (v: number) => { bytes.push(v & 255, (v >> 8) & 255, (v >> 16) & 255, (v >>> 24) & 255); };
    const f32 = (v: number) => { const b = new Uint8Array(new Float32Array([v]).buffer); bytes.push(...b); };
    u32(1); u32(8); u32(1);
    [0, 0, 0, 1, 1, 1, 0.5, 0.5, 0, 0].forEach(f32);         // pos min/pas, taille min/pas
    u32(8); u32(1);                                            // table juste après (40 + 8 = 48)
    // table : naissance 2, durée 4, données 8 octets plus loin, taille
    bytes.push(2, 0, 4, 0); u32(8); u32(0);
    const u16 = (v: number) => bytes.push(v & 255, v >> 8);
    bytes.push(2); [0, 0, 0, 4, 8, 12].forEach(u16);           // position : 2 clés
    bytes.push(1); [0, 0].forEach(u16);                        // taille : 1 clé
    bytes.push(1); u16(0);                                     // rotation
    bytes.push(2); bytes.push(255, 255, 255, 255, 255, 255, 255, 0);  // couleur : fondu d'alpha
    bytes.push(1, 0);                                          // image
    return new Uint8Array(bytes).buffer;
  }

  it('décode émetteurs, particules et canaux, puis interpole', () => {
    const parsed = parseParticles(file());
    const p = parsed.emitters[0].particles[0];
    expect([p.birth, p.span]).toEqual([2, 4]);
    const out = new Float32Array(4);
    expect(Array.from(sampleChannel(p.channels[0], 2, out).slice(0, 3))).toEqual([2, 4, 6]);
    expect(sampleChannel(p.channels[3], 1, out)[3]).toBeCloseTo(191.25, 3);
    expect(maxAlive(parsed.emitters[0].particles)).toBe(1);
  });

  it('boucle sur l’image de fin quand le système boucle', () => {
    expect(particleFrame(1, { speed: 1, loop: false, endFrame: 20 })).toBe(30);
    expect(particleFrame(1, { speed: 1, loop: true, endFrame: 20 })).toBe(10);
  });
});

describe('teintes et secousses', () => {
  const base: FatalityTimeline = { end: 10, victim: [], scale: [], alpha: [], spawns: [], attached: [] };
  it('la teinte la plus prioritaire est atteinte en timeOn depuis le blanc', () => {
    const tl = { ...base, tints: [
      { t: 0, color: 0xffffffff, blend: 'DEFAULT', priority: 0, timeOn: 0.3 },
      { t: 1, color: 0xff000000, blend: 'DEFAULT', priority: 1, timeOn: 10 },
    ] };
    expect(victimTintAt(tl, 0.5).mul).toEqual([1, 1, 1]);
    expect(victimTintAt(tl, 6).mul[0]).toBeCloseTo(0.5, 5);
    expect(victimTintAt(tl, 20).mul).toEqual([0, 0, 0]);
    const add = victimTintAt({ ...base, tints: [{ t: 0, color: 0xff55ffdd, blend: 'MUL', priority: 0, timeOn: 0 }] }, 1);
    expect(add.mul[1]).toBeCloseTo(1, 5);
    const glow = victimTintAt({ ...base, tints: [{ t: 0, color: 0xffff0000, blend: 'ADD', priority: 0, timeOn: 0 }] }, 1);
    expect(glow.add).toEqual([1, 0, 0]);
  });

  it('la secousse suit sa courbe, amortie par la distance', () => {
    const tl = { ...base, shakes: [{ t: 2, amplitude: 5, radius: [20, 50] as [number, number], curve: [0, 0, 0, 0.1, 0, 0, 0, 0, 0] }] };
    expect(shakeOffsetAt(tl, 1.9, 10)).toEqual([0, 0, 0]);
    expect(shakeOffsetAt(tl, 2 + 1 / 30, 10)[0]).toBeCloseTo(0.5, 5);
    expect(shakeOffsetAt(tl, 2 + 1 / 30, 35)[0]).toBeCloseTo(0.25, 5);
    expect(shakeOffsetAt(tl, 2 + 1 / 30, 60)[0]).toBe(0);
  });
});
