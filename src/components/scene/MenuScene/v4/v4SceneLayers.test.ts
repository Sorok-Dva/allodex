import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { prepareV4Layers } from './v4SceneLayers';

function mesh(parent: THREE.Object3D, element: string, depthOrder: number) {
  const result = new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial());
  result.geometry.userData.element = element;
  result.renderOrder = depthOrder; // ce que `sortByDepth` aurait posé
  parent.add(result);
  return result;
}

describe('V4 scene layers', () => {
  it("peint les éléments dans l'ordre du fichier, le dôme d'abord, quelle que soit leur profondeur", () => {
    const root = new THREE.Group();
    const group = new THREE.Group(); group.name = 'Animated_Background_mesh'; root.add(group);
    // Ordre natif : dôme, île, soleil (plus proche de la caméra), château, nuages de premier plan.
    const dome = mesh(group, 'Back3', -150);
    const land = mesh(group, 'Land1', -220);
    const sun = mesh(group, 'Sun', -178);
    const castle = mesh(group, 'castle', -222);
    const clouds = mesh(group, 'Clouds_019', -143);
    prepareV4Layers(root);
    expect([dome, land, sun, castle, clouds].map(m => m.renderOrder)).toEqual([0, 1, 2, 3, 4]);
    expect(sun.renderOrder).toBeLessThan(castle.renderOrder);
    expect(dome.renderOrder).toBeLessThan(land.renderOrder);
  });
  it('ignore les nœuds qui ne sont pas des maillages (articulations du squelette)', () => {
    const root = new THREE.Group();
    const group = new THREE.Group(); root.add(group);
    const joint = new THREE.Bone(); group.add(joint);
    const first = mesh(group, 'Back2', -148);
    const second = mesh(group, 'Water', -134);
    prepareV4Layers(root);
    expect(first.renderOrder).toBe(0);
    expect(second.renderOrder).toBe(1);
    expect(joint.renderOrder).toBe(0);
  });
});
