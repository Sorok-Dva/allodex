import * as THREE from 'three';
import type { GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { clone as cloneSkinned } from 'three/examples/jsm/utils/SkeletonUtils.js';
import { composeBaked } from './bake';
import type { Look } from '@/data/character/look';

/** Chargements partagés entre les personnages (glTF, images) : chaque fichier une seule fois. */
export type AssetCache = {
  gltf(url: string): Promise<GLTF>;
  image(url: string): Promise<HTMLImageElement | ImageBitmap>;
  texture(url: string): Promise<THREE.Texture>;
};

/** Élément (géoset) d'un primitif, lu dans les `extras` du glTF (que `GLTFLoader` ne copie pas). */
export function elementOf(gltf: GLTF, mesh: THREE.Object3D): string {
  const assoc = gltf.parser.associations.get(mesh) as { meshes?: number; primitives?: number } | undefined;
  if (!assoc || assoc.meshes === undefined || assoc.primitives === undefined) return '';
  const json = gltf.parser.json as { meshes: { primitives: { extras?: { element?: string } }[] }[] };
  return json.meshes[assoc.meshes]?.primitives[assoc.primitives]?.extras?.element ?? '';
}

export function uvScrollOf(gltf: GLTF, mesh: THREE.Object3D): [number, number] | null {
  const assoc = gltf.parser.associations.get(mesh) as { meshes?: number; primitives?: number } | undefined;
  if (!assoc || assoc.meshes === undefined || assoc.primitives === undefined) return null;
  const json = gltf.parser.json as { meshes: { primitives: { extras?: { uvScroll?: [number, number] } }[] }[] };
  return json.meshes[assoc.meshes]?.primitives[assoc.primitives]?.extras?.uvScroll ?? null;
}

/**
 * Matériau éclairé d'un primitif de personnage. Les textures du jeu sont des octets (pas de
 * conversion sRGB, comme les scènes de menu) ; les matériaux transparents du jeu (ailes des
 * elfes, lueurs) restent sans écriture de profondeur, les additifs en mélange additif.
 */
export function characterMaterial(source: THREE.Material): THREE.MeshLambertMaterial {
  const src = source as THREE.MeshBasicMaterial;
  const additive = (source.userData as { blend?: string }).blend === 'add';
  const translucent = source.transparent || additive;
  const material = new THREE.MeshLambertMaterial({
    name: source.name, map: src.map ?? null, color: 0xffffff, transparent: translucent,
    alphaTest: translucent ? 0 : 0.5, side: THREE.DoubleSide, vertexColors: false, fog: false,
  });
  if (translucent) material.depthWrite = false;
  if (additive) material.blending = THREE.AdditiveBlending;
  if (material.map) material.map.colorSpace = THREE.NoColorSpace;
  material.userData = { ...source.userData };
  return material;
}

type Part = { mesh: THREE.Mesh; element: string; base: THREE.Texture | null; baked: boolean };

/**
 * Un personnage (ou un familier) chargé depuis `models/<Gabarit>.glb` : un primitif par
 * géoset, dont on règle la visibilité, la texture et la teinte selon l'apparence ; la texture
 * cuite est recomposée à chaque changement ; les modèles accrochés suivent les articulations.
 */
export class CharacterRig {
  readonly root = new THREE.Group();
  readonly model: THREE.Object3D;
  readonly parts: Part[] = [];
  readonly clips: THREE.AnimationClip[];
  readonly mixer: THREE.AnimationMixer;
  readonly textured = new Set<string>();
  private attachments: THREE.Object3D[] = [];
  private bakedTexture: THREE.CanvasTexture | null = null;
  private current: THREE.AnimationAction | null = null;
  private token = 0;

  private cache: AssetCache;
  readonly template: string;

  constructor(gltf: GLTF, cache: AssetCache, template: string) {
    this.cache = cache;
    this.template = template;
    // Clone profond (squelette compris) : un même gabarit sert au trio gibberling et aux familiers.
    this.model = cloneSkinned(gltf.scene);
    this.clips = gltf.animations;
    this.root.add(this.model);
    this.mixer = new THREE.AnimationMixer(this.model);
    this.model.traverse(object => {
      const mesh = object as THREE.Mesh;
      if (!mesh.isMesh || Array.isArray(mesh.material)) return;
      const element = String(mesh.userData.element ?? '');
      const baked = !!(mesh.material.userData as { baked?: boolean }).baked;
      mesh.material = characterMaterial(mesh.material);
      const map = (mesh.material as THREE.MeshLambertMaterial).map;
      if (map) this.textured.add(element);
      mesh.frustumCulled = false;
      this.parts.push({ mesh, element, base: map, baked });
    });
  }

  joint(name: string): THREE.Object3D | null {
    let found: THREE.Object3D | null = null;
    this.model.traverse(o => { if (!found && (o.name === name || o.name.endsWith(`/${name}`))) found = o; });
    return found;
  }

  /** Applique une apparence résolue (`resolveLook`). Les chargements asynchrones périmés sont ignorés. */
  async apply(look: Look, bakeSize = 512): Promise<void> {
    const token = ++this.token;
    const textures = await Promise.all(Object.entries(look.textures).map(async ([el, url]) => [el, await this.cache.texture(url)] as const));
    const images = await Promise.all(look.bake.map(b => this.cache.image(b.texture).catch(() => null)));
    const models = await Promise.all(look.attachments.map(a => this.cache.gltf(a.model).then(g => ({ a, g })).catch(() => null)));
    if (token !== this.token) return;
    const texOf = new Map(textures);
    // Texture cuite.
    const layers = look.bake.map((b, i) => ({ image: images[i], rect: b.rect, tint: b.tint, tintThroughAlpha: b.throughAlpha }))
      .filter((l): l is typeof l & { image: NonNullable<typeof l.image> } => !!l.image);
    const canvas = composeBaked(bakeSize, layers as never);
    this.bakedTexture?.dispose();
    this.bakedTexture = new THREE.CanvasTexture(canvas as HTMLCanvasElement);
    this.bakedTexture.flipY = false;
    this.bakedTexture.colorSpace = THREE.NoColorSpace;
    this.bakedTexture.wrapS = this.bakedTexture.wrapT = THREE.RepeatWrapping;
    for (const part of this.parts) {
      const material = part.mesh.material as THREE.MeshLambertMaterial;
      part.mesh.visible = look.visible.has(part.element);
      const tex = texOf.get(part.element);
      material.map = part.baked && !tex ? this.bakedTexture : tex ?? part.base;
      material.color.set(look.colors[part.element] ?? '#ffffff');
      material.needsUpdate = true;
    }
    // Modèles accrochés.
    for (const a of this.attachments) a.removeFromParent();
    this.attachments = [];
    for (const entry of models) {
      if (!entry) continue;
      const joint = this.joint(entry.a.locator) ?? this.model;
      const clone = entry.g.scene.clone(true);
      const names: string[] = [];
      clone.traverse(o => { if ((o as THREE.Mesh).isMesh) names.push(elementOf(entry.g, o) || this.sourceElement(entry.g, o)); });
      const perTemplate = names.includes(this.template);
      clone.traverse(o => {
        const mesh = o as THREE.Mesh;
        if (!mesh.isMesh || Array.isArray(mesh.material)) return;
        const element = this.sourceElement(entry.g, mesh);
        mesh.material = characterMaterial(mesh.material);
        mesh.frustumCulled = false;
        if (perTemplate) mesh.visible = element === this.template;
      });
      joint.add(clone);
      this.attachments.push(clone);
    }
  }

  /** Élément d'un maillage cloné : le nom du primitif d'origine est conservé dans `userData`. */
  private sourceElement(gltf: GLTF, mesh: THREE.Object3D): string {
    return (mesh.userData.element as string | undefined) ?? elementOf(gltf, mesh);
  }

  /** Joue `start` une fois puis `loop` en boucle (animations de création), sinon l'attente. */
  play(start: string | null, loop: string | null): void {
    const find = (name: string | null) => (name ? this.clips.find(c => c.name.toLowerCase() === name.toLowerCase()) : undefined);
    const idle = this.clips.find(c => c.name === 'idle') ?? this.clips[0];
    const startClip = find(start);
    const loopClip = find(loop) ?? idle;
    this.mixer.stopAllAction();
    this.mixer.removeEventListener('finished', this.onFinished);
    if (startClip && loopClip) {
      const a = this.mixer.clipAction(startClip);
      a.setLoop(THREE.LoopOnce, 1);
      a.clampWhenFinished = true;
      a.play();
      this.current = a;
      this.pendingLoop = loopClip;
      this.mixer.addEventListener('finished', this.onFinished);
    } else if (loopClip) {
      this.current = this.mixer.clipAction(loopClip);
      this.current.play();
    }
  }

  private pendingLoop: THREE.AnimationClip | null = null;
  private onFinished = () => {
    if (!this.pendingLoop) return;
    const next = this.mixer.clipAction(this.pendingLoop);
    next.reset().play();
    if (this.current && this.current !== next) this.current.crossFadeTo(next, 0.2, false);
    this.current = next;
    this.pendingLoop = null;
  };

  update(dt: number): void {
    this.mixer.update(dt);
  }

  dispose(): void {
    this.bakedTexture?.dispose();
    this.mixer.stopAllAction();
    this.root.removeFromParent();
  }
}

/** Cache de chargement : glTF, images décodées et textures three.js. */
export function createAssetCache(load: (url: string) => Promise<GLTF>, base = ''): AssetCache {
  const abs = (url: string) => (/^(\/|[a-z]+:)/.test(url) ? url : base + url);
  const gltfs = new Map<string, Promise<GLTF>>();
  const images = new Map<string, Promise<HTMLImageElement>>();
  const textures = new Map<string, Promise<THREE.Texture>>();
  const image = (url: string) => {
    if (!images.has(url)) {
      images.set(url, new Promise((resolve, reject) => {
        const img = new Image();
        img.crossOrigin = 'anonymous';
        img.onload = () => resolve(img);
        img.onerror = () => reject(new Error(`image ${url}`));
        img.src = abs(url);
      }));
    }
    return images.get(url)!;
  };
  return {
    gltf(url) {
      if (!gltfs.has(url)) {
        gltfs.set(url, load(abs(url)).then(g => {
          // Garde le nom de l'élément sur chaque maillage : il survit aux clonages.
          g.scene.traverse(o => { if ((o as THREE.Mesh).isMesh) o.userData.element = elementOf(g, o); });
          return g;
        }));
      }
      return gltfs.get(url)!;
    },
    image,
    texture(url) {
      if (!textures.has(url)) {
        textures.set(url, image(url).then(img => {
          const t = new THREE.Texture(img);
          t.flipY = false;
          t.colorSpace = THREE.NoColorSpace;
          t.wrapS = t.wrapT = THREE.RepeatWrapping;
          t.needsUpdate = true;
          return t;
        }));
      }
      return textures.get(url)!;
    },
  };
}
