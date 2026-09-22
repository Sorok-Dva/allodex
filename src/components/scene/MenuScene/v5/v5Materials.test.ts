import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { ALPHA_TEST, applyV5Materials, ignoreVertexAlpha, type V5Material } from './v5Materials';

function primitive(parent: THREE.Object3D, element: string) {
  const material = new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true });
  material.depthTest = false; material.depthWrite = false;
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(), material);
  mesh.geometry.userData.element = element;
  parent.add(mesh);
  return mesh;
}

function scene() {
  const root = new THREE.Group();
  const group = new THREE.Group(); group.name = 'Animated_Background_5_0_mesh'; root.add(group);
  const bowl = primitive(group, 'Back6');
  const cloud = primitive(group, 'Back1');
  const tower = primitive(group, 'Tower');
  return { root, group, bowl, cloud, tower };
}
const flags: V5Material[] = [
  { element: 'Back6', blend: 'alpha', transparent: false },
  { element: 'Back1', blend: 'alpha', transparent: true },
  { element: 'Tower', blend: 'alpha', transparent: false },
];

describe('V5 matériaux non mélangés du xdb', () => {
  it('découpe par test d’alpha, écrit la profondeur et ignore l’alpha de sommet des matériaux non transparents', () => {
    const { root, bowl, cloud, tower } = scene();
    const applied = applyV5Materials(root, { Animated_Background_5_0: flags });
    expect(applied.count).toBe(3);
    for (const opaque of [bowl, tower]) {
      expect(opaque.material.transparent).toBe(false);
      expect(opaque.material.alphaTest).toBe(ALPHA_TEST);
      expect(opaque.material.depthTest).toBe(true);
      expect(opaque.material.depthWrite).toBe(true);
      expect(opaque.material.vertexColors).toBe(true); // le RGB module toujours
      const shader = { fragmentShader: 'a\n#include <color_fragment>\nb', vertexShader: '', uniforms: {} } as unknown as THREE.WebGLProgramParametersWithUniforms;
      opaque.material.onBeforeCompile(shader, {} as THREE.WebGLRenderer);
      expect(shader.fragmentShader).toContain('diffuseColor.rgb *= vColor.rgb');
      expect(shader.fragmentShader).not.toContain('diffuseColor *= vColor');
    }
    // Mélangé : reste en mélange alpha, mais testé contre la profondeur des opaques.
    expect(cloud.material.transparent).toBe(true);
    expect(cloud.material.alphaTest).toBe(0);
    expect(cloud.material.depthTest).toBe(true);
    expect(cloud.material.depthWrite).toBe(false);
    applied.dispose();
    expect(tower.material.transparent).toBe(true);
    expect(tower.material.depthWrite).toBe(false);
    expect(tower.material.alphaTest).toBe(0);
  });

  it('ne devine rien quand le méta et l’export ne comptent pas le même nombre de primitives', () => {
    const { root, tower } = scene();
    expect(applyV5Materials(root, { Animated_Background_5_0: flags.slice(0, 2) }).count).toBe(0);
    expect(tower.material.transparent).toBe(true);
    expect(applyV5Materials(root, undefined).count).toBe(0);
    expect(applyV5Materials(root, { Raid_Ship: flags }).count).toBe(0); // groupe absent
  });

  it('réécrit aussi le bloc de couleur déjà expansé', () => {
    const expanded = '#if defined( USE_COLOR_ALPHA )\n\tdiffuseColor *= vColor;\n#elif defined( USE_COLOR )\n\tdiffuseColor.rgb *= vColor;\n#endif';
    expect(ignoreVertexAlpha(expanded)).toContain('diffuseColor.rgb *= vColor.rgb');
  });
});
