---
name: pr-review
description: Review a GitHub PR (code, CI/CD, infra) and write a Vietnamese verdict with blocking / should-fix / pre-existing findings.
---

# PR review

## Steps
1. Read PR body + reviews: `pr://<N>`; diff: `pr://<N>/diff/all`.
2. Fetch head and search it for leftovers of what the PR removes/renames (`rg` cannot search a git ref, so use `git grep` on it):
   `rtk git fetch -q origin <head-branch> && rtk git grep -nE '<old-names>' FETCH_HEAD -- <paths>`
3. Check each change against the checklist below. All "Odoo PRs" sections (new fields/strings, A, B, C) apply only when the PR touches `src/`; otherwise list them as N/A.
4. Write the review in the output format. Do not post to GitHub unless the user asks.

## Checklist
- **Leaked secrets**: scan added lines of the diff for keys/tokens/passwords/private keys/connection strings (e.g. `AKIA`, `-----BEGIN`, `password=`, `secret`, `token`, `api_key`, `.env` values, base64 blobs). Placeholders/`${{ secrets.X }}`/env var names = pass. Never repeat a found secret in the review; cite file:line only.
- **Comments** (should fix): AGENTS.md says no comments; code must be self-documenting. Flag added comments that restate the code or explain what a badly named variable/function does; fix = rename/extract, then delete the comment. Docstrings, `# -*- coding` header, migration ASCII box docstrings and non-Python files (YAML, Jenkinsfile, shell) where comments carry operational context = pass.
- **Preconditions**: anything the PR body says must happen before merge (seed images, secrets, migrations) — not done = blocking.
- **Leftovers**: old names/vars/credentials still referenced after the change.
- **Credentials**: least privilege (e.g. push token used only to pull); secrets passed via stdin/env, never printed; how long the secret stays on disk.
- **Untrusted code window**: does PR code run while a credential is loaded?
- **Deploy targets**: hosts/envs the change affects that the author could not verify.
- **Capacity/cost**: only report numbers actually observed; estimates go as "risk to measure", never as a conclusion.
- **Arch/consistency**: amd64/arm64 tags, base image vs target platform, comments/docs contradicting each other.

## Odoo PRs — new fields / strings
- **i18n** (should fix): every new user-facing string (field `string=`/`help=`, selection labels, view `string=`/button labels/placeholders, `_()` / `ERR_*` messages, menu/action names) has a `msgid` + non-empty Vietnamese `msgstr` in the module's `i18n/vi_VN.po`; a selection change also syncs every `.po` that mirrors it. Missing/empty = should fix; list file + msgid.
- **New fields**: list every field added on an Odoo model in the diff (model, field, type), including `fields.X(...)`, imported aliases, and fields added to an `_inherit` model. Read the class context, not just a regex. None = pass.
- **Stored compute without migration**: every new field with `compute=` AND `store=True` requires a `version` bump in `__manifest__.py` and a `migrations/<version>/` folder; missing either = blocking. When that migration backfills the field it must follow the repo standard (AGENTS.md "Migrations", skill `odoo-migration`): pre-migration backs up `write_date`/`write_uid` into `<table>_write_meta_backup_<ver>` (drop first), post-migration uses `env.add_to_compute` + `flush_recordset` then restores write metadata and drops the backup, idempotent, ASCII box docstring; raw `UPDATE ... CASE` or `records.write()` backfill = blocking. Migrations that do not backfill a field are not subject to the backup sandwich.

## Odoo PRs — blocking (group A)
- **Access control**: concrete `models.Model` and `TransientModel` (wizard) added via `_name` need lines in `ir.model.access.csv` for the module's group chain; `AbstractModel` needs none. Flag only real missing access (model unusable or opened to the wrong groups), not naming style.
- **ir.rule**: numbered stack (1. Don't view → … → N. View all), `domain_force` matches the role; flag rules that widen access (global rule without `groups`, `[(1,'=',1)]` on a restricted group), rules referencing missing fields/groups, `perm_*` contradicting the CSV.
- **Deployed XML IDs**: never renamed/deleted (compare with `rtk git show main:<file>`); rename = new ID + `implied_ids` from old + old marked `[DEPRECATED]`.
- **Writable stored compute**: `compute=` + `store=True` field that users/code write to has `inverse=`.
- **Other migrations**: rename/drop column or data move = version bump + idempotent + raw SQL only for schema surgery; never `records.write()` backfill.
- **SQL/report**: 1-to-many joins aggregated (GROUP BY/CTE) before joining.
- **Money rounding**: outflows `math.floor`, inflows `math.ceil`.
- **SQL injection**: `cr.execute` with f-string/`%`/`+` built queries instead of parameters (or `psycopg2.sql` for identifiers).
- **Compute deps**: every `compute=` method has a complete `@api.depends` (stored compute with missing deps = stale data).
- **Manifest**: new files listed in `data` (security before views before data); new imports/models covered by `depends`.
- **XML load safety**: no hardcoded database ids (use `ref=`); data XML reloads on upgrade without duplicating records; inherited views use XPath by `@name`, never by index (`//field[3]`).

## Odoo PRs — should fix (group B)
- **Groups naming**: label `[Prefix] Farmnet <Module>[ <Role>]`, XML ID `<module>.<type>`, category `FarmNet / <Domain>` (`module_category_farmnet_<domain>`), chain `base.group_user` → `read` → `write` → `restrict_for_bo` → `restrict_for_bo2` → `restrict_for_am` / `restrict_for_admin`.
- **Fields**: `string=` + `help=` on every field; `tracking=True` on important ones.
- **Python**: `raise` messages are `ERR_*` constants in `constants.py`; `ensure_one()` at start of action/button methods (not in onchange/`@api.model`/loops); `account.move` uses `display_name`, not `.name`; f-strings; English only (Vietnamese only in `i18n/*.po`); docstrings on classes/functions.
- **Structure**: `constants.py`/`utils.py` at module root; line models in their own `<model>_line.py`; `# -*- coding: utf-8 -*-` first line.
- **XML**: buttons have `icon`, color `class`, ALL CAPS `string` (primary+fa-check, secondary+fa-undo, info+fa-search, danger+fa-times); only `<field>` uses shorthand `invisible`, other tags use `attrs`; every field in `attrs` present in the view; state fields `widget="badge"` with AGENTS.md decorations; partner/company M2o `no_create`/`no_open`; bank account M2o domain; embedded O2m tree includes `name` (+ `sequence`).
- **ORM usage**: no queries inside loops (N+1) — batch `search`/`read`/`write`/`create`; `search_count()` over `len(search())`; `filtered()`/`mapped()` over manual loops; integrity rules in `@api.constrains`.
- **Naming**: M2o ends `_id`, O2m/M2m ends `_ids`.
- **Lint**: `ruff check src/` + `ruff format --check src/` — read the CI result, do not rerun.

## Odoo PRs — needs user confirmation (group C)
- New `noupdate="1"` or new `groups="..."` on buttons (AGENTS.md: ask before both): report as "cần user xác nhận", not as a violation.

## Rules
- Separate findings caused by this PR from pre-existing ones.
- Mark unverified claims as unverified; state what was only checked statically.
- Each finding: file/symbol + concrete risk + concrete fix.

## Output format (Vietnamese)
Failed checks only go in the table; passed checks go on one line, comma-separated.
```
Kết luận: approve / approve có điều kiện / request changes — <1 dòng lý do>

| # | Checklist | Mức | File:line | Vấn đề | Cách sửa |
|---|---|---|---|---|---|
| 1 | Stored compute without migration | Chặn merge | ... | ... | ... |
| 2 | ... | Nên sửa / Có sẵn | ... | ... | ... |

Pass: Leaked secrets, New fields (model.field: type, ...), Leftovers, ...
N/A: <checks that do not apply, e.g. Odoo groups on a CI-only PR>

Đã kiểm: <những gì thực sự chạy/đọc>. Chưa kiểm: <...>.
Next: <1 hành động < 2 phút>
```
