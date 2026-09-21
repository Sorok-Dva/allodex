import * as THREE from 'three';

/** Incendie des navires secondaires uniquement. Les canons et boucliers sont
 * des maillages natifs dans v7NativeShots, sans shader de forme reconstruit. */
export function burningSurface(texture: THREE.Texture | undefined) {
  const material = new THREE.ShaderMaterial({
    uniforms: { map: { value: texture ?? null }, time: { value: 0 }, opacity: { value: 0 } },
    transparent: true, blending: THREE.NormalBlending, depthTest: false,
    depthWrite: false, side: THREE.DoubleSide, toneMapped: false,
    vertexShader: `varying vec2 effectUv;
      void main() { effectUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `uniform sampler2D map;
      uniform float time, opacity;
      varying vec2 effectUv;
      void main() {
        vec2 p = effectUv * 2.0 - 1.0;
        float mask = 1.0 - smoothstep(0.65, 1.0, length(p));
        vec4 texel = texture2D(map, fract(effectUv + vec2(time * 0.12, -time * 0.35)));
        float height = effectUv.y;
        float width = mix(0.8, 0.28, height);
        float silhouette = (1.0 - smoothstep(width * 0.4, width, abs(p.x))) * mask;
        float heat = clamp(texel.a + (0.8 - height) * 0.8, 0.0, 1.0);
        float flame = smoothstep(0.08, 0.65, heat) * silhouette;
        vec3 tint = mix(vec3(0.7, 0.13, 0.015), vec3(1.0, 0.65, 0.12), heat * heat);
        gl_FragColor = vec4(tint, flame * opacity);
      }`,
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(2, 2, 12, 12), material);
  mesh.name = 'V7_cannon_flame';
  mesh.rotation.x = Math.PI / 2;
  mesh.visible = false;
  return mesh;
}
