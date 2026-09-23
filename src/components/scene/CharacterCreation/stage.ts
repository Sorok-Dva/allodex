import * as THREE from 'three';
import type { GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js';
import type { SceneMeta } from '@/data/character/chargen.types';
import { uvScrollOf } from './rig';

/**
 * Matériau d'un décor de création : la lumière y est peinte (textures et couleurs de sommet,
 * déjà doublées par l'exportateur), donc sans éclairage ; profondeur testée et écrite (ce sont
 * de vraies scènes 3D, pas les calques des menus) ; feuillages découpés (`extras.cutout`),
 * transparents sans écriture de profondeur, additifs en mélange additif.
 */
export function sceneMaterial(source: THREE.Material): THREE.MeshBasicMaterial {
  const src = source as THREE.MeshBasicMaterial;
  const extras = source.userData as { blend?: string; cutout?: boolean };
  const additive = extras.blend === 'add';
  const translucent = source.transparent || additive;
  const material = new THREE.MeshBasicMaterial({
    name: source.name, map: src.map ?? null, color: 0xffffff, opacity: source.opacity,
    transparent: translucent, alphaTest: extras.cutout ? 0.5 : source.alphaTest, side: THREE.DoubleSide,
    vertexColors: true, toneMapped: false, fog: true,
  });
  if (translucent) material.depthWrite = false;
  if (additive) material.blending = THREE.AdditiveBlending;
  if (material.map) material.map.colorSpace = THREE.NoColorSpace;
  return material;
}

export type Scroller = { texture: THREE.Texture; speed: [number, number]; base: THREE.Vector2 };

/** Prépare un décor chargé : matériaux, défilements UV, animations (toutes en boucle). */
export function prepareScene(gltf: GLTF): { root: THREE.Object3D; mixer: THREE.AnimationMixer; scrollers: Scroller[] } {
  const root = gltf.scene;
  const scrollers: Scroller[] = [];
  root.traverse(object => {
    const mesh = object as THREE.Mesh;
    if (!mesh.isMesh || Array.isArray(mesh.material)) return;
    const speed = uvScrollOf(gltf, mesh);
    const material = sceneMaterial(mesh.material);
    if (speed && material.map && (speed[0] || speed[1])) {
      const texture = material.map.clone();
      texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
      texture.needsUpdate = true;
      material.map = texture;
      scrollers.push({ texture, speed, base: texture.offset.clone() });
    }
    mesh.material = material;
    mesh.frustumCulled = false;
  });
  const mixer = new THREE.AnimationMixer(root);
  for (const clip of gltf.animations) mixer.clipAction(clip).play();
  return { root, mixer, scrollers };
}

export function updateScrollers(scrollers: Scroller[], time: number): void {
  for (const { texture, speed, base } of scrollers) {
    texture.offset.set(base.x + (time * speed[0]) % 1, base.y - (time * speed[1]) % 1);
  }
}

/** Direction de visée du jeu (lacet, tangage en degrés, Z en haut). */
export function gameDirection(yawDeg: number, pitchDeg: number): THREE.Vector3 {
  const yaw = THREE.MathUtils.degToRad(yawDeg);
  const pitch = THREE.MathUtils.degToRad(pitchDeg);
  return new THREE.Vector3(Math.cos(pitch) * Math.cos(yaw), Math.cos(pitch) * Math.sin(yaw), Math.sin(pitch));
}

/**
 * Caméra de la place `CharacterSelect<Race>` (`UICharacterScenes`) dans le repère du monde
 * affiché (miroir X appliqué) : position relative au personnage, visée par lacet et tangage.
 * Le champ du jeu (1,36 rad) est pris comme **horizontal** et converti en vertical selon l'image.
 */
export function placeCamera(camera: THREE.PerspectiveCamera, meta: SceneMeta['camera'], aspect: number): void {
  const [x, y, z] = meta.position;
  const dir = gameDirection(meta.yaw, meta.pitch);
  camera.position.set(-x, y, z);
  const target = new THREE.Vector3(-x - dir.x, y + dir.y, z + dir.z);
  camera.up.set(0, 0, 1);
  camera.lookAt(target);
  const horizontal = meta.fov;
  camera.fov = THREE.MathUtils.radToDeg(2 * Math.atan(Math.tan(horizontal / 2) / Math.max(aspect, 0.1)));
  camera.aspect = aspect;
  camera.updateProjectionMatrix();
}

/** Couleur du jeu (`#rrggbb`, unité 128 = 1, comme `GAME_COLOR_UNIT` des fatalités). */
export function gameColor(hex: string): THREE.Color {
  const n = parseInt(hex.replace('#', ''), 16);
  return new THREE.Color(((n >> 16) & 255) / 128, ((n >> 8) & 255) / 128, (n & 255) / 128);
}

/** three.js divise l'éclairage de Lambert par π (BRDF physique) : compensé, comme les fatalités. */
export const LIGHT_SCALE = Math.PI;

/**
 * Lumière de la zone (`ZoneLights` de la carte) : formule du jeu texture × (ambiante + soleil·N·L),
 * brouillard linéaire ; le fond prend la couleur du brouillard.
 */
export function applyLight(scene: THREE.Scene, meta: SceneMeta | undefined): { ambient: THREE.AmbientLight; sun: THREE.DirectionalLight } {
  const light = meta?.light;
  const ambient = new THREE.AmbientLight(light ? gameColor(light.ambient) : new THREE.Color(0.5, 0.5, 0.5), LIGHT_SCALE);
  const sun = new THREE.DirectionalLight(light ? gameColor(light.sun) : new THREE.Color(1, 1, 1), LIGHT_SCALE);
  const d = light?.sunDirection ?? [0.5, -0.5, 0.7];
  // Direction du jeu vers le soleil ; le monde affiché est en miroir X.
  sun.position.set(-d[0] * 10, d[1] * 10, d[2] * 10);
  scene.add(ambient, sun);
  if (light?.fog && light.fog.far > light.fog.near) {
    scene.fog = new THREE.Fog(light.fog.color, Math.max(light.fog.near, 0), light.fog.far);
    scene.background = new THREE.Color(light.fog.color);
  } else {
    scene.background = new THREE.Color('#1b1f27');
  }
  return { ambient, sun };
}
