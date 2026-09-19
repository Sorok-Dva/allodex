export function formatGameDate(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split('-');
  return `${d}.${m}.${y}`;
}

/** 'HH:MM JJ.MM.AAAA' si une heure est présente dans l'ISO, sinon 'JJ.MM.AAAA'. */
export function formatGameDateTime(iso: string): string {
  const datePart = formatGameDate(iso);
  const time = iso.slice(11, 16);
  return time.length === 5 ? `${time} ${datePart}` : datePart;
}
