import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import * as THREE from 'three';
import { GLTFLoader, type GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js';
import type { ChargenData, ChargenSceneFile, Sex } from '@/data/character/chargen.types';
import { comboKey, type CharacterDescriptor, type Appearance } from '@/data/character/descriptor';
import { resolveLook } from '@/data/character/look';
import { CharacterRig, createAssetCache, type AssetCache } from './rig';
import { aimCamera, chargenCamera, clampZoom } from './stage';
import { loadChargenDecor, type ChargenDecor } from './chargenDecor';
import { CharacterFxHost, type FxWant } from './characterFx';
import { ActorLighting } from './actorLight';
import { exportCharacterGlb } from './exportGlb';
import s from './ChargenViewer.module.css';

THREE.ColorManagement.enabled = false;

export type ChargenFocus = 'primary' | 'secondary' | 'tertiary' | 'pet';

export type ChargenViewerProps = {
  data: ChargenData;
  /** Racine des fichiers (`/game/character/`). */
  base: string;
  descriptor: CharacterDescriptor;
  /** `faction` : aucun personnage ; `race` et `custom` : même plan que le jeu. */
  step: 'faction' | 'race' | 'custom';
  /** Tenue montrée (indice de `growths`) ou `null` sans tenue. */
  equipment: number | null;
  helmet: boolean;
  focus: ChargenFocus;
  /** Sons du décor (ambiance, objets) : coupés avec la musique. */
  muted?: boolean;
  className?: string;
  onReady?: () => void;
  onError?: (message: string) => void;
};

export type ChargenViewerHandle = {
  exportGlb: () => Promise<Blob>;
  resetRotation: () => void;
};

/**
 * Décalage des compagnons du trio gibberling et du familier, en mètres (repère du personnage,
 * qui regarde −Y) : **placement inventé**, le client ne le publie pas. Le familier se tient à la
 * droite du personnage, un pas en arrière, au sol de l'estrade.
 */
const COMPANION_OFFSETS: Record<Exclude<ChargenFocus, 'primary'>, [number, number]> = {
  secondary: [-0.75, 0.45],
  tertiary: [0.75, 0.45],
  pet: [-1.1, 0.6],
};
/** Lacet ajouté au modèle pour qu'il fasse face à la caméra de la place (le modèle regarde -Y). */
const MODEL_FACING = 0;
/** Pas de la molette (fraction du zoom par cran de 100) et du pincement (par pixel). */
const WHEEL_STEP = 0.12;
const PINCH_STEP = 1 / 300;

type Slot = { key: string; rig: CharacterRig | null; loading: string | null };

export const ChargenViewer = forwardRef<ChargenViewerHandle, ChargenViewerProps>(function ChargenViewer(props, ref) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const propsRef = useRef(props);
  propsRef.current = props;
  const st = useRef({
    renderer: null as THREE.WebGLRenderer | null,
    scene: new THREE.Scene(),
    world: new THREE.Group(),
    camera: new THREE.PerspectiveCamera(45, 1, 0.05, 4000),
    cache: null as AssetCache | null,
    sceneRace: '',
    decor: null as ChargenDecor | null,
    characters: new THREE.Group(),
    slots: {} as Record<ChargenFocus, Slot>,
    yaw: 0,
    zoom: 0,
    drag: null as null | { x: number; yaw: number },
    pointers: new Map<number, { x: number; y: number }>(),
    pinch: null as null | { d: number; zoom: number },
    time: 0,
    /** Départ de l'animation de création en cours (les effets de la tenue s'y calent). */
    playAt: 0,
    fx: null as CharacterFxHost | null,
    /** Éclairage des personnages (ambiante, soleil, lumières ponctuelles de la place). */
    lighting: new ActorLighting(),
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
    resetRotation: () => { st.current.yaw = 0; st.current.zoom = 0; st.current.frame?.(); },
  }), []);

  // Montage : moteur de rendu, boucle, glisser pour tourner le personnage, molette et pincement.
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
    // Pas de miroir : le repère du jeu (X, Y au sol, Z en haut) se lit en main droite — le décor
    // et le personnage retrouvent la disposition des écrans du jeu (méridienne à gauche du
    // décor elfe, orbe du mage dans sa main gauche vue de face).
    s0.world.add(s0.characters);
    s0.scene.add(s0.world);
    s0.camera.up.set(0, 0, 1);
    const frame = () => {
      const w = canvas.clientWidth || 1;
      const h = canvas.clientHeight || 1;
      renderer.setSize(w, h, false);
      const p = propsRef.current;
      const meta = p.data.scenes?.[p.descriptor.race];
      if (!meta) return;
      const [sx, sy, sz] = meta.character.position ?? [0, 0, 0];
      s0.characters.position.set(sx, sy, sz);
      const tpl = p.data.templates[p.data.combos[comboKey(p.descriptor.race, p.descriptor.class)]?.sexes[p.descriptor.sex]?.template ?? ''];
      const shot = chargenCamera(meta, tpl, s0.zoom);
      aimCamera(s0.camera, shot.position, shot.target, meta.camera.fov, w / h);
    };
    s0.frame = frame;
    const ro = new ResizeObserver(frame);
    ro.observe(canvas);
    const clock = new THREE.Clock();
    let raf = 0;
    const loop = () => {
      raf = requestAnimationFrame(loop);
      const dt = Math.min(clock.getDelta(), 0.1);
      s0.time += dt;
      for (const slot of Object.values(s0.slots)) slot.rig?.update(dt);
      const primary = s0.slots.primary?.rig;
      if (primary) primary.root.rotation.z = MODEL_FACING + THREE.MathUtils.degToRad(sceneYaw()) + s0.yaw;
      const p = propsRef.current;
      s0.decor?.update(s0.time, s0.camera, p.step !== 'faction' && !p.muted);
      s0.fx?.update(s0.time, s0.camera);
      s0.camera.updateMatrixWorld();
      s0.lighting.update(s0.camera, s0.world);
      renderer.render(s0.scene, s0.camera);
    };
    const sceneYaw = () => propsRef.current.data.scenes?.[propsRef.current.descriptor.race]?.character.yaw ?? 0;
    loop();
    const setZoom = (z: number) => { s0.zoom = clampZoom(z); frame(); };
    const down = (e: PointerEvent) => {
      s0.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      canvas.setPointerCapture(e.pointerId);
      if (s0.pointers.size === 2) {
        const [a, b] = [...s0.pointers.values()];
        s0.pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), zoom: s0.zoom };
        s0.drag = null;
      } else if (s0.pointers.size === 1) {
        s0.drag = { x: e.clientX, yaw: s0.yaw };
      }
    };
    const move = (e: PointerEvent) => {
      if (!s0.pointers.has(e.pointerId)) return;
      s0.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (s0.pinch && s0.pointers.size >= 2) {
        const [a, b] = [...s0.pointers.values()];
        setZoom(s0.pinch.zoom + (Math.hypot(a.x - b.x, a.y - b.y) - s0.pinch.d) * PINCH_STEP);
      } else if (s0.drag) {
        s0.yaw = s0.drag.yaw + (e.clientX - s0.drag.x) * 0.01;
      }
    };
    const up = (e: PointerEvent) => {
      s0.pointers.delete(e.pointerId);
      if (s0.pointers.size < 2) s0.pinch = null;
      if (s0.pointers.size === 0) s0.drag = null;
      else if (s0.pointers.size === 1) { const [only] = [...s0.pointers.values()]; s0.drag = { x: only.x, yaw: s0.yaw }; }
    };
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      setZoom(s0.zoom - Math.sign(e.deltaY) * Math.min(Math.abs(e.deltaY) / 100, 3) * WHEEL_STEP);
    };
    canvas.addEventListener('pointerdown', down);
    canvas.addEventListener('pointermove', move);
    canvas.addEventListener('pointerup', up);
    canvas.addEventListener('pointercancel', up);
    canvas.addEventListener('wheel', wheel, { passive: false });
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
      canvas.removeEventListener('wheel', wheel);
      s0.decor?.dispose();
      s0.decor = null;
      s0.fx?.dispose();
      s0.fx = null;
      s0.sceneRace = '';
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
    const cache = s0.cache;
    fetch(props.base + meta.file).then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json() as Promise<ChargenSceneFile>; })
      .then(file => loadChargenDecor(file, props.base, url => cache.gltf(url), { anisotropy: () => s0.renderer?.capabilities.getMaxAnisotropy() ?? 1 }))
      .then(decor => {
        // (StrictMode monte deux fois : seul le dernier chargement demandé s'applique.)
        if (cancelled || s0.sceneRace === race) { decor.dispose(); return; }
        s0.sceneRace = race;
        if (s0.decor) { s0.decor.sun.removeFromParent(); s0.decor.dispose(); }
        s0.decor = decor;
        s0.world.add(decor.group);
        s0.scene.background = decor.background;
        s0.scene.fog = decor.fog;
        s0.scene.add(decor.sun);
        s0.lighting.setScene(props.data.scenes?.[race]?.character, { color: decor.sun.color, direction: decor.sun.position });
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
    // Lumière du personnage (shaders du jeu, voir `ActorLighting`) : ambiante de la zone en émission
    // modulée par la texture, soleil par N·L, lumières ponctuelles de la place une à une.
    const lightRig = (rig: CharacterRig) => {
      rig.root.traverse(node => {
        const mesh = node as THREE.Mesh;
        if (!mesh.isMesh) return;
        for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
          if (!(material instanceof THREE.MeshLambertMaterial) || material.transparent || material.blending === THREE.AdditiveBlending) continue;
          s0.lighting.apply(material);
        }
      });
    };
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
    // Hôte des effets lu à l'appel (le double montage de StrictMode en recrée un).
    const fxHost = () => s0.fx ?? (s0.fx = new CharacterFxHost(p.data, p.base, url => s0.cache!.gltf(url)));
    for (const key of ['primary', 'secondary', 'tertiary', 'pet'] as ChargenFocus[]) {
      const want = wants.find(w => w.key === key);
      const slot = s0.slots[key] ?? (s0.slots[key] = { key, rig: null, loading: null });
      if (!want) { if (slot.rig) fxHost().forget(slot.rig); slot.rig?.dispose(); slot.rig = null; slot.loading = null; continue; }
      const tpl = want.pet ? p.data.pets[want.template] : p.data.templates[want.template];
      if (!tpl?.glb) continue;
      const applyTo = (rig: CharacterRig) => {
        const items = want.key === 'primary' || !want.pet ? growth?.items ?? [] : [];
        const look = resolveLook(p.data, want.template, tpl, want.sex, want.appearance, want.pet ? [] : items,
          { equipment: want.pet ? null : p.equipment, helmet: p.helmet }, rig.textured);
        void rig.apply(look).then(() => {
          lightRig(rig);
          // Effets : ceux des objets portés en continu, ceux de la tenue avec l'animation de création.
          const fx: FxWant[] = look.fx.map(f => ({ fx: f.fx, locator: f.locator, start: 0, effectsOnly: true }));
          if (want.key === 'primary') {
            for (const f of growth?.fx ?? []) if (f.fx) fx.push({ fx: f.fx, locator: f.locator, scale: f.scale || 1, start: s0.playAt, runType: f.runType });
          }
          void fxHost().sync(rig, fx);
        });
      };
      if (slot.rig && slot.rig.template === want.template) {
        applyTo(slot.rig);
        continue;
      }
      if (slot.loading === want.template) continue;
      slot.loading = want.template;
      s0.cache.gltf(p.base + tpl.glb).then(gltf => {
        if (slot.loading !== want.template) return;
        if (slot.rig) fxHost().forget(slot.rig);
        slot.rig?.dispose();
        const rig = new CharacterRig(gltf, s0.cache!, want.template);
        rig.root.scale.setScalar(scale);
        if (want.key !== 'primary') {
          const [ox, oy] = COMPANION_OFFSETS[want.key as Exclude<ChargenFocus, 'primary'>];
          // Repère du personnage (tourné du lacet de la place) → repère du décor.
          const yaw = MODEL_FACING + THREE.MathUtils.degToRad(meta?.character.yaw ?? 0);
          const offset = new THREE.Vector2(ox * scale, oy * scale).rotateAround(new THREE.Vector2(), yaw);
          rig.root.position.set(offset.x, offset.y, 0);
          rig.root.rotation.z = yaw;
        }
        s0.characters.add(rig.root);
        slot.rig = rig;
        slot.loading = null;
        if (want.key === 'primary') s0.playAt = s0.time;
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
    if (!rig) return;
    rig.play(growth?.start ?? null, growth?.loop ?? null);
    s0.playAt = s0.time;
  }, [d.class, props.equipment, d.race, d.sex]);

  // Caméra : même plan aux deux étapes (celui du jeu) ; le zoom revient au plan large au changement de race.
  useEffect(() => { st.current.zoom = 0; st.current.frame?.(); }, [race]);
  useEffect(() => { st.current.frame?.(); }, [props.step, props.data, d.class, d.sex]);

  return <canvas ref={canvasRef} className={`${s.canvas} ${props.className ?? ''}`} data-testid="chargen-canvas" />;
});

export default ChargenViewer;
