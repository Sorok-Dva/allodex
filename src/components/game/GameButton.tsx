import { useState, type CSSProperties, type ReactNode } from 'react';
import { tex } from '@/lib/assets';
import s from './GameButton.module.css';

type StateNames = { hover?: string; pressed?: string; disabled?: string };
type Props = {
  base: string; label?: ReactNode; title?: string; onClick?: () => void; disabled?: boolean;
  width: number; height: number; hoverState?: string; stateNames?: StateNames; className?: string; style?: CSSProperties;
};

export function GameButton({ base, label, title, onClick, disabled, width, height, hoverState = 'Highlighted', stateNames, className, style }: Props) {
  const [hover, setHover] = useState(false);
  const [pressed, setPressed] = useState(false);
  const hoverName = stateNames?.hover ?? hoverState;
  const pressedName = stateNames?.pressed ?? 'Pressed';
  const disabledName = stateNames?.disabled ?? 'Disabled';
  const state = disabled ? disabledName : pressed ? pressedName : hover ? hoverName : 'Normal';
  return (
    <button
      type="button" title={title} disabled={disabled} onClick={onClick}
      className={`${s.btn} ${className ?? ''}`}
      style={{ width, height, backgroundImage: `url(${tex(`${base}${state}`)})`, ...style }}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => { setHover(false); setPressed(false); }}
      onMouseDown={() => setPressed(true)} onMouseUp={() => setPressed(false)}
    >
      {label && <span className={s.label}>{label}</span>}
    </button>
  );
}
