import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import type { SceneMeta } from '@/lib/assets';
import { hooks } from './hooks';

const meta = (extra: object = {}): SceneMeta => ({
  version: '4.0', camera: { position: [115, 0, 4], target: [-45, 0, 1], fov: 45 }, up: [0, 0, 1],
  background: '#2b3c55', animations: [], ...extra,
});
function scene() {
  const root = new THREE.Group();
  const group = new THREE.Group(); root.add(group);
  const dome = new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial()); dome.renderOrder = -150;
  const land = new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial()); land.renderOrder = -220;
  group.add(dome, land);
  return { root, dome, land };
}

describe('V4 hooks', () => {
  it("redresse les textures dont l'origine est en bas dans le client", () => {
    const texture = new THREE.Texture();
    hooks.prepareTexture!(texture);
    expect(texture.repeat.y).toBe(-1);
    expect(texture.offset.y).toBe(1);
  });
  it("applique l'ordre du fichier quand le xdb déclare sortMode OFFSETS", () => {
    const { root, dome, land } = scene();
    expect(hooks.createEffects!(root, meta({ sortMode: 'OFFSETS' }), () => new THREE.Texture())).not.toBeNull(); // la brume dérive
    expect(dome.renderOrder).toBe(0);
    expect(land.renderOrder).toBe(1);
  });
  it('laisse le tri par profondeur du lecteur sans ce mode', () => {
    const { root, dome, land } = scene();
    hooks.createEffects!(root, meta(), () => new THREE.Texture());
    expect(dome.renderOrder).toBe(-150);
    expect(land.renderOrder).toBe(-220);
  });
});
