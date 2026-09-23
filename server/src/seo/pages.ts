import fs from 'node:fs';
import path from 'node:path';
import { metaFor, renderHead, type PageMeta } from '../../../src/seo/meta.ts';
import type { LoreIndex } from './lore.ts';

const SEO_BLOCK = /<!--seo-->[\s\S]*?<!--\/seo-->/;

/**
 * Page HTML d'une URL : `dist/index.html` dont le bloc `<!--seo-->…<!--/seo-->` reçoit les
 * balises de la page. Le gabarit est relu quand un nouveau build le remplace.
 */
export function createPageRenderer(distDir: string, siteUrl: string, lore: LoreIndex) {
  const file = path.join(distDir, 'index.html');
  let template: string | null = null;
  let mtime = 0;
  let checked = 0;
  const images = new Map<string, boolean>();
  // Image Open Graph absente de dist/og/ (pas encore capturée) : l'image générique du site.
  const withImage = (meta: PageMeta): PageMeta => {
    const name = /\/og\/([\w-]+)\.jpg$/.exec(meta.image)?.[1];
    if (!name || name === 'default') return meta;
    let found = images.get(name);
    if (found === undefined) images.set(name, found = fs.existsSync(path.join(distDir, 'og', `${name}.jpg`)));
    return found ? meta : { ...meta, image: `${siteUrl}/og/default.jpg` };
  };

  function current(now: number) {
    if (now - checked > 2000) {
      checked = now;
      try {
        const stat = fs.statSync(file);
        if (stat.mtimeMs !== mtime) {
          template = fs.readFileSync(file, 'utf8');
          mtime = stat.mtimeMs;
          images.clear();
        }
      } catch {
        template = null;
      }
    }
    return template;
  }

  return function render(pathname: string, search: string, acceptLanguage: string | null, now = Date.now()) {
    const html = current(now);
    if (!html) return null;
    const meta = withImage(metaFor(pathname, new URLSearchParams(search), { site: siteUrl, acceptLanguage, lore: lore.resolve }));
    const head = `<!--seo-->\n    ${renderHead(meta)}\n    <!--/seo-->`;
    return {
      status: meta.status,
      html: html.replace(SEO_BLOCK, () => head).replace(/<html lang="[^"]*"/, `<html lang="${meta.lang}"`),
    };
  };
}
