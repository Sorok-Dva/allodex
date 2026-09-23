import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import * as THREE from 'three';
import { GLTFLoader, type GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js';
import type { ChargenData, Sex } from '@/data/character/chargen.types';
import { comboKey, type CharacterDescriptor, type Appearance } from '@/data/character/descriptor';
import { resolveLook } from '@/data/character/look';
import { CharacterRig, createAssetCache, type AssetCache } from './rig';
import { applyLight, placeCamera, prepareScene, updateScrollers, type Scroller } from './stage';
import { exportCharacterGlb } from './exportGlb';
import s from './ChargenViewer.module.css';

THREE.ColorManagement.enabled = false;

export type ChargenFocus = 'primary' | 'secondary' | 'tertiary' | 'pet';

export type ChargenViewerProps = {
  data: ChargenData;
  /** Racine des fichiers (`/game/character/`). */
  base: string;
  descriptor: CharacterDescriptor;
  /** `faction` : aucun personnage ; `race` : plan large ; `custom` : caméra rapprochée. */
  step: 'faction' | 'race' | 'custom';
  /** Tenue montrée (indice de `growths`) ou `null` sans tenue. */
  equipment: number | null;
  helmet: boolean;
  focus: ChargenFocus;
  className?: string;
  onReady?: () => void;
  onError?: (message: string) => void;
};

export type ChargenViewerHandle = {
  exportGlb: () => Promise<Blob>;
  resetRotation: () => void;
};

/** Décalage des compagnons du trio gibberling et du familier, en mètres (repère du personnage). */
const COMPANION_OFFSETS: Record<Exclude<ChargenFocus, 'primary'>, [number, number]> = {
  secondary: [-0.75, 0.45],
  tertiary: [0.75, 0.45],
  pet: [1.1, 0.2],
};
/** Lacet ajouté au modèle pour qu'il fasse face à la caméra de la place (le modèle regarde -Y). */
const MODEL_FACING = 0;

/** Recul de la caméra du plan large, en fraction de celle de `UICharacterScenes`. */
const RACE_CAMERA = 1;

type Slot = { key: string; rig: CharacterRig | null; loading: string | null };

export const ChargenViewer = forwardRef<ChargenViewerHandle, ChargenViewerProps>(function ChargenViewer(props, ref) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const propsRef = useRef(props);
  propsRef.current = props;
  const st = useRef({
    renderer: null as THREE.WebGLRenderer | null,
    scene: new THREE.Scene(),
    world: new THREE.Group(),
    camera: new THREE.PerspectiveCamera(45, 1, 0.05, 2000),
    cache: null as AssetCache | null,
    sceneRace: '',
    sceneRoot: null as THREE.Object3D | null,
    sceneMixer: null as THREE.AnimationMixer | null,
    scrollers: [] as Scroller[],
    lights: [] as THREE.Object3D[],
    characters: new THREE.Group(),
    slots: {} as Record<ChargenFocus, Slot>,
    yaw: 0,
    drag: null as null | { x: number; yaw: number },
    time: 0,
    frame: null as null | (() => void),
  });

  useImperativeHandle(ref, () => ({
    exportGlb: () => {
      const s0 = st.current;
      const p = propsRef.current;
      const primary = s0.slots.primary?.rig;
      if (!primary) return Promise.reject(new Error('no character'));
      const growth = p.equipment === null ? null : p.data.combos[comboKey(p.descriptor.race, p.descriptor.class)]?.sexes[p.descriptor.sex]?.growths[p.equipment];
      return exportCharacterGlb({
        primary, companions: (['secondary', 'tertiary', 'pet'] as const).map(k => s0.slots[k]?.rig ?? null),
        name: p.descriptor.name || p.descriptor.race, clips: [growth?.start ?? null, growth?.loop ?? null, 'idle'],
        descriptor: p.descriptor,
      });
    },
    resetRotation: () => { st.current.yaw = 0; },
  }), []);

  // Montage : moteur de rendu, boucle, glisser pour tourner le personnage.
  useEffect(() => {
    const canvas = canvasRef.current!;
    const s0 = st.current;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: false });
    } catch {
      propsRef.current.onError?.('webgl');
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
    s0.renderer = renderer;
    const loader = new GLTFLoader();
    s0.cache = createAssetCache(url => new Promise<GLTF>((resolve, reject) => loader.load(url, resolve, undefined, reject)), propsRef.current.base);
    s0.world.scale.set(-1, 1, 1);
    s0.world.add(s0.characters);
    s0.scene.add(s0.world);
    const resize = () => {
      const w = canvas.clientWidth || 1;
      const h = canvas.clientHeight || 1;
      renderer.setSize(w, h, false);
      const meta = propsRef.current.data.scenes?.[propsRef.current.descriptor.race];
      if (meta) placeCamera(s0.camera, cameraFor(meta.camera), w / h);
    };
    const cameraFor = (c: NonNullable<ChargenData['scenes']>[string]['camera']) => {
      const p = propsRef.current;
      // Plan large (race et classe) : la caméra de sélection du jeu (5 m) tombe derrière des
      // poutres du décor ; on l'avance sur son axe (voir le rapport, « écarts »).
      if (p.step !== 'custom') {
        const [x, y, z] = c.position;
        return { ...c, position: [x * RACE_CAMERA, y * RACE_CAMERA, z] as [number, number, number] };
      }
      // Plan rapproché de la personnalisation : même axe, caméra avancée vers le visage.
      const tpl = p.data.templates[p.data.combos[comboKey(p.descriptor.race, p.descriptor.class)]?.sexes[p.descriptor.sex]?.template ?? ''];
      const scale = (p.data.scenes?.[p.descriptor.race]?.character.scale ?? 1) * (tpl?.scale ?? 1);
      const face = (tpl?.ui?.preMissionFaceCameraAnchor?.[2] ?? tpl?.height ?? 1.8) * scale;
      const [x, y, z] = c.position;
      const k = 0.55;
      return { ...c, position: [x * k, y * k, face * 0.9 + (z - face * 0.9) * k] as [number, number, number] };
    };
    s0.frame = resize;
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    const clock = new THREE.Clock();
    let raf = 0;
    const loop = () => {
      raf = requestAnimationFrame(loop);
      const dt = Math.min(clock.getDelta(), 0.1);
      s0.time += dt;
      s0.sceneMixer?.update(dt);
      updateScrollers(s0.scrollers, s0.time);
      for (const slot of Object.values(s0.slots)) slot.rig?.update(dt);
      const primary = s0.slots.primary?.rig;
      if (primary) primary.root.rotation.z = MODEL_FACING + THREE.MathUtils.degToRad(sceneYaw()) + s0.yaw;
      renderer.render(s0.scene, s0.camera);
    };
    const sceneYaw = () => propsRef.current.data.scenes?.[propsRef.current.descriptor.race]?.character.yaw ?? 0;
    loop();
    const down = (e: PointerEvent) => { s0.drag = { x: e.clientX, yaw: s0.yaw }; canvas.setPointerCapture(e.pointerId); };
    const move = (e: PointerEvent) => { if (s0.drag) s0.yaw = s0.drag.yaw + (e.clientX - s0.drag.x) * 0.01; };
    const up = () => { s0.drag = null; };
    canvas.addEventListener('pointerdown', down);
    canvas.addEventListener('pointermove', move);
    canvas.addEventListener('pointerup', up);
    canvas.addEventListener('pointercancel', up);
    (window as unknown as { __chargen?: unknown; __THREE?: unknown }).__chargen = s0;
    (window as unknown as { __THREE?: unknown }).__THREE = THREE;
    // Crochet de contrôle (captures sans tête) : relit un .glb exporté avec GLTFLoader.
    (window as unknown as { __parseGlb?: unknown }).__parseGlb = (buffer: ArrayBuffer) => loader.parseAsync(buffer, '');
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      canvas.removeEventListener('pointerdown', down);
      canvas.removeEventListener('pointermove', move);
      canvas.removeEventListener('pointerup', up);
      canvas.removeEventListener('pointercancel', up);
      renderer.dispose();
      s0.renderer = null;
    };
  }, []);

  // Décor de la race.
  const race = props.descriptor.race;
  useEffect(() => {
    const s0 = st.current;
    const meta = props.data.scenes?.[race];
    if (!meta || !s0.cache || s0.sceneRace === race) return;
    let cancelled = false;
    s0.cache.gltf(props.base + meta.glb).then(gltf => {
      // (StrictMode monte deux fois : seul le dernier chargement demandé s'applique.)
      if (cancelled || s0.sceneRace === race) return;
      s0.sceneRace = race;
      s0.sceneRoot?.removeFromParent();
      s0.sceneMixer?.stopAllAction();
      for (const l of s0.lights) l.removeFromParent();
      const prepared = prepareScene(gltf);
      s0.sceneRoot = prepared.root;
      s0.sceneMixer = prepared.mixer;
      s0.scrollers = prepared.scrollers;
      s0.world.add(prepared.root);
      const { ambient, sun } = applyLight(s0.scene, meta);
      s0.lights = [ambient, sun];
      s0.frame?.();
      propsRef.current.onReady?.();
    }).catch(err => propsRef.current.onError?.(String(err)));
    return () => { cancelled = true; };
  }, [race, props.data, props.base]);

  // Personnages : gabarit, apparence, tenue, animation.
  const d = props.descriptor;
  const appearanceKey = JSON.stringify([d.appearance, d.companions, d.pet]);
  useEffect(() => {
    const s0 = st.current;
    if (!s0.cache) return;
    const p = propsRef.current;
    const meta = p.data.scenes?.[d.race];
    const combo = p.data.combos[comboKey(d.race, d.class)];
    const scale = meta?.character.scale ?? 1;
    type Want = { key: ChargenFocus; template: string; sex: Sex; appearance: Appearance; pet?: boolean; color?: number };
    const wants: Want[] = [];
    if (p.step !== 'faction' && combo) {
      const main = combo.sexes[d.sex];
      if (main) wants.push({ key: 'primary', template: main.template, sex: d.sex, appearance: d.appearance });
      for (const k of ['secondary', 'tertiary'] as const) {
        const c = d.companions?.[k];
        const t = c ? combo.sexes[c.sex]?.template : undefined;
        if (c && t) wants.push({ key: k, template: t, sex: c.sex, appearance: c.appearance });
      }
      if (d.pet) wants.push({ key: 'pet', template: d.pet.template, sex: 'male', appearance: { faces: d.pet.color }, pet: true });
    }
    const growth = p.equipment === null ? null : combo?.sexes[d.sex]?.growths[p.equipment] ?? null;
    for (const key of ['primary', 'secondary', 'tertiary', 'pet'] as ChargenFocus[]) {
      const want = wants.find(w => w.key === key);
      const slot = s0.slots[key] ?? (s0.slots[key] = { key, rig: null, loading: null });
      if (!want) { slot.rig?.dispose(); slot.rig = null; slot.loading = null; continue; }
      const tpl = want.pet ? p.data.pets[want.template] : p.data.templates[want.template];
      if (!tpl?.glb) continue;
      const applyTo = (rig: CharacterRig) => {
        const items = want.key === 'primary' || !want.pet ? growth?.items ?? [] : [];
        const look = resolveLook(p.data, want.template, tpl, want.sex, want.appearance, want.pet ? [] : items,
          { equipment: want.pet ? null : p.equipment, helmet: p.helmet }, rig.textured);
        // Effets de la tenue de création (`growths[].fx` : lueurs accrochées à un locator).
        if (want.key === 'primary' && growth) {
          for (const fx of growth.fx) if (fx.model) look.attachments.push({ model: fx.model, locator: fx.locator, template: want.template });
        }
        void rig.apply(look);
      };
      if (slot.rig && slot.rig.template === want.template) {
        applyTo(slot.rig);
        continue;
      }
      if (slot.loading === want.template) continue;
      slot.loading = want.template;
      s0.cache.gltf(p.base + tpl.glb).then(gltf => {
        if (slot.loading !== want.template) return;
        slot.rig?.dispose();
        const rig = new CharacterRig(gltf, s0.cache!, want.template);
        rig.root.scale.setScalar(scale);
        if (want.key !== 'primary') {
          const [ox, oy] = COMPANION_OFFSETS[want.key as Exclude<ChargenFocus, 'primary'>];
          rig.root.position.set(ox * scale, oy * scale, 0);
          rig.root.rotation.z = MODEL_FACING + THREE.MathUtils.degToRad(meta?.character.yaw ?? 0);
        }
        s0.characters.add(rig.root);
        slot.rig = rig;
        slot.loading = null;
        applyTo(rig);
        if (want.key === 'primary' && growth) rig.play(growth.start, growth.loop); else rig.play(null, null);
      }).catch(err => p.onError?.(String(err)));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d.race, d.class, d.sex, appearanceKey, props.step, props.equipment, props.helmet]);

  // Animation de création rejouée au changement de classe ou de tenue.
  useEffect(() => {
    const s0 = st.current;
    const p = propsRef.current;
    const rig = s0.slots.primary?.rig;
    const growth = p.equipment === null ? null : p.data.combos[comboKey(d.race, d.class)]?.sexes[d.sex]?.growths[p.equipment];
    if (rig) rig.play(growth?.start ?? null, growth?.loop ?? null);
  }, [d.class, props.equipment, d.race, d.sex]);

  // Caméra : plan large (race) ou rapproché (personnalisation).
  useEffect(() => { st.current.frame?.(); }, [props.step, race, props.data]);

  return <canvas ref={canvasRef} className={`${s.canvas} ${props.className ?? ''}`} data-testid="chargen-canvas" />;
});

export default ChargenViewer;
