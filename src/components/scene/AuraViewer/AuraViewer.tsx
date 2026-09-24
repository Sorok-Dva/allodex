import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import type { GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js';
import type { LoadedScene, SceneLoader } from '@/components/scene/MenuScene';
import { VotFactory, particleSystems, updateInstance, type VotInstance } from '@/components/scene/vot/votInstances';
import { buildTerrainExtras, type TerrainExtras } from '@/components/scene/vot/terrainExtras';
import { CameraCollider, decorColliders } from '@/components/scene/FatalityViewer/cameraCollision';
import { loadParticleFile, type ParticleAtlasMeta } from '@/components/scene/FatalityViewer/particles';
import { bindClips, dressedBodies, tintedOf, type Body, type FatalityDress } from '@/components/scene/FatalityViewer/dress';
import { skyBehindEverything, type FatalityEnvironment } from '@/components/scene/FatalityViewer/FatalityViewer';
import { objectClipTime, type FatalityObject } from '@/components/scene/FatalityViewer/timeline';
import s from '@/components/scene/FatalityViewer/FatalityViewer.module.css';

// Mêmes conventions que les fatalités : textures en octets bruts, pas de linéarisation.
THREE.ColorManagement.enabled = false;

/** Effets d'une aura (`tools/extract_auras.py`, `aura_timeline`) : gabarits accrochés, posés. */
export type AuraAttach = { t: number; vot: string; locator: string; scale: number; offset?: [number, number, number]; fadeIn?: number };
export type AuraSpawn = { t: number; vot: string; lifeTime?: number | null; offset?: [number, number, number] | null; scale: number };
export type AuraTimeline = { attached: AuraAttach[]; spawns: AuraSpawn[]; ignored?: string[] };

/** Modèle d'une apparence (peau de monture ou d'exosquelette) : gabarit du client exporté seul. */
export type AuraAppearanceModel = { url: string; vot: string; objects: Record<string, FatalityObject> };

export type AuraViewerProps = {
  /** Avatar habillé (création de personnage) ; ignoré quand `appearance` est donné. */
  dress: FatalityDress | null;
  /** Modèle d'apparence posé à la place de l'avatar (l'aura se pose à ses pieds). */
  appearance?: AuraAppearanceModel | null;
  /** `.glb` des gabarits de l'aura, ou `null` (aura sans effet visuel dans le client). */
  fxUrl: string | null;
  objects: Record<string, FatalityObject>;
  timeline: AuraTimeline | null;
  sceneUrl?: string | null;
  environment?: FatalityEnvironment | null;
  orbitMax?: number | null;
  /** Hauteur de l'avatar (m) : cadre la caméra. */
  height: number;
  playing: boolean;
  speed: number;
  showFx: boolean;
  assetUrl?: (file: string) => string;
  particleAtlas?: ParticleAtlasMeta | null;
  /** URL d'un son d'effet (`sfx/…`), `null` coupe les sons. */
  soundUrl?: ((file: string) => string) | null;
  volume?: number;
  className?: string;
  onReady?: () => void;
  createLoader?: () => SceneLoader;
  createRenderer?: (canvas: HTMLCanvasElement) => THREE.WebGLRenderer;
};

export type AuraViewerHandle = { resetView: () => void };

const FOV = 38;
const LIGHT_SCALE = Math.PI;
const EMPTY_BACKGROUND = '#111420';
/** Animation d'attente des modèles de la création de personnage. */
const IDLE = /^idle/i;

/**
 * Scène d'une aura : l'avatar debout (ou le modèle d'une apparence) dans la clairière des
 * fatalités, l'aura du client à ses pieds, en boucle sans fin — le buff dure tant que l'aura est
 * active. Le temps court sans chronologie ni fin : vitesse, pause, effets on/off. Les gabarits
 * gardent leur vie propre (`lifetimes`) et les particules bouclent sans saut (`continuousParticles`).
 */
export const AuraViewer = forwardRef<AuraViewerHandle, AuraViewerProps>(function AuraViewer(
  { dress, appearance = null, fxUrl, objects, timeline, sceneUrl = null, environment = null, orbitMax = null, height,
    playing, speed, showFx, assetUrl, particleAtlas = null, soundUrl = null, volume = 1, className, onReady, createLoader, createRenderer },
  ref,
) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const state = useRef({ playing, speed, showFx, volume, dirty: true, controls: null as OrbitControls | null, camera: null as THREE.PerspectiveCamera | null });
  const callbacks = useRef({ onReady });
  callbacks.current = { onReady };

  useImperativeHandle(ref, () => ({
    resetView: () => {
      const st = state.current;
      if (!st.camera || !st.controls) return;
      frameAura(st.camera, st.controls, height, orbitMax);
      st.dirty = true;
    },
  }), [height, orbitMax]);

  useEffect(() => {
    const st = state.current;
    Object.assign(st, { playing, speed, showFx, volume, dirty: true });
  }, [playing, speed, showFx, volume]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const st = state.current;
    let alive = true;
    let frame = 0;
    let previous = 0;
    let time = 0;
    let renderer: THREE.WebGLRenderer | null = null;
    let observer: ResizeObserver | null = null;
    const scene = new THREE.Scene();
    const fogColor = environment?.fog ? new THREE.Color(...environment.fog.color) : null;
    scene.background = fogColor ?? new THREE.Color(EMPTY_BACKGROUND);
    if (environment?.fog && fogColor) scene.fog = new THREE.Fog(fogColor, environment.fog.near, environment.fog.far);
    const disposables: { dispose(): void }[] = [];
    const camera = new THREE.PerspectiveCamera(FOV, 1, 0.05, 2000);
    camera.up.set(0, 0, 1);
    st.camera = camera;
    const collider = new CameraCollider();
    const orbit = new THREE.Vector3();
    const shown = new THREE.Vector3(Number.NaN, 0, 0);

    const ambientColor = environment?.ambient ? new THREE.Color(...environment.ambient) : new THREE.Color(0xb8c2dc);
    scene.add(new THREE.AmbientLight(ambientColor, LIGHT_SCALE));
    const sun = new THREE.DirectionalLight(environment?.sun ? new THREE.Color(...environment.sun) : new THREE.Color(0xfff1dc),
      environment?.sun ? LIGHT_SCALE : LIGHT_SCALE * 0.6);
    const dir = environment?.sunDirection ?? [-0.3, -0.6, 0.8];
    sun.position.set(-dir[0], dir[1], dir[2]);
    scene.add(sun);
    const world = new THREE.Group();
    world.scale.set(-1, 1, 1);
    scene.add(world);

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

    let bodies: Body[] = [];
    const instances: VotInstance[] = [];
    const sounds: HTMLAudioElement[] = [];
    let skyNode: THREE.Object3D | null = null;
    let terrainExtras: TerrainExtras | null = null;
    const factory = new VotFactory({ objects, baseUrl: fxUrl, disposables, anisotropy: () => renderer?.capabilities?.getMaxAnisotropy?.() ?? 1,
      lifetimes: true, continuousParticles: true });

    let firstFrame = true;
    const applyTime = (t: number) => {
      for (const body of bodies) {
        for (const [name, action] of body.actions) {
          const on = IDLE.test(name);
          action.enabled = on;
          action.setEffectiveWeight(on ? 1 : 0);
          if (on) action.time = objectClipTime(t, body.durations.get(name) ?? action.getClip().duration, true);
        }
        body.mixer.update(0);
      }
      for (const inst of instances) {
        const local = t - inst.start;
        const fx = (inst.root.userData as { appearance?: boolean }).appearance ? true : st.showFx;
        const entry = inst.fadeIn > 0 ? Math.min(1, Math.max(0, local / inst.fadeIn)) : 1;
        updateInstance(inst, local, fx ? entry : 0, camera, fx);
      }
      for (const audio of sounds) {
        audio.volume = Math.max(0, Math.min(1, st.volume));
        const want = st.playing && st.showFx;
        if (want && audio.paused) void audio.play().catch(() => {});
        if (!want && !audio.paused) audio.pause();
        audio.playbackRate = Math.max(0.25, st.speed);
      }
    };
    const tick = () => {
      frame = requestAnimationFrame(tick);
      const now = performance.now();
      const delta = previous ? Math.min((now - previous) / 1000, 0.25) : 0;
      previous = now;
      if (st.playing) { time += delta * st.speed; st.dirty = true; }
      if (camera.position.equals(shown)) camera.position.copy(orbit);
      const moved = st.controls?.update() ?? false;
      orbit.copy(camera.position);
      const settling = st.controls ? collider.resolve(st.controls.target, orbit, delta, camera.position) : false;
      if (!camera.position.equals(orbit) && st.controls) camera.lookAt(st.controls.target);
      shown.copy(camera.position);
      if (skyNode?.parent) {
        const eye = skyNode.parent.worldToLocal(camera.position.clone());
        skyNode.position.set(eye.x, eye.y, 0);
      }
      if (!st.dirty && !moved && !settling && !instances.some(i => i.billboards.length && i.root.visible)) return;
      applyTime(time);
      if (!renderer) return;
      terrainExtras?.update(renderer, scene, camera, time);
      renderer.render(scene, camera);
      st.dirty = false;
      if (firstFrame) { firstFrame = false; callbacks.current.onReady?.(); }
    };
    const start = () => { if (!frame) { previous = 0; frame = requestAnimationFrame(tick); } };
    const stop = () => { if (frame) { cancelAnimationFrame(frame); frame = 0; } for (const a of sounds) a.pause(); };
    const onVisibility = () => (document.hidden ? stop() : start());

    const loader = createLoader ? createLoader() : new GLTFLoader();
    const load = (url: string) => new Promise<LoadedScene>((resolve, reject) => loader.load(url, resolve, undefined, reject));
    const warnLoad = (error: unknown) => { if (import.meta.env.DEV) console.warn('[AuraViewer] chargement impossible', error); return null; };

    const setup = async () => {
      renderer = createRenderer ? createRenderer(canvas) : new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'high-performance' });
      renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      const controls = new OrbitControls(camera, canvas);
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;
      controls.minDistance = Math.max(height, 1) * 0.6;
      controls.maxDistance = Math.max(height, 1) * 16;
      controls.maxPolarAngle = Math.PI * 0.53;
      st.controls = controls;
      window.addEventListener('resize', resize);
      if (typeof ResizeObserver !== 'undefined') { observer = new ResizeObserver(resize); observer.observe(canvas.parentElement ?? canvas); }
      resize();
      frameAura(camera, controls, height, orbitMax);
      try {
        const tpl = !appearance && dress ? dress.data.templates[dress.template] : null;
        const [fx, decor, model, rig] = await Promise.all([
          fxUrl ? load(fxUrl).catch(warnLoad) : Promise.resolve(null),
          sceneUrl ? load(sceneUrl).catch(warnLoad) : Promise.resolve(null),
          appearance ? load(appearance.url).catch(warnLoad) : Promise.resolve(null),
          tpl?.glb && dress ? load(`${dress.base}${tpl.glb}`).catch(warnLoad) : Promise.resolve(null),
        ]);
        if (!alive) return;
        if (decor) {
          factory.prepare(decor.scene, true, [], null);
          decor.scene.traverse(node => { if ((node.userData as { sky?: boolean }).sky) skyBehindEverything(node); });
          skyNode = decor.scene.getObjectByName('sky') ?? null;
          decor.scene.getObjectByName('site')?.traverse(child => { if ((child as THREE.Mesh).isMesh) child.frustumCulled = true; });
          if (sceneUrl) {
            const env = environment;
            terrainExtras = await buildTerrainExtras(decor.scene, new URL(sceneUrl, window.location.href), {
              ambient: env?.ambient ? new THREE.Color(...env.ambient) : ambientColor.clone(),
              sun: env?.sun ? new THREE.Color(...env.sun) : new THREE.Color(0, 0, 0),
              point: new THREE.Color(0, 0, 0), sunDir: new THREE.Vector3(...(env?.sunDirection ?? [-0.3, -0.6, 0.8])), ambientFactor: 1, lightmap: null,
              waterGradientStart: env?.waterGradientStart, waterGradientEnd: env?.waterGradientEnd, waterSpecular: env?.waterSpecular,
            });
            if (!alive) { terrainExtras?.dispose(); return; }
            if (terrainExtras) disposables.push(terrainExtras);
          }
          world.add(decor.scene);
          const { ground, obstacles } = decorColliders(decor.scene);
          collider.setColliders(ground, obstacles);
        }
        // Particules : fichiers des gabarits de l'aura (et du modèle d'apparence), puis l'atlas.
        const allObjects = { ...(appearance?.objects ?? {}), ...objects };
        factory.objects = allObjects;
        const systems = particleSystems(allObjects);
        if (systems.size && particleAtlas && assetUrl && typeof DecompressionStream !== 'undefined') {
          const [texture] = await Promise.all([
            new THREE.TextureLoader().loadAsync(assetUrl(particleAtlas.file)).catch(warnLoad),
            ...[...systems].map(file => loadParticleFile(assetUrl(file)).then(data => { factory.particleFiles.set(file, data); }).catch(warnLoad)),
          ]);
          if (!alive) return;
          if (texture) {
            texture.flipY = false;
            texture.colorSpace = THREE.NoColorSpace;
            texture.needsUpdate = true;
            factory.atlasTexture = texture;
            factory.particleAtlas = particleAtlas;
            disposables.push(texture);
          }
        }
        // Porteur de l'aura : modèle d'apparence (gabarit du client, sa propre animation) ou avatar.
        const holder = new THREE.Group();
        world.add(holder);
        let anchor: THREE.Object3D = holder;
        let prefix = '';
        if (model && appearance) {
          const proto = findVot(model.scene, appearance.vot);
          if (proto) {
            const inst = factory.instantiate(proto, model.animations, 0, Infinity, 0, 0);
            (inst.root.userData as { appearance?: boolean }).appearance = true;
            holder.add(inst.root);
            instances.push(inst);
            anchor = inst.root;
          }
        } else if (dress && rig) {
          const dressed = await dressedBodies(dress, dress.template, rig.animations.filter(c => IDLE.test(c.name)),
            url => load(url) as Promise<GLTF>, holder).catch(warnLoad);
          if (!alive) return;
          if (dressed) {
            bodies = dressed;
            anchor = dressed[0].model;
            prefix = dress.template;
          } else {
            factory.prepare(rig.scene, true, [], null);
            holder.add(rig.scene);
            bodies = [{ holder: rig.scene, model: rig.scene, modelRoot: rig.scene, ...bindClips(rig.scene, rig.animations), tinted: tintedOf(rig.scene), baseScale: rig.scene.scale.clone() }];
            anchor = rig.scene;
            prefix = dress.template;
          }
        }
        if (fx && timeline) {
          const locate = (locator: string) => (prefix && anchor.getObjectByName(THREE.PropertyBinding.sanitizeNodeName(`${prefix}/${locator}`))) || anchor;
          for (const item of timeline.attached) {
            const proto = findVot(fx.scene, item.vot);
            const info = objects[item.vot];
            if (!proto || !info) continue;
            const inst = factory.instantiate(proto, fx.animations, item.t, Infinity, item.fadeIn || info.fadeIn, 0);
            const [x, y, z] = item.offset ?? [0, 0, 0];
            inst.root.position.set(x, y, z);
            inst.root.scale.setScalar((item.scale || 1) * (info.scale || 1));
            // `Global` et `Slot_Global` : aux pieds (racine du porteur, ou son locator de sol).
            locate(item.locator).add(inst.root);
            instances.push(inst);
          }
          for (const spawn of timeline.spawns) {
            const proto = findVot(fx.scene, spawn.vot);
            const info = objects[spawn.vot];
            if (!proto || !info) continue;
            const inst = factory.instantiate(proto, fx.animations, spawn.t, Infinity, info.fadeIn, 0);
            const [x, y, z] = spawn.offset ?? [0, 0, 0];
            inst.root.position.set(x, y, z);
            inst.root.scale.setScalar((spawn.scale || 1) * (info.scale || 1));
            world.add(inst.root);
            instances.push(inst);
          }
        }
        if (soundUrl && typeof Audio !== 'undefined') {
          const ogg = new Audio().canPlayType?.('audio/ogg') ? 'ogg' : 'mp3';
          for (const info of Object.values(objects)) {
            if (!info.sfx) continue;
            const audio = new Audio(`${soundUrl(info.sfx)}.${ogg}`);
            audio.loop = true;
            audio.preload = 'auto';
            sounds.push(audio);
          }
        }
        st.dirty = true;
      } catch (error) {
        if (import.meta.env.DEV) console.warn('[AuraViewer] chargement impossible', error);
        return;
      }
      // Crochet de développement : captures pilotées dans le temps (`setTime(120)`).
      if (import.meta.env.DEV) (window as Window & { __auraViewer?: unknown }).__auraViewer = { THREE, scene, world, instances, bodies, renderer, camera, state: st,
        time: () => time, setTime: (t: number) => { time = t; st.dirty = true; } };
      document.addEventListener('visibilitychange', onVisibility);
      if (!document.hidden) start();
    };
    void setup();

    return () => {
      alive = false;
      stop();
      for (const audio of sounds) { audio.pause(); audio.src = ''; }
      observer?.disconnect();
      window.removeEventListener('resize', resize);
      document.removeEventListener('visibilitychange', onVisibility);
      st.controls?.dispose();
      st.controls = null;
      for (const body of bodies) body.mixer.stopAllAction();
      for (const inst of instances) inst.mixer.stopAllAction();
      for (const item of disposables) item.dispose();
      scene.traverse(object => { const mesh = object as THREE.Mesh; if (mesh.isMesh) mesh.geometry.dispose(); });
      scene.clear();
      renderer?.dispose();
      renderer = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fxUrl, sceneUrl, timeline, appearance?.url, createLoader, createRenderer, dressKey(dress)]);

  return <canvas ref={canvasRef} className={`${s.canvas} ${className ?? ''}`} data-testid="aura-viewer" aria-hidden="true" />;
});

/**
 * Cadrage de l'aura : de trois quarts face, en plongée (≈ 27°), visée à mi-hauteur du porteur,
 * assez loin pour voir l'aura entière au sol (rayon de 2 à 3 m pour les plus grandes). Constantes
 * du lecteur : le client n'a pas de caméra d'aperçu d'aura (la garde-robe montre l'icône seule).
 */
export const AURA_FRAME = { target: 0.5, distance: 3.4, minDistance: 6.5, side: 0.45, back: -1, up: 0.55 };

export function frameAura(camera: THREE.PerspectiveCamera, controls: OrbitControls, height: number, orbitMax: number | null = null): void {
  const h = Math.max(height, 1);
  const distance = Math.min(Math.max(h * AURA_FRAME.distance, AURA_FRAME.minDistance), orbitMax ?? Infinity);
  const dir = new THREE.Vector3(AURA_FRAME.side, AURA_FRAME.back, AURA_FRAME.up).normalize();
  controls.target.set(0, 0, h * AURA_FRAME.target);
  camera.position.copy(controls.target).addScaledVector(dir, distance);
  if (orbitMax && orbitMax > 0) controls.maxDistance = Math.min(controls.maxDistance, orbitMax);
  camera.lookAt(controls.target);
  controls.update();
}

/** Nœud `vot:<nom>` (premier trouvé) d'un `.glb` de gabarits. */
function findVot(root: THREE.Object3D, name: string): THREE.Object3D | undefined {
  let found: THREE.Object3D | undefined;
  root.traverse(node => { if (!found && (node.userData as { vot?: string }).vot === name) found = node; });
  return found;
}

function dressKey(dress: FatalityDress | null): string {
  return dress ? `${dress.template}:${dress.tier}:${dress.trio ? 3 : 1}:${dress.items.map(i => i.item).join(',')}` : '';
}

export default AuraViewer;
