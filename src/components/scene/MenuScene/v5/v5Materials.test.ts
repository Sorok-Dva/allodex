import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { ALPHA_TEST, applyV5Materials, hasNoVertexAlpha, ignoreVertexAlpha, type V5Material } from './v5Materials';

function primitive(parent: THREE.Object3D, element: string) {
  const material = new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true });
  material.depthTest = false; material.depthWrite = false;
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(), material);
  mesh.geometry.userData.element = element;
  parent.add(mesh);
  return mesh;
}

/** Couleur de sommet RGBA (0-255) uniforme sur les quatre sommets du quad. */
function paint<T extends THREE.Mesh>(mesh: T, rgba: [number, number, number, number]): T {
  const count = mesh.geometry.getAttribute('position').count;
  const values = new Uint8Array(count * 4);
  for (let i = 0; i < count; i += 1) values.set(rgba, i * 4);
  mesh.geometry.setAttribute('color', new THREE.BufferAttribute(values, 4, true));
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

describe('V5 alpha de sommet nul sur tout un élément', () => {
  it('le reconnaît sans confondre avec un alpha qui varie ou une couleur sans alpha', () => {
    const root = new THREE.Group();
    const rock = paint(primitive(root, 'Allods'), [128, 128, 128, 0]);
    const sibling = primitive(root, 'Allods2');
    const values = new Uint8Array([128, 128, 128, 0, 128, 128, 128, 255, 128, 128, 128, 128, 128, 128, 128, 64]);
    sibling.geometry.setAttribute('color', new THREE.BufferAttribute(values, 4, true));
    const rgbOnly = primitive(root, 'Tower');
    rgbOnly.geometry.setAttribute('color', new THREE.BufferAttribute(new Uint8Array(12), 3, true));
    expect(hasNoVertexAlpha(rock.geometry)).toBe(true);
    expect(hasNoVertexAlpha(sibling.geometry)).toBe(false);
    expect(hasNoVertexAlpha(rgbOnly.geometry)).toBe(false);
    expect(hasNoVertexAlpha(new THREE.PlaneGeometry())).toBe(false); // sans couleur de sommet
  });

  it('ne regarde que les sommets indexés par la primitive, pas le tampon partagé', () => {
    // Deux primitives d'un même objet : même tampon de couleurs, index différents.
    const values = new Uint8Array([128, 128, 128, 0, 128, 128, 128, 0, 128, 128, 128, 255, 128, 128, 128, 255]);
    const color = new THREE.BufferAttribute(values, 4, true);
    const rock = new THREE.BufferGeometry(); rock.setAttribute('color', color);
    rock.setIndex([0, 1, 0]);
    const sibling = new THREE.BufferGeometry(); sibling.setAttribute('color', color);
    sibling.setIndex([2, 3, 2]);
    expect(hasNoVertexAlpha(rock)).toBe(true);
    expect(hasNoVertexAlpha(sibling)).toBe(false);
  });

  it('garde le mélange du rocher mais n’applique que son RGB, sinon il serait invisible', () => {
    const root = new THREE.Group();
    const group = new THREE.Group(); group.name = 'Animated_Background_5_0_mesh'; root.add(group);
    const rock = paint(primitive(group, 'Allods'), [128, 128, 128, 0]);
    const cloud = paint(primitive(group, 'Back1'), [128, 128, 128, 200]);
    // Le matériau du xdb est partagé entre les deux primitives, comme dans le glTF.
    cloud.material = rock.material;
    const shared = rock.material;
    const applied = applyV5Materials(root, { Animated_Background_5_0: [
      { element: 'Allods', blend: 'alpha', transparent: true },
      { element: 'Back1', blend: 'alpha', transparent: true },
    ] });
    expect(applied.rgbOnly).toBe(1);
    expect(rock.material).not.toBe(shared); // cloné : le voisin garde son masque
    expect(cloud.material).toBe(shared);
    expect(rock.material.transparent).toBe(true);
    expect(rock.material.depthTest).toBe(true);
    const shader = { fragmentShader: 'a\n#include <color_fragment>\nb', vertexShader: '', uniforms: {} } as unknown as THREE.WebGLProgramParametersWithUniforms;
    rock.material.onBeforeCompile(shader, {} as THREE.WebGLRenderer);
    expect(shader.fragmentShader).toContain('diffuseColor.rgb *= vColor.rgb');
    // La nappe de nuages, elle, garde son alpha de sommet : c'est son masque.
    const untouched = { fragmentShader: 'a\n#include <color_fragment>\nb', vertexShader: '', uniforms: {} } as unknown as THREE.WebGLProgramParametersWithUniforms;
    cloud.material.onBeforeCompile(untouched, {} as THREE.WebGLRenderer);
    expect(untouched.fragmentShader).toContain('#include <color_fragment>');
    applied.dispose();
    expect(rock.material).toBe(shared); // matériau natif rendu au démontage
  });
});
