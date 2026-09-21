import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { freezeEngineTrails } from './v7Engines';

/** Navire à deux os : la racine porte le tangage, l'articulation secondaire agite la traînée. */
function ship(root: THREE.Object3D, name: string, element = 'Engine_Back01') {
  const group = new THREE.Group(); group.name = `AMM_7_0_${name}`; root.add(group);
  const visual = new THREE.Group(); visual.name = `AMM_7_0_${name}/VisualSceneNode`; group.add(visual);
  const hull = new THREE.Bone(); hull.name = `AMM_7_0_${name}/Ship_l1`; hull.position.set(10, 0, 0); visual.add(hull);
  const joint = new THREE.Bone(); joint.name = `AMM_7_0_${name}/Ship_l1_group2_C01_C02`; joint.position.set(0, 2, 0); hull.add(joint);
  const geometry = new THREE.PlaneGeometry(2, 4);
  geometry.userData.element = element;
  const count = geometry.getAttribute('position').count;
  geometry.setAttribute('skinIndex', new THREE.Uint16BufferAttribute(Array(count).fill([1, 0, 0, 0]).flat(), 4));
  geometry.setAttribute('skinWeight', new THREE.Float32BufferAttribute(Array(count).fill([1, 0, 0, 0]).flat(), 4));
  const mesh = new THREE.SkinnedMesh(geometry, new THREE.MeshBasicMaterial({ transparent: true, opacity: .7 }));
  mesh.name = `${name}_engine`; mesh.renderOrder = -640; visual.add(mesh);
  root.updateMatrixWorld(true);
  mesh.bind(new THREE.Skeleton([hull, joint]));
  return { group, visual, hull, joint, mesh };
}
function worldPoint(mesh: THREE.Mesh, index: number) {
  mesh.updateWorldMatrix(true, false);
  const v = new THREE.Vector3().fromBufferAttribute(mesh.geometry.getAttribute('position') as THREE.BufferAttribute, index);
  return mesh.localToWorld(v);
}

describe('V7 engine trails', () => {
  it('fige la traînée dans sa pose de départ et la rattache à la racine du navire', () => {
    const root = new THREE.Group();
    const { visual, hull, joint, mesh } = ship(root, 'FrontShips');
    const frozen = freezeEngineTrails(root);
    expect(frozen.count).toBe(1);
    const rigid = hull.children.find(child => (child as THREE.Mesh).isMesh) as THREE.Mesh;
    expect(rigid).toBeDefined(); expect(mesh.visible).toBe(false);
    expect(rigid.material).toBe(mesh.material); expect(rigid.renderOrder).toBe(-640);
    expect(rigid.geometry.userData.element).toBe('Engine_Back01');
    expect(rigid.geometry.getAttribute('skinIndex')).toBeUndefined();
    // Même position de départ que le maillage skinné, mais dans l'espace de la coque.
    const before = worldPoint(rigid, 0).clone();
    expect(before.y).toBeCloseTo(2); // pose de liaison : sommet du plan à y=+2, inchangé
    // L'articulation secondaire s'agite : la traînée rigide ne bouge pas.
    joint.position.y = 5; root.updateMatrixWorld(true);
    expect(worldPoint(rigid, 0).distanceTo(before)).toBeCloseTo(0);
    // La coque tangue : la traînée suit en bloc.
    hull.position.y += 1.5; root.updateMatrixWorld(true);
    expect(worldPoint(rigid, 0).y).toBeCloseTo(before.y + 1.5);
    expect(visual.children).toContain(mesh);
    frozen.dispose();
    expect(hull.children).not.toContain(rigid); expect(mesh.visible).toBe(true);
  });
  it('laisse l\'intro gérer les réacteurs des coques détruites et ignore les autres calques', () => {
    const root = new THREE.Group();
    ship(root, 'Ships_Destroyed');
    ship(root, 'Ships_Attack', 'Ship_L');
    const frozen = freezeEngineTrails(root);
    expect(frozen.count).toBe(0);
    frozen.dispose();
  });
});
