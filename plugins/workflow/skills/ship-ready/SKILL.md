---
name: ship-ready
description: Finish completed code and publish it as a GitHub pull request end to end, using repository or semantic branch naming, full formatting, lint, test, and build checks, followed by a concise reviewer pass over the published PR diff. Use whenever the user says "code done ship pr", "done ship PR", "ship this", "prep for PR", "get this ready to merge", "push this up", "create PR", "open PR", "tạo PR", or asks Codex to create a branch, commit completed work, push it, and open a PR. Default the PR base to main unless the user specifies another branch.
---

# Ship Ready

Turn completed local work into a reviewable GitHub pull request. Treat the trigger as authorization to create or reuse a branch, commit task-scoped changes, push, and create a ready PR. Do not pause for routine confirmations.

## Workflow

1. Read repository instructions such as `AGENTS.md`, then inspect:
   - current branch and upstream
   - `git status`, staged/unstaged diff, and untracked files
   - remotes and the remote default branch
   - commits and diff against `origin/main` or the user-specified base
   - any existing PR for the current branch
2. Identify only the files belonging to the completed task. Preserve unrelated user changes. Ask before continuing only when ownership is ambiguous or changes overlap.
3. Run the complete repository-native validation sequence before publishing:
   - apply the documented formatter to the task scope
   - run the formatter in check mode when supported
   - run all applicable lint, static analysis, type, XML, security, or preflight checks
   - run the full relevant unit/integration test suite, not only a newly added focused test
   - run the build or packaging check when CI requires it
   Prefer the repo's documented aggregate or CI-equivalent commands. Do not silently skip a category; report it as not applicable or blocked with the reason. Do not bulk-format unrelated files when repository policy or task scope forbids it.
4. If validation modifies files, review those changes and rerun the complete sequence. If a small failure is clearly caused by the task changes, fix it and rerun all affected checks. Stop and ask before any fix that materially expands scope.
5. Prepare the branch:
   - Default the base branch to `main`.
   - Follow an explicit branch convention from `AGENTS.md`, contributing docs, existing branch patterns, or issue policy first.
   - Otherwise use a semantic prefix matching the change: `feat/`, `fix/`, `hotfix/`, `refactor/`, `perf/`, `test/`, `docs/`, `ci/`, `build/`, or `chore/`.
   - Use a short lowercase kebab-case slug, for example `feat/customer-credit-limit` or `fix/invoice-rounding`.
   - Never add agent/vendor prefixes such as `codex/`, `claude/`, `openai/`, or `ai/`.
   - Validate a generated name with `git check-ref-format --branch <branch>` before creating it.
   - If currently on the base branch or detached HEAD, create the semantic branch before committing.
   - If already on a suitable feature branch, keep it.
   - Fetch the base before final comparison. Do not rewrite shared history or force-push without explicit permission.
6. Review the final diff for secrets, generated noise, debug artifacts, and unintended files.
7. Stage only task-related files and create one intentional commit. Follow repository and session commit-message rules. Do not amend an existing user commit unless explicitly requested.
8. Push with upstream tracking using `git push -u origin <branch>`.
9. Create a ready PR to the base branch:
   - Reuse an existing open PR instead of creating a duplicate.
   - Build the title and body from the actual commits, diff, and validation results.
   - Keep the title concise and the body factual.
10. After the PR exists, switch perspective and review the published PR diff as an independent reviewer:
   - focus on correctness, regressions, edge cases, security, data integrity, performance, and missing tests
   - report only actionable, evidence-backed findings; do not invent issues to fill a quota
   - prioritize defects over summaries or praise
   - keep the pass concise, with at most five findings
   - present the review in the final response only; do not post GitHub review comments unless the user explicitly asks
11. Return the PR URL, branch, commit, validation summary, and quick review.

## PR Format

Use a short English title in present tense, at most 70 characters.

Use only useful sections:

```markdown
## What

- Concrete changes

## Why

- Reason or user impact

## Testing

- `command` — passed
- Not run: reason
```

Do not claim a test passed unless its command completed successfully.

## Quick Review Format

Use numbered dash bullets exactly like this:

```markdown
## Quick review

- 1. **[P1] `path/file.py:42`** — Concrete defect, impact, and suggested fix.
- 2. **[P2] `path/test_file.py:18`** — Missing case and why it matters.
```

Use `P0` for critical, `P1` for high, `P2` for normal, and `P3` for low priority. If there are no actionable findings, do not fabricate one; write:

```markdown
- 1. Không phát hiện vấn đề actionable trong PR diff; nêu ngắn gọn residual risk hoặc phần chưa được runtime-test nếu có.
```

## Branch Naming

Choose the prefix from the primary purpose of the diff, not from the tool that created it:

| Change | Branch example |
|---|---|
| Feature | `feat/add-credit-warning` |
| Bug fix | `fix/payment-rounding` |
| Urgent production fix | `hotfix/token-validation` |
| Refactor | `refactor/customer-sync` |
| Performance | `perf/batch-customer-query` |
| Tests only | `test/payment-webhook` |
| Documentation | `docs/deployment-guide` |
| CI/build/dependencies | `ci/parallel-tests`, `build/update-odoo-image` |
| Maintenance | `chore/cleanup-migrations` |

Use the repository's own convention instead when one exists.

## Safety Boundaries

Stop before publishing when:

- task ownership cannot be separated from unrelated local changes
- the diff contains likely secrets or credentials
- validation fails and the necessary fix changes the agreed scope
- resolving a conflict requires business judgment
- GitHub authentication or permissions are unavailable

Never use destructive reset, discard user changes, merge the PR, or force-push unless the user explicitly asks.

## Completion

A successful `code done ship pr` run ends only when the branch is pushed, a ready PR exists against `main` or the requested base, and the final response includes the quick reviewer pass. Report blockers with the exact failed step and preserve all completed local work.
