import { useEffect, useState } from 'react';
import { loadManifest, cursor, hasAssets } from '@/lib/assets';
import { useRoute } from '@/lib/router';
import { AudioProvider } from '@/lib/audio/AudioProvider';
import { OpeningScreen } from '@/screens/OpeningScreen/OpeningScreen';
import { MedalsScreen } from '@/screens/MedalsScreen/MedalsScreen';
import { ChroniclesScreen } from '@/screens/ChroniclesScreen/ChroniclesScreen';

export default function App() {
  const [ready, setReady] = useState(false);
  const { path } = useRoute();
  useEffect(() => { loadManifest().then(() => setReady(true)); }, []);
  useEffect(() => { document.body.style.cursor = `url(${cursor('Default')}), auto`; }, []);
  if (!ready) return null;
  return (
    <AudioProvider>
      {import.meta.env.DEV && !hasAssets() && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, zIndex: 99, background: '#a33', color: '#fff', padding: 6, textAlign: 'center', fontSize: 14 }}>
          Assets du jeu absents : lancez <code>npm run extract</code>
        </div>
      )}
      {path === '/succes' ? <MedalsScreen /> : path === '/chroniques' ? <ChroniclesScreen /> : <OpeningScreen />}
    </AudioProvider>
  );
}
