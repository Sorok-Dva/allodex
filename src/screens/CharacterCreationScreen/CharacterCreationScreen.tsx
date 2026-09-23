import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { AppearanceKey, ChargenData, UiLayout } from '@/data/character/chargen.types';
import {
  checkName, comboKey, newDescriptor, randomAppearance, shiftAppearance, templateFor, validateDescriptor, withSelection,
  type CharacterDescriptor,
} from '@/data/character/descriptor';
import { uiScale, type TextLang } from '@/data/character/layout';
import { LocalCharacterStore, downloadBlob, downloadDescriptor, type CharacterStore } from '@/data/character/store';
import { navigate } from '@/lib/router';
import { useI18n } from '@/lib/i18n';
import { hasWebGL } from '@/lib/webgl';
import type { ChargenViewerHandle } from '@/components/scene/CharacterCreation/ChargenViewer';
import { ChargenUi, type Place, type Step } from './ChargenUi';
import s from './CharacterCreationScreen.module.css';

// `three` n'est chargé que sur cet écran.
const ChargenViewer = lazy(() => import('@/components/scene/CharacterCreation/ChargenViewer'));

export const CHARGEN_BASE = '/game/character/';

function useViewport() {
  const [size, setSize] = useState({ w: window.innerWidth, h: window.innerHeight });
  useEffect(() => {
    const on = () => setSize({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener('resize', on);
    return () => window.removeEventListener('resize', on);
  }, []);
  return size;
}

/**
 * Écran de création de personnage du client 17 (mode développement seulement) : trois
 * étapes du jeu — faction, race et classe, apparence et nom — sur le décor 3D de la race.
 * Le résultat est un descripteur versionné (`CharacterDescriptor`), enregistré par un
 * `CharacterStore` (navigateur aujourd'hui, serveur demain) et exportable en `.glb`.
 */
export function CharacterCreationScreen({ store: storeProp }: { store?: CharacterStore } = {}) {
  const { t, lang } = useI18n();
  const store = useMemo(() => storeProp ?? new LocalCharacterStore(), [storeProp]);
  const [data, setData] = useState<ChargenData | null>(null);
  const [layout, setLayout] = useState<UiLayout | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState<Step>('faction');
  const [faction, setFaction] = useState<string | null>(null);
  const [descriptor, setDescriptor] = useState<CharacterDescriptor | null>(null);
  const [equipment, setEquipment] = useState<number | null>(0);
  const [helmet, setHelmet] = useState(true);
  const [place, setPlace] = useState<Place>('primary');
  const [textLang, setTextLang] = useState<TextLang>(lang);
  const [nameError, setNameError] = useState<string | null>(null);
  const [saved, setSaved] = useState<{ id: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const viewer = useRef<ChargenViewerHandle>(null);
  const music = useRef<HTMLAudioElement>(null);
  const [muted, setMuted] = useState(false);
  // Musique du menu 17.0 (celle qui accompagne la création dans le client), lancée au premier
  // geste : les navigateurs refusent le son avant une interaction.
  useEffect(() => {
    const start = () => { void music.current?.play().catch(() => undefined); };
    window.addEventListener('pointerdown', start, { once: true });
    return () => window.removeEventListener('pointerdown', start);
  }, []);
  useEffect(() => { if (music.current) music.current.muted = muted; }, [muted]);
  const { w, h } = useViewport();

  useEffect(() => { document.title = `Allodex — ${t('character.title')}`; }, [t]);
  useEffect(() => { setTextLang(lang); }, [lang]);
  useEffect(() => {
    let alive = true;
    Promise.all([
      fetch(`${CHARGEN_BASE}chargen.json`).then(r => { if (!r.ok) throw new Error(String(r.status)); return r.json() as Promise<ChargenData>; }),
      fetch(`${CHARGEN_BASE}ui/layout.json`).then(r => { if (!r.ok) throw new Error(String(r.status)); return r.json() as Promise<UiLayout>; }),
    ]).then(([d, l]) => {
      if (!alive) return;
      setData(d);
      setLayout(l);
      let first = newDescriptor(d, d.raceOrder[0]);
      // Développement : `?race=Elf&class=MAGE&sex=female&step=race` ouvre une étape donnée
      // (captures comparées aux écrans du jeu).
      if (import.meta.env.DEV) {
        const q = new URLSearchParams(window.location.search);
        const race = q.get('race');
        if (race && d.races[race]) {
          first = newDescriptor(d, race);
          setFaction(d.races[race].faction === 'League' || d.races[race].faction === 'Empire' ? d.races[race].faction : null);
        }
        const cls = q.get('class');
        if (cls) first = withSelection(d, first, { class: cls });
        const sex = q.get('sex');
        if (sex === 'male' || sex === 'female') first = withSelection(d, first, { sex });
        const at = q.get('step');
        if (at === 'race' || at === 'custom') setStep(at);
      }
      setDescriptor(first);
    }).catch(() => { if (alive) setError('missing'); });
    return () => { alive = false; };
  }, []);

  const update = useCallback((fn: (d: CharacterDescriptor) => CharacterDescriptor) => {
    setDescriptor(prev => (prev ? fn(prev) : prev));
  }, []);

  if (error || (data && !layout)) {
    return (
      <div className={s.missing}>
        <p>{t('character.missing')}</p>
        <code>python3 tools/extract_character_creation.py</code>
        <button type="button" onClick={() => navigate('/')}>{t('character.home')}</button>
      </div>
    );
  }
  if (!data || !layout || !descriptor) return <div className={s.loading}>{t('character.loading')}</div>;

  const scale = uiScale(w, h);
  const vw = w / scale;
  const vh = h / scale;
  const d = descriptor;

  // Sons de l'interface du jeu (sélection de faction et de classe, réplique de la combinaison).
  const play = (key: string, delay = 0) => {
    const file = data.sounds?.[key];
    if (!file || muted) return;
    const audio = new Audio();
    audio.src = `${CHARGEN_BASE}${file}.${audio.canPlayType?.('audio/ogg') ? 'ogg' : 'mp3'}`;
    audio.volume = 0.8;
    window.setTimeout(() => { void audio.play().catch(() => undefined); }, delay);
  };
  const onFaction = (id: string) => {
    play('faction');
    setFaction(id);
    const first = data.factions.find(f => f.id === id)?.races[0];
    if (first && data.races[d.race]?.faction !== id) setDescriptor(newDescriptor(data, first));
  };
  const onNext = async () => {
    if (step === 'faction') { setStep('race'); return; }
    if (step === 'race') { setStep('custom'); setPlace('primary'); return; }
    const check = checkName(data, d.name);
    if (!check.ok) { setNameError(t(`character.name.${check.reason ?? 'empty'}` as never)); setPlace('primary'); return; }
    const errors = validateDescriptor(data, d);
    if (errors.length) { setNameError(errors.map(e => `${e.path} : ${e.message}`).join(' ; ')); return; }
    setNameError(null);
    const entry = await store.save(d);
    setSaved({ id: entry.id });
  };
  const onBack = () => {
    if (step === 'custom') setStep('race');
    else if (step === 'race') setStep('faction');
    else navigate('/');
  };
  const onShift = (key: AppearanceKey | 'petIndex', delta: number) => {
    update(prev => {
      if (place === 'pet' && prev.pet) {
        if (key === 'petIndex') {
          const pets = data.races[prev.race]?.pets ?? [];
          const i = (pets.indexOf(prev.pet.template) + delta + pets.length) % pets.length;
          return { ...prev, pet: { ...prev.pet, template: pets[i], color: 0 } };
        }
        const n = data.pets[prev.pet.template]?.variations?.faces?.length ?? 1;
        return { ...prev, pet: { ...prev.pet, color: (prev.pet.color + delta + n) % n } };
      }
      if (key === 'petIndex' || place === 'pet') return prev;
      if (place === 'primary') return { ...prev, appearance: shiftAppearance(templateFor(data, prev.race, prev.class, prev.sex), prev.appearance, key, delta) };
      const c = prev.companions?.[place];
      if (!c) return prev;
      const tpl = templateFor(data, prev.race, prev.class, c.sex);
      return { ...prev, companions: { ...prev.companions, [place]: { ...c, appearance: shiftAppearance(tpl, c.appearance, key, delta) } } };
    });
  };
  const onRandom = () => {
    update(prev => {
      if (place === 'pet' && prev.pet) {
        const n = data.pets[prev.pet.template]?.variations?.faces?.length ?? 1;
        return { ...prev, pet: { ...prev.pet, color: Math.floor(Math.random() * n) } };
      }
      if (place === 'pet') return prev;
      if (place === 'primary') return { ...prev, appearance: randomAppearance(templateFor(data, prev.race, prev.class, prev.sex)) };
      const c = prev.companions?.[place];
      if (!c) return prev;
      return { ...prev, companions: { ...prev.companions, [place]: { ...c, appearance: randomAppearance(templateFor(data, prev.race, prev.class, c.sex)) } } };
    });
  };
  const onName = (p: Place, name: string) => {
    setNameError(null);
    update(prev => {
      if (p === 'primary') return { ...prev, name };
      if (p === 'pet') return prev.pet ? { ...prev, pet: { ...prev.pet, name } } : prev;
      const c = prev.companions?.[p];
      return c ? { ...prev, companions: { ...prev.companions, [p]: { ...c, name } } } : prev;
    });
  };
  const onSex = (sex: 'male' | 'female') => {
    if (place === 'secondary' || place === 'tertiary') {
      update(prev => {
        const c = prev.companions?.[place];
        if (!c) return prev;
        return { ...prev, companions: { ...prev.companions, [place]: { ...c, sex, appearance: {} } } };
      });
      return;
    }
    update(prev => withSelection(data, prev, { sex }));
  };
  const exportGlb = async () => {
    if (!viewer.current) return;
    setBusy('glb');
    try {
      const blob = await viewer.current.exportGlb();
      downloadBlob(blob, `${d.name || d.race}.glb`);
    } catch (e) {
      setNameError(String(e));
    } finally {
      setBusy(null);
    }
  };
  const webgl = hasWebGL();
  const combo = data.combos[comboKey(d.race, d.class)];

  return (
    <div className={s.screen} data-step={step} data-race={d.race} data-class={d.class} data-sex={d.sex}>
      <audio ref={music} src="/game/archive/17.0/theme.ogg" loop preload="none" />
      {step === 'faction' && (
        <video className={s.backdrop} src="/game/archive/17.0/menu.webm" autoPlay muted loop playsInline />
      )}
      {webgl && (
        <Suspense fallback={null}>
          <ChargenViewer
            ref={viewer}
            data={data}
            base={CHARGEN_BASE}
            descriptor={d}
            step={step}
            equipment={equipment}
            helmet={helmet}
            focus={place}
            muted={muted}
            className={step === 'faction' ? s.hidden : s.viewer}
            onError={message => console.error('chargen viewer:', message)}
          />
        </Suspense>
      )}
      <div className={s.ui} style={{ transform: `scale(${scale})`, width: vw, height: vh }}>
        <ChargenUi
          data={data} layout={layout} base={CHARGEN_BASE} lang={textLang} step={step} descriptor={d}
          faction={faction} equipment={equipment} helmet={helmet} place={place} width={vw} height={vh}
          onFaction={onFaction}
          onRace={race => { setDescriptor(prev => (prev ? withSelection(data, prev, { race }) : prev)); setFaction(data.races[race]?.faction === 'League' || data.races[race]?.faction === 'Empire' ? data.races[race].faction : faction); }}
          onClass={cls => { play(`class:${cls}`); play(`voice:${d.race}/${cls}`, 450); update(prev => withSelection(data, prev, { class: cls })); }}
          onSex={onSex}
          onEquipment={level => setEquipment(level)}
          onToggleHelmet={() => setHelmet(v => !v)}
          onToggleArmor={() => setEquipment(v => (v === null ? 0 : null))}
          onRandom={onRandom}
          onShift={onShift}
          onName={onName}
          onPlace={setPlace}
          onBack={onBack}
          onNext={() => { void onNext(); }}
          nameError={nameError}
        />
      </div>
      <div className={s.toolbar} role="toolbar" aria-label={t('character.tools')}>
        <span className={s.badge}>{t('character.devOnly')}</span>
        <label className={s.langPick}>
          {t('character.textLang')}
          <select value={textLang} onChange={e => setTextLang(e.target.value as TextLang)}>
            <option value="fr">FR</option>
            <option value="en">EN</option>
            <option value="ru">RU</option>
          </select>
        </label>
        {step !== 'faction' && <button type="button" onClick={() => { void exportGlb(); }} disabled={!!busy}>{busy === 'glb' ? t('character.exporting') : t('character.exportGlb')}</button>}
        <button type="button" onClick={() => downloadDescriptor(d)}>{t('character.downloadJson')}</button>
        <button type="button" aria-pressed={muted} onClick={() => setMuted(m => !m)}>{muted ? t('character.unmute') : t('character.mute')}</button>
        <button type="button" onClick={() => navigate('/')}>{t('character.home')}</button>
      </div>
      {saved && (
        <div className={s.dialog} role="dialog" aria-modal="true" aria-label={t('character.saved')}>
          <h2>{t('character.saved')}</h2>
          <p>{d.name} — {combo?.name?.[textLang === 'ru' ? 'ru' : textLang] ?? combo?.name?.en ?? d.class}</p>
          <p className={s.note}>{t('character.savedHint')}</p>
          <div className={s.dialogButtons}>
            <button type="button" onClick={() => { void exportGlb(); }}>{t('character.exportGlb')}</button>
            <button type="button" onClick={() => downloadDescriptor(d)}>{t('character.downloadJson')}</button>
            <button type="button" onClick={() => { setSaved(null); setStep('faction'); setFaction(null); setDescriptor(newDescriptor(data, data.raceOrder[0])); }}>{t('character.again')}</button>
            <button type="button" onClick={() => setSaved(null)}>{t('character.close')}</button>
          </div>
        </div>
      )}
    </div>
  );
}

export default CharacterCreationScreen;
