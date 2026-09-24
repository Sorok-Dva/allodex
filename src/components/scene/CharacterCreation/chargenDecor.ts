import * as THREE from 'three';
import type { GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { loadParticleFile } from '@/components/scene/FatalityViewer/particles';
import { VotFactory, particleSystems, updateInstance, type Tinted, type VotInstance } from '@/components/scene/vot/votInstances';
import { argb, falloff } from '@/components/scene/EngineCutscene/timeline';
import { terrainMaterial } from '@/components/scene/EngineCutscene/EngineCutscene';
import type { ChargenSceneFile } from '@/data/character/chargen.types';

/** Couleurs du jeu : 0x80 = 1. */
export const GAME_UNIT = 255 / 128;
/** Compense la division par π du Lambert de three.js : une lumière du jeu à 1 éclaire à 1. */
export const LIGHT_SCALE = Math.PI;
/** Portée des boucles sonores des objets du décor (m), volume linéaire jusqu'à zéro. */
const SOUND_RANGE = 40;

export type ChargenDecor = {
  /** Décor, ciel et sol, en coordonnées de la carte ramenées à l'origine du décor. */
  group: THREE.Group;
  sun: THREE.DirectionalLight;
  /** Couleur du brouillard (fond) et brouillard de la zone. */
  background: THREE.Color;
  fog: THREE.Fog | null;
  /** Pose les objets animés (particules, lanternes) au temps `t` et suit la caméra (ciel, sons). */
  update(t: number, camera: THREE.Camera, audible: boolean): void;
  dispose(): void;
};

/**
 * Décor d'une race (`scenes/<Race>.json`, chaîne des cinématiques moteur) : gabarits posés du
 * décor commun `maps/MainMenu/decor.glb` avec l'éclairage précalculé de chaque sommet
 * (`<Race>-light.bin` : ambiante + soleil + lumières ponctuelles de la carte, doublé à l'affichage),
 * particules (feuilles, lueurs), animations des gabarits, ciel de la zone qui suit la caméra,
 * brouillard et soleil de la zone (`ZoneLights`), boucles sonores (ambiance de la place, sons des
 * objets). Même lecture que `EngineCutscene`, sans chronologie : le temps court en boucle.
 */
export async function loadChargenDecor(scene: ChargenSceneFile, base: string,
  load: (url: string) => Promise<GLTF>, opts: { anisotropy?: () => number } = {}): Promise<ChargenDecor> {
  const disposables: { dispose(): void }[] = [];
  const factory = new VotFactory({ objects: scene.objects, baseUrl: base + scene.decor.glb, disposables, anisotropy: opts.anisotropy });
  const group = new THREE.Group();
  const [ox, oy, oz] = scene.origin;
  group.position.set(-ox, -oy, -oz);
  const safe = (url: string | null | undefined) => (url ? load(base + url).catch(() => null) : Promise.resolve(null));
  const systems = particleSystems(scene.objects);
  const [decor, skyGlb, terrainGlb, lightBin, atlas] = await Promise.all([
    safe(scene.decor.glb),
    safe(scene.decor.skyGlb),
    safe(scene.decor.terrainGlb),
    fetch(base + scene.decor.light).then(r => (r.ok ? r.arrayBuffer() : null)).catch(() => null),
    scene.particleAtlas && systems.size && typeof DecompressionStream !== 'undefined'
      ? new THREE.TextureLoader().loadAsync(base + scene.particleAtlas.file).catch(() => null) : Promise.resolve(null),
    ...[...systems].map(file => loadParticleFile(base + file).then(parsed => { factory.particleFiles.set(file, parsed); }).catch(() => null)),
  ]);
  if (atlas) {
    atlas.flipY = false;
    atlas.colorSpace = THREE.NoColorSpace;
    atlas.needsUpdate = true;
    factory.atlasTexture = atlas;
    factory.particleAtlas = scene.particleAtlas;
    disposables.push(atlas);
  }
  const light = scene.light ?? {};
  const ambient = argb(light.ambient, GAME_UNIT);
  // Ciel : dôme qui suit la caméra, derrière tout, hors brouillard.
  let sky: THREE.Object3D | null = null;
  const skyProto = skyGlb?.scene.getObjectByName('sky');
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
    group.add(skyProto);
    sky = skyProto;
  }
  // Sol de la carte : calques mélangés par le SplatMap et lumière cuite des lightmaps, même
  // matériau que les cinématiques moteur (`terrainMaterial`).
  if (terrainGlb && scene.decor.terrainGlb) {
    const terrainUrl = new URL(base + scene.decor.terrainGlb, window.location.href);
    const node = terrainGlb.scene.getObjectByName('terrain');
    const extras = node?.userData as { terrainLayers?: { texture: string | null }[]; terrainLightmap?: string | null } | undefined;
    const material = await terrainMaterial(extras?.terrainLayers ?? [], extras?.terrainLightmap ?? null, terrainUrl, light);
    disposables.push(material);
    terrainGlb.scene.traverse(child => {
      const mesh = child as THREE.Mesh;
      if (!mesh.isMesh) return;
      mesh.material = material;
      mesh.frustumCulled = false;
    });
    group.add(terrainGlb.scene);
  }
  const prototypes = new Map<string, THREE.Object3D>();
  const clips: THREE.AnimationClip[] = [];
  if (decor) {
    decor.scene.traverse(node => { const vot = (node.userData as { vot?: string }).vot; if (vot && !prototypes.has(vot)) prototypes.set(vot, node); });
    clips.push(...decor.animations);
  }
  const baked = lightBin ? new Uint8Array(lightBin) : null;
  const instances: VotInstance[] = [];
  type Loop = { audio: HTMLAudioElement; volume: number; position: THREE.Vector3 | null };
  const loops: Loop[] = [];
  const audioFile = (file: string) => {
    const audio = new Audio();
    const ogg = typeof audio.canPlayType === 'function' && audio.canPlayType('audio/ogg');
    audio.src = `${base}${file}.${ogg ? 'ogg' : 'mp3'}`;
    audio.preload = 'auto';
    audio.loop = true;
    return audio;
  };
  for (const item of scene.decor.instances) {
    const proto = prototypes.get(item.vot);
    const info = scene.objects[item.vot];
    if (!proto || !info) continue;
    const inst = factory.instantiate(proto, clips, 0, Infinity, 0, 0);
    inst.root.position.set(...item.p);
    inst.root.rotation.set(item.tilt?.[0] ?? 0, item.tilt?.[1] ?? 0, item.yaw, 'ZYX');
    inst.root.scale.setScalar((item.scale || 1) * (info.scale || 1));
    // Éclairage précalculé sur le maillage propre de l'instance (octets à moitié : doublés) ; les
    // autres maillages opaques (composants) prennent l'ambiante de la zone.
    // Le maillage propre (`<gabarit>_mesh`) est un groupe quand il a plusieurs matériaux (un
    // primitif chacun, tous sur le même tampon de sommets) : l'éclairage vaut pour chacun.
    const own = new Set<THREE.Object3D>();
    const ownRoot = inst.root.getObjectByName(THREE.PropertyBinding.sanitizeNodeName(`${item.vot}_mesh`));
    if (ownRoot) {
      own.add(ownRoot);
      for (const child of ownRoot.children) if ((child as THREE.Mesh).isMesh) own.add(child);
    }
    inst.root.traverse(node => {
      const mesh = node as THREE.Mesh;
      if (!mesh.isMesh) return;
      const material = mesh.material as THREE.MeshBasicMaterial;
      if (material.transparent || material.blending === THREE.AdditiveBlending) return;
      if (own.has(mesh) && item.light && baked && mesh.geometry.getAttribute('position').count === item.light[1]) {
        const [offset, count] = item.light;
        const geometry = mesh.geometry.clone();
        geometry.setAttribute('color', new THREE.BufferAttribute(baked.slice(offset * 4, (offset + count) * 4), 4, true));
        mesh.geometry = geometry;
        disposables.push(geometry);
        material.color.setScalar(2);
      } else {
        const [r, g, b] = item.ambient ?? ambient;
        material.color.setRGB(r, g, b);
      }
    });
    group.add(inst.root);
    instances.push(inst);
    if (info.sfx) loops.push({ audio: audioFile(info.sfx), volume: 0.6, position: new THREE.Vector3(...item.p).sub(new THREE.Vector3(ox, oy, oz)) });
  }
  for (const file of scene.sounds?.ambience ?? []) loops.push({ audio: audioFile(file), volume: 0.5, position: null });

  const fogColor = new THREE.Color(...argb(light.fog));
  const fog = light.fogEnd ? new THREE.Fog(fogColor, light.fogStart ?? 0, light.fogEnd) : null;
  const sun = new THREE.DirectionalLight(new THREE.Color(...argb(light.diffuse, GAME_UNIT)), LIGHT_SCALE);
  const [dx, dy, dz] = light.sunDirection ?? [0.5, 0.5, 0.7];
  sun.position.set(dx, dy, dz);
  const eye = new THREE.Vector3();
  return {
    group, sun, background: fogColor, fog,
    update(t, camera, audible) {
      if (sky) { group.worldToLocal(camera.getWorldPosition(eye)); sky.position.set(eye.x, eye.y, 0); }
      for (const inst of instances) updateInstance(inst, t, 1, camera);
      camera.getWorldPosition(eye);
      for (const loop of loops) {
        const volume = loop.volume * (loop.position ? falloff(loop.position.distanceTo(eye), SOUND_RANGE) : 1);
        if (!audible || volume <= 0.001) { if (!loop.audio.paused) loop.audio.pause(); continue; }
        loop.audio.volume = Math.min(1, volume);
        if (loop.audio.paused) void loop.audio.play()?.catch?.(() => {});
      }
    },
    dispose() {
      for (const loop of loops) { loop.audio.pause(); loop.audio.removeAttribute('src'); }
      for (const inst of instances) inst.mixer.stopAllAction();
      for (const d of disposables) d.dispose();
      group.traverse(object => { const mesh = object as THREE.Mesh; if (mesh.isMesh) mesh.geometry.dispose(); });
      group.removeFromParent();
    },
  };
}
