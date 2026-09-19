import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { MedalBadge } from './MedalBadge';

function badge(score: number): HTMLElement {
  const { container } = render(
    <MedalBadge score={score} icon="Interface/Icons/Misc/Event/GoldMedal" complete />,
  );
  return container.firstElementChild as HTMLElement;
}

const part = (el: HTMLElement, name: string) => el.querySelector(`[class*="${name}"]`) as HTMLElement;

describe('MedalBadge', () => {
  /**
   * Les cinq textures `MedalFrame*` portent la même plaque aux mêmes coordonnées (vérifié
   * au pixel : région y 20→70 / x 25→76 identique), seul l'ornement autour grandit. Le
   * cadre est donc posé au même endroit et l'icône ne bouge pas d'un palier à l'autre.
   */
  it('pose le cadre et l’icône au même endroit à tous les paliers', () => {
    const one = badge(10);
    const four = badge(100);
    expect([one.style.left, one.style.top]).toEqual([four.style.left, four.style.top]);
    expect(part(one, 'icon').style.left).toBe(part(four, 'icon').style.left);
    expect(part(one, 'icon').style.top).toBe(part(four, 'icon').style.top);
    // Seule la taille de la texture change (81 × 109 contre 98 × 121, à l'échelle 0,875).
    expect(one.style.width).toBe('70.875px');
    expect(four.style.width).toBe('85.75px');
  });

  /**
   * L'écu est centré sur la plaque, pas sur la texture (qui déborde à droite au palier I) :
   * centrer sur la boîte décalait le score de 8 px à gauche (relevé : « 20 » du jeu centré
   * en x 873 sur `refs/astral.png`, contre 866 avant correction).
   */
  it('centre le score sur la plaque, pas sur la boîte de la texture', () => {
    const one = badge(10);
    expect(part(one, 'score').style.left).toBe('44.1875px');
    expect(part(badge(100), 'score').style.left).toBe('44.1875px');
  });
});
