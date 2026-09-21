import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { NATIVE_ORDER_BASE, applyNativeDrawOrder } from './v6SceneLayers';

function primitive(parent: THREE.Object3D, element: string, order: number) {
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial());
  mesh.geometry.userData.element = element;
  mesh.renderOrder = order;
  parent.add(mesh);
  return mesh;
}

describe('V6 native draw order', () => {
  it('peint les primitives du maillage dans l\'ordre du xdb, quel que soit le tri par profondeur', () => {
    const root = new THREE.Group();
    const group = new THREE.Group(); group.name = 'Animated_Background_6_0_mesh'; root.add(group);
    // `sortByDepth` met le versant (plus proche en moyenne) après le laboratoire : à l'inverse du client.
    const sky = primitive(group, 'Sky_Back', -97.8);
    const slope = primitive(group, 'Mountains_04', -82.4);
    const lab = primitive(group, 'Lab', -85.1);
    const train = primitive(group, 'Train', -47);
    expect(applyNativeDrawOrder(root)).toBe(4);
    expect(sky.renderOrder).toBe(NATIVE_ORDER_BASE);
    expect(slope.renderOrder).toBeLessThan(lab.renderOrder);
    expect(lab.renderOrder).toBeLessThan(train.renderOrder);
  });
  it('ignore les groupes sans élément nommé et les maillages isolés', () => {
    const root = new THREE.Group();
    const lone = primitive(root, 'Only', -5);
    const plain = new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial());
    plain.renderOrder = -3; root.add(plain);
    expect(applyNativeDrawOrder(root)).toBe(0);
    expect(lone.renderOrder).toBe(-5);
    expect(plain.renderOrder).toBe(-3);
  });
});
