import type { MedalsDataset } from '@/data/medals.types';
import type { MedalsState } from './useMedalsState';
export function MedalsList({ state }: { ds: MedalsDataset; state: MedalsState }) {
  return <section style={{ flex: 1 }}>{state.title} — {state.visible.length} succès</section>;
}
