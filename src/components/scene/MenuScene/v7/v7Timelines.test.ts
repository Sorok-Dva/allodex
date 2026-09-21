import { describe, expect, it } from 'vitest';
import { cannonPhase, destructionPhase, impactEnvelope, INTRO_HITS } from './v7Timelines';
describe('chronologie V7', () => {
  it('fait voyager chaque tir pendant six secondes avant son impact', () => {
    expect(cannonPhase(2.4, 2.5, 14).flight).toBe(-1);
    expect(cannonPhase(2.5, 2.5, 14).flight).toBe(0);
    expect(cannonPhase(5.5, 2.5, 14).flight).toBe(.5);
    expect(cannonPhase(8.49, 2.5, 14).impact).toBe(-1);
    expect(cannonPhase(8.5, 2.5, 14)).toEqual({ age: 6, flight: -1, impact: 0 });
    expect(cannonPhase(10.91, 2.5, 14).impact).toBe(-1);
  });
  it('enchaîne tir, feu, chute puis disparition séparément pour chaque navire', () => {
    const hits = [3, 11, 19];
    hits.forEach(hit => {
      expect(destructionPhase(0, hit).burning).toBe(false);
      expect(destructionPhase(hit - .5, hit).incoming).toBe(true);
      expect(destructionPhase(hit + .2, hit)).toMatchObject({ burning: true, fall: 0 });
      expect(destructionPhase(hit + 3, hit).fall).toBeGreaterThan(0);
      expect(destructionPhase(hit + 6, hit).visible).toBe(false);
      expect(destructionPhase(100, hit).visible).toBe(false);
    });
    expect(hits.map(hit => destructionPhase(9, hit).visible)).toEqual([false, true, true]);
    expect(hits.map(hit => destructionPhase(17, hit).visible)).toEqual([false, false, true]);
  });
  it('attend le choc concentré puis rétracte légèrement les anneaux avant le fondu', () => {
    expect(impactEnvelope(.2).opacity).toBe(0);
    expect(impactEnvelope(.665).shape).toBeCloseTo(.5);
    expect(impactEnvelope(1.225).shape).toBeCloseTo(.91);
    expect(impactEnvelope(1.225).returning).toBe(true);
    expect(impactEnvelope(1.05).shape).toBeCloseTo(1);
    expect(impactEnvelope(1.4).opacity).toBe(0);
  });
  it('suit l’ordre observé 03, 01, 02 sans attendre la fin de la fumée précédente', () => {
    expect(INTRO_HITS[3]).toBeLessThan(INTRO_HITS[1]);
    expect(INTRO_HITS[1]).toBeLessThan(INTRO_HITS[2]);
    expect(INTRO_HITS[1] - INTRO_HITS[3]).toBeLessThan(5.9);
  });
});
