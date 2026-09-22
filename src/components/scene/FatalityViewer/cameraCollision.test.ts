import { describe, it, expect } from 'vitest';
import * as THREE from 'three';
import { CameraCollider, CAMERA_GROUND_MARGIN, CAMERA_HARD_MARGIN, decorColliders } from './cameraCollision';

/** Terrain en pente douce (z = 0,1·x) de 40 m de côté, et un rocher de 2 m en (0, −5). */
function decor() {
  const root = new THREE.Group();
  const plane = new THREE.PlaneGeometry(40, 40, 8, 8);
  const pos = plane.attributes.position;
  for (let i = 0; i < pos.count; i += 1) pos.setZ(i, 0.1 * pos.getX(i));
  const ground = new THREE.Mesh(plane, new THREE.MeshBasicMaterial({ side: THREE.DoubleSide }));
  ground.name = 'ground';
  const rock = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2), new THREE.MeshBasicMaterial({ side: THREE.DoubleSide }));
  rock.position.set(0, -5, 1);
  const leaves = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2), new THREE.MeshBasicMaterial({ alphaTest: 0.5 }));
  leaves.position.set(5, -5, 1);
  root.add(ground, rock, leaves);
  return root;
}

function collider() {
  const { ground, obstacles } = decorColliders(decor());
  const c = new CameraCollider();
  c.setColliders(ground, obstacles);
  return { c, ground, obstacles };
}

describe('CameraCollider', () => {
  it('trie le décor : sol, obstacles opaques, feuillages traversables', () => {
    const { ground, obstacles } = collider();
    expect(ground).toHaveLength(1);
    expect(obstacles).toHaveLength(2);
  });

  it('mesure la hauteur réelle du terrain', () => {
    const { c } = collider();
    expect(c.groundHeight(10, 3)).toBeCloseTo(1, 3);
    expect(c.groundHeight(100, 0)).toBeNull();
  });

  it('relève la caméra au-dessus du sol, marge comprise', () => {
    const { c } = collider();
    const out = c.constrain(new THREE.Vector3(10, 10, 2), new THREE.Vector3(10, 16, 0.2), new THREE.Vector3());
    expect(out.z).toBeCloseTo(1 + CAMERA_GROUND_MARGIN, 3);
  });

  it('rapproche la caméra devant un obstacle entre elle et la cible', () => {
    const { c } = collider();
    const out = c.constrain(new THREE.Vector3(0, 0, 1), new THREE.Vector3(0, -10, 1), new THREE.Vector3());
    // Face du rocher à y = −4 : la caméra s'arrête avant, marge comprise.
    expect(out.y).toBeCloseTo(-4 + CAMERA_GROUND_MARGIN, 3);
  });

  it('laisse passer la caméra à travers les feuillages découpés', () => {
    const { c } = collider();
    const out = c.constrain(new THREE.Vector3(5, 0, 1), new THREE.Vector3(5, -10, 1), new THREE.Vector3());
    expect(out.y).toBeCloseTo(-10, 3);
  });

  it('lisse la correction sans jamais passer sous le sol', () => {
    const { c } = collider();
    const target = new THREE.Vector3(10, 10, 2);
    const wanted = new THREE.Vector3(10, 16, -3);
    const out = new THREE.Vector3();
    let settling = c.resolve(target, wanted, 1 / 60, out);
    expect(settling).toBe(true);
    expect(out.z).toBeGreaterThanOrEqual(1 + CAMERA_HARD_MARGIN - 1e-6);
    for (let i = 0; i < 120 && settling; i += 1) settling = c.resolve(target, wanted, 1 / 60, out);
    expect(settling).toBe(false);
    expect(out.z).toBeCloseTo(1 + CAMERA_GROUND_MARGIN, 2);
  });

  it('ne corrige rien sans décor', () => {
    const c = new CameraCollider();
    const out = new THREE.Vector3();
    expect(c.resolve(new THREE.Vector3(), new THREE.Vector3(0, -5, -2), 0.016, out)).toBe(false);
    expect(out.z).toBe(-2);
  });
});
