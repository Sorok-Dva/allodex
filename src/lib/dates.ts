// Aucune conversion de fuseau horaire : la chaîne ISO est affichée littéralement (heure du jeu telle que capturée).
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

const MONTHS_FR = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'];

/** « AAAA-MM » → « mars 2013 » ; « AAAA » seul est rendu tel quel ; autre chose est renvoyé intact. */
export function formatReleaseMonth(release: string): string {
  const match = /^(\d{4})(?:-(\d{2}))?$/.exec(release.trim());
  if (!match) return release;
  const [, year, month] = match;
  if (!month) return year;
  const name = MONTHS_FR[Number(month) - 1];
  return name ? `${name} ${year}` : release;
}
