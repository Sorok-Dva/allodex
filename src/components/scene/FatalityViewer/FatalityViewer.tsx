import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import type { LoadedScene, SceneLoader } from '@/components/scene/MenuScene';
import s from './FatalityViewer.module.css';

// Même parti pris que les scènes de menu : les textures du jeu sont des octets, pas des
// couleurs sRGB à linéariser (voir `MenuScene`).
THREE.ColorManagement.enabled = false;

export type FatalityViewerProps = {
  /** `.glb` du personnage (toutes ses animations `DeathFatality*` en clips). */
  characterUrl: string;
  /** `.glb` des objets de l'effet, ou `null` si la fatalité n'en a pas d'exporté. */
  fxUrl: string | null;
  /** Nom du clip de la cible à jouer (`DeathFatalityWarrior`…). */
  clip: string;
  /** Hauteur du personnage en unités du jeu : cadre la caméra et la grille au sol. */
  height: number;
  playing: boolean;
  loop: boolean;
  speed: number;
  showFx: boolean;
  className?: string;
  /** Position et durée courantes, une dizaine de fois par seconde pendant la lecture. */
  onProgress?: (time: number, duration: number) => void;
  /** Fin de l'animation, hors boucle : l'écran repasse le bouton en « lecture ». */
  onEnded?: () => void;
  onReady?: () => void;
  /** Seams de test : loader et renderer injectables (jsdom n'a ni réseau ni WebGL). */
  createLoader?: () => SceneLoader;
  createRenderer?: (canvas: HTMLCanvasElement) => THREE.WebGLRenderer;
};

/** Commandes que l'écran envoie au lecteur sans passer par un rendu React. */
export type FatalityViewerHandle = {
  seek: (time: number) => void;
  resetView: () => void;
};

/** Champ de vision vertical de la caméra, en degrés. */
const FOV = 38;
/** Intervalle minimal entre deux `onProgress`, en millisecondes. */
const PROGRESS_INTERVAL_MS = 80;

type Playable = { mixer: THREE.AnimationMixer; actions: THREE.AnimationAction[]; duration: number };

/**
 * Matériau d'affichage d'une primitive exportée par `tools/extract_fatalities.py`.
 *
 * Les personnages sont éclairés (Lambert, normales exportées) pour que les volumes se
 * lisent sous tous les angles ; les effets translucides ou additifs restent sans
 * éclairage, comme dans le jeu, sans écriture de profondeur pour ne pas trouer le
 * personnage.
 */
export function toViewerMaterial(source: THREE.Material): THREE.Material {
  const src = source as THREE.MeshBasicMaterial;
  const additive = (source.userData as { blend?: string } | undefined)?.blend === 'add';
  const translucent = source.transparent || additive;
  const common = {
    name: source.name,
    map: src.map ?? null,
    color: 0xffffff,
    opacity: source.opacity,
    alphaTest: translucent ? 0 : source.alphaTest,
    transparent: translucent,
    side: THREE.DoubleSide,
    vertexColors: true,
    toneMapped: false,
    fog: false,
  };
  const material = translucent ? new THREE.MeshBasicMaterial(common) : new THREE.MeshLambertMaterial(common);
  if (translucent) material.depthWrite = false;
  if (additive) material.blending = THREE.AdditiveBlending;
  if (material.map) material.map.colorSpace = THREE.NoColorSpace;
  return material;
}

/** Actions d'un glTF chargé : le clip demandé pour la cible, tous les clips pour l'effet. */
export function setupPlayable(root: THREE.Object3D, clips: THREE.AnimationClip[]): Playable | null {
  if (!clips.length) return null;
  const mixer = new THREE.AnimationMixer(root);
  const actions = clips.map(clip => {
    const action = mixer.clipAction(clip);
    action.setLoop(THREE.LoopOnce, 1);
    action.clampWhenFinished = true;
    action.play();
    return action;
  });
  return { mixer, actions, duration: Math.max(...clips.map(c => c.duration)) };
}

/** Pose tous les mixeurs à `time` (borné à la durée de chaque clip, dernière image tenue). */
export function applyTime(playables: Playable[], time: number): void {
  for (const { mixer, actions } of playables) {
    for (const action of actions) {
      action.enabled = true;
      action.paused = false;
      action.time = Math.max(0, Math.min(time, action.getClip().duration - 1e-4));
    }
    mixer.update(0);
  }
}

/**
 * Scène 3D d'une fatalité : le personnage cible joue son animation de mort, l'effet de
 * la fatalité s'anime à ses pieds, et la caméra tourne autour (`OrbitControls`). Le temps
 * est piloté à la main (pas par le mixeur), ce qui permet de le figer, l'accélérer ou de
 * le déplacer à la volée depuis la barre de lecture.
 */
export const FatalityViewer = forwardRef<FatalityViewerHandle, FatalityViewerProps>(function FatalityViewer(
  { characterUrl, fxUrl, clip, height, playing, loop, speed, showFx, className, onProgress, onEnded, onReady, createLoader, createRenderer },
  ref,
) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // Tout ce que la boucle de rendu lit à chaque image, hors du cycle React.
  const state = useRef({
    time: 0,
    playing,
    loop,
    speed,
    showFx,
    clip,
    duration: 0,
    character: null as Playable | null,
    fx: null as Playable | null,
    fxRoot: null as THREE.Object3D | null,
    characterRoot: null as THREE.Object3D | null,
    characterClips: [] as THREE.AnimationClip[],
    controls: null as OrbitControls | null,
    camera: null as THREE.PerspectiveCamera | null,
    lastProgress: 0,
    dirty: true,
  });
  const callbacks = useRef({ onProgress, onEnded, onReady });
  callbacks.current = { onProgress, onEnded, onReady };

  const select = (name: string) => {
    const st = state.current;
    if (!st.characterRoot) return;
    st.character?.mixer.stopAllAction();
    const chosen = st.characterClips.filter(c => c.name === name);
    st.character = setupPlayable(st.characterRoot, chosen);
    st.duration = Math.max(st.character?.duration ?? 0, st.fx?.duration ?? 0);
    st.time = 0;
    st.dirty = true;
  };

  useImperativeHandle(ref, () => ({
    seek: (time: number) => {
      const st = state.current;
      st.time = Math.max(0, Math.min(time, st.duration));
      st.lastProgress = 0;
      st.dirty = true;
    },
    resetView: () => {
      const st = state.current;
      if (!st.camera || !st.controls) return;
      frameCamera(st.camera, st.controls, height);
      st.dirty = true;
    },
  }), [height]);

  // Réglages changés par l'écran : pris en compte à la prochaine image, sans rechargement.
  useEffect(() => {
    const st = state.current;
    st.playing = playing;
    st.loop = loop;
    st.speed = speed;
    st.showFx = showFx;
    if (st.fxRoot) st.fxRoot.visible = showFx;
    if (st.clip !== clip) { st.clip = clip; select(clip); }
    st.dirty = true;
  }, [playing, loop, speed, showFx, clip]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const st = state.current;
    let alive = true;
    let frame = 0;
    let previous = 0;
    let renderer: THREE.WebGLRenderer | null = null;
    let observer: ResizeObserver | null = null;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#111420');
    const disposables: { dispose(): void }[] = [];

    const camera = new THREE.PerspectiveCamera(FOV, 1, 0.05, 500);
    camera.up.set(0, 0, 1);
    st.camera = camera;

    scene.add(new THREE.HemisphereLight(0xcfd8ff, 0x2a2418, 1.1));
    const key = new THREE.DirectionalLight(0xfff1dc, 1.4);
    key.position.set(-3, -6, 8);
    scene.add(key);
    const rim = new THREE.DirectionalLight(0x8fb4ff, 0.6);
    rim.position.set(4, 5, 3);
    scene.add(rim);

    // Sol : un disque sombre et une grille fine, à l'échelle du personnage.
    const radius = Math.max(height, 1) * 1.6;
    const disc = new THREE.Mesh(
      new THREE.CircleGeometry(radius, 64),
      new THREE.MeshBasicMaterial({ color: 0x1a1f2c, transparent: true, opacity: 0.9, toneMapped: false }),
    );
    disc.position.z = -0.002;
    scene.add(disc);
    const grid = new THREE.PolarGridHelper(radius, 8, 6, 64, 0x3a4560, 0x2a3348);
    grid.rotation.x = Math.PI / 2;
    scene.add(grid);
    disposables.push(disc.geometry, disc.material, grid.geometry, grid.material as THREE.Material);

    const size = () => {
      const host = canvas.parentElement ?? canvas;
      return { width: Math.max(1, host.clientWidth || window.innerWidth || 1), height: Math.max(1, host.clientHeight || window.innerHeight || 1) };
    };
    const resize = () => {
      if (!renderer) return;
      const { width, height: h } = size();
      camera.aspect = width / h;
      camera.updateProjectionMatrix();
      renderer.setSize(width, h, false);
      st.dirty = true;
    };

    let firstFrame = true;
    const draw = () => {
      if (!renderer) return;
      renderer.render(scene, camera);
      st.dirty = false;
      if (firstFrame) { firstFrame = false; callbacks.current.onReady?.(); }
    };

    const tick = () => {
      frame = requestAnimationFrame(tick);
      const now = performance.now();
      const delta = previous ? Math.min((now - previous) / 1000, 0.25) : 0;
      previous = now;
      if (st.playing && st.duration > 0) {
        st.time += delta * st.speed;
        if (st.time >= st.duration) {
          if (st.loop) st.time -= st.duration;
          else { st.time = st.duration; st.playing = false; callbacks.current.onEnded?.(); }
        }
        st.dirty = true;
      }
      const moved = st.controls?.update() ?? false;
      if (!st.dirty && !moved) return;
      const playables = [st.character, st.showFx ? st.fx : null].filter((p): p is Playable => !!p);
      applyTime(playables, st.time);
      if (now - st.lastProgress >= PROGRESS_INTERVAL_MS || st.time === st.duration || st.time === 0) {
        st.lastProgress = now;
        callbacks.current.onProgress?.(st.time, st.duration);
      }
      draw();
    };
    const start = () => { if (!frame) { previous = 0; frame = requestAnimationFrame(tick); } };
    const stop = () => { if (frame) { cancelAnimationFrame(frame); frame = 0; } };
    const onVisibility = () => (document.hidden ? stop() : start());

    const convert = (root: THREE.Object3D) => {
      root.traverse(object => {
        const mesh = object as THREE.Mesh;
        if (!mesh.isMesh) return;
        mesh.frustumCulled = false;
        const source = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
        const converted = source.map(toViewerMaterial);
        for (const material of converted) {
          const map = (material as THREE.MeshBasicMaterial).map;
          if (map) { map.anisotropy = renderer?.capabilities?.getMaxAnisotropy?.() ?? 1; disposables.push(map); }
          disposables.push(material);
        }
        disposables.push(mesh.geometry);
        mesh.material = Array.isArray(mesh.material) ? converted : converted[0];
      });
    };

    const loader = createLoader ? createLoader() : new GLTFLoader();
    const load = (url: string) => new Promise<LoadedScene>((resolve, reject) => loader.load(url, resolve, undefined, reject));

    const setup = async () => {
      renderer = createRenderer
        ? createRenderer(canvas)
        : new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'high-performance' });
      renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      const controls = new OrbitControls(camera, canvas);
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;
      controls.minDistance = Math.max(height, 1) * 0.6;
      controls.maxDistance = Math.max(height, 1) * 8;
      controls.maxPolarAngle = Math.PI * 0.55;
      st.controls = controls;
      frameCamera(camera, controls, height);
      window.addEventListener('resize', resize);
      if (typeof ResizeObserver !== 'undefined') { observer = new ResizeObserver(resize); observer.observe(canvas.parentElement ?? canvas); }
      resize();

      try {
        const [character, fx] = await Promise.all([load(characterUrl), fxUrl ? load(fxUrl).catch(() => null) : Promise.resolve(null)]);
        if (!alive) return;
        convert(character.scene);
        scene.add(character.scene);
        st.characterRoot = character.scene;
        st.characterClips = character.animations;
        if (fx) {
          convert(fx.scene);
          fx.scene.visible = st.showFx;
          scene.add(fx.scene);
          st.fxRoot = fx.scene;
          st.fx = setupPlayable(fx.scene, fx.animations);
        }
        select(st.clip);
      } catch (error) {
        if (import.meta.env.DEV) console.warn('[FatalityViewer] chargement impossible', error);
        return;
      }
      if (import.meta.env.DEV) (window as Window & { __fatalityViewer?: unknown }).__fatalityViewer = { scene, state: st };
      document.addEventListener('visibilitychange', onVisibility);
      if (!document.hidden) start();
    };
    void setup();

    return () => {
      alive = false;
      stop();
      observer?.disconnect();
      window.removeEventListener('resize', resize);
      document.removeEventListener('visibilitychange', onVisibility);
      st.controls?.dispose();
      st.controls = null;
      st.character?.mixer.stopAllAction();
      st.fx?.mixer.stopAllAction();
      st.character = st.fx = null;
      st.characterRoot = st.fxRoot = null;
      st.characterClips = [];
      st.duration = 0;
      st.time = 0;
      for (const item of disposables) item.dispose();
      scene.clear();
      renderer?.dispose();
      renderer = null;
    };
    // `height` et `clip` initiaux suffisent : les changements ultérieurs passent par l'effet
    // des réglages et par `resetView`, sans reconstruire la scène.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [characterUrl, fxUrl, createLoader, createRenderer]);

  return <canvas ref={canvasRef} className={`${s.canvas} ${className ?? ''}`} data-testid="fatality-viewer" aria-hidden="true" />;
});

/** Cadrage initial : de face, légèrement en plongée, le personnage entier dans le champ. */
export function frameCamera(camera: THREE.PerspectiveCamera, controls: OrbitControls, height: number): void {
  const h = Math.max(height, 1);
  controls.target.set(0, 0, h * 0.48);
  camera.position.set(0, -h * 2.4, h * 0.8);
  camera.lookAt(controls.target);
  controls.update();
}

export default FatalityViewer;
