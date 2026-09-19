import { useEffect, useState, type ReactNode, type MouseEvent } from 'react';

function read() {
  return { path: window.location.pathname, query: new URLSearchParams(window.location.search) };
}

/**
 * `replace: true` remplace l'entrée d'historique courante au lieu d'en empiler une
 * nouvelle : la frise des Chroniques change de version sans remplir l'historique, et
 * le bouton « précédent » ramène d'où l'on venait.
 */
export function navigate(to: string, opts: { replace?: boolean } = {}) {
  if (opts.replace) window.history.replaceState(null, '', to);
  else window.history.pushState(null, '', to);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

export function useRoute() {
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const onPop = () => setRoute(read());
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);
  return route;
}

export function Link({ to, children, className }: { to: string; children: ReactNode; className?: string }) {
  const onClick = (e: MouseEvent) => { e.preventDefault(); navigate(to); };
  return <a href={to} onClick={onClick} className={className}>{children}</a>;
}
