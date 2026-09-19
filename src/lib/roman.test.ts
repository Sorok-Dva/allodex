import { describe, it, expect } from 'vitest';
import { toRoman } from './roman';

describe('toRoman', () => {
  it('convertit les entiers 1..20 en chiffres romains', () => {
    expect(toRoman(1)).toBe('I');
    expect(toRoman(4)).toBe('IV');
    expect(toRoman(6)).toBe('VI');
    expect(toRoman(9)).toBe('IX');
    expect(toRoman(14)).toBe('XIV');
    expect(toRoman(20)).toBe('XX');
  });

  it('renvoie String(n) pour 0 ou plus de 20', () => {
    expect(toRoman(0)).toBe('0');
    expect(toRoman(21)).toBe('21');
    expect(toRoman(100)).toBe('100');
  });
});
