import { useEffect, useState } from 'react';
import type { ClassTalents, TalentsIndex, UiLayout } from './talents.types';
import { talentsFile } from './talents.logic';

const cache = new Map<string, Promise<unknown>>();

export function loadJson<T>(url: string, fetcher: typeof fetch = fetch): Promise<T> {
  let p = cache.get(url) as Promise<T> | undefined;
  if (!p) {
    p = fetcher(url).then(res => {
      if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
      return res.json() as Promise<T>;
    });
    p.catch(() => cache.delete(url));
    cache.set(url, p);
  }
  return p;
}

export function clearTalentsCache() { cache.clear(); }

export type Loaded<T> = { data: T | null; error: string | null; loading: boolean };

export function useJson<T>(url: string | null): Loaded<T> {
  const [state, setState] = useState<Loaded<T>>({ data: null, error: null, loading: Boolean(url) });
  useEffect(() => {
    if (!url) { setState({ data: null, error: null, loading: false }); return; }
    let alive = true;
    setState(s => ({ data: s.data, error: null, loading: true }));
    loadJson<T>(url).then(
      data => { if (alive) setState({ data, error: null, loading: false }); },
      err => { if (alive) setState({ data: null, error: String(err?.message ?? err), loading: false }); },
    );
    return () => { alive = false; };
  }, [url]);
  return state;
}

export const useTalentsIndex = () => useJson<TalentsIndex>('/game/talents/index.json');
export const useUiLayout = () => useJson<UiLayout>('/game/talents/ui/talent_builder.json');
export const useClassTalents = (version: string | null, slug: string | null) =>
  useJson<ClassTalents>(version && slug ? talentsFile(version, slug) : null);
