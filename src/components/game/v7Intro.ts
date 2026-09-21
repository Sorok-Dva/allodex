import * as THREE from 'three';
import type { CannonTextures } from './menuSceneV7';
import { burningSurface } from './v7CannonSurface';
import { destructionPhase, INTRO_HITS } from './v7Timelines';

/** Reconstruction de l'introduction : une seule transformation pour chaque
 * coque et tous ses effets. Les durées sont un calage visuel, pas des pistes natives. */
export function createV7Intro(root: THREE.Object3D, textures: CannonTextures) {
  const parent = root.getObjectByName('AMM_7_0_Ships_Destroyed');
  const originals: THREE.Mesh[] = [];
  parent?.traverse(object => { if ((object as THREE.Mesh).isMesh) originals.push(object as THREE.Mesh); });
  const visibility = originals.map(mesh => mesh.visible);
  root.updateMatrixWorld(true);
  const ships = [1, 2, 3].map(id => {
    const group = new THREE.Group(); group.name = `V7_intro_ship_${id}`;
    const parts: { mesh: THREE.Mesh<THREE.BufferGeometry, THREE.MeshBasicMaterial>; opacity: number; fire: boolean }[] = [];
    const hullName = `SmalShip_destr_0${id}`;
    const hull = originals.find(mesh => mesh.geometry.userData.element === hullName);
    const center = new THREE.Vector3();
    if (hull) {
      const positions = hull.geometry.getAttribute('position');
      const indices = hull.geometry.index;
      const used = new Set(indices ? Array.from(indices.array) : Array.from({ length: positions.count }, (_, i) => i));
      for (const i of used) center.add(new THREE.Vector3().fromBufferAttribute(positions, i));
      center.divideScalar(used.size || 1);
    }
    for (const source of originals) {
      const element = String(source.geometry.userData.element ?? '');
      const engine = id === 2 ? /^Engine_.*03$/ : id === 3 ? /^Engine_.*04$/ : /$a/;
      if (!element.startsWith(hullName) && !engine.test(element)) continue;
      if (Array.isArray(source.material)) continue;
      const geometry = source.geometry.clone();
      geometry.deleteAttribute('skinIndex'); geometry.deleteAttribute('skinWeight');
      geometry.translate(-center.x, -center.y, -center.z);
      const material = (source.material as THREE.MeshBasicMaterial).clone();
      const mesh = new THREE.Mesh(geometry, material);
      // Tous les débris et FX restent derrière les coques permanentes (bande 200).
      mesh.renderOrder = element.startsWith('Engine_') ? 188 : 186;
      mesh.frustumCulled = false;
      group.add(mesh);
      parts.push({ mesh, opacity: material.opacity, fire: element.includes('_fire') });
    }
    group.position.copy(center); parent?.add(group);
    const fire = burningSurface(textures.flame); fire.renderOrder = 190;
    fire.material.blending = THREE.NormalBlending;
    fire.scale.set(4.5, 6, 1); fire.position.z = 1; group.add(fire);
    const smoke = new THREE.Sprite(new THREE.SpriteMaterial({ map: textures.smoke,
      color: 0x302b28, transparent: true, depthTest: false, depthWrite: false, toneMapped: false }));
    smoke.renderOrder = 189; group.add(smoke);
    const incoming = new THREE.Sprite(new THREE.SpriteMaterial({ map: textures.projectile,
      color: 0xffcd92, blending: THREE.AdditiveBlending, transparent: true, depthTest: false, depthWrite: false }));
    incoming.renderOrder = 191; parent?.add(incoming);
    incoming.scale.set(3, .65, 1);
    return { group, center, parts, fire, smoke, incoming, hit: INTRO_HITS[id], id };
  });
  originals.forEach(mesh => { mesh.visible = false; });
  return {
    update(time: number, reduced: boolean) {
      if (parent) parent.visible = !reduced && ships.some(ship => destructionPhase(time, ship.hit).visible);
      ships.forEach((ship, index) => {
        const phase = destructionPhase(time, ship.hit);
        ship.group.visible = !reduced && phase.visible;
        ship.group.userData.stage = !phase.visible ? 'gone' : phase.fall > 0 ? 'falling' : phase.burning ? 'burning' : 'intact';
        ship.group.position.copy(ship.center);
        ship.group.position.z -= (ship.id === 2 ? 17 : 24) * phase.fall * phase.fall;
        ship.group.position.x += (index === 1 ? -2 : 2) * phase.fall;
        ship.group.rotation.y = (index === 1 ? -.4 : .4) * phase.fall;
        for (const part of ship.parts) {
          // Noise11White était un masque de distorsion du client, pas une
          // flamme à afficher en négatif sur la coque.
          part.mesh.visible = !part.fire;
          part.mesh.material.transparent = true;
          part.mesh.material.opacity = part.opacity * phase.opacity;
        }
        ship.fire.visible = !reduced && phase.burning && !!textures.flame?.image;
        ship.fire.material.uniforms.time.value = time;
        ship.fire.material.uniforms.opacity.value = phase.opacity * (.85 + .1 * Math.sin(time * 13));
        ship.smoke.visible = !reduced && phase.burning && !!textures.smoke?.image;
        ship.smoke.position.z = 5 + Math.min(phase.age, 4) * 1.5;
        ship.smoke.scale.set(11, 18, 1);
        ship.smoke.material.opacity = phase.opacity * .85;
        ship.smoke.material.rotation = time * .12;
        ship.incoming.visible = !reduced && phase.incoming && !!textures.projectile?.image;
        const progress = (phase.age + .9) / .9;
        ship.incoming.position.copy(ship.center);
        ship.incoming.position.x += (index === 1 ? 35 : -35) * (1 - progress);
      });
    },
    dispose() {
      originals.forEach((mesh, index) => { mesh.visible = visibility[index]; });
      for (const ship of ships) {
        for (const { mesh } of ship.parts) { mesh.geometry.dispose(); mesh.material.dispose(); }
        ship.fire.geometry.dispose(); ship.fire.material.dispose();
        ship.smoke.material.dispose(); ship.incoming.material.dispose();
        ship.group.removeFromParent(); ship.incoming.removeFromParent();
      }
    },
  };
}
