import json
import shutil
import subprocess
import sys
from pathlib import Path

from bs4 import BeautifulSoup
import pytest


ROOT = Path(__file__).resolve().parents[1]


def build(workspace, output):
    workspaces = [workspace] if isinstance(workspace, Path) else workspace
    arguments = [argument for path in workspaces for argument in ["--workspace", str(path)]]
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/build_site.py"), *arguments, "--output", str(output)],
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
    course = json.loads((output / "course.json").read_text())["courses"][0]
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
    course = json.loads((output / "course.json").read_text())["courses"][0]
    assert [page["title"] for page in course["pages"]] == ["Overview"]


def test_multiple_courses_keep_lessons_assets_and_topics_separate(tmp_path):
    workspaces = [tmp_path / "sql", tmp_path / "python"]
    for workspace, title, topics in zip(workspaces, ["SQL", "Python"], [["Queries", "Indexes"], [None, "Functions"]]):
        (workspace / "lessons").mkdir(parents=True)
        (workspace / "assets").mkdir()
        (workspace / "MISSION.md").write_text(f"# Mission: {title}\n\nLearn {title}.")
        (workspace / "assets/chart.svg").write_text(f"<svg>{title}</svg>")
        for index, topic in enumerate(topics, 1):
            metadata = f'<meta name="topic" content="{topic}">' if topic else ""
            (workspace / f"lessons/{index:04}-lesson.html").write_text(f'{metadata}<h1>{title} lesson {index}</h1><img src="../assets/chart.svg">')
    output = tmp_path / "site"
    result = build(workspaces, output)
    assert result.returncode == 0, result.stderr
    courses = json.loads((output / "course.json").read_text())["courses"]
    assert [course["title"] for course in courses] == ["SQL", "Python"]
    assert [course["id"] for course in courses] == ["sql", "python"]
    assert [[page["topic"] for page in course["pages"] if page["section"] == "Lessons"] for course in courses] == [["Queries", "Indexes"], ["General", "Functions"]]
    assert courses[0]["pages"][1]["path"] == "content/lessons/0001-lesson.html"
    paths = [page["path"] for course in courses for page in course["pages"]]
    assert len(paths) == len(set(paths))
    for course in courses:
        for page in course["pages"]:
            path = output / page["path"]
            soup = BeautifulSoup(path.read_text(), "html.parser")
            assert course["title"] in soup.get_text()
            if page["section"] == "Lessons":
                asset = (path.parent / soup.img["src"]).resolve()
                assert course["title"] in asset.read_text()
            else:
                assert (path.parent / soup.link["href"]).resolve() == output / "reading.css"

    # The Pages command discovers real course folders without a hand-maintained list.
    repository = tmp_path / "repository"
    (repository / "scripts").mkdir(parents=True)
    shutil.copyfile(ROOT / "scripts/build_site.py", repository / "scripts/build_site.py")
    shutil.copytree(ROOT / "site", repository / "site")
    shutil.copytree(workspaces[0], repository / "demo-workspace")
    shutil.copytree(workspaces[1], repository / "courses/python")
    (repository / "courses/not-a-course").mkdir()
    result = subprocess.run([sys.executable, str(repository / "scripts/build_site.py"), "--output", str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    discovered = json.loads((output / "course.json").read_text())["courses"]
    assert [course["title"] for course in discovered] == ["SQL", "Python"]


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


def test_book_workspace_publishes_chapters_and_images(tmp_path):
    workspace = tmp_path / "book"
    (workspace / "chapters").mkdir(parents=True)
    (workspace / "assets").mkdir()
    (workspace / "BOOK.md").write_text("# Book: Indexes\n\n## Chapters\n- [x] 01. Pages")
    (workspace / "assets/figure.png").write_bytes(b"png")
    (workspace / "chapters/01-pages.html").write_text('<h1>Pages</h1><img src="../assets/figure.png">')
    (workspace / "chapters/kindle-output").mkdir()
    (workspace / "chapters/kindle-output/book.html").write_text("Private output")
    output = tmp_path / "site"
    result = build(workspace, output)
    assert result.returncode == 0, result.stderr
    course = json.loads((output / "course.json").read_text())["courses"][0]
    assert course["title"] == "Indexes" and course["unit"] == "Chapters"
    assert [(page["title"], page["section"]) for page in course["pages"]] == [("Overview", "Course"), ("Pages", "Chapters")]
    chapter = output / course["pages"][1]["path"]
    image = BeautifulSoup(chapter.read_text(), "html.parser").img["src"]
    assert (chapter.parent / image).resolve().read_bytes() == b"png"
    assert not (output / "content/chapters/kindle-output").exists()
