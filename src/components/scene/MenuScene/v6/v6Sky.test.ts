import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { RGB_ONLY_COLOR_FRAGMENT, hasZeroVertexAlpha, ignoreVertexAlpha, restoreOpaqueVertexAlpha } from './v6Sky';

function colored(alphas: number[], parent: THREE.Object3D, material: THREE.MeshBasicMaterial) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(alphas.flatMap((_, i) => [i, 0, 0]), 3));
  geometry.setAttribute('color', new THREE.Uint8BufferAttribute(alphas.flatMap(a => [100, 110, 105, a]), 4, true));
  geometry.setIndex(alphas.map((_, i) => i));
  const mesh = new THREE.Mesh(geometry, material);
  parent.add(mesh);
  return mesh;
}

describe('V6 sky dome', () => {
  it('ne retient que les primitives dont chaque sommet indexé a un alpha nul', () => {
    const root = new THREE.Group(); const material = new THREE.MeshBasicMaterial({ vertexColors: true });
    expect(hasZeroVertexAlpha(colored([0, 0, 0], root, material).geometry)).toBe(true);
    expect(hasZeroVertexAlpha(colored([0, 0, 255], root, material).geometry)).toBe(false);
    expect(hasZeroVertexAlpha(new THREE.PlaneGeometry())).toBe(false); // pas de couleur de sommet
    // Un sommet non référencé par l'index ne compte pas.
    const partial = colored([0, 0, 255], root, material);
    partial.geometry.setIndex([0, 1, 0]);
    expect(hasZeroVertexAlpha(partial.geometry)).toBe(true);
  });
  it('clone le matériau partagé du dôme et ne garde que le RGB des couleurs de sommet', () => {
    const root = new THREE.Group(); const shared = new THREE.MeshBasicMaterial({ vertexColors: true });
    const sky = colored([0, 0, 0], root, shared);
    const mountain = colored([255, 255, 255], root, shared);
    expect(restoreOpaqueVertexAlpha(root)).toBe(1);
    expect(mountain.material).toBe(shared);
    expect(sky.material).not.toBe(shared);
    // `onBeforeCompile` reçoit le shader avant l'expansion des includes.
    const shader = { fragmentShader: 'void main() {\n\t#include <map_fragment>\n\t#include <color_fragment>\n}' } as THREE.WebGLProgramParametersWithUniforms;
    (sky.material as THREE.MeshBasicMaterial).onBeforeCompile(shader, {} as THREE.WebGLRenderer);
    expect(shader.fragmentShader).toContain(RGB_ONLY_COLOR_FRAGMENT);
    expect(shader.fragmentShader).toContain('#include <map_fragment>');
    expect(shader.fragmentShader).not.toContain('#include <color_fragment>');
    expect((sky.material as THREE.MeshBasicMaterial).customProgramCacheKey()).toBe('v6-opaque-vertex-alpha');
  });
  it('couvre aussi la forme expansée du bloc et laisse intact un shader sans alpha de sommet', () => {
    expect(ignoreVertexAlpha('\tdiffuseColor *= vColor;\n')).toBe('\tdiffuseColor.rgb *= vColor.rgb;\n');
    expect(ignoreVertexAlpha('diffuseColor.rgb *= vColor.rgb;')).toBe('diffuseColor.rgb *= vColor.rgb;');
  });
});
