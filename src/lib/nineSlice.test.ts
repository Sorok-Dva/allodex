import { describe, it, expect } from 'vitest';
import { nineSlice } from './nineSlice';

describe('nineSlice', () => {
  it('retombe sur les tranches fournies quand le manifeste n\'est pas chargé', () => {
    // `loadManifest()` n'a pas été appelé : `spriteSize()` ne répond rien.
    expect(nineSlice('dropdown-field', [5, 6, 7, 8])).toEqual({
      borderImageSource: 'url(/game/sprites/dropdown-field.png)',
      borderImageSlice: '5 6 7 8',
      borderImageWidth: '5px 6px 7px 8px',
      borderImageRepeat: 'stretch',
      borderStyle: 'solid',
      borderWidth: '5px 6px 7px 8px',
    });
  });

  it('ajoute le mot-clé `fill` aux tranches quand on le demande', () => {
    expect(nineSlice('search-field', [5, 6, 5, 6], { fill: true }).borderImageSlice).toBe('5 6 5 6 fill');
    expect(nineSlice('search-field', [5, 6, 5, 6]).borderImageSlice).toBe('5 6 5 6');
  });

  it('accepte une image hors des sprites découpés (texture du client)', () => {
    const style = nineSlice('ProgressBar', [0, 8, 0, 8], { fill: true, source: '/game/textures/X/ProgressBar.png' });
    expect(style.borderImageSource).toBe('url(/game/textures/X/ProgressBar.png)');
    expect(style.borderWidth).toBe('0px 8px 0px 8px');
  });
});
