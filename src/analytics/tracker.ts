import type { CollectEvent } from './api';

/**
 * Traceur d'audience, sans cookie (voir `src/analytics/api.ts`) : une vue par changement de
 * chemin, un ping toutes les 20 s tant que l'onglet est visible (présence en direct, durée), une
 * fin de vue à la navigation suivante ou à la fermeture. Tout part par `sendBeacon`, sans
 * jamais bloquer la page ; une erreur réseau est ignorée.
 */

const ENDPOINT = '/api/collect';
const SESSION_KEY = 'allodex:session';
export const PING_INTERVAL = 20_000;

type View = { id: string; path: string; visibleMs: number; visibleSince: number | null };

export function randomId(): string {
  const bytes = new Uint8Array(12);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/** Provenance de la première vue : paramètre de campagne s'il y en a un, sinon le référent du navigateur. */
export function entryReferrer(search: string, documentReferrer: string): string | undefined {
  const query = new URLSearchParams(search);
  return query.get('utm_source') ?? query.get('ref') ?? (documentReferrer || undefined);
}

export function createTracker(send: (event: CollectEvent) => void, now: () => number = () => performance.now()) {
  let session = '';
  let fresh = false;
  let view: View | null = null;

  function ensureSession() {
    if (session) return;
    try { session = sessionStorage.getItem(SESSION_KEY) ?? ''; } catch { /* stockage indisponible */ }
    if (!session) {
      session = randomId();
      fresh = true;
      try { sessionStorage.setItem(SESSION_KEY, session); } catch { /* stockage indisponible */ }
    }
  }

  const duration = (v: View) => Math.round(v.visibleMs + (v.visibleSince === null ? 0 : now() - v.visibleSince));
  const base = (v: View) => ({ session, view: v.id, path: v.path });

  return {
    view(path: string, lang: string, extra: { search: string; referrer: string; width: number; visible: boolean }) {
      ensureSession();
      if (view?.path === path) return;
      if (view) send({ type: 'leave', ...base(view), duration: duration(view) });
      view = { id: randomId(), path, visibleMs: 0, visibleSince: extra.visible ? now() : null };
      send({ type: 'view', ...base(view), lang, width: extra.width, referrer: fresh ? entryReferrer(extra.search, extra.referrer) : undefined });
      fresh = false;
    },
    ping() {
      if (view && view.visibleSince !== null) send({ type: 'ping', ...base(view), duration: duration(view) });
    },
    visibility(visible: boolean) {
      if (!view) return;
      if (visible && view.visibleSince === null) {
        view.visibleSince = now();
        send({ type: 'ping', ...base(view), duration: duration(view) });
      } else if (!visible && view.visibleSince !== null) {
        view.visibleMs += now() - view.visibleSince;
        view.visibleSince = null;
        send({ type: 'ping', ...base(view), duration: duration(view) });
      }
    },
    leave() {
      if (!view) return;
      send({ type: 'leave', ...base(view), duration: duration(view) });
      view = null;
    },
  };
}

export function beacon(event: CollectEvent) {
  const body = JSON.stringify(event);
  try {
    if (navigator.sendBeacon?.(ENDPOINT, new Blob([body], { type: 'text/plain' }))) return;
  } catch { /* repli sur fetch */ }
  fetch(ENDPOINT, { method: 'POST', body, keepalive: true, headers: { 'Content-Type': 'text/plain' } }).catch(() => {});
}
