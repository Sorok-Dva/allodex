import type { MusicTrack } from '@/lib/assets';
import zones from './music-zones.json';

type ArchiveConfidence = 'confirmed' | 'probable' | 'inferred' | 'unknown';
type ArchiveMusicTrack = MusicTrack & {
  maps?: string[];
  introducedIn?: string | null;
  archiveConfidence?: ArchiveConfidence;
  archiveSources?: string[];
  archiveNote?: string;
};

type ZoneRule = (typeof zones.zones)[number] & {
  groups: string[];
  pattern: string | null;
  mapPatterns: string[];
};

const rules = (zones.zones as ZoneRule[]).map(zone => ({
  ...zone,
  regex: zone.pattern ? new RegExp(zone.pattern, 'i') : null,
  mapRegexes: (zone.mapPatterns ?? []).map(pattern => new RegExp(pattern, 'i')),
}));

const zoneGroups = new Set(['Zones', ...rules.flatMap(zone => zone.groups ?? [])]);
const archiveTrack = (track: MusicTrack) => track as ArchiveMusicTrack;

export const musicMaps = (track: MusicTrack) => archiveTrack(track).maps ?? [];
export const musicIntroducedIn = (track: MusicTrack) => archiveTrack(track).introducedIn ?? null;
export const musicArchiveConfidence = (track: MusicTrack) => archiveTrack(track).archiveConfidence ?? 'unknown';
export const musicArchiveNote = (track: MusicTrack) => archiveTrack(track).archiveNote ?? null;
export const musicArchiveSources = (track: MusicTrack) => archiveTrack(track).archiveSources ?? [];

export const musicGroup = (track: MusicTrack) => zoneGroups.has(track.group) ? 'Zones' : track.group;

export function musicZone(track: MusicTrack) {
  if (musicGroup(track) !== 'Zones') return null;

  const maps = musicMaps(track);

  // Structured archive metadata always wins over the old filename heuristics.
  const metadataRule = rules.find(zone =>
    zone.groups?.includes(track.group)
    || maps.some(map => zone.mapRegexes.some(regex => regex.test(map)))
  );
  if (metadataRule) return metadataRule;

  // Keep legacy/internal-name classification for tracks whose map is still unknown.
  return rules.find(zone => zone.regex?.test(track.name)) ?? zones.fallback;
}

export function musicSubcategories(tracks: MusicTrack[]) {
  return [...rules, zones.fallback].map(zone => ({
    id: zone.id,
    title: zone.title,
    tracks: tracks.filter(track => musicZone(track)?.id === zone.id),
  })).filter(zone => zone.tracks.length > 0);
}

export const musicQueueKey = (track: MusicTrack) => musicZone(track)?.id ?? musicGroup(track);
