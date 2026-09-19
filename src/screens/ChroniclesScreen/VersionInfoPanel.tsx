import { nineSlice } from '@/lib/nineSlice';
import type { ArchiveEntry } from '@/lib/assets';
import { formatReleaseMonth } from '@/lib/dates';
import { pick, useI18n, type Localized } from '@/lib/i18n';
import s from './VersionInfoPanel.module.css';

/** Fiche d'une version (`src/data/versions.json`) ; tous les champs sont facultatifs. */
export type VersionInfo = {
  /** `AAAA-MM` ou `AAAA` de la sortie EU/FR. */
  release?: string;
  /** Résumé de l'histoire de l'add-on, par langue. */
  lore?: Localized;
  /** Grands changements, phrases courtes sans point final, par langue. */
  changes?: Localized<string[]>;
  /** Documentation de la recherche, non affichée. */
  release_note?: string;
  confidence?: string;
  sources?: string[];
};

type Props = { entry: ArchiveEntry; info: VersionInfo | undefined; id: string };

/**
 * Panneau « À propos de cette version », ouvert par le bouton « ? » du jeu : date de
 * sortie, histoire de l'add-on et grands changements, dans la langue du site. Cadre
 * d'infobulle du jeu sur le fond noir translucide des infobulles, comme le lecteur.
 */
export function VersionInfoPanel({ entry, info, id }: Props) {
  const { lang, t } = useI18n();
  const lore = pick(info?.lore, lang);
  const changes = pick(info?.changes, lang);
  const hasContent = !!(info?.release || lore || changes?.length);
  return (
    <section
      id={id}
      className={s.panel}
      style={nineSlice('tooltip-frame', [4, 4, 4, 4])}
      aria-label={t('chronicles.aboutOf', { label: entry.label })}
      data-testid="version-info"
    >
      <h2 className={s.title}>{entry.label}</h2>
      {!hasContent && <p className={s.pending}>{t('chronicles.pending')}</p>}
      {info?.release && (
        <p className={s.release}>
          <span className={s.key}>{t('chronicles.release')}</span> {formatReleaseMonth(info.release, lang)}
        </p>
      )}
      {lore && <p className={s.lore}>{lore}</p>}
      {changes && changes.length > 0 && (
        <>
          <p className={s.key}>{t('chronicles.highlights')}</p>
          <ul className={s.changes}>
            {changes.map(change => <li key={change}>{change}</li>)}
          </ul>
        </>
      )}
    </section>
  );
}
