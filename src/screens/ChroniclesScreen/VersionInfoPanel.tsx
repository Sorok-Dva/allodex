import { nineSlice } from '@/lib/nineSlice';
import type { ArchiveEntry } from '@/lib/assets';
import { formatReleaseMonth } from '@/lib/dates';
import s from './VersionInfoPanel.module.css';

/** Fiche d'une version (`src/data/versions.json`) ; tous les champs sont facultatifs. */
export type VersionInfo = {
  /** `AAAA-MM` ou `AAAA` de la sortie EU/FR. */
  release?: string;
  /** Résumé de l'histoire de l'add-on. */
  lore?: string;
  /** Grands changements, phrases courtes sans point final. */
  changes?: string[];
};

type Props = { entry: ArchiveEntry; info: VersionInfo | undefined; id: string };

/**
 * Panneau « À propos de cette version », ouvert par le bouton « ? » du jeu : date de
 * sortie, histoire de l'add-on et grands changements. Cadre d'infobulle du jeu sur le
 * fond noir translucide des infobulles, comme le lecteur du thème.
 */
export function VersionInfoPanel({ entry, info, id }: Props) {
  const hasContent = !!(info?.release || info?.lore || info?.changes?.length);
  return (
    <section
      id={id}
      className={s.panel}
      style={nineSlice('tooltip-frame', [4, 4, 4, 4])}
      aria-label={`À propos de ${entry.label}`}
      data-testid="version-info"
    >
      <h2 className={s.title}>{entry.label}</h2>
      {!hasContent && <p className={s.pending}>Fiche à venir.</p>}
      {info?.release && (
        <p className={s.release}>
          <span className={s.key}>Sortie</span> {formatReleaseMonth(info.release)}
        </p>
      )}
      {info?.lore && <p className={s.lore}>{info.lore}</p>}
      {info?.changes && info.changes.length > 0 && (
        <>
          <p className={s.key}>Au programme</p>
          <ul className={s.changes}>
            {info.changes.map(change => <li key={change}>{change}</li>)}
          </ul>
        </>
      )}
    </section>
  );
}
