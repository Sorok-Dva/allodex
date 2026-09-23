import * as THREE from 'three';

/**
 * Particules précalculées du jeu (`(ParticleAnimation).bin`, voir `tools/allods_particles.py`
 * pour le format). Chaque particule a une image de naissance, une durée de vie en images et
 * cinq canaux de clés (position, taille, rotation, couleur, image de texture) ; le lecteur
 * interpole ces clés à chaque image et dessine des quads face caméra (ou couchés à plat pour
 * les émetteurs `Z_QUAD`), en mélange additif ou alpha selon l'émetteur.
 */

export type ParticleChannel = { grid: Uint16Array; values: Float32Array; comps: number };
export type Particle = { birth: number; span: number; channels: ParticleChannel[] };
export type ParticleEmitterData = {
  posMin: [number, number, number];
  posStep: [number, number, number];
  sizeMin: [number, number];
  sizeStep: [number, number];
  particles: Particle[];
};
export type ParticleFile = { textures: number; emitters: ParticleEmitterData[] };

export type ParticleEmitterMeta = {
  additive: boolean;
  tint: [number, number, number];
  render: number;
  pivot: [number, number];
  virtualOffset: number;
  looping: boolean;
  worldSpace: boolean;
  flip: [boolean, boolean];
};
export type ParticleSystemMeta = {
  file: string;
  speed: number;
  loop: boolean;
  endFrame: number;
  loopFrame: number;
  frames: number[];
  emitters: ParticleEmitterMeta[];
};
export type ParticleAtlasMeta = { file: string; width: number; height: number; rects: [number, number, number, number][] };

/** Images par seconde des animations de particules (celles des animations squelettiques). */
export const PARTICLE_FPS = 30;
/** Au-delà de cette durée de vie (images), nombres et positions de clés sont sur 16 bits. */
const WIDE_GRID = 254;
const CHANNELS: [number, number][] = [[3, 2], [2, 2], [1, 2], [4, 1], [1, 1]];

/** Décode un fichier de particules (déjà décompressé). */
export function parseParticles(buffer: ArrayBuffer): ParticleFile {
  const view = new DataView(buffer);
  const textures = view.getUint32(0, true);
  const count = view.getUint32(8, true);
  const emitters: ParticleEmitterData[] = [];
  for (let i = 0; i < count; i += 1) {
    const rec = 12 + 48 * i;
    const f = (k: number) => view.getFloat32(rec + 4 * k, true);
    const table = rec + 40 + view.getUint32(rec + 40, true);
    const n = view.getUint32(rec + 44, true);
    const particles: Particle[] = [];
    for (let j = 0; j < n; j += 1) {
      const entry = table + 12 * j;
      const birth = view.getUint16(entry, true);
      const span = view.getUint16(entry + 2, true);
      let off = entry + 4 + view.getUint32(entry + 4, true);
      const wide = span > WIDE_GRID;
      const channels: ParticleChannel[] = [];
      for (const [comps, width] of CHANNELS) {
        const cnt = wide ? view.getUint16(off, true) : view.getUint8(off);
        off += wide ? 2 : 1;
        const grid = new Uint16Array(Math.max(cnt, 1));
        if (cnt >= 2) {
          grid[cnt - 1] = span;
          for (let k = 1; k < cnt - 1; k += 1) {
            grid[k] = wide ? view.getUint16(off, true) : view.getUint8(off);
            off += wide ? 2 : 1;
          }
        }
        const values = new Float32Array(cnt * comps);
        for (let k = 0; k < cnt * comps; k += 1) {
          values[k] = width === 2 ? view.getUint16(off, true) : view.getUint8(off);
          off += width;
        }
        channels.push({ grid, values, comps });
      }
      particles.push({ birth, span, channels });
    }
    emitters.push({ posMin: [f(0), f(1), f(2)], posStep: [f(3), f(4), f(5)], sizeMin: [f(6), f(7)], sizeStep: [f(8), f(9)], particles });
  }
  return { textures, emitters };
}

/** Interpolation linéaire d'un canal à la position `x` de sa grille (`out` : `comps` valeurs). */
export function sampleChannel(channel: ParticleChannel, x: number, out: Float32Array, step = false): Float32Array {
  const { grid, values, comps } = channel;
  const n = values.length / comps;
  if (n <= 1) { for (let c = 0; c < comps; c += 1) out[c] = values[c] ?? 0; return out; }
  let k = 0;
  while (k < n - 2 && grid[k + 1] <= x) k += 1;
  const g0 = grid[k];
  const g1 = grid[k + 1];
  const w = step ? 0 : Math.min(1, Math.max(0, g1 > g0 ? (x - g0) / (g1 - g0) : 0));
  for (let c = 0; c < comps; c += 1) out[c] = values[k * comps + c] * (1 - w) + values[(k + 1) * comps + c] * w;
  return out;
}

/** Image de l'animation de particules à `local` secondes (en boucle si le système boucle). */
export function particleFrame(local: number, meta: Pick<ParticleSystemMeta, 'speed' | 'loop' | 'endFrame'>): number {
  const frame = local * PARTICLE_FPS * (meta.speed || 1);
  if (meta.loop && meta.endFrame > 0) return frame % meta.endFrame;
  return frame;
}

const VERTEX = /* glsl */`
attribute vec3 iPos;
attribute vec2 iSize;
attribute float iRot;
attribute vec4 iColor;
attribute vec4 iRect;
uniform vec2 pivot;
uniform float virtualOffset;
uniform float lying;
varying vec2 vUv;
varying vec4 vColor;
void main() {
  vec2 corner = position.xy - pivot;
  float c = cos(iRot);
  float s = sin(iRot);
  vec2 r = vec2(c * corner.x - s * corner.y, s * corner.x + c * corner.y) * iSize;
  vec4 mv;
  if (lying > 0.5) {
    mv = modelViewMatrix * vec4(iPos + vec3(r, 0.0), 1.0);
  } else {
    float scale = length(modelMatrix[0].xyz);
    mv = modelViewMatrix * vec4(iPos, 1.0);
    mv.xy += r * scale;
    mv.xyz += normalize(-mv.xyz) * virtualOffset * scale;
  }
  gl_Position = projectionMatrix * mv;
  vUv = iRect.xy + (position.xy + 0.5) * iRect.zw;
  vColor = iColor;
}
`;
const FRAGMENT = /* glsl */`
uniform sampler2D map;
uniform float opacity;
varying vec2 vUv;
varying vec4 vColor;
void main() {
  vec4 texel = texture2D(map, vUv);
  gl_FragColor = vec4(texel.rgb * vColor.rgb, texel.a * vColor.a * opacity);
}
`;

type EmitterView = {
  mesh: THREE.Mesh;
  data: ParticleEmitterData;
  meta: ParticleEmitterMeta;
  pos: THREE.InstancedBufferAttribute;
  size: THREE.InstancedBufferAttribute;
  rot: THREE.InstancedBufferAttribute;
  color: THREE.InstancedBufferAttribute;
  rect: THREE.InstancedBufferAttribute;
  geometry: THREE.InstancedBufferGeometry;
  material: THREE.ShaderMaterial;
};

/** Nombre maximal de particules vivantes à la même image (dimensionne les tampons). */
export function maxAlive(particles: Particle[]): number {
  const events: [number, number][] = [];
  for (const p of particles) { events.push([p.birth, 1]); events.push([p.birth + p.span + 1, -1]); }
  events.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  let alive = 0;
  let best = 0;
  for (const [, d] of events) { alive += d; best = Math.max(best, alive); }
  return best;
}

/** Un système de particules prêt à dessiner : un maillage instancié par émetteur. */
export class ParticleSystemView {
  readonly group = new THREE.Group();
  private readonly emitters: EmitterView[] = [];
  private readonly scratch = new Float32Array(4);
  private readonly meta: ParticleSystemMeta;
  private readonly atlasMeta: ParticleAtlasMeta;

  constructor(file: ParticleFile, meta: ParticleSystemMeta, atlas: THREE.Texture, atlasMeta: ParticleAtlasMeta) {
    this.meta = meta;
    this.atlasMeta = atlasMeta;
    const quad = new THREE.PlaneGeometry(1, 1);
    file.emitters.forEach((data, i) => {
      const em = meta.emitters[i] ?? meta.emitters[meta.emitters.length - 1];
      if (!em || !data.particles.length) return;
      const capacity = Math.max(1, maxAlive(data.particles));
      const geometry = new THREE.InstancedBufferGeometry();
      geometry.index = quad.index;
      geometry.setAttribute('position', quad.getAttribute('position'));
      const attr = (size: number) => new THREE.InstancedBufferAttribute(new Float32Array(capacity * size), size).setUsage(THREE.DynamicDrawUsage);
      const pos = attr(3); const size = attr(2); const rot = attr(1); const color = attr(4); const rect = attr(4);
      geometry.setAttribute('iPos', pos);
      geometry.setAttribute('iSize', size);
      geometry.setAttribute('iRot', rot);
      geometry.setAttribute('iColor', color);
      geometry.setAttribute('iRect', rect);
      geometry.instanceCount = 0;
      const material = new THREE.ShaderMaterial({
        vertexShader: VERTEX,
        fragmentShader: FRAGMENT,
        uniforms: {
          map: { value: atlas },
          opacity: { value: 1 },
          pivot: { value: new THREE.Vector2(em.pivot[0], em.pivot[1]) },
          virtualOffset: { value: em.virtualOffset },
          lying: { value: em.render === 1 ? 1 : 0 },
        },
        transparent: true,
        depthWrite: false,
        side: THREE.DoubleSide,
        blending: em.additive ? THREE.AdditiveBlending : THREE.NormalBlending,
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.frustumCulled = false;
      mesh.renderOrder = 2;
      this.group.add(mesh);
      this.emitters.push({ mesh, data, meta: em, pos, size, rot, color, rect, geometry, material });
    });
    quad.dispose();
  }

  /** Pose les particules à `local` secondes de la vie de l'objet, avec son opacité. */
  update(local: number, opacity: number): void {
    const frame = particleFrame(local, this.meta);
    const { width, height, rects } = this.atlasMeta;
    const s = this.scratch;
    for (const view of this.emitters) {
      const { data, meta } = view;
      view.material.uniforms.opacity.value = opacity;
      let n = 0;
      for (const p of data.particles) {
        const x = frame - p.birth;
        if (x < 0 || x > p.span) continue;
        const [cp, cs, cr, cc, cf] = p.channels;
        sampleChannel(cp, x, s);
        view.pos.setXYZ(n, data.posMin[0] + s[0] * data.posStep[0], data.posMin[1] + s[1] * data.posStep[1], data.posMin[2] + s[2] * data.posStep[2]);
        sampleChannel(cs, x, s);
        view.size.setXY(n, (data.sizeMin[0] + s[0] * data.sizeStep[0]) * (meta.flip[0] ? -1 : 1),
          (data.sizeMin[1] + s[1] * data.sizeStep[1]) * (meta.flip[1] ? -1 : 1));
        sampleChannel(cr, x, s);
        view.rot.setX(n, (s[0] / 65536) * Math.PI * 2);
        sampleChannel(cc, x, s);
        view.color.setXYZW(n, (s[0] / 255) * meta.tint[0], (s[1] / 255) * meta.tint[1], (s[2] / 255) * meta.tint[2], s[3] / 255);
        sampleChannel(cf, x, s, true);
        const index = this.meta.frames[Math.round(s[0])] ?? -1;
        const r = rects[index];
        if (r) view.rect.setXYZW(n, r[0] / width, r[1] / height, r[2] / width, r[3] / height);
        else view.rect.setXYZW(n, 0, 0, 0, 0);
        n += 1;
      }
      view.geometry.instanceCount = n;
      for (const a of [view.pos, view.size, view.rot, view.color, view.rect]) a.needsUpdate = true;
    }
  }

  dispose(): void {
    for (const view of this.emitters) { view.geometry.dispose(); view.material.dispose(); }
  }
}

/** Télécharge et décompresse (zlib) un fichier de particules. */
export async function loadParticleFile(url: string): Promise<ParticleFile> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`particules introuvables : ${url}`);
  const stream = response.body!.pipeThrough(new DecompressionStream('deflate'));
  const buffer = await new Response(stream).arrayBuffer();
  return parseParticles(buffer);
}
