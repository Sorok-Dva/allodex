import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { FOG_FAR, FOG_NEAR, applyV5Fog, restoreOpaqueVertexAlpha } from './v5Atmosphere';

function mesh(parent: THREE.Object3D, element: string, alpha: number, blending: THREE.Blending = THREE.NormalBlending) {
  const geometry = new THREE.PlaneGeometry();
  const count = geometry.getAttribute('position').count;
  const color = new Float32Array(count * 4);
  for (let i = 0; i < count; i += 1) color.set([1, 1, 1, alpha], i * 4);
  geometry.setAttribute('color', new THREE.BufferAttribute(color, 4));
  geometry.userData.element = element;
  const material = new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true, blending });
  material.depthTest = false; material.depthWrite = false; material.fog = false;
  const result = new THREE.Mesh(geometry, material);
  parent.add(result);
  return result;
}

describe('V5 brouillard', () => {
  it('pose un brouillard linéaire sur la scène et l’active sur les seuls matériaux non additifs', () => {
    const scene = new THREE.Scene();
    const root = new THREE.Group(); scene.add(root);
    const tower = mesh(root, 'Tower', 1);
    const glow = mesh(root, 'Glow_L', 1, THREE.AdditiveBlending);
    const fog = applyV5Fog(root, '#3d4da9');
    expect(fog.count).toBe(1);
    expect(scene.fog).toBeInstanceOf(THREE.Fog);
    expect((scene.fog as THREE.Fog).near).toBe(FOG_NEAR);
    expect((scene.fog as THREE.Fog).far).toBe(FOG_FAR);
    expect((scene.fog as THREE.Fog).color.getHexString()).toBe('3d4da9');
    expect(tower.material.fog).toBe(true);
    expect(glow.material.fog).toBe(false);
    fog.dispose();
    expect(scene.fog).toBeNull();
    expect(tower.material.fog).toBe(false);
  });

  it('ne fait rien quand la racine n’est pas encore montée dans une scène', () => {
    const root = new THREE.Group();
    mesh(root, 'Tower', 1);
    expect(applyV5Fog(root, 0x000000).count).toBe(0);
  });
});

describe('V5 sommets à alpha nul', () => {
  it('rend opaques les seules primitives dont tous les sommets ont un alpha nul', () => {
    const root = new THREE.Group();
    const hull = mesh(root, 'Ship', 0);
    const rock = mesh(root, 'Allods', 0);
    const cloud = mesh(root, 'Fog_01', 0.5);
    const fixed = restoreOpaqueVertexAlpha(root);
    expect(fixed.count).toBe(2);
    for (const opaque of [hull, rock]) {
      expect(opaque.material.vertexColors).toBe(false);
      expect(opaque.material.transparent).toBe(false);
      expect(opaque.material.depthTest).toBe(true);
      expect(opaque.material.depthWrite).toBe(true);
    }
    expect(cloud.material.vertexColors).toBe(true);
    expect(cloud.material.transparent).toBe(true);
    fixed.dispose();
    expect(hull.material.vertexColors).toBe(true);
    expect(hull.material.depthWrite).toBe(false);
  });
});
