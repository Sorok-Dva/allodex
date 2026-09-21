import * as THREE from 'three';
import { cannonPhase, impactEnvelope, IMPACT_RING_START } from './v7Timelines';

/** Aucun dessin de FX : les géométries, UV et couleurs viennent d'AMM_Shot01.
 * Seuls placement, taille, opacité et défilement UV sont animés ici. */
export function createNativeShots(root: THREE.Object3D, smokeTexture?: THREE.Texture) {
  const front = root.getObjectByName('AMM_7_0_FrontShips');
  const source = root.getObjectByName('AMM_Shot01');
  const originalVisible = source?.visible;
  if (source) source.visible = false;
  const templates: THREE.Mesh<THREE.BufferGeometry, THREE.MeshBasicMaterial>[] = [];
  source?.traverse(object => {
    const mesh = object as THREE.Mesh<THREE.BufferGeometry, THREE.MeshBasicMaterial>;
    if (mesh.isMesh && !Array.isArray(mesh.material)) templates.push(mesh);
  });
  const effects = new THREE.Group(); effects.name = 'V7_cannon_effects'; front?.add(effects);
  const shots = [
    { start: [-32.90, -23.55, 2.60], end: [45, -30, -4], delay: 2.5, period: 14 },
    { start: [-36.89, -24.04, -1.55], end: [43, -30, -10], delay: 4, period: 14 },
    { start: [31.30, -25.59, -6.54], end: [-38, -24, -12], delay: 5.8, period: 16 },
    { start: [33.06, -25.87, -14.19], end: [-38, -24, -17], delay: 7.3, period: 16 },
  ].map(spec => {
    const projectile = new THREE.Group(); projectile.name = 'V7_cannon_projectile';
    const muzzle = new THREE.Group(); muzzle.name = 'V7_cannon_muzzle';
    const impact = new THREE.Group(); impact.name = 'V7_cannon_impact';
    const smoke = new THREE.Sprite(new THREE.SpriteMaterial({ map: smokeTexture, color: 0xada9af,
      transparent: true, depthTest: false, depthWrite: false, toneMapped: false }));
    smoke.name = 'V7_cannon_smoke'; smoke.renderOrder = 1001;
    effects.add(projectile, muzzle, impact, smoke);
    const parts = templates.flatMap(template => {
      const name = String(template.geometry.userData.element ?? '');
      const flying = /^(Proj_|Tail_)/.test(name);
      const firing = name === 'FireMuzzle';
      const hitting = /^(ShockWave|Shield|Flash)/.test(name);
      if (!flying && !firing && !hitting) return [];
      const geometry = template.geometry.clone();
      geometry.deleteAttribute('skinIndex'); geometry.deleteAttribute('skinWeight');
      if (flying) geometry.translate(-1.65, 0, 0);
      if (name === 'Shield01' || name === 'ShieldRays01') geometry.translate(-68.5, 7, -.27);
      const material = template.material.clone();
      const originalMap = material.map;
      if (originalMap) {
        material.map = originalMap.clone();
        material.map.wrapS = material.map.wrapT = THREE.RepeatWrapping;
        material.map.needsUpdate = true;
      }
      // Ne pas teinter les textures : conserver les couleurs natives exportées.
      material.color.setRGB(1, 1, 1);
      material.transparent = true; material.depthTest = false; material.depthWrite = false;
      const mesh = new THREE.Mesh(geometry, material);
      mesh.name = `V7_native_${name}`; mesh.renderOrder = 1000 + (hitting ? 10 : 0);
      mesh.frustumCulled = false;
      (flying ? projectile : firing ? muzzle : impact).add(mesh);
      const scroll = geometry.userData.uvScroll as number[] | undefined;
      const part = { mesh, name, opacity: material.opacity, offset: material.map?.offset.clone(), scroll, delay: 0 };
      if (name !== 'Shield01') return [part];
      // Deux couches du même asset natif, la seconde démarre après la première.
      const innerMaterial = material.clone();
      innerMaterial.map = material.map?.clone() ?? null;
      const inner = new THREE.Mesh(geometry.clone(), innerMaterial);
      inner.name = 'V7_native_Shield01_inner'; inner.renderOrder = mesh.renderOrder + 1;
      inner.frustumCulled = false; impact.add(inner);
      return [part, { ...part, mesh: inner, delay: .12, opacity: material.opacity * .65 }];
    });
    const from = new THREE.Vector3(...spec.start), to = new THREE.Vector3(...spec.end);
    let bone: THREE.Object3D | undefined;
    front?.traverse(object => {
      if ((object as THREE.Bone).isBone && object.name.endsWith(spec.start[0] < 0 ? 'Ship_l' : 'Ship_r')) bone = object;
    });
    root.updateMatrixWorld(true);
    const anchor = bone && front ? bone.worldToLocal(front.localToWorld(from.clone())) : null;
    return { ...spec, from, to, bone, anchor, projectile, muzzle, impact, smoke, parts };
  });
  return {
    update(time: number, reduced: boolean) {
      root.updateMatrixWorld(true);
      for (const shot of shots) {
        if (shot.bone && shot.anchor && front) shot.from.copy(front.worldToLocal(shot.bone.localToWorld(shot.anchor.clone())));
        const phase = cannonPhase(time, shot.delay, shot.period);
        const envelope = impactEnvelope(phase.impact);
        const ready = shot.parts.length > 0 && shot.parts.every(part => !!part.mesh.material.map?.image);
        shot.projectile.visible = !reduced && ready && phase.flight >= 0;
        shot.muzzle.visible = !reduced && ready && phase.age >= 0 && phase.age < .25;
        shot.impact.visible = !reduced && ready && phase.impact >= 0;
        shot.smoke.visible = !reduced && !!smokeTexture?.image && phase.age >= 0 && phase.age < 2;
        const smokePhase = Math.max(0, Math.min(1, phase.age / 2));
        shot.smoke.position.copy(shot.from); shot.smoke.position.z += smokePhase * 3;
        shot.smoke.scale.setScalar(4 + smokePhase * 7);
        shot.smoke.material.opacity = .8 * Math.min(1, phase.age / .12) * (1 - smokePhase);
        shot.projectile.position.lerpVectors(shot.from, shot.to, Math.max(0, phase.flight));
        const direction = shot.to.clone().sub(shot.from);
        shot.projectile.rotation.y = -Math.atan2(direction.z, direction.x);
        shot.projectile.scale.setScalar(2.2);
        shot.muzzle.position.copy(shot.from); shot.muzzle.rotation.copy(shot.projectile.rotation);
        shot.muzzle.scale.setScalar(2);
        shot.impact.position.copy(shot.to);
        shot.impact.userData.shape = envelope.shape;
        shot.impact.userData.returning = envelope.returning;
        for (const part of shot.parts) {
          const { mesh, name } = part;
          mesh.visible = true;
          mesh.material.opacity = part.opacity;
          const layerEnvelope = impactEnvelope(phase.impact - part.delay);
          if (name === 'Shield01') {
            mesh.visible = phase.impact >= IMPACT_RING_START + part.delay;
            const growth = (.2 + layerEnvelope.shape * .8) * (part.delay ? .86 : 1);
            mesh.scale.set(2 * growth, 1.5 * growth, 1.5 * growth);
            mesh.material.opacity *= layerEnvelope.opacity;
            if (part.delay) mesh.material.opacity *= Math.max(0, Math.min(1, (1.4 - phase.impact) / .15));
          } else if (name === 'ShieldRays01') {
            mesh.visible = phase.impact >= 0 && phase.impact < IMPACT_RING_START;
            // Cet asset est dans le plan YZ natif : le remettre face à la
            // caméra, indépendamment du bouclier bombé qui suit.
            mesh.rotation.z = Math.PI / 2;
            mesh.scale.set(.65, .65, 1.1);
            mesh.material.opacity *= Math.max(0, 1 - phase.impact / IMPACT_RING_START);
          } else if (/^(Flash|ShieldFlash)/.test(name)) {
            mesh.visible = phase.impact >= 0 && phase.impact < .22;
            mesh.scale.set(7, 1, 15);
            mesh.material.opacity *= Math.max(0, 1 - phase.impact / .22);
          } else if (name.startsWith('ShockWave')) {
            // Rays23 est le rayonnement du choc initial, pas l'anneau bleu.
            // Le laisser pendant l'expansion superposait encore les deux FX.
            mesh.visible = phase.impact >= 0 && phase.impact < IMPACT_RING_START;
            const burst = Math.max(0, Math.min(1, phase.impact / IMPACT_RING_START));
            mesh.scale.set(3 + burst * 2, 1, 7 + burst * 4);
            mesh.material.opacity *= (1 - burst) * .6;
          } else if (name === 'FireMuzzle') mesh.material.opacity *= Math.max(0, 1 - phase.age / .25);
          if (mesh.material.map && part.offset && part.scroll) {
            const t = mesh.parent === shot.impact ? layerEnvelope.shape : time;
            mesh.material.map.offset.set(part.offset.x + t * part.scroll[0], part.offset.y - t * part.scroll[1]);
          }
        }
      }
    },
    dispose() {
      for (const shot of shots) {
        shot.smoke.material.dispose();
        for (const { mesh } of shot.parts) {
          mesh.material.map?.dispose(); mesh.material.dispose(); mesh.geometry.dispose();
        }
      }
      effects.removeFromParent();
      if (source) source.visible = originalVisible ?? true;
    },
  };
}
