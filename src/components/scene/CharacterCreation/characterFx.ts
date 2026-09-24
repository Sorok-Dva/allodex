import * as THREE from 'three';
import type { GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { loadParticleFile } from '@/components/scene/FatalityViewer/particles';
import { VotFactory, updateInstance, type VotInstance } from '@/components/scene/vot/votInstances';
import type { ChargenData } from '@/data/character/chargen.types';
import type { CharacterRig } from './rig';

/**
 * Effet à poser sur un personnage : gabarit (`fx/…glb`), locator, échelle, instant de départ.
 * `effectsOnly` : objet porté dont le maillage est déjà accroché par `CharacterRig` (seuls ses
 * composants et particules sont montrés). `runType` : `ChargenEffectRunType` de la tenue (types 7.0 :
 * 0 = `CHARGEN_EFFECT_RUN_TYPE_KEY`, joué une fois ; 1 = `CHARGEN_EFFECT_RUN_TYPE_LOOP`, rejoué en boucle).
 */
export type FxWant = { fx: string; locator: string; scale?: number; start: number; effectsOnly?: boolean; runType?: number };

/** `period` : durée du gabarit rejoué en boucle ; `until` : fin d'un effet joué une fois (s, temps local). */
type Live = { key: string; inst: VotInstance; start: number; period: number | null; until: number | null };

/**
 * Effets des personnages de la création (`tools/chargen_fx.py`) : ceux des objets portés (boule de
 * feu du mage) et ceux de la tenue de création (`growths[].fx`), gabarits animés avec leurs
 * particules, accrochés aux articulations du personnage et rejoués au temps de la scène (même
 * lecture que les cinématiques et les fatalités : `VotFactory`, `updateInstance`).
 */
export class CharacterFxHost {
  private readonly factory: VotFactory;
  private readonly disposables: { dispose(): void }[] = [];
  private readonly glbs = new Map<string, Promise<GLTF | null>>();
  private readonly lives = new Map<CharacterRig, Live[]>();
  private atlasPromise: Promise<void> | null = null;
  private readonly data: ChargenData;
  private readonly base: string;
  private readonly load: (url: string) => Promise<GLTF>;

  constructor(data: ChargenData, base: string, load: (url: string) => Promise<GLTF>) {
    this.data = data;
    this.base = base;
    this.load = load;
    this.factory = new VotFactory({ objects: data.fx?.objects ?? {}, baseUrl: base, disposables: this.disposables });
  }

  private glb(file: string): Promise<GLTF | null> {
    if (!this.glbs.has(file)) this.glbs.set(file, this.load(this.base + file).catch(() => null));
    return this.glbs.get(file)!;
  }

  /** Atlas et fichiers de particules des gabarits voulus (une fois chacun). */
  private async particles(files: string[]): Promise<void> {
    const meta = this.data.fx?.particleAtlas;
    if (meta && !this.atlasPromise && typeof DecompressionStream !== 'undefined') {
      this.atlasPromise = new THREE.TextureLoader().loadAsync(this.base + meta.file).then(atlas => {
        atlas.flipY = false;
        atlas.colorSpace = THREE.NoColorSpace;
        atlas.needsUpdate = true;
        this.factory.atlasTexture = atlas;
        this.factory.particleAtlas = meta;
        this.disposables.push(atlas);
      }).catch(() => undefined);
    }
    await this.atlasPromise;
    const objects = this.data.fx?.objects ?? {};
    const wanted = new Set<string>();
    const visit = (vot: string, depth = 0) => {
      const info = objects[vot];
      if (!info || depth > 8) return;
      const system = info.particles as { file?: string } | undefined;
      if (system?.file && !this.factory.particleFiles.has(system.file)) wanted.add(system.file);
      for (const c of info.components ?? []) visit(c.vot, depth + 1);
    };
    for (const f of files) visit(f);
    if (typeof DecompressionStream === 'undefined') return;
    await Promise.all([...wanted].map(file => loadParticleFile(this.base + file)
      .then(parsed => { this.factory.particleFiles.set(file, parsed); }).catch(() => { this.factory.particleFiles.set(file, null); })));
  }

  /** Remplace les effets d'un personnage par `wants` (ceux déjà posés et toujours voulus restent). */
  async sync(rig: CharacterRig, wants: FxWant[]): Promise<void> {
    const keyOf = (w: FxWant) => `${w.fx}@${w.locator}@${w.start}`;
    const current = this.lives.get(rig) ?? [];
    const keep = current.filter(l => wants.some(w => keyOf(w) === l.key));
    for (const l of current) if (!keep.includes(l)) this.remove(l);
    this.lives.set(rig, keep);
    const missing = wants.filter(w => !keep.some(l => l.key === keyOf(w)));
    if (!missing.length) return;
    const gltfs = await Promise.all(missing.map(w => this.glb(w.fx)));
    const roots = gltfs.map(g => g?.scene.children.find(c => (c.userData as { vot?: string }).vot) ?? null);
    await this.particles(roots.map(r => (r?.userData as { vot?: string } | undefined)?.vot ?? '').filter(Boolean));
    const lives = this.lives.get(rig);
    if (!lives) return;       // personnage retiré pendant le chargement
    missing.forEach((w, i) => {
      const proto = roots[i];
      const gltf = gltfs[i];
      if (!proto || !gltf || lives.some(l => l.key === keyOf(w))) return;
      const vot = (proto.userData as { vot: string }).vot;
      const info = this.data.fx?.objects[vot];
      const inst = this.factory.instantiate(proto, gltf.animations, w.start, Infinity, 0, 0);
      inst.root.scale.setScalar((w.scale || 1) * (info?.scale || 1));
      if (w.effectsOnly) {
        const own = inst.root.getObjectByName(THREE.PropertyBinding.sanitizeNodeName(`${vot}_mesh`));
        if (own) own.visible = false;
      }
      (rig.joint(w.locator) ?? rig.model).add(inst.root);
      // Gabarit non bouclé (`loop` faux, durée connue) : effacé à la fin de sa durée quand la tenue le
      // joue une fois (sans cela, sa dernière image restait figée : traînées du guerrier) ; rejoué
      // à chaque période quand elle le boucle.
      const duration = info && !info.loop && info.duration > 0 ? info.duration : null;
      lives.push({ key: keyOf(w), inst, start: w.start, period: w.runType === 1 ? duration : null,
        until: w.runType === 0 ? duration : null });
    });
  }

  /** Pose les effets au temps `t` de la scène. */
  update(t: number, camera: THREE.Camera): void {
    for (const lives of this.lives.values()) {
      for (const l of lives) {
        let local = Math.max(0, t - l.start);
        if (l.period) local %= l.period;
        updateInstance(l.inst, local, l.until !== null && local > l.until ? 0 : 1, camera);
      }
    }
  }

  forget(rig: CharacterRig): void {
    for (const l of this.lives.get(rig) ?? []) this.remove(l);
    this.lives.delete(rig);
  }

  private remove(l: Live): void {
    l.inst.mixer.stopAllAction();
    l.inst.root.removeFromParent();
  }

  dispose(): void {
    for (const rig of [...this.lives.keys()]) this.forget(rig);
    for (const d of this.disposables) d.dispose();
  }
}
