import { describe, it, expect } from 'vitest';
import { initialPhase, INTRO_SEEN_KEY } from './useIntroState';

const mem = (init: Record<string, string> = {}) => {
  const m = new Map(Object.entries(init));
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) } as Storage;
};

describe('initialPhase', () => {
  it('joue l’intro à la première visite', () => expect(initialPhase(mem())).toBe('intro'));
  it('saute l’intro si déjà vue', () => expect(initialPhase(mem({ [INTRO_SEEN_KEY]: '1' }))).toBe('menu'));
  it('force le menu quand forceMenu est vrai, même à la première visite', () => expect(initialPhase(mem(), true)).toBe('menu'));
});
