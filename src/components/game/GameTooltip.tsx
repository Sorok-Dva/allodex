import { useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { sprite, spriteSize } from '@/lib/assets';
import s from './GameTooltip.module.css';

const MARGIN = 8;
const GAP = 8;

type Props = {
  anchor: DOMRect | null;
  title?: string;
  hint?: string;
  children?: ReactNode;
  className?: string;
};

export function GameTooltip({ anchor, title, hint, children, className }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<CSSProperties>({ visibility: 'hidden' });

  useLayoutEffect(() => {
    const el = ref.current;
    if (!anchor || !el) { setPos({ visibility: 'hidden' }); return; }
    const rect = el.getBoundingClientRect();
    let top = anchor.bottom + GAP;
    if (top + rect.height + MARGIN > window.innerHeight) top = anchor.top - rect.height - GAP;
    top = Math.min(Math.max(top, MARGIN), Math.max(MARGIN, window.innerHeight - rect.height - MARGIN));

    let left = anchor.left + anchor.width / 2 - rect.width / 2;
    left = Math.min(Math.max(left, MARGIN), Math.max(MARGIN, window.innerWidth - rect.width - MARGIN));

    setPos({ top, left, visibility: 'visible' });
  }, [anchor, title, hint, children]);

  if (!anchor) return null;

  const info = spriteSize('tooltip-frame');
  const [top, right, bottom, left] = info?.slice ?? [4, 4, 4, 4];
  const frameStyle: CSSProperties = {
    borderImageSource: `url(${sprite('tooltip-frame')})`,
    borderImageSlice: `${top} ${right} ${bottom} ${left}`,
    borderImageWidth: `${top}px ${right}px ${bottom}px ${left}px`,
    borderWidth: `${top}px ${right}px ${bottom}px ${left}px`,
    ...pos,
  };

  return (
    <div ref={ref} className={`${s.tooltip} ${className ?? ''}`} style={frameStyle}>
      {title && <div className={s.title}>{title}</div>}
      {children && <div className={s.body}>{children}</div>}
      {hint && (
        <>
          <div className={s.sep} />
          <div className={s.hint}>{hint}</div>
        </>
      )}
    </div>
  );
}
