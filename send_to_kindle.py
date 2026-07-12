#!/usr/bin/env python3
"""
Send the compiled PDF to Kindle via Gmail SMTP.
Reads credentials from .kindle-creds at the workspace root.

Drop this into your /teach workspace's lessons/kindle-output/ directory.
"""
import smtplib
import sys
import os
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
CREDS_FILE = BASE / ".kindle-creds"
OUTPUT_DIR = Path(__file__).resolve().parent

# Find the PDF — supports any workspace name
pdf_files = sorted(OUTPUT_DIR.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
if not pdf_files:
    print("❌ No PDF found in kindle-output/")
    print("   Run: python3 lessons/build_kindle.py")
    sys.exit(1)
PDF_PATH = pdf_files[0]

# Load credentials
creds = {}
if CREDS_FILE.exists():
    with open(CREDS_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                creds[k.strip()] = v.strip()

KINDLE_EMAIL = creds.get("KINDLE_EMAIL", "")
GMAIL_ADDRESS = creds.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = creds.get("GMAIL_APP_PASSWORD", "")

# Validate
missing = []
if not KINDLE_EMAIL:
    missing.append("KINDLE_EMAIL")
if not GMAIL_ADDRESS:
    missing.append("GMAIL_ADDRESS")
if not GMAIL_APP_PASSWORD or len(GMAIL_APP_PASSWORD) < 10:
    missing.append("GMAIL_APP_PASSWORD")

if missing:
    print(f"❌ Missing or invalid credentials: {', '.join(missing)}")
    print(f"   Edit: {CREDS_FILE}")
    print("   Then: chmod 600 .kindle-creds")
    print()
    print("   KINDLE_EMAIL:   amazon.com/myk → Devices → Kindle → Send-to-Kindle Email")
    print("   GMAIL_ADDRESS:  Your Gmail (add as approved sender in Amazon Kindle settings)")
    print("   GMAIL_APP_PASSWORD: myaccount.google.com/apppasswords (requires 2FA)")
    sys.exit(1)

BOOK_TITLE = BASE.resolve().name.replace("-", " ").replace("_", " ").title()

print(f"📧 Sending {PDF_PATH.name} ({PDF_PATH.stat().st_size / 1024:.0f} KB) to {KINDLE_EMAIL}...")

msg = MIMEMultipart()
msg["From"] = GMAIL_ADDRESS
msg["To"] = KINDLE_EMAIL
msg["Subject"] = BOOK_TITLE

with open(PDF_PATH, "rb") as f:
    part = MIMEBase("application", "octet-stream")
    part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{PDF_PATH.name}"')
    msg.attach(part)

msg.attach(MIMEText(f"Updated {BOOK_TITLE} learning materials.", "plain"))

try:
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)
    print("✅ Sent! Appears on your Kindle in 1-5 minutes (Wi-Fi).")
except smtplib.SMTPAuthenticationError:
    print("❌ Gmail rejected login. Check GMAIL_ADDRESS and GMAIL_APP_PASSWORD.")
    print("   App passwords require 2FA enabled: myaccount.google.com/apppasswords")
except Exception as e:
    print(f"❌ Failed: {e}")
