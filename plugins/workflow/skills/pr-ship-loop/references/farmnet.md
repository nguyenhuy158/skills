# FarmNet — Techcoop-vn/farmnet

Repo: `/Users/huyntq/Documents/techcoop/farmnet-github`. Odoo 16, ~30 custom modules in `src/`,
running in Docker. `AGENTS.md` at the repo root is the authority on coding rules — style, security
groups, XML conventions, module layout. This file only carries what changes the mechanics of the
ship loop.

## Ground rules that override the generic steps

Prefix every CLI call with `rtk` (`rtk git`, `rtk proxy make`, `rtk proxy gh`) — a hook rewrites it
to cut token cost.

Never use `sed`, `mkdir`, `touch`, `rm`, `cp` or `echo >file` for file work; the Write/Edit tools
exist for that. This is a hard project rule, not a preference.

Search with `rg` but without `--glob`/`--type`: the hook rewrites `rg` to `grep`, which rejects
those flags. Never search from the repo root either — `backup/` holds a ~460MB dump that times the
search out. `git grep` avoids both problems.

## Step 1 — Worktree

```bash
rtk proxy make worktree BRANCH=feature/<kebab-case-description>
```

Types are `feature/`, `fix/`, `chore/`, `ci/`, no issue-number prefix, always from `main`. The
Makefile resolves the path from the main checkout, so it always lands at
`<repo>/.claude/worktrees/<slug>` (slug = last path segment of the branch). Never put a worktree
anywhere else — not beside the repo, not under a tool's home directory.

Each worktree gets its own Odoo container and a cloned database on the shared `fnp` Postgres
container. Only boot that stack when you actually need to run Odoo:

```bash
rtk proxy make wt-db-clone   # needs the shared fnp postgres container up
rtk proxy make wt-up
rtk proxy make wt-proxy      # mandatory once a browser is involved
```

`wt-proxy` is not optional for UI work: every worktree otherwise shares the `localhost` origin and
their session cookies collide. Use the printed `http://<container>.localhost`, never
`localhost:<port>`.

Then `make upgrade MODULE=<module>` for changed modules, and `make test-fresh MODULE=<module>` for
tests — never bare `make test`.

## Step 2 — The gate

```bash
rtk proxy ruff check src/
rtk proxy ruff format --check src/
rtk proxy xmllint --noout src/<module>/.../<template>.xml
```

The xmllint pass matters for OWL templates and views: a malformed template fails at runtime, not at
import, so nothing else catches it locally. CI runs the same three.

There is no JS/OWL test harness in this repo. When your change is OWL components, say that plainly
rather than implying the components are covered.

## Step 3 — Commit and PR

`rtk git commit -F -` with a heredoc **fails silently** — the rtk proxy doesn't forward stdin, so
git sees an empty message and aborts. Write the message to a file, then `rtk git commit -F <file>`.

Check `rtk git status --short` before `add -A`: two Claude sessions on the same worktree have
already destroyed real code here, when one session's `add -A` swallowed the other's uncommitted
work (commit 4ed30cd0, PR 649).

Commit messages end with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

PR titles follow Conventional Commits — `<type>: <description>`, type one of `feat`, `feature`,
`fix`, `chore`, `ci`, `docs`, `refactor`, `test`, `build`, `perf`, `style`, `revert`. CI validates
the title. PR bodies end with:

```
🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

## Step 4 — The review bots

`copilot-pull-request-reviewer` submits a real review with inline comments and a verdict, roughly
five minutes after the PR opens. `chatgpt-codex-connector` usually posts an issue comment saying its
usage limits are exhausted instead of reviewing — don't wait on it.

## Step 6 — CI checks

Preflight · Lint & Format (ruff) · Lint Dockerfile (hadolint) · Lint XML (xmllint) · Test (~3 min).

## Step 8 — Teardown

```bash
rtk proxy make wt-destroy                                   # from inside the worktree
rtk proxy git -C <main-repo> worktree remove <worktree-path>
rtk proxy git -C <main-repo> branch -D <branch>
```

`make test-fresh` runs on `compose.local.yml`, a different project from the `compose.wt.yml` stack
`wt-destroy` tears down. Its final `down --remove-orphans` drops the containers but has no `-v`,
so `<project>_postgresql-data` survives and `wt-destroy` still reports the worktree data removed —
it looked at the wt stack, which never existed. After tearing down, check
`docker volume ls -q | grep <slug>` and remove what your own test run left; leave volumes from
other worktrees alone.

`wt-destroy` fails with `No such container: fnp-db-1` when the shared postgres stack is down. If
you never ran `wt-db-clone` there was no database or filestore to drop — verify that instead of
assuming, with `docker ps -a --filter name=<project>`, `docker volume ls`, and a look at
`.claude/caddy/sites/`; then tell the user the DB step was a no-op and why. A database from an
earlier session does survive: bring `fnp` up and `dropdb` it.

Don't use `rtk git log` to check merge history — the wrapper silently omits merge commits. Use
`git cat-file -p HEAD`, `git reflog`, or `git branch -r --contains <sha>`.

Stale `.caddy` files in `.claude/caddy/sites/` accumulate from worktrees that were removed without
`wt-unproxy`. Mention them; don't delete them unasked.

## After the merge

A Plane task moves to **In Progress** when its PR merges, and only to **Done** once the PR ships in
a released release tag — not on merge.
