#!/usr/bin/env python3
"""
kindle-sync: compile a /teach learning workspace into a Kindle book and email it to your Kindle.

    kindle-sync build   # lessons/*.html + reference/*.html -> lessons/kindle-output/<title>.pdf
    kindle-sync send    # email the built book to your Kindle
    kindle-sync sync    # build, then send if anything changed since the last send

Run from the workspace root, or pass --workspace. Add --format epub for a reflowable book.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import os
import re
import smtplib
import ssl
import sys
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from bs4 import BeautifulSoup

__version__ = "0.2.0"

# Shared by PDF and EPUB. Sizes are relative so EPUB readers can scale the text.
BASE_CSS = """
body { font-family: Georgia, "Times New Roman", serif; line-height: 1.5; color: #111; widows: 2; orphans: 2; }
h1 { font-size: 1.5em; margin: 0 0 0.4em; }
h2 { font-size: 1.2em; border-bottom: 1px solid #999; padding-bottom: 3px; margin-top: 1.2em; page-break-after: avoid; }
h3 { font-size: 1.05em; margin-top: 1em; page-break-after: avoid; }
p { margin: 0 0 0.6em; }
a { color: inherit; }
code { font-family: "Courier New", Courier, monospace; font-size: 0.8em; background: #f0f0f0; padding: 0 2px; }
pre {
    font-family: "Courier New", Courier, monospace; font-size: 0.7em; line-height: 1.35;
    background: #f0f0f0; border-left: 3px solid #aaa; padding: 6px 8px; margin: 6px 0;
    white-space: pre-wrap; word-break: break-all; overflow-wrap: break-word; page-break-inside: avoid;
}
pre code { font-size: 1em; background: none; padding: 0; }
table { font-size: 0.75em; border-collapse: collapse; width: 100%; margin: 8px 0; page-break-inside: avoid; }
th, td { border: 0.5px solid #bbb; padding: 3px 5px; text-align: left; vertical-align: top; }
th { background: #e8e8e8; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em; }
.mission-callout, .key-insight, .warn {
    border-left: 4px solid #555; padding: 6px 10px; margin: 8px 0; background: #fafafa; page-break-inside: avoid;
}
.reminder { border: 1px solid #ccc; padding: 8px 12px; margin: 12px 0; background: #fafafa; }
blockquote { border-left: 3px solid #aaa; padding-left: 10px; margin: 8px 0; color: #444; font-style: italic; }
ul, ol { margin: 4px 0 8px 1.2em; padding: 0; }
li { margin-bottom: 3px; }
.quiz-block { border: 1px solid #ccc; padding: 8px 10px; margin: 10px 0; background: #fafafa; page-break-inside: avoid; }
.quiz-block h3 { margin-top: 0; }
.quiz-block .q { font-weight: 600; margin: 8px 0 3px; }
.options { list-style: none; margin: 2px 0 6px 0.6em; }
.answer-key { page-break-before: always; }
.answer-key .q { font-weight: 600; margin: 0.8em 0 0.1em; }
.answer-key .a { margin: 0 0 0.4em 0.8em; }
.nav-links, .lesson-meta { display: none; }
.toc ol, .toc ul { line-height: 1.8; }
.toc a { text-decoration: none; }
"""

# 6" e-ink page.
PDF_CSS = """
@page {
    size: 4.5in 6in;
    margin: 0.35in 0.3in 0.4in 0.3in;
    @bottom-center { content: counter(page); font-family: Georgia, serif; font-size: 8pt; color: #999; }
}
@page :first { @bottom-center { content: none; } }
body { font-size: 11pt; }
.cover-title { text-align: center; font-size: 2em; margin-top: 1.6in; bookmark-level: none; }
.toc, .chapter { break-before: page; }
.toc a::after { content: leader(". ") target-counter(attr(href), page); }
"""

LEGACY_CORRECT = re.compile(r"(\w+)\s*:\s*\{\s*correct\s*:\s*(\d+)")
LEGACY_EXPLANATIONS = re.compile(r"(\w+)\s*:\s*\{\s*correct\s*:\s*\d+\s*,\s*explanations\s*:\s*\{(.*?)\}\s*\}", re.S)
LEGACY_EXPLANATION = re.compile(r"(\d+)\s*:\s*(['\"`])(.*?)(?<!\\)\2", re.S)
LEGACY_ONCLICK = re.compile(r"\(\s*['\"](\w+)['\"]\s*,\s*(\d+)")


@dataclass
class Chapter:
    id: str
    kind: str  # "lesson" or "reference"
    path: Path
    title: str
    body: object  # BeautifulSoup tag holding the chapter content


@dataclass
class Book:
    workspace: Path
    title: str
    lang: str
    chapters: list

    @property
    def slug(self):
        return re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-") or "book"

    @property
    def out_dir(self):
        return self.workspace / "lessons" / "kindle-output"


def fail(message):
    raise SystemExit(f"❌ {message}")


def book_title(workspace, override=None):
    """--title, else `# Mission: <Topic>` in MISSION.md, else the workspace folder name."""
    if override:
        return override
    mission = workspace / "MISSION.md"
    if mission.is_file():
        m = re.search(r"^#\s*Mission\s*[:—–-]\s*(.+?)\s*$", mission.read_text(encoding="utf-8"), re.M)
        if m and not m.group(1).startswith("["):
            return m.group(1)
    return workspace.name.replace("-", " ").replace("_", " ").title()


def legacy_answers(script_text):
    """Answers from the older `answers = { q1: { correct: 2, explanations: {...} } }` lesson scripts."""
    answers = {qid: (int(n), {}) for qid, n in LEGACY_CORRECT.findall(script_text)}
    for qid, block in LEGACY_EXPLANATIONS.findall(script_text):
        for n, _, text in LEGACY_EXPLANATION.findall(block):
            answers[qid][1][int(n)] = re.sub(r"\\(['\"`])", r"\1", text)
    return answers


def convert_quizzes(soup, body, legacy):
    """Turn button quizzes into lettered lists and collect an answer key for the end of the chapter."""
    key = []
    for opts in body.select(".options"):
        buttons = opts.find_all("button")
        if not buttons:
            continue
        question = opts.find_previous_sibling(class_="q")
        correct, explain = None, ""
        for i, button in enumerate(buttons):
            if button.has_attr("data-correct"):
                correct, explain = i, button.get("data-explain", "")
        if correct is None:
            m = LEGACY_ONCLICK.search(buttons[0].get("onclick", ""))
            if m and m.group(1) in legacy:
                n, explanations = legacy[m.group(1)]
                if 1 <= n <= len(buttons):
                    correct, explain = n - 1, explanations.get(n, "")
        options = [f"{chr(65 + i)}. {b.get_text(' ', strip=True)}" for i, b in enumerate(buttons)]
        ol = soup.new_tag("ol", attrs={"class": "options"})
        for text in options:
            li = soup.new_tag("li")
            li.string = text
            ol.append(li)
        opts.replace_with(ol)
        answer = "Answer: " + (options[correct] if correct is not None else "not recorded in this lesson")
        if explain:
            answer += f" — {explain}"
        key.append((question.get_text(" ", strip=True) if question else f"Question {len(key) + 1}", answer))

    for tag in body.select(".feedback") + body.find_all("button"):
        tag.decompose()
    if key:
        section = soup.new_tag("div", attrs={"class": "answer-key"})
        heading = soup.new_tag("h2")
        heading.string = "Answers"
        section.append(heading)
        for question, answer in key:
            for cls, text in (("q", question), ("a", answer)):
                p = soup.new_tag("p", attrs={"class": cls})
                p.string = text
                section.append(p)
        body.append(section)


def load_chapter(path, kind, chapter_id):
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    legacy = legacy_answers(" ".join(s.get_text() for s in soup.find_all("script")))
    page_title = soup.title.get_text(" ", strip=True) if soup.title else ""
    for tag in soup.find_all(["head", "script", "style", "link", "noscript", "template", "title", "meta"]):
        tag.decompose()
    body = soup.body or soup.html or soup
    convert_quizzes(soup, body, legacy)
    for tag in body.find_all(True):
        for attr in [a for a in tag.attrs if a.lower().startswith("on")]:
            del tag[attr]

    h1 = body.find("h1")
    if h1 is None:
        h1 = soup.new_tag("h1")
        h1.string = page_title or path.stem.lstrip("0123456789-_").replace("-", " ").capitalize() or path.stem
        body.insert(0, h1)
    return Chapter(chapter_id, kind, path, h1.get_text(" ", strip=True), body)


def load_book(workspace, title=None):
    workspace = Path(workspace).resolve()
    sources = [("lesson", p) for p in sorted((workspace / "lessons").glob("[0-9]*.html"))]
    sources += [("reference", p) for p in sorted((workspace / "reference").glob("*.html"))]
    if not sources:
        fail(f"No lessons found in {workspace}/lessons. Run from a /teach workspace or pass --workspace.")
    chapters = [load_chapter(p, kind, f"ch{i:02d}") for i, (kind, p) in enumerate(sources, 1)]
    lang = "en"
    first = BeautifulSoup(sources[0][1].read_text(encoding="utf-8"), "html.parser").html
    if first is not None and first.get("lang"):
        lang = first["lang"]
    return Book(workspace, book_title(workspace, title), lang, chapters)


def link_chapters(book, href):
    """Point links between lessons and references at the chapter inside the book."""
    by_name = {ch.path.name: ch for ch in book.chapters}
    for ch in book.chapters:
        for a in ch.body.find_all("a", href=True):
            target = a["href"]
            if re.match(r"^[a-z]+:", target, re.I):
                continue
            name = target.split("#")[0].split("?")[0].rsplit("/", 1)[-1]
            if name in by_name:
                a["href"] = href(by_name[name])


def source_digest(book, fmt):
    h = hashlib.sha256(f"{__version__}\0{book.title}\0{fmt}".encode())
    for ch in book.chapters:
        h.update(ch.path.name.encode() + b"\0" + ch.path.read_bytes())
    return h.hexdigest()


def render_pdf(book, out):
    try:
        import weasyprint
    except (ImportError, OSError) as e:
        fail(f"WeasyPrint is not usable ({e}). Install it and its system libraries (see README), "
             "or build an EPUB with --format epub.")
    link_chapters(book, lambda ch: f"#{ch.id}")
    esc = html.escape
    toc = ['<nav class="toc"><h2>Contents</h2>']
    for kind, heading, tag in (("lesson", "Lessons", "ol"), ("reference", "Reference", "ul")):
        items = [ch for ch in book.chapters if ch.kind == kind]
        if items:
            toc.append(f"<h3>{heading}</h3><{tag}>")
            toc += [f'<li><a href="#{ch.id}">{esc(ch.title)}</a></li>' for ch in items]
            toc.append(f"</{tag}>")
    toc.append("</nav>")
    doc = [
        f'<!DOCTYPE html><html lang="{esc(book.lang)}"><head><meta charset="utf-8">',
        f"<title>{esc(book.title)}</title><style>{BASE_CSS}{PDF_CSS}</style></head><body>",
        f'<h1 class="cover-title">{esc(book.title)}</h1>',
        *toc,
        *(f'<section class="chapter" id="{ch.id}">{ch.body.decode_contents()}</section>' for ch in book.chapters),
        "</body></html>",
    ]
    weasyprint.HTML(string="\n".join(doc), base_url=str(book.workspace)).write_pdf(str(out))


def xhtml(title, lang, body):
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
        f'lang="{html.escape(lang)}" xml:lang="{html.escape(lang)}">\n'
        f'<head><meta charset="utf-8"/><title>{html.escape(title)}</title>'
        '<link rel="stylesheet" type="text/css" href="style.css"/></head>\n'
        f"<body>\n{body}\n</body>\n</html>\n"
    )


def render_epub(book, out):
    link_chapters(book, lambda ch: f"{ch.id}.xhtml")
    esc = html.escape
    for ch in book.chapters:
        for svg in ch.body.find_all("svg"):
            svg["xmlns"] = "http://www.w3.org/2000/svg"
    nav = "\n".join(
        ['<nav epub:type="toc" id="toc" class="toc"><h2>Contents</h2><ol>']
        + [f'<li><a href="{ch.id}.xhtml">{esc(ch.title)}</a></li>' for ch in book.chapters]
        + ["</ol></nav>"]
    )
    manifest = "\n".join(
        f'<item id="{ch.id}" href="{ch.id}.xhtml" media-type="application/xhtml+xml"/>' for ch in book.chapters
    )
    spine = "\n".join(f'<itemref idref="{ch.id}"/>' for ch in book.chapters)
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="{esc(book.lang)}">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="bookid">urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, 'kindle-sync:' + book.title)}</dc:identifier>
<dc:title>{esc(book.title)}</dc:title>
<dc:language>{esc(book.lang)}</dc:language>
<meta property="dcterms:modified">{modified}</meta>
</metadata>
<manifest>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
<item id="css" href="style.css" media-type="text/css"/>
{manifest}
</manifest>
<spine>
<itemref idref="nav"/>
{spine}
</spine>
</package>
"""
    container = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/style.css", BASE_CSS, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/nav.xhtml", xhtml(book.title, book.lang, nav), compress_type=zipfile.ZIP_DEFLATED)
        for ch in book.chapters:
            z.writestr(f"OEBPS/{ch.id}.xhtml", xhtml(ch.title, book.lang, ch.body.decode_contents()),
                       compress_type=zipfile.ZIP_DEFLATED)


def build(book, fmt):
    book.out_dir.mkdir(parents=True, exist_ok=True)
    out = book.out_dir / f"{book.slug}.{fmt}"
    lessons = sum(ch.kind == "lesson" for ch in book.chapters)
    print(f"🔨 Building {fmt.upper()} “{book.title}” from {lessons} lessons + {len(book.chapters) - lessons} references...")
    (render_pdf if fmt == "pdf" else render_epub)(book, out)
    print(f"✅ Written: {out} ({out.stat().st_size / 1024:.1f} KB)")
    return out


CRED_KEYS = {
    "KINDLE_EMAIL": ("KINDLE_EMAIL",),
    "SENDER_EMAIL": ("SENDER_EMAIL", "GMAIL_ADDRESS"),
    "SMTP_PASSWORD": ("SMTP_PASSWORD", "GMAIL_APP_PASSWORD"),
    "SMTP_USER": ("SMTP_USER",),
    "SMTP_HOST": ("SMTP_HOST",),
    "SMTP_PORT": ("SMTP_PORT",),
}


def load_creds(workspace):
    """Environment variables, then <workspace>/.kindle-creds, then ~/.kindle-creds."""
    found, source = {}, f"{workspace / '.kindle-creds'} or ~/.kindle-creds"
    for path in (workspace / ".kindle-creds", Path.home() / ".kindle-creds"):
        if path.is_file():
            source = str(path)
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    found[k.strip()] = v.strip().strip("'\"")
            break
    creds = {}
    for key, names in CRED_KEYS.items():
        creds[key] = next((os.environ.get(n) or found.get(n) for n in names if os.environ.get(n) or found.get(n)), "")
    return creds, source


def send(book_path, workspace, title):
    creds, source = load_creds(workspace)
    missing = [k for k in ("KINDLE_EMAIL", "SENDER_EMAIL", "SMTP_PASSWORD") if not creds[k]]
    if missing:
        fail(
            f"Missing credentials: {', '.join(missing)} (looked in env vars and {source}).\n"
            "   KINDLE_EMAIL:  amazon.com/myk → Devices → your Kindle → Send-to-Kindle Email\n"
            "   SENDER_EMAIL:  an address approved in Amazon's Personal Document Settings\n"
            "   SMTP_PASSWORD: for Gmail, an app password from myaccount.google.com/apppasswords"
        )
    host = creds["SMTP_HOST"] or "smtp.gmail.com"
    port = int(creds["SMTP_PORT"] or 587)
    subtype = "pdf" if book_path.suffix == ".pdf" else "epub+zip"

    msg = EmailMessage()
    msg["From"] = creds["SENDER_EMAIL"]
    msg["To"] = creds["KINDLE_EMAIL"]
    msg["Subject"] = title
    msg.set_content(f"{title}, sent by kindle-sync.")
    msg.add_attachment(book_path.read_bytes(), maintype="application", subtype=subtype, filename=book_path.name)

    print(f"📧 Sending {book_path.name} ({book_path.stat().st_size / 1024:.0f} KB) to {creds['KINDLE_EMAIL']} via {host}...")
    context = ssl.create_default_context()
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=60, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=60)
        with server:
            if port != 465:
                server.starttls(context=context)
            server.login(creds["SMTP_USER"] or creds["SENDER_EMAIL"], creds["SMTP_PASSWORD"])
            server.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        fail(f"{host} rejected the login. Check SENDER_EMAIL/SMTP_USER and SMTP_PASSWORD "
             "(Gmail needs 2FA and an app password).")
    except (smtplib.SMTPException, OSError) as e:
        fail(f"Sending failed: {e}")
    print("✅ Sent! It appears on your Kindle within a few minutes (over Wi-Fi).")


def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-w", "--workspace", type=Path, default=Path.cwd(), help="workspace root (default: current directory)")
    common.add_argument("-f", "--format", choices=["pdf", "epub"], default="pdf", help="book format (default: pdf)")
    common.add_argument("--title", help="book title (default: `# Mission: <Topic>` in MISSION.md, else the folder name)")

    parser = argparse.ArgumentParser(prog="kindle-sync", description=__doc__.split("\n\n")[0].strip())
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build", parents=[common], help="build the book into lessons/kindle-output/")
    send_cmd = sub.add_parser("send", parents=[common], help="email the built book to your Kindle")
    send_cmd.add_argument("file", nargs="?", type=Path, help="book to send (default: the built book for --format)")
    sync_cmd = sub.add_parser("sync", parents=[common], help="build, then send if lessons changed since the last send")
    sync_cmd.add_argument("--force", action="store_true", help="send even if nothing changed")
    args = parser.parse_args(argv)

    workspace = args.workspace.resolve()
    if args.command == "send":
        title = book_title(workspace, args.title)
        path = args.file
        if path is None:
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "book"
            path = workspace / "lessons" / "kindle-output" / f"{slug}.{args.format}"
        if not path.is_file():
            fail(f"{path} not found. Run: kindle-sync build" + (" --format epub" if args.format == "epub" else ""))
        send(path, workspace, title)
        return

    book = load_book(workspace, args.title)
    if args.command == "build":
        build(book, args.format)
        return

    digest = source_digest(book, args.format)
    marker = book.out_dir / f".last-sent-{args.format}"
    if not args.force and marker.is_file() and marker.read_text().strip() == digest:
        print("✅ Nothing changed since the last send; skipping. Use --force to send anyway.")
        return
    out = build(book, args.format)
    send(out, workspace, book.title)
    marker.write_text(digest + "\n")


if __name__ == "__main__":
    main()
