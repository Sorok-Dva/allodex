import { Suspense, lazy, useEffect, useState } from 'react';
import { loadManifest, cursor, hasAssets } from '@/lib/assets';
import { useRoute } from '@/lib/router';
import { AudioProvider } from '@/lib/audio/AudioProvider';
import { I18nProvider } from '@/lib/i18n';
import { OpeningScreen } from '@/screens/OpeningScreen/OpeningScreen';
import { MedalsScreen } from '@/screens/MedalsScreen/MedalsScreen';
import { ChroniclesScreen } from '@/screens/ChroniclesScreen/ChroniclesScreen';
import { MusicScreen } from '@/screens/MusicScreen/MusicScreen';
import { LegalScreen } from '@/screens/LegalScreen/LegalScreen';
import { FatalitiesScreen } from '@/screens/FatalitiesScreen/FatalitiesScreen';
import { TalentsScreen } from '@/screens/TalentsScreen/TalentsScreen';

// Création de personnage : fonction de test, absente du build de production (la condition
// `import.meta.env.DEV` est remplacée par `false` au build, l'import dynamique disparaît).
const CharacterCreationScreen = import.meta.env.DEV
  ? lazy(() => import('@/screens/CharacterCreationScreen/CharacterCreationScreen'))
  : null;
import { LorebookScreen } from '@/screens/LorebookScreen/LorebookScreen';
import { CinematicsScreen } from '@/screens/CinematicsScreen/CinematicsScreen';

// Tableau de bord d'audience : chargé à part, seul l'administrateur y accède.
const StatsScreen = lazy(() => import('@/screens/StatsScreen/StatsScreen'));

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
       path === '/fatalities' || path === '/fatalites' ? <FatalitiesScreen /> :
       CharacterCreationScreen && (path === '/character' || path === '/personnage') ? <Suspense fallback={null}><CharacterCreationScreen /></Suspense> :
       path === '/talents' ? <TalentsScreen /> :
       path === '/lorebook' || path.startsWith('/lorebook/') ? <LorebookScreen /> :
       path === '/cinematics' || path === '/cinematiques' ? <CinematicsScreen /> :
       path === '/stats' ? <Suspense fallback={null}><StatsScreen /></Suspense> :
       <OpeningScreen />}
    </AudioProvider>
    </I18nProvider>
  );
}
