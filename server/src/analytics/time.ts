/** Découpage du temps à l'heure de Paris (les décalages y sont des heures pleines). */

export const TIME_ZONE = 'Europe/Paris';
export const HOUR = 3_600_000;
export const DAY = 24 * HOUR;

const dayFormat = new Intl.DateTimeFormat('en-CA', { timeZone: TIME_ZONE, year: 'numeric', month: '2-digit', day: '2-digit' });
const hourFormat = new Intl.DateTimeFormat('en-GB', { timeZone: TIME_ZONE, hour: '2-digit', hourCycle: 'h23' });

/** `AAAA-MM-JJ` du jour parisien contenant `ts`. */
export const dayKey = (ts: number) => dayFormat.format(ts);

export const hourStart = (ts: number) => Math.floor(ts / HOUR) * HOUR;

/** Minuit (heure de Paris) du jour contenant `ts`. */
export function dayStart(ts: number): number {
  const hour = Number(hourFormat.format(ts));
  let start = hourStart(ts) - hour * HOUR;
  // Jour de changement d'heure : l'heure locale ne correspond pas au nombre d'heures écoulées.
  while (dayKey(start - 1) === dayKey(ts)) start -= HOUR;
  while (dayKey(start) !== dayKey(ts)) start += HOUR;
  return start;
}

/** Débuts des jours parisiens de `from` (inclus) à `to` (exclu). */
export function daysBetween(from: number, to: number): { key: string; t: number }[] {
  const out: { key: string; t: number }[] = [];
  for (let t = dayStart(from); t < to; t = dayStart(t + 26 * HOUR)) out.push({ key: dayKey(t), t });
  return out;
}
