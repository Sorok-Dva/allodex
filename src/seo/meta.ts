/**
 * Métadonnées de référencement des pages (titre, description, URL canonique, Open Graph,
 * hreflang, JSON-LD). Module pur, partagé par le client (titre de l'onglet, balises mises à
 * jour à chaque navigation) et par le serveur (`server/`), qui les écrit dans le HTML envoyé :
 * les robots des réseaux sociaux n'exécutent pas le JavaScript. Pas d'alias `@/` ici, le
 * serveur importe ce fichier directement.
 */

export const SITE_URL = 'https://allodex.eu';
export const SITE_NAME = 'Allodex';

export const SEO_LANGS = ['fr', 'en'] as const;
export type SeoLang = (typeof SEO_LANGS)[number];
export const LORE_LANGS = ['en', 'fr', 'ru'] as const;
export type LoreLang = (typeof LORE_LANGS)[number];

type Copy = { title: string; description: string };
type PageDef = { path: string; aliases?: string[]; image: string; fr: Copy; en: Copy; label: Record<SeoLang, string> };

export const PAGES = {
  home: {
    path: '/', image: 'home', label: { fr: 'Accueil', en: 'Home' },
    fr: {
      title: "Allodex — Encyclopédie fan d'Allods Online",
      description: "Lore officiel, arbres de talents de la 1.1 à la 17.0, cinématiques, musiques et succès d'Allods Online, rendus avec l'interface et les assets du jeu.",
    },
    en: {
      title: 'Allodex — Allods Online fan encyclopedia',
      description: "Official lore, talent trees from 1.1 to 17.0, cinematics, music and achievements of Allods Online, rendered with the game's own interface and assets.",
    },
  },
  lorebook: {
    path: '/lorebook', image: 'lorebook', label: { fr: 'Lorebook', en: 'Lorebook' },
    fr: {
      title: "Lorebook d'Allods Online : histoire, atlas, personnages — Allodex",
      description: "Le lore officiel d'Allods Online : chronologie de Sarnaut, atlas des allods, bibliothèque, personnages, quêtes et secrets du monde, avec recherche et liens croisés.",
    },
    en: {
      title: 'Allods Online Lorebook: history, atlas, characters — Allodex',
      description: 'The official lore of Allods Online: Sarnaut timeline, atlas of the allods, library, characters, quests and world secrets, fully searchable and cross-linked.',
    },
  },
  talents: {
    path: '/talents', image: 'talents', label: { fr: 'Talents', en: 'Talents' },
    fr: {
      title: 'Calculateur de talents Allods Online (1.1 à 17.0) — Allodex',
      description: "Les arbres de talents de chaque classe d'Allods Online, de la 1.1 à la 17.0, dans la fenêtre du jeu. Créez, comparez et partagez vos builds.",
    },
    en: {
      title: 'Allods Online talent calculator (1.1 to 17.0) — Allodex',
      description: "Talent trees of every Allods Online class from 1.1 to 17.0, in the game's own window. Plan, compare and share your builds.",
    },
  },
  cinematics: {
    path: '/cinematics', aliases: ['/cinematiques'], image: 'cinematics', label: { fr: 'Cinématiques', en: 'Cinematics' },
    fr: {
      title: "Cinématiques d'Allods Online en film complet — Allodex",
      description: "Toutes les cinématiques d'Allods Online montées en film, par faction (Ligue, Empire), avec les sous-titres officiels français, anglais et russes.",
    },
    en: {
      title: 'Allods Online cinematics: the full movie — Allodex',
      description: 'Every Allods Online cinematic cut into a full movie per faction (League, Empire), with official English, French and Russian subtitles.',
    },
  },
  chronicles: {
    path: '/chronicles', aliases: ['/chroniques'], image: 'chronicles', label: { fr: 'Chroniques', en: 'Chronicles' },
    fr: {
      title: "Chroniques d'Allods Online : les écrans de lancement — Allodex",
      description: "L'histoire d'Allods Online version par version, de la 1.0 à la 17.0 : écrans de connexion, scènes de menu et thème musical de chaque extension.",
    },
    en: {
      title: 'Allods Online Chronicles: every login screen — Allodex',
      description: 'The history of Allods Online version by version, from 1.0 to 17.0: login screens, menu scenes and the theme music of each expansion.',
    },
  },
  music: {
    path: '/music', aliases: ['/musiques'], image: 'music', label: { fr: 'Musiques', en: 'Music' },
    fr: {
      title: "Musiques d'Allods Online : la bande originale — Allodex",
      description: "Écoutez la bande originale d'Allods Online : menus, zones, peuples, instruments, Astral et donjons, issus des clients français et russe.",
    },
    en: {
      title: 'Allods Online soundtrack: the full music catalogue — Allodex',
      description: 'Listen to the Allods Online soundtrack: menus, zones, races, instruments, Astral and dungeons, from the French and Russian clients.',
    },
  },
  achievements: {
    path: '/achievements', aliases: ['/medals', '/succes'], image: 'achievements', label: { fr: 'Succès', en: 'Achievements' },
    fr: {
      title: "Succès d'Allods Online — Allodex",
      description: "Les succès d'Allods Online dans le panneau Succès du jeu : catégories, paliers et récompenses.",
    },
    en: {
      title: 'Allods Online achievements — Allodex',
      description: "Allods Online achievements in the game's own Achievements panel: categories, tiers and rewards.",
    },
  },
  terms: {
    path: '/terms', aliases: ['/cgu', '/legal'], image: 'default', label: { fr: 'CGU', en: 'Terms of use' },
    fr: {
      title: "Conditions générales d'utilisation — Allodex",
      description: "Conditions d'utilisation d'Allodex, site fan indépendant consacré à Allods Online.",
    },
    en: {
      title: 'Terms of use — Allodex',
      description: 'Terms of use of Allodex, an independent fan site dedicated to Allods Online.',
    },
  },
} satisfies Record<string, PageDef>;

export type PageId = keyof typeof PAGES;
export const PAGE_IDS = Object.keys(PAGES) as PageId[];

/** Pages servies mais à ne pas indexer (outils internes, fonctions de développement). */
const PRIVATE_PATHS = ['/stats', '/fatalities', '/fatalites', '/auras', '/character', '/personnage'];

export const LORE_SECTIONS = ['timeline', 'atlas', 'library', 'characters', 'secrets', 'quests', 'gallery'] as const;
export type LoreSection = (typeof LORE_SECTIONS)[number] | 'dialogues';

export const LORE_SECTION_COPY: Record<LoreSection, Record<SeoLang, Copy>> = {
  timeline: {
    fr: { title: 'Chronologie', description: "La chronologie de Sarnaut : les grands événements de l'histoire d'Allods Online, des ères anciennes à l'âge de l'Astral." },
    en: { title: 'Timeline', description: "The timeline of Sarnaut: the major events of Allods Online's history, from the ancient eras to the age of the Astral." },
  },
  atlas: {
    fr: { title: 'Atlas', description: "L'atlas des allods d'Allods Online : îles, archipels, climats, factions et seigneurs de chaque allod." },
    en: { title: 'Atlas', description: 'The atlas of the Allods Online allods: islands, archipelagos, climates, factions and holders of every allod.' },
  },
  library: {
    fr: { title: 'Bibliothèque', description: "Les livres, lettres et documents d'Allods Online, rassemblés dans la bibliothèque du Lorebook." },
    en: { title: 'Library', description: 'The books, letters and documents of Allods Online, gathered in the Lorebook library.' },
  },
  characters: {
    fr: { title: 'Personnages', description: "Les personnages d'Allods Online : héros, PNJ, boss et figures de l'histoire de Sarnaut." },
    en: { title: 'Characters', description: 'The characters of Allods Online: heroes, NPCs, bosses and figures of Sarnaut history.' },
  },
  secrets: {
    fr: { title: 'Secrets du monde', description: "Les secrets du monde d'Allods Online, découverts au fil de l'exploration de Sarnaut." },
    en: { title: 'World Secrets', description: 'The world secrets of Allods Online, uncovered while exploring Sarnaut.' },
  },
  quests: {
    fr: { title: 'Quêtes', description: "Les quêtes d'Allods Online et leurs textes : objectifs, dialogues et récits de chaque allod." },
    en: { title: 'Quests', description: 'Allods Online quests and their texts: objectives, dialogues and stories of every allod.' },
  },
  gallery: {
    fr: { title: 'Galerie', description: "Cartes, captures et illustrations des allods d'Allods Online, réunies par Makar Terentiev pour son atlas." },
    en: { title: 'Gallery', description: 'Maps, screenshots and illustrations of the Allods Online allods, gathered by Makar Terentiev for his atlas.' },
  },
  dialogues: {
    fr: { title: 'Dialogues', description: "Répliques de PNJ d'Allods Online." },
    en: { title: 'Dialogues', description: 'Allods Online NPC lines.' },
  },
};

export type Alternate = { hreflang: string; href: string };

export type PageMeta = {
  title: string;
  description: string;
  lang: string;
  /** URL absolue canonique. */
  canonical: string;
  /** URL absolue de l'image Open Graph (1200 × 630). */
  image: string;
  robots: 'index,follow' | 'noindex,follow' | 'noindex,nofollow';
  alternates: Alternate[];
  type: 'website' | 'article';
  jsonLd: object[];
  /** Code HTTP que le serveur doit renvoyer avec la page. */
  status: 200 | 404;
};

/** Entrée du Lorebook telle que le serveur la résout (titre et extrait dans la langue du texte). */
export type LoreEntry = { section: LoreSection; id: string; title: string; description: string };

const og = (site: string, image: string) => `${site}/og/${image}.jpg`;

function withQuery(site: string, path: string, key: string, value: string | null) {
  return `${site}${path}${value ? `?${key}=${value}` : ''}`;
}

export function normalizePath(path: string): string {
  const clean = path.replace(/\/{2,}/g, '/').replace(/(.)\/+$/, '$1') || '/';
  for (const page of Object.values(PAGES) as PageDef[]) if (page.aliases?.includes(clean)) return page.path;
  return clean;
}

export function pageIdFor(path: string): PageId | null {
  const clean = normalizePath(path);
  return (PAGE_IDS.find(id => PAGES[id].path === clean) ?? null);
}

export const isPrivatePath = (path: string) => PRIVATE_PATHS.includes(normalizePath(path));

/** Langue de l'interface : `?lang=`, sinon l'en-tête Accept-Language (même règle que le client), sinon le français. */
export function seoLang(query: URLSearchParams, acceptLanguage?: string | null): SeoLang {
  const asked = query.get('lang');
  if (asked === 'fr' || asked === 'en') return asked;
  return acceptLanguage?.trim().toLowerCase().startsWith('en') ? 'en' : 'fr';
}

export function loreLang(query: URLSearchParams): LoreLang {
  const asked = query.get('text');
  return asked === 'fr' || asked === 'ru' ? asked : 'en';
}

const ORG = { '@type': 'VideoGame', name: 'Allods Online' };

function breadcrumbs(site: string, items: { name: string; path: string }[]) {
  return {
    '@context': 'https://schema.org', '@type': 'BreadcrumbList',
    itemListElement: items.map((item, i) => ({ '@type': 'ListItem', position: i + 1, name: item.name, item: `${site}${item.path}` })),
  };
}

function langAlternates(site: string, path: string): Alternate[] {
  return [
    ...SEO_LANGS.map(lang => ({ hreflang: lang, href: withQuery(site, path, 'lang', lang) })),
    { hreflang: 'x-default', href: `${site}${path}` },
  ];
}

function loreAlternates(site: string, path: string): Alternate[] {
  return [
    ...LORE_LANGS.map(lang => ({ hreflang: lang, href: withQuery(site, path, 'text', lang === 'en' ? null : lang) })),
    { hreflang: 'x-default', href: `${site}${path}` },
  ];
}

function pageMeta(site: string, id: PageId, lang: SeoLang, explicitLang: boolean): PageMeta {
  const page: PageDef = PAGES[id];
  const copy = page[lang];
  const jsonLd: object[] = [];
  if (id === 'home') {
    jsonLd.push({
      '@context': 'https://schema.org', '@type': 'WebSite', name: SITE_NAME, url: `${site}/`, inLanguage: lang, about: ORG,
      potentialAction: { '@type': 'SearchAction', target: `${site}/lorebook/search?q={search_term_string}`, 'query-input': 'required name=search_term_string' },
    });
  } else {
    jsonLd.push(breadcrumbs(site, [{ name: SITE_NAME, path: '/' }, { name: page.label[lang], path: page.path }]));
  }
  return {
    title: copy.title, description: copy.description, lang,
    canonical: explicitLang ? withQuery(site, page.path, 'lang', lang) : `${site}${page.path}`,
    image: og(site, page.image), robots: 'index,follow', alternates: langAlternates(site, page.path),
    type: 'website', jsonLd, status: 200,
  };
}

function uiCopy(lang: LoreLang): SeoLang {
  return lang === 'fr' ? 'fr' : 'en';
}

/**
 * Métadonnées d'une URL. `lore` résout une entrée du Lorebook (côté serveur : index chargé
 * depuis `dist/game/lorebook/`) ; `undefined` = entrée inconnue (404), fonction absente =
 * résolution impossible (côté client : titre générique, l'écran l'affine lui-même).
 */
export function metaFor(
  pathname: string,
  query: URLSearchParams,
  opts: { site?: string; acceptLanguage?: string | null; lore?: (section: string, id: string, lang: LoreLang) => LoreEntry | undefined } = {},
): PageMeta {
  const site = opts.site ?? SITE_URL;
  const path = normalizePath(pathname);
  const lang = seoLang(query, opts.acceptLanguage);
  const explicitLang = query.has('lang');
  const id = pageIdFor(path);
  if (id) return pageMeta(site, id, lang, explicitLang);

  const lorebook = PAGES.lorebook;
  const parts = path.split('/').filter(Boolean).map(p => { try { return decodeURIComponent(p); } catch { return p; } });
  if (parts[0] === 'lorebook') {
    const text = loreLang(query);
    const ui = uiCopy(text);
    if (parts[1] === 'search') {
      return { ...pageMeta(site, 'lorebook', lang, explicitLang), robots: 'noindex,follow', canonical: `${site}/lorebook/search` };
    }
    const section = parts[1] as LoreSection;
    if (Object.hasOwn(LORE_SECTION_COPY, section) && !parts[3]) {
      const sectionCopy = LORE_SECTION_COPY[section][ui];
      const sectionPath = `/lorebook/${section}`;
      const crumbs = [{ name: SITE_NAME, path: '/' }, { name: lorebook.label[ui], path: lorebook.path }, { name: sectionCopy.title, path: sectionPath }];
      if (!parts[2]) {
        return {
          title: `${sectionCopy.title} — Allods Online Lorebook — ${SITE_NAME}`, description: sectionCopy.description, lang: text,
          canonical: withQuery(site, sectionPath, 'text', text === 'en' ? null : text), image: og(site, 'lorebook'),
          robots: section === 'dialogues' ? 'noindex,follow' : 'index,follow', alternates: loreAlternates(site, sectionPath),
          type: 'website', jsonLd: [breadcrumbs(site, crumbs)], status: 200,
        };
      }
      const entryPath = `${sectionPath}/${encodeURIComponent(parts[2])}`;
      const generic = {
        title: `${sectionCopy.title} — Allods Online Lorebook — ${SITE_NAME}`, description: lorebook[ui].description, lang: text,
        canonical: withQuery(site, entryPath, 'text', text === 'en' ? null : text), image: og(site, 'lorebook-entry'),
        robots: 'index,follow' as const, alternates: loreAlternates(site, entryPath), type: 'article' as const, jsonLd: [], status: 200 as const,
      };
      if (!opts.lore) return generic;
      const entry = opts.lore(section, parts[2], text);
      if (!entry) return { ...generic, robots: 'noindex,follow', alternates: [], status: 404 };
      return {
        ...generic,
        title: loreEntryTitle(entry.title, sectionCopy.title),
        description: entry.description || sectionCopy.description,
        robots: section === 'dialogues' ? 'noindex,follow' : 'index,follow',
        jsonLd: [
          breadcrumbs(site, [...crumbs, { name: entry.title, path: entryPath }]),
          {
            '@context': 'https://schema.org', '@type': 'Article', headline: entry.title, description: entry.description,
            inLanguage: text, url: generic.canonical, image: generic.image, about: ORG,
            isPartOf: { '@type': 'WebSite', name: SITE_NAME, url: `${site}/` },
          },
        ],
      };
    }
  }

  const home = pageMeta(site, 'home', lang, explicitLang);
  if (isPrivatePath(path)) return { ...home, robots: 'noindex,nofollow', alternates: [], canonical: `${site}${path}` };
  // Chemin inconnu : l'application affiche l'accueil, le serveur répond 404 pour ne pas créer de doublon.
  return { ...home, robots: 'noindex,follow', alternates: [], status: 404 };
}

/** Titre d'une entrée du Lorebook, repris tel quel par l'onglet du navigateur (`EntryView`). */
export function loreEntryTitle(entry: string, section: string): string {
  return `${entry} — ${section} · Allods Online Lorebook`;
}

/** Coupe un texte à `max` caractères sur une fin de mot, avec points de suspension. */
export function excerpt(text: string, max = 160): string {
  const flat = text.replace(/\s+/g, ' ').trim();
  if (flat.length <= max) return flat;
  const cut = flat.slice(0, max - 1);
  const space = cut.lastIndexOf(' ');
  return `${(space > max * 0.6 ? cut.slice(0, space) : cut).replace(/[\s,;:.—–-]+$/, '')}…`;
}

const escapeHtml = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const OG_LOCALE: Record<string, string> = { fr: 'fr_FR', en: 'en_US', ru: 'ru_RU' };

/** Balises `<head>` d'une page, écrites par le serveur entre les marqueurs `<!--seo-->` d'index.html. */
export function renderHead(meta: PageMeta): string {
  const e = escapeHtml;
  const tags = [
    `<title>${e(meta.title)}</title>`,
    `<meta name="description" content="${e(meta.description)}" />`,
    `<meta name="robots" content="${meta.robots}" />`,
    `<link rel="canonical" href="${e(meta.canonical)}" />`,
    ...meta.alternates.map(a => `<link rel="alternate" hreflang="${a.hreflang}" href="${e(a.href)}" />`),
    `<meta property="og:site_name" content="${SITE_NAME}" />`,
    `<meta property="og:type" content="${meta.type}" />`,
    `<meta property="og:title" content="${e(meta.title)}" />`,
    `<meta property="og:description" content="${e(meta.description)}" />`,
    `<meta property="og:url" content="${e(meta.canonical)}" />`,
    `<meta property="og:image" content="${e(meta.image)}" />`,
    `<meta property="og:image:width" content="1200" />`,
    `<meta property="og:image:height" content="630" />`,
    `<meta property="og:locale" content="${OG_LOCALE[meta.lang] ?? 'fr_FR'}" />`,
    `<meta name="twitter:card" content="summary_large_image" />`,
    `<meta name="twitter:title" content="${e(meta.title)}" />`,
    `<meta name="twitter:description" content="${e(meta.description)}" />`,
    `<meta name="twitter:image" content="${e(meta.image)}" />`,
    ...meta.jsonLd.map(data => `<script type="application/ld+json">${JSON.stringify(data).replace(/</g, '\\u003c')}</script>`),
  ];
  return tags.join('\n    ');
}
