import { useEffect, useState, type DependencyList } from 'react';

export type Async<T> = { data?: T; error?: unknown; loading: boolean };

/** Résultat d'une promesse recalculée quand `deps` change ; l'ancienne réponse est ignorée. */
export function useAsync<T>(fn: () => Promise<T> | undefined, deps: DependencyList): Async<T> {
  const [state, setState] = useState<Async<T>>({ loading: true });
  useEffect(() => {
    let alive = true;
    const p = fn();
    if (!p) { setState({ loading: false }); return; }
    setState(prev => ({ data: prev.data, loading: true }));
    p.then(data => { if (alive) setState({ data, loading: false }); },
      error => { if (alive) setState({ error, loading: false }); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}
