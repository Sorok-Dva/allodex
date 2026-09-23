import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import * as THREE from 'three';
import { GLTFLoader, type GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js';
import * as SkeletonUtils from 'three/examples/jsm/utils/SkeletonUtils.js';
import type { SubtitleLang } from '@/lib/cinematics';
import { loadParticleFile } from '@/components/scene/FatalityViewer/particles';
import { spawnOpacity } from '@/components/scene/FatalityViewer/timeline';
import { VotFactory, particleSystems, toViewerMaterial, updateInstance, type Tinted, type VotInstance } from '@/components/scene/vot/votInstances';
import { actorClipAt, argb, falloff, pathAt, presentAt, sampleKeys, subtitleAt, veilAt, voiceAt, type EngineScene } from './timeline';
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
/** Couleurs du jeu : 0x80 = 1. */
const GAME_UNIT = 255 / 128;
/** Compense la division par π du Lambert de three.js : une lumière du jeu à 1 éclaire à 1 (fatalités). */
const LIGHT_SCALE = Math.PI;
/** Portée des boucles sonores du décor (m), volume linéaire jusqu'à zéro. */
const SOUND_RANGE = 70;
/** Écart toléré entre un son et la chronologie avant de le recaler (s). */
const SOUND_DRIFT = 0.3;

type Actor = { id: string; holder: THREE.Object3D; model: THREE.Object3D; mixer: THREE.AnimationMixer; actions: Map<string, THREE.AnimationAction> };
type Loop = { audio: HTMLAudioElement; volume: number; position: THREE.Vector3 | null; start: number; until: number; kind: 'music' | 'ambience' | 'sfx' };

const TERRAIN_SIZE = 512;
const TERRAIN_MAX_LAYERS = 32;

/** Charge les calques du sol dans un tableau de textures (512², répétées, mipmaps). */
async function terrainMaterial(meta: { texture: string | null; tiling: number }[], glbUrl: URL,
  light: EngineScene['light']): Promise<THREE.ShaderMaterial> {
  const count = Math.max(1, Math.min(meta.length, TERRAIN_MAX_LAYERS));
  const data = new Uint8Array(TERRAIN_SIZE * TERRAIN_SIZE * 4 * count).fill(128);
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = TERRAIN_SIZE;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  await Promise.all(meta.slice(0, count).map(async (layer, k) => {
    if (!layer.texture || !ctx) return;
    try {
      const image = await new THREE.ImageLoader().loadAsync(new URL(layer.texture, glbUrl).href);
      ctx.clearRect(0, 0, TERRAIN_SIZE, TERRAIN_SIZE);
      ctx.drawImage(image, 0, 0, TERRAIN_SIZE, TERRAIN_SIZE);
      data.set(ctx.getImageData(0, 0, TERRAIN_SIZE, TERRAIN_SIZE).data, k * TERRAIN_SIZE * TERRAIN_SIZE * 4);
    } catch { /* calque illisible : gris neutre */ }
  }));
  const layers = new THREE.DataArrayTexture(data, TERRAIN_SIZE, TERRAIN_SIZE, count);
  layers.wrapS = layers.wrapT = THREE.RepeatWrapping;
  layers.minFilter = THREE.LinearMipmapLinearFilter;
  layers.magFilter = THREE.LinearFilter;
  layers.generateMipmaps = true;
  layers.colorSpace = THREE.NoColorSpace;
  layers.flipY = false;
  layers.needsUpdate = true;
  const tiling = new Array(TERRAIN_MAX_LAYERS).fill(30);
  meta.slice(0, count).forEach((layer, k) => { tiling[k] = layer.tiling || 30; });
  const dir = light.sunDirection ?? [0.5, 0.5, 0.7];
  const material = new THREE.ShaderMaterial({
    glslVersion: THREE.GLSL3,
    fog: true,
    side: THREE.DoubleSide,
    uniforms: THREE.UniformsUtils.merge([THREE.UniformsLib.fog, {
      layers: { value: null }, tiling: { value: tiling },
      ambient: { value: new THREE.Color(...argb(light.ambient, GAME_UNIT)) },
      sunColor: { value: new THREE.Color(...argb(light.diffuse, GAME_UNIT)) },
      sunDir: { value: new THREE.Vector3(dir[0], dir[1], dir[2]).normalize() },
    }]),
    vertexShader: `
      in vec3 _layers0; in vec3 _weights0; in vec3 _layers1; in vec3 _weights1;
      out vec3 vL0; out vec3 vW0; out vec3 vL1; out vec3 vW1; out vec2 vXY; out vec3 vN;
      #include <fog_pars_vertex>
      void main() {
        vL0 = _layers0; vW0 = _weights0; vL1 = _layers1; vW1 = _weights1;
        vXY = position.xy; vN = normal;
        vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
        gl_Position = projectionMatrix * mvPosition;
        #include <fog_vertex>
      }`,
    fragmentShader: `
      precision highp sampler2DArray;
      layout(location = 0) out vec4 terrainColor;
      #define gl_FragColor terrainColor
      uniform sampler2DArray layers; uniform float tiling[${TERRAIN_MAX_LAYERS}];
      uniform vec3 ambient; uniform vec3 sunColor; uniform vec3 sunDir;
      in vec3 vL0; in vec3 vW0; in vec3 vL1; in vec3 vW1; in vec2 vXY; in vec3 vN;
      #include <fog_pars_fragment>
      vec3 tap(float id, float w) {
        if (w <= 0.002) return vec3(0.0);
        int i = int(id + 0.5);
        return w * texture(layers, vec3(vXY / tiling[i], float(i))).rgb;
      }
      void main() {
        vec3 albedo = tap(vL0.x, vW0.x) + tap(vL0.y, vW0.y) + tap(vL0.z, vW0.z)
                    + tap(vL1.x, vW1.x) + tap(vL1.y, vW1.y) + tap(vL1.z, vW1.z);
        float ndl = max(dot(normalize(vN), sunDir), 0.0);
        gl_FragColor = vec4(albedo * (ambient + sunColor * ndl), 1.0);
        #include <fog_fragment>
      }`,
  });
  material.uniforms.layers.value = layers;
  material.addEventListener('dispose', () => layers.dispose());
  return material;
}

/**
 * Matériau d'un acteur : Lambert, texture × (lumière de la carte à sa place, en émission modulée
 * par la texture) + soleil de la zone par N·L — la formule d'éclairage du jeu
 * (`texture × (ambiante + soleil · N·L)`) avec les lumières ponctuelles de la carte.
 */
function actorMaterial(source: THREE.Material, light: THREE.Color | null): THREE.Material {
  const material = toViewerMaterial(source, true);
  if (material instanceof THREE.MeshLambertMaterial && light) {
    material.emissive = light;
    material.emissiveMap = material.map;
  }
  return material;
}

/**
 * Cinématique moteur recréée en 3D : décor, ciel, effets et particules, acteurs, caméra de la
 * cinématique, musique, ambiance, sons, voix et sous-titres. Le temps est une horloge propre : chaque
 * image est recalculée d'après la position, ce qui rend la recherche exacte.
 */
export const EngineCutscene = forwardRef<MediaLike, EngineCutsceneProps>(function EngineCutscene(
  { sceneUrl, subtitleLang, hidden = false, className, onClick, onLoadedMetadata, onTimeUpdate, onEnded, onPlay, onPause,
    createRenderer, fetcher = fetch },
  ref,
) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const veilRef = useRef<HTMLDivElement>(null);
  const [scene, setScene] = useState<EngineScene | null>(null);
  const [subtitle, setSubtitle] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const devHook = useRef<unknown>(null);
  const st = useRef({
    time: 0,
    playing: false,
    muted: false,
    ready: 0,
    hidden,
    dirty: true,
    seeked: false,
    lang: subtitleLang,
    voice: -1,
    audios: [] as HTMLAudioElement[],
    loops: [] as Loop[],
    lastUpdate: 0,
  });
  const callbacks = useRef({ onLoadedMetadata, onTimeUpdate, onEnded, onPlay, onPause });
  callbacks.current = { onLoadedMetadata, onTimeUpdate, onEnded, onPlay, onPause };
  const sceneRef = useRef<EngineScene | null>(null);

  const silence = () => {
    const state = st.current;
    if (state.voice >= 0) state.audios[state.voice]?.pause();
    state.voice = -1;
    for (const loop of state.loops) if (!loop.audio.paused) loop.audio.pause();
  };

  useImperativeHandle(ref, () => ({
    play: async () => {
      const state = st.current;
      if (state.playing) return;
      if (sceneRef.current && state.time >= sceneRef.current.duration) state.time = 0;
      state.playing = true;
      state.dirty = true;
      state.seeked = true;
      callbacks.current.onPlay?.();
    },
    pause: () => {
      const state = st.current;
      if (!state.playing) return;
      state.playing = false;
      silence();
      callbacks.current.onPause?.();
    },
    get paused() { return !st.current.playing; },
    get currentTime() { return st.current.time; },
    set currentTime(value: number) {
      const state = st.current;
      state.time = Math.max(0, Math.min(value, sceneRef.current?.duration ?? value));
      silence();
      state.dirty = true;
      state.seeked = true;
    },
    get duration() { return sceneRef.current?.duration ?? NaN; },
    get readyState() { return st.current.ready; },
    get muted() { return st.current.muted; },
    set muted(value: boolean) {
      st.current.muted = value;
      if (value) silence();
    },
  }), []);

  useEffect(() => {
    const state = st.current;
    state.hidden = hidden;
    state.lang = subtitleLang;
    state.dirty = true;
    if (hidden) silence();
    if (import.meta.env.DEV && !hidden && devHook.current) (window as Window & { __engineCutscene?: unknown }).__engineCutscene = devHook.current;
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
    const view = new THREE.Scene();
    // Repère du jeu (main gauche, Z en haut) sous un miroir unique, comme les fatalités.
    const world = new THREE.Group();
    view.add(world);
    const camera = new THREE.PerspectiveCamera(45, 16 / 9, 0.5, 4000);
    camera.up.set(0, 0, 1);
    const actors: Actor[] = [];
    const decorInstances: VotInstance[] = [];
    const spawns: { inst: VotInstance; until: number }[] = [];
    const disposables: { dispose(): void }[] = [];
    const factory = new VotFactory({ objects: {}, baseUrl: base, disposables, anisotropy: () => renderer?.capabilities?.getMaxAnisotropy?.() ?? 1 });
    let data: EngineScene | null = null;
    let sky: THREE.Object3D | null = null;
    const target = new THREE.Vector3();
    const scratch = new THREE.Vector3();

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
    const gamePoint = (p: readonly number[], out: THREE.Vector3) => world.localToWorld(out.set(p[0], p[1], p[2]));

    const syncAudio = () => {
      if (!data) return;
      const active = state.playing && !state.muted && !state.hidden;
      const want = active ? voiceAt(data.lines, state.time) : null;
      if (!want) { if (state.voice >= 0) { state.audios[state.voice]?.pause(); state.voice = -1; } }
      else if (want.index !== state.voice) {
        if (state.voice >= 0) state.audios[state.voice]?.pause();
        const audio = state.audios[want.index];
        if (audio) {
          audio.currentTime = want.offset;
          audio.volume = data.sounds.volume?.voice ?? 1;
          void audio.play()?.catch?.(() => {});
          state.voice = want.index;
        }
      }
      camera.getWorldPosition(scratch);
      for (const loop of state.loops) {
        const local = state.time - loop.start;
        const inside = active && local >= 0 && state.time < loop.until;
        let volume = loop.volume;
        if (loop.position) volume *= falloff(loop.position.distanceTo(scratch), SOUND_RANGE);
        if (!inside || volume <= 0.001) { if (!loop.audio.paused) loop.audio.pause(); continue; }
        loop.audio.volume = Math.min(1, volume);
        const length = loop.audio.duration || Infinity;
        const at = loop.audio.loop && Number.isFinite(length) ? local % length : local;
        if (!loop.audio.loop && at >= length) { if (!loop.audio.paused) loop.audio.pause(); continue; }
        if (loop.audio.paused || state.seeked || Math.abs(loop.audio.currentTime - at) > SOUND_DRIFT && !loop.audio.loop) {
          try { loop.audio.currentTime = at; } catch { /* pas encore chargé */ }
          if (loop.audio.paused) void loop.audio.play()?.catch?.(() => {});
        }
      }
    };

    const apply = () => {
      if (!data) return;
      const t = state.time;
      gamePoint(sampleKeys(data.camera.points, t), camera.position);
      gamePoint(sampleKeys(data.camera.targets, t), target);
      if (camera.position.distanceToSquared(target) > 1e-6) camera.lookAt(target);
      if (sky) { const eye = world.worldToLocal(camera.position.clone()); sky.position.set(eye.x, eye.y, 0); }
      for (const actor of actors) {
        const info = data.actors.find(a => a.id === actor.id);
        if (!info) continue;
        actor.holder.visible = presentAt(info, t);
        const pose = pathAt(info.path, t);
        actor.holder.position.set(...pose.p);
        actor.holder.rotation.z = pose.yaw;
        const talk = actorClipAt(info, data.lines, t);
        const clip = pose.moving && info.move && actor.actions.has(info.move) ? { clip: info.move, time: t } : talk;
        const action = actor.actions.get(clip.clip) ?? actor.actions.get(info.idle);
        if (!action) continue;
        for (const other of actor.actions.values()) other.enabled = other === action;
        const length = action.getClip().duration || 1;
        action.play();
        action.time = clip.clip === info.idle || clip.clip === info.move ? clip.time % length : Math.min(clip.time, length - 1e-4);
        actor.mixer.update(0);
      }
      actors.forEach(a => a.holder.updateMatrixWorld(true));
      for (const inst of decorInstances) updateInstance(inst, t, 1, camera);
      for (const { inst } of spawns) updateInstance(inst, t - inst.start, spawnOpacity(t - inst.start, inst.lifeTime, inst.fadeIn, inst.fadeOut), camera);
      if (veilRef.current) veilRef.current.style.opacity = String(veilAt(data.post ?? [], t));
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
          silence();
          callbacks.current.onTimeUpdate?.(state.time);
          callbacks.current.onEnded?.();
        }
        state.dirty = true;
        if (now - state.lastUpdate >= TIME_UPDATE_MS) {
          state.lastUpdate = now;
          callbacks.current.onTimeUpdate?.(state.time);
        }
      }
      if (!renderer || state.hidden) { syncAudio(); state.seeked = false; return; }
      if (state.dirty) {
        apply();
        renderer.render(view, camera);
        state.dirty = false;
      }
      syncAudio();
      state.seeked = false;
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
      // Désaturation d'un changement de temps (vision, souvenir) : filtre de l'image entière.
      if (data.light.desaturation) canvas.style.filter = `saturate(${Math.max(0, 1 - data.light.desaturation)})`;
      if (data.mirror) world.scale.set(-1, 1, 1);
      const light = data.light;
      const fog = new THREE.Color(...argb(light.fog));
      view.background = fog;
      if (light.fogEnd) view.fog = new THREE.Fog(fog, light.fogStart ?? 0, light.fogEnd);
      // Soleil de la zone (DiffuseColor, direction SunLightYaw/Pitch) : seul éclairage dynamique ;
      // l'ambiante et les lumières ponctuelles sont dans les couleurs du décor et l'émission des acteurs.
      const sun = new THREE.DirectionalLight(new THREE.Color(...argb(light.diffuse, GAME_UNIT)), LIGHT_SCALE);
      const dir = light.sunDirection ?? [0.5, 0.5, 0.7];
      gamePoint(dir, sun.position);
      view.add(sun);

      const volume = data.sounds.volume ?? {};
      const audioFile = (file: string) => {
        const audio = new Audio();
        const ogg = typeof audio.canPlayType === 'function' && audio.canPlayType('audio/ogg');
        audio.src = `${base}${file}.${ogg ? 'ogg' : 'mp3'}`;
        audio.preload = 'auto';
        return audio;
      };
      state.audios = data.lines.map(line => {
        const audio = new Audio();
        if (line.voice) {
          const ogg = typeof audio.canPlayType === 'function' && audio.canPlayType('audio/ogg; codecs="opus"');
          audio.src = base + (ogg ? line.voice.ogg : line.voice.mp3);
          audio.preload = 'auto';
        }
        return audio;
      });
      for (const kind of ['music', 'ambience'] as const) {
        for (const entry of data.sounds[kind] ?? []) {
          const item = typeof entry === 'string' ? { file: entry, t: 0, until: Infinity } : entry;
          const audio = audioFile(item.file);
          audio.loop = true;
          state.loops.push({ audio, volume: volume[kind] ?? (kind === 'music' ? 0.4 : 0.5), position: null, start: item.t, until: item.until, kind });
        }
      }

      renderer = createRenderer
        ? createRenderer(canvas)
        : new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'high-performance' });
      renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      window.addEventListener('resize', resize);
      if (typeof ResizeObserver !== 'undefined') { observer = new ResizeObserver(resize); observer.observe(canvas.parentElement ?? canvas); }
      resize();

      const loader = new GLTFLoader();
      const load = (url: string | null) => (url ? loader.loadAsync(base + url).catch(error => {
        if (import.meta.env.DEV) console.warn('[EngineCutscene] modèle illisible', url, error);
        return null;
      }) : Promise.resolve(null));
      factory.objects = data.objects;
      const systems = particleSystems(data.objects);
      const [decor, fxGlb, skyGlb, terrainGlb, lightBin, atlas, ...rest] = await Promise.all([
        load(data.decor.glb),
        load(data.fx.glb),
        load(data.decor.skyGlb ?? null),
        load(data.decor.terrainGlb ?? null),
        fetcher(base + data.decor.light).then(r => (r.ok ? r.arrayBuffer() : null)).catch(() => null),
        data.particleAtlas && systems.size && typeof DecompressionStream !== 'undefined'
          ? new THREE.TextureLoader().loadAsync(base + data.particleAtlas.file).catch(() => null) : Promise.resolve(null),
        ...[...systems].map(file => loadParticleFile(base + file).then(parsed => { factory.particleFiles.set(file, parsed); }).catch(() => null)),
        ...data.actors.map(a => load(a.glb)),
      ]);
      if (!alive) return;
      if (atlas) {
        atlas.flipY = false;
        atlas.colorSpace = THREE.NoColorSpace;
        atlas.needsUpdate = true;
        factory.atlasTexture = atlas;
        factory.particleAtlas = data.particleAtlas;
        disposables.push(atlas);
      }
      const actorGltfs = rest.slice(systems.size) as (GLTF | null)[];
      const prototypes = new Map<string, THREE.Object3D>();
      const clips: THREE.AnimationClip[] = [];
      for (const gltf of [decor, fxGlb]) {
        if (!gltf) continue;
        gltf.scene.traverse(node => { const vot = (node.userData as { vot?: string }).vot; if (vot && !prototypes.has(vot)) prototypes.set(vot, node); });
        clips.push(...gltf.animations);
      }
      // Ciel : dôme qui suit la caméra, derrière tout, hors brouillard.
      const skyProto = skyGlb?.scene.getObjectByName('sky') ?? decor?.scene.getObjectByName('sky');
      if (skyProto) {
        const tinted: Tinted[] = [];
        factory.prepare(skyProto, false, tinted, null);
        skyProto.traverse(child => {
          const mesh = child as THREE.Mesh;
          if (!mesh.isMesh) return;
          mesh.renderOrder = -10;
          for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
            material.depthWrite = false;
            (material as THREE.MeshBasicMaterial).fog = false;
          }
        });
        world.add(skyProto);
        sky = skyProto;
      }
      // Sol : calques du terrain mélangés par sommet (poids du SplatMap, deux passes de trois calques),
      // éclairés comme les acteurs : texture × (ambiante de la zone + soleil · N·L), brouillard.
      if (terrainGlb && data.decor.terrainGlb) {
        const terrainUrl = new URL(base + data.decor.terrainGlb, window.location.href);
        const terrainNode = terrainGlb.scene.getObjectByName('terrain');
        const meta = (terrainNode?.userData as { terrainLayers?: { texture: string | null; tiling: number }[] })?.terrainLayers ?? [];
        const material = await terrainMaterial(meta, terrainUrl, data.light);
        if (!alive) return;
        disposables.push(material);
        terrainGlb.scene.traverse(node => {
          const mesh = node as THREE.Mesh;
          if (!mesh.isMesh) return;
          mesh.material = material;
          mesh.frustumCulled = false;
        });
        world.add(terrainGlb.scene);
      }
      const baked = lightBin ? new Uint8Array(lightBin) : null;
      const soundAt = (vot: string, p: THREE.Vector3 | null, start: number, until: number) => {
        const sfx = data?.objects[vot]?.sfx;
        if (!sfx) return;
        const audio = audioFile(sfx);
        audio.loop = until === Infinity || !!data?.objects[vot]?.loop;
        state.loops.push({ audio, volume: volume.sfx ?? 0.8, position: p, start, until, kind: 'sfx' });
      };
      for (const item of data.decor.instances) {
        const proto = prototypes.get(item.vot);
        const info = data.objects[item.vot];
        if (!proto || !info) continue;
        const inst = factory.instantiate(proto, clips, 0, Infinity, 0, 0);
        inst.root.position.set(...item.p);
        inst.root.rotation.set(item.tilt?.[0] ?? 0, item.tilt?.[1] ?? 0, item.yaw, 'ZYX');
        inst.root.scale.setScalar((item.scale || 1) * (info.scale || 1));
        // Éclairage précalculé de l'instance (octets à moitié : le matériau double) sur son maillage
        // propre ; les autres maillages opaques (composants) prennent l'ambiante.
        const own = inst.root.children.find(c => c.name === `${item.vot}_mesh`) as THREE.Mesh | undefined;
        inst.root.traverse(node => {
          const mesh = node as THREE.Mesh;
          if (!mesh.isMesh) return;
          const material = mesh.material as THREE.MeshBasicMaterial;
          if (material.transparent || material.blending === THREE.AdditiveBlending) return;
          // Décor opaque rendu d'une seule face, comme le jeu : une caméra de cinématique posée dans
          // un rocher du décor (cristaux du portail de Ferris) ou sous une plateforme voit au travers.
          if (data!.decor.oneSided) material.side = THREE.FrontSide;
          if (mesh === own && item.light && baked) {
            const [offset, count] = item.light;
            const geometry = mesh.geometry.clone();
            geometry.setAttribute('color', new THREE.BufferAttribute(baked.slice(offset * 4, (offset + count) * 4), 4, true));
            mesh.geometry = geometry;
            disposables.push(geometry);
            material.color.setScalar(2);
          } else {
            const [r, g, b] = item.ambient ?? argb(data!.light.ambient, GAME_UNIT);
            material.color.setRGB(r, g, b);
          }
        });
        world.add(inst.root);
        decorInstances.push(inst);
        soundAt(item.vot, world.localToWorld(new THREE.Vector3(...item.p)), 0, Infinity);
      }
      data.actors.forEach((info, i) => {
        const gltf = actorGltfs[i];
        if (!gltf) return;
        const model = SkeletonUtils.clone(gltf.scene);
        const glow = info.light ? new THREE.Color(...info.light) : null;
        model.traverse(node => {
          const mesh = node as THREE.Mesh;
          if (!mesh.isMesh) return;
          mesh.frustumCulled = false;
          const list = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
          const converted = list.map(m => actorMaterial(m, glow));
          disposables.push(...converted);
          mesh.material = Array.isArray(mesh.material) ? converted : converted[0];
        });
        const holder = new THREE.Group();
        holder.scale.setScalar(info.scale || 1);
        holder.add(model);
        world.add(holder);
        const mixer = new THREE.AnimationMixer(model);
        const actions = new Map(gltf.animations.map(clip => [clip.name, mixer.clipAction(clip)]));
        actors.push({ id: info.id, holder, model, mixer, actions });
      });
      for (const spawn of data.fx.spawns) {
        const proto = prototypes.get(spawn.vot);
        const info = data.objects[spawn.vot];
        if (!proto || !info) continue;
        const inst = factory.instantiate(proto, clips, spawn.t, spawn.until - spawn.t, info.fadeIn, info.fadeOut);
        const holder = spawn.attach ? actors.find(a => a.id === spawn.attach)?.holder : null;
        if (spawn.p) inst.root.position.set(...spawn.p);
        inst.root.rotation.z = spawn.yaw ?? 0;
        inst.root.scale.setScalar((spawn.scale || 1) * (info.scale || 1));
        (holder ?? world).add(inst.root);
        spawns.push({ inst, until: spawn.until });
        soundAt(spawn.vot, spawn.p ? world.localToWorld(new THREE.Vector3(...spawn.p)) : null, spawn.t, spawn.until);
      }
      state.ready = 4;
      state.dirty = true;
      setLoading(false);
      // Accès de débogage (captures sans écran) : celui du lecteur visible, pas du préchargé.
      devHook.current = { THREE, view, world, camera, state, actors, renderer, decorInstances, spawns };
      if (import.meta.env.DEV && !state.hidden) (window as Window & { __engineCutscene?: unknown }).__engineCutscene = devHook.current;
      frame = requestAnimationFrame(tick);
    };
    void setup();

    return () => {
      alive = false;
      if (frame) cancelAnimationFrame(frame);
      observer?.disconnect();
      window.removeEventListener('resize', resize);
      silence();
      for (const audio of [...state.audios, ...state.loops.map(l => l.audio)]) audio.removeAttribute('src');
      state.audios = [];
      state.loops = [];
      for (const actor of actors) actor.mixer.stopAllAction();
      for (const inst of [...decorInstances, ...spawns.map(x => x.inst)]) inst.mixer.stopAllAction();
      for (const d of disposables) d.dispose();
      view.traverse(object => { const mesh = object as THREE.Mesh; if (mesh.isMesh) mesh.geometry.dispose(); });
      renderer?.dispose();
      sceneRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sceneUrl]);

  return (
    <div className={`${s.cutscene} ${className ?? ''}`} onClick={onClick} data-testid="engine-cutscene" data-loading={loading ? 'true' : 'false'}>
      <canvas ref={canvasRef} className={s.canvas} />
      <div ref={veilRef} className={s.veil} aria-hidden="true" />
      {scene && loading && <div className={s.loading} aria-hidden="true" />}
      {subtitle && !hidden && <p className={s.subtitle}>{subtitle}</p>}
    </div>
  );
});
