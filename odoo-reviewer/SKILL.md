---
name: odoo-code-review
description: Review Odoo (Python & XML) code for best practices, standards, and common errors. Use this skill when the user asks to review Odoo modules, Python files in an Odoo context, or XML views/data files.
---

# Odoo Code Reviewer

## Python Guidelines

### General
- **PEP8:** Strictly follow PEP8 (120 chars line length is often acceptable in Odoo).
- **Imports:**
    - `odoo` imports first.
    - `from odoo import models, fields, api, _`
    - `from odoo.exceptions import UserError, ValidationError`

### ORM Methods
- **Search:** Use `search_count()` instead of `len(search())`.
- **Filtered:** Use `filtered()` for in-memory filtering of recordsets.
- **Mapped:** Use `mapped()` to extract values.
- **Write/Create:** Batch operations where possible.
- **SQL:** Avoid direct SQL (`self.env.cr.execute`) unless absolutely necessary for performance. If used, never inject variables directly; use parameters.

### Fields & Models
- **Naming:**
    - Fields: `snake_case`. Many2one fields usually end with `_id` (e.g., `partner_id`).
    - One2many/Many2many: usually plural (e.g., `line_ids`, `tag_ids`).
- **Computed Fields:** Always add `@api.depends`.
- **Constrains:** Use `@api.constrains` for data integrity checks.
- **Translations:** Wrap user-facing strings in `_()`.

## XML Guidelines

### Views
- **Records:** Use `<record id="..." model="ir.ui.view">`.
- **Arch:** All views must have an `<arch type="xml">` block.
- **XPath:** Use concise XPath expressions. Prefer `name` attributes over indices.
    - Bad: `//field[3]`
    - Good: `//field[@name='description']`
- **Attributes:**
    - `invisible`: Use strictly for hiding.
    - `readonly`: For uneditable fields.
    - `required`: For mandatory fields.
- **Noids:** Avoid hardcoded database IDs. Use `ref="module.xml_id"`.

### Data Files
- **NoUpdate:** Use `noupdate="1"` in `<data>` for data that shouldn't be reset on upgrade (like sequence numbers or cron jobs).

## Manifest (__manifest__.py)
- Ensure `depends` lists all required modules.
- Ensure `data` lists all XML/CSV files in correct order (security -> views -> data).
- Ensure `license` is specified (e.g., LGPL-3).

## Review Checklist
1. **Security:** Are access rights (ir.model.access.csv) defined?
2. **Performance:** Are there loops doing SQL queries inside? (N+1 problem).
3. **Upgrade:** Will this code break on module update?
4. **Idempotency:** Can this XML be loaded multiple times without duplicating data?
