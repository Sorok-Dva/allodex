import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import type { SceneMeta } from '@/lib/assets';
import { createV7Effects, type CannonTextures } from './menuSceneV7';
import s from './MenuScene.module.css';

/**
 * Le moteur du jeu (Direct3D 9) compose sans gestion des espaces colorimétriques : les
 * textures, les couleurs de sommet et les fondus sont tous calculés sur les octets tels
 * quels. On désactive donc la conversion automatique de three.js, sans quoi les mélanges
 * additifs et les alphas s'écarteraient de ce que montre le jeu (et des planches de
 * contrôle de `tools/extract_menu_scene.py`, rendues de la même façon).
 */
THREE.ColorManagement.enabled = false;

/** Un glTF chargé, réduit à ce dont la scène a besoin. */
export type LoadedScene = { scene: THREE.Object3D; animations: THREE.AnimationClip[] };
/** Ce que `MenuScene` attend d'un chargeur glTF — `GLTFLoader` en production. */
export type SceneLoader = {
  load(
    url: string,
    onLoad: (gltf: LoadedScene) => void,
    onProgress?: (event: ProgressEvent) => void,
    onError?: (error: unknown) => void,
  ): void;
};

export type MenuSceneProps = {
  /** URL du `.glb` et de son `scene.json` (`archiveFile(version, entry.scene.glb)`). */
  glbUrl: string;
  metaUrl: string;
  className?: string;
  /** Appelé une fois la première image rendue : le fond de repli peut s'effacer. */
  onReady?: () => void;
  /** Seam de test : remplace `GLTFLoader` (aucune requête réseau dans les tests). */
  createLoader?: () => SceneLoader;
  /** Seam de test : remplace `WebGLRenderer` (jsdom n'a pas de contexte WebGL). */
  createRenderer?: (canvas: HTMLCanvasElement) => THREE.WebGLRenderer;
};

/** Rapport `far / near` des plans de coupe : le plan proche suit l'étendue de la scène. */
const NEAR_RATIO = 10_000;

/**
 * Matériau de rendu d'une primitive du `.glb` : le jeu ne fait pas d'éclairage, tout est
 * peint dans la texture et dans les couleurs de sommet (déjà multipliées par deux par
 * l'exportateur — surtout ne pas le refaire ici). `extras: {blend: "add"}`, que
 * `GLTFLoader` dépose dans `userData`, marque les matériaux additifs du jeu
 * (`BLEND_EFFECT_ADD` : halos, propulseurs, brume lumineuse).
 *
 * Ces décors sont des **calques peints** : le moteur du jeu les empile de l'arrière vers
 * l'avant sans tampon de profondeur. On rend donc tout en mélange alpha, sans test ni
 * écriture de profondeur, et l'ordre vient de `sortByDepth`. Sans cela, les quelques
 * primitives exportées en `alphaMode: OPAQUE` (des halos, en réalité) masqueraient les
 * calques de nuages qui doivent passer par-dessus — la 4.0 se réduisait à un aplat.
 */
export function toMenuMaterial(source: THREE.Material): THREE.MeshBasicMaterial {
  const src = source as THREE.MeshBasicMaterial;
  const additive = (source.userData as { blend?: string } | undefined)?.blend === 'add';
  const material = new THREE.MeshBasicMaterial({
    name: source.name,
    map: src.map ?? null,
    color: 0xffffff,
    opacity: source.opacity,
    // `alphaMode: MASK` arrive de `GLTFLoader` en `alphaTest` : on le conserve tel quel.
    alphaTest: source.alphaTest,
    transparent: true,
    side: source.side,
    vertexColors: true,
    toneMapped: false,
    fog: false,
  });
  material.depthWrite = false;
  material.depthTest = false;
  if (additive) material.blending = THREE.AdditiveBlending;
  // Les textures sont des octets du jeu, pas des couleurs sRGB à linéariser.
  if (material.map) material.map.colorSpace = THREE.NoColorSpace;
  return material;
}

/**
 * Classe les primitives de la plus lointaine à la plus proche (peintre).
 *
 * `GLTFLoader` fabrique un maillage par primitive et toutes celles d'un objet partagent la
 * même origine ; or three.js trie les faces translucides sur la position de l'objet, pas
 * sur sa géométrie. Toutes les primitives d'un décor exporté d'un bloc arrivent donc à
 * égalité et le tri retombe sur l'ordre du fichier : la sphère de brume finirait
 * par-dessus le paysage. La caméra de ces scènes ne bougeant jamais, on calcule une bonne
 * fois la profondeur moyenne de chaque primitive — le même critère que la planche de
 * contrôle de l'outil d'export — et on la pose en `renderOrder` (le plus lointain d'abord).
 */
export function sortByDepth(root: THREE.Object3D, camera: THREE.Camera): void {
  root.updateMatrixWorld(true);
  const forward = camera.getWorldDirection(new THREE.Vector3());
  const eye = camera.getWorldPosition(new THREE.Vector3());
  const point = new THREE.Vector3();
  root.traverse(object => {
    const mesh = object as THREE.Mesh;
    if (!mesh.isMesh || Array.isArray(mesh.material)) return;
    const index = mesh.geometry.getIndex();
    const position = mesh.geometry.getAttribute('position');
    if (!index || !position) return;
    let sum = 0;
    for (let i = 0; i < index.count; i += 1) {
      point.fromBufferAttribute(position, index.getX(i)).applyMatrix4(mesh.matrixWorld);
      sum += point.sub(eye).dot(forward);
    }
    mesh.renderOrder = -sum / Math.max(index.count, 1);
  });
}

/**
 * Scène de menu animée (4.0 → 8.0) en plein écran, sous l'interface des Chroniques.
 *
 * Le `.glb` et son `scene.json` sont produits par `tools/extract_menu_scene.py`. La
 * caméra vient du `scene.json` (elle n'existe pas dans les données du jeu) : le champ de
 * vision est **vertical** et reste constant, seul le rapport d'image suit la fenêtre —
 * l'équivalent d'un `object-fit: cover` pour une scène 3D. Les scènes ont l'axe Z vers le
 * haut, d'où le `camera.up` lu dans le méta.
 *
 * Mouvement réduit (`prefers-reduced-motion`) : une seule image, à t = 0, et le mixeur
 * reste à l'arrêt. Onglet caché : la boucle est suspendue.
 */
export function MenuScene({ glbUrl, metaUrl, className, onReady, createLoader, createRenderer }: MenuSceneProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // La prop peut changer sans que la scène soit à recharger : on la lit par référence.
  const readyRef = useRef(onReady);
  readyRef.current = onReady;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const scene = new THREE.Scene();
    const textures = new Set<THREE.Texture>();
    // `THREE.Clock` est déprécié depuis three 0.186 : on mesure le temps écoulé à la main.
    let previous = 0;
    const delta = () => {
      const now = performance.now();
      const seconds = previous ? (now - previous) / 1000 : 0;
      previous = now;
      return Math.min(seconds, 0.25); // un onglet revenu au premier plan ne saute pas
    };
    let alive = true;
    let frame = 0;
    let firstFrame = true;
    let renderer: THREE.WebGLRenderer | null = null;
    let camera: THREE.PerspectiveCamera | THREE.OrthographicCamera | null = null;
    let mixer: THREE.AnimationMixer | null = null;
    let v7Effects: ReturnType<typeof createV7Effects> | null = null;
    let elapsed = 0;
    let observer: ResizeObserver | null = null;
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true;

    const size = () => {
      const host = canvas.parentElement ?? canvas;
      return {
        width: Math.max(1, host.clientWidth || window.innerWidth || 1),
        height: Math.max(1, host.clientHeight || window.innerHeight || 1),
      };
    };

    const draw = () => {
      if (!renderer || !camera) return;
      renderer.render(scene, camera);
      if (firstFrame) {
        firstFrame = false;
        readyRef.current?.();
      }
    };

    const resize = () => {
      if (!renderer || !camera) return;
      const { width, height } = size();
      if (camera instanceof THREE.PerspectiveCamera) camera.aspect = width / height;
      else {
        const halfHeight = (camera.top - camera.bottom) / 2;
        camera.left = -halfHeight * width / height;
        camera.right = halfHeight * width / height;
      }
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
      draw();
    };

    const tick = () => {
      frame = requestAnimationFrame(tick);
      const step = delta();
      elapsed += step;
      mixer?.update(step);
      v7Effects?.update(elapsed);
      draw();
    };
    const start = () => {
      if (frame || reduced) return;
      previous = 0; // absorbe le temps passé en pause
      frame = requestAnimationFrame(tick);
    };
    const stop = () => {
      if (!frame) return;
      cancelAnimationFrame(frame);
      frame = 0;
    };
    const onVisibility = () => (document.hidden ? stop() : start());
    const onResize = () => resize();

    const build = (gltf: LoadedScene, meta: SceneMeta) => {
      const root = gltf.scene;
      // Les décors sont vus en incidence rasante (sphères de brume, calques de nuages) :
      // sans filtrage anisotrope ils se réduisent à un aplat.
      const anisotropy = renderer?.capabilities?.getMaxAnisotropy() ?? 1;
      root.traverse(object => {
        const mesh = object as THREE.Mesh;
        if (!mesh.isMesh) return;
        // Les maillages skinnés bougent au-delà de leur boîte de repos : les exclure du
        // tri par volume évite qu'ils disparaissent en bord d'écran.
        mesh.frustumCulled = false;
        const source = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
        const converted = source.map(toMenuMaterial);
        for (const material of converted) {
          if (!material.map) continue;
          material.map.anisotropy = anisotropy;
          if (meta.version === '7.0') {
            material.map.repeat.y = -1;
            material.map.offset.y = 1;
          }
          textures.add(material.map);
        }
        mesh.material = Array.isArray(mesh.material) ? converted : converted[0];
      });
      scene.add(root);

      const { position, target, fov } = meta.camera;
      const halfHeight = meta.camera.orthographicHeight ? meta.camera.orthographicHeight / 2 : 0;
      camera = halfHeight
        ? new THREE.OrthographicCamera(-halfHeight, halfHeight, halfHeight, -halfHeight, 1, 10_000)
        : new THREE.PerspectiveCamera(fov, 1, 1, 10_000);
      camera.up.set(meta.up[0], meta.up[1], meta.up[2]);
      camera.position.set(position[0], position[1], position[2]);
      camera.lookAt(new THREE.Vector3(target[0], target[1], target[2]));
      // Plans de coupe déduits de l'étendue réelle de la scène (les décors vont de la
      // dizaine à plusieurs milliers d'unités selon la version) : le plan lointain passe
      // derrière le coin le plus éloigné, sans quoi les calques de fond sont tronqués.
      const box = new THREE.Box3().setFromObject(root);
      const corner = new THREE.Vector3();
      let distance = 100;
      for (let i = 0; i < 8; i += 1) {
        corner.set(i & 1 ? box.max.x : box.min.x, i & 2 ? box.max.y : box.min.y, i & 4 ? box.max.z : box.min.z);
        distance = Math.max(distance, camera.position.distanceTo(corner));
      }
      camera.far = distance * 1.05;
      camera.near = Math.max(camera.far / NEAR_RATIO, 0.1);
      camera.updateMatrixWorld(true);
      sortByDepth(root, camera);

      if (gltf.animations.length) {
        mixer = new THREE.AnimationMixer(root);
        for (const clip of gltf.animations) {
          // Cette piste ne décode pas encore la chute des coques : la séquence
          // cohérente coque + feu + réacteurs est pilotée par v7Intro.
          if (meta.version === '7.0' && ['AMM_7_0_Ships_Destroyed', 'AMM_Shot01'].includes(clip.name)) continue;
          const action = mixer.clipAction(clip);
          action.setLoop(THREE.LoopRepeat, Infinity);
          action.play();
        }
        mixer.update(0);
      }

      if (meta.version === '7.0') {
        const cannonTextures: CannonTextures = {};
        for (const [key, file] of Object.entries(meta.cannonTextures ?? {})) {
          const texture = new THREE.TextureLoader().load(new URL(file, new URL(metaUrl, window.location.href)).href);
          texture.colorSpace = THREE.NoColorSpace;
          texture.wrapS = texture.wrapT = THREE.ClampToEdgeWrapping;
          textures.add(texture);
          cannonTextures[key as keyof typeof cannonTextures] = texture;
        }
        v7Effects = createV7Effects(root, cannonTextures);
        v7Effects.update(0, reduced);
      }

      resize();
      if (reduced) return;
      document.addEventListener('visibilitychange', onVisibility);
      if (!document.hidden) start();
    };

    const setup = async () => {
      let meta: SceneMeta;
      try {
        const response = await fetch(metaUrl);
        if (!response.ok) throw new Error(String(response.status));
        meta = (await response.json()) as SceneMeta;
      } catch (error) {
        if (import.meta.env.DEV) console.warn(`[MenuScene] ${metaUrl} illisible`, error);
        return;
      }
      if (!alive || !meta?.camera) return;

      renderer = createRenderer
        ? createRenderer(canvas)
        : new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'high-performance' });
      renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
      renderer.sortObjects = true;
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      scene.background = new THREE.Color(meta.background ?? '#000000');

      window.addEventListener('resize', onResize);
      if (typeof ResizeObserver !== 'undefined') {
        observer = new ResizeObserver(onResize);
        observer.observe(canvas.parentElement ?? canvas);
      }

      const loader = createLoader ? createLoader() : new GLTFLoader();
      loader.load(
        glbUrl,
        gltf => { if (alive) build(gltf, meta); },
        undefined,
        error => { if (import.meta.env.DEV) console.warn(`[MenuScene] ${glbUrl} illisible`, error); },
      );
    };
    void setup();

    return () => {
      alive = false;
      stop();
      observer?.disconnect();
      window.removeEventListener('resize', onResize);
      document.removeEventListener('visibilitychange', onVisibility);
      mixer?.stopAllAction();
      v7Effects?.dispose();
      mixer = null;
      scene.traverse(object => {
        const mesh = object as THREE.Mesh;
        if (!mesh.isMesh) return;
        mesh.geometry.dispose();
        for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) material.dispose();
      });
      for (const texture of textures) texture.dispose();
      textures.clear();
      scene.clear();
      renderer?.dispose();
      renderer = null;
    };
  }, [glbUrl, metaUrl, createLoader, createRenderer]);

  return <canvas ref={canvasRef} className={`${s.canvas} ${className ?? ''}`} data-testid="menu-scene" aria-hidden="true" />;
}

export default MenuScene;
