import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { MedalsScreen } from './MedalsScreen';

const playSfx = vi.fn();
vi.mock('@/lib/audio/useGameAudio', () => ({
  useGameAudio: () => ({ muted: false, track: null, ready: true, toggleMuted: vi.fn(), setTrack: vi.fn(), playSfx }),
}));

beforeEach(() => {
  playSfx.mockClear();
  HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
  HTMLMediaElement.prototype.pause = vi.fn();
});

describe('MedalsScreen — audio', () => {
  it("joue « medals-open » au montage de l'écran", () => {
    render(<MedalsScreen />);
    expect(playSfx).toHaveBeenCalledWith('medals-open');
  });

  it('joue « medals-close » au clic sur la croix, avant la navigation', () => {
    const { getByLabelText } = render(<MedalsScreen />);
    playSfx.mockClear();
    fireEvent.click(getByLabelText('Fermer'));
    expect(playSfx).toHaveBeenCalledWith('medals-close');
  });
});
