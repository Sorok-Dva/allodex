import { describe, it, expect } from 'vitest';
import { formatGameDate, formatGameDateTime, formatReleaseMonth } from './dates';

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

describe('formatReleaseMonth', () => {
  it('rend le mois en français, l\'année seule telle quelle, et laisse passer le reste', () => {
    expect(formatReleaseMonth('2013-03')).toBe('mars 2013');
    expect(formatReleaseMonth('2013-03', 'en')).toBe('March 2013');
    expect(formatReleaseMonth('2010')).toBe('2010');
    expect(formatReleaseMonth('2013-13')).toBe('2013-13');
    expect(formatReleaseMonth('printemps 2010')).toBe('printemps 2010');
  });
});
