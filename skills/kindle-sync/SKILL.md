---
name: kindle-sync
description: Compiles a /teach learning workspace's lessons and reference docs into a Kindle book (EPUB or PDF) and emails it to the user's Kindle. Use when the user asks to sync, send, or export their lessons to Kindle, set up or troubleshoot Kindle delivery, or invokes /kindle-sync.
---

# Kindle Sync

Compile every `lessons/[0-9]*.html` and `reference/*.html` in a /teach workspace into one Kindle book and submit it by email to the user's Send-to-Kindle address.

If `kindle-sync` is not installed, run any command below as `uvx --from git+https://github.com/zura1555/kindle-sync kindle-sync <command>`.

## Instructions

1. From the workspace root, run:

   ```bash
   kindle-sync sync
   ```

2. If it fails with "Kindle delivery is not set up", ask the user to run `kindle-sync setup` themselves in a terminal. Setup asks for an app password with hidden input, so never collect credentials for them or write credential files. For any other failure, run `kindle-sync doctor` and relay what it reports.

   To show the user what would happen first, run `kindle-sync sync --dry-run`. It prints the destination, format, changed lessons, and the send or skip decision, and changes nothing.

3. Report the result honestly. Exit code 0 means the book was submitted to the user's mail provider, or skipped because this Kindle already has the current lessons. It does **not** mean the book reached the Kindle; kindle-sync can't see that. Say "submitted for delivery", not "delivered", and pass on the checks it prints when relevant. Any other exit code is a failure: report the `❌` message. It never contains credentials. If a resend is about to happen, pass on the note that the Kindle may keep a separate copy and that highlights and reading position may not carry over.

4. If a submission's outcome is unknown (the connection broke while sending), `sync` and `send` refuse to submit that book to that Kindle again. Ask the user to check their Sent mail, then run `kindle-sync resolve sent` or `kindle-sync resolve not-sent` according to their answer. Use `--retry-unknown` only when the user accepts a possible duplicate.

5. Useful options and commands:
   - `--format pdf` or `--format epub`: without it, the user's saved `FORMAT` is used, else EPUB. Workspaces that synced PDFs with older versions keep PDF.
   - `--force`: send again even though this Kindle already has the current lessons.
   - `--to EMAIL`: send to another Kindle address once.
   - `--title "..."`: override the book title. By default it comes from `# Mission: <Topic>` in `MISSION.md`.
   - `kindle-sync build` builds into `lessons/kindle-output/` without sending.
   - `kindle-sync status` shows where each setting comes from, setup progress (settings, login, test submitted, arrival confirmed), unknown outcomes, and recent submissions.
   - `kindle-sync doctor` checks settings and dependencies; `--check-login` logs in to the mail server without sending.
   - `kindle-sync test` sends a small test document. Run it only when the user asks for a test delivery. `kindle-sync test --troubleshoot` lists what to check when a test hasn't arrived and sends nothing.
   - `kindle-sync reset` deletes saved settings and the app password. It asks for confirmation in a terminal, so ask the user to run it themselves, and only when they want to remove their settings.

## Requirements

- Delivery settings from `kindle-sync setup`, or environment variables `KINDLE_EMAIL`, `SENDER_EMAIL`, `SMTP_PASSWORD`, and optionally `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `FORMAT`.
- The sender address must be approved in Amazon's Personal Document Settings. Only the user can do this.
- PDF output needs WeasyPrint's system libraries (Pango). EPUB output does not.

## Safety

- Never read, display, or expose `.kindle-creds`, `~/.config/kindle-sync/config`, keyring entries, or the credential environment variables.
- Never include credentials in messages, logs, or commits.
- Never send a test, resend with `--force`, or retry with `--retry-unknown` unless the user asked for it.
