import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { boundToDefaultJointOnly, freezeLandscape } from './v6Landscape';

/** Squelette à deux os : l'os 0 (drapeau) s'agite, l'os 1 (train) aussi. */
function scene() {
  const root = new THREE.Group();
  const object = new THREE.Group(); object.name = 'Animated_Background_6_0'; root.add(object);
  const flagJoint = new THREE.Bone(); flagJoint.name = 'joint5_joint6'; flagJoint.position.set(-41, 49, 47); object.add(flagJoint);
  const trainJoint = new THREE.Bone(); trainJoint.name = 'Train'; trainJoint.position.set(-36, -22, 9); object.add(trainJoint);
  const group = new THREE.Group(); group.name = 'Animated_Background_6_0_mesh'; object.add(group);
  root.updateMatrixWorld(true);
  const skeleton = new THREE.Skeleton([flagJoint, trainJoint]);
  const make = (element: string, joint: number, order: number) => {
    const geometry = new THREE.PlaneGeometry(2, 4);
    geometry.userData.element = element;
    const count = geometry.getAttribute('position').count;
    geometry.setAttribute('skinIndex', new THREE.Uint16BufferAttribute(Array(count).fill([joint, 0, 0, 0]).flat(), 4));
    geometry.setAttribute('skinWeight', new THREE.Float32BufferAttribute(Array(count).fill([1, 0, 0, 0]).flat(), 4));
    const mesh = new THREE.SkinnedMesh(geometry, new THREE.MeshBasicMaterial({ transparent: true }));
    mesh.name = element; mesh.renderOrder = order; group.add(mesh);
    mesh.bind(skeleton);
    return mesh;
  };
  return { root, group, flagJoint, trainJoint, sky: make('Sky_Back', 0, 0), train: make('Train', 1, 42) };
}
function worldPoint(mesh: THREE.Mesh, index: number) {
  mesh.updateWorldMatrix(true, false);
  return mesh.localToWorld(new THREE.Vector3().fromBufferAttribute(mesh.geometry.getAttribute('position') as THREE.BufferAttribute, index));
}

describe('V6 landscape', () => {
  it('reconnaît les primitives skinnées sur le seul os par défaut', () => {
    const { sky, train } = scene();
    expect(boundToDefaultJointOnly(sky.geometry)).toBe(true);
    expect(boundToDefaultJointOnly(train.geometry)).toBe(false);
    expect(boundToDefaultJointOnly(new THREE.PlaneGeometry())).toBe(false);
  });
  it('fige le décor dans sa pose de départ et laisse le train suivre son os', () => {
    const { root, group, flagJoint, trainJoint, sky, train } = scene();
    const frozen = freezeLandscape(root);
    expect(frozen.count).toBe(1);
    const rigid = group.children.find(child => (child as THREE.Mesh).isMesh && !(child as THREE.SkinnedMesh).isSkinnedMesh) as THREE.Mesh;
    expect(rigid).toBeDefined(); expect(sky.visible).toBe(false); expect(train.visible).toBe(true);
    expect(rigid.material).toBe(sky.material); expect(rigid.renderOrder).toBe(0);
    expect(rigid.geometry.userData.element).toBe('Sky_Back');
    expect(rigid.geometry.getAttribute('skinIndex')).toBeUndefined();
    const before = worldPoint(rigid, 0).clone();
    expect(before.y).toBeCloseTo(2); // pose de départ = géométrie stockée
    // Le drapeau s'agite : le décor figé ne bouge pas ; le train suit toujours son os.
    flagJoint.rotation.x = 0.4; trainJoint.position.z += 3; root.updateMatrixWorld(true);
    expect(worldPoint(rigid, 0).distanceTo(before)).toBeCloseTo(0);
    train.skeleton.update();
    expect(train.getVertexPosition(0, new THREE.Vector3()).z).toBeCloseTo(3);
    frozen.dispose();
    expect(group.children).not.toContain(rigid); expect(sky.visible).toBe(true);
  });
});
