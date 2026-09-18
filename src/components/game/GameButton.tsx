import { useState, type CSSProperties, type ReactNode } from 'react';
import { tex } from '@/lib/assets';
import s from './GameButton.module.css';

type Props = {
  base: string; label?: ReactNode; title?: string; onClick?: () => void; disabled?: boolean;
  width: number; height: number; hoverState?: string; className?: string; style?: CSSProperties;
};

export function GameButton({ base, label, title, onClick, disabled, width, height, hoverState = 'Highlighted', className, style }: Props) {
  const [hover, setHover] = useState(false);
  const [pressed, setPressed] = useState(false);
  const state = disabled ? 'Disabled' : pressed ? 'Pressed' : hover ? hoverState : 'Normal';
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
