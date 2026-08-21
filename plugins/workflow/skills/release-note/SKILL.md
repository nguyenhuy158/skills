---
name: release-note
description: Draft the Vietnamese production release note for FarmNet from one or more release tags, letting the user pick which PRs to include. Use when asked for a "release note", "note release", "phát hành", or given release versions like "v2.1.5 v2.1.6".
---

# FarmNet Release Note

Turn one or more `release/vX.Y.Z` tags into the Slack release-note message the team posts.

## Rules

- **Never filter by PR author.** Every PR in range is a candidate. The user decides what ships in the note.
- Output language: **Vietnamese**, business wording. No PR numbers, no file paths, no module names in the final note.
- Group by what the user sees (screen / feature area), not by commit.

## Steps

### 1. Resolve the range

Versions come from what the user typed when invoking (e.g. `v2.1.5 v2.1.6`). If none given, use every release published since the last one the user noted — ask if unclear.

```bash
git fetch origin --tags -q
gh release list --limit 20
```

For each version, pull its body — it already lists the PRs:

```bash
gh release view release/<version> --json body,publishedAt -q '.body'
```

If a body is empty or missing PR links, fall back to:

```bash
git log --oneline release/<prev>..release/<version>
```

### 2. Read every PR

For each PR number in range, read title + body. Batch them in one call:

```bash
for n in <numbers>; do
  echo "########## PR #$n ##########"
  gh pr view $n --json title,author,body -q '"AUTHOR: " + .author.login + "\nTITLE: " + .title + "\n\n" + .body'
done
```

Skip nothing at this stage — infra/CI PRs get dropped in step 3, not here.

### 3. Let the user pick

Show a compact numbered table of every PR: number, author, and a one-line Vietnamese guess at the user-facing impact. Mark the ones you'd drop (CI, chore, refactor, internal tooling — nothing a user would notice) with `(nội bộ)`.

Then use AskUserQuestion — or a plain list if there are many — to confirm which to include. Default selection = everything not marked `(nội bộ)`. If the user says "all" or "cứ vậy đi", go with the default.

### 4. Write the note

Merge the selected PRs into themes. One theme per numbered section, named after the screen or business area. Bug fixes with no shared theme go into a trailing "Sửa lỗi" bullet list.

Format exactly:

```
Dear team,
Production update ngày <DD/MM/YYYY> — deploy release <v1> & <v2>:

1. <Tên màn hình / nghiệp vụ>:
- <Thay đổi người dùng thấy được, 1 dòng>

2. <...>:
- <...>

<N>. Sửa lỗi <mô tả ngắn>.

Thank you.
```

Date = today, not the tag date, unless the user says otherwise.

### 5. Hand it over

Print the note in a fenced block so it can be copied straight into Slack. Do **not** post it anywhere. List separately which PRs you left out — **including every PR you auto-marked `(nội bộ)`**, not only the ones the user deselected — so nothing disappears without the user seeing it.

## Style notes

- Wording that worked before: "tự điền các ô còn trống, không ghi đè ô đã nhập", "bắt buộc khi xác nhận, sửa được sau confirm", "cấp riêng quyền sửa cho từng user".
- Column/field renames: quote both old and new names.
- A permission change always says which role/user it affects.
- If a change only locks or hides something, say what still works — users read a lock as a regression otherwise.
