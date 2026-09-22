import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src') } },
  server: { port: 5173, allowedHosts: ['allodex.eu', 'allodex.online', 'allodex.allods-developers.eu'] },
  test: {
    environment: 'jsdom', globals: true, setupFiles: [], passWithNoTests: true,
    // Les worktrees des sous-agents vivent sous .claude/ : ne pas rejouer leurs tests ici.
    exclude: ['**/node_modules/**', '**/dist/**', '.claude/**'],
  },
});
