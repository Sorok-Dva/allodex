import { useEffect, useState, type CSSProperties } from 'react';
import type { UiLayer } from '@/data/character/chargen.types';

const tinted = new Map<string, Promise<string>>();

/**
 * Image teinte comme le fait le client (couleur ARGB du calque multipliée aux pixels, alpha
 * de l'image conservé et multiplié par l'alpha de la couleur), mise en cache en URL `data:`.
 */
export function tintedUrl(url: string, argb: string, additive = false): Promise<string> {
  const key = `${url}|${argb}|${additive}`;
  if (!tinted.has(key)) {
    tinted.set(key, new Promise<string>(resolve => {
      const img = new Image();
      img.onload = () => {
        const c = document.createElement('canvas');
        c.width = img.naturalWidth;
        c.height = img.naturalHeight;
        const ctx = c.getContext('2d');
        if (!ctx) { resolve(url); return; }
        ctx.drawImage(img, 0, 0);
        const px = ctx.getImageData(0, 0, c.width, c.height);
        const p = px.data;
        if (needsTint(argb)) {
          // Teinte au pixel (le composite `multiply` du canevas mélange la couleur pure aux pixels
          // semi-transparents : les fonds de groupe des races sortaient en aplats vifs).
          const n = parseInt(argb.slice(2), 16);
          const tr = ((n >> 16) & 255) / 255, tg = ((n >> 8) & 255) / 255, tb = (n & 255) / 255;
          for (let i = 0; i < p.length; i += 4) { p[i] *= tr; p[i + 1] *= tg; p[i + 2] *= tb; }
        }
        if (additive) {
          // Mélange additif rendu en alpha : l'interface est un groupe isolé (mise à l'échelle),
          // `mix-blend-mode` n'y verrait pas la scène. Alpha = composante la plus forte, couleur
          // redressée : le noir devient transparent, les lueurs gardent leur éclat.
          for (let i = 0; i < p.length; i += 4) {
            const a = Math.max(p[i], p[i + 1], p[i + 2]) * (p[i + 3] / 255);
            if (a > 0) { const k = 255 / Math.max(p[i], p[i + 1], p[i + 2]); p[i] *= k; p[i + 1] *= k; p[i + 2] *= k; }
            p[i + 3] = a;
          }
        }
        ctx.putImageData(px, 0, 0);
        resolve(c.toDataURL());
      };
      img.onerror = () => resolve(url);
      img.src = url;
    }));
  }
  return tinted.get(key)!;
}

function needsTint(color: string): boolean {
  return color.slice(2).toLowerCase() !== 'ffffff';
}

/**
 * Calque d'un widget : texture étirée (`SimpleTexture`) ou découpée en neuf (`TiledTexture` :
 * `tile = [haut, gauche, largeur du milieu, hauteur du milieu, droite, bas]`, bords fixes,
 * milieu étiré), teinte et opacité de la couleur du calque.
 */
export function GameLayer({ layer, url, className, style }: { layer: UiLayer; url: string | null; className?: string; style?: CSSProperties }) {
  const plain = !needsTint(layer.color) && !layer.blend;
  const [src, setSrc] = useState<string | null>(url && plain ? url : null);
  useEffect(() => {
    let alive = true;
    if (!url) { setSrc(null); return; }
    if (plain) { setSrc(url); return; }
    void tintedUrl(url, layer.color, !!layer.blend).then(u => { if (alive) setSrc(u); });
    return () => { alive = false; };
  }, [url, layer.color, layer.blend, plain]);
  if (!src) return null;
  const alpha = parseInt(layer.color.slice(0, 2), 16) / 255;
  const base: CSSProperties = { position: 'absolute', inset: 0, opacity: alpha, pointerEvents: 'none', ...style };
  if (layer.tile) {
    const [top, left, , , right, bottom] = layer.tile;
    return (
      <div className={className} style={{
        ...base,
        borderStyle: 'solid',
        borderWidth: `${top}px ${right}px ${bottom}px ${left}px`,
        borderImageSource: `url(${src})`,
        borderImageSlice: `${top} ${right} ${bottom} ${left} fill`,
        borderImageRepeat: 'stretch',
      }} />
    );
  }
  return <div className={className} style={{ ...base, backgroundImage: `url(${src})`, backgroundSize: '100% 100%' }} />;
}
