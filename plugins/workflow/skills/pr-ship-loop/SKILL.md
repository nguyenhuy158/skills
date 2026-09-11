---
name: pr-ship-loop
description: Ship a change end to end without stopping — worktree or branch, implement, gate, open the PR, wait for the review bots to land, reply to every review comment, watch CI until every check is green, then verify what actually merged and clean up everything behind it. Use this for any work that touches a PR's lifecycle, in English or Vietnamese, including when the user asks for only one step of it — opening the PR, watching CI, addressing or replying to review comments, or cleaning up after a merge. Each of those looks like one `gh` command and isn't. `gh pr view` hides inline review comments, so you confidently report "no comments" on a PR that has five. A squash merge makes `git branch -d` refuse, and makes ancestry checks lie about whether your later commits landed. `git fetch` without `--prune` leaves the merged branch sitting in your checkout. An isolated test run leaves a database volume behind that the project's own teardown reports as removed. Load this before any of them, then carry the rest of the chain to done.
---

# PR ship loop

One continuous run from receiving a task to a merged PR with nothing left behind:

```
task → branch/worktree → implement + gate → commit, push, PR
     → wait for review bots → address comments (reply on the PR) → push
     → watch CI until every check passes ──┐
     ↑                                     │ any failure or new comments
     └─────────────────────────────────────┘
     → PR merged (a human's call) → delete branch, clean everything
```

Carry it to the end rather than stopping once the PR is open. When the user asks for one step
("watch CI giùm á"), resume there — then keep going down the chain and report where things stand.

## Before you start: read the repo's own rules

This skill is the mechanics of shipping; the repo decides the content rules. Spend a minute up
front so you don't guess:

- `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md` — branch naming, PR title format, commit trailers,
  whether a bot enforces Conventional Commits, and any hard constraints on tooling
- `Makefile`, `package.json` scripts, `.pre-commit-config.yaml`, `.github/workflows/` — the exact
  lint/format/test commands CI will run, so your local gate matches
- `git worktree list` — whether this project works out of worktrees or plain branches

**Repo-specific notes live in `references/`.** Read the matching file before you start if one
exists — it carries the traps that only bite in that repo:

- `references/farmnet.md` — Techcoop-vn/farmnet (Odoo 16, `make worktree`, the `rtk` CLI proxy)

`gh api` expands `{owner}` and `{repo}` from the current repo, so every API path below works
unchanged anywhere. Keep the placeholders instead of hardcoding a repo.

## 1 — Branch or worktree

Follow the repo's naming rule; a common one is `<type>/<kebab-case-description>` with type from
`feature|fix|chore|ci`, branched from the default branch. If the project ships a worktree helper
(`make worktree` and friends), use it rather than `git worktree add` by hand — it wires up the
database, ports and hostnames that a bare worktree won't have.

**Only boot the app stack if you actually need to run the app.** Work you will code, lint and PR
without clicking through a UI needs the checkout and nothing more. That saves minutes now and
leaves nothing to tear down in step 8.

## 2 — Implement, then gate

Run the repo's own checks before calling the code done — the same commands CI runs, found in the
recon above. Typical shape:

```bash
<lint command>          # e.g. ruff check src/ , eslint . , golangci-lint run
<format check command>  # the --check variant, so it reports instead of rewriting
<test command>          # scoped to what you touched, if the project supports it
```

Also validate file types whose errors only surface at runtime — templates, views, migrations,
schema files. A malformed template usually passes import and fails in front of a user, so parse it
locally (`xmllint --noout`, `jq . >/dev/null`, `yamllint`, whatever fits).

Leave one runnable check behind for non-trivial logic (a branch, a loop, a money path): the
smallest thing that goes red if the logic breaks. Where a layer has no harness at all, say so
plainly instead of letting "verified" imply coverage that doesn't exist. Same for anything
deferred — naming it costs a sentence and spares the reviewer from assuming it's done.

## 3 — Commit, push, open the PR

```bash
git status --short          # look before you `add -A`
git add -A
git commit -F <scratchpad>/commit-msg.txt
git push -u origin <branch>
```

Write the commit message to a file with the Write tool and pass it with `-F`. Heredocs into
`commit -F -` break under CLI wrappers that don't forward stdin, and the failure mode is a silent
`Aborting commit due to empty commit message`. Add whatever trailer the repo mandates.

Check `git status` before `add -A` for a concrete reason: if another agent session is editing the
same checkout, `add -A` swallows its uncommitted work into your commit.

```bash
gh pr create --base <default-branch> --head <branch> \
  --title "<type>: <description>" --body-file <scratchpad>/pr-body.md
```

Write the body with the Write tool too — heredocs and long `-f` strings get mangled by shell
quoting. Give it four parts, because this is what a reviewer actually needs:

- **Why** — the problem, or the evidence that motivated the change
- **What changed** — grouped by component, not a restatement of the diff
- **Not in this PR** — anything deferred, unconsumed, or knowingly incomplete. This is the part
  people skip and the part reviewers value most; a component shipped with no consumer, or a step
  the plan dropped, belongs here instead of being discovered in review
- **Verification** — what you actually ran, with results

Never amend or force-push unless asked. Follow-ups are new commits.

## 4 — Wait for the review bots to land

Bot reviews don't arrive with the PR — budget around five minutes. Poll in the background so the
session isn't blocked (`run_in_background: true`; you get a notification when it exits):

```bash
for i in $(seq 1 20); do
  n=$(gh api "repos/{owner}/{repo}/pulls/<N>/reviews" --jq 'length')
  [ "$n" -gt 0 ] && break
  sleep 30
done
gh api "repos/{owner}/{repo}/pulls/<N>/reviews" --jq '.[] | {user: .user.login, state, submitted_at}'
```

Launch step 6's CI watch in the same turn as this poll rather than after it. Both are background
waits on the same push, CI usually settles first, and nothing you do in step 5 depends on the
checks — running them in sequence just adds the slower wait on top of the faster one.

A bot that has run out of credits posts an issue comment saying so instead of reviewing, and
waiting on it is waiting forever. So when the loop comes back empty, read the issue comments before
assuming the bot is still thinking:

```bash
gh pr view <N> --json comments --jq '.comments[] | {author: .author.login, body}'
```

If a bot says its limits are exhausted, that's terminal, not slow. Say so and move on to CI.

## 5 — Address the comments, and reply on the PR

**Inline review comments are invisible to `gh pr view --json comments`** — that returns only
issue-level comments, so you will confidently report "no comments" while several sit on the diff.
They live on the pulls API:

```bash
gh api "repos/{owner}/{repo}/pulls/<N>/comments" --jq '.[] | {id, path, line, body}'
```

Judge each comment on merit; don't comply reflexively. Bot reviews mix real defects with
cargo-cult suggestions. A stale render dependency or a dropped ARIA attribute is usually a genuine
bug worth a one-line fix. A comment demanding a full interface contract on a component that has no
consumer yet is asking you to invent requirements — decline that, and say why in the reply, because
a reasoned "not now, because the component doesn't own the panels" is worth more to the next reader
than silence.

Fix the real ones, gate again (step 2), commit and push as a **separate** commit. Then reply into
each thread:

```bash
gh api "repos/{owner}/{repo}/pulls/<N>/comments/<comment_id>/replies" \
  -F body=@<scratchpad>/reply.md --jq .html_url
```

Use `-F body=@file`, never `-f body='...'`. Bodies with backticks, quotes or newlines get mangled
by the shell, and a mangled reply is public. Reference the new sha so the reviewer can see what
changed. If one does land wrong, patch it — note the edit endpoint takes the *reply's* id and drops
the PR number:

```bash
gh api -X PATCH "repos/{owner}/{repo}/pulls/comments/<reply_id>" \
  -F body=@<scratchpad>/reply.md --jq .body
```

A bot keeps its old verdict ("changes recommended") until someone re-requests its review, which is
a UI action on the PR. Tell the user that rather than presenting the stale verdict as a failure —
or pretending you cleared it.

## 6 — Watch CI until every check passes

Every push restarts the checks, so this step runs again after each round of fixes. Snapshot once,
then watch in the background:

```bash
gh pr checks <N>                                     # snapshot
gh pr checks <N> --watch --interval 30 2>&1 | tail -20
```

**A red check sends you back to step 5, not to the user.** Read the failing job before guessing:

```bash
gh run view <run-id> --log-failed | tail -60
```

Fix, push, watch again. Keep looping until every check is green — that's the bar, not "mostly
green".

Report the real table when it settles, and keep CI separate from review: all checks green still
leaves `reviewDecision: REVIEW_REQUIRED`, which only a human can clear.

## 7 — The merge is the human's call

Don't merge the PR yourself. Approval usually isn't yours to give, and merging is an irreversible
outward action — so if the user explicitly asks you to merge, confirm first, then do it. Otherwise
wait for them to say it's merged, or check:

```bash
gh pr view <N> --json state,mergedAt,mergeCommit --jq '{state, mergedAt, merge: .mergeCommit.oid}'
```

## 8 — Clean up everything

`gh pr view` already told you the PR merged, so don't re-verify that — verify the thing the API
can't tell you: that **every commit you pushed** survived the squash. A squash collapses your
branch into one new commit, and nothing in the merge event distinguishes "squashed all four
commits" from "squashed a stale head". If you pushed a fix after the first push, this is the check
that catches it going missing:

```bash
git -C <main-checkout> fetch origin --prune --quiet
git -C <main-checkout> branch -r --contains <merge_sha>       # expect origin/<default-branch>
git -C <main-checkout> diff <merge_sha> origin/<branch>       # expect empty
```

The diff is the real proof: an empty tree difference between the merge commit and your branch's
final tip means the squash captured everything, including the later commits. Reading
`show --stat` and recognising your filenames is weaker — the same files appear whether or not the
second commit's changes are in them.

Ancestry is the wrong tool here for a separate reason: a squash or rebase merge produces a commit
that shares no history with your branch, so `merge-base --is-ancestor` and friends report "not
merged" on a PR that merged perfectly.

Do the diff before the branch is gone. Once you delete the local branch and prune the tracking
ref, the tip you would compare against is unreachable, and all you have left is eyeballing a stat.

Then tear down:

```bash
<project teardown, e.g. make wt-destroy>              # drops per-worktree db/filestore, if any
git -C <main-checkout> worktree remove <worktree-path>
git -C <main-checkout> branch -D <branch>
git -C <main-checkout> ls-remote --heads origin <branch>   # expect empty
```

Two things routinely go wrong:

- **`git branch -d` refuses with "not fully merged"** on a merged PR. Expected, not a warning to
  obey blindly — squashing guarantees the commits aren't ancestors. Use `-D`, but only after the
  content check above passed.
- **Never merge the feature branch into local `main`** to "bring the code over". Local `main` stays
  at its upstream commit; remove the worktree and `git checkout <branch>` in the main checkout if
  the user wants to test there.
- **The remote branch being gone doesn't mean your copy of it is.** Most repos auto-delete the
  head branch on merge, so `ls-remote` comes back empty and the branch looks handled — while
  `refs/remotes/origin/<branch>` still sits in your checkout, because a plain `git fetch` never
  removes refs for branches the remote deleted. `git for-each-ref refs/remotes/origin/<branch>`
  shows it; `--prune` on the fetch is what clears it.
- **A test command that spins up its own stack leaves storage behind.** Isolated-test targets
  often start a throwaway database, then tear it down with a plain `down` that removes containers
  but not volumes — so the project's own teardown truthfully reports "nothing to remove" while a
  volume from your test run survives. List volumes and images by project name, not just
  containers, before you call it clean.

Finish by telling the user what was actually removed and what wasn't, including leftovers you
noticed but didn't touch (stale proxy config or dead databases from earlier worktrees are common).
"Dẹp hết" means the state is verified clean, not that the commands ran.

## Gotcha summary

|Symptom|Cause|Fix|
|---|---|---|
|`Aborting commit due to empty commit message`|wrapper didn't forward stdin to `commit -F -`|message file + `commit -F <file>`|
|PR "has no comments" but the review shows several|`gh pr view` omits inline comments|`gh api repos/{owner}/{repo}/pulls/<N>/comments`|
|Bot review never arrives|that bot's credits are exhausted|check issue comments; stop waiting|
|Reply renders with stray newlines/backticks|shell quoting of `-f body='...'`|`-F body=@file`; patch via `pulls/comments/<reply_id>`|
|Bot still says "changes recommended"|verdict is stale until re-requested|UI action — tell the user|
|`branch -d`: not fully merged, on a merged PR|squash/rebase merge|verify content on the default branch, then `-D`|
|CI green but PR won't merge|`reviewDecision: REVIEW_REQUIRED`|a human must approve|
|PR merged, but a later commit's change isn't on the default branch|squash took a stale head|`git diff <merge_sha> origin/<branch>` — empty — before deleting anything|
|Remote branch deleted on merge, yet `origin/<branch>` still shows locally|`fetch` without `--prune`|`git fetch origin --prune`|
