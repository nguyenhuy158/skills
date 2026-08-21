---
name: release-note
description: Draft the Vietnamese production release note for FarmNet from one release tag or a range, letting the user pick which changes to include. Use when asked for a "release note", "note release", "changelog", or given release versions like "v2.1.5 v2.1.6".
---

# FarmNet Release Note

Turn one or more `release/vX.Y.Z` tags into the Slack release-note message the team posts.

## Rules

- **Never filter by PR author.** Every PR in range is a candidate. The user decides what ships in the note.
- Output language: **Vietnamese**, business wording. No PR numbers, no file paths, no module names in the final note.
- **Name screens by their exact UI label** the user sees in the app — `Sale Orders`, `Settlement`, `Cashflow`, `Contacts`. Never a module name (`farmnet_sale_order`), never an invented Vietnamese screen name. Unsure? Look it up in the PR body, or in the view/menu file (`<menuitem name="…">`, `string="…"`) — don't guess. A wrong screen name is the #1 thing users complain about.

## Steps

### 1. Resolve the range

Versions come from what the user typed when invoking. No version given → **stop and ask**; don't assume a range.

```bash
git fetch origin --tags -q
```

- **One version** — `gh release view release/vX.Y.Z --json body,publishedAt -q '.body'`
- **A range** — one command, no per-release loop:

```bash
git log --format='%s' release/<from>..release/<to> | grep -oE '#[0-9]+' | sort -u
```

### 2. Read every PR in full

```bash
for n in <numbers>; do
  echo "########## PR #$n ##########"
  gh pr view $n --json title,author,body -q '"AUTHOR: " + .author.login + "\nTITLE: " + .title + "\n\n" + .body'
done
```

Read the whole **What / Change** section, not the title. **One PR often carries several user-visible changes** — pull each one out of the sub-bullets. Skip nothing here; dropping happens in step 3.

### 3. Decide what's user-visible

Test: **does the end-user SEE something different in the app** — a number, a document, a record, a column, a button? Not "did someone do work".

- **Keep** one-off data corrections when the result is visible: one document gets a missing field filled, a batch of debt figures corrected. Name the exact document or screen.
- **Drop** only when the user sees nothing at all: infra/deploy/CI, refactors with no behavior change, log noise, internal tooling.

### 4. Let the user pick

Present a compact table (PR, author, one-line Vietnamese impact), marking drops as `(nội bộ)`. Then confirm with **`AskUserQuestion`, always `multiSelect: true`** — one option per user-visible change, label = the English screen name, description = the one-line business summary. Max 4 options per question, so **split into several multiSelect questions inside the same call**. Pre-suggest everything user-visible; the user unticks. Never make the user type numbers.

"all" / "cứ vậy đi" → take the default.

### 5. Write the note

Merge the selected changes into themes, one numbered section per screen or business area. Bug fixes with no shared theme go into a trailing "Sửa lỗi" bullet list. State **benefit + what the user does**, not the mechanism.

```
Dear team,
Production update ngày <DD/MM/YYYY> — deploy release <v1> & <v2>:

1. <Tên màn hình / nghiệp vụ>:
- <Thay đổi người dùng thấy được, 1 dòng>

2. <...>:
- <...>

<N>. Sửa lỗi <mô tả ngắn>.

Nhờ team lưu ý <màn hình / thao tác quan trọng>.

Thank you.
```

Date = today, not the tag date, unless the user says otherwise.

### 6. Hand it over and check

Print the note in a fenced block, ready to copy into Slack. Do **not** post it anywhere.

Then, outside the note, list which PRs you left out — **including every one you auto-marked `(nội bộ)`**, not only what the user deselected — so nothing disappears unseen.

Review once before handing over:
- Only the selected changes are in the note; nothing silently re-added.
- Every user-visible action from the selected PRs has a line — including the second and third change hidden inside one PR.
- No visible data-correction dropped just for being "a data fix".
- Every screen named with its real UI label; no module names, no invented names.

## Style notes

- Wording that worked before: "tự điền các ô còn trống, không ghi đè ô đã nhập", "bắt buộc khi xác nhận, sửa được sau confirm", "cấp riêng quyền sửa cho từng user".
- Column/field renames: quote both old and new names.
- A permission change always says which role/user it affects.
- If a change only locks or hides something, say what still works — users read a lock as a regression otherwise.
