import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent, type FormEvent } from 'react';
import { navigate, useRoute } from '@/lib/router';
import { sprite } from '@/lib/assets';
import { nineSlice } from '@/lib/nineSlice';
import { GameDropdown, type DropdownOption } from '@/components/ui/GameDropdown';
import { GameStrip } from '@/components/ui/GameStrip';
import { GameWindow } from '@/components/ui/GameWindow';
import {
  DEFAULT_FILTERS, FACTION_LABEL, IMPORTANCE_LABEL, KIND_LABEL, KINDS, PRIORITIES, PRIORITY_LABEL, STATUSES, STATUS_LABEL,
  addFreeEntry, formatSeconds, moveEntry, removeEntry, siteLink, stepEntry, timeline, totals, updateEntry,
  type ChapterView, type FilmPlan, type Filters, type PlanEntry, type PlanFaction, type PlanKind, type PlanPriority, type PlanStatus, type View,
} from './filmPlan';
import { httpPlanApi, type PlanApi } from './planApi';
import s from './FilmPlanScreen.module.css';

/** Tranches de la pilule du jeu (`pill-full`, 242 × 28), mesurées sur l'image (voir VersionTimeline). */
const PILL_SLICE: [number, number, number, number] = [0, 30, 0, 24];
const SAVE_DELAY_MS = 600;
const VIEWS: { value: View; label: string }[] = [
  { value: 'league', label: 'Ligue' }, { value: 'empire', label: 'Empire' }, { value: 'all', label: 'Tout' },
];
const isView = (v: string | null): v is View => v === 'league' || v === 'empire' || v === 'all';

const STATUS_OPTIONS: DropdownOption<PlanStatus>[] = STATUSES.map(v => ({ value: v, label: STATUS_LABEL[v] }));
const PRIORITY_OPTIONS: DropdownOption<PlanPriority>[] = PRIORITIES.map(v => ({ value: v, label: PRIORITY_LABEL[v] }));
const KIND_FILTER: DropdownOption<PlanKind | 'all'>[] = [{ value: 'all', label: 'Tous les types' }, ...KINDS.map(v => ({ value: v, label: KIND_LABEL[v] }))];
const PRIORITY_FILTER: DropdownOption<PlanPriority | 'all'>[] = [{ value: 'all', label: 'Toutes priorités' }, ...PRIORITY_OPTIONS];

type SaveState = { kind: 'idle' | 'dirty' | 'saving' | 'saved' } | { kind: 'error'; message: string };

function Pill({ label, active, onClick, title, testId }: { label: string; active: boolean; onClick: () => void; title?: string; testId?: string }) {
  return (
    <button type="button" className={`${s.pill} ${active ? s.pillActive : ''}`} onClick={onClick} aria-pressed={active} title={title} data-testid={testId}>
      <span className={s.pillSkin} aria-hidden="true" style={nineSlice(active ? 'pill-full-open' : 'pill-full', PILL_SLICE, { fill: true })} />
      <span className={s.pillLabel}>{label}</span>
    </button>
  );
}

/** `GameDropdown` est posé en absolu : ce support lui réserve sa place dans le flux (champ + bouton doré). */
function Dropdown<T extends string>(props: { value: T; options: DropdownOption<T>[]; onChange: (v: T) => void; label: string; width: number }) {
  return (
    <span className={s.dd} style={{ width: props.width + 23 }}>
      <GameDropdown {...props} />
    </span>
  );
}

const durationText = (e: PlanEntry) => (e.duration === null ? 'durée ?' : `${e.durationEstimated ? '≈ ' : ''}${formatSeconds(e.duration)}`);

/**
 * Page de développement `/dev/film` : plan du film des cinématiques, frise par faction.
 * Lit et enregistre `tools/film_plan.json` par le greffon Vite ; se recharge quand le fichier
 * change sur disque (un agent l'a édité). Absente du build de production (voir `App.tsx`).
 */
export default function FilmPlanScreen({ api = httpPlanApi }: { api?: PlanApi }) {
  const { query } = useRoute();
  const view: View = isView(query.get('faction')) ? (query.get('faction') as View) : 'league';
  const [plan, setPlan] = useState<FilmPlan | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [fileErrors, setFileErrors] = useState<string[]>([]);
  const [save, setSave] = useState<SaveState>({ kind: 'idle' });
  const [conflict, setConflict] = useState(false);
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [open, setOpen] = useState<Set<string>>(() => new Set());
  const [adding, setAdding] = useState<string | null>(null);
  const [dragId, setDragId] = useState<string | null>(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);

  const revision = useRef('');
  const planRef = useRef<FilmPlan | null>(null);
  const dirty = useRef(false);
  const timer = useRef<number | null>(null);

  const reload = useCallback(async () => {
    try {
      const loaded = await api.load();
      revision.current = loaded.revision;
      planRef.current = loaded.plan;
      dirty.current = false;
      setPlan(loaded.plan);
      setFileErrors(loaded.errors);
      setLoadError(null);
      setConflict(false);
      setSave({ kind: 'idle' });
    } catch (error) {
      setLoadError(String((error as Error)?.message ?? error));
    }
  }, [api]);

  const flush = useCallback(async (force = false) => {
    if (timer.current !== null) { window.clearTimeout(timer.current); timer.current = null; }
    const current = planRef.current;
    if (!current || (!dirty.current && !force)) return;
    setSave({ kind: 'saving' });
    const result = await api.save(current, revision.current);
    if (result.ok) {
      revision.current = result.revision;
      if (planRef.current === current) { dirty.current = false; setSave({ kind: 'saved' }); }
      else setSave({ kind: 'dirty' });
    } else if (result.conflict) {
      setConflict(true);
      setSave({ kind: 'dirty' });
    } else {
      setSave({ kind: 'error', message: result.error });
    }
  }, [api]);

  useEffect(() => { void reload(); }, [reload]);
  useEffect(() => api.subscribe(rev => {
    if (rev === revision.current) return;
    if (dirty.current) setConflict(true);
    else void reload();
  }), [api, reload]);
  useEffect(() => () => { if (timer.current !== null) window.clearTimeout(timer.current); }, []);

  /** Toute modification passe par ici : état, puis enregistrement différé. */
  const apply = useCallback((change: (p: FilmPlan) => FilmPlan) => {
    const current = planRef.current;
    if (!current) return;
    const next = change(current);
    if (next === current) return;
    planRef.current = next;
    dirty.current = true;
    setPlan(next);
    setSave({ kind: 'dirty' });
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => { timer.current = null; void flush(); }, SAVE_DELAY_MS);
  }, [flush]);

  /** Conflit : on écrase le fichier avec notre version (après avoir relu sa révision). */
  const overwrite = useCallback(async () => {
    try {
      const loaded = await api.load();
      revision.current = loaded.revision;
      setConflict(false);
      await flush(true);
    } catch (error) {
      setSave({ kind: 'error', message: String((error as Error)?.message ?? error) });
    }
  }, [api, flush]);

  const chapters = useMemo(() => (plan ? timeline(plan, view, filters) : []), [plan, view, filters]);
  const sums = useMemo(() => (plan ? totals(plan, view) : null), [plan, view]);

  const toggleOpen = (id: string) => setOpen(prev => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const toggleStatus = (status: PlanStatus) => setFilters(f => {
    const has = f.statuses.includes(status);
    const statuses = has ? f.statuses.filter(v => v !== status) : STATUSES.filter(v => v === status || f.statuses.includes(v));
    return { ...f, statuses };
  });

  const onDragStart = (e: DragEvent, id: string) => { setDragId(id); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', id); };
  const onDragEnd = () => { setDragId(null); setDropTarget(null); };
  const allowDrop = (e: DragEvent, target: string) => { if (!dragId) return; e.preventDefault(); e.dataTransfer.dropEffect = 'move'; if (dropTarget !== target) setDropTarget(target); };
  const dropOn = (e: DragEvent, beforeId: string | null, chapter: string) => {
    e.preventDefault();
    const id = dragId ?? e.dataTransfer.getData('text/plain');
    onDragEnd();
    if (id) apply(p => moveEntry(p, id, { beforeId, chapter }));
  };

  if (loadError && !plan) {
    return (
      <main className={s.screen}>
        <p className={s.fatal} role="alert">Plan illisible : {loadError}. La page ne fonctionne qu’avec le serveur de développement (<code>npm run dev</code>).</p>
      </main>
    );
  }
  if (!plan || !sums) return <main className={s.screen} aria-busy="true" />;

  const target = plan.targetMinutes * 60;
  const saveText = save.kind === 'saving' ? 'Enregistrement…' : save.kind === 'dirty' ? 'Modifications en attente' : save.kind === 'saved' ? 'Enregistré dans tools/film_plan.json' : save.kind === 'error' ? `Erreur : ${save.message}` : 'À jour';

  return (
    <main className={s.screen} aria-label="Plan du film">
      <header className={s.head}>
        <div className={s.plate}>
          <GameStrip base="title-plate" cap={38} />
          <h1 className={s.title}>Plan du film</h1>
        </div>
        <div className={s.views} role="group" aria-label="Film">
          {VIEWS.map(v => (
            <Pill key={v.value} label={v.label} active={view === v.value} testId={`view-${v.value}`}
              onClick={() => navigate(`/dev/film?faction=${v.value}`, { replace: true })} />
          ))}
        </div>
        <dl className={s.totals} data-testid="totals">
          <div><dt>Film actuel</dt><dd>{formatSeconds(sums.current)}</dd></div>
          <div><dt>Film visé</dt><dd>{formatSeconds(sums.planned)}{sums.unknown ? <small> + {sums.unknown} durées ?</small> : null}</dd></div>
          <div><dt>Objectif</dt><dd>{formatSeconds(target)}</dd></div>
          <div><dt>Trous</dt><dd>{sums.gaps} chapitre{sums.gaps > 1 ? 's' : ''}</dd></div>
        </dl>
        <div className={s.gauge} aria-hidden="true">
          <span className={s.gaugePlanned} style={{ width: `${Math.min(100, (sums.planned / target) * 100)}%` }} />
          <span className={s.gaugeCurrent} style={{ width: `${Math.min(100, (sums.current / target) * 100)}%` }} />
        </div>
        <p className={`${s.saveState} ${save.kind === 'error' ? s.saveError : ''}`} role="status" data-testid="save-state">{saveText}</p>
      </header>

      {conflict && (
        <div className={s.banner} role="alert">
          Le fichier a été modifié sur disque (par un agent ?) pendant que vous l’éditiez.
          <button type="button" className={s.textButton} onClick={() => void reload()}>Recharger le fichier (perdre mes modifications)</button>
          <button type="button" className={s.textButton} onClick={() => void overwrite()}>Écraser avec ma version</button>
        </div>
      )}
      {fileErrors.length > 0 && (
        <div className={s.banner} role="alert">Le fichier a des erreurs (la page refusera de l’enregistrer tant qu’elles restent) : {fileErrors.slice(0, 6).join(' ; ')}</div>
      )}

      <section className={s.filters} aria-label="Filtres">
        {STATUSES.map(st => (
          <Pill key={st} label={STATUS_LABEL[st]} active={filters.statuses.includes(st)} onClick={() => toggleStatus(st)} testId={`filter-${st}`} />
        ))}
        <Dropdown value={filters.kind} options={KIND_FILTER} onChange={kind => setFilters(f => ({ ...f, kind }))} label="Type" width={126} />
        <Dropdown value={filters.priority} options={PRIORITY_FILTER} onChange={priority => setFilters(f => ({ ...f, priority }))} label="Priorité" width={126} />
        <input className={s.search} type="search" placeholder="Rechercher (titre, zone, quête, source…)" value={filters.text}
          onChange={e => setFilters(f => ({ ...f, text: e.target.value }))} aria-label="Rechercher" />
        <Pill label="Trous seulement" active={filters.gapsOnly} onClick={() => setFilters(f => ({ ...f, gapsOnly: !f.gapsOnly }))} testId="filter-gaps" />
      </section>

      <ol className={s.timeline}>
        {chapters.map(cv => (
          <ChapterBlock key={cv.chapter.id} cv={cv} view={view} open={open} dragId={dragId} dropTarget={dropTarget}
            onToggle={toggleOpen} onAdd={() => setAdding(cv.chapter.id)} apply={apply}
            onDragStart={onDragStart} onDragEnd={onDragEnd} allowDrop={allowDrop} dropOn={dropOn} />
        ))}
      </ol>

      {adding && (
        <AddEntryDialog chapter={plan.chapters.find(c => c.id === adding)!} view={view} onClose={() => setAdding(null)}
          onAdd={draft => { apply(p => addFreeEntry(p, adding, draft)); setAdding(null); }} />
      )}
    </main>
  );
}

type BlockProps = {
  cv: ChapterView;
  view: View;
  open: Set<string>;
  dragId: string | null;
  dropTarget: string | null;
  onToggle: (id: string) => void;
  onAdd: () => void;
  apply: (change: (p: FilmPlan) => FilmPlan) => void;
  onDragStart: (e: DragEvent, id: string) => void;
  onDragEnd: () => void;
  allowDrop: (e: DragEvent, target: string) => void;
  dropOn: (e: DragEvent, beforeId: string | null, chapter: string) => void;
};

function ChapterBlock({ cv, view, open, dragId, dropTarget, onToggle, onAdd, apply, onDragStart, onDragEnd, allowDrop, dropOn }: BlockProps) {
  const { chapter, shown, all, gap } = cv;
  const endKey = `end:${chapter.id}`;
  const candidates = all.filter(e => e.status !== 'discarded').length;
  return (
    <li className={`${s.chapter} ${gap !== 'none' ? s.chapterGap : ''}`} data-testid={`chapter-${chapter.id}`} data-gap={gap}>
      <div className={s.chapterHead} onDragOver={e => allowDrop(e, endKey)} onDrop={e => dropOn(e, null, chapter.id)}>
        <span className={s.node} aria-hidden="true" />
        <span className={s.version}>{chapter.version}</span>
        <h2 className={s.chapterTitle}>{chapter.title}</h2>
        {chapter.faction !== 'common' && <span className={s.tag}>{FACTION_LABEL[chapter.faction]}</span>}
        {gap === 'empty' && <span className={s.gapBadge}>Trou : aucune scène connue</span>}
        {gap === 'partial' && <span className={s.gapBadge}>Trou : rien dans le film ({candidates} candidate{candidates > 1 ? 's' : ''})</span>}
        {cv.filmSeconds > 0 && <span className={s.chapterTime}>{formatSeconds(cv.filmSeconds)} dans le film</span>}
        <button type="button" className={s.textButton} onClick={onAdd} data-testid={`add-${chapter.id}`}>+ Scène à créer</button>
      </div>
      {chapter.summary && <p className={s.summary}>{chapter.summary}{chapter.source ? <span className={s.chapterSource}> — {chapter.source}</span> : null}</p>}
      <ul className={s.entries}>
        {shown.map((e, i) => (
          <EntryRow key={e.id} entry={e} view={view} first={i === 0} last={i === shown.length - 1} open={open.has(e.id)}
            dragging={dragId === e.id} dropBefore={dropTarget === e.id}
            onToggle={() => onToggle(e.id)}
            onStep={step => apply(p => stepEntry(p, e.id, shown, step))}
            onPatch={patch => apply(p => updateEntry(p, e.id, patch))}
            onRemove={() => apply(p => removeEntry(p, e.id))}
            onDragStart={ev => onDragStart(ev, e.id)} onDragEnd={onDragEnd}
            onDragOver={ev => allowDrop(ev, e.id)} onDrop={ev => dropOn(ev, e.id, chapter.id)} />
        ))}
        {dragId && (
          <li className={`${s.dropEnd} ${dropTarget === endKey ? s.dropActive : ''}`} onDragOver={e => allowDrop(e, endKey)} onDrop={e => dropOn(e, null, chapter.id)}>
            Déposer en fin de chapitre
          </li>
        )}
      </ul>
    </li>
  );
}

type RowProps = {
  entry: PlanEntry;
  view: View;
  first: boolean;
  last: boolean;
  open: boolean;
  dragging: boolean;
  dropBefore: boolean;
  onToggle: () => void;
  onStep: (step: -1 | 1) => void;
  onPatch: (patch: Partial<PlanEntry>) => void;
  onRemove: () => void;
  onDragStart: (e: DragEvent) => void;
  onDragEnd: () => void;
  onDragOver: (e: DragEvent) => void;
  onDrop: (e: DragEvent) => void;
};

function EntryRow({ entry: e, view, first, last, open, dragging, dropBefore, onToggle, onStep, onPatch, onRemove, onDragStart, onDragEnd, onDragOver, onDrop }: RowProps) {
  const [note, setNote] = useState(e.note ?? '');
  useEffect(() => setNote(e.note ?? ''), [e.note]);
  const link = siteLink(e, view);
  const commitNote = () => { if (note !== (e.note ?? '')) onPatch({ note: note.trim() ? note : undefined }); };
  return (
    <li className={`${s.entry} ${s[`status_${e.status}`]} ${dragging ? s.dragging : ''} ${dropBefore ? s.dropBefore : ''}`}
      data-testid={`entry-${e.id}`} draggable onDragStart={onDragStart} onDragEnd={onDragEnd} onDragOver={onDragOver} onDrop={onDrop}>
      <div className={s.row}>
        <span className={s.handle} title="Glisser pour déplacer" aria-hidden="true">⋮⋮</span>
        <span className={s.arrows}>
          <button type="button" className={s.arrow} onClick={() => onStep(-1)} disabled={first} aria-label={`Monter « ${e.title} »`}
            style={{ backgroundImage: `url(${sprite(first ? 'scroll-up-off' : 'scroll-up')})` }} />
          <button type="button" className={s.arrow} onClick={() => onStep(1)} disabled={last} aria-label={`Descendre « ${e.title} »`}
            style={{ backgroundImage: `url(${sprite(last ? 'scroll-down-off' : 'scroll-down')})` }} />
        </span>
        <button type="button" className={s.entryTitle} onClick={onToggle} aria-expanded={open}>
          <span className={`${s.kind} ${s[`kind_${e.kind}`]}`}>{KIND_LABEL[e.kind]}</span>
          {e.title}
        </button>
        <span className={s.meta}>
          {[e.zone, e.version].filter(Boolean).join(' · ')}{e.faction !== 'common' ? ` · ${FACTION_LABEL[e.faction]}` : ''}
        </span>
        <span className={s.duration}>{durationText(e)}</span>
        {e.importance && <span className={s.importance}>{IMPORTANCE_LABEL[e.importance]}</span>}
        <Dropdown value={e.status} options={STATUS_OPTIONS} onChange={status => onPatch({ status })} label={`Statut de « ${e.title} »`} width={104} />
        <span className={s.priority} title={e.priorityProposed ? 'Priorité proposée par l’inventaire, pas encore décidée' : undefined}>
          <Dropdown value={e.priority} options={PRIORITY_OPTIONS} onChange={priority => onPatch({ priority, priorityProposed: undefined })}
            label={`Priorité de « ${e.title} »`} width={84} />
          {e.priorityProposed && <span className={s.proposed}>proposée</span>}
        </span>
        {link ? <a className={s.link} href={link} target="_blank" rel="noreferrer">Voir</a> : <span className={s.link} />}
      </div>
      {open && (
        <div className={s.details}>
          {e.trigger && <p><b>Déclencheur</b> {e.trigger}</p>}
          <p><b>Voix</b> {e.voice ?? '?'} · <b>Sous-titres</b> {e.subtitles ?? '?'}{e.siteChapter ? <> · <b>Chapitre du site</b> <code>{e.siteChapter}</code></> : null}</p>
          {e.source && <p className={s.source}><b>Source</b> {e.source}</p>}
          <label className={s.noteLabel}>
            Note
            <textarea className={s.note} value={note} onChange={ev => setNote(ev.target.value)} onBlur={commitNote} rows={3} />
          </label>
          {e.kind === 'free' && <button type="button" className={s.textButton} onClick={onRemove}>Supprimer cette entrée libre</button>}
        </div>
      )}
    </li>
  );
}

function AddEntryDialog({ chapter, view, onClose, onAdd }: {
  chapter: FilmPlan['chapters'][number];
  view: View;
  onClose: () => void;
  onAdd: (draft: { title: string; duration: number | null; note: string; faction: PlanFaction }) => void;
}) {
  const [title, setTitle] = useState('');
  const [duration, setDuration] = useState('');
  const [note, setNote] = useState('');
  const defaultFaction: PlanFaction = chapter.faction !== 'common' ? chapter.faction : 'common';
  const [faction, setFaction] = useState<PlanFaction>(defaultFaction);
  const factionOptions: DropdownOption<PlanFaction>[] = chapter.faction !== 'common'
    ? [{ value: chapter.faction, label: FACTION_LABEL[chapter.faction] }]
    : (['common', 'league', 'empire'] as PlanFaction[]).map(v => ({ value: v, label: FACTION_LABEL[v] }));
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const seconds = duration.trim() === '' ? null : Number(duration.replace(',', '.'));
    onAdd({ title, duration: seconds !== null && Number.isFinite(seconds) && seconds >= 0 ? seconds : null, note, faction });
  };
  const scale = typeof window === 'undefined' ? 1 : Math.min(1, (window.innerHeight - 40) / 804, (window.innerWidth - 16) / 600);
  return (
    <div className={s.overlay} role="dialog" aria-modal="true" aria-label="Nouvelle scène à créer">
      <div className={s.dialogHolder} style={{ transform: `translate(-50%, -50%) scale(${scale})` }}>
        <GameWindow title="Nouvelle scène à créer" onClose={onClose} closeLabel="Fermer" width={600}
          header={<p className={s.dialogLead}>{chapter.title} · {chapter.version}{view !== 'all' && chapter.faction === 'common' ? ` (vue ${FACTION_LABEL[view]})` : ''}</p>}
          footer={<p className={s.dialogFoot}>L’entrée s’ajoute en fin de chapitre, au statut « À recréer ». Le film n’est pas modifié.</p>}>
          <form className={s.form} onSubmit={submit}>
            <label>Titre<input value={title} onChange={e => setTitle(e.target.value)} required autoFocus data-testid="add-title" /></label>
            <label>Durée estimée (secondes)<input value={duration} onChange={e => setDuration(e.target.value)} inputMode="decimal" data-testid="add-duration" /></label>
            <div className={s.formRow}>Faction <Dropdown value={faction} options={factionOptions} onChange={setFaction} label="Faction" width={110} /></div>
            <label>Note<textarea value={note} onChange={e => setNote(e.target.value)} rows={4} /></label>
            <div className={s.formActions}>
              <button type="button" className={s.textButton} onClick={onClose}>Annuler</button>
              <button type="submit" className={s.textButton} data-testid="add-submit">Ajouter</button>
            </div>
          </form>
        </GameWindow>
      </div>
    </div>
  );
}
