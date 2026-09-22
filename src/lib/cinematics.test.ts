import { describe, expect, it, vi } from 'vitest';
import {
  bonusStart, chapterAt, chaptersOf, splitBonus, defaultSubtitleLang, filmDuration, filmFor, filmTime, formatDuration, groupByArc,
  isFaction, loadCinematics, nextIndex, subtitleLangs, trackFor, type Cinematic,
} from './cinematics';

function cine(id: string, over: Partial<Cinematic> = {}): Cinematic {
  return {
    id,
    title: { fr: `Titre ${id}`, en: `Title ${id}` },
    faction: 'common',
    order: 100,
    arc: 'invasion',
    version: '7.0',
    duration: 10,
    files: { webm: `${id}/video.webm`, mp4: `${id}/video.mp4`, poster: `${id}/poster.jpg` },
    tracks: [],
    audio: { language: null },
    subtitles: { status: 'none', lines: 0, timing: null },
    source: { client: '17.0', pak: 'data/Packs/Video.pak', entry: `Video/${id}.ogv`, event: `x/${id}` },
    chronology: 'test',
    ...over,
  };
}

const ALL = [
  cine('victory', { order: 260 }),
  cine('league', { faction: 'league', order: 100, arc: 'prologue' }),
  cine('bridge', { order: 210, tracks: [{ lang: 'fr', label: 'Français', src: 'bridge/fr.vtt', lines: 5 }, { lang: 'ru', label: 'Русский', src: 'bridge/ru.vtt', lines: 5 }] }),
  cine('empire', { faction: 'empire', order: 100, arc: 'prologue' }),
  cine('plague', { order: 200 }),
  cine('missing', { order: 150, files: null }),
  cine('forum', { order: 400, arc: 'kyros', tracks: [{ lang: 'en', label: 'English', src: 'forum/en.vtt', lines: 19 }] }),
];

describe('filmFor', () => {
  it('garde la faction et les communes, dans l’ordre chronologique', () => {
    expect(filmFor(ALL, 'league').map(c => c.id)).toEqual(['league', 'plague', 'bridge', 'victory', 'forum']);
    expect(filmFor(ALL, 'empire').map(c => c.id)).toEqual(['empire', 'plague', 'bridge', 'victory', 'forum']);
  });
  it('écarte les vidéos non extraites', () => {
    expect(filmFor(ALL, 'league').some(c => c.id === 'missing')).toBe(false);
  });
  it('départage deux cinématiques de même rang par leur identifiant', () => {
    const film = filmFor([cine('b', { order: 5 }), cine('a', { order: 5 })], 'league');
    expect(film.map(c => c.id)).toEqual(['a', 'b']);
  });
});

describe('bonus', () => {
  const withBonus = [...ALL, cine('boss-a', { order: 5000, bonus: true, arc: 'bosses' }), cine('late', { order: 1100 })];
  it('rejette les chapitres bonus après la fin du film, quel que soit leur rang', () => {
    const film = filmFor([cine('boss-b', { order: 50, bonus: true }), ...withBonus], 'league');
    expect(film.slice(-2).map(c => c.id)).toEqual(['boss-b', 'boss-a']);
    expect(bonusStart(film)).toBe(film.length - 2);
    expect(splitBonus(film).main.at(-1)?.id).toBe('late');
  });
  it('n’a pas de bonus quand aucun chapitre n’en est', () => {
    expect(bonusStart(filmFor(ALL, 'league'))).toBeNull();
    expect(splitBonus(filmFor(ALL, 'league')).bonus).toEqual([]);
  });
});

describe('chapitres et enchaînement', () => {
  const film = filmFor(ALL, 'league');
  const chapters = chaptersOf(film);
  it('cumule les durées', () => {
    expect(chapters.map(ch => [ch.start, ch.end])).toEqual([[0, 10], [10, 20], [20, 30], [30, 40], [40, 50]]);
    expect(filmDuration(film)).toBe(50);
  });
  it('passe au chapitre suivant puis s’arrête à la fin du film', () => {
    expect(nextIndex(film, 0)).toBe(1);
    expect(nextIndex(film, film.length - 1)).toBeNull();
  });
  it('retrouve le chapitre d’un instant du film et l’inverse', () => {
    expect(chapterAt(chapters, 0)).toBe(0);
    expect(chapterAt(chapters, 19.9)).toBe(1);
    expect(chapterAt(chapters, 20)).toBe(2);
    expect(chapterAt(chapters, 999)).toBe(4);
    expect(filmTime(chapters, 2, 3.5)).toBe(23.5);
  });
  it('regroupe les chapitres consécutifs d’un même arc', () => {
    expect(groupByArc(chapters).map(g => [g.arc, g.items.map(i => i.index)])).toEqual([
      ['prologue', [0]], ['invasion', [1, 2, 3]], ['kyros', [4]],
    ]);
  });
});

describe('sous-titres', () => {
  const film = filmFor(ALL, 'league');
  it('propose les langues présentes dans le film, dans l’ordre fr, en, ru', () => {
    expect(subtitleLangs(film)).toEqual(['fr', 'en', 'ru']);
    expect(subtitleLangs([cine('x')])).toEqual([]);
  });
  it('choisit la langue de l’interface si le film l’a', () => {
    expect(defaultSubtitleLang(film, 'en')).toBe('en');
    expect(defaultSubtitleLang([ALL[2]], 'en')).toBe('fr');
    expect(defaultSubtitleLang([cine('x')], 'fr')).toBeNull();
  });
  it('trouve la piste d’une cinématique, ou rien', () => {
    expect(trackFor(ALL[2], 'ru')?.src).toBe('bridge/ru.vtt');
    expect(trackFor(ALL[2], 'en')).toBeNull();
    expect(trackFor(ALL[2], null)).toBeNull();
  });
});

describe('divers', () => {
  it('formate les durées', () => {
    expect(formatDuration(65)).toBe('1:05');
    expect(formatDuration(3725)).toBe('1:02:05');
  });
  it('reconnaît les factions', () => {
    expect(isFaction('league')).toBe(true);
    expect(isFaction('common')).toBe(false);
    expect(isFaction(null)).toBe(false);
  });
  it('charge l’index, ou null s’il manque', async () => {
    const ok = vi.fn(async () => new Response(JSON.stringify({ arcs: {}, cinematics: [] })));
    expect(await loadCinematics(ok as unknown as typeof fetch)).toEqual({ arcs: {}, cinematics: [] });
    const missing = vi.fn(async () => new Response('', { status: 404 }));
    expect(await loadCinematics(missing as unknown as typeof fetch)).toBeNull();
  });
});
