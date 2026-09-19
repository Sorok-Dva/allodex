import s from './GameFilters.module.css';

/**
 * Filtres de couleur repris du jeu. Les captures ne fournissent qu'un seul sprite par
 * élément ; les variantes d'état (pilule dépliée, flèche d'ascenseur inactive) sont
 * obtenues par une transformation affine du sprite, ajustée aux moindres carrés entre
 * les deux états relevés dans `refs/` (erreur moyenne ≈ 3 niveaux sur 255).
 *
 * - `game-pill-open` : pilule repliée (liseré or) → pilule dépliée (liseré vert),
 *   mesuré entre « Batailles » (y 378) et « Astral » (y 408) de `refs/astral.png`.
 * - `game-navframe` : la texture `FrameNavigation` est elle aussi plus sombre que le
 *   rendu du jeu, d'un décalage constant (+15, +14, +9) mesuré sur les parties du
 *   cadre qu'aucun sprite ne recouvre (erreur moyenne 15,2 → 9,9).
 * - `game-parchment` : la texture `CategoryContent` du client est plus sombre et plus
 *   jaune que le parchemin affiché par le jeu ; l'écart est un décalage constant
 *   (+8, +12, +18) qui divise l'erreur moyenne par deux (13,8 → 7,8).
 * - `game-arrow-off` : flèche d'ascenseur active (dorée) → inactive (grisée),
 *   mesuré entre `refs/navscroll.png` et `refs/astral.png` (flèche haut, y 307).
 */
export function GameFilters() {
  return (
    <svg className={s.defs} aria-hidden="true" focusable="false">
      <defs>
        <filter id="game-pill-open" colorInterpolationFilters="sRGB" x="0%" y="0%" width="100%" height="100%">
          <feColorMatrix
            type="matrix"
            values="0.3864 -0.2177 0.4408 0 0.1048
                    -0.0996 0.6037 -0.0142 0 0.1108
                    -0.0854 0.3505 0.0898 0 0.0607
                    0 0 0 1 0"
          />
        </filter>
        <filter id="game-navframe" colorInterpolationFilters="sRGB" x="0%" y="0%" width="100%" height="100%">
          <feColorMatrix
            type="matrix"
            values="1 0 0 0 0.0577
                    0 1 0 0 0.0541
                    0 0 1 0 0.0354
                    0 0 0 1 0"
          />
        </filter>
        <filter id="game-parchment" colorInterpolationFilters="sRGB" x="0%" y="0%" width="100%" height="100%">
          <feColorMatrix
            type="matrix"
            values="1 0 0 0 0.0307
                    0 1 0 0 0.0452
                    0 0 1 0 0.0709
                    0 0 0 1 0"
          />
        </filter>
        <filter id="game-arrow-off" colorInterpolationFilters="sRGB" x="0%" y="0%" width="100%" height="100%">
          <feColorMatrix
            type="matrix"
            values="0.2899 0.0909 0.4844 0 0.0510
                    0.2447 0.1927 0.5433 0 0.0586
                    0.2157 0.0936 0.3210 0 0.0315
                    0 0 0 1 0"
          />
        </filter>
      </defs>
    </svg>
  );
}
