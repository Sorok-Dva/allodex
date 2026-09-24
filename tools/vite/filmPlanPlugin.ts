/**
 * Greffon Vite de la page de développement `/dev/film` (plan du film des cinématiques).
 *
 * En `vite` (serveur de développement) seulement (`apply: 'serve'`) : absent du build.
 *
 * - `GET  /__film-plan` : le plan (`tools/film_plan.json`) et sa révision (empreinte SHA-1 du texte) ;
 * - `PUT  /__film-plan` : `{ baseRevision, plan }` ; le plan est validé (`validatePlan`), refusé
 *   (409) si le fichier a changé depuis `baseRevision` (un agent l'a édité), sinon écrit de façon
 *   atomique (fichier temporaire du même dossier, puis `rename`) ;
 * - le fichier est surveillé : à chaque changement sur disque, un événement HMR
 *   `film-plan:changed` (avec la révision) prévient la page, qui relit le plan.
 */
import { createHash } from 'node:crypto';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import type { IncomingMessage, ServerResponse } from 'node:http';
import type { Plugin, ViteDevServer } from 'vite';
import { serializePlan, validatePlan, type FilmPlan } from '../../src/screens/FilmPlanScreen/filmPlan.ts';

export const FILM_PLAN_ROUTE = '/__film-plan';
export const FILM_PLAN_EVENT = 'film-plan:changed';
const MAX_BODY = 4 * 1024 * 1024;

export const revisionOf = (text: string) => createHash('sha1').update(text).digest('hex');

export async function readPlanFile(file: string): Promise<{ text: string; revision: string }> {
  const text = await fs.readFile(file, 'utf8');
  return { text, revision: revisionOf(text) };
}

/** Écriture atomique : un lecteur (la page, un agent) ne voit jamais un fichier à moitié écrit. */
export async function writePlanFile(file: string, plan: FilmPlan): Promise<string> {
  const text = serializePlan(plan);
  const tmp = path.join(path.dirname(file), `.${path.basename(file)}.${process.pid}.${Date.now()}.tmp`);
  await fs.writeFile(tmp, text, 'utf8');
  try {
    await fs.rename(tmp, file);
  } catch (error) {
    await fs.rm(tmp, { force: true });
    throw error;
  }
  return revisionOf(text);
}

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks: Buffer[] = [];
    req.on('data', (chunk: Buffer) => {
      size += chunk.length;
      if (size > MAX_BODY) { reject(new Error('corps trop grand')); req.destroy(); return; }
      chunks.push(chunk);
    });
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}

function send(res: ServerResponse, status: number, body: unknown) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  res.end(JSON.stringify(body));
}

/**
 * Traite une requête sur la route du plan. Séparé du greffon pour les tests (sans serveur Vite).
 * `onWrite` est appelé avec la révision écrite.
 */
export async function handlePlanRequest(file: string, req: IncomingMessage, res: ServerResponse, onWrite?: (revision: string) => void) {
  try {
    if (req.method === 'GET') {
      const { text, revision } = await readPlanFile(file);
      let plan: unknown;
      try { plan = JSON.parse(text); } catch { return send(res, 500, { error: 'film_plan.json : JSON illisible', revision }); }
      return send(res, 200, { revision, plan, errors: validatePlan(plan) });
    }
    if (req.method === 'PUT') {
      let body: unknown;
      try { body = JSON.parse(await readBody(req)); } catch { return send(res, 400, { error: 'corps JSON illisible' }); }
      const { baseRevision, plan } = (body ?? {}) as { baseRevision?: unknown; plan?: unknown };
      const errors = validatePlan(plan);
      if (errors.length) return send(res, 422, { error: 'plan invalide', errors });
      const current = await readPlanFile(file).catch(() => null);
      if (current && current.revision !== baseRevision) {
        return send(res, 409, { error: 'le fichier a changé sur disque', revision: current.revision });
      }
      const revision = await writePlanFile(file, plan as FilmPlan);
      onWrite?.(revision);
      return send(res, 200, { revision });
    }
    res.setHeader('Allow', 'GET, PUT');
    return send(res, 405, { error: 'méthode non prise en charge' });
  } catch (error) {
    return send(res, 500, { error: String((error as Error)?.message ?? error) });
  }
}

export function filmPlanPlugin(file = path.resolve(import.meta.dirname, '../film_plan.json')): Plugin {
  return {
    name: 'allodex-film-plan',
    apply: 'serve',
    configureServer(server: ViteDevServer) {
      server.watcher.add(file);
      const notify = async (changed: string) => {
        if (path.resolve(changed) !== file) return;
        const current = await readPlanFile(file).catch(() => null);
        if (current) server.ws.send({ type: 'custom', event: FILM_PLAN_EVENT, data: { revision: current.revision } });
      };
      server.watcher.on('change', notify);
      server.watcher.on('add', notify);
      server.middlewares.use(FILM_PLAN_ROUTE, (req, res, next) => {
        // `use(route)` retire le préfixe : seule la racine de la route est servie
        if (req.url && req.url !== '/' && !req.url.startsWith('/?')) return next();
        void handlePlanRequest(file, req, res);
      });
    },
  };
}
