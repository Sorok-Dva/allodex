/**
 * Fonctions pures de l'écran des auras (testées sans rendu) : noms affichés, ligne de version,
 * obtention, habit de l'avatar.
 */
import type { AuraAppearance, AuraEntry, AuraSince, FatalityCharacter, FatalityText } from '@/lib/assets';
import type { Lang } from '@/lib/i18n/messages';
import type { ChargenData, Sex } from '@/data/character/chargen.types';
import { dressFor } from '@/screens/FatalitiesScreen/outfits';
import { comboKey } from '@/data/character/descriptor';
import type { FatalityDress } from '@/components/scene/FatalityViewer/dress';

/** Texte officiel dans la langue de l'interface ; à défaut, le russe du client, signalé. */
export function officialText(text: FatalityText | undefined, lang: Lang): { text: string; official: boolean } | null {
  const own = text?.[lang];
  if (own) return { text: own, official: true };
  const other = text?.en ?? text?.fr ?? text?.ru;
  return other ? { text: other, official: false } : null;
}

/** Une entrée de la liste : aura de la garde-robe ou apparence à aura. */
export type AuraChoice = { kind: 'aura'; entry: AuraEntry } | { kind: 'appearance'; entry: AuraAppearance };

/**
 * Gabarits des exosquelettes du client (`MountExoskeleton`, `MountExo8`, `MountExo9`, `MEV*`) :
 * règle de `tools/extract_auras.py` pour les séparer des autres montures.
 */
export function isExoskeleton(vot: string | undefined): boolean {
  return !!vot && /^(MountExo|MEV)/.test(vot);
}

/**
 * Ligne de version : `15.0 (absente de la 11.0)`. Une version sans client lu juste avant est une
 * fourchette (« entre la 11.0 et la 15.0 ») ; la méthode `icon` (anciens clients 32 bits, repérée
 * par le fichier de son icône) est signalée.
 */
export function sinceParts(since: AuraSince | undefined): { version: string; previous?: string; client?: string; byIcon: boolean } | null {
  if (!since) return null;
  return { version: since.version, previous: since.previous, client: since.client, byIcon: since.method === 'icon' };
}

/** Habit de l'avatar : race et sexe de la création, classe et niveau de tenue choisis. */
export function avatarDress(data: ChargenData | null, base: string, race: string | null, sex: Sex, cls: string | null, tier: number): FatalityDress | null {
  if (!race) return null;
  const character = { race, sex } as FatalityCharacter;
  return dressFor(data, base, character, cls, tier);
}

/** Hauteur de l'avatar (m) d'après son gabarit de création, 1,9 m à défaut. */
export function avatarHeight(data: ChargenData | null, dress: FatalityDress | null): number {
  const h = dress ? data?.templates[dress.template]?.height : undefined;
  return typeof h === 'number' && h > 0 ? h : 1.9;
}

/** Races de la création dans l'ordre du client, avec les sexes qui ont un gabarit. */
export function avatarRaces(data: ChargenData | null): { race: string; sexes: Sex[] }[] {
  if (!data) return [];
  const order = data.raceOrder?.length ? data.raceOrder : Object.keys(data.races);
  return order.filter(r => data.races[r]).map(race => {
    const sexes = (['male', 'female'] as Sex[]).filter(sex => data.races[race].classes.some(cls => data.combos[comboKey(race, cls)]?.sexes[sex]));
    return { race, sexes };
  });
}
