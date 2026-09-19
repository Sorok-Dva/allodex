import { useEffect, useId, useRef, useState, type CSSProperties } from 'react';
import { sprite, spriteSize } from '@/lib/assets';
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

/** Cadre 9 tranches d'un sprite, d'après les tranches déclarées dans `sprites.json`. */
function frame(name: string, fallback: [number, number, number, number], fill: boolean): CSSProperties {
  const [top, right, bottom, left] = spriteSize(name)?.slice ?? fallback;
  return {
    borderImageSource: `url(${sprite(name)})`,
    borderImageSlice: `${top} ${right} ${bottom} ${left}${fill ? ' fill' : ''}`,
    borderImageWidth: `${top}px ${right}px ${bottom}px ${left}px`,
    borderWidth: `${top}px ${right}px ${bottom}px ${left}px`,
  };
}

/**
 * Menu déroulant du jeu : champ `dropdown-field` (126 × 24) suivi du bouton doré
 * `dropdown-button` (23 × 23) ; à l'ouverture, le cadre `dropdown-frame` (154 × 87)
 * se pose 2 px sous le champ et déborde de 3 px à gauche, options alignées à droite.
 * Géométrie relevée sur `refs/astral.png` (fermé) et `refs/dropdown.png` (ouvert).
 */
export function GameDropdown<T extends string>({ value, options, onChange, width = 126, label, className, style }: Props<T>) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const listId = useId();
  const current = options.find(o => o.value === value);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onDown);
    return () => { document.removeEventListener('keydown', onKey); document.removeEventListener('mousedown', onDown); };
  }, [open]);

  return (
    <div ref={rootRef} className={`${s.root} ${className ?? ''}`} style={{ width: width + 23, ...style }}>
      <button
        type="button"
        className={s.field}
        style={{ ...frame('dropdown-field', [5, 6, 5, 6], true), width }}
        role="combobox"
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={listId}
        aria-label={label}
        onClick={() => setOpen(o => !o)}
      >
        <span className={s.value}>{current?.label ?? ''}</span>
      </button>
      <button
        type="button"
        className={s.button}
        style={{ backgroundImage: `url(${sprite('dropdown-button')})`, left: width }}
        tabIndex={-1}
        aria-hidden="true"
        onClick={() => setOpen(o => !o)}
      />
      {open && (
        <ul id={listId} className={s.list} role="listbox" style={frame('dropdown-frame', [4, 4, 4, 4], false)}>
          {options.map(o => (
            <li key={o.value}>
              <button
                type="button"
                className={s.option}
                role="option"
                aria-selected={o.value === value}
                onClick={() => { onChange(o.value); setOpen(false); }}
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
