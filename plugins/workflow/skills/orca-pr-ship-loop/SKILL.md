---
name: orca-pr-ship-loop
description: >-
  Full-cycle shipping loop using Orca CLI as a Shipping Cockpit: task → Orca worktree & card
  status → implement & visual browser test → commit, push, PR → dedicated watcher terminal for
  review bots & CI → reply to comments → watch CI with live workspace updates → human merge gate
  → full teardown (Docker DB/filestore, PTY terminals, Git branch, and Orca UI cards). Use when
  shipping PRs within Orca IDE or when the user asks to "ship PR with orca", "orca ship loop",
  "orca pr loop", or "chạy ship loop bằng orca".
---

# Orca PR Ship Loop

A continuous, high-visibility shipping workflow integrating Git/GitHub lifecycle with Orca IDE:

```
task → Orca worktree + card status ('in-progress')
     → implement + local gate + visual smoke test (Orca Embedded Browser)
     → visual diff inspection (Orca editor) → commit, push, PR
     → dedicated watcher terminal (review bots + CI polling)
     → live workspace card updates ('CI: 3/5 passing')
     → address comments (reply on PR) → push
     → watch CI until 100% green ──┐
     ↑                             │ any failure or new comments
     └─────────────────────────────┘
     → set card status 'in-review' → Human Merge Gate
     → verify squash diff → clean everything (Docker, PTYs, Git, Orca UI cards)
```

---

## Orca CLI Pre-flight

Resolve the Orca executable once per session:
1. `ORCA_CLI_COMMAND` if set.
2. `/Applications/Orca.app/Contents/Resources/bin/orca` (macOS default for Orca.app).
3. `orca` if available in `PATH`.

Prefer `--json` for programmatic inspection.

---

## 1 — Worktree & Cockpit Setup

1. **Create/Register the Worktree**:
   - Follow repo naming convention (`<type>/<kebab-case-description>` from default branch).
   - If the project has a custom worktree target (e.g. FarmNet `make worktree BRANCH=...`), execute that, then inspect or register with Orca. Otherwise create via Orca:
     ```bash
     orca worktree create --name <type>/<description> --json
     ```
2. **Initialize Workspace Card Status**:
   ```bash
   orca worktree set --worktree active --workspace-status in-progress --comment "Implementing: <brief-goal>" --json
   ```
   *(If an issue number or Linear URL is known, pass `--issue <number>` or `--linear-issue <identifier>`)*.

---

## 2 — Implement, Gate & Visual Verification

1. **Local Checks**:
   - Run repo lint, format, and static analysis commands (`ruff check`, `xmllint`, `eslint`, etc.).
2. **Visual Smoke Testing (Orca Embedded Browser)**:
   - When the change affects UI (views, templates, web forms, styles):
     ```bash
     orca tab create --url "http://<worktree-slug>.localhost" --json
     orca wait --timeout 3000
     orca snapshot
     orca screenshot --format png
     ```
   - Verify layout and buttons visually before claiming completion.

---

## 3 — Visual Diff, Commit & Open PR

1. **Inspect Changes via Orca Diff Viewer**:
   ```bash
   orca file open-changed --mode diff
   ```
   Allows reviewing modified files side-by-side in Orca editor.
2. **Commit via Message File**:
   - Write commit message to a scratchpad file.
   - Commit with `git commit -F <file>` (avoids shell quoting/heredoc truncation).
3. **Open PR & Update Card**:
   ```bash
   gh pr create --base <default-branch> --head <branch> \
     --title "<type>: <description>" --body-file <scratchpad>/pr-body.md
   ```
   Update Orca card:
   ```bash
   orca worktree set --worktree active --comment "PR #<N> opened; awaiting bots & CI" --json
   ```

---

## 4 — Dedicated Watcher Terminal (Bot Reviews & CI)

Do not freeze the main agent session with sleep loops!

1. **Spawn Background Watcher Tab**:
   ```bash
   orca terminal create --worktree active --title "PR-Watcher" --command "gh pr checks <N> --watch" --json
   ```
2. **Poll Review Bots**:
   - Query inline comments:
     ```bash
     gh api "repos/{owner}/{repo}/pulls/<N>/comments" --jq '.[] | {id, path, line, body}'
     ```
   - If a bot reports usage limits exhausted, treat as terminal and proceed.
3. **Stream Progress to Workspace Card**:
   - As checks progress, update the comment so the user sees status on their sidebar:
     ```bash
     orca worktree set --worktree active --comment "CI running: <X>/<Y> passed..." --json
     ```

---

## 5 — Address Comments & Reply on the PR

1. **Triage Reviews**:
   - Fix genuine bugs; decline out-of-scope or speculative suggestions with reasoned explanation.
2. **Commit Fix & Push**:
   - Commit as a separate commit (never amend/force-push).
   - Push to remote.
3. **Reply in Thread**:
   ```bash
   gh api "repos/{owner}/{repo}/pulls/<N>/comments/<comment_id>/replies" \
     -F body=@<scratchpad>/reply.md --jq .html_url
   ```

---

## 6 — Watch CI Until 100% Green

- Watch until all checks pass.
- If a check fails:
  ```bash
  gh run view <run-id> --log-failed | tail -60
  ```
  Fix the issue, push, and loop back until all checks are green.
- Once green:
  ```bash
  orca worktree set --worktree active --comment "CI Green ✅ All checks passed" --json
  ```

---

## 7 — Human Merge Gate

Merging is strictly a human decision.
1. **Set Card Status to In-Review**:
   ```bash
   orca worktree set --worktree active --workspace-status in-review --comment "CI Green ✅ Waiting for Human Merge" --json
   ```
2. **Notify User**:
   - Present PR link, checks summary, and confirm readiness for user to merge.

---

## 8 — Full Teardown & UI Hygiene

Once user confirms PR is merged:

1. **Verify Squash Diff**:
   ```bash
   git -C <main-repo> fetch origin --prune --quiet
   git -C <main-repo> diff <merge_sha> origin/<branch>   # MUST BE COMPLETELY EMPTY
   ```
2. **Project Teardown**:
   - Run project-specific destroy commands (e.g. `make wt-destroy` to drop cloned DB/filestore).
3. **Clean Orca Terminals (Kill PTYs)**:
   ```bash
   orca terminal close --worktree active --all --json
   ```
4. **Remove Git Worktree & Orca Card**:
   ```bash
   orca worktree rm --worktree active --force --json
   git -C <main-repo> branch -D <branch>
   git -C <main-repo> fetch origin --prune
   ```
5. **Report Final State**:
   - Confirm DB, volumes, PTY terminals, local branch, and Orca card are 100% cleaned.
