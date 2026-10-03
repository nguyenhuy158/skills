---
name: share-artifact
description: Publish an HTML mockup, single-page app, SVG, or preview artifact to share.huyab.click and get an instant live public URL. Use when the user asks to "share preview", "upload mockup", "publish html", "share this page", "give me a link to view this", or "push to share".
---

# Share Artifact Skill

Uploads an HTML file, mockup, SVG, or prototype to `https://share.huyab.click/api/upload` to provide an instant, public, noindex preview link.

### Automatic Versioning (Stable URL)
When you re-upload a file with the same filename or `slug`, the platform **automatically increments the version (v2, v3...)** and keeps the **exact same public URL**. Old links remain valid and always show the latest changes!

## Prerequisites

The user must have signed in to `https://share.huyab.click` via SSO and set their **Master Password**.
The credentials can be supplied via environment variables or parameters:
- `SHARE_EMAIL`: Account email address
- `SHARE_PASSWORD`: Account master password
- Target API: `https://share.huyab.click/api/upload`

## How to execute

When an HTML mockup or artifact file is generated (e.g. `index.html`, `dist/index.html`, `chart.svg`), execute a curl command via bash:

```bash
curl -s -X POST "https://share.huyab.click/api/upload" \
  -F "email=${SHARE_EMAIL}" \
  -F "password=${SHARE_PASSWORD}" \
  -F "file=@<path-to-file>" \
  -F "title=<optional-title>" \
  -F "slug=<optional-stable-slug>"

Alternatively, if uploading raw string content directly without a file:

```bash
curl -s -X POST "https://share.huyab.click/api/upload" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "'"${SHARE_EMAIL}"'",
    "password": "'"${SHARE_PASSWORD}"'",
    "content": "<html>...</html>",
    "filename": "preview.html",
    "title": "Preview Title"
  }'
```

## Response Schema

The server returns JSON:

```json
{
  "success": true,
  "id": "e4f8b2c1-9a7d-4b8a-9f5e-123456789abc",
  "url": "https://share.huyab.click/artifact/e4f8b2c1-9a7d-4b8a-9f5e-123456789abc",
  "rawUrl": "https://share.huyab.click/artifact/e4f8b2c1-9a7d-4b8a-9f5e-123456789abc/raw",
  "version": 2,
  "isNew": false,
  "title": "Preview Title",
  "filename": "index.html",
  "contentType": "text/html; charset=utf-8",
  "size": 15420,
  "updatedAt": "2026-09-08T09:00:00.000Z"
}

## Presentation to User

Always format the final link clearly:
- Provide the clickable link: `https://share.huyab.click/artifact/<uuid>`
- Note that it is live, rendered with standard browser scripts enabled, and tagged `noindex` for privacy.
