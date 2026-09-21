import * as THREE from 'three';
import { expect, it } from 'vitest';
import { createV7Intro } from './v7Intro';

it('garde les coques et réacteurs dans le même repère pendant chaque chute', () => {
  const root = new THREE.Group();
  const parent = new THREE.Group(); parent.name = 'AMM_7_0_Ships_Destroyed'; root.add(parent);
  const originals = ['SmalShip_destr_01', 'SmalShip_destr_02', 'Engine_Glow03', 'SmalShip_destr_03', 'SmalShip_destr_03_fire1', 'Engine_Glow04'].map(element => {
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial());
    mesh.geometry.userData.element = element; parent.add(mesh); return mesh;
  });
  const texture = new THREE.Texture({ width: 8, height: 8 });
  const intro = createV7Intro(root, { flame: texture, smoke: texture, projectile: texture });
  const ships = [1, 2, 3].map(id => root.getObjectByName(`V7_intro_ship_${id}`)!);
  intro.update(0, false);
  expect(originals.every(mesh => !mesh.visible)).toBe(true);
  expect(ships.every(ship => ship.userData.stage === 'intact')).toBe(true);
  expect(ships.every(ship => !ship.getObjectByName('V7_cannon_flame')!.visible)).toBe(true);
  intro.update(22, false);
  const hull = ships[1].children.find(child => (child as THREE.Mesh).geometry?.userData.element === 'SmalShip_destr_02')!;
  const engine = ships[1].children.find(child => (child as THREE.Mesh).geometry?.userData.element === 'Engine_Glow03')!;
  expect(hull.parent).toBe(engine.parent);
  expect(ships[1].position.z).toBeLessThan(0);
  expect(ships.map(ship => ship.userData.stage)).toEqual(['gone', 'falling', 'gone']);
  expect(ships[1].getObjectByName('V7_cannon_flame')!.visible).toBe(true);
  ships.forEach(ship => ship.traverse(object => {
    if ((object as THREE.Mesh).isMesh || (object as THREE.Sprite).isSprite) expect(object.renderOrder).toBeLessThan(200);
  }));
  intro.update(8, false);
  expect(ships.map(ship => ship.userData.stage)).toEqual(['intact', 'intact', 'falling']);
  intro.update(12, false);
  expect(ships.map(ship => ship.userData.stage)).toEqual(['falling', 'intact', 'falling']);
  intro.update(30, false); expect(parent.visible).toBe(false);
  intro.update(0, true); expect(parent.visible).toBe(false);
  intro.dispose();
  expect(originals.every(mesh => mesh.visible)).toBe(true);
  expect(parent.children).toHaveLength(originals.length);
});
