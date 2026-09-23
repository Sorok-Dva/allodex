import { describe, expect, it } from 'vitest';
import type { TalentEvent } from '@/analytics/api';
import { createBuildTracker, IDLE } from './talents.track';

function setup() {
  const sent: TalentEvent[] = [];
  let clock = 0;
  let queue: { at: number; fn: () => void; id: number }[] = [];
  let next = 1;
  const timers = {
    set: (fn: () => void, ms: number) => { const id = next++; queue.push({ at: clock + ms, fn, id }); return id; },
    clear: (id: number) => { queue = queue.filter(t => t.id !== id); },
  };
  const advance = (ms: number) => {
    clock += ms;
    const due = queue.filter(t => t.at <= clock);
    queue = queue.filter(t => t.at > clock);
    due.forEach(t => t.fn());
  };
  const tracker = createBuildTracker(e => sent.push(e), () => 'fr', timers);
  return { sent, advance, tracker, kinds: () => sent.map(e => `${e.kind}:${e.b ?? ''}/${e.b2 ?? ''}`) };
}

const at = (b: string | null, b2: string | null = null) => ({ v: '17.0', c: 'warrior', b, b2 });

describe('suivi des builds', () => {
  it("compte la vue d'un build venu d'un lien, pas celle d'une page vierge", () => {
    const a = setup();
    a.tracker.landed(at('1.2'), true);
    const b = setup();
    b.tracker.landed(at(null), false);
    expect(a.kinds()).toEqual(['view:1.2/']);
    expect(a.sent[0]).toMatchObject({ v: '17.0', c: 'warrior', lang: 'fr' });
    expect(b.sent).toEqual([]);
  });

  it("n'envoie que le build où l'édition se pose", () => {
    const { tracker, advance, kinds } = setup();
    tracker.landed(at(null), false);
    tracker.changed(at('1.2'));
    advance(IDLE - 1);
    tracker.changed(at('1.3'));
    advance(IDLE - 1);
    expect(kinds()).toEqual([]);
    advance(1);
    expect(kinds()).toEqual(['generate:1.3/']);
    // Remise à zéro : rien à enregistrer ; retour au même build : déjà envoyé.
    tracker.changed(at(null));
    advance(IDLE);
    tracker.changed(at('1.3'));
    advance(IDLE);
    expect(kinds()).toEqual(['generate:1.3/']);
  });

  it('enregistre le build en cours au partage et à la fermeture', () => {
    const { tracker, advance, kinds } = setup();
    tracker.landed(at('1.2'), true);
    tracker.shared(at('1.2'));
    tracker.changed(at('1.2', '1.3'));
    tracker.shared(at('1.2', '1.3'));
    tracker.changed(at('1.3', '1.3'));
    tracker.flush();
    advance(IDLE);
    expect(kinds()).toEqual(['view:1.2/', 'share:1.2/', 'generate:1.2/1.3', 'share:1.2/1.3', 'generate:1.3/1.3']);
  });
});
