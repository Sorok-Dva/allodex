import { describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import { createV7Effects } from './menuSceneV7';

function fixture(loaded = true) {
  const root = new THREE.Group();
  const front = new THREE.Group(); front.name = 'AMM_7_0_FrontShips'; root.add(front);
  const destroyed = new THREE.Group(); destroyed.name = 'AMM_7_0_Ships_Destroyed'; root.add(destroyed);
  const source = new THREE.Group(); source.name = 'AMM_Shot01'; root.add(source);
  const texture = loaded ? new THREE.Texture({ width: 64, height: 64 }) : new THREE.Texture();
  for (const name of ['Proj_Foreground01', 'Proj_Back', 'Proj_Noise01', 'Tail_Glow01', 'Tail_FlowStart', 'Tail_FlowMain',
    'FireMuzzle', 'Shield01', 'ShieldRays01', 'ShockWave01', 'ShockWave02', 'Flash01', 'ShieldFlash01']) {
    const geometry = new THREE.PlaneGeometry();
    geometry.userData.element = name;
    geometry.userData.uvScroll = [.2, .1];
    geometry.setAttribute('color', new THREE.Float32BufferAttribute(Array(16).fill(.5), 4));
    source.add(new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ map: texture, vertexColors: true })));
  }
  return { root, front, destroyed, source, texture };
}

describe('V7 native menu effects', () => {
  it('réutilise les maillages, UV et couleurs natifs sans shader procédural', () => {
    const { root, source, front } = fixture();
    const effects = createV7Effects(root);
    expect(source.visible).toBe(false);
    const group = front.getObjectByName('V7_cannon_effects')!;
    expect(group.children.filter(child => child.name === 'V7_cannon_projectile')).toHaveLength(4);
    const sourceTail = source.children.find(child => (child as THREE.Mesh).geometry.userData.element === 'Tail_FlowMain') as THREE.Mesh;
    const tail = group.getObjectByName('V7_native_Tail_FlowMain') as THREE.Mesh<THREE.BufferGeometry, THREE.MeshBasicMaterial>;
    expect(tail.geometry.getAttribute('uv').array).toEqual(sourceTail.geometry.getAttribute('uv').array);
    expect(tail.geometry.getAttribute('color').array).toEqual(sourceTail.geometry.getAttribute('color').array);
    expect(tail.geometry.index!.array).toEqual(sourceTail.geometry.index!.array);
    expect(tail.material.isMeshBasicMaterial).toBe(true);
    expect(tail.material.color.toArray()).toEqual([1, 1, 1]);
    effects.dispose();
  });
  it('fait voyager deux tirs par bateau pendant six secondes puis anime les maillages du bouclier', () => {
    const { root, front } = fixture(); const effects = createV7Effects(root);
    const group = front.getObjectByName('V7_cannon_effects')!;
    const projectile = group.getObjectByName('V7_cannon_projectile')!;
    const impact = group.getObjectByName('V7_cannon_impact')!;
    effects.update(2.55); expect(projectile.visible).toBe(true); expect(impact.visible).toBe(false);
    const start = projectile.position.clone();
    effects.update(5.5); expect(projectile.position.distanceTo(start)).toBeGreaterThan(30);
    effects.update(8.49); expect(projectile.visible).toBe(true);
    effects.update(8.55); expect(projectile.visible).toBe(false); expect(impact.visible).toBe(true);
    effects.update(9.6); const shape = impact.userData.shape;
    effects.update(9.75); expect(impact.userData.shape).toBeLessThan(shape); expect(impact.userData.returning).toBe(true);
    effects.update(10); expect(impact.visible).toBe(false);
    effects.dispose();
  });
  it('sépare le choc concentré des deux couches bleues et amplifie la fumée de bouche', () => {
    const { root, front, texture } = fixture();
    const effects = createV7Effects(root, { smoke: texture });
    const impact = front.getObjectByName('V7_cannon_impact')!;
    const rays = impact.getObjectByName('V7_native_ShieldRays01')!;
    const ring = impact.getObjectByName('V7_native_Shield01')!;
    const inner = impact.getObjectByName('V7_native_Shield01_inner')!;
    effects.update(2.7);
    const smoke = front.getObjectByName('V7_cannon_smoke') as THREE.Sprite;
    expect(smoke.visible).toBe(true); expect(smoke.material.opacity).toBeGreaterThan(.6);
    effects.update(8.6);
    expect(rays.visible).toBe(true); expect(rays.rotation.z).toBeCloseTo(Math.PI / 2);
    expect(ring.visible).toBe(false); expect(inner.visible).toBe(false);
    effects.update(8.85);
    expect(rays.visible).toBe(false); expect(ring.visible).toBe(true); expect(inner.visible).toBe(false);
    effects.update(9);
    expect(inner.visible).toBe(true);
    expect(impact.getObjectByName('V7_native_ShockWave01')!.visible).toBe(false);
    expect(impact.getObjectByName('V7_native_ShockWave02')!.visible).toBe(false);
    effects.update(9.55); const peak = ring.scale.z;
    effects.update(9.8);
    expect(ring.scale.z).toBeLessThan(peak); expect(ring.scale.z).toBeGreaterThan(peak * .8);
    effects.dispose();
  });
  it('ne montre pas de quad sans texture ni de remplacement procédural si la bibliothèque manque', () => {
    for (const missing of [false, true]) {
      const { root, front, source } = fixture(false);
      if (missing) source.removeFromParent();
      const effects = createV7Effects(root); effects.update(2.55);
      expect(front.getObjectByName('V7_cannon_effects')!.children.every(child => !child.visible)).toBe(true);
      effects.dispose();
    }
  });
  it('libère uniquement les copies des ressources et masque les effets en mouvements réduits', () => {
    const { root, front, source, texture, destroyed } = fixture();
    const dispose = vi.spyOn(texture, 'dispose');
    const effects = createV7Effects(root);
    const tail = front.getObjectByName('V7_native_Tail_FlowMain') as THREE.Mesh<THREE.BufferGeometry, THREE.MeshBasicMaterial>;
    const geometryDispose = vi.spyOn(tail.geometry, 'dispose');
    const mapDispose = vi.spyOn(tail.material.map!, 'dispose');
    effects.update(8, true);
    expect(destroyed.visible).toBe(false);
    expect(front.getObjectByName('V7_cannon_effects')!.children.every(child => !child.visible)).toBe(true);
    effects.dispose();
    expect(geometryDispose).toHaveBeenCalledOnce(); expect(mapDispose).toHaveBeenCalledOnce();
    expect(dispose).not.toHaveBeenCalled(); expect(source.visible).toBe(true);
  });
  it('préserve le placement des rochers derrière les coques', () => {
    const { root, front } = fixture();
    const hull = new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial()); front.add(hull);
    const stones = new THREE.Group(); stones.name = 'AMM_7_0_Stones_01'; root.add(stones);
    const rock = new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial()); stones.add(rock);
    const effects = createV7Effects(root);
    expect(rock.renderOrder).toBeGreaterThan(100); expect(rock.renderOrder).toBeLessThan(hull.renderOrder);
    expect(stones.position.x).toBe(6); effects.dispose();
  });
  it('préserve la brume, masque les anciens faisceaux et ne boucle pas les destructions', () => {
    const { root, destroyed } = fixture();
    const ray = new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial());
    ray.geometry.userData.element = 'GunRay_01'; destroyed.add(ray);
    const mist = new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial());
    mist.geometry.userData.element = 'Front_Myst_01'; root.add(mist);
    const effects = createV7Effects(root); effects.update(1);
    expect(mist.material.opacity).toBeCloseTo(.35); expect(ray.visible).toBe(false);
    effects.update(30); expect(destroyed.visible).toBe(false);
    effects.update(60); expect(destroyed.visible).toBe(false); effects.dispose();
  });
});
