import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import * as SkeletonUtils from 'three/examples/jsm/utils/SkeletonUtils.js';
import type { SubtitleLang } from '@/lib/cinematics';
import { createUvScroll } from '@/components/scene/MenuScene/uvScroll';
import { actorClipAt, argb, sampleKeys, subtitleAt, voiceAt, type EngineScene } from './timeline';
import s from './EngineCutscene.module.css';

// Même parti pris que les scènes de menu et les fatalités : les textures du jeu sont des octets,
// pas des couleurs sRGB à linéariser.
THREE.ColorManagement.enabled = false;

/**
 * Sous-ensemble de `HTMLMediaElement` que le lecteur du film utilise : la cinématique moteur se
 * pilote comme ses vidéos (lecture, pause, position, fin).
 */
export type MediaLike = {
  play: () => Promise<void>;
  pause: () => void;
  readonly paused: boolean;
  currentTime: number;
  readonly duration: number;
  readonly readyState: number;
  muted: boolean;
};

export type EngineCutsceneProps = {
  /** URL de `scene.json` ; les autres fichiers sont relatifs à son dossier. */
  sceneUrl: string;
  subtitleLang: SubtitleLang | null;
  /** Lecteur caché (préchargement) : ni rendu ni son. */
  hidden?: boolean;
  className?: string;
  onClick?: () => void;
  onLoadedMetadata?: () => void;
  onTimeUpdate?: (time: number) => void;
  onEnded?: () => void;
  onPlay?: () => void;
  onPause?: () => void;
  /** Seams de test (jsdom n'a ni WebGL ni réseau). */
  createRenderer?: (canvas: HTMLCanvasElement) => THREE.WebGLRenderer;
  fetcher?: typeof fetch;
};

const TIME_UPDATE_MS = 250;

type Actor = { id: string; holder: THREE.Object3D; mixer: THREE.AnimationMixer; actions: Map<string, THREE.AnimationAction> };

/**
 * Matériau d'affichage d'une primitive exportée par `tools/extract_engine_cutscene.py` : décor sans
 * éclairage dynamique (sa lumière précalculée est dans les couleurs de sommets), acteurs éclairés
 * (`extras.lit`), matériaux additifs et découpes (`extras.cutout`) comme dans le jeu.
 */
function convertMaterial(source: THREE.Material, glow: THREE.Color | null): THREE.Material {
  const src = source as THREE.MeshBasicMaterial;
  const extras = (source.userData ?? {}) as { blend?: string; lit?: boolean; cutout?: boolean };
  const additive = extras.blend === 'add';
  const translucent = source.transparent || additive;
  const common = {
    name: source.name,
    map: src.map ?? null,
    color: 0xffffff,
    opacity: source.opacity,
    transparent: translucent,
    alphaTest: extras.cutout ? 0.5 : 0,
    side: THREE.DoubleSide,
    vertexColors: src.vertexColors,
    toneMapped: false,
    fog: true,
  };
  let material: THREE.MeshBasicMaterial | THREE.MeshLambertMaterial;
  if (extras.lit && !translucent) {
    // Acteur : la lumière précalculée du décor alentour l'éclaire (émission modulée par sa texture),
    // les lumières de la scène ne font que dessiner les volumes.
    material = new THREE.MeshLambertMaterial(common);
    if (glow && src.map) { material.emissive = glow; material.emissiveMap = src.map; }
  } else {
    material = new THREE.MeshBasicMaterial(common);
  }
  if (translucent) material.depthWrite = false;
  if (additive) material.blending = THREE.AdditiveBlending;
  if (material.map) material.map.colorSpace = THREE.NoColorSpace;
  return material;
}

/**
 * Cinématique moteur recréée en 3D : décor et acteurs du client, caméra de la cinématique, voix et
 * sous-titres officiels. Le temps est une horloge propre (pas le mixeur) : chaque image est
 * recalculée d'après la position, ce qui rend la recherche exacte.
 */
export const EngineCutscene = forwardRef<MediaLike, EngineCutsceneProps>(function EngineCutscene(
  { sceneUrl, subtitleLang, hidden = false, className, onClick, onLoadedMetadata, onTimeUpdate, onEnded, onPlay, onPause,
    createRenderer, fetcher = fetch },
  ref,
) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [scene, setScene] = useState<EngineScene | null>(null);
  const [subtitle, setSubtitle] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const st = useRef({
    time: 0,
    playing: false,
    muted: false,
    ready: 0,
    hidden,
    dirty: true,
    lang: subtitleLang,
    voice: -1,
    audios: [] as HTMLAudioElement[],
    lastUpdate: 0,
  });
  const callbacks = useRef({ onLoadedMetadata, onTimeUpdate, onEnded, onPlay, onPause });
  callbacks.current = { onLoadedMetadata, onTimeUpdate, onEnded, onPlay, onPause };
  const sceneRef = useRef<EngineScene | null>(null);

  const stopVoice = () => {
    const state = st.current;
    if (state.voice >= 0) state.audios[state.voice]?.pause();
    state.voice = -1;
  };

  useImperativeHandle(ref, () => ({
    play: async () => {
      const state = st.current;
      if (state.playing) return;
      if (sceneRef.current && state.time >= sceneRef.current.duration) state.time = 0;
      state.playing = true;
      state.dirty = true;
      callbacks.current.onPlay?.();
    },
    pause: () => {
      const state = st.current;
      if (!state.playing) return;
      state.playing = false;
      stopVoice();
      callbacks.current.onPause?.();
    },
    get paused() { return !st.current.playing; },
    get currentTime() { return st.current.time; },
    set currentTime(value: number) {
      const state = st.current;
      state.time = Math.max(0, Math.min(value, sceneRef.current?.duration ?? value));
      stopVoice();
      state.dirty = true;
    },
    get duration() { return sceneRef.current?.duration ?? NaN; },
    get readyState() { return st.current.ready; },
    get muted() { return st.current.muted; },
    set muted(value: boolean) {
      st.current.muted = value;
      if (value) stopVoice();
    },
  }), []);

  useEffect(() => {
    const state = st.current;
    state.hidden = hidden;
    state.lang = subtitleLang;
    state.dirty = true;
    if (hidden) stopVoice();
  }, [hidden, subtitleLang]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const state = st.current;
    let alive = true;
    let frame = 0;
    let previous = 0;
    let renderer: THREE.WebGLRenderer | null = null;
    let observer: ResizeObserver | null = null;
    const base = sceneUrl.slice(0, sceneUrl.lastIndexOf('/') + 1);
    const world = new THREE.Scene();
    const root = new THREE.Group();
    world.add(root);
    const camera = new THREE.PerspectiveCamera(45, 16 / 9, 0.5, 4000);
    camera.up.set(0, 0, 1);
    const actors: Actor[] = [];
    const disposables: { dispose(): void }[] = [];
    const scrolls: ReturnType<typeof createUvScroll>[] = [];
    const scrollSpeed = (mesh: THREE.Mesh) => mesh.geometry.userData.uvScroll as [number, number] | undefined;
    let data: EngineScene | null = null;
    const target = new THREE.Vector3();

    const size = () => {
      const host = canvas.parentElement ?? canvas;
      return { width: Math.max(1, host.clientWidth || 1), height: Math.max(1, host.clientHeight || 1) };
    };
    const resize = () => {
      if (!renderer) return;
      const { width, height } = size();
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
      state.dirty = true;
    };

    const mirror = (p: readonly number[]) => (data?.mirror ? new THREE.Vector3(-p[0], p[1], p[2]) : new THREE.Vector3(p[0], p[1], p[2]));

    const syncVoice = () => {
      if (!data) return;
      const want = state.playing && !state.muted && !state.hidden ? voiceAt(data.lines, state.time) : null;
      if (!want) { if (state.voice >= 0) stopVoice(); return; }
      if (want.index === state.voice) return;
      stopVoice();
      const audio = state.audios[want.index];
      if (!audio) return;
      audio.currentTime = want.offset;
      const p = audio.play();
      if (p && typeof p.catch === 'function') p.catch(() => {});
      state.voice = want.index;
    };

    const apply = () => {
      if (!data) return;
      const t = state.time;
      camera.position.copy(mirror(sampleKeys(data.camera.points, t)));
      target.copy(mirror(sampleKeys(data.camera.targets, t)));
      if (camera.position.distanceToSquared(target) > 1e-6) camera.lookAt(target);
      for (const actor of actors) {
        const info = data.actors.find(a => a.id === actor.id);
        if (!info) continue;
        const { clip, time } = actorClipAt(info, data.lines, t);
        const action = actor.actions.get(clip) ?? actor.actions.get(info.idle);
        if (!action) continue;
        actor.holder.visible = t >= (info.appear ?? 0);
        for (const other of actor.actions.values()) other.enabled = other === action;
        const length = action.getClip().duration || 1;
        action.play();
        action.time = clip === info.idle ? time % length : Math.min(time, length - 1e-4);
        actor.mixer.update(0);
      }
      for (const sc of scrolls) sc.update(t);
      const text = subtitleAt(data, t, state.lang);
      setSubtitle(prev => (prev === text ? prev : text));
    };

    const tick = () => {
      frame = requestAnimationFrame(tick);
      const now = performance.now();
      const delta = previous ? Math.min((now - previous) / 1000, 0.25) : 0;
      previous = now;
      if (!data) return;
      if (state.playing) {
        state.time += delta;
        if (state.time >= data.duration) {
          state.time = data.duration;
          state.playing = false;
          stopVoice();
          callbacks.current.onTimeUpdate?.(state.time);
          callbacks.current.onEnded?.();
        }
        state.dirty = true;
        if (now - state.lastUpdate >= TIME_UPDATE_MS) {
          state.lastUpdate = now;
          callbacks.current.onTimeUpdate?.(state.time);
        }
      }
      syncVoice();
      if (!state.dirty || state.hidden || !renderer) return;
      apply();
      renderer.render(world, camera);
      state.dirty = false;
    };

    const convert = (object: THREE.Object3D, glow: THREE.Color | null = null) => {
      object.traverse(node => {
        const mesh = node as THREE.Mesh;
        if (!mesh.isMesh) return;
        mesh.frustumCulled = false;
        const list = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
        const converted = list.map(m => convertMaterial(m, glow));
        for (const material of converted) disposables.push(material);
        disposables.push(mesh.geometry);
        mesh.material = Array.isArray(mesh.material) ? converted : converted[0];
      });
    };

    const setup = async () => {
      try {
        const res = await fetcher(sceneUrl);
        if (!res.ok) throw new Error(`${res.status}`);
        data = (await res.json()) as EngineScene;
      } catch (error) {
        if (import.meta.env.DEV) console.warn('[EngineCutscene] scène illisible', error);
        return;
      }
      if (!alive) return;
      sceneRef.current = data;
      setScene(data);
      state.ready = 1;
      callbacks.current.onLoadedMetadata?.();
      camera.fov = data.camera.fov || 45;
      if (data.mirror) root.scale.set(-1, 1, 1);
      const light = data.light;
      const fog = new THREE.Color(...argb(light.fog));
      world.background = fog;
      if (light.fogEnd) world.fog = new THREE.Fog(fog, light.fogStart ?? 0, light.fogEnd);
      // Acteurs : ambiante de la zone ×2 et une lumière orientée de la couleur d'auto-illumination
      // (celle des lumières ponctuelles du décor) venant du soleil de la zone. Choix du lecteur :
      // le client éclaire ses personnages avec ses shaders, non lus.
      world.add(new THREE.AmbientLight(new THREE.Color(...argb(light.ambient, 2)), 1));
      const sun = new THREE.DirectionalLight(new THREE.Color(...argb(light.selfIllum)), 0.6);
      const yaw = THREE.MathUtils.degToRad(light.sunYaw ?? 45);
      const pitch = THREE.MathUtils.degToRad(light.sunPitch ?? 40);
      sun.position.set(-Math.cos(yaw) * Math.cos(pitch), Math.sin(yaw) * Math.cos(pitch), Math.sin(pitch)).multiplyScalar(100);
      world.add(sun);
      state.audios = data.lines.map(line => {
        const audio = new Audio();
        if (line.voice) {
          const ogg = typeof audio.canPlayType === 'function' && audio.canPlayType('audio/ogg; codecs="opus"');
          audio.src = base + (ogg ? line.voice.ogg : line.voice.mp3);
          audio.preload = 'auto';
        }
        return audio;
      });

      renderer = createRenderer
        ? createRenderer(canvas)
        : new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'high-performance' });
      renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      window.addEventListener('resize', resize);
      if (typeof ResizeObserver !== 'undefined') { observer = new ResizeObserver(resize); observer.observe(canvas.parentElement ?? canvas); }
      resize();

      const loader = new GLTFLoader();
      const load = (url: string) => loader.loadAsync(base + url);
      try {
        const [decor, ...loaded] = await Promise.all([load(data.decor), ...data.actors.map(a => load(a.glb))]);
        if (!alive) return;
        convert(decor.scene);
        root.add(decor.scene);
        scrolls.push(createUvScroll(decor.scene, scrollSpeed));
        data.actors.forEach((info, i) => {
          const gltf = loaded[i];
          const model = SkeletonUtils.clone(gltf.scene);
          convert(model, info.light ? new THREE.Color(info.light[0] * 0.7, info.light[1] * 0.7, info.light[2] * 0.7) : null);
          scrolls.push(createUvScroll(model, scrollSpeed));
          const holder = new THREE.Group();
          holder.position.set(...info.position);
          holder.rotation.z = info.yaw;
          holder.scale.setScalar(info.scale || 1);
          holder.add(model);
          root.add(holder);
          const mixer = new THREE.AnimationMixer(model);
          const actions = new Map(gltf.animations.map(clip => [clip.name, mixer.clipAction(clip)]));
          actors.push({ id: info.id, holder, mixer, actions });
        });
      } catch (error) {
        if (import.meta.env.DEV) console.warn('[EngineCutscene] modèles illisibles', error);
      }
      if (!alive) return;
      state.ready = 4;
      state.dirty = true;
      setLoading(false);
      if (import.meta.env.DEV) (window as Window & { __engineCutscene?: unknown }).__engineCutscene = { world, camera, state, actors, renderer };
      frame = requestAnimationFrame(tick);
    };
    void setup();

    return () => {
      alive = false;
      if (frame) cancelAnimationFrame(frame);
      observer?.disconnect();
      window.removeEventListener('resize', resize);
      stopVoice();
      for (const audio of state.audios) { audio.removeAttribute('src'); }
      state.audios = [];
      for (const sc of scrolls) sc.dispose();
      for (const d of disposables) d.dispose();
      renderer?.dispose();
      sceneRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sceneUrl]);

  return (
    <div className={`${s.cutscene} ${className ?? ''}`} onClick={onClick} data-testid="engine-cutscene" data-loading={loading ? 'true' : 'false'}>
      <canvas ref={canvasRef} className={s.canvas} />
      {scene && loading && <div className={s.loading} aria-hidden="true" />}
      {subtitle && !hidden && <p className={s.subtitle}>{subtitle}</p>}
    </div>
  );
});
