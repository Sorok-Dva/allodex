import type { CSSProperties, ReactNode } from 'react';
import { tex } from '@/lib/assets';
import s from './GameFrame.module.css';

type Slice = { top: number; right: number; bottom: number; left: number };
type Props = { texture: string; slice: Slice; className?: string; style?: CSSProperties; children?: ReactNode; fill?: boolean };

export function GameFrame({ texture, slice, className, style, children, fill = true }: Props) {
  const { top, right, bottom, left } = slice;
  const frameStyle: CSSProperties = {
    borderImageSource: `url(${tex(texture)})`,
    borderImageSlice: `${top} ${right} ${bottom} ${left}${fill ? ' fill' : ''}`,
    borderImageWidth: `${top}px ${right}px ${bottom}px ${left}px`,
    borderWidth: `${top}px ${right}px ${bottom}px ${left}px`,
    ...style,
  };
  return <div className={`${s.frame} ${className ?? ''}`} style={frameStyle}>{children}</div>;
}
