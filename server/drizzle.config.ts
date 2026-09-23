import { defineConfig } from 'drizzle-kit';

// `npm run db:generate` : compare src/schema.ts au dernier instantané de drizzle/ et écrit la
// migration SQL suivante (aucune connexion à la base).
export default defineConfig({
  dialect: 'mysql',
  schema: './src/schema.ts',
  out: './drizzle',
});
