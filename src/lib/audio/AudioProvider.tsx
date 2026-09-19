import { createContext, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { audioMeta, audioSrc } from '@/lib/assets';

export type TrackName = 'menu' | 'ambient';

export type GameAudioState = {
  muted: boolean;
  track: TrackName | null;
  ready: boolean;
};

export type GameAudio = GameAudioState & {
  toggleMuted: () => void;
  setTrack: (name: TrackName, opts?: { crossfadeMs?: number }) => void;
  playSfx: (name: string, volume?: number) => void;
};

export const MUTE_KEY = 'allodex:audio-muted';
const MUSIC_VOLUME = 0.5;
const DEFAULT_CROSSFADE_MS = 1500;

export const AudioContext = createContext<GameAudio | null>(null);

function readMuted(storage: Storage): boolean {
  try { return storage.getItem(MUTE_KEY) === '1'; } catch { return false; }
}

function writeMuted(storage: Storage, value: boolean) {
  try { storage.setItem(MUTE_KEY, value ? '1' : '0'); } catch { /* stockage indisponible */ }
}

/** Pose les `<source>` ogg puis mp3 sur un élément musique et recharge le média. */
function assignTrack(el: HTMLAudioElement, name: TrackName) {
  const src = audioSrc(name);
  el.innerHTML = '';
  const ogg = document.createElement('source');
  ogg.src = src.ogg;
  ogg.type = 'audio/ogg';
  const mp3 = document.createElement('source');
  mp3.src = src.mp3;
  mp3.type = 'audio/mpeg';
  el.appendChild(ogg);
  el.appendChild(mp3);
  el.loop = audioMeta(name)?.loop ?? false;
  el.load();
}

export function AudioProvider({ children, storage = window.localStorage }: { children: ReactNode; storage?: Storage }) {
  const [muted, setMutedState] = useState<boolean>(() => readMuted(storage));
  const [track, setTrackState] = useState<TrackName | null>(null);
  const [ready, setReady] = useState(false);

  // Deux éléments <audio> pour la musique : celui qui joue actuellement et celui qui
  // reçoit la piste suivante pendant le fondu croisé (`activeRef` pointe l'actif).
  const musicRefA = useRef<HTMLAudioElement | null>(null);
  const musicRefB = useRef<HTMLAudioElement | null>(null);
  const activeRef = useRef<HTMLAudioElement | null>(null);
  const mutedRef = useRef(muted);
  const trackRef = useRef<TrackName | null>(null);
  const gestureRef = useRef(false);
  const fadeFrameRef = useRef<number | null>(null);

  mutedRef.current = muted;

  useEffect(() => {
    activeRef.current = musicRefA.current;
    setReady(true);
  }, []);

  const stopFade = useCallback(() => {
    if (fadeFrameRef.current !== null) {
      cancelAnimationFrame(fadeFrameRef.current);
      fadeFrameRef.current = null;
    }
  }, []);

  // Fondu linéaire par rAF : `toEl` monte de 0 (ou reste à `MUSIC_VOLUME` si rien à
  // fondre) pendant que `fromEl` redescend à 0, puis se met en pause.
  const crossfade = useCallback((toEl: HTMLAudioElement, fromEl: HTMLAudioElement | null, crossfadeMs: number) => {
    stopFade();
    toEl.muted = mutedRef.current;
    toEl.currentTime = 0;
    if (!fromEl || crossfadeMs <= 0) {
      toEl.volume = MUSIC_VOLUME;
      toEl.play().catch(() => {});
      fromEl?.pause();
      return;
    }
    toEl.volume = 0;
    toEl.play().catch(() => {});
    const fromStart = fromEl.volume || MUSIC_VOLUME;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / crossfadeMs);
      toEl.volume = MUSIC_VOLUME * t;
      fromEl.volume = fromStart * (1 - t);
      if (t < 1) {
        fadeFrameRef.current = requestAnimationFrame(tick);
      } else {
        fadeFrameRef.current = null;
        fromEl.pause();
      }
    };
    fadeFrameRef.current = requestAnimationFrame(tick);
  }, [stopFade]);

  const setTrack = useCallback((name: TrackName, opts: { crossfadeMs?: number } = {}) => {
    if (trackRef.current === name) return;
    const crossfadeMs = opts.crossfadeMs ?? DEFAULT_CROSSFADE_MS;
    const hadTrack = trackRef.current !== null;
    const fromEl = hadTrack ? activeRef.current : null;
    const toEl = fromEl === musicRefA.current ? musicRefB.current : musicRefA.current;
    if (!toEl) return;
    assignTrack(toEl, name);
    trackRef.current = name;
    setTrackState(name);
    activeRef.current = toEl;
    if (gestureRef.current && !mutedRef.current) {
      crossfade(toEl, fromEl, fromEl ? crossfadeMs : 0);
    } else {
      // Pas encore de geste utilisateur (ou son coupé) : on prépare la piste sans la
      // jouer, la politique d'autoplay du navigateur interdirait de toute façon `play()`.
      toEl.muted = mutedRef.current;
      toEl.volume = fromEl ? 0 : MUSIC_VOLUME;
    }
  }, [crossfade]);

  // Rien ne joue avant un geste utilisateur (politique d'autoplay). Au premier
  // pointerdown/keydown : si le son est coupé au chargement, on ne démarre jamais rien
  // automatiquement ; sinon on lance la piste `menu` demandée (ou déjà en attente).
  useEffect(() => {
    const onGesture = () => {
      if (gestureRef.current) return;
      gestureRef.current = true;
      window.removeEventListener('pointerdown', onGesture);
      window.removeEventListener('keydown', onGesture);
      if (mutedRef.current) return;
      const name = trackRef.current;
      if (name === null) {
        setTrack('menu', { crossfadeMs: 0 });
        return;
      }
      if (name === 'menu') {
        const el = activeRef.current;
        if (el) {
          el.muted = mutedRef.current;
          el.volume = MUSIC_VOLUME;
          el.play().catch(() => {});
        }
      }
    };
    window.addEventListener('pointerdown', onGesture);
    window.addEventListener('keydown', onGesture);
    return () => {
      window.removeEventListener('pointerdown', onGesture);
      window.removeEventListener('keydown', onGesture);
    };
  }, [setTrack]);

  const toggleMuted = useCallback(() => {
    setMutedState(prev => {
      const next = !prev;
      mutedRef.current = next;
      writeMuted(storage, next);
      // `.muted`, jamais `.pause()` : la position de lecture continue derrière le mute.
      [musicRefA.current, musicRefB.current].forEach(el => { if (el) el.muted = next; });
      return next;
    });
  }, [storage]);

  const playSfx = useCallback((name: string, volume = 0.8) => {
    if (mutedRef.current) return;
    const meta = audioMeta(name);
    if (!meta) return;
    const src = audioSrc(name);
    const el = document.createElement('audio');
    const ogg = document.createElement('source');
    ogg.src = src.ogg;
    ogg.type = 'audio/ogg';
    const mp3 = document.createElement('source');
    mp3.src = src.mp3;
    mp3.type = 'audio/mpeg';
    el.appendChild(ogg);
    el.appendChild(mp3);
    el.loop = meta.loop;
    el.volume = volume;
    el.style.display = 'none';
    document.body.appendChild(el);
    const cleanup = () => el.remove();
    el.addEventListener('ended', cleanup, { once: true });
    window.setTimeout(cleanup, Math.max(500, meta.duration * 1000 + 300));
    el.play().catch(() => {});
  }, []);

  const api = useMemo<GameAudio>(() => ({ muted, track, ready, toggleMuted, setTrack, playSfx }), [muted, track, ready, toggleMuted, setTrack, playSfx]);

  return (
    <AudioContext.Provider value={api}>
      <audio ref={musicRefA} data-testid="music-a" />
      <audio ref={musicRefB} data-testid="music-b" />
      {children}
    </AudioContext.Provider>
  );
}
