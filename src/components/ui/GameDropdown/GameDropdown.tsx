import { useEffect, useId, useRef, useState, type CSSProperties, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { sprite } from '@/lib/assets';
import { nineSlice } from '@/lib/nineSlice';
import s from './GameDropdown.module.css';

export type DropdownOption<T extends string> = { value: T; label: string };

type Props<T extends string> = {
  value: T;
  options: DropdownOption<T>[];
  onChange: (value: T) => void;
  /** Largeur du champ, hors bouton doré (126 px dans le jeu). */
  width?: number;
  /** Libellé accessible du champ (le jeu n'en affiche aucun). */
  label?: string;
  className?: string;
  style?: CSSProperties;
};

/**
 * Menu déroulant du jeu : champ `dropdown-field` (126 × 24) suivi du bouton doré
 * `dropdown-button` (23 × 23) ; à l'ouverture, le cadre `dropdown-frame` (154 × 87)
 * se pose 2 px sous le champ et déborde de 3 px à gauche, options alignées à droite.
 * Géométrie relevée sur `refs/astral.png` (fermé) et `refs/dropdown.png` (ouvert).
 *
 * Arborescence ARIA du motif `combobox` + `listbox` : le champ garde le focus et
 * désigne l'option courante par `aria-activedescendant`, la liste est un `ul`
 * `listbox` dont les `li` sont neutralisés (`presentation`) pour que seuls les
 * boutons `option` soient exposés.
 */
export function GameDropdown<T extends string>({ value, options, onChange, width = 126, label, className, style }: Props<T>) {
  const [open, setOpen] = useState(false);
  /** Option désignée au clavier ; `null` tant qu'on n'a pas navigué (ouverture à la souris). */
  const [active, setActive] = useState<number | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listId = useId();
  const optionId = (i: number) => `${listId}-${i}`;
  const current = options.find(o => o.value === value);
  const selectedIndex = Math.max(0, options.findIndex(o => o.value === value));
  const last = options.length - 1;

  /**
   * La liste est démontée à la fermeture : sans cela le focus retomberait sur `<body>`
   * et la navigation au clavier repartirait du début du document. On le rend au champ,
   * qui est l'élément `combobox` de la paire.
   */
  const close = () => { setOpen(false); setActive(null); triggerRef.current?.focus(); };
  const toggle = () => { setActive(null); setOpen(o => !o); };
  const choose = (i: number) => {
    const option = options[i];
    if (option) onChange(option.value);
    close();
  };

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close(); };
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) { setOpen(false); setActive(null); }
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onDown);
    return () => { document.removeEventListener('keydown', onKey); document.removeEventListener('mousedown', onDown); };
  }, [open]);

  // Clavier du motif `listbox` : flèches (ouvrent la liste si elle est fermée et
  // partent de l'option courante), Début/Fin, Entrée et Espace valident ; Échap est
  // déjà pris en charge au niveau du document, liste ouverte.
  const onKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (!options.length) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!open) { setOpen(true); setActive(selectedIndex); return; }
      const step = e.key === 'ArrowDown' ? 1 : -1;
      setActive(a => (a === null ? selectedIndex : Math.min(last, Math.max(0, a + step))));
      return;
    }
    if (!open) return;
    if (e.key === 'Home') { e.preventDefault(); setActive(0); return; }
    if (e.key === 'End') { e.preventDefault(); setActive(last); return; }
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); choose(active ?? selectedIndex); }
  };

  return (
    <div
      ref={rootRef}
      className={`${s.root} ${className ?? ''}`}
      style={{ width: width + 23, ...style }}
      onKeyDown={onKeyDown}
    >
      <button
        type="button"
        ref={triggerRef}
        className={s.field}
        style={{ ...nineSlice('dropdown-field', [5, 6, 5, 6], { fill: true }), width }}
        role="combobox"
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={listId}
        aria-activedescendant={open && active !== null ? optionId(active) : undefined}
        aria-label={label}
        onClick={toggle}
      >
        <span className={s.value}>{current?.label ?? ''}</span>
      </button>
      <button
        type="button"
        className={s.button}
        style={{ backgroundImage: `url(${sprite('dropdown-button')})`, left: width }}
        tabIndex={-1}
        aria-hidden="true"
        onClick={toggle}
      />
      {open && (
        <ul id={listId} className={s.list} role="listbox" style={nineSlice('dropdown-frame', [4, 4, 4, 4])}>
          {options.map((o, i) => (
            <li key={o.value} role="presentation">
              <button
                type="button"
                id={optionId(i)}
                className={`${s.option} ${i === active ? s.optionActive : ''}`}
                role="option"
                aria-selected={o.value === value}
                tabIndex={-1}
                onClick={() => choose(i)}
              >
                {o.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
