import { useState, type CSSProperties, type ReactNode } from 'react';
import type { AppearanceKey, ChargenData, GameText, UiLayer, UiLayout, UiWidget } from '@/data/character/chargen.types';
import { appearanceCounts, appearanceIndex, availableSexes, comboKey, petsFor, templateFor, TRIO_RACES,
  type CharacterDescriptor } from '@/data/character/descriptor';
import { byPriority, gameText, parseGameMarkup, placeWidget, type Rect, type TextLang } from '@/data/character/layout';
import { GameLayer } from './GameLayer';
import s from './ChargenUi.module.css';

export type Step = 'faction' | 'race' | 'custom';
export type Place = 'primary' | 'secondary' | 'tertiary' | 'pet';

export type ChargenUiProps = {
  data: ChargenData;
  layout: UiLayout;
  base: string;
  lang: TextLang;
  step: Step;
  descriptor: CharacterDescriptor;
  faction: string | null;
  equipment: number | null;
  helmet: boolean;
  place: Place;
  width: number;
  height: number;
  onFaction: (id: string) => void;
  onRace: (race: string) => void;
  onClass: (cls: string) => void;
  onSex: (sex: 'male' | 'female') => void;
  onEquipment: (level: number) => void;
  onToggleHelmet: () => void;
  onToggleArmor: () => void;
  onRandom: () => void;
  onShift: (key: AppearanceKey | 'petIndex', delta: number) => void;
  onName: (place: Place, name: string) => void;
  onPlace: (place: Place) => void;
  onBack: () => void;
  onNext: () => void;
  nameError?: string | null;
};

/** Plaques des races (`RacePlate01…08`) et des classes (`ClassPlate01…11`), dans l'ordre du script. */
const RACE_PLATES = ['RacePlate01', 'RacePlate02', 'RacePlate03', 'RacePlate04', 'RacePlate05', 'RacePlate06', 'RacePlate07', 'RacePlate08'];
/** Commandes d'apparence, ordre `variationOrder` de `ScriptCustomization`, et clé de libellé. */
export const CONTROLS: { key: AppearanceKey; label: string }[] = [
  { key: 'faces', label: 'ControlFaces' },
  { key: 'facials', label: 'ControlFacials' },
  { key: 'hairs', label: 'ControlHairs' },
  { key: 'hairColors', label: 'ControlHairColors' },
  { key: 'shoulderStones', label: 'ControlShoulderStones' },
  { key: 'additionals', label: 'ControlAdditionals' },
  { key: 'skins', label: 'ControlSkins' },
  { key: 'skinColors', label: 'ControlSkinColors' },
  { key: 'morphPresets', label: 'ControlMorphPresets' },
];
/**
 * Commandes que le serveur ferme (plage d'une seule valeur) : le script ne montre une commande que
 * si sa plage, envoyée par le serveur, compte plus d'une valeur ; l'écran du 17.0 (elfe) n'affiche ni
 * « Qualité de peau » (`skins`) ni « Caractéristiques additionnelles » (`additionals`).
 */
export const SERVER_LOCKED = new Set<AppearanceKey>(['skins', 'additionals']);
/** Hauteur par commande du panneau d'apparence et par plaque du panneau des noms (`SetPlacementPlain`). */
const APPEARANCE_ROW = 68;
const NAME_ROW = 130;
/** Emplacements des plaques de nom, remplis dans l'ordre des personnages montrés (`nameControls`). */
const NAME_SLOTS = ['primary01', 'secondary02', 'tertiary03', 'pet04'];

type Hover = { name: string; desc: string } | null;

/** Widgets cachés au départ que les scripts montrent : panneaux d'étape, lueurs des factions, bouton du familier. */
const SHOWN_BY_SCRIPT = /\/MainPanel\/(Factions|Customization)$|\/PanelFX$|\/pet04\/ButtonPet$/;

function Markup({ text }: { text: string }) {
  return (
    <>
      {parseGameMarkup(text).map((span, i) => span.br ? <br key={i} /> : <span key={i} className={span.cls ? s[span.cls] : undefined}>{span.text}</span>)}
    </>
  );
}

export function ChargenUi(props: ChargenUiProps) {
  const { data, layout, base, lang, step, descriptor: d } = props;
  const [hover, setHover] = useState<Hover>(null);
  const [pressed, setPressed] = useState<string | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const tx = (key: string) => gameText(data.texts[key] as GameText | null, lang);
  const url = (key: string | undefined) => {
    const file = key ? layout.textures[key]?.file : undefined;
    return file ? `${base}ui/${file}` : null;
  };
  const related = layout.related;
  const tpl = templateFor(data, d.race, d.class, d.sex);
  const pets = petsFor(data, d.race, d.class);
  const trio = TRIO_RACES.has(d.race);

  const layer = (l: UiLayer | undefined, key?: string) => l ? <GameLayer key={key} layer={l} url={url(l.texture)} /> : null;

  /** Bouton du jeu : calque de l'état courant (normal / survolé / appuyé / désactivé / sélectionné). */
  const button = (w: UiWidget, r: Rect, id: string, opts: {
    onClick?: () => void; disabled?: boolean; selected?: boolean; tip?: { name: string; desc: string }; children?: ReactNode; variant?: number;
  }) => {
    const variants = w.variants ?? [];
    const v = variants[Math.min(opts.variant ?? (opts.selected && variants.length > 1 ? 1 : 0), Math.max(variants.length - 1, 0))] ?? {};
    const isOver = over === id && !opts.disabled;
    const isDown = pressed === id && !opts.disabled;
    const state = opts.disabled ? (v.disabled ? 'disabled' : 'normal')
      : isDown ? (isOver && v.pressedHighlighted ? 'pressedHighlighted' : v.pressed ? 'pressed' : 'normal')
        : opts.selected && v.selected ? 'selected'
          : isOver && v.highlighted ? 'highlighted' : 'normal';
    // Variante imposée (indicateurs de progression) : son unique calque, quel que soit son état.
    const lay = v[state] ?? v.normal ?? (opts.selected ? v.selected : undefined)
      ?? (opts.variant !== undefined ? Object.values(v).find(l => l !== v.highlight) : undefined);
    const highlight = isOver ? v.highlight : undefined;
    return (
      <button
        key={id}
        type="button"
        className={`${s.widget} ${s.button}`}
        style={box(r)}
        disabled={opts.disabled}
        data-widget={id}
        aria-pressed={opts.selected}
        aria-label={opts.tip?.name ?? w.name ?? undefined}
        onPointerEnter={() => { setOver(id); if (opts.tip) setHover(opts.tip); }}
        onPointerLeave={() => { setOver(o => (o === id ? null : o)); setPressed(null); setHover(null); }}
        onPointerDown={() => setPressed(id)}
        onPointerUp={() => setPressed(null)}
        onClick={opts.disabled ? undefined : opts.onClick}
      >
        {layer(w.back)}
        {layer(lay)}
        {layer(highlight)}
        {opts.children}
      </button>
    );
  };

  const box = (r: Rect, extra?: CSSProperties): CSSProperties => ({ left: r.x, top: r.y, width: r.w, height: r.h, ...extra });

  /** Rendu générique d'un widget et de ses enfants ; `custom` intercepte les widgets à rôle. */
  const node = (w: UiWidget, pw: number, ph: number, path: string, custom: (w: UiWidget, r: Rect, path: string) => ReactNode | undefined): ReactNode => {
    const r = placeWidget(w, pw, ph);
    const id = `${path.replace(/#\d+$/, '')}/${w.name ?? `_${path.match(/#(\d+)$/)?.[1] ?? ''}`}`;
    // Widget caché au départ (octet de visibilité) : seuls les scripts le montrent — ici le
    // panneau de l'étape, rendu directement, et les lueurs de survol que `custom` pose.
    if (w.hidden && !SHOWN_BY_SCRIPT.test(id)) return null;
    const c = custom(w, r, id);
    if (c !== undefined) return c;
    if (w.type === 'TextView') return w.text ? text(r, id, <Markup text={gameText(w.text, lang)} />, s.static) : null;
    return plain(w, r, id, custom);
  };
  const plain = (w: UiWidget, r: Rect, id: string, custom: (w: UiWidget, r: Rect, path: string) => ReactNode | undefined) => (
    <div key={id} className={s.widget} style={box(r)} data-widget={id}>
      {layer(w.back)}
      {w.layers?.map((l, i) => layer(l, `layer${i}`))}
      {byPriority(w.children).map((child, i) => node(child, r.w, r.h, `${id}#${i}`, custom))}
    </div>
  );

  const text = (r: Rect, id: string, content: ReactNode, cls = '') => (
    <div key={id} className={`${s.widget} ${s.text} ${cls}`} style={box(r)} data-widget={id}>{content}</div>
  );

  // --- écrans ---------------------------------------------------------------------------------

  const main = layout.root.children?.find(c => c.name === 'MainPanel');
  if (!main) return null;
  const vw = props.width;
  const vh = props.height;
  const panelName = step === 'faction' ? 'Factions' : step === 'race' ? 'RaceClass' : 'Customization';

  const custom = (w: UiWidget, r: Rect, id: string): ReactNode | undefined => {
    const name = w.name ?? '';
    // Choix de la faction.
    if (/\/Faction(League|Empire)Panel\/Recommended$/.test(id)) return null;
    const fm = /\/Faction(League|Empire)Panel\/Button$/.exec(id);
    if (fm) {
      const fid = fm[1];
      return button(w, r, id, {
        selected: props.faction === fid, onClick: () => props.onFaction(fid),
        tip: { name: tx(fid), desc: tx(`${fid}Desc`) },
        children: props.faction === fid || over === id ? byPriority(w.children).map(ch => node(ch, r.w, r.h, id, () => undefined)) : null,
      });
    }
    if (/\/Factions\/BottomControlPanel\/Accept$/.test(id)) {
      return button(w, r, id, { disabled: !props.faction, onClick: props.onNext, tip: { name: tx('Next'), desc: tx('NextDesc') },
        children: over === id ? byPriority(w.children).map(ch => node(ch, r.w, r.h, id, () => undefined)) : null });
    }
    if (/\/BottomControlPanel\/Back$/.test(id)) {
      const desc = step === 'faction' ? tx('ExitDesc') : step === 'race' ? tx('BackToFactionsDesc') : tx('BackToRaceClassDesc');
      return button(w, r, id, { onClick: props.onBack, tip: { name: step === 'faction' ? tx('Exit') : tx('Back'), desc } });
    }
    // Description : montrée au survol d'une race, d'une classe ou d'un bouton (le script la vide
    // et la cache sinon) ; à l'étape des factions, celle de la faction choisie.
    if (/\/BottomControlPanel\/DescPanel$/.test(id) && !hover && step !== 'faction') return null;
    if (/\/BottomControlPanel\/DescPanel\/Text$/.test(id)) {
      const t = hover ?? defaultDesc();
      return text(r, id, <><div className={s.descTitle}>{t.name}</div><div className={s.descBody}><Markup text={t.desc} /></div></>, s.desc);
    }
    // Races.
    const rp = RACE_PLATES.indexOf(name);
    if (rp >= 0 && id.includes('/Race/')) {
      const race = data.raceOrder[rp];
      if (!race || !data.races[race]) return null;
      const info = data.races[race];
      const chosenFaction = props.faction;
      const locked = !!chosenFaction && info.faction !== chosenFaction && (info.faction === 'League' || info.faction === 'Empire');
      const selected = d.race === race;
      const buttonW = w.children?.find(c => c.name === 'Button');
      const iconW = w.children?.find(c => c.name === 'Icon');
      const labelW = w.children?.find(c => c.name === 'Label');
      const tip = { name: gameText(info.name, lang), desc: `<tip_golden>${tx(race)}</tip_golden><br/>${tx(`${race}Desc`)}${race === 'Aed' ? `<br/><br/><tip_grey>${tx('RaceAedForbidden')}</tip_grey>` : ''}` };
      return (
        <div key={id} className={`${s.widget} ${locked ? s.locked : ''}`} style={box(r)} data-widget={id}>
          {buttonW && button(buttonW, placeWidget(buttonW, r.w, r.h), `${id}/Button`, { selected, onClick: () => props.onRace(race), tip })}
          {iconW && <div className={s.widget} style={box(placeWidget(iconW, r.w, r.h), { backgroundImage: `url(${url(related.RaceIcons?.[race])})`, backgroundSize: '100% 100%', pointerEvents: 'none' })} />}
          {labelW && text(placeWidget(labelW, r.w, r.h), `${id}/Label`, gameText(info.name, lang), `${s.label} ${selected ? s.selectedLabel : ''}`)}
        </div>
      );
    }
    // Classes.
    const cm = /^ClassPlate(\d\d)$/.exec(name);
    if (cm) {
      const cls = data.classOrder[Number(cm[1]) - 1];
      if (!cls) return null;
      const available = data.races[d.race]?.classes.includes(cls) ?? false;
      const selected = d.class === cls;
      const buttonW = w.children?.find(c => c.name === 'Button');
      const iconW = w.children?.find(c => c.name === 'Icon');
      const labelW = w.children?.find(c => c.name === 'Label');
      const combo = data.combos[comboKey(d.race, cls)];
      const clsName = gameText(combo?.name ?? data.classes[cls]?.name, lang);
      const tip = available
        ? { name: clsName, desc: gameText(combo?.desc, lang) }
        : { name: tx('ClassNotAvailable'), desc: tx('ClassNotAvailableDesc') };
      const iconKey = cls.charAt(0) + cls.slice(1).toLowerCase();
      return (
        <div key={id} className={`${s.widget} ${available ? '' : s.locked}`} style={box(r)} data-widget={id}>
          {buttonW && button(buttonW, placeWidget(buttonW, r.w, r.h), `${id}/Button`, { selected, disabled: !available, onClick: () => props.onClass(cls), tip })}
          {iconW && <div className={s.widget} style={box(placeWidget(iconW, r.w, r.h), { backgroundImage: `url(${url(related.ClassIcons?.[iconKey])})`, backgroundSize: '100% 100%', pointerEvents: 'none' })} />}
          {labelW && text(placeWidget(labelW, r.w, r.h), `${id}/Label`, available ? clsName : gameText(data.classes[cls]?.label ?? data.classes[cls]?.name, lang), `${s.label} ${selected ? s.selectedLabel : ''}`)}
        </div>
      );
    }
    // Sexe.
    if (id.endsWith('/GenderPanel/Male') || id.endsWith('/GenderPanel/Female')) {
      const sex = name === 'Male' ? 'male' : 'female';
      const sexes = availableSexes(data, d.race, d.class);
      return button(w, r, id, { selected: d.sex === sex, disabled: !sexes.includes(sex), onClick: () => props.onSex(sex), tip: { name: tx(name), desc: '' } });
    }
    // Niveau de tenue.
    const vp = /\/VisualProgressPanel\/(Low01|Medium02|High03)$/.exec(id);
    if (vp) {
      const level = ['Low01', 'Medium02', 'High03'].indexOf(vp[1]);
      const key = ['Low', 'Medium', 'High'][level];
      return button(w, r, id, { selected: props.equipment === level, onClick: () => props.onEquipment(level), tip: { name: tx(key), desc: '' } });
    }
    if (/\/BottomControlPanel\/Helmet$/.test(id)) {
      return button(w, r, id, { variant: props.helmet ? 0 : 1, selected: !props.helmet, onClick: props.onToggleHelmet, tip: { name: tx('ToggleHelmet'), desc: tx('ToggleHelmetDesc') } });
    }
    if (/\/BottomControlPanel\/Armor$/.test(id)) {
      return button(w, r, id, { variant: props.equipment === null ? 1 : 0, selected: props.equipment === null, onClick: props.onToggleArmor, tip: { name: tx('ToggleArmor'), desc: tx('ToggleArmorDesc') } });
    }
    if (/\/BottomControlPanel\/Random$/.test(id)) {
      return button(w, r, id, { onClick: props.onRandom, tip: { name: tx('Random'), desc: tx('RandomDesc') } });
    }
    if (/\/RaceClass\/BottomControlPanel\/Complite$/.test(id)) return null;
    if (/\/RaceClass\/BottomControlPanel\/Accept$/.test(id)) {
      return button(w, r, id, { onClick: props.onNext, tip: { name: tx('Next'), desc: tx('NextDesc') } });
    }
    if (/\/Customization\/BottomControlPanel\/Accept$/.test(id)) {
      return button(w, r, id, { onClick: props.onNext, tip: { name: tx('CreateAvatar'), desc: tx('CreateAvatarDesc') } });
    }
    // Plaques de nom : le script remplit les emplacements dans l'ordre des personnages montrés
    // (principal, compagnons du trio, familier) et donne au panneau (1 + n) × 130 px de haut.
    if (id.endsWith('/Customization/Name')) {
      const places: Place[] = ['primary', ...(trio ? ['secondary', 'tertiary'] as Place[] : []), ...(pets.length ? ['pet'] as Place[] : [])];
      const placed = placeWidget({ place: { x: w.place.x, y: { ...w.place.y, size: (1 + places.length) * NAME_ROW } } }, pr(id).w, pr(id).h);
      return (
        <div key={id} className={s.widget} style={box(placed)} data-widget={id}>
          {places.map((place, k) => {
            const slot = w.children?.find(c => c.name === NAME_SLOTS[k]);
            return slot ? namePlate(slot, placeWidget(slot, placed.w, placed.h), `${id}/${NAME_SLOTS[k]}`, place) : null;
          })}
        </div>
      );
    }
    // Panneau d'apparence : n × 68 px de haut, centré (−50) ; les plaques restent à 72 px d'écart.
    if (id.endsWith('/Customization/Appearance')) {
      const n = appearanceControls().length;
      const placed = placeWidget({ place: { x: w.place.x, y: { ...w.place.y, size: n * APPEARANCE_ROW } } }, pr(id).w, pr(id).h);
      return plain(w, placed, id, custom);
    }
    // Plaques d'apparence.
    const ap = /^AppearancePlate(\d\d)$/.exec(name);
    if (ap) return appearancePlate(w, r, id, Number(ap[1]) - 1);
    return undefined;
  };

  function defaultDesc(): { name: string; desc: string } {
    if (step === 'faction') {
      if (props.faction) return { name: tx(props.faction), desc: tx(`${props.faction}Desc`) };
      return { name: tx('Choice'), desc: tx('ChoiceDesc') };
    }
    const combo = data.combos[comboKey(d.race, d.class)];
    return { name: `${gameText(data.races[d.race]?.name, lang)} — ${gameText(combo?.name, lang)}`, desc: gameText(combo?.desc, lang) };
  }

  function namePlate(w: UiWidget, r: Rect, id: string, place: Place) {
    const active = props.place === place;
    const children = w.children ?? [];
    const frame = children.find(c => c.name === 'Frame');
    const btn = children.find(c => c.name === (place === 'pet' ? 'ButtonPet' : 'Button'));
    const arrow = children.find(c => c.name === 'Arrow');
    const who = place === 'primary' ? d : place === 'pet' ? d.pet : d.companions?.[place];
    const value = who?.name ?? '';
    const sex = place === 'pet' ? null : place === 'primary' ? d.sex : d.companions?.[place]?.sex;
    const tip = { name: place === 'pet' ? tx('SelectPetForEdit') : tx('SelectCharacterForEdit'), desc: tx('SelectCharacterForEditDesc') };
    return (
      <div key={id} className={s.widget} style={box(r)} data-widget={id}>
        {frame && (() => {
          const fr = placeWidget(frame, r.w, r.h);
          const gender = frame.children?.find(c => c.name === 'Gender');
          const edit = frame.children?.find(c => c.name === 'EditlineFrame');
          return (
            <div className={s.widget} style={box(fr)}>
              {layer(frame.back)}
              {gender && sex && <div className={s.widget} style={box(placeWidget(gender, fr.w, fr.h), { backgroundImage: `url(${url(related.Common?.[sex === 'male' ? 'Male' : 'Female'])})`, backgroundSize: '100% 100%' })} />}
              {edit && (() => {
                const er = placeWidget(edit, fr.w, fr.h);
                const line = edit.children?.[0];
                const lr = line ? placeWidget(line, er.w, er.h) : { x: 8, y: 4, w: er.w - 16, h: er.h - 8 };
                return (
                  <div className={s.widget} style={box(er)}>
                    {layer(edit.back)}
                    <input
                      className={`${s.editline} ${props.nameError && active ? s.editError : ''}`}
                      style={box(lr)}
                      value={value}
                      maxLength={16}
                      spellCheck={false}
                      aria-label={tip.name}
                      data-place={place}
                      onFocus={() => props.onPlace(place)}
                      onChange={e => props.onName(place, e.target.value)}
                    />
                  </div>
                );
              })()}
            </div>
          );
        })()}
        {btn && button(btn, placeWidget(btn, r.w, r.h), `${id}/${btn.name}`, { selected: active, onClick: () => props.onPlace(place), tip })}
        {arrow && active && <div className={s.widget} style={box(placeWidget(arrow, r.w, r.h))}>{layer(arrow.back)}</div>}
      </div>
    );
  }

  function appearanceControls(): { key: AppearanceKey | 'petIndex'; label: string; count: number; index: number }[] {
    if (props.place === 'pet') {
      const petTpl = d.pet ? data.pets[d.pet.template] : undefined;
      const out = [];
      if (pets.length > 1) out.push({ key: 'petIndex' as const, label: 'ControlPetIndex', count: pets.length, index: Math.max(0, pets.indexOf(d.pet?.template ?? '')) });
      const colors = petTpl?.variations?.faces?.length ?? 0;
      if (colors) out.push({ key: 'faces' as const, label: 'ControlPetFaces', count: colors, index: d.pet?.color ?? 0 });
      return out;
    }
    const sex = props.place === 'primary' ? d.sex : d.companions?.[props.place as 'secondary' | 'tertiary']?.sex ?? d.sex;
    const t = templateFor(data, d.race, d.class, sex) ?? tpl;
    const appearance = props.place === 'primary' ? d.appearance : d.companions?.[props.place as 'secondary' | 'tertiary']?.appearance ?? {};
    const counts = appearanceCounts(t);
    const race = d.race;
    return CONTROLS.filter(c => counts[c.key] > 1 && !SERVER_LOCKED.has(c.key) && !(race === 'Aed' && c.key === 'hairColors')).map(c => ({ key: c.key, label: c.label, count: counts[c.key], index: appearanceIndex(t, appearance, c.key) }));
  }

  function appearancePlate(w: UiWidget, r: Rect, id: string, k: number) {
    const control = appearanceControls()[k];
    if (!control) return null;
    const children = w.children ?? [];
    const label = children.find(c => c.name === 'Label');
    const orb = children.find(c => c.name === 'Orb');
    const next = children.find(c => c.name === 'Next');
    const prev = children.find(c => c.name === 'Previous');
    const single = control.count < 2;
    return (
      <div key={id} className={s.widget} style={box(r)} data-widget={id} data-control={control.key}>
        {layer(w.back)}
        {label && text(placeWidget(label, r.w, r.h), `${id}/Label`, tx(control.label), s.plateLabel)}
        {orb && (() => {
          const or = placeWidget(orb, r.w, r.h);
          const value = orb.children?.[0];
          return (
            <div className={s.widget} style={box(or)}>
              {layer(orb.back)}
              {orb.layers?.map((l, i) => layer(l, `layer${i}`))}
              {value && text(placeWidget(value, or.w, or.h), `${id}/Value`, `${control.index + 1}`, s.orbValue)}
            </div>
          );
        })()}
        {prev && button(prev, placeWidget(prev, r.w, r.h), `${id}/Previous`, { disabled: single, onClick: () => props.onShift(control.key, -1) })}
        {next && button(next, placeWidget(next, r.w, r.h), `${id}/Next`, { disabled: single, onClick: () => props.onShift(control.key, 1) })}
      </div>
    );
  }

  const panel = main.children?.find(c => c.name === panelName);
  // Taille du parent d'un widget du panneau d'étape (plein écran : les panneaux sont étirés).
  function pr(_id: string) { return { w: vw, h: vh }; }
  return (
    <div className={s.root} style={{ width: vw, height: vh }} data-step={step}>
      {/* Bandeau bas des écrans du menu (addon `Main`), sous les boutons de l'étape. */}
      {step !== 'faction' && layout.bottomLine && node(layout.bottomLine, vw, vh, '/Main', () => undefined)}
      {panel && node(panel, vw, vh, '/MainPanel', custom)}
      {step === 'custom' && hover && (
        <div className={s.tooltip}><div className={s.descTitle}>{hover.name}</div>{hover.desc && <div className={s.descBody}><Markup text={hover.desc} /></div>}</div>
      )}
      {step === 'custom' && props.nameError && <div className={s.nameError}>{props.nameError}</div>}
    </div>
  );
}
