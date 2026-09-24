// Allège des `.glb` exportés : retire les accesseurs que rien ne référence, puis compresse les
// tampons de sommets, d'indices et d'animation en `EXT_meshopt_compression` (sans perte : le
// décodeur rend les octets d'origine). Le lecteur pose `MeshoptDecoder` sur son `GLTFLoader`.
//
//     node tools/compress_glb.mjs public/game/auras/models/s*.glb
//
// Seuls les tampons d'un accesseur unique, à éléments de 4 à 256 octets multiples de 4 (sommets,
// clés d'animation) ou d'indices de triangles (uint16/uint32, compte multiple de 3), sont
// compressés ; les autres restent tels quels.
import { readFileSync, writeFileSync } from 'node:fs';
import { MeshoptEncoder } from 'meshoptimizer';

const COMPONENT = { 5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4 };
const COUNT = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4, MAT2: 4, MAT3: 9, MAT4: 16 };
const align = n => (n + 3) & ~3;

function parse(buf) {
  const jsonLen = buf.readUInt32LE(12);
  const json = JSON.parse(buf.subarray(20, 20 + jsonLen).toString('utf8'));
  const binStart = 20 + jsonLen + 8;
  const binLen = buf.readUInt32LE(20 + jsonLen);
  return { json, bin: buf.subarray(binStart, binStart + binLen) };
}

function write(json, bin) {
  const text = Buffer.from(JSON.stringify(json), 'utf8');
  const jsonChunk = Buffer.concat([text, Buffer.alloc(align(text.length) - text.length, 0x20)]);
  const binChunk = Buffer.concat([bin, Buffer.alloc(align(bin.length) - bin.length)]);
  const header = Buffer.alloc(12);
  header.write('glTF', 0);
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(12 + 8 + jsonChunk.length + 8 + binChunk.length, 8);
  const h1 = Buffer.alloc(8); h1.writeUInt32LE(jsonChunk.length, 0); h1.writeUInt32LE(0x4e4f534a, 4);
  const h2 = Buffer.alloc(8); h2.writeUInt32LE(binChunk.length, 0); h2.writeUInt32LE(0x004e4942, 4);
  return Buffer.concat([header, h1, jsonChunk, h2, binChunk]);
}

/** Références d'accesseurs du document : `[objet, clé]` à réécrire. */
function accessorRefs(json) {
  const refs = [];
  for (const mesh of json.meshes ?? []) for (const p of mesh.primitives) {
    for (const k of Object.keys(p.attributes)) refs.push([p.attributes, k]);
    if (p.indices !== undefined) refs.push([p, 'indices']);
    for (const t of p.targets ?? []) for (const k of Object.keys(t)) refs.push([t, k]);
  }
  for (const a of json.animations ?? []) for (const s of a.samplers) { refs.push([s, 'input']); refs.push([s, 'output']); }
  for (const s of json.skins ?? []) if (s.inverseBindMatrices !== undefined) refs.push([s, 'inverseBindMatrices']);
  return refs;
}

export function compress(buf) {
  const { json, bin } = parse(buf);
  if ((json.extensionsUsed ?? []).includes('EXT_meshopt_compression')) return buf;
  // 1. accesseurs référencés seulement, renumérotés.
  const refs = accessorRefs(json);
  const keep = [...new Set(refs.map(([o, k]) => o[k]))].sort((a, b) => a - b);
  const newIndex = new Map(keep.map((old, i) => [old, i]));
  for (const [o, k] of refs) o[k] = newIndex.get(o[k]);
  const accessors = keep.map(i => json.accessors[i]);
  const indexAccessors = new Set((json.meshes ?? []).flatMap(m => m.primitives.map(p => p.indices)).filter(i => i !== undefined));
  // 2. une vue par accesseur, compressée si possible.
  const views = [];
  const main = [];
  let mainLen = 0;
  let fallbackLen = 0;
  const push = data => { const off = mainLen; main.push(data, Buffer.alloc(align(data.length) - data.length)); mainLen += align(data.length); return off; };
  accessors.forEach((acc, i) => {
    const view = json.bufferViews[acc.bufferView];
    const size = COMPONENT[acc.componentType] * COUNT[acc.type];
    const start = (view.byteOffset ?? 0) + (acc.byteOffset ?? 0);
    const stride = view.byteStride ?? size;
    const length = stride * (acc.count - 1) + size;
    const data = Buffer.from(bin.subarray(start, start + length));
    const out = { buffer: 0, byteLength: length, ...(view.byteStride ? { byteStride: view.byteStride } : {}), ...(view.target ? { target: view.target } : {}) };
    let mode = null;
    if (indexAccessors.has(i) && (size === 2 || size === 4) && acc.count % 3 === 0) mode = 'TRIANGLES';
    else if (!indexAccessors.has(i) && stride === size && size % 4 === 0 && size <= 256) mode = 'ATTRIBUTES';
    if (mode) {
      const encoded = Buffer.from(MeshoptEncoder.encodeGltfBuffer(new Uint8Array(data), acc.count, size, mode));
      if (encoded.length < data.length) {
        const byteOffset = push(encoded);
        out.buffer = 1;
        out.byteOffset = fallbackLen;
        fallbackLen += align(length);
        out.extensions = { EXT_meshopt_compression: { buffer: 0, byteOffset, byteLength: encoded.length, byteStride: size, count: acc.count, mode } };
        if (mode === 'ATTRIBUTES' && !out.byteStride && out.target === 34962) out.byteStride = size;
        views.push(out);
        acc.bufferView = views.length - 1;
        delete acc.byteOffset;
        return;
      }
    }
    out.byteOffset = push(data);
    views.push(out);
    acc.bufferView = views.length - 1;
    delete acc.byteOffset;
  });
  json.accessors = accessors;
  json.bufferViews = views;
  json.buffers = [{ byteLength: mainLen }, { byteLength: fallbackLen, extensions: { EXT_meshopt_compression: { fallback: true } } }];
  json.extensionsUsed = [...new Set([...(json.extensionsUsed ?? []), 'EXT_meshopt_compression'])];
  json.extensionsRequired = [...new Set([...(json.extensionsRequired ?? []), 'EXT_meshopt_compression'])];
  return write(json, Buffer.concat(main));
}

if (process.argv[1] && import.meta.url.endsWith(process.argv[1].split('/').pop())) {
  await MeshoptEncoder.ready;
  let before = 0; let after = 0;
  for (const file of process.argv.slice(2)) {
    const src = readFileSync(file);
    const out = compress(src);
    writeFileSync(file, out);
    before += src.length; after += out.length;
    console.log(`${file}  ${(src.length / 1024).toFixed(0)} → ${(out.length / 1024).toFixed(0)} Kio`);
  }
  console.log(`total ${(before / 1048576).toFixed(1)} → ${(after / 1048576).toFixed(1)} Mio`);
}
