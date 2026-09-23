// pm2 : `pm2 start deploy/ecosystem.config.cjs && pm2 save`, depuis server/.
// Réglages dans server/.env (voir .env.example) ; NODE_ENV n'a aucun effet sur ce serveur.
module.exports = {
  apps: [{
    name: 'allodex-api',
    cwd: __dirname + '/..',
    script: 'node_modules/.bin/tsx',
    args: 'src/index.ts',
    interpreter: 'none',
    max_memory_restart: '512M',
    kill_timeout: 5000,
    time: true,
  }],
};
