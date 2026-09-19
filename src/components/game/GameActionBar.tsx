import { useRef, useState } from 'react';
import { GameButton } from './GameButton';
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

const SLOT_WIDTH = 48;
const SLOT_HEIGHT = 52;

export function GameActionBar({ items, className }: Props) {
  const [hover, setHover] = useState<{ id: string; anchor: DOMRect } | null>(null);
  const slots = useRef<Record<string, HTMLDivElement | null>>({});

  const hovered = hover ? items.find(item => item.id === hover.id) : undefined;

  return (
    <div className={`${s.bar} ${className ?? ''}`}>
      {items.map(item => (
        <div
          key={item.id}
          ref={el => { slots.current[item.id] = el; }}
          className={s.slot}
          onMouseEnter={() => {
            const el = slots.current[item.id];
            if (el) setHover({ id: item.id, anchor: el.getBoundingClientRect() });
          }}
          onMouseLeave={() => setHover(current => (current?.id === item.id ? null : current))}
        >
          <GameButton
            base={item.base}
            width={SLOT_WIDTH}
            height={SLOT_HEIGHT}
            stateNames={{ hover: 'Highlight' }}
            onClick={item.onClick}
            title={item.label}
            className={s.btn}
            style={{ backgroundSize: 'contain', backgroundPosition: 'center', backgroundRepeat: 'no-repeat' }}
          />
        </div>
      ))}
      {hovered && hover && (
        <GameTooltip anchor={hover.anchor} title={hovered.label}>
          {hovered.hint}
        </GameTooltip>
      )}
    </div>
  );
}
