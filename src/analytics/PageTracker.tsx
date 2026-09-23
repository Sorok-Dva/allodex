import { useEffect, useRef } from 'react';
import { useRoute } from '@/lib/router';
import { useI18n } from '@/lib/i18n';
import { PING_INTERVAL, TRACKING_ENABLED as ENABLED, beacon, createTracker } from './tracker';

/** Mesure d'audience : une vue par chemin, présence en direct et durée de visibilité. */
export function PageTracker() {
  const { path } = useRoute();
  const { lang } = useI18n();
  const tracker = useRef<ReturnType<typeof createTracker> | null>(null);

  useEffect(() => {
    if (!ENABLED) return;
    const t = tracker.current = createTracker(beacon);
    const onVisibility = () => t.visibility(document.visibilityState === 'visible');
    const onHide = () => t.leave();
    const timer = window.setInterval(() => t.ping(), PING_INTERVAL);
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('pagehide', onHide);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('pagehide', onHide);
      t.leave();
    };
  }, []);

  useEffect(() => {
    tracker.current?.view(path, lang, {
      search: window.location.search, referrer: document.referrer, width: window.screen.width,
      visible: document.visibilityState === 'visible',
    });
  }, [path]); // eslint-disable-line react-hooks/exhaustive-deps -- la langue accompagne la vue, elle n'en crée pas

  return null;
}
