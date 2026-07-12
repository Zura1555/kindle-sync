# `kindle-sync` — A Skill for AI Agents

**`/teach` builds the lessons. `/kindle-sync` puts them in your pocket.**

A companion skill for [Matt Pocock's skills framework](https://github.com/mattpocock/skills). Compiles HTML lessons from any `/teach` learning workspace into a Kindle-optimized PDF and syncs it to your Kindle via email — so you can review on e-ink, anywhere, no laptop needed.

<p align="center">
  <em>(screenshot of Kindle output coming soon)</em>
</p>

---

## How It Works

```
Your /teach workspace          kindle-sync                  Your Kindle
┌──────────────────┐          ┌─────────────┐          ┌──────────────┐
│ lessons/         │    →     │ Compile PDF  │    →     │ 📖 "Learning  │
│  0001-*.html     │          │ (WeasyPrint) │          │  PostgreSQL"  │
│  0002-*.html     │          │              │          │              │
│  0003-*.html     │          │ Kindle-opt.  │          │ 5 min via    │
│ reference/       │          │ CSS + TOC    │          │ Gmail SMTP   │
└──────────────────┘          └─────────────┘          └──────────────┘
```

1. Your AI agent generates HTML lessons via `/teach`
2. You run `python3 lessons/sync_to_kindle.py` (or type `/kindle-sync` to the agent)
3. The PDF appears on your Kindle in ~5 minutes

---

## Quick Start

### Prerequisites

- **Kindle email address** — find it at [amazon.com/myk](https://amazon.com/myk) → Devices → Kindle → Send-to-Kindle Email
- **Gmail account** with 2FA enabled
- **Gmail app password** — generate at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
- **Approved sender** — add your Gmail to Amazon's Approved Personal Document Email List (same Amazon settings page)
- **Python 3.9+** with `weasyprint` (see requirements.txt)

### 1. Install

```bash
# Clone into your workspace
git clone https://github.com/YOUR_USERNAME/kindle-sync.git
cd kindle-sync

# Install Python deps
pip install -r requirements.txt

# WeasyPrint needs system libs too:
# Ubuntu/Debian:  sudo apt install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev libcairo2
# macOS:          brew install pango libffi
```

### 2. Configure Credentials

```bash
# From the repo root:
cp .kindle-creds.example .kindle-creds
chmod 600 .kindle-creds
```

Edit `.kindle-creds` with your details:
```ini
KINDLE_EMAIL=yourname@kindle.com
GMAIL_ADDRESS=yourname@gmail.com
GMAIL_APP_PASSWORD=abcd efgh ijkl mnop
```

> **Never commit `.kindle-creds`.** It's gitignored. Never share it. The AI agent skill is designed to never read or expose its contents.

### 3. Drop Scripts Into Your Workspace

Copy the three scripts into your `/teach` workspace:

```bash
# Assuming your workspace is ~/my-learning/
cp sync_to_kindle.py ~/my-learning/lessons/
cp build_kindle.py ~/my-learning/lessons/
cp send_to_kindle.py ~/my-learning/lessons/kindle-output/

# Also copy (or symlink) the .kindle-creds to workspace root:
ln -s $(pwd)/.kindle-creds ~/my-learning/.kindle-creds
```

### 4. Sync

```bash
cd ~/my-learning
python3 lessons/sync_to_kindle.py
```

Or ask your AI agent: **`/kindle-sync`**

---

## Try It With The Demo Workspace

This repo includes `demo-workspace/` — a minimal `/teach` workspace with one sample lesson.

```bash
# Set up the demo
cp sync_to_kindle.py demo-workspace/lessons/
cp build_kindle.py demo-workspace/lessons/
cp send_to_kindle.py demo-workspace/lessons/kindle-output/
ln -s $(pwd)/.kindle-creds demo-workspace/.kindle-creds

# Run it
cd demo-workspace
python3 lessons/sync_to_kindle.py
```

The demo produces `lessons/kindle-output/demo-workspace.pdf` with one lesson and one glossary.

---

## Skill Definition

The `skill.md` file defines how AI agents should handle `/kindle-sync`. It follows the [skills framework](https://github.com/mattpocock/skills) pattern. Drop it into your agent's skills directory.

**Key behaviors:**
- Runs `python3 lessons/sync_to_kindle.py` from workspace root
- Reports success/failure
- **Never reads or exposes `.kindle-creds` contents**

---

## Requirements

| Dependency | Purpose |
|---|---|
| `weasyprint` | HTML → PDF rendering |
| `libpango`, `libcairo` | System libs for WeasyPrint |
| Gmail SMTP access | Sending PDF to Kindle |
| Kindle email | Amazon's Send-to-Kindle service |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `❌ Missing credentials` | Fill in all three fields in `.kindle-creds` |
| `❌ Gmail rejected login` | App password is wrong or 2FA not enabled |
| `❌ No PDF found` | Run `python3 lessons/build_kindle.py` first |
| PDF doesn't appear on Kindle | Check Wi-Fi on Kindle; verify sender is approved in Amazon settings |
| Import error for `weasyprint` | `pip install weasyprint` + install system deps (see above) |

---

## Compatibility

Built for [Matt Pocock's skills-for-AI-agents](https://github.com/mattpocock/skills) framework. Works with any workspace that follows the pattern:

```
workspace/
├── MISSION.md
├── .kindle-creds
├── lessons/
│   ├── 0*.html
│   ├── sync_to_kindle.py
│   ├── build_kindle.py
│   └── kindle-output/
│       └── send_to_kindle.py
└── reference/
    └── *.html
```

## License

MIT — see [LICENSE](LICENSE).
