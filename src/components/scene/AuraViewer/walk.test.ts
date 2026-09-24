import { describe, expect, it } from 'vitest';
import { moveClip, seedTimes, stateShown, walkPose, WALK_RADIUS } from './walk';

describe('boucle de marche', () => {
  it('reste sur le cercle et regarde dans le sens de la marche', () => {
    const p = walkPose(0);
    expect(p.x).toBeCloseTo(WALK_RADIUS);
    expect(p.y).toBeCloseTo(0);
    // Tangente en (R, 0) : +Y ; le modèle regarde −Y, donc un demi-tour.
    expect(Math.abs(p.rz)).toBeCloseTo(Math.PI);
    const q = walkPose((Math.PI / 2) * WALK_RADIUS);
    expect(q.x).toBeCloseTo(0);
    expect(q.y).toBeCloseTo(WALK_RADIUS);
  });

  it('court si le gabarit a `run`, sinon marche', () => {
    expect(moveClip({ walk: 1.2, run: 0.8 })).toBe('run');
    expect(moveClip({ walk: 1.2 })).toBe('walk');
    expect(moveClip(undefined)).toBeNull();
  });

  it('montre les empreintes pendant leurs animations seulement', () => {
    expect(stateShown(['run'], 'run')).toBe(true);
    expect(stateShown(['run'], null)).toBe(false);
    expect(stateShown(null, null)).toBe(true);
  });

  it('sème deux fois par seconde, le pied droit décalé de 0,25 s', () => {
    expect(seedTimes(0, 1.1, 0, 0, 2)).toEqual([0.5, 1]);
    expect(seedTimes(0, 1.1, 0, 0.25, 2)).toEqual([0.25, 0.75]);
    expect(seedTimes(1, 1, 0, 0, 2)).toEqual([]);
  });
});
