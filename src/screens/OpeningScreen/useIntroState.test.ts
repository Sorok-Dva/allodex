import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { initialPhase, resetIntroMemory, useIntroState, FADE_MS, INTRO_MS } from './useIntroState';

describe('initialPhase', () => {
  it('joue l’intro à chaque chargement de page', () => expect(initialPhase(false, false)).toBe('intro'));
  it('ne la rejoue pas si elle a déjà été jouée dans ce chargement (navigation interne)', () => expect(initialPhase(false, true)).toBe('menu'));
  it('force le menu quand forceMenu est vrai', () => expect(initialPhase(true, false)).toBe('menu'));
});

describe('useIntroState', () => {
  beforeEach(() => { resetIntroMemory(); vi.useFakeTimers(); window.history.replaceState(null, '', '/'); });
  afterEach(() => vi.useRealTimers());

  it('enchaîne intro → fading → menu sur les minuteries', () => {
    const { result } = renderHook(() => useIntroState());
    expect(result.current.phase).toBe('intro');
    act(() => { vi.advanceTimersByTime(INTRO_MS); });
    expect(result.current.phase).toBe('fading');
    act(() => { vi.advanceTimersByTime(FADE_MS); });
    expect(result.current.phase).toBe('menu');
  });

  it('skipIntro lance le fondu immédiatement, sans repasser par intro', () => {
    const { result } = renderHook(() => useIntroState());
    act(() => result.current.skipIntro());
    expect(result.current.phase).toBe('fading');
    act(() => result.current.skipIntro());
    expect(result.current.phase).toBe('fading');
    act(() => { vi.advanceTimersByTime(FADE_MS); });
    expect(result.current.phase).toBe('menu');
  });

  it('mémorise l’intro jouée pour le reste du chargement, sans toucher au localStorage', () => {
    renderHook(() => useIntroState());
    expect(initialPhase()).toBe('menu');
    expect(window.localStorage.length).toBe(0);
    const { result } = renderHook(() => useIntroState());
    expect(result.current.phase).toBe('menu');
    act(() => result.current.replayIntro());
    expect(result.current.phase).toBe('intro');
  });

  it('respecte ?skipIntro', () => {
    window.history.replaceState(null, '', '/?skipIntro');
    const { result } = renderHook(() => useIntroState());
    expect(result.current.phase).toBe('menu');
  });
});
