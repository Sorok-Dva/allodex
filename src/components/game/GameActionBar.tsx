import { useRef, useState } from 'react';
import { tex } from '@/lib/assets';
import { GameTooltip } from './GameTooltip';
import s from './GameActionBar.module.css';

export type ActionItem = {
  id: string;
  base: string;
  label: string;
  hint?: string;
  onClick?: () => void;
};

type Props = { items: ActionItem[]; className?: string };

// Les textures `…Highlight` de ContextPinMenu3 ne sont qu'un halo lumineux (pas d'icône) :
// on empile une couche `Normal`/`Pressed` toujours visible et une couche `Highlight`
// en surimpression, révélée uniquement au survol — GameButton ne gère qu'un seul fond
// et ne peut pas exprimer cet empilement, d'où un rendu dédié ici.
export function GameActionBar({ items, className }: Props) {
  const [hover, setHover] = useState<{ id: string; anchor: DOMRect } | null>(null);
  const [pressedId, setPressedId] = useState<string | null>(null);
  const slots = useRef<Record<string, HTMLButtonElement | null>>({});

  const hovered = hover ? items.find(item => item.id === hover.id) : undefined;

  return (
    <div className={`${s.bar} ${className ?? ''}`}>
      {items.map(item => {
        const isHover = hover?.id === item.id;
        const isPressed = pressedId === item.id;
        return (
          <button
            key={item.id}
            type="button"
            ref={el => { slots.current[item.id] = el; }}
            className={s.slot}
            aria-label={item.label}
            onClick={item.onClick}
            onMouseEnter={() => {
              const el = slots.current[item.id];
              if (el) setHover({ id: item.id, anchor: el.getBoundingClientRect() });
            }}
            onMouseLeave={() => {
              setHover(current => (current?.id === item.id ? null : current));
              setPressedId(current => (current === item.id ? null : current));
            }}
            onMouseDown={() => setPressedId(item.id)}
            onMouseUp={() => setPressedId(null)}
          >
            <span
              className={s.base}
              data-testid={`action-base-${item.id}`}
              style={{ backgroundImage: `url(${tex(`${item.base}${isPressed ? 'Pressed' : 'Normal'}`)})` }}
            />
            <span
              className={s.highlight}
              data-testid={`action-highlight-${item.id}`}
              style={{ backgroundImage: `url(${tex(`${item.base}Highlight`)})`, opacity: isHover ? 1 : 0 }}
            />
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
