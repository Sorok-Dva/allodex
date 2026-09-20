import { describe, expect, it } from 'vitest';
import { musicGroup, musicZone, musicSubcategories } from './music.logic';
import type { MusicTrack } from '@/lib/assets';
const track = (name: string, group = 'Zones'): MusicTrack => ({ id: name, name, group, bank: '', title: null, duration: 1, ogg: '', mp3: '', client: '' });
describe('classement des musiques', () => {
  it('regroupe les préfixes fournis et toutes les variantes Umoir', () => {
    expect(musicZone(track('ZL1_Main_1'))?.title.fr).toBe('Kania');
    expect(musicZone(track('ZE2_BaseGuard_NM'))?.title.fr).toBe('Empire');
    expect(musicZone(track('Airin_Castle_Indoor'))?.title).toEqual({ fr: 'Irene', en: 'Iren' });
    for (const name of ['umoir_common', 'UmoirAwry_II', 'UmoirFly', 'UmoirMoundDungeonAdaptive']) {
      expect(musicZone(track(name))?.title.fr).toBe('Umoira');
    }
  });
  it('replace les banques récentes sous Zones et conserve toutes les pistes inconnues', () => {
    const tracks = ['Eden', 'Jigran', 'Kadagan', 'Kvator'].map(group => track('Music', group));
    tracks.push(track('AC5_Main_NM'), track('ZL1_Main_1'));
    expect(tracks.every(t => musicGroup(t) === 'Zones')).toBe(true);
    const children = musicSubcategories(tracks);
    expect(children.flatMap(c => c.tracks)).toHaveLength(tracks.length);
    expect(children.find(c => c.id === 'other')?.tracks[0].name).toBe('AC5_Main_NM');
    expect(musicZone(track('ZL1_Main_1', 'Menu'))).toBeNull();
  });
});
