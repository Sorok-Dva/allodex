import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { VotFactory, partOpacity, updateInstance } from './votInstances';
import { elementAlphaAt, type FatalityObject } from '@/components/scene/FatalityViewer/timeline';

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

describe('component death', () => {
  it('lets a component outlive its parent by its own fade-out, not the parent one', () => {
    // Mage : socle `FatalityMage` (vie 7,6 s, fadeOutMS 800), météore accroché (fadeOutMS 3500).
    const root = new THREE.Group();
    root.userData = { vot: 'Base' };
    root.add(new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial({ transparent: true })));
    const child = new THREE.Group();
    child.userData = { vot: 'Meteor' };
    child.add(new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial({ transparent: true })));
    root.add(child);
    const objects = { Base: object({ duration: 11.6667, fadeOut: 0.8 }), Meteor: object({ duration: 13.3333, fadeOut: 3.5 }) };
    const inst = new VotFactory({ objects, baseUrl: null, disposables: [], lifetimes: true }).instantiate(root, [], 0, 7.6, 3, 0.8);
    const camera = new THREE.PerspectiveCamera();
    const base = (inst.root.children[0] as THREE.Mesh).material as THREE.Material;
    const meteor = (inst.root.children[1].children[0] as THREE.Mesh).material as THREE.Material;
    // L'entrée de l'action (3 s) vaut pour tout le gabarit.
    updateInstance(inst, 1.5, 0.5, camera);
    expect(meteor.opacity).toBeCloseTo(0.5, 5);
    updateInstance(inst, 9.35, 0, camera);
    expect(inst.root.visible).toBe(true);
    expect(base.opacity).toBe(0);
    expect(meteor.opacity).toBeCloseTo(0.5, 5);
    updateInstance(inst, 11.2, 0, camera);
    expect(inst.root.visible).toBe(false);
    updateInstance(inst, 5, 1, camera, false);
    expect(inst.root.visible).toBe(false);
  });

  it('blends an opaque material while it fades', () => {
    const root = new THREE.Group();
    root.userData = { vot: 'Angel' };
    root.add(new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial()));
    const inst = new VotFactory({ objects: { Angel: object({}) }, baseUrl: null, disposables: [], lifetimes: true }).instantiate(root, [], 0, 5, 0, 1);
    const material = (inst.root.children[0] as THREE.Mesh).material as THREE.Material;
    const camera = new THREE.PerspectiveCamera();
    updateInstance(inst, 2, 1, camera);
    expect(material.transparent).toBe(false);
    updateInstance(inst, 5.5, 0.5, camera);
    expect(material.transparent).toBe(true);
    expect(material.opacity).toBeCloseTo(0.5, 5);
  });
});

describe('element transparency tracks', () => {
  it('hides a frozen element outside its keys and fades it with the clip time', () => {
    // Instruments du Barde : pleins jusqu'à 5,7 s, fondus jusqu'à 5,9 s ; clip bouclé de 11,67 s.
    const root = new THREE.Group();
    root.userData = { vot: 'FatalityBard' };
    const geometry = new THREE.PlaneGeometry();
    geometry.userData.element = 'Drum_mesh';
    const drum = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial());
    const other = new THREE.Mesh(new THREE.PlaneGeometry(), new THREE.MeshBasicMaterial());
    root.add(drum, other);
    const objects = { FatalityBard: object({ duration: 11.6667, loop: true, elementAlpha: { Drum_mesh: [0, 1, 5.7, 1, 5.9, 0, 11.6667, 0] } }) };
    const inst = new VotFactory({ objects, baseUrl: null, disposables: [], lifetimes: true }).instantiate(root, [], 0, 11.6, 0, 0);
    const camera = new THREE.PerspectiveCamera();
    const [shownDrum, shownOther] = inst.root.children as THREE.Mesh[];
    const material = shownDrum.material as THREE.Material;
    updateInstance(inst, 3, 1, camera);
    expect(shownDrum.visible).toBe(true);
    expect(material.opacity).toBeCloseTo(1, 5);
    expect(material.transparent).toBe(false);
    updateInstance(inst, 5.8, 1, camera);
    expect(material.opacity).toBeCloseTo(0.5, 5);
    expect(material.transparent).toBe(true);
    updateInstance(inst, 8, 1, camera);
    expect(shownDrum.visible).toBe(false);
    expect(shownOther.visible).toBe(true);
    updateInstance(inst, 3, 1, camera);
    expect(shownDrum.visible).toBe(true);
    expect(material.transparent).toBe(false);
  });
});

describe('elementAlphaAt', () => {
  it('interpolates flat [t, a] keys and clamps outside them', () => {
    const keys = [0, 0, 1, 1, 3, 0];
    expect(elementAlphaAt(keys, -1)).toBe(0);
    expect(elementAlphaAt(keys, 0.5)).toBeCloseTo(0.5, 6);
    expect(elementAlphaAt(keys, 2)).toBeCloseTo(0.5, 6);
    expect(elementAlphaAt(keys, 9)).toBe(0);
    expect(elementAlphaAt([], 1)).toBe(1);
  });
});
