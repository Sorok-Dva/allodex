import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import type { ArchiveEntry } from '@/lib/assets';
import { VersionTimeline } from './VersionTimeline';

const ENTRIES: ArchiveEntry[] = [
  { version: '1.1', label: 'Allods Online 1.1', media: 'image', background: 'background.png' },
  { version: '8.0', label: 'Allods Online 8.0', media: 'image', background: 'background.png' },
  { version: '16.0', label: 'Allods Online 16.0', media: 'video', video: { webm: 'menu.webm', mp4: 'menu.mp4' } },
];

function setup(active = '8.0', onSelect = vi.fn()) {
  const utils = render(<VersionTimeline entries={ENTRIES} active={active} onSelect={onSelect} />);
  return { ...utils, onSelect };
}

describe('VersionTimeline', () => {
  it('rend une pilule par version', () => {
    const { getAllByTestId } = setup();
    expect(getAllByTestId('version-pill').map(el => el.textContent)).toEqual(['1.1', '8.0', '16.0']);
  });

  it('met en surbrillance la seule version active', () => {
    const { getAllByTestId } = setup('16.0');
    const current = getAllByTestId('version-pill').filter(el => el.getAttribute('aria-current') === 'true');
    expect(current.map(el => el.textContent)).toEqual(['16.0']);
  });

  it('sélectionne la version au clic sur sa pilule', () => {
    const { getAllByTestId, onSelect } = setup();
    fireEvent.click(getAllByTestId('version-pill')[2]);
    expect(onSelect).toHaveBeenCalledWith('16.0');
  });

  it('les flèches vont à la version précédente et suivante', () => {
    const { getByLabelText, onSelect } = setup();
    fireEvent.click(getByLabelText('Version suivante'));
    expect(onSelect).toHaveBeenCalledWith('16.0');
    fireEvent.click(getByLabelText('Version précédente'));
    expect(onSelect).toHaveBeenCalledWith('1.1');
  });

  it('désactive la flèche des extrémités', () => {
    const first = setup('1.1');
    expect((first.getByLabelText('Version précédente') as HTMLButtonElement).disabled).toBe(true);
    expect((first.getByLabelText('Version suivante') as HTMLButtonElement).disabled).toBe(false);
    first.unmount();

    const last = setup('16.0');
    expect((last.getByLabelText('Version suivante') as HTMLButtonElement).disabled).toBe(true);
  });
});
