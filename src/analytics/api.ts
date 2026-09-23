/**
 * Contrat entre le backend d'audience (`server/`) et le tableau de bord (`/stats`).
 *
 * Mesure sans cookie : le visiteur est un condensat (sel du jour + IP + navigateur) que le
 * serveur ne conserve pas au-delà de la journée ; la session est un identifiant aléatoire par
 * onglet (`sessionStorage`). Les chemins sont normalisés, sans requête (`/talents`, pas
 * `/talents?b=…`), sauf les entrées du Lorebook qui gardent leur chemin complet.
 */

export const RANGES = ['24h', '7d', '30d', '90d', '12m'] as const;
export type Range = (typeof RANGES)[number];

/** Une ligne de classement : `key` = chemin, domaine, navigateur… selon la liste. */
export type Count = { key: string; visitors: number; views: number };

export type Totals = {
  visitors: number;
  views: number;
  sessions: number;
  /** Durée moyenne passée sur une page vue, en millisecondes. */
  avgDurationMs: number;
  /** Part des sessions à une seule page vue, entre 0 et 1. */
  bounceRate: number;
  viewsPerSession: number;
};

export type StatsResponse = {
  range: Range;
  /** Filtre de chemin appliqué (`?path=`) : la page et ses sous-pages, l'accueil seul pour `/` ; ou null. */
  path: string | null;
  /** Bornes de la période, en millisecondes depuis l'époque. */
  from: number;
  to: number;
  bucket: 'hour' | 'day';
  totals: Totals;
  /** Même durée juste avant `from`, pour les évolutions. */
  previous: Totals;
  /** Un point par tranche (heure ou jour, fuseau Europe/Paris), tranches vides comprises. */
  series: { t: number; visitors: number; views: number }[];
  /** Pages les plus vues. */
  pages: (Count & { avgDurationMs: number })[];
  /** Rubriques : premier segment du chemin (`/`, `/lorebook`, `/talents`…). */
  sections: Count[];
  /** Pages d'arrivée (première page de chaque session). */
  entries: Count[];
  /** Domaine d'origine, `(direct)` sans référent. */
  referrers: Count[];
  devices: Count[];   // desktop | mobile | tablet
  browsers: Count[];
  os: Count[];
  /** Langue de l'interface au moment de la vue (`fr`, `en`). */
  langs: Count[];
};

/** Instantané du direct, poussé toutes les deux secondes par `GET /api/admin/live` (SSE). */
export type LiveSnapshot = {
  t: number;
  total: number;
  pages: { path: string; visitors: number }[];
};

/**
 * Points d'entrée (tous sous `/api`) :
 *   POST /api/collect              événements du traceur (public, `navigator.sendBeacon`)
 *   POST /api/admin/login          { password } → 204 + cookie de session, 401 sinon
 *   POST /api/admin/logout         204
 *   GET  /api/admin/me             204 si connecté, 401 sinon
 *   GET  /api/admin/stats?range=7d[&path=/talents]  → StatsResponse
 *   GET  /api/admin/live           text/event-stream, `data: LiveSnapshot`
 *   POST /api/talents/events       événement du calculateur de talents (public, `TalentEvent`)
 *   GET  /api/admin/talents?range=7d  → TalentStatsResponse
 */
export type CollectEvent = {
  /** `view` : nouvelle page ; `ping` : toujours là (toutes les 20 s) ; `leave` : fin de la vue. */
  type: 'view' | 'ping' | 'leave';
  session: string;
  /** Identifiant de la vue en cours, choisi par le client (reprise par `ping` et `leave`). */
  view: string;
  path: string;
  referrer?: string;
  lang?: string;
  /** Largeur d'écran, pour classer tablette / mobile quand l'agent utilisateur ne suffit pas. */
  width?: number;
  /** `ping` et `leave` : temps de visibilité cumulé de la vue, en millisecondes. */
  duration?: number;
};

/* --- calculateur de talents ------------------------------------------------------------------- */

export const TALENT_EVENT_KINDS = ['generate', 'share', 'view'] as const;
export type TalentEventKind = (typeof TALENT_EVENT_KINDS)[number];

/**
 * Événement d'un build (`POST /api/talents/events`, `sendBeacon`) : `generate`, build composé
 * dans le calculateur (envoyé quand l'édition se pose) ; `share`, lien copié ; `view`, build
 * ouvert depuis un lien. Le build est celui de l'URL : version `v`, classe `c`, codes `b` et
 * `b2` (au moins un). Le serveur le vérifie contre les données des talents avant de l'écrire.
 */
export type TalentEvent = {
  kind: TalentEventKind;
  v: string;
  c: string;
  b?: string | null;
  b2?: string | null;
  lang?: string;
};

/**
 * `builds` : builds distincts composés (au moins une génération) ; `generations`, `shares`,
 * `views` : un par visiteur, par jour et par build.
 */
export type TalentCounts = { builds: number; generations: number; shares: number; views: number };
type TalentActivity = Omit<TalentCounts, 'builds'>;

export type TalentBuildRow = {
  /** Condensat du contenu : identifiant stable du build. */
  id: string;
  version: string;
  cls: string;
  b: string | null;
  b2: string | null;
  /** Auteur (« build de X ») : réservé, toujours null tant que les joueurs n'existent pas. */
  playerId: number | null;
  firstTs: number;
  /** Sur la période demandée. */
  period: TalentActivity;
  /** Depuis le début. */
  total: TalentActivity;
};

export type TalentStatsResponse = {
  range: Range;
  from: number;
  to: number;
  totals: TalentCounts;
  /** Depuis le début de la mesure. */
  allTime: TalentCounts;
  /** Par version et classe, sur la période. */
  classes: (TalentCounts & { version: string; cls: string })[];
  /** Builds les plus vus sur la période (puis partagés, composés). */
  top: TalentBuildRow[];
};
