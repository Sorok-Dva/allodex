import * as THREE from 'three';

/**
 * Herbe et eau du sol des cartes (`terrainDump`), communes aux cinématiques moteur et aux fatalités.
 * Données : `tools/allods_terrain_extras.py` (nœuds `grass` et `water` du `.glb` du sol).
 *
 * **Herbe** — shader `grass` du client (`Material/grass-dx11.bin`, désassemblé) : touffes cuites
 * (sommets en monde), couleur = texture × lumière du sommet × 2 × ½, test d'alpha
 * `texture.a × fondu < 0,02`, balancement horizontal du haut des feuilles = produit complexe d'un
 * coefficient par sommet (nul au pied) et d'un vecteur de vent global (`offsets`). Ici : une
 * touffe par instance, `numLeaves` feuilles réparties autour du pied, chaque feuille allant de
 * `bottom` à `top` (hauteur, décalage vers l'extérieur, largeur), le tout × l'échelle ; éclairage
 * du sol à son pied (même formule que le terrain, lumière cuite comprise).
 * Non établi par les données (constantes du moteur) : l'amplitude et la fréquence du vent, la
 * distance de fondu.
 *
 * **Eau** — shader `StaticWater` du client (`Material/StaticWater-dx11.bin`) porté tel quel : relief
 * = somme de trois lectures défilantes de la texture de relief (`pos/4 + t·(0, 3)`,
 * `pos/4 + t·(−½, −1)`, `(pos/4 + t·(1, −2))/4`), couleur = dégradé `WaterGradientStart → End` de la
 * zone selon la profondeur (`sat(2B − 1)`, B du bloc d'eau), reflet (image miroir, × `waterReflection
 * Contribution`) mêlé par l'alpha du dégradé, reflet spéculaire `|V·N| × SpecularWaterColor ×
 * waterSpecularCoeff`, puis Fresnel (texture lue en `(½, |V·N|)`) entre la réfraction (l'image
 * derrière, × couleur du Fresnel) et la surface ; alpha = `min(sat(8B − 4) / (sat(N_fond·V) + 0,01),
 * 1) × waterAlpha`, couleur prémultipliée. Non établi : l'unité du temps (`t = s × waterSpeedMultiply
 * / 1000`, supposée) et les textures de repli (types d'eau sans Fresnel ou sans relief).
 */

export type GrassKind = { uv: number[]; leaves: number; top: number[]; bottom: number[]; scale: number[] };
export type WaterMeta = {
  name?: string | null; alpha: number; reflection: number; specular: number; speed: number; addColor?: number;
  textures: Record<string, string | null>;
};

export type ExtrasLight = {
  /** Couleurs de lumière du jeu (1 = 0x80) et direction du soleil, repère du jeu. */
  ambient: THREE.Color; sun: THREE.Color; point: THREE.Color; sunDir: THREE.Vector3; ambientFactor: number;
  /** Atlas de lumière cuite du sol (`_LIGHTUV`), ou `null`. */
  lightmap: THREE.Texture | null;
  /** ARGB de la zone : `WaterGradientStart`, `WaterGradientEnd`, `SpecularWaterColor`. */
  waterGradientStart?: number; waterGradientEnd?: number; waterSpecular?: number;
};

export type TerrainExtras = {
  /** À appeler avant chaque rendu : temps de la scène (s), caméra, et le rendu du reflet. */
  update(renderer: THREE.WebGLRenderer, scene: THREE.Scene, camera: THREE.PerspectiveCamera, time: number): void;
  readonly animated: boolean;
  dispose(): void;
};

/** Distance (m) où l'herbe commence à se dissoudre, et où elle a disparu (choix du lecteur). */
export const GRASS_FADE_NEAR = 45;
export const GRASS_FADE_FAR = 70;
/** Vent : amplitude (m au sommet d'une feuille d'échelle 1) et pulsations (rad/s), choix du lecteur. */
const WIND_AMPLITUDE = 0.07;
const WIND_PULSE: [number, number] = [1.3, 0.9];
/** Temps du relief de l'eau : `t × waterSpeedMultiply / 1000` (unité supposée). */
const WATER_TIME_SCALE = 1 / 1000;
const REFLECTION_SCALE = 0.5;

function argb4(value: number | undefined): THREE.Vector4 {
  const v = value ?? 0;
  return new THREE.Vector4(((v >>> 16) & 255) / 255, ((v >>> 8) & 255) / 255, (v & 255) / 255, ((v >>> 24) & 255) / 255);
}

async function loadTexture(uri: string | null | undefined, base: URL, repeat: boolean): Promise<THREE.Texture | null> {
  if (!uri) return null;
  try {
    const texture = await new THREE.TextureLoader().loadAsync(new URL(uri, base).href);
    texture.flipY = false;
    texture.colorSpace = THREE.NoColorSpace;
    texture.wrapS = texture.wrapT = repeat ? THREE.RepeatWrapping : THREE.ClampToEdgeWrapping;
    texture.needsUpdate = true;
    return texture;
  } catch {
    return null;
  }
}

const LIGHTING_GLSL = `
  uniform vec3 ambient; uniform vec3 sunColor; uniform vec3 sunDir; uniform vec3 pointColor;
  uniform float ambientFactor; uniform sampler2D lightmap; uniform int hasLightmap;
  vec3 groundLight(vec3 n, vec2 lm) {
    vec3 baked = vec3(1.0, 1.0, 0.0);
    if (hasLightmap == 1 && lm.x >= 0.0) baked = texture(lightmap, lm).rgb;
    return ambient * (ambientFactor + (1.0 - ambientFactor) * baked.r) + sunColor * max(dot(normalize(n), sunDir), 0.0) * baked.g
         + pointColor * baked.b;
  }`;

function grassMaterial(atlas: THREE.Texture, kinds: THREE.DataTexture, light: ExtrasLight): THREE.ShaderMaterial {
  const material = new THREE.ShaderMaterial({
    glslVersion: THREE.GLSL3,
    fog: true,
    side: THREE.DoubleSide,
    uniforms: THREE.UniformsUtils.merge([THREE.UniformsLib.fog, {
      atlas: { value: null }, kinds: { value: null }, time: { value: 0 }, eyeLocal: { value: new THREE.Vector3() },
      fadeNear: { value: GRASS_FADE_NEAR }, fadeFar: { value: GRASS_FADE_FAR },
      windAmplitude: { value: WIND_AMPLITUDE }, windPulse: { value: new THREE.Vector2(...WIND_PULSE) },
      ambient: { value: light.ambient }, sunColor: { value: light.sun }, sunDir: { value: light.sunDir.clone().normalize() },
      pointColor: { value: light.point }, ambientFactor: { value: light.ambientFactor },
      lightmap: { value: null }, hasLightmap: { value: light.lightmap ? 1 : 0 },
    }]),
    vertexShader: `
      precision highp sampler2D;
      in float leaf; in vec2 corner; in vec3 root; in vec4 groundNormal; in vec4 grassBytes; in vec2 lightUV;
      uniform sampler2D kinds; uniform float time; uniform vec3 eyeLocal; uniform float fadeNear; uniform float fadeFar;
      uniform float windAmplitude; uniform vec2 windPulse;
      out vec2 vUv; out vec2 vLM; out vec3 vN; out float vFade;
      #include <fog_pars_vertex>
      void main() {
        // Octets : sorte, lacet et phase en 256ᵉ de tour, échelle en 64ᵉ.
        vec4 grass = vec4(grassBytes.x, grassBytes.y * 6.2831853 / 256.0, grassBytes.z / 64.0, grassBytes.w * 6.2831853 / 256.0);
        int k = int(grass.x + 0.5);
        vec4 rect = texelFetch(kinds, ivec2(0, k), 0);
        vec4 top = texelFetch(kinds, ivec2(1, k), 0);
        vec4 bottom = texelFetch(kinds, ivec2(2, k), 0);
        vFade = clamp((fadeFar - distance(eyeLocal, root)) / (fadeFar - fadeNear), 0.0, 1.0);
        if (leaf >= top.w - 0.5 || vFade <= 0.0) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }
        float ang = grass.y + leaf * 6.2831853 / top.w;
        vec2 d = vec2(cos(ang), sin(ang));
        vec2 t = vec2(-d.y, d.x);
        vec3 hw = mix(bottom.xyz, top.xyz, corner.y);
        float s = grass.z;
        vec3 p = vec3(d * hw.y + t * (corner.x - 0.5) * hw.z, hw.x) * s;
        // Vent (shader du client) : coefficient complexe du sommet × vecteur de vent, nul au pied.
        vec2 c = corner.y * vec2(cos(grass.w), sin(grass.w));
        vec2 w = windAmplitude * vec2(sin(time * windPulse.x), sin(time * windPulse.y + 1.3));
        p.xy += vec2(c.x * w.x - c.y * w.y, c.x * w.y + c.y * w.x) * s;
        vec4 mvPosition = modelViewMatrix * vec4(root + p, 1.0);
        gl_Position = projectionMatrix * mvPosition;
        vUv = mix(rect.xy, rect.zw, vec2(corner.x, 1.0 - corner.y));
        vLM = lightUV.x > 0.99995 ? vec2(-1.0) : lightUV;
        vN = groundNormal.xyz * 2.0 - 1.0;
        #include <fog_vertex>
      }`,
    fragmentShader: `
      layout(location = 0) out vec4 grassColor;
      #define gl_FragColor grassColor
      uniform sampler2D atlas;
      ${LIGHTING_GLSL}
      in vec2 vUv; in vec2 vLM; in vec3 vN; in float vFade;
      #include <fog_pars_fragment>
      void main() {
        vec4 tex = texture(atlas, vUv);
        // Test d'alpha du client : texture.a × fondu × 0,2 − 0,004 < 0.
        if (tex.a * vFade * 0.2 - 0.004 < 0.0) discard;
        gl_FragColor = vec4(tex.rgb * groundLight(vN, vLM), 1.0);
        #include <fog_fragment>
      }`,
  });
  // Textures posées après la fusion des uniformes (`UniformsUtils.merge` les clonerait).
  material.uniforms.atlas.value = atlas;
  material.uniforms.kinds.value = kinds;
  material.uniforms.lightmap.value = light.lightmap;
  return material;
}

/** Touffe de référence : quatre feuilles de quatre sommets (`leaf`, `corner` = travers, hauteur). */
function tuftGeometry(): { leaf: Float32Array; corner: Float32Array; index: number[] } {
  const leaf: number[] = [];
  const corner: number[] = [];
  const index: number[] = [];
  for (let l = 0; l < 4; l++) {
    const b = l * 4;
    for (const [u, v] of [[0, 0], [1, 0], [0, 1], [1, 1]]) { leaf.push(l); corner.push(u, v); }
    index.push(b, b + 1, b + 2, b + 2, b + 1, b + 3);
  }
  return { leaf: new Float32Array(leaf), corner: new Float32Array(corner), index };
}

function waterMaterial(meta: WaterMeta, tex: { bump: THREE.Texture | null; fresnel: THREE.Texture | null }, light: ExtrasLight,
  refl: THREE.Texture, refr: THREE.Texture): THREE.ShaderMaterial {
  const add = argb4(meta.addColor);
  const material = new THREE.ShaderMaterial({
    glslVersion: THREE.GLSL3,
    fog: true,
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    blending: THREE.CustomBlending,
    blendSrc: THREE.OneFactor,
    blendDst: THREE.OneMinusSrcAlphaFactor,
    uniforms: THREE.UniformsUtils.merge([THREE.UniformsLib.fog, {
      bump: { value: null }, fresnel: { value: null }, refl: { value: null }, refr: { value: null },
      reflMatrix: { value: new THREE.Matrix4() }, hasRefl: { value: 0 },
      eyeLocal: { value: new THREE.Vector3() }, time: { value: 0 },
      waterColor1: { value: argb4(light.waterGradientStart) }, waterColor2: { value: argb4(light.waterGradientEnd) },
      specularColor: { value: argb4(light.waterSpecular) }, addColor: { value: add },
      waterParams: { value: new THREE.Vector4(meta.reflection ?? 1, meta.alpha ?? 1, 0, meta.specular ?? 0) },
      viewport: { value: new THREE.Vector2(1, 1) },
    }]),
    vertexShader: `
      in vec4 _water;
      uniform mat4 reflMatrix; uniform vec3 eyeLocal; uniform float time;
      out vec3 vView; out vec4 vRefl; out vec4 vTexel; out vec2 vUv1; out vec2 vUv2; out vec2 vUv3;
      out vec4 vDx; out vec4 vDy;
      #include <fog_pars_vertex>
      void main() {
        vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
        gl_Position = projectionMatrix * mvPosition;
        vView = eyeLocal - position;
        vRefl = reflMatrix * modelMatrix * vec4(position, 1.0);
        vTexel = _water;
        vec2 p = position.xy * 0.25;
        vUv1 = p + time * vec2(0.0, 3.0);
        vUv2 = p + time * vec2(-0.5, -1.0);
        vUv3 = (p + time * vec2(1.0, -2.0)) * 0.25;
        // Dérivées de l'écran par mètre en x et en y (lignes de la matrice du client) : distorsion.
        mat4 mvp = projectionMatrix * modelViewMatrix;
        vDx = mvp[0]; vDy = mvp[1];
        #include <fog_vertex>
      }`,
    fragmentShader: `
      layout(location = 0) out vec4 waterColor;
      #define gl_FragColor waterColor
      uniform sampler2D bump; uniform sampler2D fresnel; uniform sampler2D refl; uniform sampler2D refr;
      uniform int hasRefl; uniform vec4 waterColor1; uniform vec4 waterColor2; uniform vec4 specularColor;
      uniform vec4 addColor; uniform vec4 waterParams; uniform vec2 viewport;
      in vec3 vView; in vec4 vRefl; in vec4 vTexel; in vec2 vUv1; in vec2 vUv2; in vec2 vUv3; in vec4 vDx; in vec4 vDy;
      #include <fog_pars_fragment>
      void main() {
        vec3 n = (texture(bump, vUv1).xyz + texture(bump, vUv2).xyz + texture(bump, vUv3).xyz) * vec3(0.66, 0.66, 0.33)
               - vec3(1.0, 1.0, 0.0);
        vec2 dist = n.x * vDx.xy - n.y * vDy.xy;
        vec2 screen = gl_FragCoord.xy / viewport;
        vec3 refraction = texture(refr, screen - 0.1 * dist).rgb;
        vec3 reflection = hasRefl == 1 ? texture(refl, vRefl.xy / vRefl.w + dist).rgb : vec3(0.0);
        float depth = vTexel.b;
        vec4 grad = mix(waterColor1, waterColor2, clamp(2.0 * depth - 1.0, 0.0, 1.0));
        grad.rgb *= n.z;
        vec3 surface = mix(grad.rgb, reflection * waterParams.x, grad.a) + addColor.rgb * addColor.a;
        vec3 nn = normalize(n);
        vec3 v = normalize(vView);
        float vn = abs(dot(v, nn));
        surface += vn * specularColor.rgb * waterParams.w;
        vec4 fr = texture(fresnel, vec2(0.5, vn));
        vec3 color = mix(refraction * fr.rgb, surface, fr.a);
        float alpha = min(clamp(8.0 * depth - 4.0, 0.0, 1.0) / (clamp(dot(vec3(2.0 * vTexel.rg - 1.0, 1.0), v), 0.0, 1.0) + 0.01), 1.0);
        gl_FragColor = vec4(color, 1.0);
        #include <fog_fragment>
        gl_FragColor = vec4(gl_FragColor.rgb * alpha, alpha * waterParams.y);
      }`,
  });
  material.uniforms.bump.value = tex.bump;
  material.uniforms.fresnel.value = tex.fresnel;
  material.uniforms.refl.value = refl;
  material.uniforms.refr.value = refr;
  return material;
}

/**
 * Remplace les nœuds `grass` (points) et `water` d'un sol chargé par l'herbe instanciée et l'eau.
 * `holder` : groupe du repère du jeu (miroir compris) où le sol est posé.
 */
export async function buildTerrainExtras(root: THREE.Object3D, base: URL, light: ExtrasLight): Promise<TerrainExtras | null> {
  const disposables: { dispose(): void }[] = [];
  const grassCells: { mesh: THREE.Mesh; center: THREE.Vector3; radius: number }[] = [];
  const grassMaterials: THREE.ShaderMaterial[] = [];
  const bodies: { mesh: THREE.Mesh; material: THREE.ShaderMaterial; speed: number; height: number; box: THREE.Box3 }[] = [];

  const grassNode = root.getObjectByName('grass');
  const grassMeta = grassNode?.userData?.grass as { atlas: string | null; kinds: GrassKind[] } | undefined;
  if (grassNode && grassMeta?.kinds?.length) {
    const atlas = await loadTexture(grassMeta.atlas, base, false);
    if (atlas) {
      atlas.minFilter = THREE.LinearMipmapLinearFilter;
      atlas.generateMipmaps = true;
      disposables.push(atlas);
      const kinds = grassMeta.kinds;
      const table = new Float32Array(kinds.length * 3 * 4);
      kinds.forEach((k, i) => {
        table.set([k.uv[0], k.uv[1], k.uv[2], k.uv[3]], i * 12);
        table.set([k.top[0], k.top[1], k.top[2], k.leaves], i * 12 + 4);
        table.set([k.bottom[0], k.bottom[1], k.bottom[2], 0], i * 12 + 8);
      });
      const kindTex = new THREE.DataTexture(table, 3, kinds.length, THREE.RGBAFormat, THREE.FloatType);
      kindTex.needsUpdate = true;
      disposables.push(kindTex);
      const material = grassMaterial(atlas, kindTex, light);
      disposables.push(material);
      grassMaterials.push(material);
      const tuft = tuftGeometry();
      const cells: THREE.Object3D[] = [];
      grassNode.traverse(node => { if ((node as THREE.Points).isPoints) cells.push(node); });
      for (const node of cells) {
        const points = node as THREE.Points;
        const src = points.geometry;
        const count = src.getAttribute('position')?.count ?? 0;
        if (!count) continue;
        const geometry = new THREE.InstancedBufferGeometry();
        geometry.setAttribute('leaf', new THREE.BufferAttribute(tuft.leaf, 1));
        geometry.setAttribute('corner', new THREE.BufferAttribute(tuft.corner, 2));
        // `position` fictif (le shader place les sommets) : requis par three.js pour compter les sommets.
        geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(16 * 3), 3));
        geometry.setIndex(tuft.index);
        const inst = (name: string, size: number, normalized: boolean) => {
          const a = src.getAttribute(name) as THREE.BufferAttribute;
          return new THREE.InstancedBufferAttribute(a.array, size, normalized);
        };
        if (!src.getAttribute('_gnormal') || !src.getAttribute('_grass') || !src.getAttribute('_lightuv')) continue;
        geometry.setAttribute('root', inst('position', 3, false));
        geometry.setAttribute('groundNormal', inst('_gnormal', 4, true));
        geometry.setAttribute('grassBytes', inst('_grass', 4, false));
        geometry.setAttribute('lightUV', inst('_lightuv', 2, true));
        geometry.instanceCount = count;
        src.computeBoundingSphere();
        const sphere = src.boundingSphere!.clone();
        sphere.radius += 3;
        geometry.boundingSphere = sphere;
        const mesh = new THREE.Mesh(geometry, material);
        mesh.name = 'grass_cell';
        mesh.userData.noCollide = true;
        // Pas de lancer de rayon sur les touffes (géométrie placée par le shader).
        mesh.raycast = () => {};
        points.parent?.add(mesh);
        points.removeFromParent();
        src.dispose();
        disposables.push(geometry);
        grassCells.push({ mesh, center: sphere.center.clone(), radius: sphere.radius });
      }
    }
  }

  const reflTarget = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType });
  const refrTexture = new THREE.FramebufferTexture(1, 1);
  const waterNode = root.getObjectByName('water');
  if (waterNode) {
    const meshes: THREE.Mesh[] = [];
    waterNode.traverse(node => { if ((node as THREE.Mesh).isMesh && node.userData?.water) meshes.push(node as THREE.Mesh); });
    const cache = new Map<string, Promise<THREE.Texture | null>>();
    const get = (uri: string | null | undefined) => {
      if (!uri) return Promise.resolve(null);
      if (!cache.has(uri)) cache.set(uri, loadTexture(uri, base, true));
      return cache.get(uri)!;
    };
    for (const mesh of meshes) {
      const meta = mesh.userData.water as WaterMeta;
      const t = meta.textures ?? {};
      const [bump, fresnel] = await Promise.all([
        get(t.bump ?? t.defaultBump),
        get(t.fresnelUp ?? t.fresnelDown ?? t.fresnelUpWaterWaves ?? t.defaultFresnel),
      ]);
      if (fresnel) fresnel.wrapS = fresnel.wrapT = THREE.ClampToEdgeWrapping;
      const material = waterMaterial(meta, { bump, fresnel }, light, reflTarget.texture, refrTexture);
      disposables.push(material);
      (mesh.material as THREE.Material).dispose?.();
      mesh.material = material;
      mesh.renderOrder = 5;
      mesh.userData.noCollide = true;
      mesh.geometry.computeBoundingBox();
      const box = mesh.geometry.boundingBox!.clone();
      bodies.push({ mesh, material, speed: meta.speed || 16, height: box.max.z, box });
      mesh.onBeforeRender = (renderer) => {
        // Réfraction : l'image déjà dessinée (opaques), copiée avant la première eau de l'image.
        if (frameCopied) return;
        frameCopied = true;
        renderer.getDrawingBufferSize(drawing);
        if (refrTexture.image.width !== drawing.x || refrTexture.image.height !== drawing.y) {
          refrTexture.image.width = drawing.x;
          refrTexture.image.height = drawing.y;
          refrTexture.dispose();
        }
        renderer.copyFramebufferToTexture(refrTexture);
      };
    }
    for (const texture of cache.values()) void texture.then(t => t && disposables.push(t));
  }
  let frameCopied = false;
  const drawing = new THREE.Vector2();
  disposables.push(reflTarget, refrTexture);

  if (!grassCells.length && !bodies.length) {
    for (const d of disposables) d.dispose();
    return null;
  }

  // Reflet : caméra miroir sous le plan de l'eau la plus proche, plan de coupe oblique (Lengyel).
  const mirror = new THREE.PerspectiveCamera();
  const frustum = new THREE.Frustum();
  const projScreen = new THREE.Matrix4();
  const eye = new THREE.Vector3();
  const reflMatrix = new THREE.Matrix4();
  const worldBox = new THREE.Box3();
  const renderReflection = (renderer: THREE.WebGLRenderer, scene: THREE.Scene, camera: THREE.PerspectiveCamera, height: number) => {
    const size = renderer.getDrawingBufferSize(drawing);
    const w = Math.max(1, Math.round(size.x * REFLECTION_SCALE));
    const h = Math.max(1, Math.round(size.y * REFLECTION_SCALE));
    if (reflTarget.width !== w || reflTarget.height !== h) reflTarget.setSize(w, h);
    camera.updateMatrixWorld();
    const pos = new THREE.Vector3().setFromMatrixPosition(camera.matrixWorld);
    const dir = new THREE.Vector3(0, 0, -1).transformDirection(camera.matrixWorld);
    const up = new THREE.Vector3(0, 1, 0).transformDirection(camera.matrixWorld);
    mirror.copy(camera);
    mirror.position.set(pos.x, pos.y, 2 * height - pos.z);
    mirror.up.set(up.x, up.y, -up.z);
    mirror.lookAt(pos.x + dir.x, pos.y + dir.y, 2 * height - (pos.z + dir.z));
    mirror.updateMatrixWorld();
    mirror.projectionMatrix.copy(camera.projectionMatrix);
    reflMatrix.set(0.5, 0, 0, 0.5, 0, 0.5, 0, 0.5, 0, 0, 0.5, 0.5, 0, 0, 0, 1)
      .multiply(mirror.projectionMatrix).multiply(mirror.matrixWorldInverse);
    const plane = new THREE.Plane(new THREE.Vector3(0, 0, 1), -height).applyMatrix4(mirror.matrixWorldInverse);
    const clip = new THREE.Vector4(plane.normal.x, plane.normal.y, plane.normal.z, plane.constant);
    const e = mirror.projectionMatrix.elements;
    const q = new THREE.Vector4((Math.sign(clip.x) + e[8]) / e[0], (Math.sign(clip.y) + e[9]) / e[5], -1, (1 + e[10]) / e[14]);
    clip.multiplyScalar(2 / clip.dot(q));
    e[2] = clip.x; e[6] = clip.y; e[10] = clip.z + 1; e[14] = clip.w;
    mirror.projectionMatrixInverse.copy(mirror.projectionMatrix).invert();
    for (const b of bodies) b.mesh.visible = false;
    for (const c of grassCells) c.mesh.visible = false;
    const previous = renderer.getRenderTarget();
    renderer.setRenderTarget(reflTarget);
    renderer.clear();
    renderer.render(scene, mirror);
    renderer.setRenderTarget(previous);
    for (const b of bodies) b.mesh.visible = true;
  };

  return {
    animated: true,
    update(renderer, scene, camera, time) {
      frameCopied = false;
      camera.updateMatrixWorld();
      eye.setFromMatrixPosition(camera.matrixWorld);
      if (grassCells.length) {
        // Les carreaux d'herbe partagent le repère du jeu : un seul œil local pour le matériau.
        const local = grassCells[0].mesh.worldToLocal(eye.clone());
        for (const material of grassMaterials) {
          material.uniforms.time.value = time;
          material.uniforms.eyeLocal.value.copy(local);
        }
        for (const cell of grassCells) cell.mesh.visible = local.distanceTo(cell.center) < GRASS_FADE_FAR + cell.radius;
      }
      if (!bodies.length) return;
      projScreen.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
      frustum.setFromProjectionMatrix(projScreen);
      const far = (scene.fog as THREE.Fog | null)?.far ?? camera.far;
      let nearest: { height: number; d: number } | null = null;
      for (const b of bodies) {
        worldBox.copy(b.box).applyMatrix4(b.mesh.matrixWorld);
        const d = worldBox.distanceToPoint(eye);
        const seen = frustum.intersectsBox(worldBox) && d < far;
        b.mesh.visible = seen;
        const local = b.mesh.worldToLocal(eye.clone());
        b.material.uniforms.eyeLocal.value.copy(local);
        b.material.uniforms.time.value = time * b.speed * WATER_TIME_SCALE;
        renderer.getDrawingBufferSize(drawing);
        b.material.uniforms.viewport.value.copy(drawing);
        if (seen && (!nearest || d < nearest.d)) nearest = { height: worldBox.max.z, d };
      }
      if (nearest && eye.z > nearest.height) {
        const grassShown = grassCells.map(c => c.mesh.visible);
        renderReflection(renderer, scene, camera, nearest.height);
        grassCells.forEach((c, i) => { c.mesh.visible = grassShown[i]; });
        for (const b of bodies) {
          b.material.uniforms.reflMatrix.value.copy(reflMatrix);
          b.material.uniforms.hasRefl.value = 1;
        }
      } else {
        for (const b of bodies) b.material.uniforms.hasRefl.value = 0;
      }
    },
    dispose() { for (const d of disposables) d.dispose(); },
  };
}
