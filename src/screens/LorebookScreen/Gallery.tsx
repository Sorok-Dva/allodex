import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '@/lib/i18n';
import { imageUrl } from './lorebook.data';
import type { Img } from './lorebook.logic';
import s from './LorebookScreen.module.css';

/** Vignettes affichées avant « tout afficher » (un album peut en compter plusieurs centaines). */
export const GALLERY_PREVIEW = 24;

function Lightbox({ images, index, onIndex, onClose }: { images: Img[]; index: number; onIndex: (i: number) => void; onClose: () => void }) {
  const { t } = useI18n();
  const closeRef = useRef<HTMLButtonElement>(null);
  const [id, w, h] = images[index];
  const step = useCallback((d: number) => onIndex((index + d + images.length) % images.length), [index, images.length, onIndex]);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    return () => previous?.focus?.();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); onClose(); }
      else if (e.key === 'ArrowRight') { e.preventDefault(); step(1); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, step]);

  return createPortal(
    <div className={s.lightbox} role="dialog" aria-modal="true" aria-label={t('lore.gallery')} onClick={e => { if (e.target === e.currentTarget) onClose(); }} data-testid="lore-lightbox">
      <img key={id} className={s.lightboxImage} src={imageUrl(id)} width={w} height={h} alt="" />
      <div className={s.lightboxBar}>
        {images.length > 1 && <button type="button" onClick={() => step(-1)} aria-label={t('lore.gallery.prev')}>‹</button>}
        <span className={s.lightboxPos}>{t('lore.gallery.position', { n: index + 1, count: images.length })}</span>
        {images.length > 1 && <button type="button" onClick={() => step(1)} aria-label={t('lore.gallery.next')}>›</button>}
        <a href={imageUrl(id)} target="_blank" rel="noopener noreferrer">{t('lore.gallery.original')}</a>
        <button ref={closeRef} type="button" onClick={onClose} aria-label={t('lore.gallery.close')}>✕</button>
      </div>
    </div>,
    document.body,
  );
}

/** Grille de vignettes (chargement différé) ; un clic ouvre la visionneuse (flèches, Échap). */
export function Gallery({ images, compact = false }: { images: Img[]; compact?: boolean }) {
  const { t } = useI18n();
  const [open, setOpen] = useState<number | null>(null);
  const [all, setAll] = useState(false);
  const close = useCallback(() => setOpen(null), []);
  if (!images.length) return null;
  const shown = all ? images : images.slice(0, GALLERY_PREVIEW);
  return (
    <div className={`${s.gallery} ${compact ? s.galleryCompact : ''}`} data-testid="lore-gallery">
      <ul className={s.thumbs}>
        {shown.map(([id, w, h], i) => (
          <li key={id}>
            <button type="button" className={s.thumb} onClick={() => setOpen(i)} aria-label={t('lore.gallery.open', { n: i + 1 })}>
              <img src={imageUrl(id, true)} alt="" loading="lazy" decoding="async" width={w} height={h} />
            </button>
          </li>
        ))}
      </ul>
      {!all && images.length > GALLERY_PREVIEW && (
        <button type="button" className={s.more} onClick={() => setAll(true)}>{t('lore.gallery.showAll', { count: images.length })}</button>
      )}
      {open !== null && <Lightbox images={images} index={open} onIndex={setOpen} onClose={close} />}
    </div>
  );
}
