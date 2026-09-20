import type { MusicTrack } from '@/lib/assets';
import zones from './music-zones.json';

const rules = zones.zones.map(zone => ({ ...zone, regex: zone.pattern ? new RegExp(zone.pattern, 'i') : null }));
const zoneGroups = new Set(['Zones', ...rules.flatMap(zone => zone.groups ?? [])]);
export const musicGroup = (track: MusicTrack) => zoneGroups.has(track.group) ? 'Zones' : track.group;
export function musicZone(track: MusicTrack) {
  if (musicGroup(track) !== 'Zones') return null;
  return rules.find(zone => zone.groups?.includes(track.group) || zone.regex?.test(track.name)) ?? zones.fallback;
}
export function musicSubcategories(tracks: MusicTrack[]) {
  return [...rules, zones.fallback].map(zone => ({
    id: zone.id, title: zone.title, tracks: tracks.filter(track => musicZone(track)?.id === zone.id),
  })).filter(zone => zone.tracks.length > 0);
}
export const musicQueueKey = (track: MusicTrack) => musicZone(track)?.id ?? musicGroup(track);
