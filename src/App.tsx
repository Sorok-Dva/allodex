import { useEffect, useState } from 'react';
import { loadManifest, cursor, hasAssets } from '@/lib/assets';
import { useRoute } from '@/lib/router';
import { AudioProvider } from '@/lib/audio/AudioProvider';
import { I18nProvider } from '@/lib/i18n';
import { OpeningScreen } from '@/screens/OpeningScreen/OpeningScreen';
import { MedalsScreen } from '@/screens/MedalsScreen/MedalsScreen';
import { ChroniclesScreen } from '@/screens/ChroniclesScreen/ChroniclesScreen';
import { MusicScreen } from '@/screens/MusicScreen/MusicScreen';
import { LegalScreen } from '@/screens/LegalScreen/LegalScreen';

export default function App() {
  const [ready, setReady] = useState(false);
  const { path } = useRoute();
  useEffect(() => { loadManifest().then(() => setReady(true)); }, []);
  useEffect(() => { document.body.style.cursor = `url(${cursor('Default')}), auto`; }, []);
  if (!ready) return null;
  return (
    <I18nProvider>
    <AudioProvider>
      {import.meta.env.DEV && !hasAssets() && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, zIndex: 99, background: '#a33', color: '#fff', padding: 6, textAlign: 'center', fontSize: 14 }}>
          Assets du jeu absents : lancez <code>npm run extract</code>
        </div>
      )}
      {path === '/terms' || path === '/cgu' || path === '/legal' ? <LegalScreen /> :
       path === '/achievements' || path === '/medals' || path === '/succes' ? <MedalsScreen /> :
       path === '/chronicles' || path === '/chroniques' ? <ChroniclesScreen /> :
       path === '/music' || path === '/musiques' ? <MusicScreen /> :
       <OpeningScreen />}
    </AudioProvider>
    </I18nProvider>
  );
}
