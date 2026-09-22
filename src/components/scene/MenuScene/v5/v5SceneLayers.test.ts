import { describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import { findByNodeName, prepareV5Layers, prepareV5Scroll, prepareV5Ship } from './v5SceneLayers';

function mesh(parent: THREE.Object3D, element: string, order: number, map: THREE.Texture | null = new THREE.Texture(), x = 0) {
  const result = new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial({ map }));
  result.geometry.userData.element = element;
  result.renderOrder = order;
  result.position.x = x;
  parent.add(result);
  return result;
}

describe('V5 ordre de peinture natif (sortMode OFFSETS)', () => {
  it('donne à chaque primitive son rang parmi ses frères, dans l’ordre du fichier', () => {
    const root = new THREE.Group();
    const group = new THREE.Group(); root.add(group);
    const bowl = mesh(group, 'Back6', -70);   // le tri par profondeur l'aurait mis loin derrière…
    const fog = mesh(group, 'Fog_01', -26);
    const tower = mesh(group, 'Tower', -80);
    const blink = mesh(group, 'Tower_blink', -83);
    expect(prepareV5Layers(root)).toBe(4);
    expect([bowl, fog, tower, blink].map(m => m.renderOrder)).toEqual([0, 1, 2, 3]);
  });
});

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

  it('suit le retournement vertical des textures du client (repeat.y = -1, offset.y = 1)', () => {
    const root = new THREE.Group();
    const flipped = new THREE.Texture();
    flipped.repeat.y = -1; flipped.offset.y = 1;
    const blink = mesh(root, 'Tower_blink', -80, flipped);
    blink.geometry.userData.uvScroll = [0, 0.02];
    const scroll = prepareV5Scroll(root);
    scroll.update(10, false);
    expect(blink.material.map!.offset.y).toBeCloseTo(0.8); // +0,2 tour vers le haut de l'image
    expect(blink.material.map!.repeat.y).toBe(-1);
  });
});

describe('V5 navire de raid', () => {
  // Caméra du manifeste : sur l'axe du bol, regardant -X ; la tour est à 79 unités.
  const camera = { position: [27, -1, -2], target: [-52, -1, 1.82] };
  function scene() {
    const root = new THREE.Group();
    const group = new THREE.Group(); root.add(group);
    const bowl = mesh(group, 'Back6', 0, new THREE.Texture(), -90);
    const tower = mesh(group, 'Tower', 1, new THREE.Texture(), -52);
    const fog = mesh(group, 'Fog_01', 2, new THREE.Texture(), -2);
    const ship = new THREE.Group(); ship.name = 'Raid_Ship'; root.add(ship);
    const bone = new THREE.Bone(); bone.name = 'Raid_ShipShip'; ship.add(bone); // nom nettoyé par GLTFLoader
    const hull = mesh(ship, 'Ship', 0);
    const sail = mesh(ship, 'group_Sails03', 1);
    return { root, bowl, tower, fog, ship, bone, hull, sail };
  }

  it('retrouve un nœud par son nom natif ou nettoyé', () => {
    const { root, bone } = scene();
    expect(findByNodeName(root, 'Raid_Ship/Ship')).toBe(bone);
    expect(findByNodeName(root, 'Raid_Ship')).toBe(root.getObjectByName('Raid_Ship'));
  });

  it('peint le navire juste avant la tour quand il est derrière elle, après tout le décor sinon', () => {
    const { root, bowl, tower, fog, bone, hull, sail } = scene();
    const layers = prepareV5Ship(root, camera);
    expect(layers.count).toBe(2);
    expect(layers.towerDepth).toBeGreaterThan(78);
    expect(layers.towerDepth).toBeLessThan(82);
    bone.position.set(-87, 20, -15); // 40 s : derrière la tour, devant le fond
    layers.update();
    expect(hull.renderOrder).toBeGreaterThan(bowl.renderOrder);
    expect(hull.renderOrder).toBeLessThan(tower.renderOrder);
    expect(sail.renderOrder).toBeGreaterThan(hull.renderOrder); // ordre relatif des pièces conservé
    expect(sail.renderOrder).toBeLessThan(tower.renderOrder);
    bone.position.set(-2, 26, -5); // 70 s : au premier plan
    layers.update();
    expect(hull.renderOrder).toBeGreaterThan(fog.renderOrder);
    expect(sail.renderOrder).toBeGreaterThan(hull.renderOrder);
  });

  it('reste inerte sans navire dans la scène', () => {
    const root = new THREE.Group();
    const layers = prepareV5Ship(root, camera);
    expect(layers.count).toBe(0);
    expect(() => layers.update()).not.toThrow();
  });
});
