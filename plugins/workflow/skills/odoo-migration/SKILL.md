---
name: odoo-migration
description: Write Odoo upgrade migrations - bump the module version and add migrations/<version>/{pre,post}-migration.py - and in particular protect write_date/write_uid from being re-stamped when a backfill touches every row. Use this skill whenever a change needs existing rows fixed up on upgrade: a new stored computed field, a renamed or split column, a data backfill, dropping a field, or editing records that live in a noupdate="1" data block. Also use it when someone says "migration", "backfill", "existing data", "pre-migration / post-migration", or asks why an upgrade dirtied write_date on thousands of records - even if they never use the word "migration".
---

# Writing an Odoo migration

A model change only alters the schema. Rows that already exist keep whatever
they had, and for a new stored computed field that means NULL - which reads as
zero, or as false, and quietly breaks any report or domain that filters on it.
The migration is what makes existing data agree with the new code.

The second thing a migration is for is damage control. Odoo backfills a new
stored compute by *writing* every row, and a write stamps `write_date` /
`write_uid`. On a table with tens of thousands of rows that destroys the audit
trail in one upgrade, and nobody notices until someone asks who last touched a
record. So most migrations are a sandwich: snapshot the stamps before, restore
them after.

## Before writing anything: read the repo's own migrations

```bash
find . -type d -name migrations -not -path '*/node_modules/*'
```

Conventions vary between codebases - backup table naming, whether they use
`flush_all` or `flush_recordset`, how much they log. Matching the closest
existing migration is faster than deriving the pattern, and it keeps the next
person from having to learn two styles. What follows is the shape to fall back
on when there is no precedent, or to check an existing one against.

Watch out for lookalikes that are *not* migrations: directories of hand-run
`odoo shell` scripts (often `deploy/<date>/`, or a singular `migration/`).
Nothing guarantees those bracket a module upgrade, so upgrade logic does not
belong there.

## The steps

### 1. Bump the module version

`__manifest__.py`: `'version': '0.3'` -> `'0.4'`. Odoo only runs migrations
when the manifest version is higher than the version recorded in
`ir_module_module`. Skip this and your files never execute - the single most
common way a migration silently does nothing.

The directory name must match the *new* version exactly: `migrations/0.4/`.

### 2. Layout

`<module>/migrations/<version>/pre-migration.py` and `post-migration.py`.
Hyphen in the filename, `def migrate(cr, version):` inside. Odoo discovers
them from the version directory, so nothing needs registering.

`pre-` runs before the module's schema and data load, `post-` after. That
timing is the whole reason there are two files: only `pre-` can see the world
as it was, and only `post-` can see the new columns.

### 3. pre-migration: snapshot the write metadata

Needed whenever the upgrade will write to rows you did not mean to modify -
which is every stored-compute backfill.

```python
"""Snapshot write metadata before <field> lands.

<field> is a new stored compute, so adding it re-stamps write_date /
write_uid on every existing row. post-migration.py puts them back.
"""

WRITE_METADATA_BACKUP_TABLE = '<table>_write_meta_backup_0_4'
TARGET_TABLE = '<table>'


def migrate(cr, version):
    cr.execute(f'DROP TABLE IF EXISTS {WRITE_METADATA_BACKUP_TABLE}')
    cr.execute(
        f'CREATE TABLE {WRITE_METADATA_BACKUP_TABLE} AS '
        f'SELECT id, write_date, write_uid FROM {TARGET_TABLE}'
    )
```

The version suffix (`..._0_4`) keeps two migrations from fighting over one
backup table, and `DROP ... IF EXISTS` makes the file safe to re-run after a
failed upgrade.

Table name is the model's `_name` with dots flattened to underscores:
`account.move.line` -> `account_move_line`.

### 4. post-migration: backfill, then restore

Default to the ORM. The compute method is the definition of what the field
means; re-expressing it as SQL creates a second copy that drifts the moment
someone edits the Python.

```python
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

FIELDS = ('cash_in', 'cash_out', 'cash_net')
WRITE_METADATA_BACKUP_TABLE = '<table>_write_meta_backup_0_4'
TARGET_TABLE = '<table>'


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    records = env['<model>'].search([])
    for fname in FIELDS:
        env.add_to_compute(records._fields[fname], records)
    records.flush_recordset(FIELDS)
    _logger.info('<field> backfilled: rows=%s', len(records))

    cr.execute(
        f'UPDATE {TARGET_TABLE} target '
        f'SET write_date = backup.write_date, write_uid = backup.write_uid '
        f'FROM {WRITE_METADATA_BACKUP_TABLE} backup '
        f'WHERE target.id = backup.id'
    )
    cr.execute(f'DROP TABLE IF EXISTS {WRITE_METADATA_BACKUP_TABLE}')
```

The ordering carries the whole thing:

**snapshot -> Odoo loads the new schema -> mark for compute -> flush -> restore stamps -> drop backup**

The flush has to come *before* the restore. `add_to_compute` only queues the
work; the values - and the fresh `write_date` - land in SQL when the ORM
flushes. If that flush happens after your `UPDATE`, it overwrites the stamps
you just restored and the migration accomplishes nothing. `flush_recordset(fnames)`
makes the timing explicit right where you need it; `env.flush_all()` also works
but flushes unrelated pending work too, so prefer the narrow one.

On Odoo versions before 16, `add_to_compute` / `flush_recordset` may not exist -
check what the installed `odoo/api.py` and `odoo/models.py` actually expose
before using them, and fall back to calling the compute method directly plus
`recordset.modified(FIELDS)`.

### 5. When to drop to raw SQL instead

The ORM path loads and writes every row inside the upgrade's boot path. Reach
for SQL when that is genuinely a problem:

- the table is large enough that the flush is a real outage
- the value has to come from something the ORM cannot see - a legacy column
  mid-migration, a deprecated field being read one last time

Then guard the column, because a partly-applied upgrade may not have it yet:

```python
from odoo.tools.sql import column_exists

def migrate(cr, version):
    if not column_exists(cr, TABLE, 'has_attachment'):
        return
    cr.execute(f'UPDATE {TABLE} SET has_attachment = FALSE WHERE has_attachment IS NULL')
    # ... then the same write-metadata restore
```

Whichever path you take, say *why* in the module docstring. "Raw SQL on
purpose: the ORM compute would flush 46k+ records inside the boot path" is the
sentence that stops the next person from helpfully rewriting it - and if you
cannot write that sentence honestly, use the ORM.

### 6. noupdate data needs a post-migration too

Records in a `noupdate="1"` block are written once at install and never touched
again, so editing or deleting the XML does nothing to a live database. Fix
those in `post-migration.py` via `env.ref(xmlid, raise_if_not_found=False)`,
skipping silently when the record is already gone. Adding a *new* record is
fine to leave to the XML - only changes and removals need the migration.

```python
def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    removed = 0
    for xmlid in _XMLIDS:
        record = env.ref(xmlid, raise_if_not_found=False)
        if not record:
            continue
        record.unlink()
        removed += 1
    _logger.info('removed %s record(s)', removed)
```

## Conventions that are easy to get wrong

- Never `cr.commit()`. Odoo owns the upgrade transaction; committing halfway
  leaves a database that is neither the old version nor the new one if a later
  step raises.
- `_logger.info(...)` with a row count, not `print`. Upgrades run headless and
  the log is the only evidence the backfill did anything - a count of `0` is
  how you find out the search domain was wrong.
- Migrations run on *upgrade only*. A freshly installed database never sees
  them, so the model code must already be correct on an empty table; the
  migration only ever catches up existing rows.
- Guard for absence rather than asserting presence. Databases at different
  ages will run this file, so `raise_if_not_found=False` and `column_exists`
  turn "already done" into a no-op instead of a failed upgrade.
- Lint before finishing. Repos often exempt shell-script directories from
  undefined-name checks but *not* `migrations/`, so `env` and `cr` must come
  from the function signature or an explicit `api.Environment(cr, SUPERUSER_ID, {})`.

## Verify it actually ran

Upgrade the module (`odoo -u <module> --stop-after-init`, or whatever the repo
wraps that in), then check the two things that fail quietly:

1. the new column is populated - not NULL, and not uniformly zero
2. `write_date` on a row you did not intend to modify still matches what it
   was before the upgrade

If nothing happened at all, the manifest version bump is the first suspect;
the second is a `migrations/` directory name that does not match it.
