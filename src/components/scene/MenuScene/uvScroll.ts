import * as THREE from 'three';
import type { SceneEffects } from './effects';

/** Vitesse de défilement UV (tuiles par seconde) d'un maillage, ou rien s'il ne défile pas. */
export type ScrollSpeedOf = (mesh: THREE.Mesh, element: string) => readonly [number, number] | undefined;

/**
 * Défilement UV des calques (brume, nuages, jets) : la texture du matériau est clonée pour
 * que son offset avance sans entraîner les autres calques qui partagent l'image, et un
 * matériau partagé n'est animé qu'une fois. L'axe V est inversé comme le fait le lecteur
 * du client (voir v7SceneLayers). Le démontage rend le matériau à sa texture d'origine.
 */
export function createUvScroll(root: THREE.Object3D, speedOf: ScrollSpeedOf): SceneEffects {
  const scrolling: { texture: THREE.Texture; original: THREE.Texture; material: THREE.MeshBasicMaterial;
    offset: THREE.Vector2; speed: THREE.Vector2 }[] = [];
  const animated = new Set<THREE.Material>();
  root.traverse(object => {
    const mesh = object as THREE.Mesh;
    if (!mesh.isMesh || Array.isArray(mesh.material)) return;
    const material = mesh.material as THREE.MeshBasicMaterial;
    const speed = speedOf(mesh, String(mesh.geometry.userData.element ?? ''));
    if (!material.map || !speed || (!speed[0] && !speed[1]) || animated.has(material)) return;
    animated.add(material);
    const original = material.map;
    const texture = original.clone();
    texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
    texture.needsUpdate = true;
    material.map = texture;
    scrolling.push({ texture, original, material, offset: texture.offset.clone(), speed: new THREE.Vector2(speed[0], speed[1]) });
  });
  return {
    update(time, reduced = false) {
      const elapsed = reduced ? 0 : time;
      for (const { texture, offset, speed } of scrolling) {
        texture.offset.set(offset.x + (elapsed * speed.x) % 1, offset.y - (elapsed * speed.y) % 1);
      }
    },
    dispose() {
      for (const { texture, original, material } of scrolling) { material.map = original; texture.dispose(); }
    },
  };
}
