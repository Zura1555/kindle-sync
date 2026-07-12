<p align="center">
  <!-- TODO: add your logo -->
  <img src="" alt="logo" width="120">
</p>

# Learn Anything. Review Anywhere.

Two AI agent skills, one repo. **`/teach`** turns any topic into interactive HTML lessons. **`/kindle-sync`** compiles them into a Kindle book and delivers it to your device.

Built for [Matt Pocock's skills-for-AI-agents](https://github.com/mattpocock/skills) framework.

<p align="center">
  <!-- TODO: add side-by-side screenshot (browser lesson + Kindle PDF) -->
  <img src="" alt="demo" width="100%">
</p>

```
   /teach                           /kindle-sync
   AI generates                  Compile PDF
   HTML lessons      ──→         Send via Gmail      ──→    📖 Kindle
   + references                  ~5 min delivery
```

---

## What's Inside

| | |
|---|---|
| `skills/teach.md` | Agent skill — generates interactive lessons |
| `skills/kindle-sync.md` | Agent skill — syncs lessons to Kindle |
| `workspace-template/` | Scaffolding — copy to start learning anything |
| `demo-workspace/` | Working example — PostgreSQL lesson, ready to sync |
| `sync_to_kindle.py` | Build PDF + send |
| `build_kindle.py` | Compile lessons → Kindle-optimized PDF |
| `send_to_kindle.py` | Deliver via Gmail SMTP |

---

## Quick Start

```bash
# 1. Scaffold a workspace
cp -r workspace-template ~/my-learning && cd ~/my-learning

# 2. Copy sync scripts
cp ../sync_to_kindle.py lessons/
cp ../build_kindle.py lessons/
mkdir -p lessons/kindle-output
cp ../send_to_kindle.py lessons/kindle-output/

# 3. Install
pip install weasyprint
# Ubuntu: sudo apt install libpango-1.0-0 libcairo2
# macOS:  brew install pango

# 4. Configure Kindle
cp ../.kindle-creds.example .kindle-creds && chmod 600 .kindle-creds
# Fill in: KINDLE_EMAIL, GMAIL_ADDRESS, GMAIL_APP_PASSWORD
```

You need three things:

| Credential | Where to get it |
|---|---|
| **Kindle email** | [amazon.com/myk](https://amazon.com/myk) → Devices → Kindle → Send-to-Kindle Email |
| **App password** | [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) (2FA required) |
| **Approved sender** | Add your Gmail in Amazon's Kindle settings |

```bash
# 5. Learn and sync
/teach me PostgreSQL         # Agent generates lessons
python3 lessons/sync_to_kindle.py   # → appears on Kindle in ~5 min
```

---

## How It Works

```
build script  →  Gmail (app password)  →  Kindle email (Amazon)  →  your device
```

The build script compiles all `lessons/0*.html` and `reference/*.html` into a single PDF with Kindle-optimized CSS (page breaks, readable fonts, stripped JavaScript). Amazon receives the email and pushes the PDF to your Kindle over Wi-Fi.

Lessons follow a structured pedagogy: knowledge first, interactive quiz with immediate feedback, primary source citation, and a reminder to ask the agent follow-up questions.

---

## Try the Demo

```bash
cd demo-workspace
ln -s ../.kindle-creds .kindle-creds
python3 lessons/build_kindle.py
# → lessons/kindle-output/demo-workspace.pdf
```

---

## Safety

- `.kindle-creds` is gitignored and `chmod 600` — never committed
- Skill definitions instruct agents to **never read or expose** credential contents

---

MIT — see [LICENSE](LICENSE).
