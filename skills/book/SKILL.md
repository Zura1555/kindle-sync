---
name: book
description: Writes a book chapter by chapter for the user to read on Kindle: plans an outline in BOOK.md, then writes one self-contained HTML chapter per session with SVG diagrams and optional AI-generated images, and compiles it with kindle-sync. Use when the user asks to write, plan, or continue a book, a long-form guide, or "the next chapter", or invokes /book. For short interactive lessons with quizzes, use /teach instead.
---

# Book

Grow a book over time in a book workspace. Each session plans the book or writes the next chapter; `kindle-sync` compiles the chapters written so far into one EPUB (or PDF) for the Kindle.

## Workspace

A book workspace is a folder with `BOOK.md` at its root. Start one by copying `book-template/` from this repository, or create the same files:

- `BOOK.md` — the plan and the single source of truth for the book. First line `# Book: <Title>`; kindle-sync uses `<Title>` as the book title. Sections: Reader, Promise, Style, Chapters, Notes.
- `chapters/NN-<dash-case-name>.html` — one self-contained HTML file per chapter, such as `chapters/03-how-indexes-work.html`. The number orders the book.
- `assets/` — images the chapters show. `assets/cover.png` (or `.jpg`), if present, becomes the book cover.
- `reference/*.html` — optional appendices (glossary, cheat sheet), placed after the chapters.
- `RESOURCES.md` — sources the book draws on.

kindle-sync and the site builder detect `BOOK.md` and read `chapters/` instead of `lessons/`. Output goes to `chapters/kindle-output/`.

## Planning (first session, or when the user changes direction)

1. Ask who the reader is, what they already know, and what they should be able to do after the book, unless the user already said.
2. Write `BOOK.md`. Under `## Chapters`, one line per chapter: `- [ ] 01. <Title> — <one-line goal>`. Aim for chapters that each take 15–30 minutes to read and build on the ones before.
3. Show the outline and ask for changes before writing chapters.

## Writing a chapter

Write one chapter per request unless the user asks for more.

1. Read `BOOK.md`, including Notes, and the previous chapter, so terms, examples, and tone stay consistent.
2. Write the next unchecked chapter from the outline, or the one the user names.
3. Tick it in `BOOK.md` (`- [x]`) and add to Notes any term you defined, running example you introduced, or promise you made for a later chapter.
4. Build it with `kindle-sync build` and fix any `⚠️` warning it prints. Send it with `kindle-sync sync` only when the user asks; follow the kindle-sync skill for delivery.

### Chapter HTML

kindle-sync keeps the chapter body and drops `<head>`, `<style>`, `<script>`, `<link>`, event handlers, and buttons, then applies its own e-ink stylesheet. So:

- Put all meaning in the markup. Use `<h1>` once for the chapter title (it becomes the contents entry), `<h2>`/`<h3>` for sections, `<p>`, lists, `<table>`, `<pre><code>`, `<blockquote>`.
- Callouts that survive on Kindle: `<div class="key-insight">`, `<div class="warn">`, `<div class="reminder">`.
- Embedded CSS is fine for the browser, but never rely on color, hover, or layout for meaning: the Kindle shows grayscale with its own styles. Do not load web fonts or other network resources.
- Link other chapters by file name (`<a href="02-setup.html">`); kindle-sync rewrites those links to point inside the book.
- End each chapter with a short summary and, optionally, two or three review questions. For questions with answers, use the /teach quiz markup (`.quiz-block`, `.q`, `.options`, `button.opt` with `data-correct` and `data-explain`); kindle-sync turns them into a lettered list and an answer key at the end of the chapter.

## Visuals

Add a visual where it explains something faster than prose: a structure, a flow, a comparison, a timeline. Wrap each in a `<figure>` with a `<figcaption>`.

**Diagrams: inline SVG by default.** Write `<svg viewBox="0 0 W H" width="100%">` directly in the chapter. SVG stays crisp on e-ink, needs no files, and works in EPUB, PDF, and the browser. Use black, white, and grays with strokes at least 1.5 units wide, `font-family="Georgia, serif"`, and text no smaller than about 1/30 of the width. Tables and plain HTML lists are better than a diagram for tabular facts.

**Illustrations: AI-generated images, when a picture helps** (a scene, a metaphor, a cover), not for anything a diagram can show exactly. If you have an image generation tool (in Amp, `painter`):

1. Ask for a grayscale-friendly, high-contrast image with no small text, since the Kindle shows grayscale.
2. Save it into the workspace: `amp files get <attachment-url> -o assets/<chapter-number>-<name>.png` in Amp, or copy the generated file there.
3. Reference it relative to the chapter: `<figure><img src="../assets/03-index-card-catalog.png" alt="A librarian searching a card catalog"><figcaption>An index works like a card catalog.</figcaption></figure>`. Always write a descriptive `alt`.

For the cover, save the image as `assets/cover.png`, portrait (about 1600×2560).

Images must be PNG, JPEG, GIF, WebP, or SVG files inside the workspace. kindle-sync embeds them in both EPUB and PDF and resends the book when one changes. A remote URL or missing file is replaced by its alt text with a `⚠️` warning, because books are built offline.

## Gotchas

- Do not put chapters in `lessons/` in a book workspace; with `BOOK.md` present, only `chapters/[0-9]*.html` are compiled.
- `src="../assets/x.png"` is correct from `chapters/`; `src="assets/x.png"` points at a nonexistent `chapters/assets/` and the image is dropped.
- Never read or expose Kindle credentials; see the kindle-sync skill.
