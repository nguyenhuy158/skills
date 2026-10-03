# Watchdog notes

The user reads replies under ADHD rules (action first, numbered steps, no recap). Do not flag that style.

## Every repo

- Claims of "done", "fixed" or "verified" with no command output, test run or screenshot behind them in the transcript.
- Destructive or irreversible steps taken without the user's go-ahead: `git push --force`, `git commit --amend` on pushed work, `rm -rf`, dropping databases, writing to prod (`odoo-prod` MCP, prod hosts).
- Scope creep: edits to files or behavior the user did not ask about, reformatting untouched code, new abstractions for one call site.
- Guessed APIs, field names or settings keys that were never read from source, docs or tool output.
- Debug loops: the same fix attempted a third time without a new hypothesis.

## FarmNet (`farmnet-github`, modules `src/farmnet_*`) — Odoo 16

- Migrations: `version` in `__manifest__.py` not bumped past the `migrations/<version>/` folder (the script silently never runs); non-idempotent SQL (unguarded `INSERT`/`ALTER`); ORM used to backfill instead of raw SQL.
- Fields without `help=`; `raise` with an inline string instead of an `ERR_` constant in the module-root `constants.py`; `constants.py`/`utils.py` placed inside `models/`.
- Line models (`*.line`) defined in the parent model file instead of `<model>_line.py`.
- XML: `invisible="..."` shorthand on anything other than `<field>`; a field used in `attrs` but missing from the view; buttons without `icon`, color class and an ALL CAPS `string`; new `groups=` on a button without asking the user.
- Money: outflows must round with `math.floor`, inflows with `math.ceil`.
- SQL reports: `LEFT JOIN` straight onto a one-to-many table (row duplication) instead of aggregating first.
- Branch names `<type>/<kebab>` with no issue number; PR titles in Conventional Commits; English only in code, Vietnamese only in `i18n/*.po`.
- Shell CLI calls (`git`, `docker`, `make`, `curl`) not prefixed with `rtk`.
- `ruff check src/` and `ruff format --check src/` not run before a commit.

## Farmlink (`farmlink`)

- Bulk reformatting of lines the task did not touch; keep diffs to the edited blocks.
