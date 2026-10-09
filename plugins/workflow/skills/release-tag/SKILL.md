---
name: release-tag
description: Cut a new FarmNet production release tag on origin/main and watch the Release workflow build it. Use when asked to "tạo release tag", "create new release tag", "cut a release", "tag main rồi watch CI", or "release tag mới".
---

# FarmNet Release Tag

Push a new `release/vX.Y.Z` tag at the tip of `origin/main`, then watch the **Release** workflow
until it publishes the GitHub Release.

## Rules

- **Never pick the next version with `git tag --sort=-v:refname`.** That sort puts the dead
  date-based series (`v2026.07.27`) on top and you will invent a tag nobody uses. The live series
  is `release/vX.Y.Z`; find it by **creation date**.
- Tag the **tip of `origin/main`**, never a local `main` — fetch first.
- Bump the **patch** only. Minor/major bumps are a human decision: ask.
- Both `v*` and `release/*` fire the Release workflow, so a wrong-shaped tag still builds and still
  cuts a Release. It will not error — you have to notice yourself.
- Annotated vs lightweight doesn't matter; existing tags are lightweight.

## Steps

### 1. Resolve the next version

```bash
git fetch origin --tags -q
git for-each-ref --sort=-creatordate --format='%(creatordate:short) %(refname:short)' refs/tags | head -5
git log --oneline -1 origin/main
```

Take the newest `release/vX.Y.Z` row, bump the last number. `release/v2.7.42` → `release/v2.7.43`.

Report the delta before tagging, so the user can stop you if main has something unwanted:

```bash
git log --oneline release/<prev>..origin/main
```

Zero commits in the range → nothing to release; stop and say so.

### 2. Tag and push

```bash
git tag release/vX.Y.Z <origin/main sha>
git push origin release/vX.Y.Z
```

### 3. Watch the build

The push triggers the **Release** workflow. Give it a few seconds to register, then watch it:

```bash
sleep 8 && gh run list --limit 3
gh run watch <run-id> --exit-status
```

Two jobs must go green: **Build & Push Image** (ECR + ACR) and **Create GitHub Release**. Typical
runtime ~2.5 min. The `Node.js 20 is deprecated` and `ubuntu-latest will migrate` annotations are
infra warnings on every run — not failures.

### 4. Confirm

```bash
gh release list --limit 3
gh release view release/vX.Y.Z --json url,publishedAt -q '.url + "  " + .publishedAt'
```

The new tag must show as **Latest**. Report: tag name, commit + its subject, commit count since the
previous tag, run conclusion, release publish time, and — always — the **release URL** from the
command above, as a clickable link. The user's next step is opening it; never make them go find it.

## Fixing a wrong tag

A pushed tag already built an image and published a Release, so cleanup is three deletes:

```bash
gh release delete <bad-tag> --yes --cleanup-tag   # release + remote tag
git tag -d <bad-tag>                              # local
git ls-remote --tags origin | grep <bad-tag>      # must return nothing
```

Then redo steps 1–4 with the correct name. The stale image in ECR/ACR is harmless; leave it.

## After the release

The release note is a separate job — hand off to the `release-note` skill with the tag you just cut.
