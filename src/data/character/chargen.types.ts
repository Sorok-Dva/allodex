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
  fx: { locator: string; scale: number; model: string | null }[];
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
  default?: Partial<Record<AppearanceKey, number>>;
};

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
  races?: string[];
};

export type SceneMeta = {
  glb: string;
  objects: number;
  clips: number;
  character: { yaw: number; scale: number; position?: [number, number, number] };
  camera: { position: [number, number, number]; yaw: number; pitch: number; height: number; fov: number; placeOffset?: [number, number, number] };
  light?: {
    ambient: string; sun: string; point: string; specular: string;
    sunPitch: number; sunYaw: number; sunDirection: [number, number, number];
    fog: { color: string; near: number; far: number };
  };
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
  notes?: string[];
};

/** Commandes d'apparence de l'écran (`ScriptCustomization` : `controlOrder`). */
export type AppearanceKey = 'faces' | 'facials' | 'hairs' | 'hairColors' | 'skins' | 'skinColors' | 'additionals'
  | 'shoulderStones' | 'shoulderStoneColors';

/** Arbre de widgets de l'addon `CharacterGenerator` (`ui/layout.json`). */
export type Axis = { align: 'low' | 'high' | 'center' | 'both' | 'lowAbs' | number; pos?: number; high?: number; size?: number };
export type UiLayer = { type: string; color: string; texture?: string; tile?: number[]; blend?: number };
export type UiWidget = {
  type: string;
  name: string | null;
  place: { x: Axis; y: Axis };
  priority: number;
  back?: UiLayer;
  textTag?: string;
  variants?: Record<string, UiLayer>[];
  children?: UiWidget[];
};
export type UiLayout = {
  root: UiWidget;
  related: Record<string, Record<string, string>>;
  textures: Record<string, { path: string; file: string; width: number; height: number }>;
};
