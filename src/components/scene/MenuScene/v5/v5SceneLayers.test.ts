import { describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import { findByNodeName, prepareV5Scroll, prepareV5Ship } from './v5SceneLayers';

function mesh(parent: THREE.Object3D, element: string, order: number, map: THREE.Texture | null = new THREE.Texture()) {
  const result = new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial({ map }));
  result.geometry.userData.element = element;
  result.renderOrder = order;
  parent.add(result);
  return result;
}

describe('V5 défilement UV natif', () => {
  it('fait défiler chaque matériau sur sa propre texture, dans le sens des UV du fichier', () => {
    const root = new THREE.Group();
    const shared = new THREE.Texture();
    const clouds = mesh(root, 'Front_Clouds1', -100, shared);
    const blink = mesh(root, 'Tower_blink', -80, shared);
    blink.geometry.userData.uvScroll = [0, 0.02];
    const lightning = mesh(root, 'lightning_01', -80);
    lightning.geometry.userData.uvScroll = [1, 0];
    const still = mesh(root, 'Tower', -80);
    still.geometry.userData.uvScroll = [0, 0];
    const scroll = prepareV5Scroll(root);
    expect(scroll.count).toBe(2);
    const moving = blink.material.map!;
    expect(moving).not.toBe(shared);
    expect(moving.wrapT).toBe(THREE.RepeatWrapping);
    scroll.update(10, false);
    expect(moving.offset.y).toBeCloseTo(0.2);
    expect(lightning.material.map!.offset.x).toBeCloseTo(0); // 10 tours entiers
    scroll.update(10.25, false);
    expect(lightning.material.map!.offset.x).toBeCloseTo(0.25);
    expect(clouds.material.map!.offset.toArray()).toEqual([0, 0]); // la texture partagée ne bouge pas
    scroll.update(10, true);
    expect(moving.offset.y).toBe(0); // mouvements réduits : image fixe
    const dispose = vi.spyOn(moving, 'dispose');
    scroll.dispose();
    expect(dispose).toHaveBeenCalledOnce();
    expect(blink.material.map).toBe(shared);
  });
});

describe('V5 navire de raid', () => {
  function scene() {
    const root = new THREE.Group();
    const tower = mesh(root, 'Tower', -80);
    const ship = new THREE.Group(); ship.name = 'Raid_Ship'; root.add(ship);
    const bone = new THREE.Bone(); bone.name = 'Raid_ShipShip'; ship.add(bone); // nom nettoyé par GLTFLoader
    const hull = mesh(ship, 'Ship', -35);
    const sail = mesh(ship, 'group_Sails03', -34);
    return { root, tower, ship, bone, hull, sail };
  }
  const camera = { position: [135, 0, 0], target: [55, 0, 0] };

  it('retrouve un nœud par son nom natif ou nettoyé', () => {
    const { root, bone } = scene();
    expect(findByNodeName(root, 'Raid_Ship/Ship')).toBe(bone);
    expect(findByNodeName(root, 'Raid_Ship')).toBe(root.getObjectByName('Raid_Ship'));
  });

  it('reclasse le navire selon la profondeur courante de son articulation racine', () => {
    const { root, tower, bone, hull, sail } = scene();
    const layers = prepareV5Ship(root, camera);
    expect(layers.count).toBe(2);
    bone.position.set(100, 0, 0); // premier passage : 35 unités devant la caméra, avant la tour (80)
    layers.update();
    expect(hull.renderOrder).toBeGreaterThan(tower.renderOrder);
    expect(sail.renderOrder).toBeGreaterThan(hull.renderOrder); // ordre relatif des pièces conservé
    bone.position.set(-15, 0, 0); // second passage : 150 unités, derrière la tour
    layers.update();
    expect(hull.renderOrder).toBeLessThan(tower.renderOrder);
    expect(hull.renderOrder).toBeCloseTo(-150, 0);
  });

  it('reste inerte sans navire dans la scène', () => {
    const root = new THREE.Group();
    const layers = prepareV5Ship(root, camera);
    expect(layers.count).toBe(0);
    expect(() => layers.update()).not.toThrow();
  });
});
