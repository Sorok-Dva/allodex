import { describe, it, expect } from 'vitest';
import { formatGameDate, formatGameDateTime } from './dates';

describe('formatGameDate', () => {
  it('formate comme le jeu : JJ.MM.AAAA', () => {
    expect(formatGameDate('2017-09-13')).toBe('13.09.2017');
    expect(formatGameDate('2020-01-29T10:00:00Z')).toBe('29.01.2020');
  });
});

describe('formatGameDateTime', () => {
  it("inclut l'heure si présente, sinon seulement la date", () => {
    expect(formatGameDateTime('2026-08-29T20:54')).toBe('20:54 29.08.2026');
    expect(formatGameDateTime('2026-05-25')).toBe('25.05.2026');
  });
});
