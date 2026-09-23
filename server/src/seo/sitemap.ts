import { LORE_LANGS, LORE_SECTIONS, PAGES, PAGE_IDS, SEO_LANGS } from '../../../src/seo/meta.ts';
import type { LoreIndex } from './lore.ts';

/**
 * Plan du site : un index (`/sitemap.xml`), les pages et rubriques (`/sitemaps/pages.xml`), puis
 * un fichier par section du Lorebook. Chaque variante de langue est une URL, avec ses
 * alternatives hreflang (langue de l'interface `?lang=`, langue du texte `?text=` au Lorebook).
 */

type Variant = { hreflang: string; href: string };

const xml = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function urlset(groups: Variant[][]): string {
  const out = ['<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">'];
  for (const variants of groups) {
    const links = variants.map(v => `<xhtml:link rel="alternate" hreflang="${v.hreflang}" href="${xml(v.href)}"/>`).join('');
    for (const v of variants) out.push(`<url><loc>${xml(v.href)}</loc>${links}</url>`);
  }
  out.push('</urlset>');
  return out.join('\n');
}

export function createSitemaps(site: string, lore: LoreIndex) {
  const uiVariants = (path: string): Variant[] => [
    ...SEO_LANGS.map(lang => ({ hreflang: lang, href: `${site}${path}?lang=${lang}` })),
    { hreflang: 'x-default', href: `${site}${path}` },
  ];
  const textVariants = (path: string): Variant[] =>
    LORE_LANGS.map(lang => ({ hreflang: lang, href: lang === 'en' ? `${site}${path}` : `${site}${path}?text=${lang}` }));

  const files = new Map<string, () => string>();
  files.set('pages', () => urlset([
    ...PAGE_IDS.map(id => uiVariants(PAGES[id].path)),
    ...LORE_SECTIONS.map(section => textVariants(`/lorebook/${section}`)),
  ]));
  for (const section of LORE_SECTIONS) {
    if (!lore.ids[section].length) continue;
    files.set(`lorebook-${section}`, () => urlset(lore.ids[section].map(id => textVariants(`/lorebook/${section}/${encodeURIComponent(id)}`))));
  }

  const cache = new Map<string, string>();
  return {
    index(): string {
      return ['<?xml version="1.0" encoding="UTF-8"?>',
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        ...[...files.keys()].map(name => `<sitemap><loc>${site}/sitemaps/${name}.xml</loc></sitemap>`),
        '</sitemapindex>'].join('\n');
    },
    file(name: string): string | undefined {
      const build = files.get(name);
      if (!build) return undefined;
      let body = cache.get(name);
      if (!body) cache.set(name, body = build());
      return body;
    },
    robots(): string {
      return ['User-agent: *', 'Allow: /', 'Disallow: /api/', 'Disallow: /stats', 'Disallow: /lorebook/search', '',
        `Sitemap: ${site}/sitemap.xml`, ''].join('\n');
    },
  };
}
