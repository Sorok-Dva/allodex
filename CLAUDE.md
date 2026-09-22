# Allodex — instructions pour les agents

## Commits

- Messages de commit **en anglais**, titre au format gitmoji : `<gitmoji> <type>(<scope>): <message>`
  (ex. `🐛 fix(menu-scene-8.0): recentre the dome halo`), impératif, sans point final, 72 caractères max.
- **Aucun trailer `Co-Authored-By:`** ni autre mention d'attribution (`Generated with …`).
- Merges : `git merge --no-ff -m "🔀 merge(<scope>): merge <ce qui est fusionné>"`, jamais le nom
  technique de la branche `worktree-agent-…`.
- Convention complète, table gitmoji ↔ type et scopes courants : [CONTRIBUTING.md](CONTRIBUTING.md).
- Le hook `.githooks/commit-msg` fait respecter la règle ; l'activer dans chaque clone ou worktree :
  `git config core.hooksPath .githooks`.
