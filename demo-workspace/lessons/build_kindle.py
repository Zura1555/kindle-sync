#!/usr/bin/env python3
"""
Build a single Kindle-optimized PDF from all lessons and references.
Usage: python3 build_kindle.py
Output: lessons/kindle-output/<workspace-name>.pdf

Drop this into your /teach workspace's lessons/ directory.
"""
import weasyprint
from pathlib import Path

# Workspace root = parent of the lessons/ directory this script lives in
BASE = Path(__file__).resolve().parent.parent
LESSONS = sorted(BASE.glob("lessons/0*.html"))
REFERENCES = sorted(BASE.glob("reference/*.html"))
OUTPUT_DIR = BASE / "lessons" / "kindle-output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Derive book title from workspace directory name
BOOK_TITLE = BASE.resolve().name.replace("-", " ").replace("_", " ").title()

# Kindle-optimized CSS for 6" e-ink display
KINDLE_CSS = """
@page {
    size: 4.5in 6in;
    margin: 0.35in 0.3in 0.4in 0.3in;
    @bottom-center {
        content: counter(page);
        font-family: Georgia, serif;
        font-size: 8pt;
        color: #999;
    }
}
body {
    font-family: Georgia, "Times New Roman", serif;
    font-size: 11pt;
    line-height: 1.5;
    color: #111;
    max-width: 100%;
    padding: 0;
    background: white;
    widows: 2;
    orphans: 2;
}
h1 {
    font-size: 1.5em;
    page-break-before: always;
    margin-top: 0;
    padding-top: 0;
}
h2 {
    font-size: 1.2em;
    border-bottom: 1px solid #999;
    padding-bottom: 3px;
    margin-top: 1.2em;
    page-break-after: avoid;
}
h3 {
    font-size: 1.05em;
    margin-top: 1em;
    page-break-after: avoid;
}
p { margin-bottom: 0.6em; }
code {
    font-family: "Courier New", Courier, monospace;
    font-size: 8.5pt;
    background: #f0f0f0;
    padding: 0 2px;
}
pre {
    font-family: "Courier New", Courier, monospace;
    font-size: 7.5pt;
    line-height: 1.35;
    background: #f0f0f0;
    border-left: 3px solid #aaa;
    padding: 6px 8px;
    margin: 6px 0;
    white-space: pre-wrap;
    word-break: break-all;
    overflow-wrap: break-word;
    page-break-inside: avoid;
}
table {
    font-size: 8pt;
    border-collapse: collapse;
    width: 100%;
    margin: 8px 0;
    page-break-inside: avoid;
}
th, td {
    border: 0.5px solid #bbb;
    padding: 3px 5px;
    text-align: left;
    vertical-align: top;
}
th {
    background: #e8e8e8;
    font-weight: 700;
    font-size: 7.5pt;
    text-transform: uppercase;
    letter-spacing: 0.03em;
}
.mission-callout, .key-insight, .warn {
    border-left: 4px solid #555;
    padding: 6px 10px;
    margin: 8px 0;
    background: #fafafa;
}
.reminder {
    border: 1px solid #ccc;
    padding: 8px 12px;
    margin: 12px 0;
    background: #fafafa;
}
blockquote {
    border-left: 3px solid #aaa;
    padding-left: 10px;
    margin: 8px 0;
    color: #444;
    font-style: italic;
}
ul, ol { margin: 4px 0 8px 1.2em; padding: 0; }
li { margin-bottom: 3px; }
.quiz-block {
    border: 1px solid #ccc;
    padding: 8px 10px;
    margin: 10px 0;
    background: #fafafa;
    page-break-inside: avoid;
}
.quiz-block h3 { margin-top: 0; }
.quiz-block .q { font-weight: 600; margin: 8px 0 3px; font-size: 10pt; }
.quiz-block .options { display: none; }
.quiz-block .feedback {
    display: block !important;
    font-size: 9pt;
    color: #555;
    margin-top: 4px;
    padding: 4px 6px;
    border-left: 3px solid #aaa;
}
.nav-links { display: none; }
button { display: none; }
.lesson-meta { display: none; }
.mission-callout, .key-insight, .warn { page-break-inside: avoid; }
.cover-title {
    text-align: center;
    font-size: 2em;
    margin-top: 2in;
    page-break-after: always;
}
.toc ol { line-height: 1.8; }
"""


def extract_body(html_path):
    """Extract content between <body> and </body>, removing <script> blocks."""
    text = html_path.read_text()
    body_start = text.find("<body>") + 6
    body_end = text.find("</body>")
    if body_start == 5 or body_end == -1:
        return ""
    body = text[body_start:body_end]
    while "<script>" in body:
        s = body.find("<script>")
        e = body.find("</script>", s) + 9
        body = body[:s] + body[e:]
    return body


# Build combined HTML
parts = [
    '<!DOCTYPE html><html><head><meta charset="UTF-8">',
    f'<title>{BOOK_TITLE}</title>',
    f'<meta name="dc:title" content="{BOOK_TITLE}">',
    '<style>',
    KINDLE_CSS,
    '</style></head><body>'
]

# Cover page + Table of Contents
parts.append(f'<div class="cover-title">{BOOK_TITLE}</div>')
parts.append('<div class="toc"><h2>Contents</h2><ol>')
for i, lp in enumerate(LESSONS):
    title = lp.read_text().split("<title>")[1].split("</title>")[0]
    parts.append(f'<li>Lesson {i + 1}: {title}</li>')
for rp in REFERENCES:
    title = rp.read_text().split("<title>")[1].split("</title>")[0]
    parts.append(f'<li>Reference: {title}</li>')
parts.append('</ol></div>')

# Add each lesson
for lp in LESSONS:
    title = lp.read_text().split("<title>")[1].split("</title>")[0]
    parts.append(f'<h1>{title}</h1>')
    parts.append(extract_body(lp))

# Add references
for rp in REFERENCES:
    title = rp.read_text().split("<title>")[1].split("</title>")[0]
    parts.append(f'<h1>{title}</h1>')
    parts.append(extract_body(rp))

parts.append('</body></html>')

combined_html = '\n'.join(parts)
html_path = OUTPUT_DIR / "combined.html"
html_path.write_text(combined_html)

# Convert to PDF
print(f"Rendering PDF from {len(LESSONS)} lessons + {len(REFERENCES)} references...")
doc = weasyprint.HTML(filename=str(html_path))
pdf_name = BOOK_TITLE.lower().replace(" ", "-") + ".pdf"
pdf_path = OUTPUT_DIR / pdf_name
doc.write_pdf(str(pdf_path))
print(f"✅ PDF written: {pdf_path}")
print(f"   Size: {pdf_path.stat().st_size / 1024:.1f} KB")
