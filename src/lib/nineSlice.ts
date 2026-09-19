import type { CSSProperties } from 'react';
import { sprite, spriteSize } from './assets';

export type Slice = [top: number, right: number, bottom: number, left: number];

type Options = {
  /**
   * Ajoute le mot-clé `fill` aux tranches : l'intérieur du sprite est dessiné comme
   * fond. Les cadres dont le centre a été vidé (`clear_center` du manifeste) s'en
   * passent, les champs pleins (`dropdown-field`, `search-field`…) en ont besoin.
   */
  fill?: boolean;
  /**
   * URL de l'image, quand elle ne vient pas de `public/game/sprites` : les textures
   * brutes du client (barre de progression) n'ont pas d'entrée dans `sprites.json`,
   * seules leurs tranches sont connues à l'avance (`fallback`).
   */
  source?: string;
};

/**
 * Style d'un cadre 9 tranches (`border-image`) posé en style en ligne.
 *
 * Les tranches viennent de `sprites.json` (écrit par `tools/cut_sprites.py`), qui est
 * la seule source de vérité ; `fallback` sert tant que le manifeste n'est pas chargé
 * — ou n'existe pas, comme dans les tests — et doit donc porter les mêmes valeurs que
 * le manifeste, sans quoi la bordure sauterait au chargement.
 *
 * `borderStyle` et `borderWidth` sont indispensables : sans bordure dessinée, le
 * navigateur ignore purement et simplement `border-image`.
 */
export function nineSlice(name: string, fallback: Slice, opts: Options = {}): CSSProperties {
  const [top, right, bottom, left] = spriteSize(name)?.slice ?? fallback;
  return {
    borderImageSource: `url(${opts.source ?? sprite(name)})`,
    borderImageSlice: `${top} ${right} ${bottom} ${left}${opts.fill ? ' fill' : ''}`,
    borderImageWidth: `${top}px ${right}px ${bottom}px ${left}px`,
    borderImageRepeat: 'stretch',
    borderStyle: 'solid',
    borderWidth: `${top}px ${right}px ${bottom}px ${left}px`,
  };
}
