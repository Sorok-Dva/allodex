/**
 * Texture « cuite » d'un personnage, composée comme le client : la peau choisie (teinte de
 * peau appliquée à travers le masque alpha de l'`IndexedTexture`), puis les patchs des objets
 * portés (visage, cuir chevelu teint de la couleur des cheveux, signe additionnel, pièces de
 * tenue) posés dans leurs rectangles. Les rectangles sont en coordonnées de texture du jeu :
 * `x1, x2, y1, y2`, V = 0 en bas de l'image.
 */

export type BakeLayer = {
  image: CanvasImageSource & { width: number; height: number };
  /** Rectangle cible ; absent = toute la texture. */
  rect?: [number, number, number, number];
  /** Couleur multipliée (`#rrggbb`), le blanc ne change rien. */
  tint?: string;
  /** Teinte appliquée à travers l'alpha de l'image (peau), l'image étant ensuite rendue opaque. */
  tintThroughAlpha?: boolean;
};

export type CanvasFactory = (w: number, h: number) => HTMLCanvasElement | OffscreenCanvas;

export const defaultCanvas: CanvasFactory = (w, h) => {
  if (typeof OffscreenCanvas !== 'undefined') return new OffscreenCanvas(w, h);
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  return c;
};

/** Rectangle du jeu (`x1, x2, y1, y2`, V vers le haut) → rectangle de canevas en pixels. */
export function rectToPixels(rect: [number, number, number, number], width: number, height: number): [number, number, number, number] {
  const [x1, x2, y1, y2] = rect;
  return [Math.round(x1 * width), Math.round((1 - y2) * height), Math.round((x2 - x1) * width), Math.round((y2 - y1) * height)];
}

export function parseHex(color: string): [number, number, number] {
  const n = parseInt(color.replace('#', ''), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function isWhite(color: string | undefined): boolean {
  return !color || color.toLowerCase() === '#ffffff';
}

type Ctx2D = CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;

/** Multiplie les pixels RVB par la couleur ; `throughAlpha` : mélange selon l'alpha puis opaque. */
export function tintPixels(data: Uint8ClampedArray, color: string, throughAlpha: boolean): void {
  const [r, g, b] = parseHex(color);
  for (let i = 0; i < data.length; i += 4) {
    if (throughAlpha) {
      const a = data[i + 3] / 255;
      data[i] = data[i] * (1 - a + a * r / 255);
      data[i + 1] = data[i + 1] * (1 - a + a * g / 255);
      data[i + 2] = data[i + 2] * (1 - a + a * b / 255);
      data[i + 3] = 255;
    } else {
      data[i] = data[i] * r / 255;
      data[i + 1] = data[i + 1] * g / 255;
      data[i + 2] = data[i + 2] * b / 255;
    }
  }
}

export function composeBaked(size: number, layers: BakeLayer[], makeCanvas: CanvasFactory = defaultCanvas): HTMLCanvasElement | OffscreenCanvas {
  const canvas = makeCanvas(size, size);
  const ctx = canvas.getContext('2d') as Ctx2D;
  ctx.fillStyle = '#808080';
  ctx.fillRect(0, 0, size, size);
  for (const layer of layers) {
    const [x, y, w, h] = layer.rect ? rectToPixels(layer.rect, size, size) : [0, 0, size, size];
    if (w <= 0 || h <= 0) continue;
    if (!layer.tint || (isWhite(layer.tint) && !layer.tintThroughAlpha)) {
      if (layer.tintThroughAlpha) {
        // Peau blanche : l'image reste telle quelle mais opaque (l'alpha n'est qu'un masque).
        const tmp = makeCanvas(w, h);
        const tctx = tmp.getContext('2d') as Ctx2D;
        tctx.drawImage(layer.image, 0, 0, w, h);
        const px = tctx.getImageData(0, 0, w, h);
        for (let i = 3; i < px.data.length; i += 4) px.data[i] = 255;
        tctx.putImageData(px, 0, 0);
        ctx.drawImage(tmp, x, y);
      } else {
        ctx.drawImage(layer.image, x, y, w, h);
      }
      continue;
    }
    const tmp = makeCanvas(w, h);
    const tctx = tmp.getContext('2d') as Ctx2D;
    tctx.drawImage(layer.image, 0, 0, w, h);
    const px = tctx.getImageData(0, 0, w, h);
    tintPixels(px.data, layer.tint, !!layer.tintThroughAlpha);
    tctx.putImageData(px, 0, 0);
    ctx.drawImage(tmp, x, y);
  }
  return canvas;
}
