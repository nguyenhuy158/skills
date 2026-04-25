---
name: code-polish
description: Polish Python code in git-changed files. Removes all comments and docstrings, eliminates magic strings and numbers, makes code self-documenting via naming. Python only — skips other languages. Use when user says "code-polish", "polish code", "clean code", "self-documenting", "remove comments", "làm sạch code".
---

# Code Polish

Make changed Python files self-documenting. Remove all comments and docstrings. Extract magic strings and numbers into named constants. Improve naming to eliminate the need for comments.

**Python files only.** Skip non-Python files silently.

---

## Step 1: Verify Git Repo

```bash
git rev-parse --is-inside-work-tree 2>/dev/null
```

If not a git repo → print `"Not a git repo. Skipping."` and stop.

---

## Step 2: Find Changed Python Files

```bash
git status --porcelain | awk '{print $2}' | grep '\.py$'
```

Include: modified (`M`), added (`A`), untracked (`??`) Python files.
Exclude: deleted files (`D`).

If no `.py` files changed → print `"No Python files changed. Nothing to polish."` and stop.

---

## Step 3: Analyze Each File

Read each changed Python file. For each file, identify **all** of the following:

### 3a. Comments to Remove

- All `#` comment lines (standalone)
- All inline `#` comments (after code)
- All docstrings: `"""..."""` and `'''...'''` (triple-quoted strings used as documentation, not assigned to a variable)

### 3b. Magic Strings

Any string literal used directly in logic that is **not** assigned to a named constant. Examples:

```python
# Magic string — bad
if status == "active":
    role = "admin"

# Named constant — good
ACTIVE_STATUS = "active"
ADMIN_ROLE = "admin"
if status == ACTIVE_STATUS:
    role = ADMIN_ROLE
```

Exceptions (do NOT flag):
- Strings in `raise` with full context (e.g., `raise ValueError("must be positive")`) — these are already self-documenting
- Strings that ARE the constant assignment right-hand side

### 3c. Magic Numbers

Any numeric literal (int or float) used directly in logic that is **not** assigned to a named constant.

Allowed literals (do NOT flag): `0`, `1`, `-1`, `2` (only in `// 2` or `* 2` doubling/halving context), `True`, `False`, `None`.

Examples:

```python
# Magic number — bad
if retries > 3:
    sleep(60)

# Named constant — good
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 60
if retries > MAX_RETRIES:
    sleep(RETRY_DELAY_SECONDS)
```

### 3d. Poor Naming That Required Comments

If a comment existed to explain what a variable/function does, that name is too vague. Flag it and suggest a rename.

Examples:
- `x` → `user_age`
- `process()` → `validate_and_save_user()`
- `data` → `raw_api_response`
- `flag` → `is_email_verified`

---

## Step 4: Build Report

For each file, output:

```
## file: path/to/file.py

### Comments / Docstrings to Remove
- Line 12: inline comment `# increment counter`
- Lines 5–8: docstring on function `load_data`

### Magic Strings
- Line 24: `"active"` → suggest constant `ACTIVE_STATUS = "active"`
- Line 31: `"admin"` → suggest constant `ADMIN_ROLE = "admin"`

### Magic Numbers
- Line 47: `3` in `retries > 3` → suggest `MAX_RETRIES = 3`
- Line 48: `60` in `sleep(60)` → suggest `RETRY_DELAY_SECONDS = 60`

### Naming Improvements
- Line 19: variable `x` used with comment `# user age` → rename to `user_age`
- Line 33: function `do_stuff()` → rename to `send_welcome_email()`
```

If a file has no issues → `path/to/file.py: clean. No changes needed.`

---

## Step 5: Ask User to Confirm

After report, ask:

> "Apply changes?
> - `yes` — apply all files
> - `no` — cancel
> - `select` — choose specific files"

Wait for user reply.

**If `no`** → print `"Cancelled. No files modified."` and stop.

**If `select`** → list files with numbers, ask user to pick (e.g., `1 3`), then apply only those.

**If `yes`** → apply to all files with issues.

---

## Step 6: Apply Changes

For each confirmed file, modify it:

### Remove Comments and Docstrings
- Delete all `#` comment lines
- Delete all inline `#` comments (preserve the code on that line)
- Delete all triple-quoted docstrings (`"""..."""` / `'''...'''`) that are not assigned to a variable

### Extract Constants
- Group all new named constants at **top of file** (after imports, before first class/function)
- Use `ALL_CAPS_SNAKE_CASE` for constant names
- Replace all usages in file with the constant name

### Apply Renames
- Rename variables, parameters, and functions as suggested
- Update all references in the same file

### Self-Documenting Validation
After changes, verify:
- No remaining `#` comments
- No remaining unassigned triple-quoted strings
- No remaining magic strings or numbers (per rules above)
- All names are descriptive without needing comments

---

## Step 7: Confirm Done

```
Polished 2 file(s):

  src/auth.py — removed 8 comments, 1 docstring, extracted 3 constants, renamed 2 variables
  src/utils.py — removed 3 comments, extracted 1 constant

Files are clean and self-documenting.
```

---

## Error Handling

| Situation | Action |
|-----------|--------|
| Not a git repo | Print message, stop |
| No Python files changed | Print message, stop |
| File has syntax error | Warn `"Skipping path/to/file.py — syntax error detected. Fix syntax first."` |
| File is already clean | Report `"clean"`, skip in apply step |
| Rename would conflict with existing name | Warn user, skip that rename, apply rest |

---

## Safety Rules

- **Never modify without user confirmation.** Always show report first.
- **Never modify non-Python files.**
- **Never delete code logic** — only comments, docstrings, and magic literals (replacing with named constants).
- Preserve all whitespace structure and formatting outside of removed lines.
- If unsure whether a string is a magic string or already well-named, **do not flag it**.
