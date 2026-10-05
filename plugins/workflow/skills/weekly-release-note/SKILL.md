---
name: weekly-release-note
description: Build the weekly FN/FL/Bank service release-note recap from Huy's own Slack messages, in two versions (detailed + one-line-per-item). Use when asked for a "release note tuần", "weekly release note", "tổng hợp release tuần", or "recap release from last Monday".
---

# Weekly Release Note (from Slack)

Roll up a week of production updates already posted in Slack into one message for the lead, in **two versions**: detailed and high-level.

Different from `/workflow:release-note`: that one drafts a single release from git tags/PRs. This one **summarises what was already announced** in Slack over a week.

## Sources (Slack)

| What | Where |
|---|---|
| Me | `U091S43SN30` (Nguyen Tran Quang Huy) |
| FN / FL release threads | `#project-odoo-dev` `C0AMJ3144HG` — parent `[FN - Release DD/MM/YY]`, `[FL - Release DD/MM/YY]`; reply starts with `Production update ngày …` |
| Bank service / Virtual Accounts | `#fn-fl-dev` `C0B1HAGKX9D` — thread `[FN - Virtual Accounts]`, latest `Updated:` reply (MB / VPB / VTB status) |
| Work still on dev | `#project-odoo-dev` threads like `[FN - OEM]`, `[FN - Cấn trừ NCC/…]` with dev1/dev2 links |

## Steps

### 1. Resolve the week

Default range = **last Monday → now**. If today is Monday, "thứ 2 vừa rồi" means the Monday 7 days ago. User gives another range → use it. Unsure → ask once with `AskUserQuestion`.

### 2. Pull the releases

Slack search (one call, full text):

- keywords: `"Production update"`
- filters: `from:<@U091S43SN30> in:<#C0AMJ3144HG> after:<day-before-start>`
- `sort: timestamp`, `response_format: detailed`, `include_context: false`

Each hit = one release (version range + numbered items). Note which are FN (`v2.7.x`, `v2.8.x`…) vs FL (`v2.5.x`…) from the thread parent.

### 3. Pull Bank service + dev work

- Search `from:<@U091S43SN30> in:<#C0B1HAGKX9D> after:<…>` → take the **newest** `Updated:` status for each bank.
- Search `in:<#C0AMJ3144HG> after:<…>` for spec / preview threads (`OEM`, `dev1`, `dev2`, `preview`). These go under **"Đang test trên dev"** unless a message says it went to prod.

Use `response_format: concise` + pagination for broad sweeps; switch to `detailed` only for messages you need verbatim.

### 4. Merge

- Group by **screen / module UI label** (Agreements, Disbursement, Bank Transactions, Repayment Monitoring…), not by release date.
- Same screen across releases → one numbered item.
- Header shows the full version span: `FN (v<first> → v<last>):`.
- Speed items → one "Tốc độ" line. Leftover small fixes → one "Sửa lỗi" line.
- Never invent a go-live date, owner, or status that isn't in Slack.

### 5. Write two versions

Match this format exactly (plain Slack text, Vietnamese):

```
Dạ em gửi anh release note tuần DD/MM – DD/MM
FN (vX → vY):
1. <Màn hình>: <thay đổi>; <thay đổi>.
2. ...
FL (vX → vY):
1. <Màn hình>: <thay đổi>.

Bank service:
• <trạng thái>
• E2E: MB ✅, VPB ✅, VTB ⏳

Đang test trên dev:
• FN – <tính năng>: <tóm tắt>.
```

- **Detailed**: keep every user-visible change from the release posts, merged per screen.
- **High-level**: same sections and numbering, **one short line per item** (≤ ~12 words).

### 6. Hand over

- Print both versions in fenced code blocks, ready to copy. **Do not post or draft in Slack** unless the user asks.
- After the blocks, a short table of **points to check**: anything placed under "dev" by assumption, missing dates, pending banks.
- Add a `Sources:` line with permalinks to each release thread used.
- Reply bilingual (English first, then Vietnamese) per user preference.

## Checks before handing over

- Every `Production update` in range is reflected; none double-counted.
- FN vs FL not mixed up.
- Bank statuses = the **latest** update, not an older one.
- Dev-only work is not presented as released.
