import { describe, expect, it } from 'vitest';
import { clipRate, footOf, moveClip, moveSpeed, seedTimes, stateShown, stepTimes, walkPose, WALK_RADIUS, WALK_SPEED } from './walk';

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

  it('marche (`walk`) dès que le gabarit en a une, sinon court', () => {
    expect(moveClip({ walk: 1.2, run: 0.8 })).toBe('walk');
    expect(moveClip({ walk: 1.2 })).toBe('walk');
    expect(moveClip({ run: 0.8 })).toBe('run');
    expect(moveClip(undefined)).toBeNull();
  });

  it('avance à la vitesse de marche du gabarit, ou de course pour `run`', () => {
    const kania = { speed: 2.1, runSpeed: 3.5 };
    expect(moveSpeed(kania, 'walk')).toBe(2.1);
    expect(moveSpeed(kania, 'run')).toBe(3.5);
    expect(moveSpeed(null, 'walk')).toBe(WALK_SPEED);
  });

  it('accorde la cadence du clip à l’avancée (pied posé sans glissement)', () => {
    expect(clipRate({ speed: 2.1, pace: { walk: 1.927 } }, 'walk')).toBeCloseTo(1.0898, 3);
    expect(clipRate({ speed: 2.1 }, 'walk')).toBe(1);
    expect(clipRate({ speed: 9, pace: { walk: 1 } }, 'walk')).toBe(2);
  });

  it('pose les empreintes aux pas du clip, pied par pied', () => {
    expect(footOf(['PremiumTrace_Step_01L'], [0.5, 0.5, 0])).toBe('L');
    expect(footOf(['PremiumTrace_Step_01R'], [-0.5, -0.5, 0])).toBe('R');
    expect(footOf(['Trace'], [-0.5, 0, 0])).toBe('R');
    // Cycle d'une seconde, pied gauche posé à 0,2 s : 0,2 puis 1,2.
    expect(stepTimes(0, 1.5, 1, [0.2])).toEqual([0.2, 1.2]);
    expect(stepTimes(0.2, 1.2, 1, [0.2, 0.7])).toEqual([0.7, 1.2]);
    expect(stepTimes(1, 1, 1, [0.2])).toEqual([]);
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
