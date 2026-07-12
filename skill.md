# Kindle Sync

## Description
Compile all HTML lessons from a /teach learning workspace into a Kindle-optimized PDF and send it to the user's Kindle via email.

## Usage
Invoke with `/kindle-sync` or trigger manually by running the sync script.

## Instructions
When activated:

1. Run `python3 lessons/sync_to_kindle.py` from the workspace root.
2. The script will:
   - Compile all `lessons/0*.html` and `reference/*.html` into a single PDF
   - Send the PDF to the Kindle email address configured in `.kindle-creds`
3. Report success or failure to the user. If it fails, report the non-sensitive parts of the error output.

## Requirements
- `.kindle-creds` must exist at the workspace root with `KINDLE_EMAIL`, `GMAIL_ADDRESS`, and `GMAIL_APP_PASSWORD`.
- The Gmail account must have 2FA enabled and an app password generated.
- The sender Gmail must be approved in Amazon's Kindle Personal Documents settings.
- `weasyprint` and its system dependencies must be installed.

## Safety
- Never read, display, or expose the contents of `.kindle-creds`.
- Never include credentials in error messages or logs.
- The `.kindle-creds` file should be `chmod 600` and gitignored.
