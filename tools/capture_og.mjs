#!/usr/bin/env node
/**
 * Captures Open Graph du site (aperçus de partage) : une image 1200×630 par page, en JPEG,
 * dans `public/og/`. Chaque vue est rendue par Chromium headless à une taille d'écran donnée,
 * recadrée sur la zone la plus riche (même ratio 1.905), puis réduite dans un canevas.
 *
 * Usage : node tools/capture_og.mjs --base http://localhost:5193 [--only home,talents]
 *
 * Le serveur (Vite ou build servi) doit tourner à part. Playwright n'est pas une dépendance du
 * dépôt : chemin de son `index.mjs` dans la variable `PLAYWRIGHT`.
 */
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const PLAYWRIGHT = process.env.PLAYWRIGHT ?? 'playwright';
const { chromium } = await import(PLAYWRIGHT);

const args = process.argv.slice(2);
const opt = name => { const i = args.indexOf(`--${name}`); return i >= 0 ? args[i + 1] : undefined; };
const BASE = (opt('base') ?? 'http://localhost:5193').replace(/\/$/, '');
const ONLY = opt('only')?.split(',');
const OUT = path.resolve(import.meta.dirname, '..', 'public', 'og');

const W = 1200, H = 630;
const QUALITY = 0.82;
const MAX_BYTES = 250_000;

// Build de mage 17.0 complet (livre et trois champs) : les icônes allumées font la couleur.
const MAGE_BUILD = '1.3330333030303003001000000000300000030303.uDH-DHgB.AAC_IDjLMvBI.AAG8jHOgC8jG-';

/**
 * `view` : taille d'écran CSS ; `clip` : zone retenue (largeur seule, la hauteur suit le ratio),
 * absente = tout l'écran. `settle` : attente après chargement, pour les vidéos et la 3D.
 */
const SHOTS = [
  { name: 'home', url: '/?skipIntro', view: [1600, 840] },
  // Variante sans l'interface : le logo et les personnages du fond animé.
  { name: 'default', url: '/?skipIntro', view: [1920, 1008], clip: { x: 500, y: 60, w: 1420 } },
  { name: 'achievements', url: '/achievements', view: [1280, 672] },
  { name: 'chronicles', url: '/chronicles?v=13.0', view: [1920, 1008] },
  { name: 'music', url: '/music', view: [1280, 672] },
  { name: 'cinematics', url: '/cinematics', view: [1920, 1008], clip: { x: 190, y: 98, w: 1543 } },
  { name: 'talents', url: `/talents?v=17.0&c=mage&b=${MAGE_BUILD}`, view: [1920, 1008], clip: { x: 55, y: 150, w: 1345 } },
  { name: 'lorebook', url: '/lorebook', view: [1280, 672] },
  { name: 'lorebook-entry', url: '/lorebook/atlas/a-a001', view: [1920, 1008], clip: { x: 285, y: 0, w: 1350 } },
];

const withLang = url => `${url}${url.includes('?') ? '&' : '?'}lang=en`;

/** Attend polices, images et vidéos réellement affichées (au moins une seconde de lecture). */
async function settle(page, ms) {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() => {
    const imgs = [...document.images].every(i => i.complete);
    const vids = [...document.querySelectorAll('video')].every(v => v.readyState >= 2 && v.currentTime > 1);
    return imgs && vids;
  }, null, { polling: 500, timeout: 60_000 }).catch(() => console.warn('  médias incomplets, capture quand même'));
  await page.mouse.move(2, 2);
  await page.waitForTimeout(ms);
}

/** Réduit la capture PNG en 1200×630 JPEG dans un canevas ; baisse la qualité si trop lourd. */
async function toJpeg(scaler, png) {
  let q = QUALITY, buf;
  for (;;) {
    const dataUrl = await scaler.evaluate(async ({ src, w, h, q }) => {
      const img = new Image();
      img.src = src;
      await img.decode();
      const c = document.createElement('canvas');
      c.width = w; c.height = h;
      const g = c.getContext('2d');
      g.imageSmoothingEnabled = true;
      g.imageSmoothingQuality = 'high';
      g.drawImage(img, 0, 0, w, h);
      return c.toDataURL('image/jpeg', q);
    }, { src: `data:image/png;base64,${png.toString('base64')}`, w: W, h: H, q });
    buf = Buffer.from(dataUrl.split(',')[1], 'base64');
    if (buf.length <= MAX_BYTES || q <= 0.5) return { buf, q };
    q = Math.round((q - 0.05) * 100) / 100;
  }
}

await mkdir(OUT, { recursive: true });
const browser = await chromium.launch({
  args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist',
    '--autoplay-policy=no-user-gesture-required'],
});
const scaler = await (await browser.newContext()).newPage();

for (const shot of SHOTS) {
  if (ONLY && !ONLY.includes(shot.name)) continue;
  const [vw, vh] = shot.view;
  const ctx = await browser.newContext({ viewport: { width: vw, height: vh }, locale: 'en-US' });
  const page = await ctx.newPage();
  await page.goto(BASE + withLang(shot.url), { waitUntil: 'networkidle', timeout: 120_000 });
  await settle(page, shot.settle ?? 2500);
  const clip = shot.clip
    ? { x: shot.clip.x, y: shot.clip.y, width: shot.clip.w, height: Math.round(shot.clip.w * H / W) }
    : undefined;
  const png = await page.screenshot({ clip, timeout: 180_000 });
  await ctx.close();
  const { buf, q } = await toJpeg(scaler, png);
  await writeFile(path.join(OUT, `${shot.name}.jpg`), buf);
  console.log(`${shot.name}.jpg  ${(buf.length / 1024).toFixed(0)} Ko  q=${q}  ${shot.url}`);
}

await browser.close();
