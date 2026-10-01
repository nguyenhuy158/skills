---
name: plane
description: Chuẩn hóa mọi thao tác với Plane cho DichvuFarmNet (DICHVUFARM) và FarmLink (FARMLINK) — tạo task bắt buộc có timeline start/due tính theo ngày làm việc (bỏ T7, CN và ngày lễ VN), title `[Domain] Mô tả`, label, module (chưa rõ thì Uncategorized), priority, assignee, description dạng checklist; ghi mọi tiến độ bằng comment; gắn link PR; gắn relation qua browser-use; chuyển state Todo → In Progress → Done. Dùng skill này bất cứ khi nào người dùng nói "tạo task", "tạo plane task", "lưu vào plane", "note lại vào plane", "cập nhật task", "gắn relation", "chuyển done", nhắc tới mã DICHVUFARM-/FARMLINK-, hoặc vừa xong một PR/hotfix cần ghi nhận trên Plane — kể cả khi không gọi tên skill.
---

# Plane task flow

One standard for every Plane work item in DichvuFarmNet (`DICHVUFARM`) and FarmLink (`FARMLINK`).
For any other Plane project, ask before applying it.

## Lookups

Resolve every UUID at runtime with the plane MCP and reuse it for the session; never hard-code ids.

- Project: `project list` → match `identifier`. FarmNet repo → `DICHVUFARM`, Farmlink repo → `FARMLINK`; otherwise ask.
- `state list`, `label list`, `module list` per project; `member me` for the current user.
- Web URL of a task: `<PLANE_BASE_URL>/<slug>/browse/<IDENTIFIER-N>/` — host from the plane MCP config
  (`rg -o '"PLANE_BASE_URL": *"[^"]*' ~/.claude.json`), slug from `workspace retrieve`.

## Required fields

A task is never created with any of these missing.

| Field | Rule |
|---|---|
| Title | `[CODE] Mô tả` — CODE is the exactly-4-letter code of the primary label (table below), uppercase A–Z only, e.g. `[SALE] Luồng phê duyệt ngoại lệ…`. Short, no ids or dates |
| Language | By reader: task for BA/Ops (business flow, OPS label) → Vietnamese; dev-only (refactor, CI, infra) → English. Comments follow the task's language |
| Labels | ≥1 domain label; the first one gives the title code. Nothing fits → ask to create a label (and its code), never invent a prefix |
| Module | Best-fitting module; unclear → `Uncategorized` (reclassify later) |
| Priority | Never `none`. urgent: prod broken or ops blocked now · high: wrong money/data or a dated commitment · medium: normal · low: nice-to-have |
| Assignee | `member me` unless the user names someone (`member list_workspace display_name=…`) |
| Start + Due | Working days only (no Sat/Sun, no VN public holiday). The timeline lives here only, never in the description |
| State | `Todo` on creation; `In Progress` if work starts right now |
| Description | One context line + checklist (templates below) |

### Title codes

Labels keep their full names; only the title prefix is short: exactly 4 uppercase letters A–Z, no digits, no lowercase.

| Label | Code | Label | Code | Label | Code |
|---|---|---|---|---|---|
| SO | SALE | DISBURSEMENT | DISB | DEBT | DEBT |
| PR (payment request) | PREQ | REPAYMENT | RPMT | INVOICE | INVC |
| APPENDIX | APDX | TREASURY | TRSY | FORM | FORM |
| SYNC | SYNC | DATA | DATA | PLANNING | PLAN |
| OEM | OEMP | OPS | OPER | INFRA | INFR |
| OBSERVABILITY | OBSV | BANK | BANK | CREDIT | CRED |
| CUSTOMER | CUST | | | | |

## Create

1. Collect what, who asked, project, size, related tasks/PRs.
2. Timeline (`scripts/workdays.py`; start counts as day 1):
   - User gave dates → `workdays.py check START DUE`; settle non-working days with the user.
   - No dates → `workdays.py plan SIZE` (add `--start` if work cannot start today). SIZE: `hotfix` (data fix, 1 day) ·
     `bug` (2) · `small` feature (3) · `large` feature (5). Over 5 working days → a parent task plus sub-items
     (`parent=`) of at most 5 days each.
   - Workload: list the assignee's open items in both projects (`workitem list` with `fields`, filter client-side on
     assignee, state Todo/In Progress and overlapping dates). Three or more overlapping → list them with priorities
     and propose starting after the earliest one ends, or re-prioritising.
   - Suggested (not user-given) timeline → confirm with the `ask` tool before creating: title, labels, module,
     priority, assignee, start/due with working-day count, skipped days, workload conflicts, checklist.
3. `workitem create` with name, description_html, state, priority, assignees, labels, start_date, target_date (and `parent`).
4. `module manage_workitems module_id=… add_ids=<new id>` — module is not a create field.
5. Related tasks → `references/relations.md`.
6. Reply in the output format below, then list every field that was defaulted.

## Output

Every reply that creates, updates or reports on tasks ends with one block per task, in this exact shape:

```text
[DICHVUFARM-125](<PLANE_BASE_URL>/<slug>/browse/DICHVUFARM-125/) — [DEBT] Title of the task
Mô tả: one short line — what the task is about / what changed now
Timeline: 2026-10-05 → 2026-10-07 · còn 3 ngày làm việc
```

- Link text is the identifier (`DICHVUFARM-125`, `FARMLINK-12`), the URL is the task's web URL, then the title.
- Days left: `workdays.py left DUE` (working days from today to due, today included). Overdue → `quá hạn N ngày làm việc`;
  task already Done → `đã xong`.
- Several tasks → one block each, same order as handled.

## Description: checklist only

Plane renders `<ul data-type="taskList">` items as checkboxes. Results, numbers, causes, decisions go to comments.

Feature:

```html
<p><b>Bối cảnh:</b> one line — what, who asked, source link</p>
<ul data-type="taskList">
  <li data-type="taskItem" data-checked="false"><p>acceptance 1</p></li>
  <li data-type="taskItem" data-checked="false"><p>acceptance 2</p></li>
  <li data-type="taskItem" data-checked="false"><p>PR merged</p></li>
  <li data-type="taskItem" data-checked="false"><p>Released lên prod</p></li>
</ul>
```

Bug / hotfix:

```html
<p><b>Hiện tượng:</b> one line — what is wrong, where, who reported</p>
<ul data-type="taskList">
  <li data-type="taskItem" data-checked="false"><p>Reproduce</p></li>
  <li data-type="taskItem" data-checked="false"><p>Root cause</p></li>
  <li data-type="taskItem" data-checked="false"><p>Fix (PR hoặc hotfix script)</p></li>
  <li data-type="taskItem" data-checked="false"><p>Verify local</p></li>
  <li data-type="taskItem" data-checked="false"><p>Deploy / chạy trên prod</p></li>
  <li data-type="taskItem" data-checked="false"><p>Verify prod (UI + DB)</p></li>
</ul>
```

English task: `Context:` / `Symptom:` and the same items in English.

## Formatting for the Plane editor (description and comments)

Plane renders HTML in a proportional font and narrow table columns. Two layouts break (seen on DICHVUFARM-108):

| Breaks | Why | Do instead |
|---|---|---|
| ASCII art: box tables `┌─┬─┐ │ │`, arrow trees `├──►`, aligned columns made with spaces | In `<p>…<br>` the spaces collapse and characters have different widths, so boxes and arrows go out of line. Even inside `<pre><code>` Plane drops leading spaces, so tree branches lose their indentation | Real `<table>` for tabular data; `<ol>`/`<ul>` for steps and trees; a flow on one line `A → B → C`. A real diagram → attach an image (Attach), never draw it with characters |
| Two-column "key │ value" `<table>` with long `<code>` values | Plane gives each column ~150px, so long identifiers wrap mid-word (`vendor_transfe` / `r`) | Key/value pairs as a list: `<li><b>XML ID:</b> <code>farmnet_debt.agreement_vendor_transfer</code></li>`. Use a table only when every cell is short and there are 3+ columns |

Also: keep one topic per comment (a whole spec in one comment is unreadable — split by section); `<code>` only for
identifiers, not for sentences or long flows.

## While working

- Tick a box: read `description_html`, flip only that item to `data-checked="true"`, write the whole body back
  (an update replaces it). Never add prose to the description.
- Everything else is a comment (`workitem_comment create`), one event per comment, led by a bold tag:
  `<b>Root cause:</b>`, `<b>PR:</b>`, `<b>Hotfix:</b>`, `<b>Verify:</b>`, `<b>Timeline:</b>`, `<b>Decision:</b>`.
- Work starts → `In Progress`. Started on another day than planned → move start (and due if it shifts) with
  `workdays.py`, plus a `Timeline:` comment.
- Due date at risk → propose a new due with `workdays.py`, update once the user agrees, comment the reason.
  An open task never sits past its due date.

## PR

- Opened: `workitem_link create url=<PR url> title="PR #<n>: <title>"`; the PR body names `DICHVUFARM-<n>` /
  `FARMLINK-<n>`; comment `<b>PR:</b> #<n> opened`.
- Merged: tick "PR merged", comment, state stays `In Progress`.
- Shipped: the release tag containing the PR is on prod → `Done`, tick "Released", comment
  `<b>Release:</b> release/vX.Y.Z`. Never `Done` on merge.

## Hotfix / data fix without a PR

`Done` once verified on prod (UI + DB). Comment the script paths, what ran, before → after, and the check.

## States

| State | Meaning |
|---|---|
| Backlog | Parked, no commitment — re-plan the timeline when picked up |
| Todo | Committed, timeline set, not started |
| In Progress | Being worked on, or merged and waiting for a release |
| Done | On prod: release shipped, or hotfix verified |
| Cancelled | Dropped — comment why |

## Task buttons: MCP or browser-use

The four buttons under a task's description, and which tool does each:

| Button | Tool | How |
|---|---|---|
| Add sub-work item | MCP | `workitem create … parent=<parent id>` (or `update parent=` on an existing item) |
| Add relation | **browser-use** | `references/relations.md` — the MCP has no `Relates to` / `Duplicate of` (`workitem_relation` returns 404) |
| Add link | MCP | `workitem_link create url=… title=…` (tested) |
| Attach | MCP if the file has a public URL | `workitem_attachment upload_from_url url=… name=…` — Plane fetches it server-side, so no localhost, no private IP, no login |
| Attach a local file | **browser-use** | Upload through the Attach button (not exercised yet — verify it appears with `workitem_attachment list`) |

Reading attachments (`workitem_attachment list / read / download_url`) is MCP.

## Holidays

`references/vn-holidays.txt` lists weekday public holidays per year. `workdays.py` warns when a year in the timeline
has no entry, and the file marks dates that were still proposals. On a warning, or once the Ministry of Home
Affairs (Bộ Nội vụ) publishes the next year's schedule, web-search the official schedule, update the file and commit it
in the skills repo.

## Plane API gotchas (self-hosted community edition)

- `workitem list` rejects PQL and structured filters: pass `project_id` + `fields`, filter client-side, page with `cursor`.
- `retrieve_by_identifier` accepts `DICHVUFARM-123`.
- `workitem_relation`, `workitem_type` and `release` return 404.
- Drafts (`is_draft`) cannot be read back and still consume a sequence number — never create drafts.
- Web UI menus need real clicks (`click_at_xy`); JS `.click()` does not open them.
