import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { clone as cloneSkinned } from 'three/examples/jsm/utils/SkeletonUtils.js';
import type { LoadedScene, SceneLoader } from '@/components/scene/MenuScene';
import {
  objectClipTime, spawnOpacity, stepAt, timelineDuration, timelineSounds, victimClipTime, victimOpacityAt, victimScaleAt,
  victimStepAt, type ChannelEvent, type ChannelPoint, type FatalityObject, type FatalityTimeline,
} from './timeline';
import { CameraCollider, decorColliders } from './cameraCollision';
import { SoftMaskCache, applySoftGeometry } from './softGeometry';
import { ParticleSystemView, loadParticleFile, type ParticleAtlasMeta, type ParticleFile, type ParticleSystemMeta } from './particles';
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
};

/**
 * Place du tueur : à `ATTACKER_DISTANCE` m de la victime, décalé de `ATTACKER_BEARING` depuis
 * l'avant de la victime (côté −X du jeu, à droite de la caméra), tourné vers elle. Mise en
 * scène : le client pose le tueur où il se trouvait au coup fatal. Le côté +X est pris par
 * certains effets modelés à l'écart de la victime (l'écureuil de 2024).
 */
const ATTACKER_DISTANCE = 5;
const ATTACKER_BEARING = THREE.MathUtils.degToRad(-55);
/**
 * Axe le long duquel les rayons (`CreatureChannelDirectAction`) sont modelés : l'avant des
 * modèles du jeu, −Y (`Fatality_Channel` s'étend de 0 à −8,6 m à sa pose de bind).
 */
/** Part du chemin victime → tueur dont glisse la cible du cadrage initial. */
const ATTACKER_FOCUS = 0.3;
const CHANNEL_AXIS = new THREE.Vector3(0, -1, 0);
/** Compense la division par π du Lambert de three.js : une lumière du jeu à 1 éclaire à 1. */
const LIGHT_SCALE = Math.PI;
/** Seuil de découpe des feuillages (textures opaques à trous). */
const CUTOUT_ALPHA = 0.5;
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

type Tinted = { material: THREE.Material & { opacity: number }; base: number; transparent: boolean };
type Scrolling = { texture: THREE.Texture; speed: [number, number] };
type Instance = {
  root: THREE.Object3D;
  mixer: THREE.AnimationMixer;
  clips: { action: THREE.AnimationAction; duration: number; loop: boolean; offset: number }[];
  /** Composants retardés (`DelayComponent`) ou arrêtés : fenêtre d'apparition, temps de l'objet. */
  gated: { node: THREE.Object3D; start: number; stop: number | null }[];
  start: number;
  lifeTime: number;
  fadeIn: number;
  fadeOut: number;
  tinted: Tinted[];
  scrolling: Scrolling[];
  billboards: { node: THREE.Object3D; mode: string; base: THREE.Quaternion }[];
  particles: { view: ParticleSystemView; offset: number }[];
};

type Gate = [number, number | null];
/** Début cumulé d'un nœud de gabarit : somme des retards de ses ancêtres (lui compris). */
function windowOffset(node: THREE.Object3D, root: THREE.Object3D): number {
  let offset = 0;
  for (let n: THREE.Object3D | null = node; n && n !== root.parent; n = n.parent) {
    const w = (n.userData as { window?: Gate }).window;
    if (w) offset += w[0];
  }
  return offset;
}

/**
 * Matériau d'affichage d'une primitive exportée par `tools/extract_fatalities.py`.
 *
 * Les personnages sont éclairés (Lambert, normales exportées) ; les effets sont sans
 * éclairage comme dans le jeu : additifs ou en mélange alpha sans écriture de profondeur,
 * opaques sinon.
 */
export function toViewerMaterial(source: THREE.Material, lit = true): THREE.Material {
  const src = source as THREE.MeshBasicMaterial;
  const additive = (source.userData as { blend?: string } | undefined)?.blend === 'add';
  const translucent = source.transparent || additive;
  const common = {
    name: source.name,
    map: src.map ?? null,
    // Teinte d'un géoset (couleur des cheveux, d'armure) portée par `baseColorFactor`.
    color: (source.userData as { tint?: boolean } | undefined)?.tint && src.color ? src.color.clone() : new THREE.Color(0xffffff),
    opacity: source.opacity,
    alphaTest: translucent ? 0 : source.alphaTest,
    transparent: translucent,
    side: THREE.DoubleSide,
    vertexColors: true,
    toneMapped: false,
    fog: !translucent,
  };
  // Feuillages du décor : opaques mais découpés par l'alpha de leur texture (`cutout`).
  if (!translucent && (source.userData as { cutout?: boolean } | undefined)?.cutout) common.alphaTest = CUTOUT_ALPHA;
  const material = translucent || !lit ? new THREE.MeshBasicMaterial(common) : new THREE.MeshLambertMaterial(common);
  if (translucent) material.depthWrite = false;
  if (additive) material.blending = THREE.AdditiveBlending;
  if (material.map) material.map.colorSpace = THREE.NoColorSpace;
  return material;
}

/**
 * Oriente un nœud d'effet vers la caméra selon le mode du jeu : `Z_AXIS` tourne autour de
 * l'axe Z local pour présenter sa face −Y (normale des quads de ces géométries), `BILLBOARD`
 * fait face entièrement. Le calcul se fait dans le repère du parent (miroir compris).
 */
export function faceCamera(node: THREE.Object3D, mode: string, base: THREE.Quaternion, camera: THREE.Camera): void {
  const parent = node.parent;
  if (!parent) return;
  const eye = parent.worldToLocal(camera.getWorldPosition(new THREE.Vector3()));
  const dir = eye.sub(node.position);
  if (mode === 'Z_AXIS' || mode === 'WORLD_Z') {
    const angle = Math.atan2(dir.x, -dir.y);
    node.quaternion.copy(base).premultiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), angle));
  } else if (mode === 'BILLBOARD') {
    const m = new THREE.Matrix4().lookAt(dir.normalize(), new THREE.Vector3(), new THREE.Vector3(0, 0, 1));
    // lookAt aligne +Z sur la direction ; le quad regarde −Y : on tourne de −90° autour de X.
    const q = new THREE.Quaternion().setFromRotationMatrix(m).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), -Math.PI / 2));
    node.quaternion.copy(q);
  }
}

/**
 * Scène 3D d'une fatalité, rejouée d'après sa chronologie : la victime enchaîne les
 * animations du script (vitesse, dernière pose tenue), change d'échelle et s'efface ; les
 * gabarits d'effet apparaissent à leur instant, jouent leur animation (en boucle ou non),
 * s'estompent au bout de leur vie ; les objets accrochés suivent les locators de la victime ;
 * les sons partent avec leur objet. Le temps est piloté à la main : pause, vitesse, recherche.
 */
export const FatalityViewer = forwardRef<FatalityViewerHandle, FatalityViewerProps>(function FatalityViewer(
  { characterUrl, model, attackerUrl = null, attackerModel = '', fxUrl, timeline, objects, fadeStart, fadeDuration, sceneUrl = null, environment = null, height,
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
      frameCamera(st.camera, st.controls, height, !!attackerUrl);
      st.dirty = true;
    },
  }), [height, attackerUrl]);

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
    let victim: { root: THREE.Object3D; mixer: THREE.AnimationMixer; actions: Map<string, THREE.AnimationAction>;
      durations: Map<string, number>; tinted: Tinted[]; baseScale: THREE.Vector3 } | null = null;
    const instances: Instance[] = [];
    let attacker: { root: THREE.Object3D; mixer: THREE.AnimationMixer; actions: Map<string, THREE.AnimationAction> } | null = null;
    const channels: { inst: Instance; event: ChannelEvent }[] = [];
    const sounds: { t: number; audio: HTMLAudioElement; duration: number }[] = [];

    const softMasks = new SoftMaskCache();
    disposables.push(softMasks);
    /** URL absolue d'une ressource référencée par un `.glb` (chemin relatif au `.glb`). */
    const resolveFrom = (base: string | null, uri: string) => {
      try { return new URL(uri, new URL(base ?? '', window.location.href)).href; } catch { return uri; }
    };
    const prepare = (root: THREE.Object3D, lit: boolean, tinted: Tinted[], scrolling: Scrolling[] | null, baseUrl: string | null = null) => {
      root.traverse(object => {
        const mesh = object as THREE.Mesh;
        if (!mesh.isMesh) return;
        mesh.frustumCulled = false;
        const source = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
        const converted = source.map(m => {
          const material = toViewerMaterial(m, lit);
          const soft = (m.userData as { soft?: string } | undefined)?.soft;
          if (soft && material.transparent && typeof document !== 'undefined') applySoftGeometry(material, softMasks.get(resolveFrom(baseUrl, soft)));
          return material;
        });
        const speedPair = (mesh.geometry.userData as { uvScroll?: [number, number] }).uvScroll;
        for (const material of converted) {
          const basic = material as THREE.MeshBasicMaterial;
          if (basic.map) {
            basic.map.anisotropy = renderer?.capabilities?.getMaxAnisotropy?.() ?? 1;
            if (scrolling && speedPair) {
              const texture = basic.map.clone();
              texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
              texture.needsUpdate = true;
              basic.map = texture;
              scrolling.push({ texture, speed: speedPair });
              disposables.push(texture);
            }
          }
          tinted.push({ material: material as Tinted['material'], base: material.opacity, transparent: material.transparent });
          disposables.push(material);
        }
        mesh.material = Array.isArray(mesh.material) ? converted : converted[0];
      });
    };

    const particleFiles = new Map<string, ParticleFile | null>();
    let skyNode: THREE.Object3D | null = null;
    let atlasTexture: THREE.Texture | null = null;
    const instantiate = (proto: THREE.Object3D, clips: THREE.AnimationClip[], start: number, lifeTime: number,
      fadeIn: number, fadeOut: number): Instance => {
      const root = cloneSkinned(proto);
      const mixer = new THREE.AnimationMixer(root);
      const inst: Instance = { root, mixer, clips: [], start, lifeTime, fadeIn, fadeOut, tinted: [], scrolling: [], billboards: [], particles: [], gated: [] };
      const withParticles: [THREE.Object3D, ParticleSystemMeta][] = [];
      root.traverse(node => {
        const { vot, window } = node.userData as { vot?: string; window?: Gate };
        if (window) {
          const parentOffset = node.parent ? windowOffset(node.parent, root) : 0;
          inst.gated.push({ node, start: parentOffset + window[0], stop: window[1] === null ? null : parentOffset + window[1] });
        }
        if (!vot) return;
        const info = objects[vot];
        const clip = clips.find(c => c.name === vot);
        if (clip) {
          const action = mixer.clipAction(clip, root);
          action.play();
          action.paused = true;
          inst.clips.push({ action, duration: info?.duration || clip.duration, loop: !!info?.loop, offset: windowOffset(node, root) });
        }
        if (info?.orientation && info.orientation !== 'COMMON') inst.billboards.push({ node, mode: info.orientation, base: node.quaternion.clone() });
        const system = info?.particles as ParticleSystemMeta | undefined;
        if (system && typeof system === 'object') withParticles.push([node, system]);
      });
      prepare(root, false, inst.tinted, inst.scrolling, fxUrl);
      if (atlasTexture && particleAtlas) {
        for (const [node, system] of withParticles) {
          const file = particleFiles.get(system.file);
          if (!file) continue;
          const view = new ParticleSystemView(file, system, atlasTexture, particleAtlas);
          node.add(view.group);
          inst.particles.push({ view, offset: windowOffset(node, root) });
          disposables.push(view);
        }
      }
      return inst;
    };

    // --- boucle
    let firstFrame = true;
    const draw = () => {
      if (!renderer) return;
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

    const applyTime = (t: number) => {
      if (victim && timeline) {
        const step = victimStepAt(timeline, t);
        const idle = [...victim.actions.keys()].find(name => /^idle/i.test(name));
        const active = step?.anim && victim.actions.has(step.anim) ? step.anim : idle;
        for (const [name, action] of victim.actions) {
          const on = name === active;
          action.enabled = on;
          action.setEffectiveWeight(on ? 1 : 0);
          if (!on) continue;
          const duration = victim.durations.get(name) ?? action.getClip().duration;
          action.time = step && name === step.anim ? victimClipTime(step, t, duration) : objectClipTime(t, duration, true);
        }
        victim.mixer.update(0);
        victim.root.scale.copy(victim.baseScale).multiplyScalar(victimScaleAt(timeline, t));
        const opacity = victimOpacityAt(timeline, t, fadeStart, fadeDuration);
        victim.root.visible = opacity > 0.001;
        for (const { material, base, transparent } of victim.tinted) {
          material.opacity = base * opacity;
          const want = transparent || opacity < 0.999;
          if (material.transparent !== want) { material.transparent = want; material.needsUpdate = true; }
        }
      }
      if (attacker) {
        const step = stepAt(timeline?.caster?.anims ?? [], t);
        const idle = [...attacker.actions.keys()].find(name => /^idle/i.test(name));
        const active = step?.anim && attacker.actions.has(step.anim) ? step.anim : idle;
        for (const [name, action] of attacker.actions) {
          const on = name === active;
          action.enabled = on;
          action.setEffectiveWeight(on ? 1 : 0);
          if (!on) continue;
          const duration = action.getClip().duration;
          action.time = step && name === step.anim ? victimClipTime(step, t, duration) : objectClipTime(t, duration, true);
        }
        attacker.mixer.update(0);
      }
      for (const { inst, event } of channels) stretchChannel(inst.root, event);
      for (const inst of instances) {
        const local = t - inst.start;
        const fade = st.showFx ? spawnOpacity(local, inst.lifeTime, inst.fadeIn, inst.fadeOut) : 0;
        inst.root.visible = fade > 0.001;
        if (!inst.root.visible) continue;
        for (const gate of inst.gated) gate.node.visible = local >= gate.start && (gate.stop === null || local < gate.stop);
        for (const clip of inst.clips) clip.action.time = objectClipTime(Math.max(0, local - clip.offset), clip.duration, clip.loop);
        inst.mixer.update(0);
        for (const { material, base } of inst.tinted) material.opacity = base * fade;
        for (const { texture, speed: [su, sv] } of inst.scrolling) texture.offset.set((local * su) % 1, -((local * sv) % 1));
        for (const { node, mode, base } of inst.billboards) faceCamera(node, mode, base, camera);
        for (const { view, offset } of inst.particles) view.update(Math.max(0, local - offset), fade);
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
      shown.copy(camera.position);
      if (skyNode?.parent) {
        const eye = skyNode.parent.worldToLocal(camera.position.clone());
        skyNode.position.set(eye.x, eye.y, 0);
      }
      if (!st.dirty && !moved && !settling && !instances.some(i => i.billboards.length && i.root.visible)) return;
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
      controls.maxDistance = Math.max(height, 1) * 16;
      controls.maxPolarAngle = Math.PI * 0.53;
      st.controls = controls;
      frameCamera(camera, controls, height, !!attackerUrl);
      window.addEventListener('resize', resize);
      if (typeof ResizeObserver !== 'undefined') { observer = new ResizeObserver(resize); observer.observe(canvas.parentElement ?? canvas); }
      resize();

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
          world.add(decor.scene);
          const { ground, obstacles } = decorColliders(decor.scene);
          collider.setColliders(ground, obstacles);
        }
        const tinted: Tinted[] = [];
        prepare(character.scene, true, tinted, null);
        world.add(character.scene);
        const mixer = new THREE.AnimationMixer(character.scene);
        const actions = new Map<string, THREE.AnimationAction>();
        const durations = new Map<string, number>();
        for (const clip of character.animations) {
          const action = mixer.clipAction(clip);
          action.play();
          action.paused = true;
          actions.set(clip.name, action);
          durations.set(clip.name, clip.duration);
        }
        const modelRoot = character.scene.getObjectByName(THREE.PropertyBinding.sanitizeNodeName(model)) ?? character.scene;
        victim = { root: modelRoot, mixer, actions, durations, tinted, baseScale: modelRoot.scale.clone() };
        victimAnchor = { root: character.scene, model };

        // Tueur : face à la victime, à distance ; il joue son attente (ou les animations de son script).
        if (killer) {
          prepare(killer.scene, true, [], null);
          const holder = new THREE.Group();
          holder.position.set(ATTACKER_DISTANCE * Math.sin(ATTACKER_BEARING), -ATTACKER_DISTANCE * Math.cos(ATTACKER_BEARING), 0);
          // Les modèles regardent −Y : on les tourne vers la victime (origine).
          holder.rotation.z = Math.atan2(-holder.position.x, holder.position.y);
          holder.add(killer.scene);
          world.add(holder);
          const kMixer = new THREE.AnimationMixer(killer.scene);
          const kActions = new Map<string, THREE.AnimationAction>();
          for (const clip of killer.animations) {
            const action = kMixer.clipAction(clip);
            action.play();
            action.paused = true;
            kActions.set(clip.name, action);
          }
          attacker = { root: holder, mixer: kMixer, actions: kActions };
          attackerAnchor = { root: killer.scene, model: attackerModel };
        }

        // Particules : fichiers des gabarits utilisés, puis l'atlas commun de leurs images.
        const systems = new Set<string>();
        for (const info of Object.values(objects)) {
          const system = info.particles as ParticleSystemMeta | undefined;
          if (system && typeof system === 'object') systems.add(system.file);
        }
        if (fx && systems.size && particleAtlas && assetUrl && typeof DecompressionStream !== 'undefined') {
          const [texture] = await Promise.all([
            new THREE.TextureLoader().loadAsync(assetUrl(particleAtlas.file)).catch(warnLoad),
            ...[...systems].map(file => loadParticleFile(assetUrl(file)).then(data => { particleFiles.set(file, data); }).catch(warnLoad)),
          ]);
          if (!alive) return;
          if (texture) {
            texture.flipY = false;
            texture.colorSpace = THREE.NoColorSpace;
            texture.needsUpdate = true;
            atlasTexture = texture;
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
            const holder = (item.locator && character.scene.getObjectByName(THREE.PropertyBinding.sanitizeNodeName(`${model}/${item.locator}`))) || modelRoot;
            const [x, y, z] = item.offset ?? [0, 0, 0];
            inst.root.position.set(x, y, z);
            inst.root.scale.setScalar((item.scale || 1) * (info.scale || 1));
            holder.add(inst.root);
            instances.push(inst);
          }
          if (killer && timeline.caster) {
            for (const item of timeline.caster.attached) {
              const p = proto(item.vot);
              const info = objects[item.vot];
              if (!p || !info) continue;
              const inst = instantiate(p, fx.animations, item.t, (item.until ?? Infinity) - item.t, item.fadeIn || info.fadeIn, item.fadeOut || info.fadeOut);
              const holder = (item.locator && killer.scene.getObjectByName(THREE.PropertyBinding.sanitizeNodeName(`${attackerModel}/${item.locator}`))) || killer.scene;
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
      if (import.meta.env.DEV) (window as Window & { __fatalityViewer?: unknown }).__fatalityViewer = { scene, world, state: st, instances, victim, attacker, channels };
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
      victim?.mixer.stopAllAction();
      attacker?.mixer.stopAllAction();
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
  }, [characterUrl, attackerUrl, fxUrl, sceneUrl, timeline, createLoader, createRenderer]);

  return <canvas ref={canvasRef} className={`${s.canvas} ${className ?? ''}`} data-testid="fatality-viewer" aria-hidden="true" />;
});

/**
 * Cadrage initial : face à la victime (côté −Y du jeu), légère plongée. Avec un tueur, la cible
 * glisse de `ATTACKER_FOCUS` vers lui pour que les deux tiennent dans l'image (`withAttacker`).
 */
export function frameCamera(camera: THREE.PerspectiveCamera, controls: OrbitControls, height: number, withAttacker = false): void {
  const h = Math.max(height, 1);
  // Repère de la scène (miroir X du repère du jeu).
  const shift = withAttacker ? -ATTACKER_DISTANCE * Math.sin(ATTACKER_BEARING) * ATTACKER_FOCUS : 0;
  // Les effets montent à 3-6 hauteurs de personnage et s'étalent sur ~8 m : cadre large.
  controls.target.set(shift, 0, h * FRAME_TARGET);
  camera.position.set(shift + h * FRAME_SIDE, -h * FRAME_BACK, h * FRAME_UP);
  camera.lookAt(controls.target);
  controls.update();
}

export default FatalityViewer;
