import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { T, archiveEntries, archiveFile, sprite, tex, type ArchiveEntry } from '@/lib/assets';
import { navigate, useRoute } from '@/lib/router';
import { useGameAudio } from '@/lib/audio/useGameAudio';
import { useI18n } from '@/lib/i18n';
import { hasWebGL } from '@/lib/webgl';
import { nineSlice } from '@/lib/nineSlice';
import { GameStrip } from '@/components/ui/GameStrip';
import { SpeakerToggle } from '@/components/controls/SpeakerToggle';
import { FullscreenToggle } from '@/components/controls/FullscreenToggle';
import { VersionTimeline } from './VersionTimeline';
import { ThemePlayer } from './ThemePlayer';
import { VersionInfoPanel, type VersionInfo } from './VersionInfoPanel';
import versionsJson from '@/data/versions.json';
import s from './ChroniclesScreen.module.css';

/** Fiches par version (clés `"4.0"`…) ; `_note` est la documentation du fichier. */
const VERSION_INFOS = versionsJson as Record<string, VersionInfo | string | undefined>;
const infoFor = (version: string): VersionInfo | undefined => {
  const info = VERSION_INFOS[version];
  return typeof info === 'object' ? info : undefined;
};

/** Bouton « ? » des fenêtres du jeu (Contextructor/CornerQuestion) : base + halo au survol. */
const HELP_TEX = 'Interface/Ingame/Contextructor/CornerQuestion/CornerQuestion';


/** Fondu croisé d'une version à l'autre (image/vidéo et thème), spec § 4. */
const CROSSFADE_MS = 600;
/** Temps d'affichage d'une version sans thème avant de passer à la suivante. */
const NO_THEME_DWELL_MS = 20_000;

const hasMedia = (entry: ArchiveEntry) =>
  (entry.media === 'video' && !!entry.video) || (entry.media === 'image' && !!entry.background);

// La scène 3D tire `three` derrière elle : chargement à la demande, pour que les autres
// écrans du site n'en paient pas le poids.
const MenuScene = lazy(() => import('@/components/scene/MenuScene'));

/**
 * Écran de lancement d'une version, en plein écran : la vidéo du menu en boucle quand
 * le client en avait une, la scène 3D animée du menu (4.0 → 8.0) quand elle a été
 * exportée et que le navigateur sait la rendre, sinon le fond statique. Version dont le
 * média n'a pas été extrait (client absent) : fond `Background_14_0_Temp` assombri.
 */
function MediaLayer({ entry, onReady }: { entry: ArchiveEntry; onReady?: () => void }) {
  const { t } = useI18n();
  const scene = entry.media === 'image' && entry.scene && hasWebGL() ? entry.scene : null;
  // Un média immédiat (vidéo, image, fond de secours) est « prêt » dès son montage ; la
  // scène 3D ne le devient qu'à sa première image rendue (onReady de MenuScene).
  const readyRef = useRef(onReady);
  readyRef.current = onReady;
  useEffect(() => { if (!scene) readyRef.current?.(); }, [scene]);

  if (entry.media === 'video' && entry.video) {
    return (
      <video className={s.media} autoPlay loop muted playsInline>
        <source src={archiveFile(entry.version, entry.video.webm)} type="video/webm" />
        <source src={archiveFile(entry.version, entry.video.mp4)} type="video/mp4" />
      </video>
    );
  }
  if (entry.media === 'image' && entry.background) {
    // Avec la scène, l'illustration officielle n'est pas affichée : elle ne représente pas
    // la scène et jurerait sous elle. La couche précédente reste visible jusqu'à la
    // première image de la scène, qui apparaît alors en fondu (voir les couches plus bas).
    if (scene) {
      return (
        <Suspense fallback={null}>
          <MenuScene
            glbUrl={archiveFile(entry.version, scene.glb)}
            metaUrl={archiveFile(entry.version, scene.meta)}
            onReady={() => readyRef.current?.()}
          />
        </Suspense>
      );
    }
    return (
      <img
        className={s.media}
        src={archiveFile(entry.version, entry.background)}
        alt={t('chronicles.launchScreen', { label: entry.label })}
      />
    );
  }
  return (
    <div
      className={`${s.media} ${s.mediaMissing}`}
      style={{ backgroundImage: `url(${tex(`${T.main2}/Background_14_0_Temp`)})` }}
      aria-hidden="true"
    />
  );
}

/**
 * Titre de l'écran de lancement : le logo de l'add-on, à sa taille native, centré un
 * peu au-dessus du premier tiers comme dans le jeu. Les versions dont aucun client
 * archivé ne conserve le logo (1.0, 2.0, 11.0, 12.0) affichent le libellé en toutes
 * lettres dans la police du jeu. Le `key` sur la version relance l'apparition en fondu
 * à chaque changement.
 */
function LaunchTitle({ entry }: { entry: ArchiveEntry }) {
  if (entry.logo) {
    return (
      <div className={`${s.title} ${entry.version === '7.0' ? s.titleV7 : ''}`}>
        <img
          key={entry.version}
          className={s.logo}
          src={archiveFile(entry.version, entry.logo)}
          alt={entry.label}
          data-testid="version-logo"
        />
      </div>
    );
  }
  return (
    <div className={s.title}>
      <h1 key={entry.version} className={s.plainTitle} data-testid="version-title">{entry.label}</h1>
    </div>
  );
}


export function ChroniclesScreen() {
  const entries = useMemo(() => archiveEntries(), []);
  const { query } = useRoute();
  const { playSfx, playExternal, pauseMusic, resumeAmbient, playing, external, ended } = useGameAudio();
  const { t } = useI18n();

  // La version affichée vit dans l'URL (`?v=8.0`) : partageable, et le bouton
  // « précédent » ramène d'où l'on venait (la frise remplace l'entrée d'historique).
  const requested = entries.findIndex(e => e.version === query.get('v'));
  const index = requested >= 0 ? requested : entries.length - 1;
  const entry: ArchiveEntry | undefined = entries[index];

  const select = useCallback((version: string) => {
    navigate(`/chronicles?v=${encodeURIComponent(version)}`, { replace: true });
  }, []);

  // Fondu croisé du fond : la nouvelle couche se monte par-dessus l'ancienne, qui reste
  // affichée — scène 3D comprise — tant que la nouvelle n'est pas prête (première image
  // de sa scène, ou montage d'un média immédiat), puis encore le temps du fondu, et on
  // ne garde que la dernière. Une scène met plusieurs secondes à charger son `.glb` :
  // sans cette attente, l'écran passerait par du noir ou une illustration sans rapport.
  // Retirer la couche démonte son `<video>` : le navigateur met alors le média en
  // pause et abandonne son décodage — jamais deux vidéos décodées au-delà du fondu,
  // et rien à arrêter à la main (les vidéos sont muettes, elles ne passent pas par le
  // moteur audio).
  const layerKey = useRef(0);
  const [layers, setLayers] = useState<{ key: number; entry: ArchiveEntry }[]>(() => (entry ? [{ key: 0, entry }] : []));
  const [readyKeys, setReadyKeys] = useState<number[]>([]);
  const markReady = useCallback((key: number) => {
    setReadyKeys(prev => (prev.includes(key) ? prev : [...prev, key]));
  }, []);
  useEffect(() => {
    if (!entry) return;
    setLayers(prev => {
      const top = prev[prev.length - 1];
      if (top?.entry.version === entry.version) return prev;
      layerKey.current += 1;
      return [...prev.slice(-1), { key: layerKey.current, entry }];
    });
  }, [entry]);
  useEffect(() => {
    if (layers.length < 2) return;
    const top = layers[layers.length - 1];
    if (!readyKeys.includes(top.key)) return;
    const timer = window.setTimeout(() => setLayers(prev => prev.slice(-1)), CROSSFADE_MS);
    return () => window.clearTimeout(timer);
  }, [layers, readyKeys]);

  // Son d'ouverture du panneau du jeu et reprise de la musique du site en partant.
  useEffect(() => {
    playSfx('medals-open');
    return () => { resumeAmbient({ crossfadeMs: CROSSFADE_MS }); };
  }, [playSfx, resumeAmbient]);

  // `wanted` est l'intention (« le thème doit suivre les changements de version »), à ne
  // pas confondre avec la lecture réelle rapportée par le moteur (`playing`) : la
  // politique d'autoplay peut refuser le démarrage sur une arrivée directe.
  const [wanted, setWanted] = useState(true);
  const [infoOpen, setInfoOpen] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const theme = entry?.theme;
  const themeId = entry && theme ? `archive:${entry.version}` : null;
  const themeSrc = useMemo(
    () => (entry && theme ? { ogg: archiveFile(entry.version, theme.ogg), mp3: archiveFile(entry.version, theme.mp3) } : null),
    [entry, theme],
  );

  useEffect(() => {
    if (!wanted) return;
    if (themeId && themeSrc) {
      playExternal(themeId, themeSrc, { loop: false, crossfadeMs: CROSSFADE_MS });
    } else if (!themeId) {
      pauseMusic();
    }
  }, [themeId, themeSrc, wanted, playExternal, pauseMusic]);

  // Défilement automatique : à la fin du thème (lecture non bouclée), la version
  // suivante prend le relais, et la dernière ramène à la première. Une version sans
  // thème reste affichée `NO_THEME_DWELL_MS` avant de passer la main. Mettre le thème
  // en pause (`wanted` faux) suspend l'enchaînement.
  const nextVersion = entries[(index + 1) % entries.length]?.version;
  useEffect(() => {
    if (!wanted || infoOpen || !nextVersion || !entry || nextVersion === entry.version) return;
    if (themeId) {
      if (ended === themeId) select(nextVersion);
      return;
    }
    const timer = window.setTimeout(() => select(nextVersion), NO_THEME_DWELL_MS);
    return () => window.clearTimeout(timer);
  }, [wanted, infoOpen, nextVersion, entry, themeId, ended, select]);

  /** Le thème de la version affichée joue vraiment (et pas une autre piste). */
  const themePlaying = playing && external === themeId;

  const toggleTheme = useCallback(() => {
    if (themePlaying) { pauseMusic(); setWanted(false); return; }
    // Le clic est lui-même le geste utilisateur qui débloque l'autoplay : on relance
    // sans attendre l'effet, qui ne se redéclencherait pas si `wanted` était déjà vrai.
    setWanted(true);
    if (themeId && themeSrc) playExternal(themeId, themeSrc, { loop: false, crossfadeMs: CROSSFADE_MS });
  }, [themePlaying, pauseMusic, playExternal, themeId, themeSrc]);

  const toggleFullscreen = useCallback(() => {
    playSfx('ui-click');
    setFullscreen(fs => {
      const next = !fs;
      if (next) {
        setInfoOpen(false);
        if (!document.fullscreenElement && document.documentElement.requestFullscreen) {
          document.documentElement.requestFullscreen().catch(() => {});
        }
      } else {
        if (document.fullscreenElement && document.exitFullscreen) {
          document.exitFullscreen().catch(() => {});
        }
      }
      return next;
    });
  }, [playSfx]);

  useEffect(() => {
    const handleFsChange = () => {
      if (!document.fullscreenElement) {
        setFullscreen(false);
      }
    };
    document.addEventListener('fullscreenchange', handleFsChange);
    return () => document.removeEventListener('fullscreenchange', handleFsChange);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'f' || e.key === 'F') {
        e.preventDefault();
        toggleFullscreen();
        return;
      }
      if (e.key === 'Escape') {
        if (fullscreen) {
          e.preventDefault();
          setFullscreen(false);
          if (document.fullscreenElement && document.exitFullscreen) {
            document.exitFullscreen().catch(() => {});
          }
          return;
        }
        if (infoOpen) {
          e.preventDefault();
          setInfoOpen(false);
          return;
        }
      }
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      const next = entries[index + (e.key === 'ArrowRight' ? 1 : -1)];
      if (!next) return;
      e.preventDefault();
      select(next.version);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [entries, fullscreen, index, infoOpen, select, toggleFullscreen]);

  const handleClose = () => {
    playSfx('medals-close');
    navigate('/');
  };

  // Panneau « À propos de cette version » : bouton « ? » du jeu, Échap le ferme. Tant
  // qu'il est ouvert, le défilement automatique attend (on est en train de lire).
  const [helpPressed, setHelpPressed] = useState(false);
  const toggleInfo = useCallback(() => {
    playSfx('ui-click');
    setInfoOpen(open => !open);
  }, [playSfx]);

  const handleScreenClick = () => {
    if (fullscreen) {
      toggleFullscreen();
    }
  };

  return (
    <div className={`${s.screen} ${fullscreen ? s.hudHidden : ''}`} onClick={handleScreenClick}>
      {layers.map((layer, i) => (
        <div key={layer.key} className={`${s.layer} ${i > 0 ? s.fadeIn : ''}`}>
          <MediaLayer entry={layer.entry} onReady={() => markReady(layer.key)} />
        </div>
      ))}
      <div className={`${s.vignette} ${entry.version === '7.0' ? s.vignetteV7 : ''} ${s.hud}`} />

      {entry && <LaunchTitle entry={entry} />}

      {entry ? (
        <div className={`${s.cartouche} ${s.hud}`}>
          <div className={s.plate}>
            <GameStrip base="title-plate" cap={38} />
            <span className={s.plateTitle}>{entry.label}</span>
          </div>
        </div>
      ) : (
        <div className={`${s.card} ${s.hud}`} style={nineSlice('tooltip-frame', [4, 4, 4, 4])}>
          <div className={s.cardTitle}>{t('chronicles.archiveMissing')}</div>
          <div className={s.cardHint}>{t('chronicles.archiveMissingHint')} <code>python3 tools/extract_archive.py</code></div>
        </div>
      )}

      {entry && !hasMedia(entry) && (
        <div className={`${s.card} ${s.hud}`} style={nineSlice('tooltip-frame', [4, 4, 4, 4])}>
          <div className={s.cardTitle}>{t('chronicles.mediaMissing')}</div>
          <div className={s.cardHint}>{t('chronicles.mediaMissingHint')}</div>
        </div>
      )}

      <button
        type="button"
        className={`${s.close} ${s.hud}`}
        style={{ backgroundImage: `url(${sprite('close-button')})` }}
        onClick={handleClose}
        aria-label={t('common.close')}
      />
      <SpeakerToggle className={`${s.speaker} ${s.hud}`} />
      <FullscreenToggle className={`${s.fullscreen} ${s.hud}`} fullscreen={fullscreen} onToggle={toggleFullscreen} />
      {entry && (
        <button
          type="button"
          className={`${s.help} ${s.hud}`}
          onClick={toggleInfo}
          onPointerDown={() => setHelpPressed(true)}
          onPointerUp={() => setHelpPressed(false)}
          onPointerLeave={() => setHelpPressed(false)}
          aria-label={t('chronicles.about')}
          aria-expanded={infoOpen}
          aria-controls="version-info"
        >
          <span className={s.helpBase} style={{ backgroundImage: `url(${tex(`${HELP_TEX}${helpPressed ? 'Pressed' : 'Normal'}`)})` }} />
          <span className={s.helpGlow} style={{ backgroundImage: `url(${tex(`${HELP_TEX}Highlight`)})` }} />
        </button>
      )}
      {entry && infoOpen && <VersionInfoPanel id="version-info" entry={entry} info={infoFor(entry.version)} />}

      {entry && <ThemePlayer entry={entry} playing={themePlaying} onToggle={toggleTheme} className={`${s.player} ${s.hud}`} />}

      {entry && (
        <VersionTimeline entries={entries} active={entry.version} onSelect={select} className={`${s.timeline} ${s.hud}`} />
      )}
    </div>
  );
}
