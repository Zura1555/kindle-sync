import json
import subprocess
import sys
from pathlib import Path

from bs4 import BeautifulSoup
import pytest


ROOT = Path(__file__).resolve().parents[1]


def build(workspace, output):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/build_site.py"), "--workspace", str(workspace), "--output", str(output)],
        capture_output=True, text=True,
    )


def test_site_publishes_ordered_content_without_private_workspace_files(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "MISSION.md").write_text("# Mission: SQL & Data\n\n## Goal\nLearn **queries**.")
    (workspace / "RESOURCES.md").write_text("# Resources\n\nhttps://example.com/?a=1&b=2\n\n[Docs](https://example.org)")
    (workspace / "lessons").mkdir()
    lesson = '<h1>First &amp; foremost</h1><button onclick="this.textContent=42">Quiz</button><script>window.lesson = true</script><a href="https://example.net">Source</a>'
    (workspace / "lessons/0002-second.html").write_text("<title>Second lesson</title>")
    (workspace / "lessons/0001-first.html").write_text(lesson)
    (workspace / "lessons/draft.html").write_text("Do not publish")
    (workspace / "lessons/kindle-output").mkdir()
    (workspace / "lessons/kindle-output/book.html").write_text("Private output")
    (workspace / "reference").mkdir()
    (workspace / "reference/glossary.html").write_text("<h1>Glossary</h1>")
    (workspace / ".kindle-creds").write_text("not-a-real-secret")
    (workspace / "NOTES.md").write_text("Private notes")
    (workspace / "assets").mkdir()
    (workspace / "assets/chart.svg").write_text("<svg/>")
    output = tmp_path / "site"
    result = build(workspace, output)
    assert result.returncode == 0, result.stderr
    course = json.loads((output / "course.json").read_text())
    assert course["title"] == "SQL & Data"
    assert [page["title"] for page in course["pages"]] == ["Overview", "First & foremost", "Second lesson", "Glossary", "Resources"]
    for page in course["pages"]:
        assert (output / page["path"]).is_file()
        assert not page["path"].startswith("/")
    rendered = BeautifulSoup((output / "content/lessons/0001-first.html").read_text(), "html.parser")
    assert rendered.button["onclick"] == "this.textContent=42"
    assert rendered.script.string == "window.lesson = true"
    assert rendered.a["target"] == "_blank"
    assert "noopener" in rendered.a["rel"]
    assert (output / "content/assets/chart.svg").is_file()
    published = {path.name for path in output.rglob("*")}
    assert not published & {".kindle-creds", "NOTES.md", "draft.html", "kindle-output", "book.html"}
    overview = BeautifulSoup((output / "content/mission.html").read_text(), "html.parser")
    assert overview.h2.text == "Goal"
    assert overview.strong.text == "queries"
    resources = BeautifulSoup((output / "content/resources.html").read_text(), "html.parser")
    assert [link["href"] for link in resources.find_all("a")] == ["https://example.com/?a=1&b=2", "https://example.org"]
    assert all(link["target"] == "_blank" for link in resources.find_all("a"))
    # A rebuild removes deleted lessons instead of leaving stale public content.
    (workspace / "lessons/0002-second.html").unlink()
    assert build(workspace, output).returncode == 0
    assert not (output / "content/lessons/0002-second.html").exists()


def test_empty_workspace_can_publish_an_overview(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "MISSION.md").write_text("# Mission: New course\n\nStart here.")
    output = tmp_path / "site"
    result = build(workspace, output)
    assert result.returncode == 0, result.stderr
    course = json.loads((output / "course.json").read_text())
    assert [page["title"] for page in course["pages"]] == ["Overview"]


@pytest.mark.parametrize("destination", ["workspace", "workspace/output", "existing"])
def test_build_refuses_to_delete_source_or_unrelated_files(tmp_path, destination):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    mission = workspace / "MISSION.md"
    mission.write_text("# Mission: Keep me")
    output = tmp_path / destination
    output.mkdir(parents=True, exist_ok=True)
    keep = output / "keep.txt"
    keep.write_text("Keep me")
    result = build(workspace, output)
    assert result.returncode != 0
    assert keep.read_text() == "Keep me"
    assert mission.read_text() == "# Mission: Keep me"
