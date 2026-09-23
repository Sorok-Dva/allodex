/**
 * Descripteur de personnage : ce que l'écran de création produit, et tout ce qu'il faut pour
 * reconstruire le modèle côté client ou serveur. Sérialisable tel quel (JSON), versionné.
 *
 * Les apparences sont des **indices** dans les listes du gabarit (`chargen.json` →
 * `templates[<Gabarit>].variations`), comme le client les envoie au serveur (`SetSceneCharacterVariation`,
 * `CreateAvatar`) ; ils restent valables tant que les listes du client ne changent pas, d'où le
 * champ `data` qui date les données utilisées.
 */
import type { AppearanceKey, ChargenData, ChargenTemplate, Sex } from './chargen.types';

export const DESCRIPTOR_KIND = 'allodex.character';
export const DESCRIPTOR_VERSION = 1;

/** Indices d'apparence ; une clé absente = valeur par défaut du gabarit. */
export type Appearance = Partial<Record<AppearanceKey, number>>;

/** Compagnon du trio gibberling (`secondary`, `tertiary`) : même race, sexe et apparence propres. */
export type Companion = { sex: Sex; appearance: Appearance; name: string };

export type PetChoice = { template: string; color: number; name: string };

export type CharacterDescriptor = {
  kind: typeof DESCRIPTOR_KIND;
  version: typeof DESCRIPTOR_VERSION;
  /** Données de référence (client et schéma de `chargen.json`). */
  data: { client: string; schema: number };
  faction: string;
  race: string;
  sex: Sex;
  class: string;
  name: string;
  appearance: Appearance;
  /** Tenue montrée à la création (0 départ, 1 moyenne, 2 haute) : visuel seulement. */
  equipment: 0 | 1 | 2;
  companions?: { secondary?: Companion; tertiary?: Companion };
  pet?: PetChoice | null;
  createdAt?: string;
  updatedAt?: string;
};

export const APPEARANCE_KEYS: AppearanceKey[] = ['faces', 'facials', 'hairs', 'hairColors', 'skins', 'skinColors',
  'additionals', 'shoulderStones', 'shoulderStoneColors'];

/** Races jouées en trio (trois personnages nommés) : les gibberlings. */
export const TRIO_RACES = new Set(['Gibberling']);

export function comboKey(race: string, cls: string): string {
  return `${race}/${cls}`;
}

export function templateFor(data: ChargenData, race: string, cls: string, sex: Sex): ChargenTemplate | null {
  const name = data.combos[comboKey(race, cls)]?.sexes[sex]?.template;
  return name ? data.templates[name] ?? null : null;
}

/** Nombre d'options de chaque commande d'apparence pour un gabarit (0 = commande absente). */
export function appearanceCounts(tpl: ChargenTemplate | null): Record<AppearanceKey, number> {
  const v = tpl?.variations ?? {};
  const out = {} as Record<AppearanceKey, number>;
  for (const key of APPEARANCE_KEYS) out[key] = (v[key] as unknown[] | undefined)?.length ?? 0;
  return out;
}

/** Indice effectif d'une commande : celui du descripteur s'il est valide, sinon le défaut du gabarit. */
export function appearanceIndex(tpl: ChargenTemplate | null, appearance: Appearance, key: AppearanceKey): number {
  const n = appearanceCounts(tpl)[key];
  const value = appearance[key];
  if (value !== undefined && Number.isInteger(value) && value >= 0 && value < n) return value;
  const d = tpl?.variations?.default?.[key];
  return d !== undefined && d < n ? d : 0;
}

export function defaultAppearance(tpl: ChargenTemplate | null): Appearance {
  const out: Appearance = {};
  const counts = appearanceCounts(tpl);
  for (const key of APPEARANCE_KEYS) if (counts[key] > 0) out[key] = appearanceIndex(tpl, {}, key);
  return out;
}

export function firstClass(data: ChargenData, race: string): string {
  const classes = data.races[race]?.classes ?? [];
  return data.classOrder.find(c => classes.includes(c)) ?? classes[0] ?? '';
}

export function availableSexes(data: ChargenData, race: string, cls: string): Sex[] {
  const sexes = data.combos[comboKey(race, cls)]?.sexes ?? {};
  return (['male', 'female'] as Sex[]).filter(s => sexes[s]);
}

export function petsFor(data: ChargenData, race: string, cls: string): string[] {
  const combo = data.combos[comboKey(race, cls)];
  if (!combo) return [];
  // Seules les classes à familier (les Pacificateurs, `classesWithPet` du script) en ont un ;
  // l'« Облик » choisit alors parmi tous les familiers de la race.
  const hasPet = Object.values(combo.sexes).some(s => s?.pet);
  return hasPet ? data.races[race]?.pets ?? [] : [];
}

export function newDescriptor(data: ChargenData, race: string, cls?: string, sex?: Sex): CharacterDescriptor {
  const klass = cls && data.races[race]?.classes.includes(cls) ? cls : firstClass(data, race);
  const sexes = availableSexes(data, race, klass);
  const chosen = sex && sexes.includes(sex) ? sex : sexes[0] ?? 'male';
  const tpl = templateFor(data, race, klass, chosen);
  const d: CharacterDescriptor = {
    kind: DESCRIPTOR_KIND, version: DESCRIPTOR_VERSION, data: { client: data.client, schema: data.schema },
    faction: data.races[race]?.faction ?? '', race, sex: chosen, class: klass, name: '',
    appearance: defaultAppearance(tpl), equipment: 0, pet: null,
  };
  if (TRIO_RACES.has(race)) {
    d.companions = {
      secondary: { sex: chosen, appearance: defaultAppearance(tpl), name: '' },
      tertiary: { sex: chosen, appearance: defaultAppearance(tpl), name: '' },
    };
  }
  const pets = petsFor(data, race, klass);
  if (pets.length) d.pet = { template: pets[0], color: data.pets[pets[0]]?.variations?.default?.faces ?? 0, name: '' };
  return d;
}

/** Change de race / classe / sexe en gardant ce qui reste valable (apparence ramenée aux bornes). */
export function withSelection(data: ChargenData, d: CharacterDescriptor, next: { race?: string; class?: string; sex?: Sex }): CharacterDescriptor {
  const race = next.race ?? d.race;
  if (race !== d.race) return newDescriptor(data, race, next.class ?? d.class, next.sex ?? d.sex);
  const cls = next.class && data.races[race]?.classes.includes(next.class) ? next.class : d.class;
  const sexes = availableSexes(data, race, cls);
  const sex = next.sex && sexes.includes(next.sex) ? next.sex : sexes.includes(d.sex) ? d.sex : sexes[0];
  const tpl = templateFor(data, race, cls, sex);
  const appearance = sex === d.sex ? clampAppearance(tpl, d.appearance) : defaultAppearance(tpl);
  const pets = petsFor(data, race, cls);
  const pet = pets.length ? (d.pet && pets.includes(d.pet.template) ? d.pet : { template: pets[0], color: 0, name: d.pet?.name ?? '' }) : null;
  return { ...d, race, class: cls, sex, appearance, pet };
}

export function clampAppearance(tpl: ChargenTemplate | null, appearance: Appearance): Appearance {
  const out: Appearance = {};
  const counts = appearanceCounts(tpl);
  for (const key of APPEARANCE_KEYS) if (counts[key] > 0) out[key] = appearanceIndex(tpl, appearance, key);
  return out;
}

export function shiftAppearance(tpl: ChargenTemplate | null, appearance: Appearance, key: AppearanceKey, delta: number): Appearance {
  const n = appearanceCounts(tpl)[key];
  if (!n) return appearance;
  const current = appearanceIndex(tpl, appearance, key);
  return { ...appearance, [key]: ((current + delta) % n + n) % n };
}

/** Tirage uniforme de chaque commande (bouton « Случайный выбор »). `rand` ∈ [0, 1). */
export function randomAppearance(tpl: ChargenTemplate | null, rand: () => number = Math.random): Appearance {
  const out: Appearance = {};
  const counts = appearanceCounts(tpl);
  for (const key of APPEARANCE_KEYS) if (counts[key] > 0) out[key] = Math.floor(rand() * counts[key]);
  return out;
}

export type NameCheck = { ok: boolean; reason?: 'empty' | 'short' | 'long' | 'alphabet' | 'mixed' };

/**
 * Règles de nommage du client (`NameRules`) : un seul alphabet (cyrillique sur les serveurs
 * russes, latin ailleurs), longueurs de la règle de l'alphabet employé.
 */
export function checkName(data: ChargenData, name: string): NameCheck {
  const rules = data.nameRules?.length ? data.nameRules : [{ pattern: '[A-Za-z]+', min: 4, max: 13 }];
  if (!name) return { ok: false, reason: 'empty' };
  const matching = rules.filter(r => new RegExp(`^${r.pattern}$`).test(name));
  if (!matching.length) {
    const partial = rules.some(r => new RegExp(r.pattern).test(name));
    return { ok: false, reason: partial ? 'mixed' : 'alphabet' };
  }
  const rule = matching[0];
  if (name.length < rule.min) return { ok: false, reason: 'short' };
  if (name.length > rule.max) return { ok: false, reason: 'long' };
  return { ok: true };
}

export type DescriptorError = { path: string; message: string };

/** Validation complète (côté serveur comme côté client) contre les données extraites. */
export function validateDescriptor(data: ChargenData, value: unknown): DescriptorError[] {
  const errors: DescriptorError[] = [];
  const d = value as Partial<CharacterDescriptor> | null;
  if (!d || typeof d !== 'object') return [{ path: '', message: 'not an object' }];
  if (d.kind !== DESCRIPTOR_KIND) errors.push({ path: 'kind', message: `expected ${DESCRIPTOR_KIND}` });
  if (d.version !== DESCRIPTOR_VERSION) errors.push({ path: 'version', message: `unsupported version ${String(d.version)}` });
  const race = d.race ? data.races[d.race] : undefined;
  if (!race) errors.push({ path: 'race', message: `unknown race ${String(d.race)}` });
  else if (race.faction !== d.faction) errors.push({ path: 'faction', message: `race ${d.race} belongs to ${race.faction}` });
  if (race && (!d.class || !race.classes.includes(d.class))) errors.push({ path: 'class', message: `class ${String(d.class)} not available for ${d.race}` });
  if (d.sex !== 'male' && d.sex !== 'female') errors.push({ path: 'sex', message: 'expected male or female' });
  const tpl = d.race && d.class && d.sex ? templateFor(data, d.race, d.class, d.sex) : null;
  if (race && d.class && !tpl) errors.push({ path: 'sex', message: 'no template for this combination' });
  const counts = appearanceCounts(tpl);
  for (const [key, v] of Object.entries(d.appearance ?? {})) {
    const k = key as AppearanceKey;
    if (!(k in counts)) errors.push({ path: `appearance.${key}`, message: 'unknown control' });
    else if (!Number.isInteger(v) || (v as number) < 0 || (v as number) >= counts[k]) errors.push({ path: `appearance.${key}`, message: `out of range 0..${counts[k] - 1}` });
  }
  if (typeof d.name !== 'string') errors.push({ path: 'name', message: 'expected a string' });
  else if (!checkName(data, d.name).ok) errors.push({ path: 'name', message: `invalid name (${checkName(data, d.name).reason})` });
  if (![0, 1, 2].includes(d.equipment as number)) errors.push({ path: 'equipment', message: 'expected 0, 1 or 2' });
  if (d.pet) {
    const pets = d.race && d.class ? petsFor(data, d.race, d.class) : [];
    if (!pets.includes(d.pet.template)) errors.push({ path: 'pet.template', message: 'pet not offered to this class' });
    const colors = data.pets[d.pet.template]?.variations?.faces?.length ?? 0;
    if (!Number.isInteger(d.pet.color) || d.pet.color < 0 || d.pet.color >= Math.max(colors, 1)) errors.push({ path: 'pet.color', message: 'out of range' });
  }
  return errors;
}

export function serialize(d: CharacterDescriptor): string {
  return JSON.stringify(d, null, 2);
}

export function parseDescriptor(data: ChargenData, text: string): { descriptor: CharacterDescriptor | null; errors: DescriptorError[] } {
  let value: unknown;
  try { value = JSON.parse(text); } catch { return { descriptor: null, errors: [{ path: '', message: 'invalid JSON' }] }; }
  const errors = validateDescriptor(data, value);
  return { descriptor: errors.length ? null : value as CharacterDescriptor, errors };
}
