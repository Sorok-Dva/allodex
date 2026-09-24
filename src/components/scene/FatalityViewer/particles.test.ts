import { describe, expect, it } from 'vitest';
import { continuousFrames, onceFrame, oncePeriod, PARTICLE_FPS } from './particles';

// Système du décalque de l'aura de Marquis (`Aura_LoginEventFun_2024_Cat`) : 601 images, boucle à 301.
const MARQUIS = { speed: 1, loop: true, endFrame: 601, loopFrame: 301 };

describe('boucle continue des particules', () => {
  it('reprend les émetteurs bouclés au point de boucle, avec le tour précédent', () => {
    expect(continuousFrames(100 / PARTICLE_FPS, MARQUIS)).toEqual([100]);
    const [f, previous] = continuousFrames(700 / PARTICLE_FPS, MARQUIS);
    expect(f).toBeCloseTo(400);
    expect(previous).toBeCloseTo(700);
  });

  it('rejoue un émetteur non bouclé sur sa période : le décalque ne s’éteint pas', () => {
    expect(oncePeriod(MARQUIS)).toBe(301);
    expect(oncePeriod({ endFrame: 300, loopFrame: 300 })).toBe(300);
    // Le décalque vit de 0 à 300 : à 30 s (900 images) et à 120 s (3600 images), il est dans sa vie.
    for (const t of [0, 30, 120]) {
      const frame = onceFrame(t, MARQUIS);
      expect(frame).toBeGreaterThanOrEqual(0);
      expect(frame).toBeLessThanOrEqual(300);
    }
  });

  it('laisse le temps tel quel pour un système qui ne boucle pas', () => {
    expect(onceFrame(30, { ...MARQUIS, loop: false })).toBe(900);
  });
});
