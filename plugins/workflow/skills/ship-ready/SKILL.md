---
name: ship-ready
description: Use this skill when the user wants to prepare a branch for production, open a pull request, or hand off work for review. Trigger on phrases like "ship this", "prep for PR", "get this ready to merge", "open a PR", "create PR", "tạo PR", "make pull request", "push this up".
---

# Ship Ready

Create a pull request from the current branch to a destination branch. Use simple, short English for title and body.

## Step-by-Step Process

### Step 1: Get destination branch

If user did not specify destination branch, ask:

> "Which branch do you want to merge into? (e.g., main, develop, staging)"

Wait for user reply before continuing.

### Step 2: Gather git info

Run these commands in parallel:
- `git branch --show-current` — get current branch name
- `git status --porcelain` — check if working tree is clean
- `git log origin/$(git branch --show-current)..HEAD --oneline 2>/dev/null || echo "NOT_PUSHED"` — check if branch is pushed to remote
- `git log main..HEAD --oneline 2>/dev/null || git log $(git symbolic-ref refs/remotes/origin/HEAD | sed 's@^refs/remotes/origin/@@')..HEAD --oneline 2>/dev/null` — get commits ahead of base
- `git diff --stat HEAD~1 2>/dev/null || git diff --stat` — get changed files summary

### Step 3: Check blockers — ask user to confirm if any

**If git status is NOT clean** (output from `git status --porcelain` is non-empty):
> "You have uncommitted changes:
> [show the dirty files]
> 
> Continue anyway? (yes/no)"

**If branch NOT pushed to remote** (remote tracking branch does not exist or commits ahead):
> "Branch '[branch-name]' is not pushed to remote yet.
>
> Continue anyway? (yes/no)"

If user says **no** to either → stop, tell user to fix then retry.
If user says **yes** → push branch first with `git push -u origin [branch-name]` then continue.

### Step 4: Generate PR title and body

Analyze: current branch name + commits + changed files.

Rules for title:
- Max 70 characters
- Simple present tense ("Add login", "Fix bug in auth", "Update readme")
- No emoji, no ticket prefix unless branch name has one (e.g., `feature/AUTH-123-...` → include `AUTH-123`)
- English only, shortest possible

Rules for body:
- Plain English, short sentences
- Sections: **What**, **Why**, **How to test** (skip sections with nothing useful)
- No fluff, no "This PR...", just facts
- Max 10 bullet points total

### Step 5: Create PR

Use `gh pr create`:

```bash
gh pr create \
  --base [destination-branch] \
  --title "[generated title]" \
  --body "$(cat <<'EOF'
[generated body]
EOF
)"
```

If `gh` not installed or not authenticated: tell user to run `gh auth login` first.

### Step 6: Report result

Show PR URL after creation. Done.

## Error Handling

| Error | Action |
|-------|--------|
| `gh: command not found` | "Install GitHub CLI: `brew install gh` then `gh auth login`" |
| `gh auth` error | "Run `gh auth login` first" |
| Branch already has open PR | Show existing PR URL, ask if user wants to update description instead |
| Push rejected | Show error, ask user to fix conflict then retry |
| Destination branch does not exist on remote | Warn user, confirm to continue |

## Example Output

```
PR created: https://github.com/org/repo/pull/42

Title: Add user authentication with JWT
Branch: feature/auth → main
```
