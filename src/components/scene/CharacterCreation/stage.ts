import * as THREE from 'three';
import type { GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js';
import type { ChargenTemplate, SceneMeta } from '@/data/character/chargen.types';
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

/** Zoom de la molette et du pincement : 0 = plan du jeu, 1 = visage. */
export function clampZoom(z: number): number {
  return Math.min(1, Math.max(0, z));
}

/** Distance du plan rapproché au visage (m, à l'échelle du personnage) : réglage du site. */
const FACE_DISTANCE = 1.3;

/**
 * Plan de la création : la caméra de la place `CharacterSelect<Race>` (`UICharacterScenes`,
 * position relative au personnage, lacet et tangage — **positif vers le bas** : −3° pour l'elfe,
 * le quaternion de la place 7.0 donne une visée relevée de 3°), reculée sur son axe de
 * `preMissionAdditionalAway` du gabarit (0,5 m : l'écart mesuré entre la caméra brute et les
 * écrans du jeu, statues et estrade entières). Le zoom avance vers `preMissionFaceCameraAnchor`
 * (hauteur du visage) jusqu'à `FACE_DISTANCE`.
 */
export function chargenCamera(meta: SceneMeta, tpl: ChargenTemplate | undefined, zoom: number): { position: THREE.Vector3; target: THREE.Vector3 } {
  const stand = new THREE.Vector3(...(meta.character.position ?? [0, 0, 0]));
  const dir = gameDirection(meta.camera.yaw, -meta.camera.pitch);
  const away = tpl?.ui?.preMissionAdditionalAway ?? 0;
  const base = new THREE.Vector3(...meta.camera.position).add(stand).addScaledVector(dir, -away);
  const reach = base.distanceTo(stand);
  const baseTarget = base.clone().addScaledVector(dir, reach);
  if (zoom <= 0) return { position: base, target: baseTarget };
  const scale = (meta.character.scale ?? 1) * (tpl?.scale ?? 1);
  const anchor = tpl?.ui?.preMissionFaceCameraAnchor ?? [0, 0, tpl?.height ?? 1.8];
  const face = stand.clone().add(new THREE.Vector3(0, 0, anchor[2] * scale));
  const back = base.clone().sub(face).setZ(0).normalize();
  const close = face.clone().addScaledVector(back, FACE_DISTANCE * scale);
  const k = zoom * zoom * (3 - 2 * zoom);   // départ et arrivée en douceur
  return { position: base.clone().lerp(close, k), target: baseTarget.clone().lerp(face, k) };
}

/** Oriente la caméra ; le champ du jeu (1,36 rad) est **horizontal**, converti en vertical selon l'image. */
export function aimCamera(camera: THREE.PerspectiveCamera, position: THREE.Vector3, target: THREE.Vector3, fovH: number, aspect: number): void {
  camera.position.copy(position);
  camera.up.set(0, 0, 1);
  camera.lookAt(target);
  camera.fov = THREE.MathUtils.radToDeg(2 * Math.atan(Math.tan(fovH / 2) / Math.max(aspect, 0.1)));
  camera.aspect = aspect;
  camera.updateProjectionMatrix();
}

/** Couleur du jeu (`#rrggbb`, unité 128 = 1, comme `GAME_COLOR_UNIT` des fatalités). */
export function gameColor(hex: string): THREE.Color {
  const n = parseInt(hex.replace('#', ''), 16);
  return new THREE.Color(((n >> 16) & 255) / 128, ((n >> 8) & 255) / 128, (n & 255) / 128);
}

