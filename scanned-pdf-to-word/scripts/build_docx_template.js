// Template: rebuild a scanned tabular document as .docx
// Copy this file, replace TITLE/SUBTITLE/HEADERS/COL_WIDTHS/ROWS/OUTPUT, then:
//   npm install docx && node build.js
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  WidthType, AlignmentType, PageOrientation, ShadingType, VerticalAlign } = require('docx');
const fs = require('fs');

// ====== EDIT ME ======
const OUTPUT = 'output.docx';
const FONT = 'Times New Roman';          // convention for official VN documents
const LANDSCAPE = true;                  // wide tables -> landscape A4
const TITLE = 'PHỤ LỤC';
const SUBTITLE = 'Danh sách ...';
const NOTE_BELOW = '';                   // e.g. italic "Ghi chú: ..." under the table; '' to skip
const HEADERS = ['STT', 'Họ và tên', 'Ngày sinh'];
// Column widths in DXA (1440 = 1 inch). Must sum to usable width:
// A4 landscape w/ 0.5" margins ≈ 15326; portrait ≈ 10466.
const COL_WIDTHS = [700, 8000, 6626];
const ROWS = [
  ['1', 'Nguyễn Văn A', '01/01/1990'],
  // ...transcribed rows go here as string arrays...
];
const CENTER_COLS = new Set([0, 2]);     // indexes of columns to center-align
// =====================

function cell(text, w, { header = false, center = false } = {}) {
  return new TableCell({
    width: { size: w, type: WidthType.DXA },
    verticalAlign: VerticalAlign.CENTER,
    shading: header ? { type: ShadingType.CLEAR, fill: 'D9E2F3' } : undefined,
    margins: { top: 60, bottom: 60, left: 80, right: 80 },
    children: [new Paragraph({
      alignment: center || header ? AlignmentType.CENTER : AlignmentType.LEFT,
      children: [new TextRun({ text, font: FONT, size: 24, bold: header })],
    })],
  });
}

const tableWidth = COL_WIDTHS.reduce((a, b) => a + b, 0);
const headerRow = new TableRow({
  tableHeader: true,
  children: HEADERS.map((h, i) => cell(h, COL_WIDTHS[i], { header: true })),
});
const bodyRows = ROWS.map(r => new TableRow({
  children: r.map((v, i) => cell(v, COL_WIDTHS[i], { center: CENTER_COLS.has(i) })),
}));

const children = [
  new Paragraph({ alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: TITLE, font: FONT, size: 28, bold: true })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 240 },
    children: [new TextRun({ text: SUBTITLE, font: FONT, size: 26, bold: true })] }),
  new Table({ columnWidths: COL_WIDTHS, width: { size: tableWidth, type: WidthType.DXA },
    rows: [headerRow, ...bodyRows] }),
];
if (NOTE_BELOW) children.push(new Paragraph({ spacing: { before: 240 },
  children: [new TextRun({ text: NOTE_BELOW, font: FONT, size: 24, italics: true })] }));

const doc = new Document({
  sections: [{
    properties: { page: {
      size: LANDSCAPE ? { orientation: PageOrientation.LANDSCAPE } : {},
      margin: { top: 720, bottom: 720, left: 720, right: 720 },
    } },
    children,
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(OUTPUT, buf);
  console.log('written', OUTPUT, buf.length, 'bytes');
});
