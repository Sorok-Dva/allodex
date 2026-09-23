import { beforeEach, describe, expect, it } from 'vitest';
import type { CollectEvent } from './api';
import { createTracker, entryReferrer, randomId } from './tracker';

describe('traceur', () => {
  let sent: CollectEvent[];
  let clock: number;
  const extra = { search: '', referrer: 'https://discord.com/channels/1', width: 1920, visible: true };
  const make = () => createTracker(e => sent.push(e), () => clock);

  beforeEach(() => {
    sent = [];
    clock = 0;
    sessionStorage.clear();
  });

  it('envoie une vue par chemin, la provenance sur la première seulement', () => {
    const t = make();
    t.view('/', 'fr', extra);
    t.view('/', 'fr', extra);
    clock = 5000;
    t.view('/talents', 'fr', extra);
    expect(sent.map(e => e.type)).toEqual(['view', 'leave', 'view']);
    expect(sent[0]).toMatchObject({ path: '/', lang: 'fr', width: 1920, referrer: 'https://discord.com/channels/1' });
    expect(sent[1]).toMatchObject({ path: '/', view: sent[0].view, duration: 5000 });
    expect(sent[2].referrer).toBeUndefined();
    expect(new Set(sent.map(e => e.session)).size).toBe(1);
    expect(sent[2].view).not.toBe(sent[0].view);
  });

  it("garde la session de l'onglet entre deux chargements", () => {
    make().view('/', 'fr', extra);
    make().view('/music', 'fr', extra);
    expect(sent[1].session).toBe(sent[0].session);
    expect(sent[1].referrer).toBeUndefined();
  });

  it("ne compte que le temps où l'onglet est visible", () => {
    const t = make();
    t.view('/lorebook', 'en', extra);
    clock = 10_000;
    t.visibility(false);
    clock = 60_000;
    t.ping();
    t.visibility(true);
    clock = 65_000;
    t.ping();
    t.leave();
    expect(sent.map(e => [e.type, e.duration])).toEqual([
      ['view', undefined], ['ping', 10_000], ['ping', 10_000], ['ping', 15_000], ['leave', 15_000],
    ]);
  });

  it('préfère un paramètre de campagne au référent du navigateur', () => {
    expect(entryReferrer('?utm_source=reddit', 'https://www.google.com/')).toBe('reddit');
    expect(entryReferrer('?ref=newsletter', '')).toBe('newsletter');
    expect(entryReferrer('', '')).toBeUndefined();
    expect(randomId()).toMatch(/^[A-Za-z0-9_-]{16}$/);
  });
});
