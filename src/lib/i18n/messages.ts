/**
 * Chaînes de l'interface, par langue. Le français est la langue de référence : toute
 * clé doit exister dans les deux langues (vérifié par un test). Les libellés produits
 * par les données (« Allods Online - Game of Gods (3.0) », noms de pistes) ne passent
 * pas par ici.
 */
export const MESSAGES = {
  fr: {
    'audio.mute': 'Couper le son',
    'audio.unmute': 'Activer le son',
    'common.close': 'Fermer',
    'chronicles.previous': 'Version précédente',
    'chronicles.next': 'Version suivante',
    'chronicles.about': 'À propos de cette version',
    'chronicles.aboutOf': 'À propos de {label}',
    'chronicles.release': 'Sortie :',
    'chronicles.highlights': 'Au programme',
    'chronicles.pending': 'Fiche à venir.',
    'chronicles.archiveMissing': 'Archive non extraite',
    'chronicles.archiveMissingHint': 'Lancez',
    'chronicles.mediaMissing': 'Média non extrait',
    'chronicles.mediaMissingHint': "Le client de cette version n'était pas monté au moment de l'extraction.",
    'chronicles.launchScreen': 'Écran de lancement — {label}',
    'theme.play': 'Lire le thème',
    'theme.pause': 'Mettre le thème en pause',
    'theme.unavailable': 'Thème indisponible',
    'theme.kind': 'Thème du menu',
    'theme.notAvailable': 'Thème non disponible',
    'theme.notExtracted': 'Thème non extrait',
  },
  en: {
    'audio.mute': 'Mute',
    'audio.unmute': 'Unmute',
    'common.close': 'Close',
    'chronicles.previous': 'Previous version',
    'chronicles.next': 'Next version',
    'chronicles.about': 'About this version',
    'chronicles.aboutOf': 'About {label}',
    'chronicles.release': 'Released:',
    'chronicles.highlights': 'Highlights',
    'chronicles.pending': 'Details coming soon.',
    'chronicles.archiveMissing': 'Archive not extracted',
    'chronicles.archiveMissingHint': 'Run',
    'chronicles.mediaMissing': 'Media not extracted',
    'chronicles.mediaMissingHint': 'The client for this version was not mounted when the archive was extracted.',
    'chronicles.launchScreen': 'Launch screen — {label}',
    'theme.play': 'Play theme',
    'theme.pause': 'Pause theme',
    'theme.unavailable': 'Theme unavailable',
    'theme.kind': 'Menu theme',
    'theme.notAvailable': 'Theme not available',
    'theme.notExtracted': 'Theme not extracted',
  },
} as const;

export type Lang = keyof typeof MESSAGES;
export type MessageKey = keyof typeof MESSAGES.fr;
export const LANGS: readonly Lang[] = ['fr', 'en'];
