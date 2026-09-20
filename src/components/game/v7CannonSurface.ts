import * as THREE from 'three';

/** Calque texturé à contour progressif : aucune bordure de quad, même sur Fire07,
 * dont la couleur est blanche partout et dont seul l'alpha porte les flammes. */
export function cannonSurface(texture: THREE.Texture | undefined, electric: boolean) {
  const material = new THREE.ShaderMaterial({
    uniforms: {
      map: { value: texture ?? null }, time: { value: 0 }, opacity: { value: 0 },
      electric: { value: electric ? 1 : 0 },
      regeneration: { value: 0 }, phase: { value: 0 },
    },
    transparent: true, blending: THREE.AdditiveBlending, depthTest: false,
    depthWrite: false, side: THREE.DoubleSide, toneMapped: false,
    vertexShader: `varying vec2 effectUv;
      void main() { effectUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `uniform sampler2D map;
      uniform float time, opacity, electric, regeneration, phase;
      varying vec2 effectUv;
      void main() {
        vec2 p = effectUv * 2.0 - 1.0;
        float radius = length(p);
        float mask = 1.0 - smoothstep(0.65, 1.0, radius);
        vec2 scroll = fract(effectUv + vec2(time * 0.7, -time * 0.31));
        vec4 texel = texture2D(map, scroll);
        float strands = dot(texel.rgb, vec3(0.3, 0.5, 0.2)) * texel.a;
        float energy = mix(texel.a, pow(strands, 2.0), electric);
        vec3 tint = mix(vec3(4.0, 0.85, 0.08), vec3(0.4, 0.65, 2.6), electric);
        tint = mix(tint, vec3(1.8, 0.35, 3.2), regeneration);
        // Une onde violette reconstruit la membrane du bord vers le centre.
        float seam = exp(-pow((radius - (1.0 - phase)) * 14.0, 2.0));
        energy += regeneration * seam * 0.22;
        gl_FragColor = vec4(tint, energy * mask * opacity);
      }`,
  });
  const geometry = new THREE.PlaneGeometry(2, 2, 12, 12);
  // Bombement léger de la membrane : elle épouse un volume, pas un panneau plat.
  if (electric) {
    const position = geometry.getAttribute('position');
    for (let i = 0; i < position.count; i++) {
      const x = position.getX(i), y = position.getY(i);
      position.setZ(i, Math.max(0, 1 - x * x - y * y) * .25);
    }
  }
  const mesh = new THREE.Mesh(geometry, material);
  mesh.name = electric ? 'V7_cannon_membrane' : 'V7_cannon_flame';
  mesh.rotation.x = Math.PI / 2;
  mesh.renderOrder = 1002;
  mesh.visible = false;
  return mesh;
}
