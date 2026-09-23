/**
 * Apparence résolue d'un personnage : quels géosets montrer, quelles textures leur poser,
 * quels modèles accrocher, et la pile de la texture cuite. Règles du client (relevées sur les
 * `VisualItem` du 17 et leurs `.xdb` 7.0) :
 *
 * * la tenue par défaut du gabarit (`defaultDress`) cache tous les géosets à variantes
 *   (visages, coiffures, traits, robes, capes…) ; ce qui reste est le corps nu ;
 * * chaque objet porté (variations d'apparence, puis tenue de classe) **montre** ses formes
 *   (`shapeName` → géoset, éventuellement avec une texture de remplacement) et **cache** ses
 *   géosets (`hiddenGeosets`) ; un géoset caché par un objet l'emporte sur un géoset montré ;
 * * un géoset sans texture (emplacements de jupe ou de cape) n'est dessiné que si un objet lui
 *   en apporte une ;
 * * les formes à `locator` accrochent un modèle (casque, épaulière, arme) à l'articulation ;
 *   un modèle qui porte un élément par gabarit (casques) n'en montre que celui du gabarit ;
 * * la couleur de cheveux teint les géosets `hairColoredGeosets` et le cuir chevelu cuit ;
 * * main secondaire : l'objet de l'emplacement `OFFHAND` se tient dans la main **gauche** bien que sa
 *   forme vise `Slot_Hand_R` (orbe du mage elfe dans la main levée sur l'écran du 17.0), et l'arme à
 *   distance (`RANGED`, baguette du mage) n'est pas tenue à l'écran de création.
 */
import type { AppearanceKey, ChargenData, ChargenItem, ChargenTemplate, Sex, SexKey } from './chargen.types';
import { appearanceIndex, type Appearance } from './descriptor';

export type BakeSpec = { texture: string; rect?: [number, number, number, number]; tint?: string; throughAlpha?: boolean };
export type Attachment = { model: string; locator: string; template: string };
/** Effet d'un objet porté (`fx/…glb`) à accrocher au même locator. */
export type FxAttachment = { fx: string; locator: string };

/** Échelle locale d'un os (corpulence), produit des commandes qui le touchent. */
export type MorphScale = { bone: string; scale: [number, number, number] };

export type Look = {
  visible: Set<string>;
  textures: Record<string, string>;
  colors: Record<string, string>;
  attachments: Attachment[];
  bake: BakeSpec[];
  morph: MorphScale[];
  fx: FxAttachment[];
};

/** Corpulence : chaque os touché prend `valeur ** puissance` sur chaque axe, commandes multipliées. */
export function morphScales(tpl: ChargenTemplate, preset: Record<string, number> | undefined): MorphScale[] {
  const out = new Map<string, [number, number, number]>();
  if (!preset || !tpl.morph) return [];
  for (const [control, value] of Object.entries(preset)) {
    if (!(value > 0) || value === 1) continue;
    for (const { bone, power } of tpl.morph[control] ?? []) {
      const s = out.get(bone) ?? [1, 1, 1];
      out.set(bone, [s[0] * value ** power[0], s[1] * value ** power[1], s[2] * value ** power[2]]);
    }
  }
  return [...out].map(([bone, scale]) => ({ bone, scale }));
}

export type LookOptions = {
  /** Tenue portée : indice de `growths` (0, 1, 2) ou `null` (bouton « Надеть/снять предметы »). */
  equipment: number | null;
  helmet: boolean;
};

const ORDER_OF_SLOTS = ['SHIRT', 'PANTS', 'BOOTS', 'BRACERS', 'GLOVES', 'ARMOR', 'BELT', 'CLOAK', 'MANTLE', 'HELM',
  'MAINHAND', 'OFFHAND', 'RANGED'];

function lists<T>(record: Partial<Record<SexKey, T[]>> | undefined, sex: Sex): T[] {
  if (!record) return [];
  return [...(record.unisex ?? []), ...(record[sex] ?? [])];
}

type Worn = { item: ChargenItem; tint?: string; slot?: string };

/** `Slot_Hand_R` ↔ `Slot_Hand_L` (et tout suffixe `_R`/`_L`). */
export function otherHand(locator: string): string {
  return locator.replace(/_R$/, '_#').replace(/_L$/, '_R').replace(/_#$/, '_L');
}

export function resolveLook(data: ChargenData, templateName: string, tpl: ChargenTemplate, sex: Sex,
  appearance: Appearance, growthItems: { slot: string; item: string }[], options: LookOptions,
  /** Géosets qui ont une texture propre dans le modèle (tous si absent). */
  textured?: Set<string>): Look {
  const elements = tpl.elements ?? [];
  const v = tpl.variations ?? {};
  const pick = (key: AppearanceKey): number => appearanceIndex(tpl, appearance, key);
  const hairColor = v.hairColors?.length ? v.hairColors[pick('hairColors')] : undefined;
  const skinColor = v.skinColors?.length ? v.skinColors[pick('skinColors')] : undefined;
  const stoneColor = v.shoulderStoneColors?.length ? v.shoulderStoneColors[pick('shoulderStoneColors')] : undefined;

  const worn: Worn[] = [];
  const add = (id: string | null | undefined, tint?: string, slot?: string) => {
    const item = id ? data.items[id] : undefined;
    if (item) worn.push({ item, tint, slot });
  };
  // Variations d'apparence, dans l'ordre de cuisson du client (visage, pilosité, signe
  // additionnel, coiffure — `Variation.items` de `tools/allods_characters.py`), puis pierres.
  if (v.faces?.length) add(v.faces[pick('faces')]);
  if (v.facials?.length) add(v.facials[pick('facials')]);
  if (v.additionals?.length) add(v.additionals[pick('additionals')]);
  if (v.hairs?.length) add(v.hairs[pick('hairs')], hairColor);
  if (v.shoulderStones?.length) add(v.shoulderStones[pick('shoulderStones')], stoneColor);
  // Tenue de classe.
  const dressed = options.equipment === null ? [] : [...growthItems]
    .filter(g => options.helmet || g.slot !== 'HELM')
    .sort((a, b) => (ORDER_OF_SLOTS.indexOf(a.slot) + 99) % 99 - (ORDER_OF_SLOTS.indexOf(b.slot) + 99) % 99);
  const underwearHidden = dressed.some(g => (data.items[g.item]?.underwear ?? 0) > 0);
  if (!underwearHidden) add(tpl.underwear);
  for (const g of dressed) add(g.item, undefined, g.slot);

  const defaults = tpl.defaultDress ? data.items[tpl.defaultDress] : undefined;
  const defaultHidden = new Set(lists(defaults?.hidden, sex));
  const shown = new Set<string>();
  const hidden = new Set<string>();
  const textures: Record<string, string> = {};
  const colors: Record<string, string> = {};
  const attachments: Attachment[] = [];
  const fx: FxAttachment[] = [];
  for (const shape of lists(defaults?.shapes, sex)) {
    if (shape.model) attachments.push({ model: shape.model, locator: shape.locator ?? '', template: templateName });
  }
  for (const { item, tint, slot } of worn) {
    for (const shape of lists(item.shapes, sex)) {
      if (shape.model && slot === 'RANGED') continue;
      if (shape.geoset) {
        shown.add(shape.geoset);
        if (shape.texture) textures[shape.geoset] = shape.texture;
        if (shape.color) colors[shape.geoset] = shape.color;
        if (tint) colors[shape.geoset] = tint;
      }
      const locator = slot === 'OFFHAND' ? otherHand(shape.locator ?? '') : shape.locator ?? '';
      if (shape.model) attachments.push({ model: shape.model, locator, template: templateName });
      if (shape.fx && !fx.some(f => f.fx === shape.fx && f.locator === locator)) fx.push({ fx: shape.fx, locator });
    }
    for (const g of lists(item.hidden, sex)) hidden.add(g);
  }
  const hasTexture = textured ?? new Set(elements);
  const visible = new Set<string>();
  for (const e of elements) {
    if (hidden.has(e)) continue;
    const textured = hasTexture.has(e) || e in textures;
    if (shown.has(e) ? textured : !defaultHidden.has(e) && textured) visible.add(e);
  }
  if (hairColor) for (const g of tpl.hairColored ?? []) if (!(g in colors)) colors[g] = hairColor;

  // Texture cuite : peau (teinte à travers l'alpha), puis les patchs dans l'ordre des objets.
  const bake: BakeSpec[] = [];
  const skin = v.skins?.length ? v.skins[pick('skins')] : null;
  if (skin) bake.push({ texture: skin, tint: skinColor, throughAlpha: true });
  else if (tpl.baked) bake.push({ texture: tpl.baked });
  for (const { item, tint } of worn) {
    for (const p of lists(item.patches, sex)) bake.push({ texture: p.texture, rect: p.rect, tint });
  }
  const morph = morphScales(tpl, v.morphPresets?.length ? v.morphPresets[pick('morphPresets')] : undefined);
  return { visible, textures, colors, attachments, bake, morph, fx };
}
