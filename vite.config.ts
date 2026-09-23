import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import { metaFor, renderHead } from './src/seo/meta.ts';

/** Bloc `<!--seo-->` d'index.html : balises de l'accueil, remplacées page par page par le serveur. */
const seoHead = { name: 'allodex-seo-head', transformIndexHtml: (html: string) =>
  html.replace('<!--seo--><!--/seo-->', `<!--seo-->\n    ${renderHead(metaFor('/', new URLSearchParams()))}\n    <!--/seo-->`) };

export default defineConfig({
  plugins: [react(), seoHead],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src') } },
  server: {
    port: 5173, allowedHosts: ['allodex.eu', 'allodex.online', 'allodex.allods-developers.eu'],
    // Backend (`server/`, `npm run dev` dans ce dossier) : mesure d'audience et tableau de bord.
    proxy: { '/api': { target: 'http://127.0.0.1:8787', changeOrigin: false } },
  },
  test: {
    environment: 'jsdom', globals: true, setupFiles: [], passWithNoTests: true,
    // Les worktrees des sous-agents vivent sous .claude/ : ne pas rejouer leurs tests ici.
    exclude: ['**/node_modules/**', '**/dist/**', '.claude/**', 'server/**'],
  },
});
