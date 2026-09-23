import * as THREE from 'three';

/**
 * Collision de la caméra orbitale avec le décor, comme la caméra du jeu :
 *
 * - **sol** : la caméra reste au-dessus du terrain sous sa position (rayon vertical sur les
 *   maillages de sol), plus une marge ;
 * - **obstacles** : si un élément du décor (colline, rocher, tronc…) s'interpose entre la cible
 *   et la caméra, la caméra est rapprochée de la cible (rayon cible → caméra) au lieu de le
 *   traverser.
 *
 * La position voulue par `OrbitControls` n'est jamais modifiée (son rayon d'orbite et son zoom
 * restent ceux de l'utilisateur) : on calcule une correction, lissée dans le temps — rapide quand
 * il faut rentrer, lente quand l'obstacle disparaît — puis on la rend. Un plancher dur, sans
 * lissage, garantit qu'aucune image ne passe sous le sol.
 */
export type CameraColliderOptions = {
  /** Marge au-dessus du sol et devant un obstacle, en unités du jeu (m). */
  margin?: number;
  /** Plancher absolu au-dessus du sol, appliqué sans lissage. */
  hardMargin?: number;
  /** Raideur du lissage quand la correction grandit (1/s). */
  engage?: number;
  /** Raideur du lissage quand la correction diminue (1/s). */
  release?: number;
};

/** Marge au-dessus du terrain (m) : ≈ celle de la caméra du jeu, qui ne rase jamais le sol. */
export const CAMERA_GROUND_MARGIN = 0.4;
/** Plancher strict (m), garanti à chaque image quel que soit le lissage. */
export const CAMERA_HARD_MARGIN = 0.15;
const ENGAGE = 30;
const RELEASE = 5;
/** Hauteur d'où part le rayon vertical qui mesure le sol. */
const PROBE_HEIGHT = 1000;
/** En deçà (m), la correction est considérée comme stabilisée. */
const SETTLED = 1e-3;

export class CameraCollider {
  private ground: THREE.Object3D[] = [];
  private obstacles: THREE.Object3D[] = [];
  private readonly ray = new THREE.Raycaster();
  private readonly offset = new THREE.Vector3();
  private readonly tmp = new THREE.Vector3();
  private readonly dir = new THREE.Vector3();
  private readonly origin = new THREE.Vector3();
  private readonly opts: Required<CameraColliderOptions>;

  constructor(options: CameraColliderOptions = {}) {
    this.opts = {
      margin: options.margin ?? CAMERA_GROUND_MARGIN,
      hardMargin: options.hardMargin ?? CAMERA_HARD_MARGIN,
      engage: options.engage ?? ENGAGE,
      release: options.release ?? RELEASE,
    };
  }

  /** Maillages du terrain (rayon vertical) et du décor solide (rayon cible → caméra). */
  setColliders(ground: THREE.Object3D[], obstacles: THREE.Object3D[]): void {
    this.ground = ground;
    this.obstacles = obstacles;
    this.offset.set(0, 0, 0);
  }

  get active(): boolean {
    return this.ground.length > 0 || this.obstacles.length > 0;
  }

  /** Hauteur du terrain (repère monde, Z en haut) à la verticale de (x, y), `null` hors terrain. */
  groundHeight(x: number, y: number): number | null {
    if (!this.ground.length) return null;
    this.ray.set(this.tmp.set(x, y, PROBE_HEIGHT), this.dir.set(0, 0, -1));
    this.ray.far = PROBE_HEIGHT * 2;
    const hit = this.ray.intersectObjects(this.ground, true)[0];
    return hit ? hit.point.z : null;
  }

  /** Position sans lissage : rapprochée devant le premier obstacle, relevée au-dessus du sol. */
  constrain(target: THREE.Vector3, wanted: THREE.Vector3, out: THREE.Vector3): THREE.Vector3 {
    out.copy(wanted);
    const { margin } = this.opts;
    if (this.obstacles.length) {
      // Une cible posée au ras du sol (déplacement au clic droit) toucherait le terrain dès le
      // départ du rayon : on la relève au-dessus du sol pour ce test.
      const origin = this.origin.copy(target);
      const under = this.groundHeight(origin.x, origin.y);
      if (under !== null && origin.z < under + margin) origin.z = under + margin;
      this.dir.subVectors(wanted, origin);
      const distance = this.dir.length();
      if (distance > 1e-6) {
        this.dir.divideScalar(distance);
        this.ray.set(origin, this.dir);
        this.ray.far = distance;
        const hit = this.ray.intersectObjects(this.obstacles, true)[0];
        if (hit) out.copy(origin).addScaledVector(this.dir, Math.max(hit.distance - margin, 0));
      }
    }
    const floor = this.groundHeight(out.x, out.y);
    if (floor !== null && out.z < floor + margin) out.z = floor + margin;
    return out;
  }

  /**
   * Position à rendre pour la position voulue `wanted` (celle d'`OrbitControls`), lissée sur
   * `dt` secondes. Renvoie vrai tant que la correction n'est pas stabilisée (il faut redessiner).
   */
  resolve(target: THREE.Vector3, wanted: THREE.Vector3, dt: number, out: THREE.Vector3): boolean {
    if (!this.active) { out.copy(wanted); return false; }
    this.constrain(target, wanted, out);
    const goal = this.tmp.subVectors(out, wanted);
    const growing = goal.lengthSq() > this.offset.lengthSq();
    const k = 1 - Math.exp(-Math.max(dt, 0) * (growing ? this.opts.engage : this.opts.release));
    this.offset.lerp(goal, dt > 0 ? k : 1);
    const settling = this.offset.distanceTo(goal) > SETTLED;
    out.copy(wanted).add(this.offset);
    // Plancher strict : jamais sous le terrain, même pendant le lissage.
    const floor = this.groundHeight(out.x, out.y);
    if (floor !== null && out.z < floor + this.opts.hardMargin) out.z = floor + this.opts.hardMargin;
    return settling;
  }
}

/**
 * Colliders d'un décor exporté : les maillages de sol (`extras.ground`, ou nœuds `ground*`)
 * pour le rayon vertical ; pour les obstacles, le sol et tout le décor opaque hors ciel —
 * les feuillages découpés (`alphaTest`) et les calques translucides laissent passer la caméra,
 * comme les feuilles dans le jeu.
 */
export function decorColliders(decor: THREE.Object3D): { ground: THREE.Object3D[]; obstacles: THREE.Object3D[] } {
  const ground: THREE.Object3D[] = [];
  const obstacles: THREE.Object3D[] = [];
  let root: THREE.Object3D = decor;
  while (root.parent) root = root.parent;
  root.updateMatrixWorld(true);
  const flagged = (node: THREE.Object3D, key: 'ground' | 'sky') => {
    for (let n: THREE.Object3D | null = node; n; n = n.parent) {
      if ((n.userData as Record<string, unknown>)[key]) return true;
      if (key === 'ground' && /^ground/.test(n.name)) return true;
      if (n === decor) break;
    }
    return false;
  };
  decor.traverse(node => {
    const mesh = node as THREE.Mesh;
    if (!mesh.isMesh || flagged(mesh, 'sky')) return;
    if (flagged(mesh, 'ground')) { ground.push(mesh); obstacles.push(mesh); return; }
    const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    if (materials.every(m => !m.transparent && !(m.alphaTest > 0))) obstacles.push(mesh);
  });
  return { ground, obstacles };
}
