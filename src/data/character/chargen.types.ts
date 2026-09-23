/**
 * Données de la création de personnage (`public/game/character/chargen.json`, écrit par
 * `tools/extract_character_creation.py` depuis le dernier client, RU 17.x).
 */
import type { Localized } from '@/lib/i18n';

/** Texte du client : russe et anglais (le `.loc` du client RU), français (client FR). */
export type GameText = Localized & { ru?: string };

export type Sex = 'male' | 'female';

export type ChargenFaction = { id: string; name: GameText | null; races: string[] };

export type ChargenRace = {
  faction: string;
  name: GameText | null;
  sexNames: Partial<Record<Sex, GameText | null>>;
  motto: GameText | null;
  desc: GameText | null;
  classes: string[];
  scene: string;
  /** Familiers proposés aux Pacificateurs de la race (gabarits de `pets`). */
  pets?: string[];
};

export type ChargenClass = { name: GameText | null; label: GameText | null };

export type ItemShape = {
  geoset?: string;
  /** Modèle accroché (`attach/…glb`) et son locator (articulation du squelette). */
  model?: string;
  locator?: string;
  /** Effets du gabarit accroché (`fx/…glb` : particules, composants — boule de feu du mage). */
  fx?: string;
  texture?: string;
  color?: string;
};
export type TexturePatch = { rect: [number, number, number, number]; texture: string };
export type SexKey = 'unisex' | 'male' | 'female';

/** Objet visuel du client (`VisualItem`) : géosets montrés, géosets cachés, patchs de la peau cuite. */
export type ChargenItem = {
  shapes?: Partial<Record<SexKey, ItemShape[]>>;
  hidden?: Partial<Record<SexKey, string[]>>;
  patches?: Partial<Record<SexKey, TexturePatch[]>>;
  underwear?: number;
};

export type Growth = {
  start: string | null;
  loop: string | null;
  items: { slot: string; item: string }[];
  /** Effets de la tenue de création (`fx/…glb`), rejoués avec l'animation de création : échelle du client (+0x24 du `ChargenEffect`), `runType` (0 ou 1, sens non établi). */
  fx: { locator: string; scale: number; runType?: number; fx: string | null }[];
};

export type ChargenCombo = {
  race: string;
  class: string;
  name: GameText | null;
  title: GameText | null;
  desc: GameText | null;
  sexes: Partial<Record<Sex, { template: string; pet?: string; growths: Growth[] }>>;
};

export type Variations = {
  faces?: string[];
  facials?: string[];
  hairs?: string[];
  hairColors?: string[];
  skins?: (string | null)[];
  skinColors?: string[];
  additionals?: string[];
  shoulderStones?: string[];
  shoulderStoneColors?: string[];
  /** Préréglages de corpulence (`ModelMorphSettings.presets`) : {indice de commande: valeur}. */
  morphPresets?: Record<string, number>[];
  default?: Partial<Record<AppearanceKey, number>>;
};

/** Os touchés par une commande de corpulence : échelle locale `valeur ** puissance` par axe. */
export type MorphBone = { bone: string; power: [number, number, number] };

export type ChargenTemplate = {
  gender: Sex | 'none';
  glb?: string;
  scale?: number;
  height?: number;
  elements?: string[];
  joints?: string[];
  clips?: Record<string, number>;
  baked?: string;
  hairColored?: string[];
  specialHairPatch?: TexturePatch[];
  ui?: { cameraAnchor: number[]; cameraBodyAnchorCoeff: number; preMissionAdditionalAway: number; preMissionFaceCameraAnchor: number[]; scale: number };
  defaultDress?: string | null;
  underwear?: string | null;
  variations?: Variations;
  /** Commandes de corpulence (indice → os), voir `tools/allods_chargen.py` (`read_morph`). */
  morph?: Record<string, MorphBone[]>;
  races?: string[];
};

/** Résumé d'un décor de race dans `chargen.json` ; le détail est dans `scenes/<Race>.json`. */
export type SceneMeta = {
  file: string;
  character: SceneCharacter;
  camera: SceneCamera;
  instances?: number;
};

export type SceneCharacter = {
  yaw: number;
  scale: number;
  /** Place sur l'estrade, relative à l'origine du décor. */
  position?: [number, number, number];
  /** Ambiante de la zone à la place, unités du jeu (1 = 0x80). */
  ambient?: [number, number, number] | null;
  /** `PointLightColor` de la zone (1 = 0x80). */
  pointColor?: [number, number, number] | null;
  /** Lumières ponctuelles de la carte qui atteignent la place (positions relatives à l'origine du décor). */
  pointLights?: { p: [number, number, number]; intensity: number; radius: number; attenuation: number }[];
};

/** Caméra de `UICharacterScenes` : position relative au personnage, lacet et tangage (degrés, tangage positif vers le bas), champ horizontal (rad). */
export type SceneCamera = { position: [number, number, number]; yaw: number; pitch: number; height: number; fov: number };

/** `scenes/<Race>.json` : décor de la chaîne des cinématiques moteur, places de la création. */
export type ChargenSceneFile = {
  origin: [number, number, number];
  character: SceneCharacter;
  camera: SceneCamera;
  decor: {
    glb: string; light: string;
    instances: import('@/components/scene/EngineCutscene/timeline').DecorInstance[];
    sky: { radius: number } | null; skyGlb?: string | null; terrainGlb?: string | null;
  };
  objects: Record<string, import('@/components/scene/FatalityViewer/timeline').FatalityObject>;
  particleAtlas: import('@/components/scene/FatalityViewer/particles').ParticleAtlasMeta | null;
  light: import('@/components/scene/EngineCutscene/timeline').EngineLight;
  sounds?: { ambience: string[] };
  source?: { scene: string; map: string; position: [number, number, number] };
};

export type NameRule = { pattern: string; min: number; max: number };

export type ChargenData = {
  schema: number;
  client: string;
  texts: Record<string, GameText | null>;
  progress: Record<string, GameText | null>;
  raceOrder: string[];
  classOrder: string[];
  nameRules?: NameRule[];
  ui?: { layout: string; related: Record<string, Record<string, string>> };
  factions: ChargenFaction[];
  races: Record<string, ChargenRace>;
  classes: Record<string, ChargenClass>;
  combos: Record<string, ChargenCombo>;
  templates: Record<string, ChargenTemplate>;
  pets: Record<string, ChargenTemplate>;
  items: Record<string, ChargenItem>;
  slots: string[];
  scenes?: Record<string, SceneMeta>;
  /** Métadonnées des gabarits d'effets (`fx/`) et atlas de leurs particules. */
  fx?: { objects: Record<string, import('@/components/scene/FatalityViewer/timeline').FatalityObject>;
    particleAtlas: import('@/components/scene/FatalityViewer/particles').ParticleAtlasMeta | null };
  /** Sons de l'interface (`Chargen.bsb`) : `faction`, `class:<CLASSE>`, `voice:<Race>/<CLASSE>` → fichier sans extension. */
  sounds?: Record<string, string>;
  notes?: string[];
};

/** Commandes d'apparence de l'écran (`ScriptCustomization` : `controlOrder`). */
export type AppearanceKey = 'faces' | 'facials' | 'hairs' | 'hairColors' | 'skins' | 'skinColors' | 'additionals'
  | 'shoulderStones' | 'shoulderStoneColors' | 'morphPresets';

/** Arbre de widgets de l'addon `CharacterGenerator` (`ui/layout.json`). */
export type Axis = { align: 'low' | 'high' | 'center' | 'both' | 'lowAbs' | number; pos?: number; high?: number; size?: number };
export type UiLayer = { type: string; color: string; texture?: string; tile?: number[]; blend?: number };
export type UiWidget = {
  type: string;
  name: string | null;
  place: { x: Axis; y: Axis };
  priority: number;
  /** Caché au départ (octet de visibilité du widget) : les scripts le montrent selon l'étape. */
  hidden?: boolean;
  back?: UiLayer;
  /** Calques suivants du widget (perle de l'orbe d'apparence, reflet du bandeau). */
  layers?: UiLayer[];
  /** Texte fixe d'un `WidgetTextView` (« Sexe »), balisage du jeu. */
  text?: GameText;
  textTag?: string;
  variants?: Record<string, UiLayer>[];
  children?: UiWidget[];
};
export type UiLayout = {
  root: UiWidget;
  related: Record<string, Record<string, string>>;
  /** Bandeau bas des écrans du menu (addon `Main`), sous les boutons du bas. */
  bottomLine?: UiWidget | null;
  textures: Record<string, { path: string; file: string; width: number; height: number }>;
};
