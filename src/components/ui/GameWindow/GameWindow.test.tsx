import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render } from '@testing-library/react';
import { GameWindow } from './GameWindow';

describe('GameWindow', () => {
  it('pose le cadre, la plaque de titre et la croix de l’hôtel des ventes du jeu', () => {
    const onClose = vi.fn();
    const page = render(<GameWindow title="Cinématiques" onClose={onClose} closeLabel="Fermer" header={<p>haut</p>} footer={<p>bas</p>}>corps</GameWindow>);
    const win = page.getByRole('region', { name: 'Cinématiques' }) as HTMLElement;
    expect(win.style.width).toBe('857px');
    expect(win.style.height).toBe('790px');
    expect(page.getByRole('heading', { name: 'Cinématiques' })).toBeTruthy();
    const frame = win.querySelector('span[aria-hidden="true"]') as HTMLElement;
    expect(frame.style.borderImageSource).toContain('ContextAuction/AuctionFrame.png');
    const cross = page.getByRole('button', { name: 'Fermer' });
    expect(cross.style.backgroundImage).toContain('CornerCrossNormal.png');
    fireEvent.pointerDown(cross);
    expect(cross.style.backgroundImage).toContain('CornerCrossPressed.png');
    fireEvent.click(cross);
    expect(onClose).toHaveBeenCalled();
    expect(page.getByText('haut')).toBeTruthy();
    expect(page.getByText('bas')).toBeTruthy();
  });
  it('ne descend pas sous la largeur des deux extrémités du cadre', () => {
    const page = render(<GameWindow title="T" onClose={() => {}} closeLabel="Fermer" width={200}>x</GameWindow>);
    expect((page.getByRole('region', { name: 'T' }) as HTMLElement).style.width).toBe('453px');
  });
});
