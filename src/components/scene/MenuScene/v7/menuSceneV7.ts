import * as THREE from 'three';
import { prepareV7Layers } from './v7SceneLayers';
import { createV7Intro } from './v7Intro';
import { createNativeShots } from './v7NativeShots';
import { freezeEngineTrails } from './v7Engines';

export type CannonTextures = Partial<Record<'projectile' | 'muzzle' | 'impact' | 'shield' | 'flame' | 'electric' | 'spark' | 'smoke', THREE.Texture>>;
export function createV7Effects(root: THREE.Object3D, textures: CannonTextures = {}) {
  const nearStones = root.getObjectByName('AMM_7_0_Stones_01');
  if (nearStones) nearStones.position.x += 6;
  const farStones = root.getObjectByName('AMM_7_0_Stones_02');
  if (farStones) { farStones.position.z -= 9; farStones.scale.multiplyScalar(.9); }
  root.traverse(object => {
    const mesh = object as THREE.Mesh;
    if (!mesh.isMesh || Array.isArray(mesh.material)) return;
    const element = String(mesh.geometry.userData.element ?? '');
    const material = mesh.material as THREE.MeshBasicMaterial;
    if (element.startsWith('Front_Myst')) material.opacity *= .35;
    if (element === 'Back_Myst') material.opacity *= .65;
    if (/^Back_Cloud_0[2-6]$/.test(element)) material.opacity *= .65;
    if (element.startsWith('GunRay')) mesh.visible = false;
    // Les réacteurs natifs n'ont ni pulsation ni variation de taille.
    if (element.startsWith('Engine_')) material.color.setRGB(2.4, 2.8, 3);
  });
  const engines = freezeEngineTrails(root);
  const layers = prepareV7Layers(root);
  const intro = createV7Intro(root, textures);
  const shots = createNativeShots(root, textures.smoke);
  return {
    update(time: number, reduced = false) {
      layers.update(time, reduced);
      intro.update(time, reduced);
      shots.update(time, reduced);
    },
    dispose() { shots.dispose(); intro.dispose(); layers.dispose(); engines.dispose(); },
  };
}
