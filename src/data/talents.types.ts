/**
 * Données produites par `tools/extract_talents.py` (`public/game/talents/`). Tout vient des
 * `pack.bin` des clients ; un champ absent l'est dans les données (voir `missing`).
 */
export type TalentLang = 'fr' | 'en' | 'ru';
export type LocText = Partial<Record<TalentLang, string>>;

export type ScalerNode = { type: string; of?: ScalerNode[]; multiplier?: number };
export type TalentVar = { value: number | null; scalers?: ScalerNode[] };

export type TalentRank = {
  ref: string;
  vars?: Record<string, TalentVar>;
  /** Description propre au rang, seulement quand elle diffère de celle du talent. */
  description?: LocText;
  icon?: string;
};

export type TalentInfo = {
  kind: 'spell' | 'ability';
  /** Chemin xdb (clients 32 bits) ou identifiant d'objet `#n` (clients 64 bits). */
  ref: string;
  name: LocText;
  description?: LocText;
  icon?: string;
  ranks: TalentRank[];
  missing?: string[];
};

export type TalentCell = {
  type: string;
  talent: string;
  /** Talent prérequis (`parentTalent`). */
  parent?: string;
  unlock?: string;
  linked?: string[];
};

export type BookLayer = { points: number | null; cells: (TalentCell | null)[]; unlock?: string };

export type TalentField = {
  ref: string;
  name: LocText;
  icon: string | null;
  rows: (TalentCell | null)[][];
  /** Case de départ (ligne, colonne) quand la ressource la déclare. */
  start?: [number, number];
};

export type ClassTalents = {
  version: string;
  code: string;
  ref: string;
  name: LocText;
  languages: TalentLang[];
  format: 'v1' | 'v2';
  book: { ref: string; layers: BookLayer[] };
  fields: TalentField[];
  talents: Record<string, TalentInfo>;
};

export type ClassEntry = {
  code: string;
  slug: string;
  name: LocText;
  talents: number;
  layers: number;
  fields: number;
  systems: string[];
  missingNames: number;
};

export type VersionEntry = {
  id: string;
  label: string;
  client: string;
  languages: TalentLang[];
  format: 'v1' | 'v2';
  classes: ClassEntry[];
};

export type TalentsIndex = {
  versions: VersionEntry[];
  unavailable: { id: string; reason: string }[];
};

/* --- fenêtre TalentBuilder (17.0) --- */
export type Align = 'low' | 'high' | 'center' | 'both' | 'lowAbs';
export type AxisPlacement = { align: Align; pos?: number; high?: number; size?: number };
export type UiLayer = {
  type: string;
  /** ARGB en hexadécimal. */
  color: string;
  texture?: string;
  /** Texture découpée en neuf (`WidgetLayerTiledTexture`) : haut, droite, bas, gauche, en pixels. */
  slice?: [number, number, number, number];
  middle?: [number, number];
  /** Milieu étiré (1) ou répété (0), en X puis en Y. */
  stretch?: [number, number];
};
export type UiVariant = Partial<Record<'highlight' | 'disabled' | 'highlighted' | 'normal' | 'pressed' | 'pressedHighlighted', UiLayer>>;
export type UiWidget = {
  type: string;
  name: string | null;
  place: { x: AxisPlacement; y: AxisPlacement };
  priority?: number;
  back?: UiLayer;
  front?: UiLayer | null;
  textTag?: string;
  variants?: UiVariant[];
  children?: UiWidget[];
};
export type UiTexture = { path: string; file?: string; width?: number; height?: number; w?: number; h?: number; realW?: number; realH?: number };
export type Rgba = [number, number, number, number];
type FieldConsts = { SCALE: number; LEFT_BORDER: number; UP_BORDER: number; INTERVAL_X: number; INTERVAL_Y: number };
/** Constantes lues dans le bytecode des scripts de l'addon (voir `builder_layout` de l'extracteur). */
export type BuilderLayout = {
  baseField: FieldConsts & { arrow: [number, number, number]; side: { left: number; right: number } };
  field: FieldConsts;
  builder: { fieldsInterval: number; mainOffsetY: number };
  counts: Record<'BASE_TALENTS_ROW_COUNT' | 'BASE_TALENTS_COL_COUNT' | 'FIELD_TALENTS_FIELD_COUNT' | 'FIELD_TALENTS_ROW_COUNT' | 'FIELD_TALENTS_COL_COUNT', number>;
  /** Coût en points des rangs 1, 2, 3 d'un sort du livre. */
  rankCost: number[];
  fieldTalentSize: { main: number; done: number };
  baseTalentSize: { main: number; icon: number };
  fieldHighlight: Record<string, Rgba>;
  classColors: Record<string, Rgba>;
  /** Code de classe → texture de `PlayerClasses` (absente du client pour certaines classes). */
  classIcons: Record<string, string>;
};
export type UiLayout = {
  addon: string;
  version: string;
  root: UiWidget;
  templates: Record<string, UiWidget>;
  namedTextures: Record<string, string>;
  related: string[];
  textures: Record<string, UiTexture>;
  layout: BuilderLayout;
};
