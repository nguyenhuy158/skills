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
task → environment pre-flight (Docker, gh, Orca)
     → Orca worktree + card status ('in-progress')
     → UI/data task? clone worktree DB from root (fresh ≤ 2 days, else ASK user: use stale / sync root)
     → implement + local gate + tests (ASK user: run / ship fast) + self-review + UI check (browser-use CLI only)
     → visual diff inspection (Orca editor) → commit, push, DRAFT PR
     → dedicated watcher terminal (CI polling) + live card updates ('CI: 3/5 passing')
     → watch CI until 100% green
     → PR description (little text + ASCII chart + screenshots) → `gh pr ready` (bots + humans review)
     → triage EVERY comment (fix or decline) → reply on PR → reply-coverage scan X/X → push ──┐
     ↑                                                        new comments or CI failure    │
     └──────────────────────────────────────────────────────────────────────────────────────┘
     → final reply scan clean → card 'in-review' → Human Merge Gate
     → verify squash diff → clean everything (Docker, PTYs, Git, Orca UI cards)
     → sync task tracker status
```

---

## Orca CLI Pre-flight

Resolve the Orca executable once per session:
1. `ORCA_CLI_COMMAND` if set.
2. `/Applications/Orca.app/Contents/Resources/bin/orca` (macOS default for Orca.app).
3. `orca` if available in `PATH`.

Prefer `--json` for programmatic inspection.

### Status line & sub-step announce (every reply, every action)

Start every reply of the loop with one line: `Ship loop: step <X.Y>/9 — <step name> · PR #<N> · skills: <used>`.
The user cannot hold the loop position between turns; this line is the source of truth.

**End every reply of the loop with a links block**, whenever the item exists (omit a line only if it does not exist yet):
```
🔗 PR:   https://github.com/<owner>/<repo>/pull/<N>
🖥️ Odoo: http://<container-name>.localhost  (admin/admin)
```
The Odoo line is the worktree's local URL printed by `make wt-proxy` (never `localhost:<port>`); drop it once
step 8 has torn the stack down.

**Before each action**, announce the exact sub-step it belongs to, at the deepest level that exists
(`Step 1.3 — checking root DB freshness`, `Step 2.2 — Orca browser smoke test`, `Step 5.1 — triage table`).
Never run a command without its step number; never report "step 2" when the work is 2.3.

### Execution: background jobs, not subagents

This skill runs commands, not open-ended research. Every command expected to take **more than 10 s**
runs as a **background job** (`bash` with `async: true`): DB clone, `make test-fresh`, `gh pr checks --watch`,
`wt-up`, builds. Wait on the job id; read its output; continue.

- **Timeout: every background job gets `timeout ≤ 30` s.** Set it explicitly on the call.
- **Needs longer than 30 s?** (test suites, DB clone, image build, CI watch) → **ask the user first**:
  state the command, the expected duration, and why; run with the longer timeout only after a yes.
  One yes covers the same command for the rest of the PR (e.g. every rerun of `make test-fresh`).
- A job killed by the 30 s timeout is not a failure of the code: report it and ask whether to rerun longer.
- **Two timed-out waits on the same job = stop.** After the second `wait` that returns
  "still running", never issue a third. Read its output (`hub logs`), check the underlying
  system directly (deploy API, `docker ps`, `curl` the URL, `gh run view`), and report to the
  user: how long it has run, what the logs say, what the direct check says, and 2–3 options
  (keep waiting N minutes / kill and retry / investigate X). Waiting in a loop hides a job that
  finished its work but never exits, and burns the turn.
- A supervised process that already printed its success markers (e.g. `deploy:done`, `http:200`)
  is done: read the markers, kill it, move on — do not wait for the process to exit.
- **Do not spawn subagents** (`task` tool) for any step of this loop. Subagents start blind, cannot see
  the conversation or the user's decisions at gates 1.3 / 2.3 / 7, and make the loop position unclear.
- Short commands (≤ 10 s) run in the foreground.
- The Orca `PR-Watcher` terminal (step 4.1) is for the user to watch; the agent still reads CI through `gh`.

### Browser: `browser-use` CLI in every step

Any step that needs a browser (UI test, login, user switch, GitHub attachment upload, reading a page) uses the
**`browser-use` CLI only** — never the Orca embedded browser, the harness `browser` object, Playwright/Puppeteer,
or another app. `browser-use` broken → ask the user to check it; never fall back.

**Never steal the user's focus**: do not call `activate_tab()` (CDP `Target.activateTarget`) or `headed`/foreground
helpers. They pull Chrome to the front on every call while the user works in other apps. Pick the tab with
`switch_tab(<targetId>)` only; `capture_screenshot`, `js`, `cdp` and drag-drop upload all work on a background tab.
Set the viewport (`Emulation.setDeviceMetricsOverride`) inside every call: a shared Chrome may reset it between calls.

### Test data priority (UI/data tests)

Use the fastest real data first; build from scratch only as the last resort:
1. **Existing records** that already match the scenario (query the worktree DB).
2. **Past records** close to the scenario → move them into the needed state on the **worktree clone DB only**
   (reset stage/status, re-run the workflow action, adjust a field such as signer or amount).
3. **Create new records from scratch** only when no existing or past record can be adapted.

Never touch the root/shared DB for this. Say in the status line which option was used.


### Ask when unsure (every step)

If any step's check leaves the next action unclear — unexpected output, a check that is neither pass nor fail,
two plausible fixes with different trade-offs, missing access/data, or a result that contradicts the plan —
**stop and ask the user** before continuing. Never guess and never skip ahead.

- Ask one short question with 2–3 concrete options, recommendation first.
- State what was checked, what came back, and why it is ambiguous.
- Mark the step as blocked in the status line (`step X/9 — waiting on user`) until answered.
- Decision gates already defined (1.3 stale DB, 2.3 run tests, 7 merge) are always questions, never defaults.

---

## 0 — Environment Pre-flight

Run before creating anything; a dead daemon mid-loop wastes whole test runs.

1. **Docker**: `docker info --format '{{.ServerVersion}}'` — fails → start the runtime (OrbStack: `orb start`), re-check.
2. **GitHub CLI**: `gh auth status`.
3. **Orca CLI**: `orca --version`.
4. **Browser (UI tasks only)**: `browser-use --doctor`. Fails → ask the user to check the `browser-use` CLI
   before step 2.2; never switch to another browser.

If Docker dies later (`docker.sock: no such file`), restart it and rerun only the failed sub-step.

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
3. **Worktree Database (only when the task touches UI or data)**:
   - Skip for pure logic/CI/docs tasks.
   - Clone the worktree DB **from the root repo database**, never from a guessed container.
   - Before cloning, check the source is fresh: newest business record within the last **2 days**.
     ```sql
     SELECT max(write_date) FROM <main_business_table>;   -- FarmNet: sale_order, account_move
     ```
   - Fresh (≤ 2 days) → clone and continue.
   - Stale (> 2 days) → **stop and ask the user** (one question, two options):
     1. Use the stale data anyway — continue, and note "stale DB (<date>)" in the status line.
     2. Sync the root DB first — wait for the user to confirm the sync, re-check freshness, then clone.
   - Never refresh or overwrite the root database yourself.
   - **Stack refuses to start because the DB is newer than the code (downgrade guard)** → first rebase:
     `git fetch origin`; if `origin/main` holds the DB's module version and the branch is behind, rebase onto
     `origin/main`, rerun lint, push with `--force-with-lease` (standing user approval for this case only),
     restart the stack. Branch already contains `origin/main` → rebase cannot help: **ask the user**
     (start without touching the schema, or sync the root DB). Project details: `references/<project>.md`.

---

## 2 — Implement, Gate & Visual Verification

1. **Local Checks**:
   - Run repo lint, format, and static analysis commands (`ruff check`, `xmllint`, `eslint`, etc.).
2. **Visual Smoke Testing — `browser-use` CLI only**:
   - When the change affects UI (views, templates, web forms, styles), use the **`browser-use` CLI**
     (read `skill://browser-use` first). **No other browser tool**: not the Orca embedded browser,
     not the harness `browser` object, not Playwright/Puppeteer, not screenshots of another app.
     ```bash
     browser-use <<'PY'
     new_tab("http://<worktree-slug>.localhost/web")
     wait_for_load()
     print(page_info())
     PY
     ```
     Reuse the same tab in later calls (`current_tab()` / `switch_tab()`).
   - **Capture screenshots while testing (UI tasks, mandatory)**: one PNG per verified state
     (e.g. before action, dialog open, after confirm). Save **outside the repo** to
     `${TMPDIR:-/tmp}/pr-shots/<branch-slug>/<NN>-<state>.png` so nothing can be committed by accident,
     and keep a list `file → one-line caption` for step 7.1.
   - **Show the chatter / log note when the model has one** (Odoo `mail.thread`): before capturing, zoom out
     so the form **and** the chatter fit in one frame — e.g. `js("document.body.style.zoom='67%'")`, or a wider
     viewport via `cdp("Emulation.setDeviceMetricsOverride", width=1920, height=1200, deviceScaleFactor=1, mobile=False)`.
     Scroll the chatter so the entry produced by the action (e.g. the over-limit log) is visible. **Keep that zoom**
     for the remaining shots — do not reset it. Dialog shots may hide the chatter behind the modal; the
     after-action shot must show it.
   - **Mobile version (every UI action, mandatory)**: repeat the key states on a phone viewport with `browser-use`:
     `cdp("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=3, mobile=True)` +
     `cdp("Emulation.setTouchEmulationEnabled", enabled=True)`, reload, redo the action, capture
     `<NN>-<state>-mobile.png` (same ①②③ marks). Clear the override after
     (`Emulation.clearDeviceMetricsOverride`). Put desktop | mobile side by side in the 7.1 screenshot table.
     Broken layout on mobile = a bug to fix before 7.2, not a screenshot to skip.
   - **Annotate on the page, before capturing** (not by editing the PNG afterwards): with `browser-use`, read the
     target element's `getBoundingClientRect()`, inject a `position:fixed` overlay — red border
     (`border-radius:8px` box or `50%` circle), `pointer-events:none`, high `z-index` — plus a short label
     (e.g. `①  Over-limit warning`) just above it; capture; then remove the overlays. Number the key elements
     ①②③ per shot (≤ 3 per shot) and reuse the same numbers in the step 7.1 captions.
     ```python
     js("""((sel, label) => { const r = document.querySelector(sel).getBoundingClientRect();
       const box = Object.assign(document.createElement('div'), {className: '__pr_mark'});
       box.style.cssText = `position:fixed;left:${r.left-6}px;top:${r.top-6}px;width:${r.width+12}px;`
         + `height:${r.height+12}px;border:3px solid #e03131;border-radius:8px;z-index:99999;pointer-events:none`;
       const tag = Object.assign(document.createElement('div'), {className: '__pr_mark', textContent: label});
       tag.style.cssText = `position:fixed;left:${r.left-6}px;top:${r.top-32}px;background:#e03131;color:#fff;`
         + `font:600 13px sans-serif;padding:3px 8px;border-radius:6px;z-index:99999;pointer-events:none`;
       document.documentElement.append(box, tag); })('<css selector>', '① <label>')""")  # html, not the zoomed body
     capture_screenshot(path=...)
     js("document.querySelectorAll('.__pr_mark').forEach(e => e.remove())")
     ```
   - `browser-use` not working (command missing, daemon cannot connect, `browser-use --doctor` fails)?
     **Stop and ask the user** to check the `browser-use` CLI (install, Chrome remote debugging at
     `chrome://inspect/#remote-debugging`, macOS remote-debugging approval). Do not fall back to another browser.
   - Login wall: use the project's documented local test login if it has one (FarmNet: `admin/admin` +
     `login_as_any_user`, see `references/farmnet.md`); otherwise stop and ask. Never type the user's own passwords.
   - Verify layout and buttons visually before claiming completion.
   - Blocked (no DB/stack/browser)? Say so in the status line and keep step 2.2 open; never report the UI as verified.
   - **Before any manual module upgrade, read the app log first.** Dev containers may already be upgrading the
     changed modules on start; a parallel upgrade deadlocks. Still loading → watch (≤ 30 s polls) until HTTP 200;
     then check the installed module version: already current → skip the upgrade; still old → run it.
3. **Isolated Tests — user decides**:
   - Before running, **ask the user** (yes/no): "Run the isolated tests (~<N> min), or ship fast without them?"
     - **Yes** → run the project's isolated test target for every touched module
       (FarmNet: `make test-fresh MODULE=<m>`). Read the summary line from the log, not the exit code alone
       (FarmNet: `0 failed, 0 error(s) of N tests`). A `setUpClass` error hides every test of that class:
       fix fixtures first, rerun.
     - **No (ship fast)** → skip, and write "tests skipped by user" in the status line, the PR body
       and the step 7 merge-gate summary. CI still runs.
   - Ask once per PR; reuse the answer for later fix commits unless the user changes it.
4. **Self-Review Before Push** (catches what bots flag later):
   - **Override chain**: for every overridden method, `rg "def <method>"` across all modules. Any override that
     calls `super()` and drops its return value (or acts after it) breaks a "return an action" design —
     prefer raising, or a new button method.
   - **Client-forgeable flags**: context keys, kwargs and hidden fields are set by any RPC caller. Never gate a
     permission or bypass on them; use values RPC cannot send (recordsets) or a server-side check.
   - **UI-only constraints**: `domain=`, `invisible`, `readonly` do not validate server-side. Re-check in the method.
   - **ACL scope**: a wizard/model readable by `base.group_user` is callable by every internal user;
     re-check who may act inside the action method.
   - **Other entry points**: controllers/APIs/crons calling the same method must get a correct result or an explicit error.
   - **Multi-record assumptions**: `[:1]`, `ensure_one()` — confirm the data model really is single.
   - **Migration only when prod needs it**: before writing a migration or data backfill, query **prod**
     (read-only, e.g. the `odoo_prod` MCP `search_records`) for rows the change would fix. Prod has none →
     no migration, no version bump. Fix dev/local data with a one-off hotfix (SQL/RPC on that env) or a DB
     restore instead, and say which in the status line. Write the migration only when prod actually holds
     the broken data.

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
3. **Open the PR as a DRAFT & Update Card**:
   ```bash
   gh pr create --draft --base <default-branch> --head <branch> \
     --title "<type>: <description>" --body-file <scratchpad>/pr-body.md
   ```
   The PR stays draft until step 7.2: bots and humans review only finished, verified work.
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

1. **Triage EVERY Comment** (bots and humans), then show the user a table before editing:
   | # | Author | Finding | Verdict (fix / decline) | Reason |
   - Fix genuine bugs; decline out-of-scope or speculative suggestions with a reasoned, evidence-backed explanation.
   - While fixing, re-run the step 2.4 self-review: one bot finding often reveals a sibling bug.
2. **Commit Fix & Push**:
   - Commit as a separate commit (never amend/force-push).
   - Push to remote.
3. **Reply in Thread**:
   ```bash
   gh api "repos/{owner}/{repo}/pulls/<N>/comments/<comment_id>/replies" \
     -F body=@<scratchpad>/reply.md --jq .html_url
   ```
   - Reply to every comment, including declines. Never leave a thread silent.
4. **Re-verify**: if the user chose to run tests in step 2.3, rerun them before pushing the fix commit.
5. **Reply-coverage scan (after every round, and again before 7.2 / 7.4)**: list every top-level review
   comment and confirm each has a reply from us; any gap → reply now.
   ```bash
   gh api "repos/{owner}/{repo}/pulls/<N>/comments" --paginate --jq '
     (map(select(.in_reply_to_id != null and .user.login == "<me>") | .in_reply_to_id) | unique) as $done
     | map(select(.in_reply_to_id == null and ((.id) as $i | $done | index($i) | not)))
     | .[] | "\(.id) \(.user.login) \(.path):\(.line)"'
   ```
   Also read review bodies (`gh pr view <N> --json reviews`) and PR conversation comments
   (`gh api repos/{owner}/{repo}/issues/<N>/comments`) for findings outside inline threads.
   Report "replied X/X" in the status line; never move on with an unreplied comment.

---

## 6 — Watch CI Until 100% Green

1. **Watch**: wait on the `gh pr checks <N> --watch` background job until every check settles.
2. **Fix failures**: for a failed check,
   ```bash
   gh run view <run-id> --log-failed | tail -60
   ```
   fix, commit, push, and loop back to 6.1. New comments → back to step 5.1.
3. **Mark green**:
   ```bash
   orca worktree set --worktree active --comment "CI Green ✅ All checks passed" --json
   ```

---

## 7 — Human Merge Gate

Merging is strictly a human decision.
1. **Update the PR Description (mandatory, before telling the user it is done)**:
   - Rewrite the body from the **final** diff (all fix commits included), not the first draft.
     `pr-desc-updater` skill may be used for reading the diff; the format below wins.
   - **Little text**: no paragraphs; every line ≤ ~80 chars; max ~25 lines total.
   - **One ASCII box chart** showing what the PR changes (flow / before→after), with icons:
     ```
     ┌──────────────┐    ┌───────────────────┐    ┌──────────────┐
     │ 🧾 SO amount │ ─▶ │ ⚖️  >= signer limit │ ─▶ │ 👔 CEO added │
     └──────────────┘    └───────────────────┘    └──────┬───────┘
                                                        ▼
                                              ┌───────────────────┐
                                              │ 🪟 confirm dialog │
                                              └───────────────────┘
     ```
   - Then short sections, icons as headers:
     `✨ What` (≤ 4 bullets) · `🛡️ Safety` (only if relevant) · `🧪 Tests` (result, or "skipped by user")
     · `🔍 How to check` (≤ 3 steps).
   - Keep box chars aligned (monospace); wrap the chart in a fenced code block.
   - **UI task → attach the step 2.2 screenshots as GitHub user-attachments**, using the `browser-use` CLI only:
     1. Write the body text first with `gh pr edit <N> --body-file <scratchpad>/pr-body.md`.
     2. `browser-use`: `new_tab("https://github.com/<owner>/<repo>/pull/<N>")` in the user's logged-in Chrome
        (then `switch_tab`, never `activate_tab`), scroll the **new comment** box `#new_comment_field` into view.
     3. Upload by **drag-and-drop** (the only reliable path; `setFileInputFiles` + `change` does not trigger
        GitHub's uploader, and the `…` → Edit menu is ambiguous): for each PNG, `cdp("Input.dispatchDragEvent",
        type=…, x, y, data={"items": [], "files": [path], "dragOperationsMask": 1})` for `dragEnter`, `dragOver`,
        `drop` at the textarea center; wait ~6 s per file.
     4. Read the `https://github.com/user-attachments/assets/<uuid>` URLs from the textarea, then **clear it
        without posting**. Put the images in a 2-column `📸 Screenshots` table with captions in the body file.
     5. `gh pr edit <N> --body-file …`; verify with `gh pr view <N> --json body` that every URL is present.
   - Never host images elsewhere (no gist, no repo commit, no external upload). Not logged in to GitHub, upload
     stuck, or `browser-use` failing → stop and ask the user; keep the text body and say screenshots are pending.
   - Show the user the new body.
2. **Mark Ready for Review** — only when ALL are true: code final, step 2.2 UI verified with screenshots,
   7.1 description applied, CI green, reply scan (5.5) clean:
   ```bash
   gh pr ready <N>
   ```
   This triggers the review bots (`ready_for_review`) and notifies humans.
3. **Review round after ready**: wait for the bots (background jobs, ≤ 30 s polls), then loop 5.1 → 5.5 → 6
   until no new comment; update 7.1 if a fix changes behavior or screenshots.
4. **Final reply scan** (5.5) → must be clean.
5. **Set Card Status to In-Review**:
   ```bash
   orca worktree set --worktree active --workspace-status in-review --comment "CI Green ✅ Waiting for Human Merge" --json
   ```
6. **Notify User**:
   - Present PR link, checks summary, reply coverage (X/X), the updated description, and confirm readiness to merge.

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

---

## 9 — Task Tracker Sync

Follow the repo rule for the linked task (FarmNet / Plane):
1. **PR merged** → task **In Progress** (not Done).
2. **Released** → task **Done** only after the PR ships in a released tag.

Report the task ID and its new status in the final message.
