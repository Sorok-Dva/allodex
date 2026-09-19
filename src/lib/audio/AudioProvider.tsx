import { createContext, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { audioMeta, audioSrc } from '@/lib/assets';

export type TrackName = 'menu' | 'ambient';
/** Source musicale hors `audio.json` (thème d'une version archivée, par exemple). */
export type TrackSource = { ogg: string; mp3: string };

export type GameAudioState = {
  muted: boolean;
  /** Piste du site (`menu`/`ambient`) mémorisée, même pendant une source externe. */
  track: TrackName | null;
  /** Identifiant de la source externe en cours, `null` si le site joue sa propre piste. */
  external: string | null;
  /** Vrai quand la musique a été mise en pause (`pauseMusic`), sans oublier sa position. */
  paused: boolean;
  /**
   * Lecture **réelle** de l'élément musical actif, déduite de ses événements
   * `play`/`playing`/`pause`/`ended` — pas de l'intention du site. Un `play()` refusé
   * par la politique d'autoplay laisse donc `playing` à `false`, et l'interface ne
   * prétend pas jouer une piste muette.
   */
  playing: boolean;
  ready: boolean;
};

export type GameAudio = GameAudioState & {
  toggleMuted: () => void;
  setTrack: (name: TrackName, opts?: { crossfadeMs?: number }) => void;
  /**
   * Joue une source arbitraire sur le moteur musical, avec le même fondu croisé que
   * `setTrack`. Rappelée avec le même `id`, elle reprend la lecture là où
   * `pauseMusic` l'avait laissée au lieu de repartir du début.
   */
  playExternal: (id: string, src: TrackSource, opts?: { loop?: boolean; crossfadeMs?: number }) => void;
  /** Met la musique en pause en conservant sa position (et la piste du site en mémoire). */
  pauseMusic: () => void;
  /** Revient à la piste du site là où elle en était, en fondu depuis la source externe. */
  resumeAmbient: (opts?: { crossfadeMs?: number }) => void;
  playSfx: (name: string, volume?: number) => void;
};

export const MUTE_KEY = 'allodex:audio-muted';
/** Volume de base des deux pistes musicales (cible du fondu croisé), 0..1. */
const MUSIC_VOLUME = 0.3;
/** Volume par défaut d'un son d'interface joué par `playSfx`, 0..1. */
const SFX_VOLUME = 0.5;
const DEFAULT_CROSSFADE_MS = 1500;
/** Événements qui suffisent à suivre la lecture réelle d'un `<audio>`. */
const MEDIA_EVENTS = ['play', 'playing', 'pause', 'ended'] as const;

export const AudioContext = createContext<GameAudio | null>(null);

function readMuted(storage: Storage): boolean {
  try { return storage.getItem(MUTE_KEY) === '1'; } catch { return false; }
}

function writeMuted(storage: Storage, value: boolean) {
  try { storage.setItem(MUTE_KEY, value ? '1' : '0'); } catch { /* stockage indisponible */ }
}

/** Pose les `<source>` ogg puis mp3 sur un élément musique et recharge le média. */
function assignSource(el: HTMLAudioElement, src: TrackSource, loop: boolean) {
  el.innerHTML = '';
  const ogg = document.createElement('source');
  ogg.src = src.ogg;
  ogg.type = 'audio/ogg';
  const mp3 = document.createElement('source');
  mp3.src = src.mp3;
  mp3.type = 'audio/mpeg';
  el.appendChild(ogg);
  el.appendChild(mp3);
  el.loop = loop;
  el.load();
}

function assignTrack(el: HTMLAudioElement, name: TrackName) {
  assignSource(el, audioSrc(name), audioMeta(name)?.loop ?? false);
}

export function AudioProvider({ children, storage = window.localStorage }: { children: ReactNode; storage?: Storage }) {
  const [muted, setMutedState] = useState<boolean>(() => readMuted(storage));
  const [track, setTrackState] = useState<TrackName | null>(null);
  const [external, setExternalState] = useState<string | null>(null);
  const [paused, setPausedState] = useState(false);
  const [playing, setPlayingState] = useState(false);
  const [ready, setReady] = useState(false);

  // Deux éléments <audio> pour la musique : celui qui joue actuellement et celui qui
  // reçoit la piste suivante pendant le fondu croisé (`activeRef` pointe l'actif).
  const musicRefA = useRef<HTMLAudioElement | null>(null);
  const musicRefB = useRef<HTMLAudioElement | null>(null);
  const activeRef = useRef<HTMLAudioElement | null>(null);
  const mutedRef = useRef(muted);
  const trackRef = useRef<TrackName | null>(null);
  const externalRef = useRef<string | null>(null);
  const pausedRef = useRef(false);
  const gestureRef = useRef(false);
  const fadeFrameRef = useRef<number | null>(null);

  mutedRef.current = muted;

  const setPaused = useCallback((value: boolean) => {
    pausedRef.current = value;
    setPausedState(value);
  }, []);

  useEffect(() => {
    activeRef.current = musicRefA.current;
    setReady(true);
  }, []);

  // Lecture réelle : on écoute les deux éléments (l'actif change à chaque fondu) et on
  // ne retient que les événements de celui qui est actif. C'est le navigateur qui a le
  // dernier mot — un `play()` bloqué par l'autoplay n'émet pas d'événement `play`.
  useEffect(() => {
    const els = [musicRefA.current, musicRefB.current].filter((el): el is HTMLAudioElement => el !== null);
    const sync = (e: Event) => {
      if (e.target !== activeRef.current) return;
      setPlayingState(e.type === 'play' || e.type === 'playing');
    };
    els.forEach(el => MEDIA_EVENTS.forEach(name => el.addEventListener(name, sync)));
    return () => els.forEach(el => MEDIA_EVENTS.forEach(name => el.removeEventListener(name, sync)));
  }, []);

  const stopFade = useCallback(() => {
    if (fadeFrameRef.current !== null) {
      cancelAnimationFrame(fadeFrameRef.current);
      fadeFrameRef.current = null;
    }
  }, []);

  // Sans ça, un fondu en cours continuerait de muter le volume des <audio> après le
  // démontage du provider (aucun composant ne les possède plus).
  useEffect(() => stopFade, [stopFade]);

  // Fondu linéaire par rAF : `toEl` monte de 0 (ou reste à `MUSIC_VOLUME` si rien à
  // fondre) pendant que `fromEl` redescend à 0, puis se met en pause. `restart: false`
  // reprend `toEl` à sa position courante (retour à l'ambiance du site, reprise après
  // pause) au lieu de le rembobiner.
  const crossfade = useCallback((toEl: HTMLAudioElement, fromEl: HTMLAudioElement | null, crossfadeMs: number, opts: { restart?: boolean } = {}) => {
    stopFade();
    toEl.muted = mutedRef.current;
    if (opts.restart !== false) toEl.currentTime = 0;
    if (!fromEl || crossfadeMs <= 0) {
      toEl.volume = MUSIC_VOLUME;
      toEl.play().catch(() => {});
      fromEl?.pause();
      return;
    }
    toEl.volume = 0;
    toEl.play().catch(() => {});
    const fromStart = fromEl.paused ? MUSIC_VOLUME : fromEl.volume;
    const start = performance.now();
    const tick = (now: number) => {
      // `now` est l'horodatage du **début de la frame** : il peut précéder le
      // `performance.now()` lu juste avant, d'où un `t` négatif et un volume hors
      // domaine refusé par le navigateur si on ne borne pas des deux côtés.
      const t = Math.min(1, Math.max(0, (now - start) / crossfadeMs));
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

  /** Reprend l'élément actif là où il en était (sortie de `pauseMusic`). */
  const resumeActive = useCallback(() => {
    setPaused(false);
    const el = activeRef.current;
    if (!el || !gestureRef.current || mutedRef.current) return;
    el.muted = mutedRef.current;
    el.volume = MUSIC_VOLUME;
    el.play().catch(() => {});
  }, [setPaused]);

  const setTrack = useCallback((name: TrackName, opts: { crossfadeMs?: number } = {}) => {
    const sameTrack = trackRef.current === name && externalRef.current === null;
    if (sameTrack && !pausedRef.current) return;
    if (sameTrack) { resumeActive(); return; }
    const crossfadeMs = opts.crossfadeMs ?? DEFAULT_CROSSFADE_MS;
    const hadMusic = trackRef.current !== null || externalRef.current !== null;
    const fromEl = hadMusic ? activeRef.current : null;
    const toEl = fromEl === musicRefA.current ? musicRefB.current : musicRefA.current;
    if (!toEl) return;
    assignTrack(toEl, name);
    trackRef.current = name;
    setTrackState(name);
    externalRef.current = null;
    setExternalState(null);
    setPaused(false);
    activeRef.current = toEl;
    if (gestureRef.current && !mutedRef.current) {
      crossfade(toEl, fromEl, fromEl ? crossfadeMs : 0);
    } else {
      // Pas encore de geste utilisateur (ou son coupé) : on prépare la piste sans la
      // jouer, la politique d'autoplay du navigateur interdirait de toute façon `play()`.
      toEl.muted = mutedRef.current;
      toEl.volume = fromEl ? 0 : MUSIC_VOLUME;
    }
  }, [crossfade, resumeActive, setPaused]);

  // Le thème d'une version des Chroniques n'est pas une piste du site : il ne figure
  // pas dans `audio.json` et ne doit pas effacer `track`, qu'on retrouve en sortant de
  // la page (`resumeAmbient`). Les deux éléments <audio> suffisent : l'un porte la
  // piste du site en pause, l'autre la source externe.
  const playExternal = useCallback((id: string, src: TrackSource, opts: { loop?: boolean; crossfadeMs?: number } = {}) => {
    if (externalRef.current === id) { resumeActive(); return; }
    const crossfadeMs = opts.crossfadeMs ?? DEFAULT_CROSSFADE_MS;
    const hadMusic = trackRef.current !== null || externalRef.current !== null;
    const fromEl = hadMusic ? activeRef.current : null;
    const toEl = fromEl === musicRefA.current ? musicRefB.current : musicRefA.current;
    if (!toEl) return;
    assignSource(toEl, src, opts.loop ?? false);
    externalRef.current = id;
    setExternalState(id);
    setPaused(false);
    activeRef.current = toEl;
    if (gestureRef.current && !mutedRef.current) {
      crossfade(toEl, fromEl, fromEl ? crossfadeMs : 0);
    } else {
      toEl.muted = mutedRef.current;
      toEl.volume = fromEl ? 0 : MUSIC_VOLUME;
    }
  }, [crossfade, resumeActive, setPaused]);

  const pauseMusic = useCallback(() => {
    stopFade();
    setPaused(true);
    activeRef.current?.pause();
  }, [setPaused, stopFade]);

  const resumeAmbient = useCallback((opts: { crossfadeMs?: number } = {}) => {
    if (trackRef.current === null) return;      // rien à reprendre (entrée directe sur la page)
    const fromEl = externalRef.current !== null ? activeRef.current : null;
    const toEl = fromEl ? (fromEl === musicRefA.current ? musicRefB.current : musicRefA.current) : activeRef.current;
    if (!toEl) return;
    externalRef.current = null;
    setExternalState(null);
    setPaused(false);
    activeRef.current = toEl;
    if (!gestureRef.current || mutedRef.current) { toEl.muted = mutedRef.current; return; }
    // `restart: false` : la piste du site repart là où la visite l'avait laissée.
    crossfade(toEl, fromEl, fromEl ? (opts.crossfadeMs ?? DEFAULT_CROSSFADE_MS) : 0, { restart: false });
  }, [crossfade, setPaused]);

  // Rien ne joue avant un geste utilisateur (politique d'autoplay). Au premier
  // pointerdown/keydown : si le son est coupé au chargement, on ne démarre jamais rien
  // automatiquement ; sinon on lance la piste `menu` demandée (ou déjà en attente).
  useEffect(() => {
    const onGesture = () => {
      if (gestureRef.current) return;
      gestureRef.current = true;
      window.removeEventListener('pointerdown', onGesture);
      window.removeEventListener('keydown', onGesture);
      if (mutedRef.current || pausedRef.current) return;
      // Entrée directe sur les Chroniques : c'est le thème de la version, déjà chargé,
      // qui démarre — surtout pas la piste `menu` du site par-dessus.
      if (externalRef.current !== null) {
        const el = activeRef.current;
        if (el) {
          el.muted = mutedRef.current;
          el.volume = MUSIC_VOLUME;
          el.play().catch(() => {});
        }
        return;
      }
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

  const playSfx = useCallback((name: string, volume = SFX_VOLUME) => {
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

  const api = useMemo<GameAudio>(
    () => ({ muted, track, external, paused, playing, ready, toggleMuted, setTrack, playExternal, pauseMusic, resumeAmbient, playSfx }),
    [muted, track, external, paused, playing, ready, toggleMuted, setTrack, playExternal, pauseMusic, resumeAmbient, playSfx],
  );

  return (
    <AudioContext.Provider value={api}>
      <audio ref={musicRefA} data-testid="music-a" />
      <audio ref={musicRefB} data-testid="music-b" />
      {children}
    </AudioContext.Provider>
  );
}
