import { createRef } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { EngineCutscene, type MediaLike } from './EngineCutscene';

describe('EngineCutscene', () => {
  it('behaves like a paused media element until its scene loads', async () => {
    const ref = createRef<MediaLike>();
    const fetcher = vi.fn(async () => new Response('nope', { status: 404 })) as unknown as typeof fetch;
    render(<EngineCutscene ref={ref} sceneUrl="/game/cinematics/engine/x/scene.json" subtitleLang="en" fetcher={fetcher} />);
    expect(screen.getByTestId('engine-cutscene').getAttribute('data-loading')).toBe('true');
    await waitFor(() => expect(fetcher).toHaveBeenCalledWith('/game/cinematics/engine/x/scene.json'));
    expect(ref.current?.paused).toBe(true);
    expect(ref.current?.readyState).toBe(0);
    await ref.current?.play();
    expect(ref.current?.paused).toBe(false);
    ref.current!.currentTime = 12;
    expect(ref.current?.currentTime).toBe(12);
    ref.current?.pause();
    expect(ref.current?.paused).toBe(true);
  });
});
