import * as THREE from 'three';
import { cannonSurface } from './v7CannonSurface';
import { prepareV7Layers } from './v7SceneLayers';

/** Reconstruction des effets AMM_Shot01/02 de la V7 avec leurs textures natives.
 * Les salves et enveloppes restent une approximation visuelle : les courbes
 * ParticleAnimation du client ne sont pas encore décodées.
 */
export type CannonTextures = Partial<Record<'projectile' | 'muzzle' | 'impact' | 'shield' | 'flame' | 'electric' | 'spark', THREE.Texture>>;
export function createV7Effects(root: THREE.Object3D, textures: CannonTextures = {}) {
  const front = root.getObjectByName('AMM_7_0_FrontShips');
  const destroyed = root.getObjectByName('AMM_7_0_Ships_Destroyed');
  // Calage des deux plans sur les captures « ok » après recentrage des sommets.
  // Les locators sont natifs, mais leur projection client n'est pas disponible.
  const nearStones = root.getObjectByName('AMM_7_0_Stones_01');
  if (nearStones) nearStones.position.x += 6;
  const farStones = root.getObjectByName('AMM_7_0_Stones_02');
  if (farStones) { farStones.position.z -= 9; farStones.scale.multiplyScalar(.9); }
  const engines: { material: THREE.MeshBasicMaterial; opacity: number }[] = [];
  let glow: THREE.Texture | null = null;
  root.traverse(object => {
    const mesh = object as THREE.Mesh;
    if (!mesh.isMesh || Array.isArray(mesh.material)) return;
    // GLTFLoader place les extras d'une primitive sur BufferGeometry, pas Mesh.
    const element = String(mesh.geometry.userData.element ?? '');
    const material = mesh.material as THREE.MeshBasicMaterial;
    if (element.startsWith('Front_Myst')) material.opacity *= .35;
    if (element === 'Back_Myst') material.opacity *= .65;
    if (/^Back_Cloud_0[2-6]$/.test(element)) material.opacity *= .65;
    if (element.startsWith('GunRay')) mesh.visible = false;
    if (element.startsWith('Engine_')) {
      const material = mesh.material as THREE.MeshBasicMaterial;
      material.color.setRGB(2.4, 2.8, 3);
      engines.push({ material, opacity: material.opacity });
      if (element.startsWith('Engine_Glow')) glow = material.map;
    }
  });
  const layers = prepareV7Layers(root);
  const effects = new THREE.Group();
  effects.name = 'V7_cannon_effects';
  front?.add(effects);
  function sprite(color: number, kind: keyof CannonTextures) {
    const material = new THREE.SpriteMaterial({ map: textures[kind] ?? glow, color, blending: THREE.AdditiveBlending,
      transparent: true, depthTest: false, depthWrite: false, toneMapped: false });
    const object = new THREE.Sprite(material);
    object.renderOrder = 1000;
    effects.add(object);
    return object;
  }
  // Locators Slot_Special06/08/12/14, avec hauteur recalée sur les sabords visibles.
  const shots = [
    { start: [-32.90, -23.55, -6.5], end: [45, -30, -9], delay: 2.5, period: 9 },
    { start: [-36.89, -24.04, -12], end: [43, -30, -13], delay: 2.72, period: 9 },
    { start: [-34, -24, -15], end: [46, -30, -16], delay: 2.94, period: 9 },
    { start: [31.30, -25.59, -7], end: [-42, -24, -10], delay: 5.8, period: 12 },
    { start: [33.06, -25.87, -14.19], end: [-42, -24, -17], delay: 6.03, period: 12 },
    { start: [32, -26, -11], end: [-40, -24, -13], delay: 6.26, period: 12 },
  ].map(shot => ({ ...shot, from: new THREE.Vector3(...shot.start), to: new THREE.Vector3(...shot.end),
    direction: new THREE.Vector3(...shot.end).sub(new THREE.Vector3(...shot.start)).normalize(),
    projectile: sprite(0xffce76, 'projectile'), muzzle: sprite(0xffb95b, 'muzzle'),
    impact: sprite(0x85dbff, 'impact'), shield: sprite(0x8de5ff, 'shield'),
    trail: sprite(0xffb75d, 'projectile'),
    flash: sprite(0xc6adff, 'spark'),
    flashGlow: sprite(0xff8aff, 'projectile'),
    flame: cannonSurface(textures.flame, false), membrane: cannonSurface(textures.electric, true),
  }));
  for (const shot of shots) {
    shot.projectile.name = 'V7_cannon_projectile';
    shot.flash.name = 'V7_cannon_flash';
    effects.add(shot.flame, shot.membrane);
    shot.projectile.material.color.setRGB(4, 1.5, .4);
    shot.trail.material.color.setRGB(4, .7, .06);
  }
  function update(time: number, reduced = false) {
    layers.update(time, reduced);
    // La séquence de destruction appartient à l'introduction, pas à la boucle du menu.
    if (destroyed) destroyed.visible = !reduced && time < 27;
    for (const [index, engine] of engines.entries()) {
      engine.material.opacity = engine.opacity * (reduced ? 1 : .88 + .12 * Math.sin(time * 7 + index * .7));
    }
    for (const shot of shots) {
      const age = (time - shot.delay) % shot.period;
      // Aucun quad blanc, même avec un ancien export ou pendant le chargement.
      const ready = (object: THREE.Sprite) => !!object.material.map?.image;
      const active = !reduced && time >= shot.delay;
      shot.projectile.visible = active && ready(shot.projectile) && age < .85;
      shot.trail.visible = shot.projectile.visible && ready(shot.trail);
      shot.muzzle.visible = active && ready(shot.muzzle) && age < .18;
      shot.impact.visible = active && ready(shot.impact) && age >= .85 && age < 1.6;
      shot.shield.visible = active && ready(shot.shield) && age >= .85 && age < 1.6;
      shot.flash.visible = active && ready(shot.flash) && age >= .85 && age < 1.05;
      shot.flashGlow.visible = shot.flash.visible && ready(shot.flashGlow);
      shot.flame.visible = shot.projectile.visible && !!textures.flame?.image;
      shot.membrane.visible = active && !!textures.electric?.image && age >= .85 && age < 2.8;
      if (shot.projectile.visible) {
        shot.projectile.position.lerpVectors(shot.from, shot.to, age / .85);
        shot.projectile.scale.set(2.3, 1.8, 1);
        const direction = shot.direction;
        shot.trail.position.copy(shot.projectile.position).addScaledVector(direction, -2.2);
        shot.trail.scale.set(8, .65, 1);
        shot.trail.material.rotation = Math.atan2(direction.z, -direction.x);
        shot.trail.material.opacity = .8;
        shot.flame.position.copy(shot.projectile.position).addScaledVector(direction, -.7);
        shot.flame.scale.set(1.5, .7, 1);
        shot.flame.material.uniforms.time.value = time;
        shot.flame.material.uniforms.opacity.value = .9;
      }
      if (shot.muzzle.visible) {
        shot.muzzle.position.copy(shot.from);
        shot.muzzle.scale.setScalar(3);
        shot.muzzle.material.opacity = 1 - age / .18;
      }
      if (shot.impact.visible) {
        const phase = (age - .85) / .75;
        shot.impact.position.copy(shot.to);
        shot.impact.scale.set(3 + phase * 5, 7 + phase * 16, 1);
        shot.impact.material.opacity = (1 - phase) * .35;
        shot.impact.material.rotation = .18;
      }
      if (shot.shield.visible) {
        const phase = (age - .85) / .75;
        shot.shield.position.copy(shot.to);
        shot.shield.scale.set(4 + phase * 6, 10 + phase * 20, 1);
        shot.shield.material.rotation = .18;
        shot.shield.material.opacity = (1 - phase) * .8;
      }
      if (shot.flash.visible) {
        const phase = (age - .85) / .2;
        shot.flash.position.copy(shot.to);
        shot.flash.scale.set(7, 17, 1);
        shot.flash.material.color.setRGB(2.2, 1.7, 3);
        shot.flash.material.opacity = Math.pow(1 - phase, 2);
        shot.flashGlow.position.copy(shot.to);
        shot.flashGlow.scale.set(8, 18, 1);
        shot.flashGlow.material.color.setRGB(3.5, .65, 3.3);
        shot.flashGlow.material.opacity = Math.pow(1 - phase, 2);
      }
      if (shot.membrane.visible) {
        const regeneration = age >= 1.6;
        const phase = regeneration ? (age - 1.6) / 1.2 : (age - .85) / .75;
        shot.membrane.position.copy(shot.to);
        shot.membrane.scale.set(regeneration ? 4.2 - phase * 1.2 : 2.6 + phase,
          regeneration ? 10 - phase * 2 : 6 + phase * 3, 1);
        shot.membrane.rotation.z = -.16;
        shot.membrane.material.uniforms.time.value = time;
        shot.membrane.material.uniforms.regeneration.value = regeneration ? 1 : 0;
        shot.membrane.material.uniforms.phase.value = phase;
        shot.membrane.material.uniforms.opacity.value = regeneration
          ? Math.sin(Math.PI * phase) * 1.35 : (1 - phase) * .85;
      }
    }
  }
  return { update, dispose() {
    layers.dispose();
    for (const shot of shots) {
      for (const object of [shot.projectile, shot.muzzle, shot.impact, shot.shield, shot.trail, shot.flash, shot.flashGlow]) object.material.dispose();
      for (const object of [shot.flame, shot.membrane]) { object.material.dispose(); object.geometry.dispose(); }
    }
    effects.removeFromParent();
  } };
}
