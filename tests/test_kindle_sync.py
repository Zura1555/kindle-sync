import shutil
import smtplib
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from pypdf import PdfReader

import kindle_sync

DEMO = Path(__file__).resolve().parent.parent / "demo-workspace"


@pytest.fixture
def demo(tmp_path):
    ws = tmp_path / "my-learning"
    shutil.copytree(DEMO, ws)
    return ws


def test_demo_pdf_has_quiz_answers_and_no_title_only_pages(demo):
    kindle_sync.main(["build", "-w", str(demo)])
    pages = [p.extract_text() for p in PdfReader(demo / "lessons/kindle-output/postgresql.pdf").pages]
    text = "\n".join(pages)

    # Title comes from MISSION.md, not the folder name; the cover has no page number.
    assert pages[0].split() == ["PostgreSQL"]
    # Contents lists each chapter once, by its heading, with a page number.
    assert "Lesson 0001" not in pages[1]
    assert "Naming" in pages[1] and any(ch.isdigit() for ch in pages[1])
    # Each chapter starts with its content, not on a page holding only its title.
    lesson_start = next(p for p in pages[2:] if "SQL Naming" in p)
    assert "Mission Connection" in lesson_start
    glossary_start = next(p for p in pages[2:] if "Glossary" in p)
    assert "camelCase" in glossary_start
    # Quiz options and the answer key survive without JavaScript.
    assert "A. UserProfiles" in text and "B. userprofiles" in text
    assert "Answer: B. userprofiles — Correct! PostgreSQL folds unquoted identifiers to lowercase." in " ".join(text.split())


def test_messy_lesson_epub(tmp_path):
    ws = tmp_path / "ws"
    (ws / "lessons").mkdir(parents=True)
    (ws / "lessons/0001-first-steps.html").write_text(
        """<html><head><style>p{}</style></head><body class="dark">
<p>Real content & more</p>
<script type="module">alert(1)</script>
<a href="./0002-next.html#top" onclick="go()">next</a>
<div class="quiz-block"><div class="q">Q1: Pick one?</div>
<div class="options"><button onclick="checkAnswer('q1', 1)">Wrong</button><button onclick="checkAnswer('q1', 2)">Right</button></div>
<div class="feedback" id="q1-fb"></div></div>
<script>const answers = { q1: { correct: 2, explanations: { 1: 'Nope.', 2: 'Yes, it\\'s right.' }} };</script>
</body></html>""",
        encoding="utf-8",
    )
    (ws / "lessons/0002-next.html").write_text(
        "<html><head><title>Next &amp; &lt;Last&gt;</title></head><body><p>Two</p></body></html>", encoding="utf-8"
    )
    kindle_sync.main(["build", "-w", str(ws), "-f", "epub"])

    with zipfile.ZipFile(ws / "lessons/kindle-output/ws.epub") as z:
        assert z.infolist()[0].filename == "mimetype"
        assert z.infolist()[0].compress_type == zipfile.ZIP_STORED
        docs = {n: z.read(n).decode() for n in z.namelist() if n.endswith((".xhtml", ".opf", ".xml"))}
    for name, doc in docs.items():
        ET.fromstring(doc.encode())  # every file is well-formed XML

    first, second = docs["OEBPS/ch01.xhtml"], docs["OEBPS/ch02.xhtml"]
    assert "Real content &amp; more" in first
    assert "alert" not in first and "onclick" not in first and "<button" not in first
    assert "<h1>First steps</h1>" in first
    assert 'href="ch02.xhtml"' in first
    assert "Answer: B. Right — Yes, it's right." in first
    assert "<h1>Next &amp; &lt;Last&gt;</h1>" in second
    assert "First steps" in docs["OEBPS/nav.xhtml"]


class FakeSMTP:
    sent = []
    fail_login = False

    def __init__(self, host, port, timeout=None):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        pass

    def login(self, user, password):
        if FakeSMTP.fail_login:
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


def test_sync_sends_once_and_fails_loudly(demo, monkeypatch, capsys):
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setenv("KINDLE_EMAIL", "me@kindle.com")
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")  # legacy names still work
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password-123")
    FakeSMTP.sent, FakeSMTP.fail_login = [], False
    args = ["sync", "-w", str(demo), "-f", "epub"]

    kindle_sync.main(args)
    kindle_sync.main(args)
    assert len(FakeSMTP.sent) == 1
    msg = FakeSMTP.sent[0]
    assert msg["To"] == "me@kindle.com"
    assert [a.get_filename() for a in msg.iter_attachments()] == ["postgresql.epub"]
    assert "skipping" in capsys.readouterr().out

    FakeSMTP.fail_login = True
    with pytest.raises(SystemExit) as exc:
        kindle_sync.main(args + ["--force"])
    assert exc.value.code not in (0, None)
    assert "app-password-123" not in str(exc.value.code)
