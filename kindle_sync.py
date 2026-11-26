#!/usr/bin/env python3
"""
kindle-sync: compile a /teach learning workspace into a Kindle book and email it to your Kindle.

    kindle-sync setup   # one-time: Kindle address, sender, app password (hidden), format
    kindle-sync build   # lessons/*.html + reference/*.html -> lessons/kindle-output/<title>.epub
                        # (book workspaces with BOOK.md: chapters/*.html -> chapters/kindle-output/)
    kindle-sync send    # email the built book to your Kindle
    kindle-sync sync    # build, then send if anything changed since the last submission to this Kindle
    kindle-sync sync --dry-run  # show what sync would do, without building, sending, or recording anything
    kindle-sync doctor  # check settings and dependencies
    kindle-sync status  # show settings, setup progress, and recent submissions
    kindle-sync test    # send a small test document
    kindle-sync resolve sent|not-sent  # settle a submission whose outcome is unknown
    kindle-sync reset   # delete saved settings and the app password (asks first)

Run from the workspace root, or pass --workspace. Books are EPUB unless you choose PDF.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import html
import json
import os
import re
import smtplib
import ssl
import sys
import tempfile
import time
import uuid
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import quote, unquote

from bs4 import BeautifulSoup

try:
    import fcntl
    msvcrt = None
except ImportError:  # Windows
    import msvcrt
    fcntl = None

__version__ = "0.3.0"

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
img, svg { max-width: 100%; height: auto; }
figure { margin: 0.8em 0; text-align: center; page-break-inside: avoid; }
figcaption { font-size: 0.85em; font-style: italic; color: #444; margin-top: 0.3em; }
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
.cover-image { display: block; max-height: 3.6in; margin: 0.2in auto 0; }
.cover-image + .cover-title { margin-top: 0.2in; }
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
    images: list = field(default_factory=list)  # image files the chapter shows, inside the workspace


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
        return content_dir(self.workspace) / "kindle-output"

    @property
    def cover(self):
        """assets/cover.png (or .jpg), shown as the book's cover."""
        return next((p for p in (self.workspace / "assets" / f"cover.{ext}" for ext in ("png", "jpg", "jpeg"))
                     if p.is_file()), None)


def fail(message):
    raise SystemExit(f"❌ {message}")


def content_dir(workspace):
    """Book workspaces (with BOOK.md) keep chapters in chapters/; /teach workspaces keep lessons in lessons/."""
    return Path(workspace) / ("chapters" if (Path(workspace) / "BOOK.md").is_file() else "lessons")


def book_title(workspace, override=None):
    """--title, else `# Book: <Title>` in BOOK.md or `# Mission: <Topic>` in MISSION.md, else the folder name."""
    if override:
        return override
    for name, word in (("BOOK.md", "Book"), ("MISSION.md", "Mission")):
        path = workspace / name
        if path.is_file():
            m = re.search(rf"^#\s*{word}\s*[:—–-]\s*(.+?)\s*$", path.read_text(encoding="utf-8"), re.M)
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


# html.parser lowercases names, but SVG is case-sensitive in EPUB's XHTML: `viewbox` is ignored and
# `lineargradient` is an unknown element. These are the camelCase names the HTML parsing spec restores.
SVG_NAMES = {n.lower(): n for n in (
    "altGlyph altGlyphDef altGlyphItem animateColor animateMotion animateTransform clipPath feBlend feColorMatrix "
    "feComponentTransfer feComposite feConvolveMatrix feDiffuseLighting feDisplacementMap feDistantLight "
    "feDropShadow feFlood feFuncA feFuncB feFuncG feFuncR feGaussianBlur feImage feMerge feMergeNode feMorphology "
    "feOffset fePointLight feSpecularLighting feSpotLight feTile feTurbulence foreignObject glyphRef "
    "linearGradient radialGradient textPath "
    "attributeName attributeType baseFrequency baseProfile calcMode clipPathUnits diffuseConstant edgeMode "
    "filterUnits gradientTransform gradientUnits kernelMatrix kernelUnitLength keyPoints keySplines keyTimes "
    "lengthAdjust limitingConeAngle markerHeight markerUnits markerWidth maskContentUnits maskUnits numOctaves "
    "pathLength patternContentUnits patternTransform patternUnits pointsAtX pointsAtY pointsAtZ preserveAlpha "
    "preserveAspectRatio primitiveUnits refX refY repeatCount repeatDur requiredExtensions requiredFeatures "
    "specularConstant specularExponent spreadMethod startOffset stdDeviation stitchTiles surfaceScale "
    "systemLanguage tableValues targetX targetY textLength viewBox viewTarget xChannelSelector yChannelSelector "
    "zoomAndPan").split()}
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
               ".svg": "image/svg+xml", ".webp": "image/webp"}


def fix_svg(body):
    for svg in body.find_all("svg"):
        for tag in [svg, *svg.find_all(True)]:
            tag.name = SVG_NAMES.get(tag.name, tag.name)
            tag.attrs = {SVG_NAMES.get(k, k): v for k, v in tag.attrs.items()}
        if any(k.startswith("xlink:") for tag in [svg, *svg.find_all(True)] for k in tag.attrs):
            svg["xmlns:xlink"] = "http://www.w3.org/1999/xlink"


def embed_images(soup, body, path, workspace):
    """Point each <img> at its file's path in the workspace, which both formats embed. Books are built offline,
    so an image that isn't a file in the workspace becomes its alt text."""
    images = []
    for img in body.find_all("img"):
        src = img.get("src", "").strip()
        if src.startswith("data:image/"):
            continue
        file = None
        if src and not re.match(r"^([a-z][a-z0-9+.-]*:|//)", src, re.I):
            file = (path.parent / unquote(src.split("#")[0].split("?")[0])).resolve()
        if file and file.is_file() and file.is_relative_to(workspace) and file.suffix.lower() in IMAGE_TYPES:
            img["src"] = quote(file.relative_to(workspace).as_posix())
            img["alt"] = img.get("alt", "")
            images.append(file)
            continue
        print(f"⚠️  {path.name}: image “{src}” is not an image file in the workspace; using its alt text instead.")
        alt = img.get("alt", "").strip()
        if alt:
            em = soup.new_tag("em")
            em.string = f"[{alt}]"
            img.replace_with(em)
        else:
            img.decompose()
    return images


def load_chapter(path, kind, chapter_id, workspace):
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
    fix_svg(body)
    images = embed_images(soup, body, path, workspace)

    h1 = body.find("h1")
    if h1 is None:
        h1 = soup.new_tag("h1")
        h1.string = page_title or path.stem.lstrip("0123456789-_").replace("-", " ").capitalize() or path.stem
        body.insert(0, h1)
    return Chapter(chapter_id, kind, path, h1.get_text(" ", strip=True), body, images)


def load_book(workspace, title=None):
    workspace = Path(workspace).resolve()
    folder = content_dir(workspace)
    sources = [("lesson", p) for p in sorted(folder.glob("[0-9]*.html"))]
    sources += [("reference", p) for p in sorted((workspace / "reference").glob("*.html"))]
    if not sources:
        fail(f"No {folder.name} found in {folder}. Run from a /teach or book workspace or pass --workspace.")
    chapters = [load_chapter(p, kind, f"ch{i:02d}", workspace) for i, (kind, p) in enumerate(sources, 1)]
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


# Identifies how books are rendered. Bump it when a change alters the built book, so unchanged lessons are sent
# again with the fix. Releases that don't change the book leave it alone, so upgrading doesn't resend anything.
RENDER_VERSION = 2  # 2: embeds images and keeps SVG case


def book_files(book):
    """Every file the book is built from: chapters, then the images they show and the cover."""
    images = dict.fromkeys(img for ch in book.chapters for img in ch.images)
    if book.cover:
        images[book.cover.resolve()] = None
    return [ch.path for ch in book.chapters] + sorted(images)


def source_digest(book, fmt):
    h = hashlib.sha256(f"render-{RENDER_VERSION}\0{book.title}\0{fmt}".encode())
    for path in book_files(book):
        h.update(path.resolve().relative_to(book.workspace).as_posix().encode() + b"\0" + path.read_bytes())
    return h.hexdigest()


def chapter_hashes(book):
    """Each source file's hash by its path in the workspace, to list which lessons and images changed."""
    return {path.resolve().relative_to(book.workspace).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in book_files(book)}


def render_pdf(book, out):
    try:
        import weasyprint
    except (ImportError, OSError) as e:
        fail(f"WeasyPrint is not usable ({e}). Install it and its system libraries (see README), "
             "or build an EPUB with --format epub.")
    link_chapters(book, lambda ch: f"#{ch.id}")
    esc = html.escape
    toc = ['<nav class="toc"><h2>Contents</h2>']
    for kind, heading, tag in (("lesson", content_dir(book.workspace).name.title(), "ol"), ("reference", "Reference", "ul")):
        items = [ch for ch in book.chapters if ch.kind == kind]
        if items:
            toc.append(f"<h3>{heading}</h3><{tag}>")
            toc += [f'<li><a href="#{ch.id}">{esc(ch.title)}</a></li>' for ch in items]
            toc.append(f"</{tag}>")
    toc.append("</nav>")
    doc = [
        f'<!DOCTYPE html><html lang="{esc(book.lang)}"><head><meta charset="utf-8">',
        f"<title>{esc(book.title)}</title><style>{BASE_CSS}{PDF_CSS}</style></head><body>",
        f'<img class="cover-image" alt="" src="{quote(book.cover.relative_to(book.workspace).as_posix())}">'
        if book.cover else "",
        f'<h1 class="cover-title">{esc(book.title)}</h1>',
        *toc,
        *(f'<section class="chapter" id="{ch.id}">{ch.body.decode_contents()}</section>' for ch in book.chapters),
        "</body></html>",
    ]
    # Image paths are relative to the workspace root (see embed_images).
    weasyprint.HTML(string="\n".join(doc), base_url=book.workspace.as_uri() + "/").write_pdf(str(out))


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
    # Images keep their path in the workspace, relative to the chapters, so the <img> paths need no change.
    images = {p.resolve().relative_to(book.workspace).as_posix(): p for p in book_files(book)[len(book.chapters):]}
    cover = book.cover and book.cover.resolve().relative_to(book.workspace).as_posix()
    manifest = "\n".join(
        [f'<item id="{ch.id}" href="{ch.id}.xhtml" media-type="application/xhtml+xml"'
         + (' properties="svg"/>' if ch.body.find("svg") else "/>") for ch in book.chapters]
        + [f'<item id="{"cover-image" if name == cover else f"img{i}"}" href="{esc(quote(name))}" '
           f'media-type="{IMAGE_TYPES[Path(name).suffix.lower()]}"'
           + (' properties="cover-image"/>' if name == cover else "/>") for i, name in enumerate(images, 1)]
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
{'<meta name="cover" content="cover-image"/>' if cover else ""}
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
        for name, path in images.items():
            z.write(path, f"OEBPS/{name}", compress_type=zipfile.ZIP_DEFLATED)


def build(book, fmt):
    book.out_dir.mkdir(parents=True, exist_ok=True)
    out = book.out_dir / f"{book.slug}.{fmt}"
    lessons = sum(ch.kind == "lesson" for ch in book.chapters)
    print(f"🔨 Building {fmt.upper()} “{book.title}” from {lessons} {content_dir(book.workspace).name} + "
          f"{len(book.chapters) - lessons} references...")
    (render_pdf if fmt == "pdf" else render_epub)(book, out)
    print(f"✅ Written: {out} ({out.stat().st_size / 1024:.1f} KB)")
    return out


# ---------------------------------------------------------------------------
# Configuration: environment, then <workspace>/.kindle-creds, then the user config (and the system keyring
# for the password), then the legacy ~/.kindle-creds. Each key comes from the first place that sets it.

FORMATS = ("epub", "pdf")
CONFIG_KEYS = ("KINDLE_EMAIL", "SENDER_EMAIL", "SMTP_PASSWORD", "SMTP_USER", "SMTP_HOST", "SMTP_PORT", "FORMAT")
ALIASES = {"SENDER_EMAIL": ("GMAIL_ADDRESS",), "SMTP_PASSWORD": ("GMAIL_APP_PASSWORD",)}
KEYRING_SERVICE = "kindle-sync"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
KINDLE_DOMAINS = ("@kindle.com", "@free.kindle.com", "@kindle.cn")
SMTP_PRESETS = {
    "gmail.com": ("smtp.gmail.com", "587"),
    "googlemail.com": ("smtp.gmail.com", "587"),
    "icloud.com": ("smtp.mail.me.com", "587"),
    "me.com": ("smtp.mail.me.com", "587"),
    "yahoo.com": ("smtp.mail.yahoo.com", "465"),
    "fastmail.com": ("smtp.fastmail.com", "465"),
}
HINTS = {
    "KINDLE_EMAIL": "your Send-to-Kindle address (amazon.com/myk → Devices → your Kindle)",
    "SENDER_EMAIL": "the address you send from, approved in Amazon's Personal Document Settings",
    "SMTP_PASSWORD": "an app password from your mail provider (Gmail: myaccount.google.com/apppasswords)",
}


def user_config_dir():
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "kindle-sync"


def config_files(workspace):
    """Credential files, highest precedence first."""
    paths = [workspace / ".kindle-creds", user_config_dir() / "config", Path.home() / ".kindle-creds"]
    return [p for i, p in enumerate(paths) if p not in paths[:i]]


def read_kv(path):
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            found[k.strip()] = v.strip().strip("'\"")
    return found


def too_open(path):
    return os.name == "posix" and path.stat().st_mode & 0o077


def keyring_backend():
    """The OS credential store (macOS Keychain, Windows Credential Locker, Secret Service), or None."""
    try:
        import keyring

        backend = keyring.get_keyring()
        return backend if backend.priority > 0 else None
    except Exception:
        return None


@dataclass
class Config:
    values: dict
    sources: dict  # key -> where its value came from
    warnings: list

    def __getitem__(self, key):
        return self.values.get(key, "")

    @property
    def host(self):
        return self["SMTP_HOST"] or "smtp.gmail.com"

    @property
    def port(self):
        return int(self["SMTP_PORT"] or 587)

    @property
    def user(self):
        return self["SMTP_USER"] or self["SENDER_EMAIL"]


def pick(raw):
    out = {}
    for key in CONFIG_KEYS:
        name = next((n for n in (key,) + ALIASES.get(key, ()) if raw.get(n)), None)
        if name:
            out[key] = raw[name]
    return out


def load_config(workspace, to=None, secrets=True):
    layers, warnings = [("environment variable", pick(os.environ))], []
    for path in config_files(workspace):
        if path.is_file():
            values = pick(read_kv(path))
            if values.get("SMTP_PASSWORD") and too_open(path):
                del values["SMTP_PASSWORD"]
                warnings.append(f"Ignored SMTP_PASSWORD in {path} because other users can read it. Run: chmod 600 {path}")
            layers.append((str(path), values))
    values, sources = {}, {}
    for label, layer in layers:
        for key, value in layer.items():
            if key not in values:
                values[key], sources[key] = value, label
    if to:
        values["KINDLE_EMAIL"], sources["KINDLE_EMAIL"] = to, "--to"
    cfg = Config(values, sources, warnings)
    if secrets and sources.get("SMTP_PASSWORD") in (None, str(Path.home() / ".kindle-creds")) and cfg.user:
        backend = keyring_backend()
        try:
            secret = backend.get_password(KEYRING_SERVICE, cfg.user) if backend else None
        except Exception:
            secret = None
        if secret:
            values["SMTP_PASSWORD"], sources["SMTP_PASSWORD"] = secret, "system keyring"
    return cfg


def email_error(value):
    return None if EMAIL_RE.match(value or "") else "Enter an email address like name@example.com."


def port_error(value):
    return None if value.isdigit() and 0 < int(value) < 65536 else "Enter a port number from 1 to 65535 (usually 587 or 465)."


def config_problems(cfg):
    problems = [f"{key} is not set: {HINTS[key]}" for key in HINTS if not cfg[key]]
    for key in ("KINDLE_EMAIL", "SENDER_EMAIL"):
        if cfg[key] and email_error(cfg[key]):
            problems.append(f"{key} is not a valid email address: {cfg[key]!r} (from {cfg.sources[key]})")
    if cfg["SMTP_PORT"] and port_error(cfg["SMTP_PORT"]):
        problems.append(f"SMTP_PORT must be a number from 1 to 65535, not {cfg['SMTP_PORT']!r} (from {cfg.sources['SMTP_PORT']})")
    if cfg["FORMAT"] and cfg["FORMAT"].lower() not in FORMATS:
        problems.append(f"FORMAT must be epub or pdf, not {cfg['FORMAT']!r} (from {cfg.sources['FORMAT']})")
    return problems


def require_send_config(cfg):
    problems = config_problems(cfg)
    if problems:
        fail("Kindle delivery is not set up:\n" + "".join(f"   - {p}\n" for p in problems + cfg.warnings)
             + "   Run `kindle-sync setup` to configure it, or `kindle-sync doctor` for details.")


def format_choice(choice, cfg, workspace):
    """(format, reason). New users get EPUB; an explicit or saved choice, or earlier PDF syncs, keep PDF."""
    if choice:
        return choice, "--format"
    if cfg["FORMAT"].lower() in FORMATS:
        return cfg["FORMAT"].lower(), f"FORMAT in {cfg.sources['FORMAT']}"
    if (content_dir(workspace) / "kindle-output" / ".last-sent-pdf").is_file():
        return "pdf", "earlier PDF syncs in this workspace"
    return "epub", "default"


def resolve_format(choice, cfg, workspace):
    fmt, reason = format_choice(choice, cfg, workspace)
    if reason.startswith("earlier"):
        print("ℹ️  Using PDF, as in this workspace's earlier syncs. New setups default to EPUB. "
              "Set FORMAT=pdf or FORMAT=epub with `kindle-sync setup` to choose and hide this note.")
    return fmt


# ---------------------------------------------------------------------------
# Submission state: lessons/kindle-output/.kindle-sync-state.json, shared by build, send, sync, and resolve.
#   builds:      book file -> digest and lesson hashes of its last build
#   submissions: destination|sender|SMTP host|SMTP user|book file -> the last submission the provider accepted
#   unknown:     same keys -> a submission whose connection broke, so it may or may not have gone out
#   history:     the last HISTORY_LIMIT attempts

STATE_FILE = ".kindle-sync-state.json"
HISTORY_LIMIT = 20
RESEND_NOTE = ("ℹ️  This sends a new copy of the whole book. Your Kindle may keep it as a separate document next to "
               "the earlier copy, and highlights, notes, and reading position from the earlier copy may not carry over.")


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def local_time(iso):
    return datetime.fromisoformat(iso).astimezone().strftime("%Y-%m-%d %H:%M")


def write_atomic(path, text, mode=0o644):
    """Write a sibling temp file, then rename it over path, so readers never see a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except ValueError:
        print(f"⚠️  {path} is unreadable; starting a fresh history.")
        return {}


def write_json(path, data):
    write_atomic(path, json.dumps(data, indent=2) + "\n")


@contextmanager
def locked_state(out_dir):
    """Hold the workspace lock, so concurrent syncs, in any process, can't both submit the same book."""
    out_dir.mkdir(parents=True, exist_ok=True)
    fd = os.open(out_dir / ".kindle-sync.lock", os.O_RDWR | os.O_CREAT, 0o644)
    try:
        if msvcrt:
            while True:  # LK_LOCK gives up after 10 seconds, and a submission can take longer
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.2)
        else:
            fcntl.flock(fd, fcntl.LOCK_EX)
        yield read_json(out_dir / STATE_FILE)
    finally:
        if msvcrt:
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        os.close(fd)


def submission_key(cfg, filename):
    """One entry per destination, sending account, and book file (which carries the format)."""
    return "|".join(s.lower() for s in (cfg["KINDLE_EMAIL"], cfg["SENDER_EMAIL"], cfg.host, cfg.user, filename))


def add_history(state, record, **changes):
    entry = {k: v for k, v in record.items() if k != "chapters"}
    entry.update(changes)
    state["history"] = (state.get("history", []) + [entry])[-HISTORY_LIMIT:]


# ---------------------------------------------------------------------------
# Onboarding progress, per user: ~/.config/kindle-sync/onboarding.json
#   logins: SMTP host|user -> the last login attempt
#   tests:  Kindle address -> the sender of the last test document, when it was submitted, and when you confirmed it


def onboarding_path():
    return user_config_dir() / "onboarding.json"


def login_key(cfg):
    return f"{cfg.host}|{cfg.user}".lower()


def update_onboarding(change):
    """Best effort: a read-only home directory must not stop a submission."""
    try:
        data = read_json(onboarding_path())
        change(data)
        write_json(onboarding_path(), data)
    except OSError:
        pass


def record_login(cfg, error=None):
    def change(data):
        data.setdefault("logins", {})[login_key(cfg)] = {"at": now_iso(), **({"error": error} if error else {})}
    update_onboarding(change)


def kindle_test(cfg):
    """The test-document record for this Kindle, if the test came from the current sender."""
    entry = read_json(onboarding_path()).get("tests", {}).get(cfg["KINDLE_EMAIL"].lower(), {})
    return entry if entry.get("sender", "").lower() == cfg["SENDER_EMAIL"].lower() else {}


def record_test(cfg, confirmed):
    def change(data):
        tests = data.setdefault("tests", {})
        key = cfg["KINDLE_EMAIL"].lower()
        entry = tests.get(key, {})
        if entry.get("sender", "").lower() != cfg["SENDER_EMAIL"].lower():
            entry = {}
        entry["sender"] = cfg["SENDER_EMAIL"]
        if confirmed:
            entry["confirmed_at"] = now_iso()
        else:
            entry["submitted_at"] = now_iso()
            entry.pop("confirmed_at", None)
        tests[key] = entry
    update_onboarding(change)


def onboarding_steps(cfg):
    problems = config_problems(cfg)
    login = read_json(onboarding_path()).get("logins", {}).get(login_key(cfg), {})
    test = kindle_test(cfg)
    steps = [("✅", "Settings are complete") if not problems else
             ("❌", f"Settings are incomplete: {problems[0]}. Run `kindle-sync setup`.")]
    if login.get("error"):
        steps.append(("❌", f"The last mail login ({local_time(login['at'])}) failed: {login['error']}"))
    elif login:
        steps.append(("✅", f"Mail login worked ({local_time(login['at'])})"))
    else:
        steps.append(("⬜", "Mail login not checked yet. Run `kindle-sync doctor --check-login` (sends nothing)."))
    if test.get("submitted_at"):
        steps.append(("✅", f"Test document submitted ({local_time(test['submitted_at'])})"))
    else:
        steps.append(("⬜", "No test document yet. Run `kindle-sync test` to send one."))
    if test.get("confirmed_at"):
        steps.append(("✅", f"You confirmed the test arrived ({local_time(test['confirmed_at'])})"))
    elif test.get("submitted_at"):
        steps.append(("⬜", "Arrival not confirmed. Once the test is on your Kindle, run `kindle-sync test --confirm`; "
                           "if it doesn't arrive, run `kindle-sync test --troubleshoot`."))
    else:
        steps.append(("⬜", "Arrival not confirmed"))
    return steps


def troubleshooting(cfg):
    sender = cfg["SENDER_EMAIL"] or "your sender address"
    dest = cfg["KINDLE_EMAIL"] or "your Send-to-Kindle address"
    return ("If the document hasn't reached your Kindle after 10 minutes, check these in order:\n"
            f"  1. Sent mail: the email to {dest} is in {sender}'s Sent folder. If it isn't, your provider didn't\n"
            "     send it; run `kindle-sync doctor --check-login`.\n"
            f"  2. Replies from Amazon: look in {sender}'s inbox and spam for an Amazon email asking you to verify\n"
            "     the request, or saying the document couldn't be delivered. Follow its instructions.\n"
            "  3. Approved sender: amazon.com/myk → Preferences → Personal Document Settings → Approved Personal\n"
            f"     Document E-mail List includes {sender}.\n"
            f"  4. Destination: {dest} is the Send-to-Kindle address shown for this device under\n"
            "     amazon.com/myk → Devices.\n"
            "  5. Your library: if the document is listed under amazon.com/myk → Content → Docs, Amazon has it and\n"
            "     the device hasn't downloaded it yet.\n"
            "  6. The Kindle: connect it to Wi-Fi and choose Sync from its menu or settings.\n"
            "Run `kindle-sync test --confirm` once it arrives, or `kindle-sync test` to send another.")


# ---------------------------------------------------------------------------
# Email submission. Success means the mail provider accepted the message, not that it reached the Kindle.

class SubmitError(Exception):
    def __init__(self, result, message):
        super().__init__(message)
        self.result, self.message = result, message  # result: "failed" or "unknown"


def smtp_login(cfg):
    host, port = cfg.host, cfg.port
    context = ssl.create_default_context()
    server = None
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=60, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=60)
            server.starttls(context=context)
        server.login(cfg.user, cfg["SMTP_PASSWORD"])
        record_login(cfg)
        return server
    except smtplib.SMTPAuthenticationError:
        message = (f"Authentication rejected: {host} refused the login for {cfg.user}. Check SENDER_EMAIL/SMTP_USER "
                   "and SMTP_PASSWORD (Gmail needs 2-Step Verification and an app password), or run `kindle-sync setup`.")
    except smtplib.SMTPNotSupportedError:
        message = f"{host}:{port} does not offer STARTTLS. Most providers use port 587 (STARTTLS) or 465 (SSL)."
    except (smtplib.SMTPException, OSError) as e:
        stage = "log in to" if server else "connect to"
        message = (f"Network problem: could not {stage} {host}:{port} ({e}). "
                   "Check your internet connection and SMTP_HOST/SMTP_PORT.")
    if server:
        server.close()
    record_login(cfg, message)
    raise SubmitError("failed", message)


def deliver(cfg, attachment, subject):
    host, to = cfg.host, cfg["KINDLE_EMAIL"]
    msg = EmailMessage()
    msg["From"] = cfg["SENDER_EMAIL"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(f"{subject}, sent by kindle-sync.")
    subtype = "pdf" if attachment.suffix.lower() == ".pdf" else "epub+zip"
    msg.add_attachment(attachment.read_bytes(), maintype="application", subtype=subtype, filename=attachment.name)

    print(f"📧 Submitting {attachment.name} ({attachment.stat().st_size / 1024:.0f} KB) for {to} via {host}...")
    server = smtp_login(cfg)
    try:
        server.send_message(msg)
    except smtplib.SMTPRecipientsRefused:
        raise SubmitError("failed", f"Recipient refused: {host} would not send to {to}. Check KINDLE_EMAIL.")
    except smtplib.SMTPSenderRefused as e:
        raise SubmitError("failed", f"Sender refused: {host} would not send from {cfg['SENDER_EMAIL']} ({e.smtp_code}).")
    except smtplib.SMTPDataError as e:
        raise SubmitError("failed", f"{host} rejected the message ({e.smtp_code} {e.smtp_error.decode(errors='replace')}). "
                                    "Large books can exceed provider attachment limits.")
    except (smtplib.SMTPException, OSError) as e:
        raise SubmitError("unknown", f"The connection to {host} broke while submitting ({e}). The provider may or may not "
                                     "have accepted the message, so it is not marked as sent. Check your Sent mail, "
                                     "then run `kindle-sync resolve sent` or `kindle-sync resolve not-sent`.")
    finally:
        try:
            server.quit()
        except Exception:
            server.close()


def print_submitted(cfg, checks=True):
    dest, sender = cfg["KINDLE_EMAIL"], cfg["SENDER_EMAIL"]
    print(f"📤 Submitted to {cfg.host} for delivery to {dest}. Kindle delivery is not confirmed.")
    if not checks:
        return
    test = kindle_test(cfg)
    if test.get("confirmed_at"):
        print(f"   Your test from {sender} reached this Kindle on {local_time(test['confirmed_at'])}. "
              "Check the Kindle once it's on Wi-Fi.")
        return
    print("   If it doesn't show up on your Kindle (over Wi-Fi), check:\n"
          f"   - {sender} is on Amazon's Approved Personal Document E-mail List\n"
          f"   - Amazon hasn't emailed {sender} a verification request waiting for approval\n"
          f"   - {dest} is the Send-to-Kindle address of the right device\n"
          "   - the Kindle is online; sync it from its settings\n"
          "   `kindle-sync test --troubleshoot` lists more checks.")


def before_submit(state, key, args):
    """Stop before a possible duplicate of a submission with an unknown outcome, and explain what a resend does."""
    pending = state.get("unknown", {}).get(key)
    if pending:
        print(f"⚠️  Outcome unknown: the connection broke while submitting {pending['file']} to "
              f"{pending['destination']} on {local_time(pending['at'])}, so it may already be on its way.")
        if args.retry_unknown:
            print("   Submitting again because of --retry-unknown.")
        elif not (sys.stdin.isatty() and confirm("   Check your Sent mail first. Submit again anyway? "
                                                 "Your Kindle may get two copies.")):
            fail("Not submitted. Look for that email in your Sent mail, then run one of:\n"
                 "   kindle-sync resolve sent        # it went out: record it as submitted\n"
                 "   kindle-sync resolve not-sent    # it didn't: clear the warning\n"
                 "   or add --retry-unknown to submit again anyway.")
    if key in state.get("submissions", {}):
        print(RESEND_NOTE)


def submit(cfg, path, title, fmt, digest, chapters, state, out_dir):
    """Submit one book and record the attempt. Only a successful submission marks the book as sent."""
    key = submission_key(cfg, path.name)
    record = {"destination": cfg["KINDLE_EMAIL"], "sender": cfg["SENDER_EMAIL"], "smtp": f"{cfg.host}:{cfg.port}",
              "book": title, "file": path.name, "format": fmt, "digest": digest, "chapters": chapters, "at": now_iso()}
    try:
        deliver(cfg, path, title)
        record["result"] = "submitted"
        state.setdefault("submissions", {})[key] = record
        state.get("unknown", {}).pop(key, None)
    except SubmitError as e:
        record.update(result=e.result, error=e.message)
        if e.result == "unknown":
            state.setdefault("unknown", {})[key] = record
        raise SystemExit(f"❌ {e.message}")
    finally:
        add_history(state, record)
        write_json(out_dir / STATE_FILE, state)
    print_submitted(cfg)


def file_digest(path):
    return "file:" + hashlib.sha256(path.read_bytes()).hexdigest()


def record_build(state, out, digest, chapters, out_dir):
    state.setdefault("builds", {})[out.name] = {"digest": digest, "chapters": chapters, "built_at": now_iso()}
    write_json(out_dir / STATE_FILE, state)


def describe_changes(old, new):
    lines = [f"added    {n}" for n in sorted(set(new) - set(old))]
    lines += [f"changed  {n}" for n in sorted(n for n in new if n in old and old[n] != new[n])]
    lines += [f"removed  {n}" for n in sorted(set(old) - set(new))]
    return lines


# ---------------------------------------------------------------------------
# Commands


def cmd_build(args, workspace):
    cfg = load_config(workspace, secrets=False)
    fmt = resolve_format(args.format, cfg, workspace)
    book = load_book(workspace, args.title)
    digest, chapters = source_digest(book, fmt), chapter_hashes(book)
    with locked_state(book.out_dir) as state:
        record_build(state, build(book, fmt), digest, chapters, book.out_dir)


def cmd_send(args, workspace):
    cfg = load_config(workspace, args.to)
    require_send_config(cfg)
    title = book_title(workspace, args.title)
    out_dir = content_dir(workspace) / "kindle-output"
    if args.file:
        path, fmt = args.file.resolve(), args.file.suffix.lower().lstrip(".")
        if fmt not in FORMATS:
            fail(f"{path.name} is not a .pdf or .epub file.")
    else:
        fmt = resolve_format(args.format, cfg, workspace)
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "book"
        path = out_dir / f"{slug}.{fmt}"
    if not path.is_file():
        fail(f"{path} not found. Run: kindle-sync build --format {fmt}")
    with locked_state(out_dir) as state:
        built = state.get("builds", {}).get(path.name) if path.parent == out_dir.resolve() else None
        before_submit(state, submission_key(cfg, path.name), args)
        submit(cfg, path, title, fmt, built["digest"] if built else file_digest(path),
               built.get("chapters") if built else None, state, out_dir)


def preview(args, cfg, workspace):
    fmt, reason = format_choice(args.format, cfg, workspace)
    book = load_book(workspace, args.title)
    name = f"{book.slug}.{fmt}"
    digest, chapters = source_digest(book, fmt), chapter_hashes(book)
    state = read_json(book.out_dir / STATE_FILE)
    key = submission_key(cfg, name)
    last = state.get("submissions", {}).get(key)
    pending = state.get("unknown", {}).get(key)
    dest = cfg["KINDLE_EMAIL"]
    print("Preview only: nothing is built, submitted, or recorded.")
    print(f"  Destination: {dest} (from {cfg.sources['KINDLE_EMAIL']})" if dest else "  Destination: not set")
    print(f"  Sender:      {cfg['SENDER_EMAIL'] or 'not set'} via {cfg.host}:{cfg['SMTP_PORT'] or 587}")
    print(f"  Book:        {name}, “{book.title}”, {len(book.chapters)} chapters, {fmt.upper()} ({reason})")
    if last:
        print(f"  Last submitted to this Kindle: {local_time(last['at'])}")
        changes = describe_changes(last["chapters"], chapters) if last.get("chapters") is not None else None
        if last["digest"] == digest:
            print("  Changes:     none")
        elif changes is None:
            print("  Changes:     can't list them; that copy was sent without a build record")
        elif changes:
            print("  Changes:")
            for line in changes:
                print(f"    {line}")
        else:
            print("  Changes:     same lessons; the title or the book layout changed")
    else:
        print("  Last submitted to this Kindle: never, from this workspace")

    problems = config_problems(cfg) + cfg.warnings
    if problems:
        decision = "would stop: Kindle delivery is not set up. Run `kindle-sync doctor` for details."
    elif last and last["digest"] == digest and not args.force:
        decision = "would skip: this Kindle already has these lessons (--force would send them again)."
    elif pending and not args.retry_unknown:
        decision = (f"would stop and ask: submitting to {pending['destination']} on {local_time(pending['at'])} "
                    "has an unknown outcome. See `kindle-sync status`.")
    else:
        decision = "would build the book and submit it."
    print(f"  Decision:    {decision}")
    if decision.startswith("would build") and last:
        print(RESEND_NOTE)


def cmd_sync(args, workspace):
    cfg = load_config(workspace, args.to)
    if args.dry_run:
        return preview(args, cfg, workspace)
    require_send_config(cfg)
    fmt = resolve_format(args.format, cfg, workspace)
    book = load_book(workspace, args.title)
    digest, chapters = source_digest(book, fmt), chapter_hashes(book)
    with locked_state(book.out_dir) as state:
        key = submission_key(cfg, f"{book.slug}.{fmt}")
        last = state.get("submissions", {}).get(key)
        if not args.force and last and last["digest"] == digest:
            print(f"✅ Nothing changed since this book was submitted to {cfg['KINDLE_EMAIL']} on "
                  f"{local_time(last['at'])}; skipping. Use --force to send it again.")
            return
        before_submit(state, key, args)
        out = build(book, fmt)
        record_build(state, out, digest, chapters, book.out_dir)
        submit(cfg, out, book.title, fmt, digest, chapters, state, book.out_dir)


def cmd_resolve(args, workspace):
    out_dir = content_dir(workspace) / "kindle-output"
    if not read_json(out_dir / STATE_FILE).get("unknown"):
        print("No submissions with an unknown outcome in this workspace.")
        return
    with locked_state(out_dir) as state:
        pending = state.get("unknown", {})
        for key, record in list(pending.items()):
            what = f"{record['file']} → {record['destination']} ({local_time(record['at'])})"
            if args.outcome == "sent":
                state.setdefault("submissions", {})[key] = dict(record, result="submitted", error=None)
                print(f"✅ Recorded {what} as submitted. `sync` won't send it again unless the lessons change.")
            else:
                print(f"✅ Cleared the warning for {what}. The next `kindle-sync sync` submits it normally.")
            del pending[key]
            add_history(state, record, result=f"resolved-{args.outcome}", error=None, at=now_iso())
        write_json(out_dir / STATE_FILE, state)


def ask(prompt, default="", check=None):
    while True:
        try:
            answer = input(prompt + (f" [{default}]" if default else "") + ": ").strip() or default
        except EOFError:
            fail("Setup needs answers. Run `kindle-sync setup` yourself in a terminal.")
        error = check(answer) if check else (None if answer else "This is required.")
        if not error:
            return answer
        print(f"   {error}")


def confirm(prompt):
    """Yes only on an explicit y; no answer (no terminal) means no."""
    try:
        return input(prompt + " [y/N]: ").strip().lower() in ("y", "yes")
    except (EOFError, OSError):
        return False


def cmd_test(args, workspace):
    cfg = load_config(workspace, args.to)
    if args.troubleshoot:
        print(troubleshooting(cfg))
        return
    require_send_config(cfg)
    if args.confirm:
        record_test(cfg, confirmed=True)
        print(f"✅ Recorded that test documents from {cfg['SENDER_EMAIL']} reach {cfg['KINDLE_EMAIL']}.")
        return
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    soup = BeautifulSoup(f"<body><h1>kindle-sync test</h1><p>Sent {stamp} from {html.escape(cfg['SENDER_EMAIL'])}. "
                         "If you can read this on your Kindle, delivery works.</p></body>", "html.parser")
    book = Book(workspace, f"kindle-sync test {stamp}", "en", [Chapter("ch01", "lesson", Path("test.html"), "kindle-sync test", soup.body)])
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "kindle-sync-test.epub"
        render_epub(book, path)
        try:
            deliver(cfg, path, book.title)
        except SubmitError as e:
            fail(e.message)
    record_test(cfg, confirmed=False)
    print_submitted(cfg, checks=False)
    if confirm("\nIt can take a few minutes. Has it arrived on your Kindle?"):
        record_test(cfg, confirmed=True)
        print("✅ Arrival confirmed by you. Run `kindle-sync sync` in a workspace to send your lessons.")
    else:
        print("\n" + troubleshooting(cfg))


def cmd_setup(args, workspace):
    target = workspace / ".kindle-creds" if args.workspace_config else user_config_dir() / "config"
    current = load_config(workspace)
    print("Set up Kindle delivery. kindle-sync emails books to your Send-to-Kindle address from your own mail account.\n"
          "It never needs your Amazon password, and it can't link to your Amazon account.\n")
    kindle = ask("Send-to-Kindle email (amazon.com/myk → Devices → your Kindle)", current["KINDLE_EMAIL"], email_error)
    if not kindle.lower().endswith(KINDLE_DOMAINS):
        print("   ⚠️  Send-to-Kindle addresses usually end in @kindle.com; double-check it.")
    sender = ask("Your email address (kindle-sync sends from it)", current["SENDER_EMAIL"], email_error)
    preset = SMTP_PRESETS.get(sender.rsplit("@", 1)[-1].lower(), ("", "587"))
    host = ask("SMTP server", current["SMTP_HOST"] or preset[0])
    port = ask("SMTP port (587 = STARTTLS, 465 = SSL)", current["SMTP_PORT"] or preset[1], port_error)
    user = ask("SMTP login", current["SMTP_USER"] or sender)
    keep = current["SMTP_PASSWORD"] if current.sources.get("SMTP_PASSWORD") != "environment variable" else ""
    print("\nCreate an app password for kindle-sync in your mail account (Gmail: myaccount.google.com/apppasswords,\n"
          "which needs 2-Step Verification). Your normal mail password usually won't work.")
    while True:
        try:
            password = getpass.getpass("App password (hidden" + ("; Enter keeps the saved one" if keep else "") + "): ")
        except EOFError:
            fail("Setup needs answers. Run `kindle-sync setup` yourself in a terminal.")
        password = password.strip() or keep
        if password:
            break
        print("   This is required.")
    fmt = ask("Book format: epub (reflowable, adjustable text) or pdf (fixed 4.5×6in pages)",
              current["FORMAT"].lower() or "epub", lambda v: None if v in FORMATS else "Enter epub or pdf.")

    print("\nAmazon only accepts documents from approved senders. kindle-sync can't do this step for you:\n"
          "  1. Open https://www.amazon.com/myk → Preferences → Personal Document Settings.\n"
          f"  2. Under Approved Personal Document E-mail List, add {sender}.\n"
          f"  3. Check that {kindle} is the Send-to-Kindle address of the device you want.")
    try:
        input("Press Enter once the sender is approved... ")
    except (EOFError, OSError):
        pass

    values = {"KINDLE_EMAIL": kindle, "SENDER_EMAIL": sender, "SMTP_HOST": host, "SMTP_PORT": port,
              "SMTP_USER": user, "FORMAT": fmt}
    backend, where = keyring_backend(), None
    if backend:
        try:
            backend.set_password(KEYRING_SERVICE, user, password)
            where = "your system keyring"
        except Exception as e:
            print(f"⚠️  Could not save to the system keyring ({type(e).__name__}); saving to {target} instead.")
    if not where:
        values["SMTP_PASSWORD"], where = password, f"{target} (readable only by you)"
    lines = ["# kindle-sync settings, written by `kindle-sync setup`. Environment variables override them."]
    write_atomic(target, "\n".join(lines + [f"{k}={v}" for k, v in values.items()]) + "\n", mode=0o600)
    os.chmod(target, 0o600)
    print(f"\n✅ Saved settings to {target}; the app password is in {where}.")

    saved = load_config(workspace)
    for key in CONFIG_KEYS:
        if saved.sources.get(key) not in (str(target), "system keyring", None):
            print(f"ℹ️  {key} still comes from {saved.sources[key]}, which takes precedence over {target}.")
    if confirm(f"\nCheck the login to {saved.host} now? It sends nothing."):
        try:
            smtp_login(saved).quit()
            print(f"✅ Logged in to {saved.host} as {saved.user}.")
        except SubmitError as e:
            print(f"❌ {e.message}\n   Fix it with `kindle-sync setup`, then check with `kindle-sync doctor --check-login`.")
            return
    if confirm(f"\nSend a small test document to {saved['KINDLE_EMAIL']} now?"):
        args.to, args.confirm, args.troubleshoot = None, False, False
        cmd_test(args, workspace)
    else:
        print("Send one later with `kindle-sync test`.")
    print("\nSee your setup progress any time with `kindle-sync status`.")


def smtp_account(path):
    values = pick(read_kv(path))
    return values.get("SMTP_USER") or values.get("SENDER_EMAIL")


def cmd_reset(args, workspace):
    if args.workspace_config:
        scope = [workspace / ".kindle-creds"]
    else:
        scope = [user_config_dir() / "config", Path.home() / ".kindle-creds"]
    files = [p for p in scope if p.is_file()]
    progress = [onboarding_path()] if not args.workspace_config and onboarding_path().is_file() else []
    # Keep a keyring password that another settings file still uses.
    in_use = {smtp_account(p) for p in config_files(workspace) if p not in scope and p.is_file()}
    backend, passwords = keyring_backend(), []
    for account in sorted({smtp_account(p) for p in files} - {None}):
        try:
            if backend and backend.get_password(KEYRING_SERVICE, account):
                if account in in_use:
                    print(f"ℹ️  Keeping the keyring password for {account}: another settings file uses it.")
                else:
                    passwords.append(account)
        except Exception:
            pass
    env = [n for n in CONFIG_KEYS + ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD") if os.environ.get(n)]

    if not (files or passwords or progress):
        print("No saved delivery settings to remove.")
    else:
        print("This removes:")
        for p in files:
            values = pick(read_kv(p))
            details = [f"{k}={values[k]}" for k in ("KINDLE_EMAIL", "SENDER_EMAIL") if values.get(k)]
            if values.get("SMTP_PASSWORD"):
                details.append("the app password")
            print(f"  - {p}" + (f": {', '.join(details)}" if details else ""))
        for account in passwords:
            print(f"  - the app password for {account} in your system keyring")
        for p in progress:
            print(f"  - your login and test-delivery progress in {p}")
        print("Submission history in your workspaces is kept, so unchanged books aren't sent again.")
        if not confirm("Delete these?"):
            print("Nothing was removed.")
            return
        for p in files + progress:
            p.unlink()
        for account in passwords:
            try:
                backend.delete_password(KEYRING_SERVICE, account)
            except Exception as e:
                print(f"⚠️  Could not remove the keyring password for {account} ({type(e).__name__}).")
        print("✅ Removed. Run `kindle-sync setup` to set up delivery again.")
    if env:
        print(f"ℹ️  These environment variables still set delivery settings; unset them yourself: {', '.join(env)}")


def cmd_doctor(args, workspace):
    cfg = load_config(workspace)
    errors = 0

    def report(level, text):
        nonlocal errors
        errors += level == "error"
        print({"ok": "✅", "warn": "⚠️ ", "error": "❌", "info": "ℹ️ "}[level], text)

    print("Settings files (highest precedence first, after environment variables):")
    for path in config_files(workspace):
        state = ("found, readable by other users" if too_open(path) else "found") if path.is_file() else "not found"
        print(f"   {path}: {state}")
    backend = keyring_backend()
    report("ok" if backend else "info", f"System keyring: {type(backend).__name__}" if backend
           else "System keyring: not available, so `kindle-sync setup` stores the password in a chmod 600 file")
    for key in ("KINDLE_EMAIL", "SENDER_EMAIL", "SMTP_USER", "SMTP_HOST", "SMTP_PORT"):
        if cfg[key]:
            report("ok", f"{key} = {cfg[key]} (from {cfg.sources[key]})")
    if cfg["SMTP_PASSWORD"]:
        report("ok", f"SMTP_PASSWORD is set (from {cfg.sources['SMTP_PASSWORD']})")
    problems = config_problems(cfg)
    for problem in problems:
        report("error", problem)
    for warning in cfg.warnings:
        report("warn", warning)
    if cfg["KINDLE_EMAIL"] and not cfg["KINDLE_EMAIL"].lower().endswith(KINDLE_DOMAINS):
        report("warn", "KINDLE_EMAIL doesn't end in @kindle.com; check it's your Send-to-Kindle address")
    domain = cfg["SENDER_EMAIL"].rsplit("@", 1)[-1].lower()
    if cfg["SENDER_EMAIL"] and not cfg["SMTP_HOST"] and domain not in ("gmail.com", "googlemail.com"):
        report("warn", f"SMTP_HOST is not set, so smtp.gmail.com is used for {cfg['SENDER_EMAIL']}")

    fmt, reason = format_choice(None, cfg, workspace)
    report("ok", f"Format: {fmt} ({reason})")
    try:
        import weasyprint  # noqa: F401
        report("ok", "PDF output: WeasyPrint is usable")
    except (ImportError, OSError) as e:
        report("error" if fmt == "pdf" else "info", f"PDF output: WeasyPrint is not usable ({e}); EPUB output still works")
    lessons = list(content_dir(workspace).glob("[0-9]*.html"))
    report("ok" if lessons else "warn", f"Workspace {workspace}: {len(lessons)} {content_dir(workspace).name}")
    for record in read_json(content_dir(workspace) / "kindle-output" / STATE_FILE).get("unknown", {}).values():
        report("warn", f"Outcome unknown for {record['file']} → {record['destination']} "
                       f"({local_time(record['at'])}); see `kindle-sync status`")

    if args.check_login and not problems:
        try:
            smtp_login(cfg).quit()
            report("ok", f"Logged in to {cfg.host} as {cfg.user}. This checks your mail account only, "
                         "not whether Amazon accepts the sender.")
        except SubmitError as e:
            report("error", e.message)
    elif not args.check_login:
        report("info", "Network not checked. `kindle-sync doctor --check-login` tests the login without sending; "
                       "`kindle-sync test` sends a test document.")
    if errors:
        raise SystemExit(1)


RESULT_LABELS = {
    "submitted": "submitted to the mail provider (Kindle delivery not confirmed)",
    "failed": "failed",
    "unknown": "OUTCOME UNKNOWN: check your Sent mail",
    "resolved-sent": "you found it in Sent mail; recorded as submitted",
    "resolved-not-sent": "you found it wasn't sent; warning cleared",
}


def cmd_status(args, workspace):
    cfg = load_config(workspace)
    state = read_json(content_dir(workspace) / "kindle-output" / STATE_FILE)
    for record in state.get("unknown", {}).values():
        print(f"⚠️  OUTCOME UNKNOWN: {record['file']} → {record['destination']} on {local_time(record['at'])}\n"
              "   The connection broke while submitting, so it may or may not have gone out, and `sync` won't\n"
              "   submit it again until you check. Look for it in your Sent mail, then run\n"
              "   `kindle-sync resolve sent` or `kindle-sync resolve not-sent`.\n")

    def show(key, empty="not set"):
        return f"{cfg[key]} (from {cfg.sources[key]})" if cfg[key] else empty

    fmt, reason = format_choice(None, cfg, workspace)
    print(f"Destination: {show('KINDLE_EMAIL', 'not set (run `kindle-sync setup`)')}")
    print(f"Sender:      {show('SENDER_EMAIL')}")
    print(f"Mail server: {cfg.host}:{cfg['SMTP_PORT'] or 587}, login {cfg.user or 'not set'}")
    print(f"Password:    {'set (from ' + cfg.sources['SMTP_PASSWORD'] + ')' if cfg['SMTP_PASSWORD'] else 'not set'}")
    print(f"Format:      {fmt} ({reason})")
    for warning in cfg.warnings:
        print(f"⚠️  {warning}")
    print("\nSetup progress:")
    for mark, text in onboarding_steps(cfg):
        print(f"  {mark} {text}")

    history = state.get("history", [])
    if not history:
        print("\nNo submissions from this workspace yet.")
        return
    print("\nRecent submissions, newest first:")
    for entry in reversed(history[-5:]):
        print(f"  {local_time(entry['at'])}  {entry['file']} ({entry['format']}) → {entry['destination']}: "
              f"{RESULT_LABELS.get(entry['result'], entry['result'])}")
        if entry.get("error"):
            print(f"      {entry['error']}")


def main(argv=None):
    workspace_arg = argparse.ArgumentParser(add_help=False)
    workspace_arg.add_argument("-w", "--workspace", type=Path, default=Path.cwd(), help="workspace root (default: current directory)")
    common = argparse.ArgumentParser(add_help=False, parents=[workspace_arg])
    common.add_argument("-f", "--format", choices=FORMATS, help="book format (default: FORMAT from setup, else epub)")
    common.add_argument("--title", help="book title (default: `# Book: <Title>` in BOOK.md or `# Mission: <Topic>` in MISSION.md, else the folder name)")
    to_arg = argparse.ArgumentParser(add_help=False)
    to_arg.add_argument("--to", metavar="EMAIL", help="send to this Kindle address instead of KINDLE_EMAIL")
    retry_arg = argparse.ArgumentParser(add_help=False)
    retry_arg.add_argument("--retry-unknown", action="store_true",
                           help="submit even though an earlier submission's outcome is unknown (may send a duplicate)")

    parser = argparse.ArgumentParser(prog="kindle-sync", description=__doc__.split("\n\n")[0].strip())
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build", parents=[common], help="build the book into lessons/kindle-output/")
    send_cmd = sub.add_parser("send", parents=[common, to_arg, retry_arg], help="email the built book to your Kindle")
    send_cmd.add_argument("file", nargs="?", type=Path, help="book to send (default: the built book for --format)")
    sync_cmd = sub.add_parser("sync", parents=[common, to_arg, retry_arg],
                              help="build, then send if lessons changed since the last submission")
    sync_cmd.add_argument("--force", action="store_true", help="send again even if nothing changed")
    sync_cmd.add_argument("--dry-run", action="store_true",
                          help="show the destination, format, changed lessons, and decision; build, send, and record nothing")
    setup_cmd = sub.add_parser("setup", parents=[workspace_arg], help="set up Kindle delivery interactively")
    setup_cmd.add_argument("--workspace-config", action="store_true",
                           help="save to <workspace>/.kindle-creds instead of your user settings")
    doctor_cmd = sub.add_parser("doctor", parents=[workspace_arg], help="check settings and dependencies")
    doctor_cmd.add_argument("--check-login", action="store_true", help="also log in to the mail server (sends nothing)")
    sub.add_parser("status", parents=[workspace_arg], help="show settings, setup progress, and recent submissions")
    test_cmd = sub.add_parser("test", parents=[workspace_arg, to_arg], help="send a small test document to your Kindle")
    test_cmd.add_argument("--confirm", action="store_true", help="record that the test document arrived (sends nothing)")
    test_cmd.add_argument("--troubleshoot", action="store_true", help="list what to check when it hasn't arrived (sends nothing)")
    resolve_cmd = sub.add_parser("resolve", parents=[workspace_arg],
                                 help="record whether a submission with an unknown outcome went out")
    resolve_cmd.add_argument("outcome", choices=["sent", "not-sent"],
                             help="sent: it is in your Sent mail; not-sent: it isn't, so sync may submit it again")
    reset_cmd = sub.add_parser("reset", parents=[workspace_arg],
                               help="delete saved delivery settings and the app password (asks first)")
    reset_cmd.add_argument("--workspace-config", action="store_true",
                           help="remove <workspace>/.kindle-creds instead of your user settings")
    args = parser.parse_args(argv)

    commands = {"build": cmd_build, "send": cmd_send, "sync": cmd_sync, "setup": cmd_setup, "doctor": cmd_doctor,
                "status": cmd_status, "test": cmd_test, "resolve": cmd_resolve, "reset": cmd_reset}
    commands[args.command](args, args.workspace.resolve())


if __name__ == "__main__":
    main()
