---
name: git-branch-clean
description: Use this skill when user wants to clean up local git branches whose remote tracking branches are gone/deleted. Triggers on phrases like "clean branches", "delete stale branches", "prune branches", "git branch clean", "dọn branch", "xóa branch cũ".
---

# Git Branch Clean

Sync remote state, then find and delete local branches whose remote is gone. Always confirm with user before any deletion.

## Step-by-Step Process

### Step 1: Fetch and prune remote refs

```bash
git fetch --prune
```

This removes remote-tracking refs that no longer exist on remote.

### Step 2: Pull alive tracking branches

Get list of alive tracking branches (not gone, not current):

```bash
git branch -vv | grep -v ': gone]' | grep -v '^\*' | grep '\[origin/' | awk '{print $1}'
```

For each branch in that list, fast-forward update it locally (no checkout needed):

```bash
git fetch origin "<branch>:<branch>" 2>/dev/null && echo "Updated: <branch>" || echo "Skipped (diverged): <branch>"
```

Run one `git fetch origin <branch>:<branch>` per branch. If it fails (diverged), skip silently — don't block. Print result per branch so user can see progress.

Also pull current branch:
```bash
git pull --ff-only 2>/dev/null || echo "Current branch: skipped (diverged or no upstream)"
```

### Step 3: Find stale branches (remote gone)

```bash
git branch -vv | grep ': gone]' | awk '{print $1}'
```

### Step 4: Handle results

**If no stale branches found:**
> "No stale branches. Local repo is clean."

Stop here.

**If stale branches found**, show list and ask user:

> "Found [N] local branch(es) whose remote is gone:
>
> [list each branch on its own line]
>
> Delete all? (yes/no)"

Wait for user reply before continuing.

### Step 5: Delete on confirm

**If user says no** → Stop. Tell user no branches were deleted.

**If user says yes** → Run:

```bash
git branch -vv | grep ': gone]' | awk '{print $1}' | xargs git branch -D
```

Report each deleted branch and confirm done.

## Error Handling

| Error | Action |
|-------|--------|
| Not inside a git repo | "Not a git repo. Run from project root." |
| `git fetch` fails (no remote / auth error) | Show error output. Stop. |
| Branch delete fails (e.g., currently checked out) | Show which branch failed, skip it, delete the rest |
| No branches at all | "Repo has no local branches to check." |

## Safety Rules

- **Never delete without user confirmation.** Always show branch list first.
- **Never force-delete current branch.** If a gone branch is currently checked out, warn and skip it.
- Use `git branch -D` (force delete) because gone branches have no upstream — `-d` would refuse.

## Example Output

```
Fetching and pruning... done.

Found 3 local branch(es) whose remote is gone:

  feature/old-login
  fix/AUTH-99-typo
  chore/remove-deprecated-api

Delete all? (yes/no)
```

User types `yes`:

```
Deleted: feature/old-login
Deleted: fix/AUTH-99-typo
Deleted: chore/remove-deprecated-api

Done. 3 branch(es) removed.
```
