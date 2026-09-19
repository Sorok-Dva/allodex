import { useCallback, useRef } from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { GameScrollbar } from './GameScrollbar';

/**
 * jsdom ne calcule aucune mise en page : `scrollHeight`, `clientHeight` et `scrollTop`
 * sont figés à 0. On les remplace par de vrais accesseurs sur le conteneur, posés par
 * la ref de rappel (attachée avant les effets de disposition de `GameScrollbar`).
 */
function Harness({ scrollHeight, clientHeight, thumbSize }: { scrollHeight: number; clientHeight: number; thumbSize?: number | null }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const attach = useCallback((el: HTMLDivElement | null) => {
    if (el && ref.current !== el) {
      let top = 0;
      Object.defineProperty(el, 'scrollHeight', { configurable: true, get: () => scrollHeight });
      Object.defineProperty(el, 'clientHeight', { configurable: true, get: () => clientHeight });
      Object.defineProperty(el, 'scrollTop', { configurable: true, get: () => top, set: (v: number) => { top = v; } });
    }
    ref.current = el;
  }, [scrollHeight, clientHeight]);
  return (
    <div>
      <div ref={attach} data-testid="target" />
      <GameScrollbar targetRef={ref} thumbSize={thumbSize} />
    </div>
  );
}

describe('GameScrollbar', () => {
  it('donne au curseur une hauteur proportionnelle au contenu avec thumbSize={null}', () => {
    render(<Harness scrollHeight={400} clientHeight={100} thumbSize={null} />);
    const thumb = screen.getByTestId('scrollbar-thumb');
    expect(thumb.style.height).toBe('25%');
    expect(thumb.style.top).toBe('0%');
  });

  it('fait défiler de 40 px au clic sur la flèche du bas et déplace le curseur', () => {
    render(<Harness scrollHeight={400} clientHeight={100} thumbSize={null} />);
    const target = screen.getByTestId('target');
    fireEvent.click(screen.getByTestId('scrollbar-down'));
    expect(target.scrollTop).toBe(40);
    // 40 / (400 - 100) = 13,33 % du débattement, soit 13,33 % de (100 % - 25 %).
    expect(screen.getByTestId('scrollbar-thumb').style.top).toBe('10%');
  });

  it('remonte de 40 px au clic sur la flèche du haut', () => {
    render(<Harness scrollHeight={400} clientHeight={100} />);
    const target = screen.getByTestId('target');
    fireEvent.click(screen.getByTestId('scrollbar-down'));
    fireEvent.click(screen.getByTestId('scrollbar-down'));
    fireEvent.click(screen.getByTestId('scrollbar-up'));
    expect(target.scrollTop).toBe(40);
  });

  it('utilise par défaut le curseur de taille fixe du jeu (20 px)', () => {
    render(<Harness scrollHeight={400} clientHeight={100} />);
    expect(screen.getByTestId('scrollbar-thumb').style.height).toBe('20px');
  });

  it('accepte une taille fixe explicite', () => {
    render(<Harness scrollHeight={400} clientHeight={100} thumbSize={32} />);
    expect(screen.getByTestId('scrollbar-thumb').style.height).toBe('32px');
  });

  it('masque le curseur quand il n’y a rien à défiler', () => {
    render(<Harness scrollHeight={100} clientHeight={100} />);
    expect(screen.queryByTestId('scrollbar-thumb')).toBeNull();
    expect((screen.getByTestId('scrollbar-down') as HTMLButtonElement).disabled).toBe(true);
  });

  // Spec § 7.1 : aucun filtre côté navigateur. L'état inactif d'une flèche est un sprite
  // à part, dérivé du sprite actif à la découpe (`tools/cut_sprites.py`).
  it('utilise les sprites grisés pour les flèches inactives', () => {
    render(<Harness scrollHeight={400} clientHeight={100} />);
    const up = screen.getByTestId('scrollbar-up');
    const down = screen.getByTestId('scrollbar-down');
    expect(up.style.backgroundImage).toContain('scroll-up-off.png');
    expect(down.style.backgroundImage).toContain('scroll-down.png');

    fireEvent.click(down);

    expect(screen.getByTestId('scrollbar-up').style.backgroundImage).toContain('scroll-up.png');
    expect(screen.getByTestId('scrollbar-up').style.backgroundImage).not.toContain('scroll-up-off.png');
  });
});
