import { useEffect, useState } from 'react';
import { loadManifest, cursor, hasAssets } from '@/lib/assets';
import { useRoute } from '@/lib/router';

export default function App() {
  const [ready, setReady] = useState(false);
  const { path } = useRoute();
  useEffect(() => { loadManifest().then(() => setReady(true)); }, []);
  useEffect(() => { document.body.style.cursor = `url(${cursor('Default')}), auto`; }, []);
  if (!ready) return null;
  return (
    <>
      {import.meta.env.DEV && !hasAssets() && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, zIndex: 99, background: '#a33', color: '#fff', padding: 6, textAlign: 'center', fontSize: 14 }}>
          Assets du jeu absents : lancez <code>npm run extract</code>
        </div>
      )}
      {path === '/succes' ? <div style={{ color: '#fff' }}>succès (Task 7)</div> : <div style={{ color: '#fff' }}>ouverture (Task 6)</div>}
    </>
  );
}
