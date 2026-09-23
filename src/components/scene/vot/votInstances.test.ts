import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { VotFactory, partOpacity, updateInstance } from './votInstances';
import type { FatalityObject } from '@/components/scene/FatalityViewer/timeline';

const object = (over: Partial<FatalityObject>): FatalityObject => ({ fadeIn: 0, fadeOut: 0, scale: 1, duration: 0, loop: false, ...over });

describe('partOpacity', () => {
  it('fades a component in from its delayed start and out after its stop', () => {
    // Muse du Barde : apparue à 4,33 s (fadeInMS 1000), arrêtée à 7,8 s (fadeOutMS 500).
    const muse = { start: 4.33, stop: 7.8, end: 4.33 + 5.3333, fadeIn: 1, fadeOut: 0.5 };
    expect(partOpacity(muse, 4)).toBe(0);
    expect(partOpacity(muse, 4.83)).toBeCloseTo(0.5, 5);
    expect(partOpacity(muse, 6)).toBe(1);
    expect(partOpacity(muse, 8.05)).toBeCloseTo(0.5, 5);
    expect(partOpacity(muse, 8.4)).toBe(0);
  });

  it('ends an object whose clip does not loop at the end of its clip, with its fade-out', () => {
    // Lumière de la Muse : clip de 1,5 s posé à 7,87 s, fadeOutMS 800, jamais arrêtée.
    const light = { start: 7.87, stop: null, end: 7.87 + 1.5, fadeIn: 0, fadeOut: 0.8 };
    expect(partOpacity(light, 9)).toBe(1);
    expect(partOpacity(light, 9.77)).toBeCloseTo(0.5, 5);
    expect(partOpacity(light, 10.5)).toBe(0);
  });

  it('keeps an object without end alive, and ignores the root fade-in (set by its action)', () => {
    expect(partOpacity({ start: 0, stop: null, end: null, fadeIn: 1, fadeOut: 1 }, 100, true)).toBe(1);
    expect(partOpacity({ start: 0, stop: null, end: null, fadeIn: 1, fadeOut: 1 }, 0.1, true)).toBe(1);
  });
});

describe('VotFactory lifetimes', () => {
  const build = () => {
    const root = new THREE.Group();
    root.userData = { vot: 'Parent' };
    const child = new THREE.Group();
    child.userData = { vot: 'Child', window: [1, null] };
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial({ transparent: true }));
    child.add(mesh);
    root.add(child);
    const objects = { Parent: object({ duration: 10, loop: true }), Child: object({ duration: 2, fadeOut: 0.5 }) };
    const factory = new VotFactory({ objects, baseUrl: null, disposables: [], lifetimes: true });
    return factory.instantiate(root, [], 0, 10, 0, 0);
  };

  it('hides a non-looping component once its clip and fade-out are over', () => {
    const inst = build();
    const camera = new THREE.PerspectiveCamera();
    const childNode = inst.root.children[0];
    const material = (childNode.children[0] as THREE.Mesh).material as THREE.Material;
    updateInstance(inst, 0.5, 1, camera);
    expect(childNode.visible).toBe(false);
    updateInstance(inst, 2, 1, camera);
    expect(childNode.visible).toBe(true);
    expect(material.opacity).toBeCloseTo(1, 5);
    updateInstance(inst, 3.25, 1, camera);
    expect(material.opacity).toBeCloseTo(0.5, 5);
    updateInstance(inst, 4, 1, camera);
    expect(childNode.visible).toBe(false);
    expect(inst.root.visible).toBe(true);
  });
});
