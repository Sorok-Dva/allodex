import type { FatalityObject, FatalityTimeline } from '@/components/scene/FatalityViewer/timeline';
import type { FatalityEnvironment } from '@/components/scene/FatalityViewer/FatalityViewer';
import type { ParticleAtlasMeta } from '@/components/scene/FatalityViewer/particles';
const BASE = '/game';
type Size = { w: number; h: number };
type SpriteSlice = [top: number, right: number, bottom: number, left: number];
type SpriteInfo = { w: number; h: number; slice: SpriteSlice | null };
export type AudioMeta = { duration: number; loop: boolean };
export type MusicTrack = {
  id: string;
  name: string;
  title: { fr: string; en: string } | null;
  bank: string;
  group: string;
  duration: number;
  ogg: string;
  mp3: string;
  client: string;
};

/** Fichiers des deux formats d'un média, relatifs au dossier de la version. */
type MediaPair = { webm: string; mp4: string };
export type ArchiveTheme = {
  name: string;
  subsong?: number;
  duration: number;
  ogg: string;
  mp3: string;
  alternatives?: string[];
};
/** Fichiers de la scène de menu en 3D d'une version (`tools/extract_menu_scene.py`). */
export type ArchiveScene = { glb: string; meta: string };
/**
 * Contenu de `scene.json` : ce que le glTF ne porte pas. La caméra n'existe nulle part
 * dans les données du jeu — elle vient de `tools/scenes_manifest.json` — et le `fov` est
 * **vertical**, en degrés. Les coordonnées sont celles du `.glb` (axe `up` donné ici,
 * `[0, 0, 1]` pour toutes les scènes connues).
 */
export type SceneMeta = {
  cannonTextures?: Partial<Record<'projectile' | 'muzzle' | 'impact' | 'shield' | 'flame' | 'electric' | 'spark' | 'smoke', string>>;
  version?: string;
  camera: { position: [number, number, number]; target: [number, number, number]; fov: number; orthographicHeight?: number };
  up: [number, number, number];
  /** Couleur du ciel hors géométrie, en hexadécimal CSS. */
  background: string;
  /** Noms des animations du `.glb` (toutes jouées en boucle). */
  animations: string[];
  stats?: { triangles: number; textures: number; animations: number; objects: number };
};
/**
 * Une version archivée du jeu (`public/game/archive.json`, écrit par
 * `tools/extract_archive.py`). `media: null` = client absent au moment de
 * l'extraction : la page Chroniques affiche « Média non extrait ».
 */
export type ArchiveEntry = {
  version: string;
  /** Nom de l'add-on (« Power of Metal »), absent avant les add-ons (1.0). */
  name?: string;
  label: string;
  media: 'video' | 'image' | null;
  /** Nom du PNG de fond (`media: 'image'`). */
  background?: string;
  /** Mention affichée quand le fond est une illustration de repli et non la vraie scène. */
  background_note?: string;
  /**
   * Scène de menu en 3D (4.0 → 8.0) : rendue par `MenuScene` quand WebGL est là,
   * `background` restant l'illustration de repli.
   */
  scene?: ArchiveScene;
  /** Nom du PNG du logo de l'add-on ; absent = aucun client archivé ne le conserve. */
  logo?: string;
  /** Durée de la vidéo de menu, en secondes. */
  duration?: number;
  video?: MediaPair;
  intro?: MediaPair;
  theme?: ArchiveTheme;
  note?: string;
  theme_note?: string;
};

/**
 * Index des fatalités (`public/game/fatalities/fatalities.json`, écrit par
 * `tools/extract_fatalities.py` depuis le dernier client). Chaque personnage est un `.glb`
 * portant son animation d'attente et toutes celles que les scripts de fatalité demandent ;
 * chaque fatalité porte ses gabarits d'effet (`objects`, nœuds `vot:<nom>` de son `.glb`) et,
 * par personnage, la chronologie aplatie de son script (`timelines`).
 */
export type FatalityCharacter = {
  id: string;
  race: string;
  sex: 'male' | 'female';
  /** Nom du modèle (`KaniaMale`) : racine du `.glb` et préfixe de ses articulations. */
  model: string;
  glb: string;
  scale: number;
  /** Hauteur du personnage en unités du jeu, échelle comprise (cadrage de la caméra). */
  height: number;
  animations: string[];
  durations: Record<string, number>;
};
export type FatalityEntry = {
  id: string;
  /** Valeur de `FatalityType` dans le client (1-10 classes, 11-26 boutique). */
  type?: number;
  kind: 'class' | 'shop';
  label: { fr: string; en: string };
  fx?: string;
  fadeStart?: number;
  fadeDuration?: number;
  objects?: Record<string, FatalityObject>;
  timelines?: Record<string, FatalityTimeline>;
  note?: { fr: string; en: string };
  /** Nom en jeu de la fatalité (buff du client : « Rituel lunaire »), par langue officielle. */
  name?: FatalityText;
  /** Objets qui l'apprennent (`tools/fatality_items.py`), l'objet de boutique principal en tête. */
  items?: FatalityItem[];
  /** `icon` : objet → capacité par pointeurs ; `name` : par le nom de la capacité. */
  itemLink?: 'icon' | 'name' | null;
  since?: FatalitySince;
};
/** Texte officiel ; une langue absente n'a pas de texte officiel dans les clients. */
export type FatalityText = { fr?: string; en?: string; ru?: string };
export type FatalityItem = { name: FatalityText; icon: string | null; resourceIds: number[] };
export type FatalitySince = {
  /** Premier client archivé qui contient la fatalité. */
  version: string;
  client?: string;
  /** Dernier client archivé vérifié sans elle. */
  previous?: string;
  /** Date d'une actualité officielle (pas dans les données du client). */
  date?: { value: string; kind: 'announced' | 'attested'; region?: string; source: string; quote?: string };
};
export type FatalityScene = {
  glb: string;
  label?: { fr: string; en: string };
  /** Lieu réel du décor (`scene.site`) : carte, centre, rayon dégagé, orbite maximale de la caméra. */
  site?: { map: string; center: [number, number]; clear: number; orbit?: number | null; objects?: number; nearest?: number | null };
  environment?: FatalityEnvironment;
};
export type FatalitiesIndex = {
  races: Record<string, { fr: string; en: string; faction: string }>;
  characters: FatalityCharacter[];
  fatalities: FatalityEntry[];
  scene?: FatalityScene;
  particleAtlas?: ParticleAtlasMeta;
};

/**
 * Index des auras (`public/game/auras/auras.json`, écrit par `tools/extract_auras.py` depuis le
 * dernier client) : la collection « Ауры » de la garde-robe, chargée par l'écran seulement.
 */
export type AuraSince = { version: string; client?: string; previous?: string; method?: 'resourceId' | 'icon' };
export type AuraEntry = {
  id: string;
  resourceId: number | null;
  /** Nom et description de l'infobulle de la garde-robe (sort qui pose l'aura). */
  name: FatalityText;
  description: FatalityText;
  icon: string | null;
  buff?: { resourceId: number | null; name: FatalityText };
  /** Comment l'obtenir : texte du client (capacité débloquée ou objet), par langue. */
  obtain: FatalityText;
  obtainFrom?: 'unlock' | 'item';
  items?: FatalityItem[];
  contentKey?: boolean;
  /** Faux : aucun buff scripté pour cette aura dans le client (pas d'effet visuel). */
  visual?: boolean;
  fx?: string;
  objects?: Record<string, FatalityObject>;
  timeline?: import('@/components/scene/AuraViewer/AuraViewer').AuraTimeline;
  /** Buff visuel sans nom retrouvé par son `resourceId` voisin du sort (`link: "rid"`). */
  visualBuff?: { resourceId: number | null; link: 'rid' };
  since?: AuraSince;
};
/** Objet qui donne une aura et une apparence (peau de monture ou d'exosquelette, costume). */
export type AuraAppearance = {
  id: string;
  resourceId: number | null;
  /** `exoskin` : couleur de robe de carapace qui pose elle-même une aura au sol (`fx`, `timeline`). */
  kind: 'mount' | 'costume' | 'exoskin';
  name: FatalityText;
  description: FatalityText;
  icon: string | null;
  auras: string[];
  skin?: { resourceId: number | null; name: FatalityText; mount: FatalityText; source?: FatalityText };
  costume?: FatalityText[];
  model?: { glb: string; vot: string; objects: Record<string, FatalityObject> };
  obtain: FatalityText;
  since?: AuraSince;
  iconKey?: string | null;
  /** Couleur de robe : aura au sol de la peau (pièce `Slot_Global` de ses objets visuels). */
  visual?: boolean;
  fx?: string;
  objects?: Record<string, FatalityObject>;
  timeline?: import('@/components/scene/AuraViewer/AuraViewer').AuraTimeline;
  visualItems?: (number | null)[];
};
/** Clips de marche d'un gabarit de la création (`walk/<gabarit>.glb`) et sa vitesse de course. */
export type AuraWalkClips = { glb: string; clips: Record<string, number>; speed?: number };
export type AurasIndex = { schema: number; client: string; auras: AuraEntry[]; appearances: AuraAppearance[]; particleAtlas?: ParticleAtlasMeta;
  walks?: Record<string, AuraWalkClips> };
/** URL d'un fichier de `public/game/auras/` (`fx/a740017040.glb`, `icons/HeroHalo06.webp`). */
export const auraFile = (file: string) => `${BASE}/auras/${file}`;

let manifest: Record<string, Size> | null = null;
let sprites: Record<string, SpriteInfo> | null = null;
let audioIndex: Record<string, AudioMeta> | null = null;
let archive: ArchiveEntry[] | null = null;
let music: MusicTrack[] = [];
let fatalities: FatalitiesIndex | null = null;

async function fetchJson<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(String(res.status));
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export async function loadManifest(): Promise<void> {
  const [texturesJson, spritesJson, audioJson, archiveJson, musicJson, fatalitiesJson] = await Promise.all([
    fetchJson<{ textures?: Record<string, Size> }>(`${BASE}/manifest.json`),
    fetchJson<Record<string, SpriteInfo>>(`${BASE}/sprites.json`),
    fetchJson<Record<string, AudioMeta>>(`${BASE}/audio.json`),
    fetchJson<ArchiveEntry[]>(`${BASE}/archive.json`),
    fetchJson<MusicTrack[]>(`${BASE}/music.json`),
    fetchJson<FatalitiesIndex>(`${BASE}/fatalities/fatalities.json`),
  ]);
  fatalities = fatalitiesJson && Array.isArray(fatalitiesJson.characters) ? fatalitiesJson : null;
  manifest = texturesJson?.textures ?? {};
  sprites = spritesJson ?? {};
  audioIndex = audioJson ?? {};
  archive = archiveJson ?? [];
  music = Array.isArray(musicJson) ? musicJson : [];
  if (import.meta.env.DEV && !texturesJson) console.warn('[assets] manifest.json absent : lancez `npm run extract`');
}

export const hasAssets = () => manifest !== null && Object.keys(manifest).length > 0;
export const tex = (path: string) => `${BASE}/textures/${path}.png`;
export const texSize = (path: string): Size | undefined => manifest?.[path];
export const cursor = (name: string) => `${BASE}/cursors/${name}.cur`;
export const sprite = (name: string) => `${BASE}/sprites/${name}.png`;
export const spriteSize = (name: string): SpriteInfo | undefined => sprites?.[name];
export const gameLogo = () => '/logo.png';
/** Versions archivées, dans l'ordre de l'index (croissant) ; tableau vide si absent. */
export const archiveEntries = (): ArchiveEntry[] => archive ?? [];
/** Dernière version archivée du jeu (ou undefined si l'archive n'est pas chargée). */
export const latestArchiveEntry = (): ArchiveEntry | undefined => {
  const entries = archiveEntries();
  return entries.length > 0 ? entries[entries.length - 1] : undefined;
};
export const video = (name: 'intro' | 'mainmenu') => {
  const latest = latestArchiveEntry();
  if (latest) {
    if (name === 'intro' && latest.intro) {
      return {
        webm: archiveFile(latest.version, latest.intro.webm),
        mp4: archiveFile(latest.version, latest.intro.mp4),
      };
    }
    if (name === 'mainmenu' && latest.media === 'video' && latest.video) {
      return {
        webm: archiveFile(latest.version, latest.video.webm),
        mp4: archiveFile(latest.version, latest.video.mp4),
      };
    }
  }
  return { webm: `${BASE}/video/${name}.webm`, mp4: `${BASE}/video/${name}.mp4` };
};
/** URLs des deux formats d'une piste audio, ogg d'abord (ordre attendu des `<source>`). */
export const audioSrc = (name: string) => {
  if (name === 'menu') {
    const latest = latestArchiveEntry();
    if (latest?.theme) {
      return {
        ogg: archiveFile(latest.version, latest.theme.ogg),
        mp3: archiveFile(latest.version, latest.theme.mp3),
      };
    }
  }
  return { ogg: `${BASE}/audio/${name}.ogg`, mp3: `${BASE}/audio/${name}.mp3` };
};
export const audioMeta = (name: string): AudioMeta | undefined => {
  if (name === 'menu') {
    const latest = latestArchiveEntry();
    if (latest?.theme) {
      return { duration: latest.theme.duration, loop: true };
    }
  }
  return audioIndex?.[name];
};
export const musicTracks = (): MusicTrack[] => music;
/** Index des fatalités, ou `null` tant que `tools/extract_fatalities.py` n'a pas tourné. */
export const fatalitiesIndex = (): FatalitiesIndex | null => fatalities;
/** URL d'un fichier de `public/game/fatalities/` (`characters/aed-female.glb`, `fx/warrior.glb`). */
export const fatalityFile = (file: string) => `${BASE}/fatalities/${file}`;
/** URL d'un fichier d'une version archivée (`background.png`, `menu.webm`, `theme.ogg`…). */
export const archiveFile = (version: string, file: string) => `${BASE}/archive/${version}/${file}`;
/** URL d'un fichier commun à toutes les versions (emblème de chargement). */
export const archiveCommon = (file: string) => `${BASE}/archive/_common/${file}`;

/** Racines de textures du client effectivement utilisées par le site. */
export const T = {
  medals: 'Interface/Ingame/Medals/Textures',
  main2: 'Interface/Wrap/MainMenu/Main2',
  pinMenu: 'Interface/Ingame/ContextPinMenu3/textures',
  standardBtn: 'Interface/Common/Buttons/Standard',
  actions: 'Interface/Icons/Actions',
  spells: 'Interface/Icons/Spells',
  choiceFaction: 'Interface/Ingame/ChoiceFaction/Textures',
  videoIcon: 'Interface/Icons/Special/Notifications/RepostVideo',
} as const;
