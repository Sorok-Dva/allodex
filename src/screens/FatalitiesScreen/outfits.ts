/**
 * Habits des personnages des fatalités : la tenue de classe de la création de personnage
 * (`chargen.json`, `growths` : départ, intermédiaire, supérieur) portée par la victime et le
 * tueur. Fonctions pures, testées sans rendu.
 */
import type { ChargenData } from '@/data/character/chargen.types';
import { TRIO_RACES, comboKey } from '@/data/character/descriptor';
import type { FatalityDress } from '@/components/scene/FatalityViewer/dress';
import type { FatalityCharacter, FatalityEntry } from '@/lib/assets';

/** Niveaux de tenue (`growths`), du départ au supérieur ; libellés `Low`/`Medium`/`High` du client. */
export const TIERS = [0, 1, 2] as const;
export const TIER_TEXTS = ['Low', 'Medium', 'High'] as const;
/** Tenue par défaut : la plus spectaculaire. */
export const DEFAULT_TIER = 2;

/** Race de la création (`Kania`) d'une race des fatalités (`kania`). */
export function chargenRace(data: ChargenData, race: string): string | null {
  return Object.keys(data.races).find(r => r.toLowerCase() === race.toLowerCase()) ?? null;
}

/** Classes jouables d'une race des fatalités, dans l'ordre du client. */
export function classesOf(data: ChargenData | null, race: string): string[] {
  const r = data ? chargenRace(data, race) : null;
  return r ? data!.races[r].classes : [];
}

/** Classe d'une fatalité de classe (`warrior` → `WARRIOR`) ; l'Occultiste de la boutique est celle des occultistes. */
export function fatalityClass(data: ChargenData | null, fatality: FatalityEntry | undefined): string | null {
  const cls = fatality?.id.toUpperCase();
  return cls && data?.classes[cls] ? cls : null;
}

/**
 * Classe du tueur : celle de la fatalité si sa race peut la prendre (c'est lui qui la lance),
 * sinon la première classe de sa race.
 */
export function attackerClass(data: ChargenData | null, race: string, fatality: FatalityEntry | undefined): string | null {
  const classes = classesOf(data, race);
  const cls = fatalityClass(data, fatality);
  return cls && classes.includes(cls) ? cls : classes[0] ?? null;
}

/** Habit d'un personnage : gabarit de la création, objets du niveau choisi, trio des gibelins. */
export function dressFor(data: ChargenData | null, base: string, character: FatalityCharacter | undefined,
  cls: string | null, tier: number): FatalityDress | null {
  if (!data || !character || !cls) return null;
  const race = chargenRace(data, character.race);
  const entry = race ? data.combos[comboKey(race, cls)]?.sexes[character.sex] : undefined;
  if (!race || !entry) return null;
  return {
    data, base, template: entry.template, sex: character.sex, tier,
    items: entry.growths[tier]?.items ?? entry.growths[entry.growths.length - 1]?.items ?? [],
    trio: TRIO_RACES.has(race),
  };
}
