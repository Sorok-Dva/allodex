import * as THREE from 'three';
import { GLTFExporter } from 'three/examples/jsm/exporters/GLTFExporter.js';
import { clone as cloneSkinned } from 'three/examples/jsm/utils/SkeletonUtils.js';
import type { CharacterRig } from './rig';
import type { CharacterDescriptor } from '@/data/character/descriptor';

export type ExportRequest = {
  primary: CharacterRig;
  companions: (CharacterRig | null)[];
  name: string;
  /** Clips à inclure pour le personnage principal (les absents sont ignorés). */
  clips: (string | null)[];
  descriptor: CharacterDescriptor;
};

/**
 * Copie exportable d'un personnage : géosets visibles seulement, matériaux ramenés à
 * `MeshStandardMaterial` (lu partout : three.js, Blender), texture cuite incluse (le canevas
 * composé est encodé en PNG par l'exportateur), modèles accrochés compris.
 */
function exportable(rig: CharacterRig, prefix: string): THREE.Object3D {
  const copy = cloneSkinned(rig.root);
  copy.name = prefix;
  const drop: THREE.Object3D[] = [];
  copy.traverse(o => {
    const mesh = o as THREE.Mesh;
    if (!mesh.isMesh) return;
    if (!mesh.visible) { drop.push(mesh); return; }
    const src = mesh.material as THREE.MeshLambertMaterial;
    const m = new THREE.MeshStandardMaterial({
      name: src.name, map: src.map, color: src.color.clone(), transparent: src.transparent,
      alphaTest: src.alphaTest, side: THREE.DoubleSide, roughness: 1, metalness: 0,
    });
    if (src.blending === THREE.AdditiveBlending) m.userData.blend = 'add';
    mesh.material = m;
  });
  for (const o of drop) o.removeFromParent();
  return copy;
}

/**
 * `.glb` unique du personnage configuré (export côté navigateur, `GLTFExporter`) : le
 * squelette, les géosets visibles, la texture cuite et les clips demandés ; le trio gibberling
 * et le familier sont des nœuds frères, chacun avec son squelette et son attente (`<nœud>:idle`).
 * Le repère du jeu (Z en haut, main droite : comparé aux écrans du client, sans miroir) est
 * tourné vers celui du glTF (Y en haut) par le nœud racine — sans échelle négative, que les
 * visionneuses rendent retournée ; le descripteur voyage dans `asset.extras`.
 */
export async function exportCharacterGlb(req: ExportRequest): Promise<Blob> {
  const root = new THREE.Group();
  root.name = req.name;
  // Z en haut → Y en haut.
  root.rotation.x = -Math.PI / 2;
  root.userData = { allodex: req.descriptor };
  const main = exportable(req.primary, req.name);
  // Pose native du modèle : ni la rotation du glisser, ni l'échelle de la place du décor.
  const unit = main.scale.x || 1;
  main.rotation.set(0, 0, 0);
  main.scale.setScalar(1);
  root.add(main);
  const animations: THREE.AnimationClip[] = [];
  const wanted = new Set(req.clips.filter(Boolean).map(c => (c as string).toLowerCase()));
  for (const clip of req.primary.clips) if (wanted.has(clip.name.toLowerCase())) animations.push(clip);
  const labels = ['secondary', 'tertiary', 'pet'];
  req.companions.forEach((rig, i) => {
    if (!rig) return;
    const node = exportable(rig, labels[i]);
    node.position.divideScalar(unit);
    node.rotation.set(0, 0, 0);
    node.scale.setScalar(1);
    root.add(node);
    const idle = rig.clips.find(c => c.name === 'idle') ?? rig.clips[0];
    if (idle) {
      // Les pistes visent les os par nom : le préfixe du gabarit distingue les squelettes,
      // sauf pour les compagnons du même gabarit que le personnage (même squelette nommé).
      const clip = idle.clone();
      clip.name = `${labels[i]}:idle`;
      if (rig.template !== req.primary.template) animations.push(clip);
    }
  });
  root.updateMatrixWorld(true);
  const exporter = new GLTFExporter();
  const result = await exporter.parseAsync(root, { binary: true, animations, onlyVisible: true, includeCustomExtensions: false });
  const buffer = result as ArrayBuffer;
  return new Blob([buffer], { type: 'model/gltf-binary' });
}
