import { Fragment, type ReactNode } from 'react';
import type { ClassTalents, TalentInfo, TalentLang } from '@/data/talents.types';
import { formatVar, parseGameText, talentName, textFor, type Prereq, type Segment } from '@/data/talents.logic';
import { useI18n } from '@/lib/i18n';
import s from './TalentCard.module.css';

function Segments({ segs }: { segs: Segment[] }) {
  return (
    <>
      {segs.map((seg, i) => {
        if (seg.kind === 'br') return <br key={i} />;
        if (seg.kind === 'var') {
          return (
            <span key={i} className={`${s.var} ${seg.tone ? s[seg.tone] : ''}`} title={seg.name}>
              {seg.value === null ? '?' : `[${seg.value}${seg.scaled ? '*' : ''}]`}
            </span>
          );
        }
        return <span key={i} className={seg.tone ? s[seg.tone] : undefined}>{seg.text}</span>;
      })}
    </>
  );
}

/**
 * Contenu de l'infobulle d'un talent : nom, rangs, état dans le build (`status` : rang atteint,
 * raison d'un blocage), prérequis, description et valeurs par rang.
 */
export function TalentCard({ data, talentKey, prereqs, lang, status }: { data: ClassTalents; talentKey: string; prereqs: Prereq[]; lang: TalentLang; status?: ReactNode }) {
  const { t } = useI18n();
  const talent: TalentInfo | undefined = data.talents[talentKey];
  if (!talent) return null;
  const name = talentName(talent, lang);
  const desc = textFor(talent.description, lang);
  const rank0 = talent.ranks[0];
  const segs = desc ? parseGameText(desc.text, rank0?.vars, lang) : [];
  const varNames = Array.from(new Set(talent.ranks.flatMap(r => Object.keys(r.vars ?? {}))));
  const multi = talent.ranks.length > 1;
  const scaled = talent.ranks.some(r => Object.values(r.vars ?? {}).some(v => v.scalers?.length));
  const usesVars = segs.some(x => x.kind === 'var');
  return (
    <div className={s.card} data-testid="talent-card">
      <div className={s.head}>
        <span className={s.name}>{name.text}</span>
        {name.lang && name.lang !== lang && <span className={s.langTag}>{name.lang.toUpperCase()}</span>}
      </div>
      <div className={s.meta}>
        {t(talent.kind === 'spell' ? 'talents.kindSpell' : 'talents.kindAbility')}
        {' · '}{t('talents.ranks', { count: talent.ranks.length })}
        {name.internal && <> · <em>{t('talents.internalName')}</em></>}
      </div>
      {status && <div className={s.status}>{status}</div>}
      {prereqs.length > 0 && (
        <ul className={s.prereqs}>
          {prereqs.map((p, i) => (
            <li key={i}>
              {p.kind === 'points' && t('talents.prereqPoints', { points: p.points })}
              {p.kind === 'parent' && t('talents.prereqParent', { name: talentName(data.talents[p.talent], lang).text })}
              {p.kind === 'unlock' && t('talents.prereqUnlock', { ref: p.ref })}
              {p.kind === 'fieldStart' && t('talents.prereqStart')}
              {p.kind === 'fieldRanks' && t('talents.prereqCells', { count: p.count })}
            </li>
          ))}
        </ul>
      )}
      {desc ? (
        <div className={s.desc}>
          {desc.lang !== lang && <span className={s.langTag}>{desc.lang.toUpperCase()}</span>}
          <Segments segs={segs} />
        </div>
      ) : (
        <div className={s.missing}>{t('talents.noDescription')}</div>
      )}
      {usesVars && multi && varNames.some(v => new Set(talent.ranks.map(r => r.vars?.[v]?.value ?? null)).size > 1) && (
        <table className={s.ranks}>
          <thead>
            <tr><th />{talent.ranks.map((_, i) => <th key={i}>{t('talents.rank', { n: i + 1 })}</th>)}</tr>
          </thead>
          <tbody>
            {varNames.map(v => (
              <tr key={v}>
                <th title={v}>{v}</th>
                {talent.ranks.map((r, i) => {
                  const f = formatVar(r.vars?.[v], lang);
                  return <td key={i}>{f ? `${f.text}${f.scaled ? '*' : ''}` : '—'}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {talent.ranks.some(r => r.description) && (
        <div className={s.rankDescs}>
          {talent.ranks.map((r, i) => {
            const d = textFor(r.description, lang);
            return d ? (
              <Fragment key={i}>
                <div className={s.rankTitle}>{t('talents.rank', { n: i + 1 })}</div>
                <div className={s.desc}><Segments segs={parseGameText(d.text, r.vars, lang)} /></div>
              </Fragment>
            ) : null;
          })}
        </div>
      )}
      {usesVars && <div className={s.note}>{t(scaled ? 'talents.noteScaled' : 'talents.noteRaw')}</div>}
    </div>
  );
}
