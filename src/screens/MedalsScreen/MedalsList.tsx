import type { MedalFilter } from '@/data/medals.types';
import { T, tex } from '@/lib/assets';
import type { MedalsState } from './useMedalsState';
import { MedalEntry } from './MedalEntry';
import s from './MedalsList.module.css';

const FILTERS: { value: MedalFilter; label: string }[] = [
  { value: 'all', label: 'Tout' }, { value: 'completed', label: 'Terminés' }, { value: 'inProgress', label: 'En cours' },
];

export function MedalsList({ state }: { state: MedalsState }) {
  return (
    <section className={s.content} style={{ backgroundImage: `url(${tex(`${T.medals}/FrameContent02`)})` }}>
      <header className={s.header} style={{ backgroundImage: `url(${tex(`${T.medals}/MedalHeader`)})` }}>
        <h2 className={s.title}>{state.title}</h2>
        <label className={s.filter}>
          <select value={state.filter} onChange={e => state.setFilter(e.target.value as MedalFilter)}>
            {FILTERS.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
          </select>
        </label>
      </header>
      <div className={s.list}>
        {state.visible.length === 0 && <p className={s.empty}>Aucun succès.</p>}
        {state.visible.map(m => <MedalEntry key={m.id} medal={m} />)}
      </div>
    </section>
  );
}
