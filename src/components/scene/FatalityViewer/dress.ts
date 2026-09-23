import * as THREE from 'three';
import type { GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js';
import type { ChargenData, Sex } from '@/data/character/chargen.types';
import { defaultAppearance } from '@/data/character/descriptor';
import { resolveLook } from '@/data/character/look';
import { CharacterRig, createAssetCache } from '@/components/scene/CharacterCreation/rig';
import type { Tinted } from '@/components/scene/vot/votInstances';

/**
 * Personnages habillés des fatalités : les modèles de la création de personnage
 * (`public/game/character/models/<Gabarit>.glb`, tous les géosets, un primitif chacun) portant
 * la tenue d'une classe (`growths` : départ, intermédiaire, supérieur) — apparence résolue par
 * `resolveLook` comme sur l'écran de création, peau cuite et modèles accrochés (armes, casques)
 * par `CharacterRig`. Les clips des fatalités (`characters/<id>.glb`, squelette sans maillage)
 * s'y lient tels quels : même squelette, mêmes noms d'articulations (`<Gabarit>/<Articulation>`).
 */
export type FatalityDress = {
  data: ChargenData;
  /** Racine des fichiers de la création (`/game/character/`). */
  base: string;
  template: string;
  sex: Sex;
  /** Objets de la tenue (`growths[tier].items`) ; vide sans tenue. */
  items: { slot: string; item: string }[];
  tier: number | null;
  /** Trio des gibelins : deux compagnons au même habit, à côté du premier. */
  trio?: boolean;
};

/**
 * Place des deux compagnons du trio gibelin, en mètres dans le repère du personnage (il regarde
 * −Y) : **placement inventé**, le client code celui du jeu sans le publier dans ses données.
 * Même décalage que l'écran de création (`ChargenViewer`, `COMPANION_OFFSETS`).
 */
export const TRIO_OFFSETS: [number, number][] = [[-0.75, 0.45], [0.75, 0.45]];

/** Un corps à animer : sa racine posée dans la scène, son modèle, ses clips. */
export type Body = {
  holder: THREE.Object3D;
  model: THREE.Object3D;
  modelRoot: THREE.Object3D;
  mixer: THREE.AnimationMixer;
  actions: Map<string, THREE.AnimationAction>;
  durations: Map<string, number>;
  tinted: Tinted[];
  baseScale: THREE.Vector3;
};

/** Matériaux (sans doublon) d'un sous-arbre, pour les fondus de la victime. */
export function tintedOf(root: THREE.Object3D): Tinted[] {
  const seen = new Set<THREE.Material>();
  const out: Tinted[] = [];
  root.traverse(node => {
    const mesh = node as THREE.Mesh;
    if (!mesh.isMesh) return;
    for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
      if (seen.has(material)) continue;
      seen.add(material);
      out.push({ material: material as Tinted['material'], base: material.opacity, transparent: material.transparent });
    }
  });
  return out;
}

/** Actions (en pause, pilotées à la main) des clips d'animation sur un modèle. */
export function bindClips(model: THREE.Object3D, clips: THREE.AnimationClip[]): Pick<Body, 'mixer' | 'actions' | 'durations'> {
  const mixer = new THREE.AnimationMixer(model);
  const actions = new Map<string, THREE.AnimationAction>();
  const durations = new Map<string, number>();
  for (const clip of clips) {
    const action = mixer.clipAction(clip);
    action.play();
    action.paused = true;
    actions.set(clip.name, action);
    durations.set(clip.name, clip.duration);
  }
  return { mixer, actions, durations };
}

/**
 * Corps habillés d'un personnage (1, ou 3 pour le trio gibelin), tous sous `holder`. Renvoie
 * `null` si le gabarit n'a pas de modèle de création (le lecteur retombe alors sur le `.glb`
 * des fatalités).
 */
export async function dressedBodies(dress: FatalityDress, model: string, clips: THREE.AnimationClip[],
  load: (url: string) => Promise<GLTF>, holder: THREE.Object3D): Promise<Body[] | null> {
  const tpl = dress.data.templates[dress.template];
  if (!tpl?.glb) return null;
  const cache = createAssetCache(load, dress.base);
  const gltf = await cache.gltf(tpl.glb);
  const offsets: [number, number][] = [[0, 0], ...(dress.trio ? TRIO_OFFSETS : [])];
  const bodies: Body[] = [];
  for (const [ox, oy] of offsets) {
    const rig = new CharacterRig(gltf, cache, dress.template);
    const look = resolveLook(dress.data, dress.template, tpl, dress.sex, defaultAppearance(tpl), dress.items,
      { equipment: dress.tier, helmet: true }, rig.textured);
    await rig.apply(look);
    rig.root.position.set(ox, oy, 0);
    holder.add(rig.root);
    const modelRoot = rig.model.getObjectByName(THREE.PropertyBinding.sanitizeNodeName(model)) ?? rig.model;
    bodies.push({ holder: rig.root, model: rig.model, modelRoot, ...bindClips(rig.model, clips), tinted: tintedOf(rig.root),
      baseScale: modelRoot.scale.clone() });
  }
  return bodies;
}
