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
