import { useRef } from 'react';
import type { MedalFilter } from '@/data/medals.types';
import { FILTER_LABELS } from '@/data/medals.logic';
import { sprite } from '@/lib/assets';
import { GameDropdown } from '@/components/game/GameDropdown';
import { GameScrollbar } from '@/components/game/GameScrollbar';
import type { MedalsState } from './useMedalsState';
import { MedalEntry } from './MedalEntry';
import s from './MedalsList.module.css';

const FILTERS: { value: MedalFilter; label: string }[] = [
  { value: 'all', label: FILTER_LABELS.all },
  { value: 'completed', label: FILTER_LABELS.completed },
  { value: 'inProgress', label: FILTER_LABELS.inProgress },
];

export function MedalsList({ state }: { state: MedalsState }) {
  const listRef = useRef<HTMLDivElement>(null);

  return (
    <div className={s.content}>
      <header className={s.header} style={{ backgroundImage: `url(${sprite('content-header')})` }}>
        <h2 className={s.title}>{state.title}</h2>
        <GameDropdown
          className={s.filter}
          value={state.filter}
          options={FILTERS}
          onChange={state.setFilter}
          label="Filtrer les succès"
        />
      </header>

      <div className={s.viewport} ref={listRef}>
        {state.visible.length === 0
          ? <p className={s.empty}>Aucun succès.</p>
          : state.visible.map(m => <MedalEntry key={m.id} medal={m} onTrack={state.setTracked} />)}
      </div>

      <GameScrollbar targetRef={listRef} className={s.scrollbar} />
    </div>
  );
}
