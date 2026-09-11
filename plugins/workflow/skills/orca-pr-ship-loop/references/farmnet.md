# FarmNet — Techcoop-vn/farmnet with Orca

Repo: `/Users/huyntq/Documents/techcoop/farmnet-github`. Odoo 16, ~30 custom modules in `src/`,
running in Docker. `AGENTS.md` at the repo root is the authority on coding rules.

## Ground Rules

- Prefix every CLI command run via bash with `rtk` (`rtk proxy make`, `rtk git`, `rtk proxy gh`, etc.).
- Never use `sed`, `mkdir`, `touch`, `rm`, `cp`, `echo >file` for file operations; use built-in tools.
- Orca binary path: `/Applications/Orca.app/Contents/Resources/bin/orca`.

---

## Step 1 — Worktree & Orca Card Setup

```bash
rtk proxy make worktree BRANCH=feature/<kebab-case-description>
```

Path lands at `.claude/worktrees/<slug>`.

Register status in Orca:
```bash
rtk proxy "/Applications/Orca.app/Contents/Resources/bin/orca" worktree set \
  --worktree active \
  --workspace-status in-progress \
  --comment "Developing FarmNet feature" --json
```

If Odoo stack is needed for testing:
```bash
rtk proxy make wt-db-clone
rtk proxy make wt-up
rtk proxy make wt-proxy
```

---

## Step 2 — Gate & Orca Browser Smoke Test

1. Local code gate:
```bash
rtk proxy ruff check src/
rtk proxy ruff format --check src/
rtk proxy xmllint --noout src/<module>/views/<template>.xml
```

2. Smoke test Odoo form/views in Orca Embedded Browser:
```bash
rtk proxy "/Applications/Orca.app/Contents/Resources/bin/orca" tab create \
  --url "http://<container-slug>.localhost" --json
rtk proxy "/Applications/Orca.app/Contents/Resources/bin/orca" wait --timeout 4000
rtk proxy "/Applications/Orca.app/Contents/Resources/bin/orca" snapshot
rtk proxy "/Applications/Orca.app/Contents/Resources/bin/orca" screenshot --format png
```

---

## Step 3 — Visual Diff & Commit

1. Inspect changed files in Orca editor diff:
```bash
rtk proxy "/Applications/Orca.app/Contents/Resources/bin/orca" file open-changed --mode diff
```

2. Commit & push:
Write message to scratchpad with trailer:
```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```
Run `rtk git commit -F <file>` and push.

3. Open PR:
```bash
rtk proxy gh pr create --base main --head <branch> \
  --title "<type>: <description>" --body-file <scratchpad>/pr-body.md
```
Update Orca card:
```bash
rtk proxy "/Applications/Orca.app/Contents/Resources/bin/orca" worktree set \
  --worktree active \
  --comment "PR #<N> opened, awaiting bot reviews & CI" --json
```

---

## Step 4 & 6 — Watcher Terminal & CI Status Streaming

1. Spawn dedicated watcher tab in Orca:
```bash
rtk proxy "/Applications/Orca.app/Contents/Resources/bin/orca" terminal create \
  --worktree active \
  --title "CI-Watcher" \
  --command "rtk proxy gh pr checks <N> --watch" --json
```

2. Update card progress while checks run:
```bash
rtk proxy "/Applications/Orca.app/Contents/Resources/bin/orca" worktree set \
  --worktree active \
  --comment "CI running: 3/5 passing" --json
```

---

## Step 7 — Human Merge Gate

When CI is 100% green and reviews addressed:
```bash
rtk proxy "/Applications/Orca.app/Contents/Resources/bin/orca" worktree set \
  --worktree active \
  --workspace-status in-review \
  --comment "CI Green ✅ Ready for Human Merge" --json
```

---

## Step 8 — Teardown

After merge confirmed:
1. Check squash diff:
```bash
rtk git -C /Users/huyntq/Documents/techcoop/farmnet-github diff <merge_sha> origin/<branch>
```
2. Tear down Docker stack & filestore:
```bash
rtk proxy make wt-destroy
```
3. Close all Orca terminals in this worktree:
```bash
rtk proxy "/Applications/Orca.app/Contents/Resources/bin/orca" terminal close --worktree active --all --json
```
4. Remove worktree and Orca workspace card:
```bash
rtk proxy "/Applications/Orca.app/Contents/Resources/bin/orca" worktree rm --worktree active --force --json
rtk git -C /Users/huyntq/Documents/techcoop/farmnet-github branch -D <branch>
rtk git -C /Users/huyntq/Documents/techcoop/farmnet-github fetch origin --prune
```
