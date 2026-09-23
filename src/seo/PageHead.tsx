import { useEffect, useRef } from 'react';
import { useRoute } from '@/lib/router';
import { useI18n } from '@/lib/i18n';
import { metaFor, type PageMeta } from './meta';

// Langue des balises écrites par le serveur, lue avant que l'application ne modifie <html lang>.
const SERVER_LANG = typeof document !== 'undefined' ? document.documentElement.lang : '';

/** Élément du `<head>` trouvé par `attr="key"`, créé s'il manque. */
function headTag(tag: 'meta' | 'link', attr: string, key: string) {
  let el = document.head.querySelector<HTMLElement>(`${tag}[${attr}="${key}"]`);
  if (!el) {
    el = document.createElement(tag);
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  return el;
}

export function applyHead(m: PageMeta, { keepTitle = false } = {}) {
  if (!keepTitle) document.title = m.title;
  const named = (name: string, content: string) => headTag('meta', 'name', name).setAttribute('content', content);
  const prop = (property: string, content: string) => headTag('meta', 'property', property).setAttribute('content', content);
  named('description', m.description);
  named('robots', m.robots);
  headTag('link', 'rel', 'canonical').setAttribute('href', m.canonical);
  prop('og:type', m.type);
  prop('og:title', m.title);
  prop('og:description', m.description);
  prop('og:url', m.canonical);
  prop('og:image', m.image);
  named('twitter:title', m.title);
  named('twitter:description', m.description);
  named('twitter:image', m.image);
  document.head.querySelectorAll('link[rel="alternate"][hreflang]').forEach(el => el.remove());
  for (const a of m.alternates) {
    const link = document.createElement('link');
    Object.assign(link, { rel: 'alternate', hreflang: a.hreflang, href: a.href });
    document.head.appendChild(link);
  }
  document.head.querySelectorAll('script[type="application/ld+json"]').forEach(el => el.remove());
  for (const data of m.jsonLd) {
    const script = document.createElement('script');
    script.type = 'application/ld+json';
    script.textContent = JSON.stringify(data);
    document.head.appendChild(script);
  }
}

/**
 * Balises de la page à chaque navigation. Au premier affichage, le serveur a déjà écrit les
 * bonnes (y compris l'extrait des entrées du Lorebook, qu'il est seul à connaître) : on n'y
 * touche que si la langue de l'interface diffère de la sienne.
 */
export function PageHead() {
  const { path, query } = useRoute();
  const { lang } = useI18n();
  const first = useRef(true);
  const search = query.toString();
  useEffect(() => {
    const initial = first.current;
    first.current = false;
    // Le tableau de bord gère lui-même son titre.
    if (path === '/stats') return;
    if (initial && (lang === SERVER_LANG || path.startsWith('/lorebook/'))) return;
    // Entrée du Lorebook : son titre est posé par `EntryView` une fois le texte chargé.
    const entry = /^\/lorebook\/[^/]+\/[^/]+/.test(path) && !path.startsWith('/lorebook/search');
    applyHead(metaFor(path, new URLSearchParams(search), { acceptLanguage: lang }), { keepTitle: entry });
  }, [path, search, lang]);
  return null;
}
