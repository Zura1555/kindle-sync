# Learn Anything. Review Anywhere.

Two AI agent skills, one repo. **`/teach`** turns any topic into interactive HTML lessons. **`/kindle-sync`** compiles them into a Kindle book and sends it to your device.

Built for [Matt Pocock's skills-for-AI-agents](https://github.com/mattpocock/skills) framework. Drop these skill definitions into your agent, and it becomes your personal teacher — with offline Kindle review built in.

```
          /teach                          /kindle-sync
   ┌──────────────────┐            ┌──────────────────┐
   │  AI generates     │    →      │  Compile to PDF   │    →    📖 Kindle
   │  HTML lessons     │           │  Send via Gmail   │
   │  + references     │           │  ~5 min delivery  │
   └──────────────────┘            └──────────────────┘
```

---

## What's In This Repo

| Path | What |
|---|---|
| `skills/teach.md` | AI agent skill — generates lessons from any topic |
| `skills/kindle-sync.md` | AI agent skill — syncs lessons to Kindle |
| `sync_to_kindle.py` | Entry point — build PDF + send |
| `build_kindle.py` | Compiles `lessons/*.html` + `reference/*.html` into a Kindle-optimized PDF |
| `send_to_kindle.py` | Sends the PDF via Gmail SMTP |
| `workspace-template/` | Scaffolding — copy this to start a new learning project |
| `demo-workspace/` | Fully working example — a PostgreSQL lesson, ready to sync |

---

## Quick Start

### 1. Create a workspace

```bash
cp -r workspace-template ~/my-learning
cd ~/my-learning
```

### 2. Add the sync scripts

```bash
# From the kindle-sync repo:
cp sync_to_kindle.py ~/my-learning/lessons/
cp build_kindle.py ~/my-learning/lessons/
mkdir -p ~/my-learning/lessons/kindle-output
cp send_to_kindle.py ~/my-learning/lessons/kindle-output/
```

### 3. Install dependencies

```bash
pip install weasyprint

# WeasyPrint system deps:
# Ubuntu:  sudo apt install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev libcairo2
# macOS:   brew install pango libffi
```

### 4. Configure Kindle sync

```bash
cp .kindle-creds.example ~/my-learning/.kindle-creds
chmod 600 ~/my-learning/.kindle-creds
```

Fill in `~/my-learning/.kindle-creds`:
```ini
KINDLE_EMAIL=yourname@kindle.com
GMAIL_ADDRESS=yourname@gmail.com
GMAIL_APP_PASSWORD=abcd efgh ijkl mnop
```

- **Kindle email**: [amazon.com/myk](https://amazon.com/myk) → Devices → Kindle → Send-to-Kindle Email
- **App password**: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) (requires 2FA)
- **Approved sender**: Add your Gmail in Amazon's Kindle settings

### 5. Learn and sync

```bash
# Ask your AI agent:  /teach me PostgreSQL
# Agent generates lessons in lessons/

# Then sync to Kindle:
cd ~/my-learning
python3 lessons/sync_to_kindle.py
# Or tell your agent:  /kindle-sync
```

---

## How `/teach` Works

The agent creates a structured learning workspace:

```
my-learning/
├── MISSION.md           # Why you're learning this
├── RESOURCES.md         # Curated references
├── NOTES.md             # Preferences + scratchpad
├── .kindle-creds        # Kindle sync credentials (gitignored)
├── lessons/
│   ├── 0001-topic.html  # Self-contained, interactive HTML lessons
│   ├── 0002-topic.html  # Each: knowledge → quiz → primary source
│   ├── build_kindle.py
│   ├── sync_to_kindle.py
│   └── kindle-output/
│       └── send_to_kindle.py
├── reference/
│   └── glossary.html    # Cheat sheets, syntax guides, glossaries
└── learning-records/
    └── 0001-insight.md  # Key insights captured after each lesson
```

Lessons follow a proven pedagogy: teach knowledge first, practice skills through quizzes with immediate feedback, recommend a primary source, and encourage follow-up questions to the agent.

---

## How `/kindle-sync` Works

Three credentials, one data path:

```
build script → Gmail (app password) → Kindle email (Amazon) → your device
```

1. **Gmail App Password** — authenticates to SMTP without 2FA every time
2. **Kindle Email** — every Kindle has a unique `@kindle.com` address; Amazon receives the PDF and pushes it over Wi-Fi
3. **Approved Sender** — whitelist your Gmail in Amazon's Kindle settings so it's not rejected

The build script compiles all `lessons/0*.html` and `reference/*.html` into a single PDF with Kindle-optimized CSS (proper page breaks, readable fonts, print-friendly tables). Interactive JavaScript is stripped so quizzes render as static Q&A.

---

## Try The Demo

```bash
cd demo-workspace
ln -s ../.kindle-creds .kindle-creds    # Or set up your own
python3 lessons/build_kindle.py          # Build only (no send)
# Output: lessons/kindle-output/demo-workspace.pdf
```

---

## Requirements

| Component | Need |
|---|---|
| Python 3.9+ | Run the scripts |
| `weasyprint` | HTML → PDF rendering |
| `libpango`, `libcairo` | WeasyPrint system deps |
| Gmail + 2FA + App Password | SMTP authentication |
| Kindle + Send-to-Kindle Email | PDF delivery |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `❌ Missing credentials` | All three fields in `.kindle-creds` must be filled |
| `❌ Gmail rejected login` | App password wrong or 2FA not enabled |
| `❌ No PDF found` | Run `build_kindle.py` first |
| PDF doesn't appear | Kindle must be on Wi-Fi; sender must be approved in Amazon settings |
| `ModuleNotFoundError: weasyprint` | `pip install weasyprint` + system deps |

---

## Safety

- `.kindle-creds` is gitignored — never committed
- The skill definitions instruct agents to **never read or expose** credential contents
- `chmod 600` on `.kindle-creds` keeps it private on disk

---

## License

MIT — see [LICENSE](LICENSE).
