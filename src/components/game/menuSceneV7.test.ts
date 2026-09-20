import { describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import { createV7Effects } from './menuSceneV7';

function fixture() {
  const root = new THREE.Group();
  const front = new THREE.Group(); front.name = 'AMM_7_0_FrontShips'; root.add(front);
  const destroyed = new THREE.Group(); destroyed.name = 'AMM_7_0_Ships_Destroyed'; root.add(destroyed);
  const ray = new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial());
  ray.geometry.userData.element = 'GunRay_01'; destroyed.add(ray);
  return { root, front, destroyed, ray };
}

describe('V7 menu effects', () => {
  it('anime les flammes puis le flash et la membrane, et libère leurs ressources', () => {
    const { root, front } = fixture();
    const texture = new THREE.Texture({ width: 64, height: 64 });
    const effects = createV7Effects(root, { projectile: texture, flame: texture, electric: texture, spark: texture });
    const group = front.getObjectByName('V7_cannon_effects')!;
    const flame = group.getObjectByName('V7_cannon_flame') as THREE.Mesh<THREE.PlaneGeometry, THREE.ShaderMaterial>;
    const membrane = group.getObjectByName('V7_cannon_membrane') as typeof flame;
    const flash = group.getObjectByName('V7_cannon_flash')!;
    effects.update(3.1);
    expect(flame.visible).toBe(true); expect(membrane.visible).toBe(false);
    expect(group.children.filter(o => o.name === 'V7_cannon_projectile' && o.visible)).toHaveLength(3);
    effects.update(3.4);
    expect(flame.visible).toBe(false); expect(flash.visible).toBe(true); expect(membrane.visible).toBe(true);
    const opacity = membrane.material.uniforms.opacity.value;
    effects.update(3.7);
    expect(flash.visible).toBe(false);
    expect(membrane.material.uniforms.opacity.value).toBeLessThan(opacity);
    expect(membrane.material.uniforms.time.value).toBe(3.7);
    effects.update(4.7);
    expect(flash.visible).toBe(false);
    expect(membrane.visible).toBe(true);
    expect(membrane.material.uniforms.regeneration.value).toBe(1);
    expect(membrane.material.uniforms.phase.value).toBeCloseTo(.5);
    expect(membrane.material.uniforms.opacity.value).toBeCloseTo(1.35);
    effects.update(5.31);
    expect(membrane.visible).toBe(false);
    effects.update(6.45);
    expect(group.children.filter(o => o.name === 'V7_cannon_projectile' && o.visible)).toHaveLength(3);
    effects.update(6.45, true);
    expect(group.children.every(o => !o.visible)).toBe(true);
    const geometryDispose = vi.spyOn(membrane.geometry, 'dispose');
    const materialDispose = vi.spyOn(membrane.material, 'dispose');
    const textureDispose = vi.spyOn(texture, 'dispose');
    effects.dispose();
    expect(geometryDispose).toHaveBeenCalledOnce(); expect(materialDispose).toHaveBeenCalledOnce();
    expect(textureDispose).not.toHaveBeenCalled(); // appartient au chargeur de scène
  });
  it('masque aussi la membrane tant que sa texture électrique n’est pas chargée', () => {
    const { root, front } = fixture();
    const effects = createV7Effects(root, { electric: new THREE.Texture(), flame: new THREE.Texture() });
    effects.update(3.4);
    expect(front.getObjectByName('V7_cannon_effects')!.children.every(o => !o.visible)).toBe(true);
    effects.dispose();
  });
  it('place les rochers derrière les coques, sans les enfouir dans le dôme', () => {
    const { root, front } = fixture();
    const hull = new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial());
    hull.renderOrder = -475; front.add(hull);
    const stones = new THREE.Group(); stones.name = 'AMM_7_0_Stones_01'; root.add(stones);
    const rock = new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial());
    rock.renderOrder = -615; stones.add(rock);
    const effects = createV7Effects(root);
    expect(rock.renderOrder).toBeGreaterThan(100);
    expect(rock.renderOrder).toBeLessThan(hull.renderOrder);
    expect(stones.position.x).toBe(6);
    effects.dispose();
  });
  it('retire les faisceaux et ne rejoue pas les destructions après l’introduction', () => {
    const { root, destroyed, ray } = fixture();
    const effects = createV7Effects(root);
    effects.update(1); expect(destroyed.visible).toBe(true); expect(ray.visible).toBe(false);
    effects.update(28); expect(destroyed.visible).toBe(false);
    effects.update(60); expect(destroyed.visible).toBe(false);
    effects.dispose();
  });
  it('enchaîne bouche du canon, projectile et impact puis masque les effets', () => {
    const { root, front } = fixture();
    const texture = new THREE.Texture({ width: 64, height: 64 });
    const effects = createV7Effects(root, { projectile: texture, muzzle: texture, impact: texture, shield: texture });
    const group = front.getObjectByName('V7_cannon_effects')!;
    const [projectile, muzzle, impact, shield, trail] = group.children;
    effects.update(0); expect(group.children.every(child => !child.visible)).toBe(true);
    effects.update(2.55); expect(muzzle.visible).toBe(true); expect(projectile.visible).toBe(true); expect(impact.visible).toBe(false);
    const position = projectile.position.clone();
    effects.update(3); expect(projectile.position.distanceTo(position)).toBeGreaterThan(10); expect(muzzle.visible).toBe(false);
    expect(trail.visible).toBe(true);
    expect(trail.scale.x).toBeGreaterThan(trail.scale.y * 10);
    effects.update(3.5); expect(projectile.visible).toBe(false); expect(impact.visible).toBe(true);
    expect(trail.visible).toBe(false);
    expect(impact.scale.y).toBeGreaterThan(impact.scale.x * 2);
    expect(shield.scale.y).toBeGreaterThan(shield.scale.x * 2);
    effects.update(4.8); expect(group.children.every(child => !child.visible)).toBe(true);
    effects.dispose(); expect(front.children).toHaveLength(0);
  });
  it('ne montre ni tirs ni destructions avec les mouvements réduits', () => {
    const { root, front, destroyed } = fixture(); const effects = createV7Effects(root);
    effects.update(3, true);
    expect(destroyed.visible).toBe(false);
    expect(front.getObjectByName('V7_cannon_effects')!.children.every(child => !child.visible)).toBe(true);
    effects.dispose();
  });
  it('ne rend jamais un sprite sans texture chargée', () => {
    const { root, front } = fixture();
    const effects = createV7Effects(root, { projectile: new THREE.Texture() });
    effects.update(2.55);
    expect(front.getObjectByName('V7_cannon_effects')!.children.every(child => !child.visible)).toBe(true);
    effects.dispose();
  });
  it('lit les extras glTF sur la géométrie pour les textures et la brume', () => {
    const { root, front } = fixture();
    const texture = new THREE.Texture({ width: 64, height: 64 });
    const engine = new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial({ map: texture }));
    engine.geometry.userData.element = 'Engine_Glow01'; root.add(engine);
    const mist = new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial());
    mist.geometry.userData.element = 'Front_Myst_01'; root.add(mist);
    const effects = createV7Effects(root);
    expect(mist.material.opacity).toBeCloseTo(.35);
    effects.update(2.55);
    const projectile = front.getObjectByName('V7_cannon_effects')!.children[0] as THREE.Sprite;
    expect(projectile.material.map).toBe(texture);
    expect(projectile.visible).toBe(true);
    effects.dispose();
  });
});
