import { useRef, useState } from 'react';
import { sprite, tex } from '@/lib/assets';
import { GameTooltip } from '@/components/ui/GameTooltip';
import s from './GameActionBar.module.css';

export type ActionItem = {
  id: string;
  base: string;
  spriteBase?: string;
  image?: string;
  /** Image hors textures du jeu (URL directe), à la place de `image`. */
  src?: string;
  icon?: string;
  label: string;
  hint?: string;
  disabled?: boolean;
  onClick?: () => void;
  /** Lien externe, ouvert dans un nouvel onglet (au lieu de `onClick`). */
  href?: string;
};

type Props = { items: ActionItem[]; className?: string; onItemInteract?: (id: string) => void };

// Les textures `…Highlight` de ContextPinMenu3 ne sont qu'un halo lumineux (pas d'icône) :
// on empile une couche `Normal`/`Pressed` toujours visible et une couche `Highlight`
// en surimpression, révélée uniquement au survol. Un bouton à fond unique ne peut pas
// exprimer cet empilement, d'où un rendu dédié ici.
export function GameActionBar({ items, className, onItemInteract }: Props) {
  const [hover, setHover] = useState<{ id: string; anchor: DOMRect } | null>(null);
  const [pressedId, setPressedId] = useState<string | null>(null);
  const slots = useRef<Record<string, HTMLElement | null>>({});

  const hovered = hover ? items.find(item => item.id === hover.id) : undefined;

  // Infobulle au survol **et** au focus clavier : sans cela la barre serait muette
  // pour qui navigue au clavier.
  const show = (id: string) => {
    const el = slots.current[id];
    if (el) setHover({ id, anchor: el.getBoundingClientRect() });
  };
  const hide = (id: string) => {
    setHover(current => (current?.id === id ? null : current));
    setPressedId(current => (current === id ? null : current));
  };

  return (
    <div className={`${s.bar} ${className ?? ''}`}>
      {items.map(item => {
        const isDisabled = item.disabled || (!item.onClick && !item.href);
        const isHover = hover?.id === item.id;
        const isPressed = pressedId === item.id;
        const image = item.src ?? (item.image ? tex(item.image) : null);
        const common = {
          ref: (el: HTMLElement | null) => { slots.current[item.id] = el; },
          className: `${s.slot} ${isDisabled ? s.disabled : ''}`,
          'aria-label': item.label,
          'aria-disabled': isDisabled || undefined,
          onMouseEnter: () => show(item.id),
          onMouseLeave: () => hide(item.id),
          onFocus: () => show(item.id),
          onBlur: () => hide(item.id),
          onMouseDown: () => setPressedId(item.id),
          onMouseUp: () => setPressedId(null),
        };
        const layers = (
          <>
            <span
              className={s.base}
              data-testid={`action-base-${item.id}`}
              style={{ backgroundImage: `url(${image ?? (item.spriteBase ? sprite(`${item.spriteBase}-${isPressed ? 'pressed' : 'normal'}`) : tex(`${item.base}${isPressed ? 'Pressed' : 'Normal'}`))})`, transform: image && isPressed ? 'translateY(1px)' : undefined }}
            />
            {item.icon && <img className={s.icon} src={tex(item.icon)} alt="" />}
            <span
              className={s.highlight}
              data-testid={`action-highlight-${item.id}`}
              style={{ backgroundImage: `url(${tex(`${item.base}Highlight`)})`, opacity: isHover ? 1 : 0 }}
            />
          </>
        );
        if (item.href && !isDisabled) {
          return (
            <a key={item.id} {...common} href={item.href} target="_blank" rel="noopener noreferrer" onClick={() => onItemInteract?.(item.id)}>
              {layers}
            </a>
          );
        }
        return (
          <button key={item.id} type="button" {...common} onClick={() => { if (isDisabled) return; onItemInteract?.(item.id); item.onClick?.(); }}>
            {layers}
          </button>
        );
      })}
      {hovered && hover && (
        <GameTooltip anchor={hover.anchor} title={hovered.label}>
          {hovered.hint}
        </GameTooltip>
      )}
    </div>
  );
}
