# skills repo

## Git

- Commit and push **straight to `main`**. No feature branch, no PR — this is a personal skills repo.
- Commit style: emoji + Conventional Commits, e.g. `✨ feat(release-note): add ...` (see `copilot-commit-style/`).

## Adding a skill

- Put it in `plugins/workflow/skills/<name>/SKILL.md` so it ships as `/workflow:<name>`.
- Add a row to the slash-command table in `README.md`.
- Don't duplicate it into a root-level dir; the root copies are legacy.
