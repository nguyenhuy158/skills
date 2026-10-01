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
     → background watcher (hub process) + live card updates ('CI: 3/5 passing'); main keeps working
     → watcher exits when CI is 100% green (or names the failed checks)
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

### Execution: watchers run in the background — never polls, never subagents

This skill runs commands, not open-ended research. Keep the main session clean and free for the next step:

- **≤ 10 s** → foreground.
- **10–30 s one-shots** (`git push`, `gh pr create`, `make wt-proxy`) → `bash` with `async: true`, `timeout ≤ 30`.
- **Anything that waits, or may exceed 30 s** — CI / review-bot watch, DB clone, `make wt-up`, `make upgrade`,
  `make test-fresh`, readiness (`curl` until HTTP 200) → a **supervised process**, not a bash job (bash jobs are
  hard-capped at 30 s):
  `hub start name=pr<N>-<purpose> application=… args=[…] cwd=<worktree> pty=false` (before the PR exists, use
  the branch slug instead of `pr<N>`). Start it, then go straight to the next step that does not depend on it.
- **Never `sleep` + poll, never repeated `hub wait`.** The harness injects
  `Supervised process <name> exited with exit code <n>` when it ends — that notice resumes the loop. Read the exit
  code first (0 = done/green), then only the tail: `hub logs name=<name> lines=15` (or `grep: "RESULT|Error"`).
  Nothing independent left to do → end the reply with the status line naming the running watchers
  (`step 6.1/9 — pr<N>-ci watching`); the notice wakes the loop, no babysitting.
- **CI + review bots → always `scripts/pr-watch.sh`** (step 4.2): one line per state change, updates the Orca card
  itself, ends with one `RESULT:` line (exit 0 green · 1 failed · 2 timeout) plus a `COMMENTS:` count.
- **Stuck detection** replaces waiting in a loop: `RESULT: TIMEOUT`, or a clone / wt-up / upgrade running
  > 10 min → check the system directly (`gh api repos/{owner}/{repo}/commits/<sha>/status`, `docker ps`, `curl`),
  then report run time, log tail, direct check and 2–3 options (wait N min / `hub stop` + retry / investigate X).
- A supervised process that already printed its success markers (e.g. `deploy:done`, `http:200`) is done:
  read the markers, `hub stop` it, move on.
- Long runs that are part of the plan the user approved (clone, wt-up, CI/bot watch) need no extra question;
  the decision gates (1.3 stale DB, 2.3 run tests, 7 merge) are still questions.
- **Do not spawn subagents** (`task` tool) for any step of this loop. Subagents start blind, cannot see
  the conversation or the user's decisions at gates 1.3 / 2.3 / 7, and make the loop position unclear.
- The Orca `PR-Watcher` terminal (step 4.1) is for the user's eyes; the agent reads its own hub watcher.

### Browser: `browser-use` CLI in every step

Any step that needs a browser (UI test, login, user switch, GitHub attachment upload, reading a page) uses the
**`browser-use` CLI only** — never agent-browser, the Orca embedded browser, the harness `browser` object,
Playwright/Puppeteer, or another app (a pre-tool hook blocks them). `browser-use` broken → ask the user; never fall back.

It drives the shared **headless agent Chrome** (CDP `http://127.0.0.1:9223`, profile `~/.chrome-agent`, launchd job
`local.agent-chrome`), already logged in to GitHub/Plane/Odoo envs. Headless = it can never steal the user's focus.
- **Every call names this PR's own session**: `BU_NAME=pr<N>-<purpose> browser-use <<'PY' ... PY` (unique per
  agent; never `agent`/`default` — the hook blocks unnamed calls).
- `new_tab(url)` opens the tab in its **own headless window** (always visible, Odoo renders) — keep its targetId and
  reuse it with `switch_tab(<id>)`. `activate_tab` is never needed.
- When the step is done, `close_tab()` your tab: it also stops your daemon (no orphan tabs/daemons).
- Set the viewport (`Emulation.setDeviceMetricsOverride`) inside every call: a shared Chrome may reset it.
- Need to look / log in by hand: ask the user to run `agent-chrome --show`, then `agent-chrome --hide`.

### Test data priority (UI/data tests)

Use the fastest real data first; build from scratch only as the last resort:
1. **Existing records** that already match the scenario (query the worktree DB).
2. **Past records** close to the scenario → move them into the needed state on the **worktree clone DB only**
   (reset stage/status, re-run the workflow action, adjust a field such as signer or amount).
3. **Create new records from scratch** only when no existing or past record can be adapted.

Never touch the root/shared DB for this. Say in the status line which option was used.

**Deep links use ids from the worktree DB, never prod ids.** Local/clone ids differ from prod; look the record
up by name in the clone DB first (`select id from agreement where name = 'CP…'`). A missing id makes Odoo 16's
legacy `BasicModel._fetchRecord` call `Promise.reject()` → misleading `'__raisedOnFormSave' of undefined` dialog.

### UI error root cause — Chrome debugger via `browser-use` (every UI bug)

An Odoo client error dialog (`OwlError … see "cause"`, `__raisedOnFormSave`, `Uncaught Promise`) is a symptom.
Find the throw site **before** blaming or changing code:
1. **Baseline**: revert the change in the worktree (`git revert --no-commit HEAD`), restart Odoo, reproduce.
   Same error on `main` code → pre-existing; restore with `git reset --hard HEAD`.
2. **Failing RPC?** Hook XHR (Odoo 16 RPC uses XHR, not `fetch`) with `Page.addScriptToEvaluateOnNewDocument`,
   reload, list responses with `error`. Also check `docker logs <odoo> --since 3m | grep -A3 Traceback`
   (ignore cron noise: gRPC `:50051`, farmlink).
3. **No RPC error / cause is `undefined`** → pause on the throw with the Chrome debugger:
   ```python
   drain_events(); cdp("Debugger.enable"); cdp("Debugger.setAsyncCallStackDepth", maxDepth=32)
   cdp("Debugger.setPauseOnExceptions", state="all")        # caught + promise rejections
   js("setTimeout(()=>odoo.__WOWL_DEBUG__.root.env.services.action.doAction({...}).catch(()=>{}),200); 1")
   for ev in drain_events():                                  # poll ~15 s
       if ev.get("method") == "Debugger.paused":
           p = ev["params"]; loc = p["callFrames"][0]["location"]
           src = cdp("Debugger.getScriptSource", scriptId=loc["scriptId"])["scriptSource"].split("\n")
           print(p.get("reason"), src[loc["lineNumber"]][loc["columnNumber"]-400:][:600])  # + p["asyncStackTrace"]
           cdp("Debugger.resume")                              # ALWAYS resume, or the page hangs
   cdp("Debugger.setPauseOnExceptions", state="none"); cdp("Debugger.disable")
   ```
   Filter pauses to `reason == "promiseRejection"` with `data.type == "undefined"` when the cause is empty.
4. Report the throw site + why (file/function, the condition that triggered it) before fixing anything.



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
4. **Browser (UI tasks only)**: `agent-chrome` (ensures the headless agent Chrome is up) and
   `curl -s http://127.0.0.1:9223/json/version`. Fails → ask the user; never switch to another browser.

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
     BU_NAME=pr<N>-ui browser-use <<'PY'
     t = new_tab("http://<worktree-slug>.localhost/web")
     wait_for_load()
     print(t, page_info())
     PY
     ```
     Reuse the same tab in later calls (`switch_tab(<t>)`), and `close_tab(<t>)` when step 2.2 is done.
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
   - `browser-use` not working (command missing, daemon cannot connect, port 9223 down)?
     Run `agent-chrome` once; still failing → **stop and ask the user** with the exact error
     (`/tmp/agent-chrome.log`). Do not fall back to another browser or launch another Chrome.
   - Login wall: use the project's documented local test login if it has one (FarmNet: `admin/admin` +
     `login_as_any_user`, see `references/farmnet.md`); otherwise stop and ask. Never type the user's own passwords.
   - **Verify every key state with both screenshot and SQL**, never one alone: read the screenshot back and check
     what the user sees (stage badge, buttons, field values, dialogs, layout), then query the same record in the
     worktree DB (state/stage, ids, links, amounts). Pass only when both agree; a mismatch is a finding to report.
     Record both in the 7.1 captions (e.g. `③ Approved badge · DB stage=reviewed`).
   - **Report the cost of every e2e run**: scripted FarmNet flows go through `scripts/flow-step` (agent-free suite =
     $0 LLM) or the `flow-runner` agent; after an agent run, `scripts/flow-step cost <agent-name>` prints `$` + tokens
     (in / out / cache) + turns — paste that line in the report (format in `references/farmnet.md`).
   - Blocked (no DB/stack/browser)? Say so in the status line and keep step 2.2 open; never report the UI as verified.
   - **Before any manual module upgrade, read the app log first.** Dev containers may already be upgrading the
     changed modules on start; a parallel upgrade deadlocks. Still loading → start a readiness watcher
     (`hub start name=pr<N>-ready application=sh args=["-c", "until curl -sf <url>/web/login >/dev/null; do sleep 3;
     done; echo READY"]`) and continue; on its notice check the installed module version: already current → skip
     the upgrade; still old → run it (`make upgrade` as a supervised process too).
3. **Two test tiers — the gate always runs, isolated tests are the user's call**:
   - **Gate** (2.1, never skipped): lint/format/static checks (FarmNet: `ruff check`, `ruff format --check`, `xmllint`).
   - **Isolated tests** — before running, **ask the user** (yes/no): "Run the isolated tests (~<N> min), or ship
     fast without them?"
     - **Yes** → run the project's isolated test target for every touched module
       (FarmNet: `make test-fresh MODULE=<m>`). Read the summary line from the log, not the exit code alone
       (FarmNet: `0 failed, 0 error(s) of N tests`). A `setUpClass` error hides every test of that class:
       fix fixtures first, rerun.
     - **No (ship fast)** → skip only these, and write "isolated tests skipped by user" in the status line, the
       PR body and the step 7 merge-gate summary. The gate and CI still run.
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

## 4 — Background Watcher (CI & Review Bots)

Never freeze the main session with sleep loops: one supervised watcher per phase, and the agent moves on.

1. **User's view** — a PR-Watcher tab in Orca (for the human only):
   ```bash
   orca terminal create --worktree active --title "PR-Watcher" --command "gh pr checks <N> --watch" --json
   ```
   Keep the terminal handle from its JSON output: teardown closes **only** the terminals the loop opened.
2. **Agent's watcher** — start right after the PR opens, and again after every push:
   ```text
   hub start name=pr<N>-ci application=bash cwd=<worktree> pty=false
     args=["<skill-dir>/scripts/pr-watch.sh", "<N>", "<worktree>", "45"]
   ```
   It polls `gh pr checks --json` every 30 s, writes `PR #<N> CI: X/Y passed` to the Orca card on every change
   (this replaces manual card updates), and exits with `RESULT: GREEN | FAILED <checks> | TIMEOUT` plus
   `FAILED-CHECK: <name> <link>` lines and a `COMMENTS:` count (exit 0 / 1 / 2).
   New push while it runs → `hub stop name=pr<N>-ci`, then start it again.
3. **While it runs** → do the next independent work: 7.1 description + screenshot upload, reply drafts, cleanup
   notes. No `sleep`, no status polls.
4. **Review bots** — after `gh pr ready` (7.2) start `pr<N>-review` with a grace period so bots can register
   their new runs (the draft runs show as `skipping`):
   `args=["<skill-dir>/scripts/pr-watch.sh", "<N>", "<worktree>", "30", "120"]`.
   On its notice read the comments (step 5.1):
   ```bash
   gh api "repos/{owner}/{repo}/pulls/<N>/comments" --jq '.[] | {id, path, line, body}'
   ```
   A bot reporting exhausted usage limits counts as done.

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

1. **Watch**: the `pr<N>-ci` watcher from step 4.2 — no polling. Its exit notice drives the next step:
   exit 0 → 6.3 · exit 1 → 6.2 with the `FAILED-CHECK` lines from `hub logs` · exit 2 → stuck detection.
2. **Fix failures**: for a failed GitHub Actions check,
   ```bash
   gh run view <run-id> --log-failed | tail -60
   ```
   (Jenkins checks: open the check link with `browser-use` — Jenkins needs a login).
   Fix, commit, push, restart the `pr<N>-ci` watcher, loop back to 6.1. New comments → back to step 5.1.
3. **Mark green**: the watcher already wrote `CI Green ✅` to the Orca card; nothing else to run.

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
   - **UI task → attach the step 2.2 screenshots as GitHub user-attachments.**
     **Default — `gh pr edit --attach` (gh ≥ 2.99, no browser, no GitHub login):**
    1. Check: `gh pr edit --help | grep -q -- --attach` — missing → gh is too old: on this machine gh comes from
       **mise** (`~/.config/mise/config.toml`, `gh = "2.101"` since 2026-10-01; `mise install gh`, then a new shell),
       elsewhere `brew upgrade gh`. Ask before upgrading; otherwise use the browser fallback below.
     2. In the body file, reference every PNG as a **relative markdown image spelled exactly like its `--attach`
        path**, inside the `📸 Screenshots` table: `| ① caption | ![desktop](./03-confirm.png) | ![mobile](./03-confirm-mobile.png) |`
        (markdown `![]()` only — `<img src="./…">` is not rewritten).
     3. Run from the screenshot dir so the paths match, ≤ 50 files per call:
        ```bash
        cd ${TMPDIR:-/tmp}/pr-shots/<branch-slug>
        A=(); for f in *.png; do A+=(--attach "./$f"); done
        gh pr edit <N> --body-file <scratchpad>/pr-body.md "${A[@]}"
        ```
        gh uploads each file and rewrites its `./file.png` reference to the `user-attachments/assets/` URL.
        Partial failure: the PR keeps the uploads that worked and gh exits non-zero → rerun for the rest.
     4. Verify `gh pr view <N> --json body`: one `user-attachments/assets/` URL per PNG and **no leftover
        `./…png`** (a leftover = path spelling mismatch → fix and rerun). Videos (`.mp4`/`.mov`) work the same
        and render as players.
     5. Want a fixed width (`<img width>`)? `gh` only rewrites markdown `![]()`, never `<img src="./…">`: after
        step 3, rewrite the uploaded links in the body (`![alt](URL)` → `<img width="420" alt="alt" src="URL">`)
        and `gh pr edit <N> --body-file …` again (no `--attach`). Verified 2026-10-01 on gh 2.101: the 3-column
        table and the widths render exactly like the old drag-and-drop body.
     **Fallback — `browser-use` drag-and-drop** (gh too old and the user does not upgrade):
     1. `BU_NAME=pr<N>-gh browser-use`: `new_tab("https://github.com/<owner>/<repo>/pull/<N>")` in the agent Chrome
        (logged in to GitHub), scroll the **new comment** box `#new_comment_field` into view.
     2. Save the box's current text (the user may have an unsent draft). For each PNG, `cdp("Input.dispatchDragEvent",
        type=…, x, y, data={"items": [], "files": [path], "dragOperationsMask": 1})` for `dragEnter`, `dragOver`,
        `drop` at the textarea center; wait ~6 s per file (`setFileInputFiles` + `change` does not trigger the uploader).
     3. Read the `https://github.com/user-attachments/assets/<uuid>` URLs from the textarea (`<img … src="URL">` or
        `![](URL)` — match both), **restore the saved text without posting**, put the URLs in the body file,
        `gh pr edit <N> --body-file …`, verify with `gh pr view <N> --json body`.
   - Never host images elsewhere (no gist, no repo commit, no external upload). Upload blocked → stop and ask the
     user; keep the text body and say screenshots are pending.
   - Show the user the new body.
2. **Mark Ready for Review** — only when ALL are true: code final, step 2.2 UI verified with screenshots,
   7.1 description applied, CI green, reply scan (5.5) clean:
   ```bash
   gh pr ready <N>
   ```
   This triggers the review bots (`ready_for_review`) and notifies humans.
3. **Review round after ready**: start the `pr<N>-review` watcher (step 4.4) and continue; on its notice loop
   5.1 → 5.5 → 6 until no new comment; update 7.1 if a fix changes behavior or screenshots.
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

1. **Verify Squash Diff** — compare the *change*, not the trees (main may have moved on; the remote branch is
   usually auto-deleted, so use the local branch):
   ```bash
   git -C <main-repo> fetch origin --prune --quiet
   M=<merge_sha>; B=<branch>
   git diff $M^ $M | git patch-id --stable                          # squash commit
   git diff $(git merge-base $B $M^) $B | git patch-id --stable     # branch → MUST print the same id
   ```
   Same id (and same `--name-only` list) → nothing lost. Different → diff the two patches and report.
2. **Project Teardown**:
   - Run project-specific destroy commands (e.g. `make wt-destroy` to drop cloned DB/filestore).
3. **Close the Orca terminals the loop opened** (never `--all`: it also kills the user's own terminals in that
   worktree):
   ```bash
   orca terminal close --terminal <handle> --json      # each handle saved in step 4.1 / when the loop opened it
   ```
   `orca worktree rm` (8.4) still ends every remaining terminal of the worktree: list them for the user
   (`orca terminal list --worktree active --json`) and remove only after they confirm.
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
