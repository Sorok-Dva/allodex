import { it, expect } from 'vitest';
import { formatGameDate } from './formatDate';
it('formate comme le jeu : JJ.MM.AAAA', () => {
  expect(formatGameDate('2017-09-13')).toBe('13.09.2017');
  expect(formatGameDate('2020-01-29T10:00:00Z')).toBe('29.01.2020');
});
