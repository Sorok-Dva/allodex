import * as THREE from 'three';
import type { SceneCharacter } from '@/data/character/chargen.types';

/** Lumières ponctuelles au plus par personnage (celles des places en comptent de 0 à 6). */
export const MAX_POINT_LIGHTS = 8;

/**
 * Éclairage des personnages de la création, d'après les shaders du client 17
 * (`Material/common_sm4-dx11.bin`, `Material/pointLit-dx11.bin`, désassemblés) :
 *
 * - passe principale (personnage sans couleurs de sommets) : `texture × (shadowColor + madColor ·
 *   max(N·L, 0) + ¼ · min(N·L, 0)² · (⅔ · Σ madColor − madColor))`, soit l'ambiante de la zone, le
 *   soleil (`DiffuseColor`, `lightDir`) et un faible contre-jour ; **aucune lumière ponctuelle** ;
 * - une passe additive par lumière ponctuelle (`pointLit`) : même formule avec la couleur de la
 *   lumière et sa direction depuis le sommet, **saturée à 2 × la texture** (`mul_sat` × 0,5 puis × 2).
 *
 * La couleur que le moteur passe à `pointLit` n'est pas dans les données : on applique la loi prouvée
 * sur le décor (octet 2 du `lightvrt`, `extract_engine_cutscene.vertex_light`), la même que celle des
 * sommets de l'estrade où se tient le personnage : `PointLightColor · min(1, Σ intensité ·
 * (1 − d / rayon)^atténuation · max(N·L, 0))` — choix du lecteur : avec `intensité × PointLightColor`
 * plafonné à 2 par lumière (le seul plafond du shader), les deux lanternes des gibberlings donnaient
 * jusqu'à 2,2 × la texture, bien au-dessus de l'estrade qu'elles éclairent (0,76 au plus).
 *
 * Ici : l'ambiante en émission modulée par la texture, le soleil par la `DirectionalLight` du décor
 * (Lambert × π), le contre-jour du soleil et les lumières ponctuelles ajoutés au fragment.
 */
export class ActorLighting {
  readonly uniforms = {
    chargenPointPos: { value: Array.from({ length: MAX_POINT_LIGHTS }, () => new THREE.Vector3()) },
    chargenPointColor: { value: new THREE.Vector3() },
    /** Rayon, atténuation, intensité de chaque lumière. */
    chargenPointRange: { value: Array.from({ length: MAX_POINT_LIGHTS }, () => new THREE.Vector3(1, 1, 0)) },
    chargenPointCount: { value: 0 },
    chargenSunDir: { value: new THREE.Vector3(0, 0, 1) },
    chargenSunColor: { value: new THREE.Vector3() },
  };
  ambient = new THREE.Color(0.4, 0.4, 0.45);
  private world: THREE.Vector3[] = [];

  /** Lumières d'une place (positions relatives à l'origine du décor = repère du monde). */
  setScene(character: SceneCharacter | undefined, sun: { color: THREE.Color; direction: THREE.Vector3 } | null): void {
    const [ar, ag, ab] = character?.ambient ?? [0.4, 0.4, 0.45];
    this.ambient.setRGB(ar, ag, ab);
    const color = character?.pointColor ?? [0, 0, 0];
    const lights = (character?.pointLights ?? []).slice(0, MAX_POINT_LIGHTS);
    this.world = lights.map(l => new THREE.Vector3(...l.p));
    this.uniforms.chargenPointColor.value.set(color[0], color[1], color[2]);
    lights.forEach((l, i) => { this.uniforms.chargenPointRange.value[i].set(l.radius, l.attenuation, l.intensity); });
    this.uniforms.chargenPointCount.value = lights.length;
    if (sun) {
      this.uniforms.chargenSunColor.value.set(sun.color.r, sun.color.g, sun.color.b);
      this.world.push(sun.direction.clone().normalize());
    } else {
      this.uniforms.chargenSunColor.value.set(0, 0, 0);
      this.world.push(new THREE.Vector3(0, 0, 1));
    }
  }

  /** Positions des lumières et direction du soleil dans le repère de la caméra (chaque image). */
  update(camera: THREE.Camera, world: THREE.Object3D): void {
    const view = camera.matrixWorldInverse;
    const n = this.uniforms.chargenPointCount.value;
    for (let i = 0; i < n; i++) this.uniforms.chargenPointPos.value[i].copy(this.world[i]).applyMatrix4(world.matrixWorld).applyMatrix4(view);
    const sun = this.world[n];
    if (sun) this.uniforms.chargenSunDir.value.copy(sun).transformDirection(view);
  }

  /** Matériau opaque d'un personnage : ambiante en émission, contre-jour et lumières ponctuelles. */
  apply(material: THREE.MeshLambertMaterial): void {
    material.emissive = this.ambient;
    material.emissiveMap = material.map;
    if (material.userData.chargenLit) { material.needsUpdate = true; return; }
    material.userData.chargenLit = true;
    material.onBeforeCompile = shader => {
      Object.assign(shader.uniforms, this.uniforms);
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <common>', `#include <common>
uniform vec3 chargenPointPos[${MAX_POINT_LIGHTS}];
uniform vec3 chargenPointColor;
uniform vec3 chargenPointRange[${MAX_POINT_LIGHTS}];
uniform int chargenPointCount;
uniform vec3 chargenSunDir;
uniform vec3 chargenSunColor;
vec3 chargenBack(vec3 c, float ndl) { float b = min(ndl, 0.0); return 0.25 * b * b * (vec3(0.666 * (c.r + c.g + c.b)) - c); }`)
        .replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>
{
  vec3 chargenN = normalize(normal);
  float chargenPoint = 0.0;
  for (int i = 0; i < ${MAX_POINT_LIGHTS}; i++) {
    if (i >= chargenPointCount) break;
    vec3 toLight = chargenPointPos[i] + vViewPosition;
    float d = length(toLight);
    float k = chargenPointRange[i].z * pow(max(0.0, 1.0 - d / chargenPointRange[i].x), chargenPointRange[i].y);
    chargenPoint += k * max(dot(chargenN, toLight / max(d, 1e-4)), 0.0);
  }
  vec3 chargenLit = chargenBack(chargenSunColor, dot(chargenN, chargenSunDir)) + chargenPointColor * min(chargenPoint, 1.0);
  totalEmissiveRadiance += diffuseColor.rgb * chargenLit;
}`);
    };
    material.customProgramCacheKey = () => 'chargen-actor';
    material.needsUpdate = true;
  }
}
