<p align="center">
  <img src="public/assets/logo.png" alt="Learn Anything. Review Anywhere." width="120">
</p>

# Learn Anything. Review Anywhere.

Two AI agent skills, one repo. **`/teach`** turns any topic into interactive HTML lessons. **`/kindle-sync`** compiles them into a Kindle book and delivers it to your device.

Built for [Matt Pocock's skills-for-AI-agents](https://github.com/mattpocock/skills) framework.

<p align="center">
  <img src="public/assets/demo.png" alt="Browser lesson on the left, Kindle PDF on the right" width="100%">
</p>


---

## What's Inside

| | |
|---|---|
| `skills/teach/SKILL.md` | Agent skill: generates interactive lessons |
| `skills/kindle-sync/SKILL.md` | Agent skill: syncs lessons to Kindle |
| `kindle_sync.py` | The `kindle-sync` CLI: builds the book (EPUB or PDF) and emails it |
| `workspace-template/` | Scaffolding: copy it to start learning anything |
| `demo-workspace/` | Working example: a PostgreSQL lesson, ready to sync |

---

## Quick Start

```bash
# 1. Install the CLI
uv tool install git+https://github.com/zura1555/kindle-sync   # or: pipx install git+https://github.com/zura1555/kindle-sync

# 2. Install the skills into your agent's skills directory
cp -r skills/teach skills/kindle-sync ~/.claude/skills/        # Claude Code
cp -r skills/teach skills/kindle-sync ~/.config/agents/skills/ # Amp

# 3. Scaffold a workspace
cp -r workspace-template ~/my-learning && cd ~/my-learning

# 4. Set up Kindle delivery (once per computer)
kindle-sync setup

# 5. Learn and send
/teach me PostgreSQL     # Agent generates lessons
kindle-sync sync         # Builds the book and submits it for delivery to your Kindle
```

### What `kindle-sync setup` does

kindle-sync emails the book to your Kindle's Send-to-Kindle address from your own mail account. It never asks for your Amazon password and can't link to your Amazon account. Setup asks for:

| | Where to find it |
|---|---|
| **Send-to-Kindle email** | [amazon.com/myk](https://amazon.com/myk) → Devices → your Kindle |
| **Your email address and its SMTP server** | Gmail, iCloud, Yahoo, and Fastmail are filled in for you |
| **An app password** | Typed hidden. Gmail: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) (needs 2-Step Verification) |
| **Book format** | EPUB (default) or PDF |

You must then approve your sender address yourself: [amazon.com/myk](https://amazon.com/myk) → Preferences → Personal Document Settings → Approved Personal Document E-mail List. Setup then offers to check your mail login (sends nothing) and to send a small test document. It never sends one unless you agree. `kindle-sync status` shows your progress through four steps: settings complete, mail login worked, test submitted, and arrival confirmed by you. If the test doesn't arrive, `kindle-sync test --troubleshoot` lists what to check, in order.

Settings go to `~/.config/kindle-sync/config` (`chmod 600`). The app password goes to your system keyring (macOS Keychain, Windows Credential Locker, or Secret Service) when one is available, and otherwise into that file. `kindle-sync setup --workspace-config` saves to `.kindle-creds` in the workspace instead, for a different Kindle or account per workspace.

For automation, set environment variables instead: `KINDLE_EMAIL`, `SENDER_EMAIL`, `SMTP_PASSWORD`, and optionally `SMTP_HOST`, `SMTP_PORT` (465 uses SSL, others STARTTLS), `SMTP_USER`, and `FORMAT`. Each setting comes from the first of: environment variables, the workspace `.kindle-creds`, `~/.config/kindle-sync/config` (password: then the keyring), and the legacy `~/.kindle-creds`. kindle-sync ignores a password in a file other users can read until you `chmod 600` it.

To see where each setting comes from, run `kindle-sync doctor` or `kindle-sync status`; neither shows the password. To change settings, run `kindle-sync setup` again. To remove them, run `kindle-sync reset` (or `reset --workspace-config`): it lists the files and keyring entries it will delete and deletes nothing until you answer yes.

---

## How It Works

`kindle-sync` compiles all `lessons/[0-9]*.html` and `reference/*.html` into one book in `lessons/kindle-output/`, then emails it to your Kindle.

| Command | |
|---|---|
| `kindle-sync setup` | Configure delivery interactively |
| `kindle-sync doctor` | Check settings, file permissions, and dependencies without showing secrets. `--check-login` also logs in to your mail server; it sends nothing |
| `kindle-sync test` | Send a small test document. `--confirm` records that it arrived; `--troubleshoot` lists what to check if it didn't |
| `kindle-sync build` | Build the book only |
| `kindle-sync send` | Email the built book |
| `kindle-sync sync` | Build, then send if the lessons changed since they were last submitted to this Kindle. `--force` sends anyway |
| `kindle-sync sync --dry-run` | Show the destination, format, changed lessons, and whether `sync` would send or skip. Builds, sends, and records nothing |
| `kindle-sync status` | Show settings and their sources, setup progress, and recent submissions |
| `kindle-sync resolve sent` / `not-sent` | Settle a submission whose outcome is unknown |
| `kindle-sync reset` | Delete saved settings and the app password, after asking |

- **Submitted is not delivered.** Success means your mail provider accepted the email. kindle-sync can't see whether Amazon accepted it or your Kindle downloaded it, so it says “Kindle delivery is not confirmed” and lists what to check: approved sender, an Amazon verification email, the right Send-to-Kindle address, and Wi-Fi. `status` shows a test as confirmed only after you confirm it with `kindle-sync test --confirm`.
- **What gets resent:** `sync` remembers each submission by Kindle address, sending account, and book file, in `lessons/kindle-output/.kindle-sync-state.json`. A new Kindle address gets the book even if nothing changed. `send` and `sync` share this record, and a failed submission is never recorded as sent. Concurrent syncs in one workspace wait for each other instead of sending twice. `--to EMAIL` sends to another Kindle once. Upgrading kindle-sync doesn't resend unchanged lessons; only a release that changes how books are built does.
- **Unknown outcomes:** if the connection breaks mid-submission, kindle-sync can't tell whether the email went out. `status` shows it at the top, and `sync` and `send` won't submit that book to that Kindle again until you check your Sent mail and run `kindle-sync resolve sent` or `resolve not-sent`. In a terminal they ask instead; `--retry-unknown` submits again anyway, accepting a possible duplicate.
- **Updates:** each send delivers a new copy of the whole book. Your Kindle may keep it as a separate document, and highlights, notes, and reading position from the earlier copy may not carry over. `sync` says so before it resends a book, and `--dry-run` shows it in advance.
- **Formats:** EPUB is the default: reflowable, so font size, dictionary, and highlights work on the Kindle. `--format pdf` (or `FORMAT=pdf` in setup) makes a 4.5×6in PDF with a clickable contents page; it needs Pango (Ubuntu: `sudo apt install libpango-1.0-0 libpangoft2-1.0-0`, macOS: `brew install pango`). Workspaces that synced PDFs before 0.3.0 keep PDF until you choose a format.
- **Title:** taken from `# Mission: <Topic>` in `MISSION.md`. Override it with `--title`.
- **Quizzes:** scripts are stripped, quiz options become a lettered list, and the answers move to an answer key at the end of each chapter, so you can still practise retrieval offline.

Lessons follow a structured pedagogy: knowledge first, an interactive quiz with immediate feedback, a primary source citation, and a reminder to ask the agent follow-up questions.

---

## Try the Demo

```bash
kindle-sync build --workspace demo-workspace
# → demo-workspace/lessons/kindle-output/postgresql.epub
```

---

## Development

```bash
pip install -e ".[test]" && pytest
```

---

## Safety

- Setup reads the app password with hidden input and stores it in the system keyring when available, otherwise in a `chmod 600` file outside the workspace
- kindle-sync refuses passwords from files other users can read, and never prints them
- Workspace `.kindle-creds` files are gitignored
- Skill definitions instruct agents to **never read or expose** credential contents, and to let users run `setup` themselves

---

MIT — see [LICENSE](LICENSE).
