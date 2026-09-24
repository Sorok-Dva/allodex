import * as THREE from 'three';
import { clone as cloneSkinned } from 'three/examples/jsm/utils/SkeletonUtils.js';
import { applySoftGeometry, SoftMaskCache } from '@/components/scene/FatalityViewer/softGeometry';
import { ParticleSystemView, type ParticleAtlasMeta, type ParticleFile, type ParticleSystemMeta } from '@/components/scene/FatalityViewer/particles';
import { elementAlphaAt, objectClipTime, type FatalityObject } from '@/components/scene/FatalityViewer/timeline';

/**
 * Gabarits d'objets visuels du jeu (`VisObjectTemplate`) exportés par `tools/allods_fx.py`
 * (`FxBuild` : nœuds `vot:<nom>`, clips, composants retardés, particules) et leur lecture :
 * matériaux, clonage d'une instance, pose à un instant. Commun aux fatalités et aux cinématiques
 * moteur (extrait de `FatalityViewer` à la réunion des branches).
 */

/** Seuil de découpe des feuillages (textures opaques à trous). */
export const CUTOUT_ALPHA = 0.5;

/** Matériau d'une instance : opacité de base, mélange d'origine, facteur de son élément (`element`). */
export type Tinted = { material: THREE.Material & { opacity: number }; base: number; transparent: boolean; element?: number };
/**
 * Élément de géométrie à piste de transparence (`elementAlpha` du gabarit) : ses maillages,
 * leurs matériaux et ses clés, lues au temps du clip de son gabarit.
 */
export type ElementFade = { meshes: THREE.Object3D[]; records: Tinted[]; keys: number[]; offset: number; duration: number; loop: boolean };
export type Scrolling = { texture: THREE.Texture; speed: [number, number] };
export type Gate = [number, number | null];
/**
 * Un gabarit de l'instance (la racine ou un composant accroché) et sa vie propre, en temps de
 * l'instance : apparition à `start` (retard des `DelayComponent`), fin à `stop`
 * (`StopVisObjectComponents`) ou au bout de son clip s'il ne boucle pas (`end`), fondus du
 * gabarit (`fadeInMS`, `fadeOutMS`). Un composant entre avec son parent (fondus d'entrée
 * multipliés) et **meurt au plus tard avec lui, en suivant son propre `fadeOutMS`** : la fumée
 * `FatalityMage_Meteor` (3,5 s) survit au socle `FatalityMage` (0,8 s), l'ange du Prêtre (1,2 s)
 * s'efface avant `Fatality_Priest_Basis` (2 s) — vidéo de référence.
 */
export type VotPart = {
  node: THREE.Object3D;
  parent: VotPart | null;
  start: number;
  stop: number | null;
  end: number | null;
  fadeIn: number;
  fadeOut: number;
  tinted: Tinted[];
  opacity: number;
  /** Fondu d'entrée cumulé (le sien × celui de ses parents) et instant de sa mort, recalculés à chaque pose. */
  enter?: number;
  death?: number;
};
export type VotInstance = {
  root: THREE.Object3D;
  mixer: THREE.AnimationMixer;
  clips: { action: THREE.AnimationAction; duration: number; loop: boolean; offset: number }[];
  /** Composants retardés (`DelayComponent`) ou arrêtés : fenêtre d'apparition, temps de l'objet. */
  gated: { node: THREE.Object3D; start: number; stop: number | null }[];
  start: number;
  lifeTime: number;
  fadeIn: number;
  fadeOut: number;
  tinted: Tinted[];
  scrolling: Scrolling[];
  billboards: { node: THREE.Object3D; mode: string; base: THREE.Quaternion }[];
  particles: { view: ParticleSystemView; offset: number; part?: VotPart }[];
  /** Vies propres des gabarits (option `lifetimes` de la fabrique), racine en tête ; sinon vide. */
  parts: VotPart[];
  /** Éléments dont le clip anime la transparence. */
  elementFades: ElementFade[];
};

/**
 * Opacité propre d'un gabarit au temps `local` de l'instance : fondu d'entrée depuis son
 * apparition (sauf la racine, dont l'entrée est celle de l'action qui la pose), fondu de sortie
 * depuis sa fin — arrêt par `StopVisObjectComponents` ou fin de son clip qui ne boucle pas.
 */
export function partOpacity(part: Pick<VotPart, 'start' | 'stop' | 'end' | 'fadeIn' | 'fadeOut'>, local: number, root = false,
  parentDeath = Infinity): number {
  if (local < part.start) return 0;
  const enter = !root && part.fadeIn > 0 ? Math.min(1, (local - part.start) / part.fadeIn) : 1;
  const death = partDeath(part, parentDeath);
  if (local <= death) return enter;
  const leave = part.fadeOut > 0 ? 1 - (local - death) / part.fadeOut : 0;
  return Math.max(0, Math.min(enter, leave));
}

/** Mort d'un gabarit : son arrêt, la fin de son clip, ou celle de son parent (la première venue). */
export function partDeath(part: Pick<VotPart, 'stop' | 'end'>, parentDeath = Infinity): number {
  return Math.min(part.stop ?? Infinity, part.end ?? Infinity, parentDeath);
}

/** Début cumulé d'un nœud de gabarit : somme des retards de ses ancêtres (lui compris). */
export function windowOffset(node: THREE.Object3D, root: THREE.Object3D): number {
  let offset = 0;
  for (let n: THREE.Object3D | null = node; n && n !== root.parent; n = n.parent) {
    const w = (n.userData as { window?: Gate }).window;
    if (w) offset += w[0];
  }
  return offset;
}

/**
 * Matériau d'affichage d'une primitive exportée par les outils 3D du site.
 *
 * Les personnages sont éclairés (Lambert, normales exportées) ; les effets sont sans éclairage
 * comme dans le jeu : additifs ou en mélange alpha sans écriture de profondeur, opaques sinon.
 */
export function toViewerMaterial(source: THREE.Material, lit = true): THREE.Material {
  const src = source as THREE.MeshBasicMaterial;
  const additive = (source.userData as { blend?: string } | undefined)?.blend === 'add';
  const translucent = source.transparent || additive;
  const common = {
    name: source.name,
    map: src.map ?? null,
    // Teinte d'un géoset (couleur des cheveux, d'armure) portée par `baseColorFactor`.
    color: (source.userData as { tint?: boolean } | undefined)?.tint && src.color ? src.color.clone() : new THREE.Color(0xffffff),
    opacity: source.opacity,
    alphaTest: translucent ? 0 : source.alphaTest,
    transparent: translucent,
    side: THREE.DoubleSide,
    vertexColors: true,
    toneMapped: false,
    fog: !translucent,
  };
  // Feuillages du décor : opaques mais découpés par l'alpha de leur texture (`cutout`).
  if (!translucent && (source.userData as { cutout?: boolean } | undefined)?.cutout) common.alphaTest = CUTOUT_ALPHA;
  const material = translucent || !lit ? new THREE.MeshBasicMaterial(common) : new THREE.MeshLambertMaterial(common);
  if (translucent) material.depthWrite = false;
  if (additive) material.blending = THREE.AdditiveBlending;
  if (material.map) material.map.colorSpace = THREE.NoColorSpace;
  return material;
}

/**
 * Oriente un nœud d'effet vers la caméra selon le mode du jeu : `Z_AXIS` tourne autour de l'axe Z
 * local pour présenter sa face −Y (normale des quads de ces géométries), `BILLBOARD` fait face
 * entièrement. Le calcul se fait dans le repère du parent (miroir compris).
 */
export function faceCamera(node: THREE.Object3D, mode: string, base: THREE.Quaternion, camera: THREE.Camera): void {
  const parent = node.parent;
  if (!parent) return;
  const eye = parent.worldToLocal(camera.getWorldPosition(new THREE.Vector3()));
  const dir = eye.sub(node.position);
  if (mode === 'Z_AXIS' || mode === 'WORLD_Z') {
    const angle = Math.atan2(dir.x, -dir.y);
    node.quaternion.copy(base).premultiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), angle));
  } else if (mode === 'BILLBOARD') {
    const m = new THREE.Matrix4().lookAt(dir.normalize(), new THREE.Vector3(), new THREE.Vector3(0, 0, 1));
    // lookAt aligne +Z sur la direction ; le quad regarde −Y : on tourne de −90° autour de X.
    const q = new THREE.Quaternion().setFromRotationMatrix(m).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), -Math.PI / 2));
    node.quaternion.copy(q);
  }
}

export type VotFactoryOptions = {
  objects: Record<string, FatalityObject>;
  /** URL du `.glb` des gabarits : les textures de géométrie douce y sont relatives. */
  baseUrl: string | null;
  disposables: { dispose(): void }[];
  anisotropy?: () => number;
  /**
   * Vie propre de chaque gabarit (`VotPart`) : un gabarit dont le clip ne boucle pas s'éteint au
   * bout de son clip, avec son `fadeOutMS` ; les composants retardés ou arrêtés entrent et sortent
   * avec leurs fondus. Règle des effets du client (fatalités) ; les cinématiques gardent l'ancien
   * comportement (dernière pose tenue) tant qu'elle n'y est pas vérifiée.
   */
  lifetimes?: boolean;
};

/** Prépare les matériaux des `.glb` et clone les instances de gabarits (particules comprises). */
export class VotFactory {
  readonly softMasks = new SoftMaskCache();
  particleFiles = new Map<string, ParticleFile | null>();
  atlasTexture: THREE.Texture | null = null;
  particleAtlas: ParticleAtlasMeta | null = null;
  private readonly opts: VotFactoryOptions;

  constructor(opts: VotFactoryOptions) {
    this.opts = opts;
    opts.disposables.push(this.softMasks);
  }

  set objects(objects: Record<string, FatalityObject>) { this.opts.objects = objects; }

  private resolve(base: string | null, uri: string): string {
    try { return new URL(uri, new URL(base ?? '', window.location.href)).href; } catch { return uri; }
  }

  /** Remplace les matériaux glTF par ceux du lecteur ; `scrolling` reçoit les textures qui défilent. */
  prepare(root: THREE.Object3D, lit: boolean, tinted: Tinted[], scrolling: Scrolling[] | null, baseUrl: string | null = null,
    convert: (m: THREE.Material, lit: boolean) => THREE.Material = toViewerMaterial): void {
    const { disposables } = this.opts;
    root.traverse(object => {
      const mesh = object as THREE.Mesh;
      if (!mesh.isMesh) return;
      mesh.frustumCulled = false;
      const source = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      const converted = source.map(m => {
        const material = convert(m, lit);
        const soft = (m.userData as { soft?: string } | undefined)?.soft;
        if (soft && material.transparent && typeof document !== 'undefined') applySoftGeometry(material, this.softMasks.get(this.resolve(baseUrl, soft)));
        return material;
      });
      const speedPair = (mesh.geometry.userData as { uvScroll?: [number, number] }).uvScroll;
      for (const material of converted) {
        const basic = material as THREE.MeshBasicMaterial;
        if (basic.map) {
          basic.map.anisotropy = this.opts.anisotropy?.() ?? 1;
          if (scrolling && speedPair) {
            const texture = basic.map.clone();
            texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
            texture.needsUpdate = true;
            basic.map = texture;
            scrolling.push({ texture, speed: speedPair });
            disposables.push(texture);
          }
        }
        tinted.push({ material: material as Tinted['material'], base: material.opacity, transparent: material.transparent });
        disposables.push(material);
      }
      mesh.material = Array.isArray(mesh.material) ? converted : converted[0];
    });
  }

  /** Clone d'un gabarit : clips en pause (le temps est posé à la main), composants retardés, particules. */
  instantiate(proto: THREE.Object3D, clips: THREE.AnimationClip[], start: number, lifeTime: number, fadeIn: number, fadeOut: number): VotInstance {
    const root = cloneSkinned(proto);
    const mixer = new THREE.AnimationMixer(root);
    const inst: VotInstance = { root, mixer, clips: [], start, lifeTime, fadeIn, fadeOut, tinted: [], scrolling: [], billboards: [], particles: [], gated: [], parts: [], elementFades: [] };
    const withParticles: [THREE.Object3D, ParticleSystemMeta][] = [];
    const { objects } = this.opts;
    root.traverse(node => {
      const { vot, window } = node.userData as { vot?: string; window?: Gate };
      if (window) {
        const parentOffset = node.parent ? windowOffset(node.parent, root) : 0;
        inst.gated.push({ node, start: parentOffset + window[0], stop: window[1] === null ? null : parentOffset + window[1] });
      }
      if (!vot) return;
      const info = objects[vot];
      const clip = clips.find(c => c.name === vot);
      if (clip) {
        const action = mixer.clipAction(clip, root);
        action.play();
        action.paused = true;
        inst.clips.push({ action, duration: info?.duration || clip.duration, loop: !!info?.loop, offset: windowOffset(node, root) });
      }
      if (info?.orientation && info.orientation !== 'COMMON') inst.billboards.push({ node, mode: info.orientation, base: node.quaternion.clone() });
      const system = info?.particles as ParticleSystemMeta | undefined;
      if (system && typeof system === 'object') withParticles.push([node, system]);
    });
    this.prepare(root, false, inst.tinted, inst.scrolling, this.opts.baseUrl);
    buildElementFades(inst, objects);
    const partOf = this.opts.lifetimes ? buildParts(inst, objects) : null;
    if (this.atlasTexture && this.particleAtlas) {
      for (const [node, system] of withParticles) {
        const file = this.particleFiles.get(system.file);
        if (!file) continue;
        const view = new ParticleSystemView(file, system, this.atlasTexture, this.particleAtlas);
        node.add(view.group);
        inst.particles.push({ view, offset: windowOffset(node, root), part: partOf?.(node) ?? undefined });
        this.opts.disposables.push(view);
      }
    }
    return inst;
  }
}

/**
 * Vies propres des gabarits d'une instance (`VotPart`, parents avant enfants) ; chaque matériau
 * revient au gabarit le plus proche qui le porte. Renvoie la recherche du gabarit d'un nœud.
 */
function buildParts(inst: VotInstance, objects: Record<string, FatalityObject>): (node: THREE.Object3D) => VotPart | null {
  const { root } = inst;
  const byNode = new Map<THREE.Object3D, VotPart>();
  const nearest = (node: THREE.Object3D | null): VotPart | null => {
    for (let n = node; n && n !== root.parent; n = n.parent) {
      const part = byNode.get(n);
      if (part) return part;
    }
    return null;
  };
  root.traverse(node => {
    const { vot, window } = node.userData as { vot?: string; window?: Gate };
    if (!vot) return;
    const info = objects[vot];
    const start = windowOffset(node, root);
    const parentOffset = node !== root && node.parent ? windowOffset(node.parent, root) : 0;
    const duration = info?.duration ?? 0;
    const part: VotPart = {
      node,
      parent: node === root ? null : nearest(node.parent),
      start,
      stop: window && window[1] !== null ? parentOffset + window[1] : null,
      end: duration > 0 && !info?.loop ? start + duration : null,
      fadeIn: info?.fadeIn ?? 0,
      fadeOut: info?.fadeOut ?? 0,
      tinted: [],
      opacity: 1,
    };
    byNode.set(node, part);
    inst.parts.push(part);
  });
  const records = new Map(inst.tinted.map(t => [t.material as THREE.Material, t]));
  root.traverse(node => {
    const mesh = node as THREE.Mesh;
    if (!mesh.isMesh) return;
    const part = nearest(mesh);
    if (!part) return;
    for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
      const record = records.get(material);
      if (record) part.tinted.push(record);
    }
  });
  // Les fenêtres des gabarits passent par leurs vies propres (fondus compris).
  inst.gated = inst.gated.filter(gate => !byNode.has(gate.node));
  return nearest;
}

/**
 * Pistes de transparence des éléments : chaque maillage revient au gabarit le plus proche qui le
 * porte (`userData.vot`) ; son élément (`geometry.userData.element`) y cherche ses clés.
 */
function buildElementFades(inst: VotInstance, objects: Record<string, FatalityObject>): void {
  const { root } = inst;
  const records = new Map(inst.tinted.map(t => [t.material as THREE.Material, t]));
  const byKey = new Map<string, ElementFade>();
  root.traverse(node => {
    const mesh = node as THREE.Mesh;
    if (!mesh.isMesh) return;
    const element = String((mesh.geometry.userData as { element?: string }).element ?? '');
    if (!element) return;
    let owner: THREE.Object3D | null = mesh;
    while (owner && owner !== root.parent && !(owner.userData as { vot?: string }).vot) owner = owner.parent;
    const vot = owner ? (owner.userData as { vot?: string }).vot : undefined;
    const info = vot ? objects[vot] : undefined;
    const keys = info?.elementAlpha?.[element];
    if (!owner || !info || !keys) return;
    const key = `${owner.uuid}/${element}`;
    let fade = byKey.get(key);
    if (!fade) {
      fade = { meshes: [], records: [], keys, offset: windowOffset(owner, root), duration: info.duration, loop: !!info.loop };
      byKey.set(key, fade);
      inst.elementFades.push(fade);
    }
    fade.meshes.push(mesh);
    for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
      const record = records.get(material);
      if (record) fade.records.push(record);
    }
  });
}

/** Opacité d'un matériau (facteur `k` de son opacité de base), mélange le temps d'un fondu. */
function setOpacity(record: Tinted, k: number): void {
  record.material.opacity = record.base * k;
  blendWhileFading(record, k);
}

/** Un matériau opaque passe en mélange tant que son facteur d'opacité `k` est sous 1. */
function blendWhileFading(record: Tinted, k: number): void {
  const want = record.transparent || k < 0.999;
  if (record.material.transparent !== want) { record.material.transparent = want; record.material.needsUpdate = true; }
}

/** Pose une instance au temps `local` de sa vie, avec son opacité `fade` (0 = masquée). */
export function updateInstance(inst: VotInstance, local: number, fade: number, camera: THREE.Camera, shown = true): void {
  if (inst.parts.length) {
    // Racine : fondus de l'action qui la pose (`fade`), fin de son propre clip ; elle meurt au
    // bout de la vie de l'action. Composants : entrée avec leur parent, mort au plus tard avec
    // lui, chacun avec son fondu de sortie.
    const entry = local < 0 ? 0 : inst.fadeIn > 0 ? Math.min(1, local / inst.fadeIn) : 1;
    let any = false;
    for (const part of inst.parts) {
      const { parent } = part;
      if (!parent) {
        part.enter = entry;
        part.death = partDeath(part, inst.lifeTime);
        part.opacity = shown ? fade * partOpacity(part, local, true) : 0;
      } else {
        const own = part.fadeIn > 0 ? Math.max(0, Math.min(1, (local - part.start) / part.fadeIn)) : 1;
        part.enter = own * (parent.enter ?? 1);
        part.death = partDeath(part, parent.death ?? Infinity);
        part.opacity = shown && local >= part.start ? (parent.enter ?? 1) * partOpacity(part, local, false, parent.death ?? Infinity) : 0;
        part.node.visible = part.opacity > 0.001;
      }
      if (part.opacity > 0.001) any = true;
    }
    inst.root.visible = any;
  } else {
    inst.root.visible = shown && fade > 0.001;
  }
  if (!inst.root.visible) return;
  for (const gate of inst.gated) gate.node.visible = local >= gate.start && (gate.stop === null || local < gate.stop);
  for (const clip of inst.clips) clip.action.time = objectClipTime(Math.max(0, local - clip.offset), clip.duration, clip.loop);
  inst.mixer.update(0);
  for (const element of inst.elementFades) {
    const a = elementAlphaAt(element.keys, objectClipTime(Math.max(0, local - element.offset), element.duration, element.loop));
    for (const mesh of element.meshes) mesh.visible = a > 0.001;
    for (const record of element.records) record.element = a;
  }
  if (inst.parts.length) {
    // Vies propres (fatalités) : un matériau opaque passe en mélange le temps d'un fondu — du
    // gabarit, de l'action qui le pose ou de son élément — sinon il apparaîtrait et
    // disparaîtrait d'un coup (ange du Prêtre, fondu de sortie de 2 s de son socle).
    for (const part of inst.parts) for (const record of part.tinted) setOpacity(record, part.opacity * (record.element ?? 1));
  } else {
    for (const record of inst.tinted) {
      record.material.opacity = record.base * fade * (record.element ?? 1);
      if (record.element !== undefined) blendWhileFading(record, record.element);
    }
  }
  for (const { texture, speed: [su, sv] } of inst.scrolling) texture.offset.set((local * su) % 1, -((local * sv) % 1));
  for (const { node, mode, base } of inst.billboards) faceCamera(node, mode, base, camera);
  for (const { view, offset, part } of inst.particles) view.update(Math.max(0, local - offset), part ? part.opacity : fade);
}

/** Systèmes de particules utilisés par des gabarits (fichiers à charger). */
export function particleSystems(objects: Record<string, FatalityObject>): Set<string> {
  const systems = new Set<string>();
  for (const info of Object.values(objects)) {
    const system = info.particles as ParticleSystemMeta | undefined;
    if (system && typeof system === 'object') systems.add(system.file);
  }
  return systems;
}
