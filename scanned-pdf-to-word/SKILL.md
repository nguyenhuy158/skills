---
name: scanned-pdf-to-word
description: Convert scanned PDFs (image-only, no usable text layer) into clean, editable Word (.docx) documents by visually transcribing each page instead of relying on OCR. Use this whenever a user asks to convert a PDF to Word/docx and the PDF turns out to be a scan — telltale signs are pdftotext returning garbage or nothing, photographed/faxed documents, stamps and signatures, or rotated pages. Especially strong for documents with tables and for Vietnamese or other diacritic-heavy languages where tesseract mangles characters. Also trigger on phrases like "chuyển PDF sang Word", "PDF to docx", "make this scan editable", or "extract this scanned table".
---

# Scanned PDF → Word

Turn a scanned PDF into a faithful, editable .docx. The core idea: **you (the model) are a better OCR engine than tesseract** — especially for tables, diacritics (Vietnamese, etc.), and messy scans. So instead of piping through OCR tools, render pages to images, read them with your own vision, and rebuild the document with docx-js.

## Why not just OCR?

`pdftotext` on a scan returns garbage or nothing. `tesseract` mangles diacritics, merges table columns, and hallucinates on stamps/handwriting. Visual transcription by the model is slower per page but dramatically more accurate, and you can flag uncertain readings (handwritten numbers, smudges) for the user instead of silently guessing.

## Workflow

### 1. Triage the PDF

```bash
pdfinfo input.pdf            # page count, size, encryption
pdftotext input.pdf - | head -50
```

If `pdftotext` gives clean text, the PDF is NOT a scan — extract directly (or use the regular pdf/docx skills) and skip the image pipeline. If it gives garbage fragments or nothing, proceed below.

### 2. Render pages to images

```bash
pdftoppm -png -r 120 input.pdf page
```

120 dpi is usually enough to read body text while keeping images small; bump to 150–200 dpi if small print is illegible when you view it.

Work in your own scratch directory (e.g. `~/work/` or the outputs dir) — avoid shared `/tmp`, which may contain files from other processes that collide with yours.

### 3. Fix orientation per page — don't assume

Scans are often rotated 90°, and **duplex scans commonly alternate direction page by page** (page 1 needs ROTATE_90, page 2 needs ROTATE_270, ...). Never batch-rotate blindly. For each page: rotate, then actually Read the image to confirm it's upright before transcribing. If it's upside down, you rotated the wrong way — apply the other rotation.

```python
from PIL import Image
Image.open('page-1.png').transpose(Image.ROTATE_90).save('up-1.png')   # or ROTATE_270
```

### 4. Transcribe visually

Read each upright page image and transcribe the content precisely:

- Copy structure: headings, table columns, merged cells, footnotes, notes in italics.
- Keep original language and diacritics exactly (Hường ≠ Huong ≠ Hưởng — one wrong mark changes the name).
- Double-check high-stakes fields character by character: ID numbers, dates, amounts, reference numbers.
- Handwritten bits (document numbers, dates filled by pen) are often ambiguous — transcribe your best reading and **tell the user to verify them** in your final message.
- If a field is blank or marked "no info", preserve that ("Chưa có thông tin"), don't invent data.

### 5. Build the .docx with docx-js

Follow the docx skill if available (read its SKILL.md). Key points that matter here:

- `docx` (npm) may need `npm install docx` in your build dir.
- Match the source layout: wide tables → `orientation: PageOrientation.LANDSCAPE`.
- Tables need `columnWidths` on the table AND `width` on every cell, both `WidthType.DXA`; column widths must sum to table width.
- Header-row shading: `ShadingType.CLEAR` (never SOLID — renders black).
- Official Vietnamese documents conventionally use Times New Roman.
- Put the whole build in ONE script with the transcribed rows as a literal array — easy to re-run after corrections.

A ready-made template is in `scripts/build_docx_template.js`; copy it and replace the header/rows/columns.

### 6. Verify by rendering back

Never ship unverified. Convert the .docx to PDF, render to images, and Read them:

```bash
soffice --headless --convert-to pdf output.docx   # or the docx skill's soffice.py wrapper
pdftoppm -jpeg -r 80 output.pdf chk
```

Check: row count matches the source, no clipped columns, diacritics render, first and last pages look right. Then clean up intermediate images from the user's outputs folder so only the deliverable remains.

### 7. Deliver

Present the .docx. In your summary, state the page/row counts and explicitly list anything the user should double-check (handwritten fields, illegible cells).

## Common pitfalls

- **Trusting one rotation for all pages** — duplex scans alternate; verify each page visually.
- **Silently guessing illegible text** — flag it instead.
- **Skipping the render-back check** — table width mistakes and font issues are invisible until you look at the rendered output.
- **PII carelessness** — scans of official documents often contain names, ID numbers, addresses. Don't leave page images lying around in the user's folder after finishing.
