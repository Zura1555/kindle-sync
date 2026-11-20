---
name: kindle-sync
description: Compiles a /teach learning workspace's lessons and reference docs into a Kindle book (PDF or EPUB) and emails it to the user's Kindle. Use when the user asks to sync, send, or export their lessons to Kindle, or invokes /kindle-sync.
---

# Kindle Sync

Compile every `lessons/[0-9]*.html` and `reference/*.html` in a /teach workspace into one Kindle book and send it to the user's Kindle by email.

## Instructions

1. From the workspace root, run:

   ```bash
   kindle-sync sync
   ```

   If `kindle-sync` is not installed, run it without installing:

   ```bash
   uvx --from git+https://github.com/zura1555/kindle-sync kindle-sync sync
   ```

2. Useful options:
   - `--format epub`: send a reflowable EPUB instead of the 4.5×6in PDF. Use it when the user wants adjustable font size or Kindle highlights.
   - `--force`: send again even though no lesson changed since the last send. Without it, `sync` skips sending unchanged lessons.
   - `--title "..."`: override the book title. By default it comes from `# Mission: <Topic>` in `MISSION.md`.
   - `kindle-sync build` builds into `lessons/kindle-output/` without sending.

3. Exit code 0 means the book was sent, or skipped because nothing changed. Any other exit code is a failure: report the `❌` message to the user. It never contains credentials.

## Requirements

- Credentials in environment variables, `.kindle-creds` at the workspace root, or `~/.kindle-creds`: `KINDLE_EMAIL`, `SENDER_EMAIL`, `SMTP_PASSWORD`, and optionally `SMTP_HOST`, `SMTP_PORT`, and `SMTP_USER` (defaults: Gmail on port 587). If they are missing, tell the user to copy `.kindle-creds.example` from the kindle-sync repository and fill it in themselves.
- The sender address must be approved in Amazon's Personal Document Settings.
- PDF output needs WeasyPrint's system libraries (Pango). EPUB output does not.

## Safety

- Never read, display, or expose the contents of `.kindle-creds` or the credential environment variables.
- Never include credentials in messages, logs, or commits. `.kindle-creds` should be `chmod 600` and gitignored.
