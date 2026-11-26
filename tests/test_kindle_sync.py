import getpass
import shutil
import smtplib
import stat
import threading
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from pypdf import PdfReader

import kindle_sync

DEMO = Path(__file__).resolve().parent.parent / "demo-workspace"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """No real settings, keyring, or mail server: every test gets its own home and a fake transport."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    for name in kindle_sync.CONFIG_KEYS + ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(kindle_sync, "keyring_backend", lambda: None)
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    FakeSMTP.reset()
    return home


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv("KINDLE_EMAIL", "me@kindle.com")
    monkeypatch.setenv("SENDER_EMAIL", "me@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password-123")


@pytest.fixture
def demo(tmp_path):
    ws = tmp_path / "my-learning"
    shutil.copytree(DEMO, ws)
    return ws


def test_demo_pdf_has_quiz_answers_and_no_title_only_pages(demo):
    kindle_sync.main(["build", "-w", str(demo), "-f", "pdf"])
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
    send_error = None
    delay = 0

    @classmethod
    def reset(cls):
        cls.sent, cls.fail_login, cls.send_error, cls.delay = [], False, None, 0

    def __init__(self, host, port, timeout=None, context=None):
        self.host = host

    def starttls(self, context=None):
        pass

    def login(self, user, password):
        if FakeSMTP.fail_login:
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    def send_message(self, msg):
        time.sleep(FakeSMTP.delay)
        if FakeSMTP.send_error:
            raise FakeSMTP.send_error
        FakeSMTP.sent.append(msg)

    def quit(self):
        pass

    def close(self):
        pass


def sync(ws, *extra):
    kindle_sync.main(["sync", "-w", str(ws), *extra])


def destinations():
    return [m["To"] for m in FakeSMTP.sent]


def test_sync_sends_once_and_fails_loudly(demo, monkeypatch, capsys):
    monkeypatch.setenv("KINDLE_EMAIL", "me@kindle.com")
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")  # legacy names still work
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password-123")
    args = ["sync", "-w", str(demo), "-f", "epub"]

    kindle_sync.main(args)
    kindle_sync.main(args)
    assert len(FakeSMTP.sent) == 1
    msg = FakeSMTP.sent[0]
    assert msg["To"] == "me@kindle.com"
    assert [a.get_filename() for a in msg.iter_attachments()] == ["postgresql.epub"]
    out = capsys.readouterr().out
    assert "skipping" in out
    # SMTP acceptance is reported as a submission, never as a delivery.
    assert "Kindle delivery is not confirmed" in out and "Sent!" not in out

    FakeSMTP.fail_login = True
    with pytest.raises(SystemExit) as exc:
        kindle_sync.main(args + ["--force"])
    assert exc.value.code not in (0, None)
    assert "Authentication rejected" in str(exc.value.code)
    assert "app-password-123" not in str(exc.value.code)


def test_changing_destination_sends_unchanged_book(demo, creds, monkeypatch):
    sync(demo)
    sync(demo)
    monkeypatch.setenv("KINDLE_EMAIL", "partner@kindle.com")
    sync(demo)
    sync(demo, "--to", "me@kindle.com")  # back to the first Kindle: already has this content
    assert destinations() == ["me@kindle.com", "partner@kindle.com"]


def test_send_and_sync_share_bookkeeping(demo, creds):
    kindle_sync.main(["build", "-w", str(demo)])
    kindle_sync.main(["send", "-w", str(demo)])
    sync(demo)  # the built book was already submitted to this Kindle
    assert len(FakeSMTP.sent) == 1
    (demo / "lessons/0001-sample-lesson.html").write_text("<h1>Changed</h1><p>New content</p>", encoding="utf-8")
    sync(demo)
    assert len(FakeSMTP.sent) == 2


def test_failed_submission_is_not_marked_sent(demo, creds, capsys):
    FakeSMTP.send_error = smtplib.SMTPRecipientsRefused({"me@kindle.com": (550, b"no")})
    with pytest.raises(SystemExit) as exc:
        sync(demo)
    assert "Recipient refused" in str(exc.value.code)
    FakeSMTP.send_error = None
    sync(demo)
    assert len(FakeSMTP.sent) == 1

    capsys.readouterr()
    kindle_sync.main(["status", "-w", str(demo)])
    out = capsys.readouterr().out
    assert "submitted to the mail provider (Kindle delivery not confirmed)" in out and ": failed" in out
    assert "app-password-123" not in out


def break_connection_during_sync(demo):
    FakeSMTP.send_error = smtplib.SMTPServerDisconnected("Connection unexpectedly closed")
    with pytest.raises(SystemExit) as exc:
        sync(demo)
    assert "may or may not have accepted" in str(exc.value.code)
    FakeSMTP.send_error = None


def test_unknown_outcome_blocks_a_duplicate_until_resolved(demo, creds, capsys):
    break_connection_during_sync(demo)
    capsys.readouterr()
    kindle_sync.main(["status", "-w", str(demo)])
    assert capsys.readouterr().out.startswith("⚠️  OUTCOME UNKNOWN: postgresql.epub → me@kindle.com")

    with pytest.raises(SystemExit) as exc:
        sync(demo)  # no terminal to ask, so it refuses rather than risk a second copy
    assert "Not submitted" in str(exc.value.code) and "kindle-sync resolve sent" in str(exc.value.code)
    with pytest.raises(SystemExit):
        sync(demo, "--force")  # --force means "content unchanged is fine", not "duplicates are fine"
    assert FakeSMTP.sent == []

    kindle_sync.main(["resolve", "sent", "-w", str(demo)])
    sync(demo)  # recorded as submitted, so unchanged lessons are skipped
    assert FakeSMTP.sent == []
    kindle_sync.main(["status", "-w", str(demo)])
    out = capsys.readouterr().out
    assert "OUTCOME UNKNOWN: postgresql" not in out and "you found it in Sent mail" in out


@pytest.mark.parametrize("how", [["resolve", "not-sent"], ["sync", "--retry-unknown"]])
def test_unknown_outcome_can_be_cleared_or_retried(demo, creds, how):
    break_connection_during_sync(demo)
    kindle_sync.main([*how, "-w", str(demo)])
    sync(demo)
    assert len(FakeSMTP.sent) == 1
    state = kindle_sync.read_json(demo / "lessons/kindle-output" / kindle_sync.STATE_FILE)
    assert state["unknown"] == {}


def test_release_version_alone_does_not_resend(demo, creds, monkeypatch, capsys):
    sync(demo)
    monkeypatch.setattr(kindle_sync, "__version__", "99.0.0")
    sync(demo)
    assert len(FakeSMTP.sent) == 1
    capsys.readouterr()
    monkeypatch.setattr(kindle_sync, "RENDER_VERSION", kindle_sync.RENDER_VERSION + 1)
    sync(demo)  # the book itself changed, so it is resent, with the caveats explained first
    assert len(FakeSMTP.sent) == 2
    out = capsys.readouterr().out
    assert out.index("separate document") < out.index("Submitting")


def test_dry_run_previews_without_side_effects(demo, creds, capsys):
    sync(demo)
    out_dir = demo / "lessons/kindle-output"
    before = {p.name: p.read_bytes() for p in out_dir.iterdir()}
    (demo / "lessons/0001-sample-lesson.html").write_text("<h1>Changed</h1>", encoding="utf-8")
    (demo / "lessons/0002-new.html").write_text("<h1>New</h1>", encoding="utf-8")
    capsys.readouterr()

    sync(demo, "--dry-run")
    out = capsys.readouterr().out
    assert "Destination: me@kindle.com (from environment variable)" in out
    assert "postgresql.epub" in out and "EPUB (default)" in out
    assert "added    lessons/0002-new.html" in out and "changed  lessons/0001-sample-lesson.html" in out
    assert "reference/" not in out  # unchanged files aren't listed
    assert "Decision:    would build the book and submit it." in out and "separate document" in out

    sync(demo, "--dry-run", "--to", "other@kindle.com")
    out = capsys.readouterr().out
    assert "Last submitted to this Kindle: never" in out and "would build" in out

    assert len(FakeSMTP.sent) == 1
    assert {p.name: p.read_bytes() for p in out_dir.iterdir()} == before

    (demo / "lessons/0002-new.html").unlink()
    sync(demo)
    sync(demo, "--dry-run")
    assert "would skip" in capsys.readouterr().out


def test_dry_run_reports_missing_settings_and_unknown_outcomes(demo, creds, monkeypatch, capsys):
    break_connection_during_sync(demo)
    capsys.readouterr()
    sync(demo, "--dry-run")
    assert "would stop and ask" in capsys.readouterr().out
    monkeypatch.delenv("SMTP_PASSWORD")
    sync(demo, "--dry-run")
    assert "would stop: Kindle delivery is not set up" in capsys.readouterr().out


def test_concurrent_syncs_submit_once(demo, creds):
    FakeSMTP.delay = 0.5
    threads = [threading.Thread(target=sync, args=(demo,)) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(FakeSMTP.sent) == 1


def attachment_names():
    return [a.get_filename() for m in FakeSMTP.sent for a in m.iter_attachments()]


def test_epub_is_the_default_but_pdf_preferences_are_kept(demo, creds, monkeypatch, tmp_path, capsys):
    sync(demo)
    assert attachment_names() == ["postgresql.epub"]

    # A workspace that synced PDFs with an older version keeps PDF, and says why.
    old = tmp_path / "old"
    shutil.copytree(DEMO, old)
    (old / "lessons/kindle-output").mkdir()
    (old / "lessons/kindle-output/.last-sent-pdf").write_text("old-digest\n")
    sync(old)
    assert attachment_names()[-1] == "postgresql.pdf"
    assert "Using PDF" in capsys.readouterr().out

    # A saved FORMAT wins over both.
    monkeypatch.setenv("FORMAT", "epub")
    sync(old)
    assert attachment_names()[-1] == "postgresql.epub"


def test_insecure_creds_file_is_refused_before_building(demo, monkeypatch):
    creds_file = demo / ".kindle-creds"
    creds_file.write_text("KINDLE_EMAIL=me@kindle.com\nSENDER_EMAIL=me@gmail.com\nSMTP_PASSWORD=app-password-123\n")
    creds_file.chmod(0o644)
    with pytest.raises(SystemExit) as exc:
        sync(demo)
    message = str(exc.value.code)
    assert f"chmod 600 {creds_file}" in message and "app-password-123" not in message
    assert not (demo / "lessons/kindle-output/postgresql.epub").exists()

    creds_file.chmod(0o600)
    sync(demo)
    assert len(FakeSMTP.sent) == 1


class FakeKeyring:
    priority = 1

    def __init__(self):
        self.store = {}

    def get_password(self, service, user):
        return self.store.get((service, user))

    def set_password(self, service, user, password):
        self.store[(service, user)] = password

    def delete_password(self, service, user):
        del self.store[(service, user)]


def run_setup(monkeypatch, answers, password, *args):
    answers = iter(answers)

    def fake_input(prompt=""):
        assert "password" not in prompt.lower()  # secrets only go through hidden input
        return next(answers)

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": password)
    kindle_sync.main(["setup", *args])


# Kindle, sender, default host, port, login, and format, Enter at the Amazon step, no login check, no test.
SETUP_ANSWERS = ["me@kindle.com", "me@gmail.com", "", "", "", "", "", "n", "n"]


@pytest.mark.parametrize("with_keyring", [True, False])
def test_setup_saves_settings_and_hides_the_password(demo, isolated, monkeypatch, with_keyring):
    keyring = FakeKeyring()
    if with_keyring:
        monkeypatch.setattr(kindle_sync, "keyring_backend", lambda: keyring)
    run_setup(monkeypatch, SETUP_ANSWERS, "app-password-123", "-w", str(demo))

    config = isolated / ".config/kindle-sync/config"
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    text = config.read_text()
    assert "KINDLE_EMAIL=me@kindle.com" in text and "SMTP_HOST=smtp.gmail.com" in text and "FORMAT=epub" in text
    assert ("app-password-123" in text) != with_keyring
    if with_keyring:
        assert keyring.store == {("kindle-sync", "me@gmail.com"): "app-password-123"}

    sync(demo)  # works with no environment variables
    assert destinations() == ["me@kindle.com"]


def status_out(ws, capsys):
    capsys.readouterr()
    kindle_sync.main(["status", "-w", str(ws)])
    return capsys.readouterr().out


def test_setup_progress_login_test_and_arrival(demo, isolated, monkeypatch, capsys):
    run_setup(monkeypatch, SETUP_ANSWERS, "app-password-123", "-w", str(demo))
    out = status_out(demo, capsys)
    assert "✅ Settings are complete" in out and "⬜ Mail login not checked yet" in out
    assert "⬜ No test document yet" in out

    # Login check and test are opt-in; a test that hasn't arrived gets troubleshooting steps.
    run_setup(monkeypatch, SETUP_ANSWERS[:-2] + ["y", "y", "n"], "app-password-123", "-w", str(demo))
    assert len(FakeSMTP.sent) == 1 and FakeSMTP.sent[0]["Subject"].startswith("kindle-sync test")
    out = capsys.readouterr().out
    assert "Logged in to smtp.gmail.com" in out and "Approved Personal" in out and "Content → Docs" in out
    out = status_out(demo, capsys)
    assert "✅ Mail login worked" in out and "✅ Test document submitted" in out
    assert "⬜ Arrival not confirmed. Once the test is on your Kindle" in out

    kindle_sync.main(["test", "-w", str(demo), "--confirm"])
    assert "✅ You confirmed the test arrived" in status_out(demo, capsys)
    assert len(FakeSMTP.sent) == 1


def test_failed_login_shows_in_setup_progress(demo, creds, capsys):
    FakeSMTP.fail_login = True
    with pytest.raises(SystemExit):
        kindle_sync.main(["doctor", "-w", str(demo), "--check-login"])
    assert "❌ The last mail login" in status_out(demo, capsys)


def run_reset(monkeypatch, answer, *args):
    def fake_input(prompt=""):
        if answer is None:
            raise EOFError
        return answer
    monkeypatch.setattr("builtins.input", fake_input)
    kindle_sync.main(["reset", *args])


def test_reset_lists_and_asks_before_deleting_credentials(demo, isolated, monkeypatch, capsys):
    keyring = FakeKeyring()
    monkeypatch.setattr(kindle_sync, "keyring_backend", lambda: keyring)
    run_setup(monkeypatch, SETUP_ANSWERS[:-2] + ["y", "n"], "app-password-123", "-w", str(demo))
    config = isolated / ".config/kindle-sync/config"
    capsys.readouterr()

    for answer in ("n", None):  # declined, and no terminal to ask
        run_reset(monkeypatch, answer, "-w", str(demo))
        out = capsys.readouterr().out
        assert str(config) in out and "app password for me@gmail.com in your system keyring" in out
        assert "app-password-123" not in out and "Nothing was removed." in out
        assert config.exists() and keyring.store

    run_reset(monkeypatch, "y", "-w", str(demo))
    assert not config.exists() and keyring.store == {}
    assert not (isolated / ".config/kindle-sync/onboarding.json").exists()
    with pytest.raises(SystemExit) as exc:
        sync(demo)
    assert "not set up" in str(exc.value.code)


def test_workspace_reset_keeps_a_password_the_user_config_still_uses(demo, isolated, monkeypatch, capsys):
    keyring = FakeKeyring()
    monkeypatch.setattr(kindle_sync, "keyring_backend", lambda: keyring)
    run_setup(monkeypatch, SETUP_ANSWERS, "app-password-123", "-w", str(demo))
    run_setup(monkeypatch, ["other@kindle.com"] + SETUP_ANSWERS[1:], "app-password-123", "-w", str(demo),
              "--workspace-config")
    run_reset(monkeypatch, "y", "-w", str(demo), "--workspace-config")
    assert not (demo / ".kindle-creds").exists()
    assert keyring.store and (isolated / ".config/kindle-sync/config").exists()
    sync(demo)
    assert destinations() == ["me@kindle.com"]


def test_doctor_reports_problems_without_secrets(demo, monkeypatch, capsys):
    monkeypatch.setenv("KINDLE_EMAIL", "not-an-email")
    monkeypatch.setenv("SMTP_PORT", "smtp")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password-123")
    with pytest.raises(SystemExit) as exc:
        kindle_sync.main(["doctor", "-w", str(demo)])
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "KINDLE_EMAIL is not a valid email address" in out
    assert "SENDER_EMAIL is not set" in out
    assert "SMTP_PORT must be a number" in out
    assert "SMTP_PASSWORD is set (from environment variable)" in out
    assert "app-password-123" not in out
    assert FakeSMTP.sent == []


def test_doctor_check_login_reports_auth_rejection(demo, creds, capsys):
    kindle_sync.main(["doctor", "-w", str(demo), "--check-login"])
    assert "Logged in to smtp.gmail.com" in capsys.readouterr().out
    FakeSMTP.fail_login = True
    with pytest.raises(SystemExit):
        kindle_sync.main(["doctor", "-w", str(demo), "--check-login"])
    assert "Authentication rejected" in capsys.readouterr().out
    assert FakeSMTP.sent == []


def png(width, height):
    import struct
    import zlib
    chunk = lambda kind, data: struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    raw = b"".join(b"\0" + b"\x80\x80\x80" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


@pytest.fixture
def book(tmp_path):
    ws = tmp_path / "my-book"
    (ws / "chapters").mkdir(parents=True)
    (ws / "assets").mkdir()
    (ws / "BOOK.md").write_text("# Book: How Indexes Work\n\n## Chapters\n- [x] 01. Pages\n")
    (ws / "MISSION.md").write_text("# Mission: Not the title\n")
    (ws / "assets/cover.png").write_bytes(png(16, 24))
    (ws / "assets/01 catalog.png").write_bytes(png(40, 20))
    (ws / "chapters/01-pages.html").write_text(
        """<html><body><h1>Pages</h1>
<figure><img src="../assets/01%20catalog.png" alt="Card catalog"><figcaption>A catalog</figcaption></figure>
<img src="https://example.com/remote.png" alt="Remote picture">
<svg viewBox="0 0 100 50"><defs><linearGradient id="g"/></defs><rect width="100" height="50" fill="url(#g)"/></svg>
</body></html>""", encoding="utf-8")
    return ws


def test_book_workspace_embeds_images_and_svg_in_epub(book, capsys):
    kindle_sync.main(["build", "-w", str(book), "-f", "epub"])
    assert "remote.png" in capsys.readouterr().out  # warned, not fetched
    with zipfile.ZipFile(book / "chapters/kindle-output/how-indexes-work.epub") as z:
        names = set(z.namelist())
        chapter, opf = z.read("OEBPS/ch01.xhtml").decode(), z.read("OEBPS/content.opf").decode()
        assert z.read("OEBPS/assets/01 catalog.png") == (book / "assets/01 catalog.png").read_bytes()
    assert "OEBPS/assets/cover.png" in names
    ET.fromstring(chapter.encode())
    # The image resolves from the chapter to a packaged file, and SVG keeps its case-sensitive names.
    assert 'src="assets/01%20catalog.png"' in chapter
    assert "viewBox=" in chapter and "<linearGradient" in chapter
    assert "[Remote picture]" in chapter and "example.com" not in chapter
    assert 'href="assets/01%20catalog.png" media-type="image/png"' in opf
    assert 'properties="cover-image"' in opf and 'properties="svg"' in opf
    assert "<dc:title>How Indexes Work</dc:title>" in opf


def test_book_pdf_embeds_cover_and_chapter_images(book):
    kindle_sync.main(["build", "-w", str(book), "-f", "pdf"])
    pages = PdfReader(book / "chapters/kindle-output/how-indexes-work.pdf").pages
    sizes = {tuple(image.image.size) for page in pages for image in page.images}
    assert {(16, 24), (40, 20)} <= sizes
    assert "Chapters" in pages[1].extract_text()


def test_changing_an_image_resends_the_book(book, creds):
    kindle_sync.main(["sync", "-w", str(book)])
    kindle_sync.main(["sync", "-w", str(book)])
    assert len(FakeSMTP.sent) == 1
    (book / "assets/01 catalog.png").write_bytes(png(41, 20))
    kindle_sync.main(["sync", "-w", str(book)])
    assert len(FakeSMTP.sent) == 2
