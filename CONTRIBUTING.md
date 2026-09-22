# Contributing to Allodex

## Commit convention

Every commit message is written in **English** and its title follows this format:

```
<gitmoji> <type>(<scope>): <message>
```

- **gitmoji**: the Unicode emoji (not the `:shortcode:`) that fits the change best, taken from
  [gitmoji.dev](https://gitmoji.dev). The table below lists the ones this repository uses.
- **type**: a Conventional Commits type, lowercase: `feat`, `fix`, `refactor`, `perf`, `docs`,
  `test`, `style`, `build`, `ci`, `chore`, `revert`, `merge`.
- **scope**: short, lowercase, in English (`a-z`, `0-9`, `.`, `-`). Always required.
- **message**: imperative mood ("add", not "added"/"adds"), no final period.
- The whole title is **72 characters max** (an emoji counts as one or two characters).
- Optional body after a blank line: what changed and why, in English. Wrap at about 80 columns.
- **No `Co-Authored-By:` trailer** or any other attribution trailer (`Generated with …`),
  whether the change was written by a person or an AI agent.

### Gitmoji and types used here

| Gitmoji | Type | When |
|---|---|---|
| ✨ | `feat` | new feature |
| 🐛 | `fix` | bug fix |
| 🩹 | `fix` | trivial fix |
| ♻️ | `refactor` | code restructuring without behaviour change |
| ⚡️ | `perf` | performance |
| 📝 | `docs` | documentation, specs, plans |
| ✅ | `test` | adding or updating tests |
| 💄 | `feat` / `fix` / `style` | UI and visual styling |
| 🎨 | `style` | code format or structure |
| 💫 | `feat` | animations and transitions |
| 🚸 | `feat` | user experience and usability |
| ♿️ | `feat` / `fix` | accessibility |
| 🌐 | `feat` | internationalisation (fr/en) |
| 🔊 | `feat` / `fix` | sounds and music |
| 📈 | `feat` | analytics and tracking |
| 🚩 | `feat` | feature flags (enable/disable per environment) |
| 🍱 | `chore` | adding or updating assets |
| 🔥 | `chore` | removing code or files |
| 🚚 | `chore` / `refactor` | moving or renaming files |
| 🙈 | `chore` | `.gitignore` |
| 🔧 | `chore` / `fix` | configuration (Vite, manifests, tooling) |
| 🎉 | `chore` | begin a project |
| 🚧 | `feat` | work in progress |
| 🔀 | `merge` | merging branches |
| ⏪ | `revert` | reverting a change |

### Common scopes

| Scope | Area |
|---|---|
| `opening` | opening screen, intro, action bar |
| `menu` | action bar entries |
| `medals` | Medals (achievements) panel |
| `chronicles` | Chronicles page (per-version launch screens) |
| `music` | Music page and player |
| `audio` | site audio engine |
| `i18n` | translations |
| `ui`, `components`, `routing` | shared UI, component layout, routes |
| `menu-scene` | 3D menu scenes, generic (extractor + player) |
| `menu-scene-4.0` … `menu-scene-8.0` | one version's menu scene |
| `fatalities` | Fatalities viewer |
| `extractor` | extraction tools under `tools/` |
| `sprites` | sprite cutting (`tools/cut_sprites.py`) |
| `assets` | generated assets under `public/game/` |
| `config`, `test`, `project` | configuration, test setup, project-wide chores |
| `deploy` | production deployment |
| `poc`, `iteration-2`, `plan` | early design documents |

### Examples

```
✨ feat(chronicles): add fullscreen toggle that hides the HUD
🐛 fix(menu-scene-5.0): frame camera on ship pass, fix ship_tail trail
♻️ refactor(menu-scene): add per-version hooks for extractor and player
📝 docs(deploy): document the production deployment procedure
🔧 fix(config): allow allodex.eu and allodex.online in the Vite server
🔀 merge(menu-scene-8.0): merge single UV scroll law and brazier fire
```

A merge title says what is merged, never the technical branch name
(`worktree-agent-…`). Git's default "Merge branch …" title is rejected by the hook, so pass it
explicitly:

```sh
git merge --no-ff -m "🔀 merge(menu-scene-6.0): merge 6.0 scene export and player" <branch>
```

### Enforcement

A versioned `commit-msg` hook ([`.githooks/commit-msg`](.githooks/commit-msg)) rejects a title
that does not follow the format, a title over 72 characters and any `Co-Authored-By` trailer.
Enable it once per clone, along with the message template:

```sh
git config core.hooksPath .githooks
git config commit.template .gitmessage
```

`fixup!`, `squash!` and `amend!` commits are let through so `git rebase --autosquash` keeps
working.
