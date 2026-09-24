import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import type { LoadedScene, SceneLoader } from '@/components/scene/MenuScene';
import {
  VotFactory, faceCamera, particleSystems, toViewerMaterial, updateInstance, type Tinted, type VotInstance,
} from '@/components/scene/vot/votInstances';
import {
  objectClipTime, shakeOffsetAt, spawnOpacity, stepAt, victimTintAt, timelineDuration, timelineSounds, victimClipTime, victimOpacityAt, victimScaleAt,
  victimStepAt, type ChannelEvent, type VictimStep, type ChannelPoint, type FatalityObject, type FatalityTimeline,
} from './timeline';
import { CameraCollider, decorColliders } from './cameraCollision';
import { buildTerrainExtras, type TerrainExtras } from '@/components/scene/vot/terrainExtras';
import { loadParticleFile, type ParticleAtlasMeta } from './particles';
import { bindClips, dressedBodies, tintedOf, type Body, type FatalityDress } from './dress';
import type { GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js';
import s from './FatalityViewer.module.css';

// Même parti pris que les scènes de menu : les textures du jeu sont des octets, pas des
// couleurs sRGB à linéariser (voir `MenuScene`).
THREE.ColorManagement.enabled = false;

export type FatalityViewerProps = {
  /** `.glb` du personnage (ses clips : attente et animations demandées par les fatalités). */
  characterUrl: string;
  /** Nom du modèle dans le `.glb` (`KaniaMale`) : préfixe des articulations, pour les locators. */
  model: string;
  /** `.glb` du tueur (script `casterFxScript` : effets, rayon vers la victime), ou `null`. */
  attackerUrl?: string | null;
  /** Nom du modèle du tueur dans son `.glb` (préfixe de ses articulations). */
  attackerModel?: string;
  /** Habit de la victime (modèle de la création de personnage, tenue de classe) ; sinon le `.glb`. */
  victimDress?: FatalityDress | null;
  /** Habit du tueur. */
  attackerDress?: FatalityDress | null;
  /** `.glb` des gabarits d'objets de la fatalité (nœuds `vot:<nom>`), ou `null`. */
  fxUrl: string | null;
  /** Chronologie de la fatalité pour ce personnage (`tools/extract_fatalities.py`). */
  timeline: FatalityTimeline | null;
  objects: Record<string, FatalityObject>;
  fadeStart: number;
  fadeDuration: number;
  /** `.glb` du décor (terrain et ornements), posé sous la victime ; `null` sans décor. */
  sceneUrl?: string | null;
  /** Réglages du décor : couleur du ciel, brouillard, lumières (`fatalities.json`). */
  environment?: FatalityEnvironment | null;
  /**
   * Distance d'orbite maximale (m) : rayon dégagé du décor moins la couronne des arbres
   * (`scene.site.orbit`), pour que la caméra ne traverse aucun objet ; `null` : pas de borne.
   */
  orbitMax?: number | null;
  /** Hauteur du personnage en unités du jeu : cadre la caméra. */
  height: number;
  playing: boolean;
  loop: boolean;
  speed: number;
  showFx: boolean;
  /** URL d'un son de fatalité (`sfx/FatalityBard`) ; `null` coupe les sons. */
  soundUrl?: ((file: string) => string) | null;
  /** URL d'un fichier de l'export (particules, atlas des particules). */
  assetUrl?: (file: string) => string;
  /** Atlas des images de particules (`fatalities.json` → `particleAtlas`). */
  particleAtlas?: ParticleAtlasMeta | null;
  volume?: number;
  className?: string;
  onProgress?: (time: number, duration: number) => void;
  onEnded?: () => void;
  onReady?: () => void;
  /** Seams de test : loader et renderer injectables (jsdom n'a ni réseau ni WebGL). */
  createLoader?: () => SceneLoader;
  createRenderer?: (canvas: HTMLCanvasElement) => THREE.WebGLRenderer;
};

/** Lumière d'une zone du jeu (`ZoneLights`), couleurs déjà ramenées à 1 = 0x80. */
export type FatalityEnvironment = {
  ambient?: [number, number, number];
  ambientFactor?: number;
  sun?: [number, number, number];
  /** Direction d'où vient le soleil, repère du jeu. */
  sunDirection?: [number, number, number];
  fog?: { color: [number, number, number]; near: number; far: number } | null;
  /** Eau de la zone (ARGB) : `SpecularWaterColor`, `WaterGradientStart`, `WaterGradientEnd`. */
  waterSpecular?: number;
  waterGradientStart?: number;
  waterGradientEnd?: number;
};

/**
 * Place du tueur : à `ATTACKER_DISTANCE` m de la victime, décalé de `ATTACKER_BEARING` depuis
 * l'avant de la victime (côté −X du jeu, à droite de la caméra), tourné vers elle. Mise en
 * scène validée : le client pose le tueur où il se trouvait au coup fatal, à distance de sort
 * (15 à 20 m). Le côté +X est pris par certains effets modelés à l'écart de la victime
 * (l'écureuil de 2024).
 */
export const ATTACKER_DISTANCE = 17;
const ATTACKER_BEARING = THREE.MathUtils.degToRad(-55);
/**
 * Axe le long duquel les rayons (`CreatureChannelDirectAction`) sont modelés : l'avant des
 * modèles du jeu, −Y (`Fatality_Channel` s'étend de 0 à −8,6 m à sa pose de bind).
 */
const CHANNEL_AXIS = new THREE.Vector3(0, -1, 0);
/**
 * Marge du cadrage autour de l'étendue des effets (fraction de la distance ajustée). Le client ne
 * décrit aucune caméra de fatalité (la caméra reste celle du joueur, seules des secousses s'y
 * ajoutent) : le lecteur cadre la victime et ses effets.
 */
const EFFECT_FRAME_MARGIN = 1.1;
/** Compense la division par π du Lambert de three.js : une lumière du jeu à 1 éclaire à 1. */
const LIGHT_SCALE = Math.PI;
/** Couleur de fond sans décor (et sous le ciel tant qu'il charge). */
const EMPTY_BACKGROUND = '#111420';

/** Commandes que l'écran envoie au lecteur sans passer par un rendu React. */
export type FatalityViewerHandle = {
  seek: (time: number) => void;
  resetView: () => void;
};

/** Champ de vision vertical de la caméra, en degrés. */
const FOV = 38;
/** Cadrage initial, en hauteurs de personnage : cible, recul (côté −Y), décalage latéral, hauteur. */
const FRAME_TARGET = 1.1;
const FRAME_BACK = 6.2;
const FRAME_SIDE = 1.6;
const FRAME_UP = 1.9;
/** Intervalle minimal entre deux `onProgress`, en millisecondes. */
const PROGRESS_INTERVAL_MS = 80;
/** Écart toléré entre la position d'un son et la chronologie avant de le recaler, en secondes. */
const SOUND_DRIFT = 0.25;

export { faceCamera, toViewerMaterial };

/**
 * Scène 3D d'une fatalité, rejouée d'après sa chronologie : la victime enchaîne les
 * animations du script (vitesse, dernière pose tenue), change d'échelle et s'efface ; les
 * gabarits d'effet apparaissent à leur instant, jouent leur animation (en boucle ou non),
 * s'estompent au bout de leur vie ; les objets accrochés suivent les locators de la victime ;
 * les sons partent avec leur objet. Le temps est piloté à la main : pause, vitesse, recherche.
 */
export const FatalityViewer = forwardRef<FatalityViewerHandle, FatalityViewerProps>(function FatalityViewer(
  { characterUrl, model, attackerUrl = null, attackerModel = '', victimDress = null, attackerDress = null, fxUrl, timeline, objects, fadeStart, fadeDuration, sceneUrl = null, environment = null, orbitMax = null, height,
    playing, loop, speed, showFx, soundUrl = null, assetUrl, particleAtlas = null, volume = 1, className, onProgress, onEnded, onReady, createLoader, createRenderer },
  ref,
) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const state = useRef({
    time: 0,
    playing,
    loop,
    speed,
    showFx,
    volume,
    duration: 0,
    controls: null as OrbitControls | null,
    camera: null as THREE.PerspectiveCamera | null,
    lastProgress: 0,
    dirty: true,
    seeked: false,
  });
  const callbacks = useRef({ onProgress, onEnded, onReady });
  callbacks.current = { onProgress, onEnded, onReady };
  const bounds = useMemo(() => effectBounds(timeline, objects, height), [timeline, objects, height]);

  useImperativeHandle(ref, () => ({
    seek: (time: number) => {
      const st = state.current;
      st.time = Math.max(0, Math.min(time, st.duration));
      st.lastProgress = 0;
      st.dirty = true;
      st.seeked = true;
    },
    resetView: () => {
      const st = state.current;
      if (!st.camera || !st.controls) return;
      frameCamera(st.camera, st.controls, height, bounds, st.camera.aspect, orbitMax);
      st.dirty = true;
    },
  }), [height, bounds, orbitMax]);

  useEffect(() => {
    const st = state.current;
    st.playing = playing;
    st.loop = loop;
    st.speed = speed;
    st.showFx = showFx;
    st.volume = volume;
    st.dirty = true;
  }, [playing, loop, speed, showFx, volume]);

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
    const fogColor = environment?.fog ? new THREE.Color(...environment.fog.color) : null;
    scene.background = fogColor ?? new THREE.Color(EMPTY_BACKGROUND);
    if (environment?.fog && fogColor) scene.fog = new THREE.Fog(fogColor, environment.fog.near, environment.fog.far);
    const disposables: { dispose(): void }[] = [];

    const camera = new THREE.PerspectiveCamera(FOV, 1, 0.05, 2000);
    camera.up.set(0, 0, 1);
    st.camera = camera;
    // Collision caméra ↔ décor : `orbit` garde la position voulue par OrbitControls,
    // `shown` celle rendue après correction (sol, obstacles).
    const collider = new CameraCollider();
    const orbit = new THREE.Vector3();
    const shown = new THREE.Vector3(Number.NaN, 0, 0);

    // Lumières : celles de la zone quand un décor est posé, sinon un éclairage neutre. Le jeu
    // éclaire en `texture × (ambiante + soleil · N·L)`, couleurs à 1 = 0x80 ; le Lambert de
    // three.js divise par π (BRDF physique) : on le compense (`LIGHT_SCALE`).
    const ambientColor = environment?.ambient ? new THREE.Color(...environment.ambient) : new THREE.Color(0xb8c2dc);
    scene.add(new THREE.AmbientLight(ambientColor, LIGHT_SCALE));
    const sun = new THREE.DirectionalLight(environment?.sun ? new THREE.Color(...environment.sun) : new THREE.Color(0xfff1dc),
      environment?.sun ? LIGHT_SCALE : LIGHT_SCALE * 0.6);
    const dir = environment?.sunDirection ?? [-0.3, -0.6, 0.8];
    sun.position.set(-dir[0], dir[1], dir[2]);
    scene.add(sun);

    // Repère du jeu (main gauche, Z en haut) sous un miroir unique : tous les `.glb` y sont
    // exprimés, les décalages des scripts aussi.
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

    // --- victime
    let victim: Body[] = [];
    const instances: VotInstance[] = [];
    let attacker: { root: THREE.Object3D; bodies: Body[] } | null = null;
    const channels: { inst: VotInstance; event: ChannelEvent }[] = [];
    const sounds: { t: number; audio: HTMLAudioElement; duration: number }[] = [];

    const factory = new VotFactory({ objects, baseUrl: fxUrl, disposables, anisotropy: () => renderer?.capabilities?.getMaxAnisotropy?.() ?? 1, lifetimes: true });
    const prepare = (root: THREE.Object3D, lit: boolean, tinted: Tinted[], scrolling: null) => factory.prepare(root, lit, tinted, scrolling);
    let skyNode: THREE.Object3D | null = null;
    // Herbe et eau : horloge propre (le vent ne repart pas à chaque boucle de la fatalité).
    let terrainExtras: TerrainExtras | null = null;
    let extrasClock = 0;
    const instantiate = (proto: THREE.Object3D, clips: THREE.AnimationClip[], start: number, lifeTime: number,
      fadeIn: number, fadeOut: number): VotInstance => factory.instantiate(proto, clips, start, lifeTime, fadeIn, fadeOut);

    // --- boucle
    let firstFrame = true;
    const draw = () => {
      if (!renderer) return;
      terrainExtras?.update(renderer, scene, camera, extrasClock);
      renderer.render(scene, camera);
      st.dirty = false;
      if (firstFrame) { firstFrame = false; callbacks.current.onReady?.(); }
    };

    const pointA = new THREE.Vector3();
    const pointB = new THREE.Vector3();
    /** Position (repère du jeu) d'une extrémité de rayon sur une créature. */
    const channelPoint = (who: { root: THREE.Object3D; model: string } | null, point: ChannelPoint | null | undefined, out: THREE.Vector3) => {
      if (!who) return out.set(0, 0, 0);
      const [sx, sy, sz] = point?.shift ?? [0, 0, 0];
      const node = point && point.locator !== 'Global'
        ? who.root.getObjectByName(THREE.PropertyBinding.sanitizeNodeName(`${who.model}/${point.locator}`)) : null;
      who.root.updateWorldMatrix(true, true);
      (node ?? who.root).localToWorld(out.set(sx, sy, sz));
      return world.worldToLocal(out);
    };
    let victimAnchor: { root: THREE.Object3D; model: string } | null = null;
    let attackerAnchor: { root: THREE.Object3D; model: string } | null = null;
    /** Tend un rayon du tueur à la victime : origine au départ, axe Y vers l'arrivée, étiré. */
    const stretchChannel = (root: THREE.Object3D, event: ChannelEvent) => {
      channelPoint(attackerAnchor, event.start, pointA);
      channelPoint(victimAnchor, event.end, pointB);
      const dir = pointB.sub(pointA);
      const distance = dir.length();
      if (distance < 1e-4) return;
      root.position.copy(pointA);
      root.quaternion.setFromUnitVectors(CHANNEL_AXIS, dir.divideScalar(distance));
      root.scale.set(1, event.length > 0 ? distance / event.length : 1, 1);
    };

    /** Couleurs d'origine des matériaux teints (la teinte les multiplie, sans les perdre). */
    const baseColors = new Map<THREE.Material, THREE.Color>();
    const applyTint = (body: Body, tint: ReturnType<typeof victimTintAt>) => {
      for (const { material } of body.tinted) {
        const m = material as THREE.Material & { color?: THREE.Color; emissive?: THREE.Color };
        if (!m.color) continue;
        let base = baseColors.get(m);
        if (!base) { base = m.color.clone(); baseColors.set(m, base); }
        m.color.setRGB(base.r * tint.mul[0], base.g * tint.mul[1], base.b * tint.mul[2]);
        m.emissive?.setRGB(tint.add[0], tint.add[1], tint.add[2]);
      }
    };
    const shake = new THREE.Vector3();

    const applyTime = (t: number) => {
      const pose = (body: Body, step: VictimStep | null) => {
        const idle = [...body.actions.keys()].find(name => /^idle/i.test(name));
        const active = step?.anim && body.actions.has(step.anim) ? step.anim : idle;
        for (const [name, action] of body.actions) {
          const on = name === active;
          action.enabled = on;
          action.setEffectiveWeight(on ? 1 : 0);
          if (!on) continue;
          const duration = body.durations.get(name) ?? action.getClip().duration;
          action.time = step && name === step.anim ? victimClipTime(step, t, duration) : objectClipTime(t, duration, true);
        }
        body.mixer.update(0);
      };
      if (victim.length && timeline) {
        const step = victimStepAt(timeline, t);
        const scale = victimScaleAt(timeline, t);
        const opacity = victimOpacityAt(timeline, t, fadeStart, fadeDuration);
        const tint = victimTintAt(timeline, t);
        for (const body of victim) {
          pose(body, step);
          applyTint(body, tint);
          body.modelRoot.scale.copy(body.baseScale).multiplyScalar(scale);
          body.holder.visible = opacity > 0.001;
          for (const { material, base, transparent } of body.tinted) {
            material.opacity = base * opacity;
            const want = transparent || opacity < 0.999;
            if (material.transparent !== want) { material.transparent = want; material.needsUpdate = true; }
          }
        }
      }
      if (attacker) {
        const step = stepAt(timeline?.caster?.anims ?? [], t);
        for (const body of attacker.bodies) pose(body, step);
      }
      for (const { inst, event } of channels) stretchChannel(inst.root, event);
      for (const inst of instances) {
        const local = t - inst.start;
        const fade = st.showFx ? spawnOpacity(local, inst.lifeTime, inst.fadeIn, inst.fadeOut) : 0;
        updateInstance(inst, local, fade, camera);
      }
    };

    const syncSounds = (t: number, active: boolean) => {
      for (const sound of sounds) {
        const local = t - sound.t;
        const inside = active && local >= 0 && local < sound.duration;
        sound.audio.volume = Math.max(0, Math.min(1, st.volume));
        if (!inside) { if (!sound.audio.paused) sound.audio.pause(); continue; }
        if (sound.audio.paused || st.seeked || Math.abs(sound.audio.currentTime - local) > SOUND_DRIFT) {
          try { sound.audio.currentTime = local; } catch { /* pas encore chargé */ }
          sound.audio.playbackRate = st.speed;
          if (sound.audio.paused) void sound.audio.play().catch(() => {});
        }
      }
    };

    const tick = () => {
      frame = requestAnimationFrame(tick);
      const now = performance.now();
      const delta = previous ? Math.min((now - previous) / 1000, 0.25) : 0;
      previous = now;
      if (st.playing && st.duration > 0) {
        extrasClock += delta * st.speed;
        st.time += delta * st.speed;
        if (st.time >= st.duration) {
          if (st.loop) { st.time -= st.duration; st.seeked = true; }
          else { st.time = st.duration; st.playing = false; callbacks.current.onEnded?.(); }
        }
        st.dirty = true;
      }
      // La position rendue n'est qu'une correction : OrbitControls repart de la sienne (sauf si
      // quelqu'un d'autre a déplacé la caméra entre-temps : recadrage, capture).
      if (camera.position.equals(shown)) camera.position.copy(orbit);
      const moved = st.controls?.update() ?? false;
      orbit.copy(camera.position);
      const settling = st.controls ? collider.resolve(st.controls.target, orbit, delta, camera.position) : false;
      if (!camera.position.equals(orbit) && st.controls) camera.lookAt(st.controls.target);
      // Secousses du script (`ShakeAction`) : décalage rendu seulement (repère du jeu → miroir X).
      const [sx, sy, sz] = timeline ? shakeOffsetAt(timeline, st.time, camera.position.length()) : [0, 0, 0];
      shake.set(-sx, sy, sz);
      const shaking = shake.lengthSq() > 0;
      if (shaking) camera.position.add(shake);
      shown.copy(camera.position);
      if (skyNode?.parent) {
        const eye = skyNode.parent.worldToLocal(camera.position.clone());
        skyNode.position.set(eye.x, eye.y, 0);
      }
      if (!st.dirty && !moved && !settling && !shaking && !instances.some(i => i.billboards.length && i.root.visible)) return;
      applyTime(st.time);
      syncSounds(st.time, st.playing && st.speed > 0);
      st.seeked = false;
      if (now - st.lastProgress >= PROGRESS_INTERVAL_MS || st.time === st.duration || st.time === 0) {
        st.lastProgress = now;
        callbacks.current.onProgress?.(st.time, st.duration);
      }
      draw();
    };
    const start = () => { if (!frame) { previous = 0; frame = requestAnimationFrame(tick); } };
    const stop = () => { if (frame) { cancelAnimationFrame(frame); frame = 0; } syncSounds(st.time, false); };
    const onVisibility = () => (document.hidden ? stop() : start());

    const loader = createLoader ? createLoader() : new GLTFLoader();
    const load = (url: string) => new Promise<LoadedScene>((resolve, reject) => loader.load(url, resolve, undefined, reject));
    const warnLoad = (error: unknown) => { if (import.meta.env.DEV) console.warn('[FatalityViewer] chargement impossible', error); return null; };

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
      controls.maxDistance = Math.max(Math.max(height, 1) * 16, attackerUrl ? ATTACKER_DISTANCE * 2.5 : 0);
      controls.maxPolarAngle = Math.PI * 0.53;
      st.controls = controls;
      window.addEventListener('resize', resize);
      if (typeof ResizeObserver !== 'undefined') { observer = new ResizeObserver(resize); observer.observe(canvas.parentElement ?? canvas); }
      resize();
      frameCamera(camera, controls, height, bounds, camera.aspect, orbitMax);

      try {
        const [character, fx, decor, killer] = await Promise.all([
          load(characterUrl),
          fxUrl ? load(fxUrl).catch(warnLoad) : Promise.resolve(null),
          sceneUrl ? load(sceneUrl).catch(warnLoad) : Promise.resolve(null),
          attackerUrl ? load(attackerUrl).catch(warnLoad) : Promise.resolve(null),
        ]);
        if (!alive) return;
        if (decor) {
          prepare(decor.scene, true, [], null);
          // Dôme de ciel : suit la caméra, derrière tout, hors brouillard.
          decor.scene.traverse(node => {
            if (!(node.userData as { sky?: boolean }).sky) return;
            node.traverse(child => {
              const mesh = child as THREE.Mesh;
              if (!mesh.isMesh) return;
              mesh.renderOrder = -10;
              for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
                material.depthWrite = false;
                (material as THREE.MeshBasicMaterial).fog = false;
              }
            });
          });
          const sky = decor.scene.getObjectByName('sky');
          if (sky) skyNode = sky;
          // Objets posés du site (plusieurs centaines, immobiles) : découpés par le champ de la
          // caméra, contrairement aux effets animés.
          decor.scene.getObjectByName('site')?.traverse(child => { if ((child as THREE.Mesh).isMesh) child.frustumCulled = true; });
          // Herbe et eau du sol réel (`terrainDump`), éclairées par la lumière de la zone.
          if (sceneUrl) {
            const env = environment;
            const sunDir = env?.sunDirection ?? [-0.3, -0.6, 0.8];
            terrainExtras = await buildTerrainExtras(decor.scene, new URL(sceneUrl, window.location.href), {
              ambient: env?.ambient ? new THREE.Color(...env.ambient) : ambientColor.clone(),
              sun: env?.sun ? new THREE.Color(...env.sun) : new THREE.Color(0, 0, 0),
              point: new THREE.Color(0, 0, 0), sunDir: new THREE.Vector3(...sunDir), ambientFactor: 1, lightmap: null,
              waterGradientStart: env?.waterGradientStart, waterGradientEnd: env?.waterGradientEnd, waterSpecular: env?.waterSpecular,
            });
            if (!alive) { terrainExtras?.dispose(); return; }
            if (terrainExtras) disposables.push(terrainExtras);
          }
          world.add(decor.scene);
          const { ground, obstacles } = decorColliders(decor.scene);
          collider.setColliders(ground, obstacles);
        }
        /** Corps d'un personnage : habillé (création de personnage) si possible, sinon le `.glb` des fatalités. */
        const bodiesOf = async (source: LoadedScene, name: string, dress: FatalityDress | null, holder: THREE.Object3D): Promise<Body[]> => {
          if (dress) {
            const dressed = await dressedBodies(dress, name, source.animations, url => load(url) as Promise<GLTF>, holder).catch(warnLoad);
            if (dressed) return dressed;
          }
          prepare(source.scene, true, [], null);
          holder.add(source.scene);
          const modelRoot = source.scene.getObjectByName(THREE.PropertyBinding.sanitizeNodeName(name)) ?? source.scene;
          return [{ holder: source.scene, model: source.scene, modelRoot, ...bindClips(source.scene, source.animations),
            tinted: tintedOf(source.scene), baseScale: modelRoot.scale.clone() }];
        };
        const victimHolder = new THREE.Group();
        world.add(victimHolder);
        victim = await bodiesOf(character, model, victimDress, victimHolder);
        if (!alive) return;
        victimAnchor = { root: victim[0].model, model };
        const modelRoot = victim[0].modelRoot;

        // Tueur : face à la victime, à distance ; il joue son attente (ou les animations de son script).
        if (killer) {
          const holder = new THREE.Group();
          holder.position.set(ATTACKER_DISTANCE * Math.sin(ATTACKER_BEARING), -ATTACKER_DISTANCE * Math.cos(ATTACKER_BEARING), 0);
          // Les modèles regardent −Y : on les tourne vers la victime (origine).
          holder.rotation.z = Math.atan2(-holder.position.x, holder.position.y);
          world.add(holder);
          // Posé sur le terrain réel (le décor n'est pas plat à 17 m de la victime).
          world.updateMatrixWorld(true);
          const at = holder.getWorldPosition(new THREE.Vector3());
          holder.position.z = collider.groundHeight(at.x, at.y) ?? 0;
          const bodies = await bodiesOf(killer, attackerModel, attackerDress, holder);
          if (!alive) return;
          attacker = { root: holder, bodies };
          attackerAnchor = { root: bodies[0].model, model: attackerModel };
        }

        // Particules : fichiers des gabarits utilisés, puis l'atlas commun de leurs images.
        const systems = particleSystems(objects);
        if (fx && systems.size && particleAtlas && assetUrl && typeof DecompressionStream !== 'undefined') {
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
        if (fx && timeline) {
          const prototypes = new Map<string, THREE.Object3D>();
          fx.scene.traverse(node => { const vot = (node.userData as { vot?: string }).vot; if (vot && !prototypes.has(vot)) prototypes.set(vot, node); });
          const proto = (name: string) => prototypes.get(name);
          for (const spawn of timeline.spawns) {
            const p = proto(spawn.vot);
            const info = objects[spawn.vot];
            if (!p || !info) continue;
            const inst = instantiate(p, fx.animations, spawn.t, spawn.lifeTime, info.fadeIn, info.fadeOut);
            const [x, y, z] = spawn.offset ?? [0, 0, 0];
            inst.root.position.set(x, y, z);
            const [rx, ry, rz] = spawn.rotation ?? [0, 0, 0];
            inst.root.rotation.set(rx, ry, rz, 'ZYX');
            inst.root.scale.setScalar((spawn.scale || 1) * (info.scale || 1));
            world.add(inst.root);
            instances.push(inst);
          }
          for (const item of timeline.attached) {
            const p = proto(item.vot);
            const info = objects[item.vot];
            if (!p || !info) continue;
            const until = item.until ?? Infinity;
            const inst = instantiate(p, fx.animations, item.t, until - item.t, item.fadeIn || info.fadeIn, item.fadeOut || info.fadeOut);
            const holder = (item.locator && victim[0].model.getObjectByName(THREE.PropertyBinding.sanitizeNodeName(`${model}/${item.locator}`))) || modelRoot;
            const [x, y, z] = item.offset ?? [0, 0, 0];
            inst.root.position.set(x, y, z);
            inst.root.scale.setScalar((item.scale || 1) * (info.scale || 1));
            holder.add(inst.root);
            instances.push(inst);
          }
          if (attacker && timeline.caster) {
            const killerModel = attacker.bodies[0].model;
            for (const item of timeline.caster.attached) {
              const p = proto(item.vot);
              const info = objects[item.vot];
              if (!p || !info) continue;
              const inst = instantiate(p, fx.animations, item.t, (item.until ?? Infinity) - item.t, item.fadeIn || info.fadeIn, item.fadeOut || info.fadeOut);
              const holder = (item.locator && killerModel.getObjectByName(THREE.PropertyBinding.sanitizeNodeName(`${attackerModel}/${item.locator}`))) || killerModel;
              const [x, y, z] = item.offset ?? [0, 0, 0];
              inst.root.position.set(x, y, z);
              inst.root.scale.setScalar((item.scale || 1) * (info.scale || 1));
              holder.add(inst.root);
              instances.push(inst);
            }
            for (const event of timeline.caster.channels) {
              const p = proto(event.vot);
              const info = objects[event.vot];
              if (!p || !info) continue;
              const inst = instantiate(p, fx.animations, event.t, event.until - event.t, event.fadeIn || info.fadeIn, event.fadeOut || info.fadeOut);
              world.add(inst.root);
              instances.push(inst);
              channels.push({ inst, event });
            }
          }
        }
        if (timeline && soundUrl) {
          const ogg = typeof Audio !== 'undefined' && new Audio().canPlayType?.('audio/ogg') ? 'ogg' : 'mp3';
          for (const { t, sfx } of timelineSounds(timeline, objects)) {
            const audio = new Audio(`${soundUrl(sfx)}.${ogg}`);
            audio.preload = 'auto';
            const entry = { t, audio, duration: Infinity };
            audio.addEventListener('loadedmetadata', () => { entry.duration = audio.duration || Infinity; });
            sounds.push(entry);
          }
        }
        st.duration = timeline ? timelineDuration(timeline, objects, fadeStart, fadeDuration) : Math.max(...character.animations.map(c => c.duration), 0);
        st.time = 0;
        st.dirty = true;
      } catch (error) {
        if (import.meta.env.DEV) console.warn('[FatalityViewer] chargement impossible', error);
        return;
      }
      if (import.meta.env.DEV) (window as Window & { __fatalityViewer?: unknown }).__fatalityViewer = { THREE, scene, world, state: st, instances, victim, attacker, channels, renderer, camera, terrainExtras };
      document.addEventListener('visibilitychange', onVisibility);
      if (!document.hidden) start();
    };
    void setup();

    return () => {
      alive = false;
      stop();
      for (const sound of sounds) { sound.audio.pause(); sound.audio.src = ''; }
      observer?.disconnect();
      window.removeEventListener('resize', resize);
      document.removeEventListener('visibilitychange', onVisibility);
      st.controls?.dispose();
      st.controls = null;
      for (const body of [...victim, ...(attacker?.bodies ?? [])]) body.mixer.stopAllAction();
      for (const inst of instances) inst.mixer.stopAllAction();
      st.duration = 0;
      st.time = 0;
      for (const item of disposables) item.dispose();
      scene.traverse(object => { const mesh = object as THREE.Mesh; if (mesh.isMesh) mesh.geometry.dispose(); });
      scene.clear();
      renderer?.dispose();
      renderer = null;
    };
    // La scène se reconstruit quand le personnage, la fatalité ou le décor changent ; les
    // réglages de lecture passent par l'effet précédent.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [characterUrl, attackerUrl, fxUrl, sceneUrl, timeline, createLoader, createRenderer, dressKey(victimDress), dressKey(attackerDress)]);

  return <canvas ref={canvasRef} className={`${s.canvas} ${className ?? ''}`} data-testid="fatality-viewer" aria-hidden="true" />;
});

/** Clé d'un habit : le lecteur se reconstruit quand elle change. */
function dressKey(dress: FatalityDress | null): string {
  return dress ? `${dress.template}:${dress.tier}:${dress.trio ? 3 : 1}:${dress.items.map(i => i.item).join(',')}` : '';
}

/**
 * Étendue de l'effet principal de la victime, dans le repère de la scène (miroir X du jeu).
 * L'effet principal est le gabarit posé (`CreatureIndependentFxAction`) ou accroché à la victime
 * qui porte le son de la fatalité (`FatalityBard`, `FatalityDruid`…), avec ses composants ; à
 * défaut de son, tous les gabarits de la victime. Les auras au sol et fonds (`Fatality_Back`,
 * boîte à 10 m au-dessus du sol) n'y entrent donc pas. Chaque gabarit apporte la boîte de son
 * animation dans le client (`bounds`, toutes images), à l'échelle et au décalage du script ; le
 * sous-sol est retiré (des os d'animation descendent sous le terrain, qui les cache : lianes du
 * Tribaliste jusqu'à −16 m) ; la victime debout y est toujours. `null` sans aucune boîte connue.
 */
export function effectBounds(timeline: FatalityTimeline | null, objects: Record<string, FatalityObject>, height: number): THREE.Box3 | null {
  if (!timeline) return null;
  const box = new THREE.Box3(new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, 0, Math.max(height, 1)));
  const sounded = (vot: string, depth = 0): boolean => {
    const info = objects[vot];
    return !!info && depth <= 8 && (!!info.sound || (info.components ?? []).some(c => sounded(c.vot, depth + 1)));
  };
  let found = false;
  const add = (vot: string, scale: number, offset: [number, number, number], depth: number) => {
    const info = objects[vot];
    if (!info || depth > 8) return;
    const s = scale * (depth === 0 ? info.scale || 1 : 1);
    if (info.bounds) {
      const [cx, cy, cz, ex, ey, ez] = info.bounds;
      const center = new THREE.Vector3(-(offset[0] + cx * s), offset[1] + cy * s, offset[2] + cz * s);
      const part = new THREE.Box3().setFromCenterAndSize(center, new THREE.Vector3(2 * ex * s, 2 * ey * s, 2 * ez * s));
      part.min.z = Math.max(part.min.z, 0);
      if (part.max.z > part.min.z) { box.union(part); found = true; }
    }
    for (const component of info.components ?? []) add(component.vot, s, offset, depth + 1);
  };
  const roots = [...timeline.spawns, ...timeline.attached];
  const main = roots.filter(item => sounded(item.vot));
  for (const item of main.length ? main : roots) add(item.vot, item.scale || 1, item.offset ?? [0, 0, 0], 0);
  return found ? box : null;
}

/**
 * Cadrage initial : face à la victime (côté −Y du jeu), légère plongée, centré sur la victime et
 * ses effets (`effectBounds`) à la distance qui fait tenir leur boîte dans le champ
 * (`EFFECT_FRAME_MARGIN`) ; sans boîte, cadre fixe en hauteurs de personnage. Le tueur n'entre
 * pas dans le cadrage (il peut sortir du champ) ; l'orbite reste libre.
 */
export function frameCamera(camera: THREE.PerspectiveCamera, controls: OrbitControls, height: number, bounds: THREE.Box3 | null = null,
  aspect = camera.aspect || 16 / 9, orbitMax: number | null = null): void {
  const h = Math.max(height, 1);
  const direction = new THREE.Vector3(FRAME_SIDE, -FRAME_BACK, FRAME_UP - FRAME_TARGET).normalize();
  if (!bounds) {
    controls.target.set(0, 0, h * FRAME_TARGET);
    camera.position.set(h * FRAME_SIDE, -h * FRAME_BACK, h * FRAME_UP);
  } else {
    const center = bounds.getCenter(new THREE.Vector3());
    // Repère de la caméra (regard −direction, Z en haut) : chaque coin de la boîte doit tenir dans
    // le champ vertical et horizontal, `D ≥ p·d + |p·u| / tan(½ champ)`.
    const right = new THREE.Vector3().crossVectors(new THREE.Vector3(0, 0, 1), direction).normalize();
    const up = new THREE.Vector3().crossVectors(direction, right).normalize();
    const tanV = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
    const tanH = tanV * Math.max(aspect, 0.5);
    let distance = h * 2;
    const corner = new THREE.Vector3();
    for (let i = 0; i < 8; i += 1) {
      corner.set(i & 1 ? bounds.max.x : bounds.min.x, i & 2 ? bounds.max.y : bounds.min.y, i & 4 ? bounds.max.z : bounds.min.z).sub(center);
      const depth = corner.dot(direction);
      distance = Math.max(distance, depth + Math.abs(corner.dot(right)) / tanH, depth + Math.abs(corner.dot(up)) / tanV);
    }
    distance *= EFFECT_FRAME_MARGIN;
    controls.target.copy(center);
    camera.position.copy(center).addScaledVector(direction, distance);
    controls.maxDistance = Math.max(controls.maxDistance, distance * 1.5);
  }
  if (orbitMax && orbitMax > 0) {
    controls.maxDistance = Math.min(controls.maxDistance, orbitMax);
    const offset = camera.position.clone().sub(controls.target);
    if (offset.length() > orbitMax) camera.position.copy(controls.target).addScaledVector(offset.normalize(), orbitMax);
  }
  camera.lookAt(controls.target);
  controls.update();
}

export default FatalityViewer;
