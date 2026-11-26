"""Build a static lesson reader from a learning workspace."""

import argparse
import html
import json
import re
import shutil
from pathlib import Path

import markdown
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]


def external_links(soup):
    for link in soup.find_all("a", href=re.compile(r"^(?:https?:)?//", re.IGNORECASE)):
        link["target"] = "_blank"
        link["rel"] = "noopener noreferrer"


def overview_file(workspace):
    """Book workspaces are described by BOOK.md and keep chapters in chapters/; courses use MISSION.md and lessons/."""
    return "BOOK.md" if (workspace / "BOOK.md").is_file() else "MISSION.md"


def build_course(workspace, output, content_path):
    book = overview_file(workspace) == "BOOK.md"
    mission = (workspace / overview_file(workspace)).read_text(encoding="utf-8")
    heading = re.search(r"^#\s+(?:(?:Mission|Book):\s*)?(.+)$", mission, re.MULTILINE)
    title = heading.group(1).strip() if heading else workspace.name
    content = output / content_path
    content.mkdir(parents=True, exist_ok=True)
    stylesheet = "../" * len(content_path.parts) + "reading.css"
    pages = []
    for filename, label in [(overview_file(workspace), "Overview"), ("RESOURCES.md", "Resources")]:
        source = workspace / filename
        if not source.exists():
            continue
        destination = content_path / (source.stem.lower() + ".html")
        body = markdown.markdown(source.read_text(encoding="utf-8"), extensions=["extra", "sane_lists"])
        # Render plain URLs in the existing resources file as usable links.
        soup = BeautifulSoup(body, "html.parser")
        for text in list(soup.find_all(string=True)):
            if any(parent.name in {"a", "code", "pre", "script", "style"} for parent in text.parents):
                continue
            parts = re.split(r"(https?://[^\s<>]+)", str(text))
            if len(parts) > 1:
                for index, part in enumerate(parts):
                    if index % 2:
                        link = soup.new_tag("a", href=part)
                        link.string = part
                        text.insert_before(link)
                    else:
                        text.insert_before(part)
                text.extract()
        external_links(soup)
        document = f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(label)}</title><link rel="stylesheet" href="{stylesheet}"><body><article>{soup}</article></body></html>'
        (output / destination).write_text(document, encoding="utf-8")
        pages.append({"path": destination.as_posix(), "title": label, "section": "Course" if label == "Overview" else "Resources"})

    resources = [page for page in pages if page["title"] == "Resources"]
    pages = [page for page in pages if page["title"] != "Resources"]
    unit = "Chapters" if book else "Lessons"
    for folder, pattern, section in [(unit.lower(), "[0-9]*.html", unit), ("reference", "*.html", "Reference")]:
        for source in sorted((workspace / folder).glob(pattern)):
            soup = BeautifulSoup(source.read_text(encoding="utf-8"), "html.parser")
            heading = soup.find("h1") or soup.title
            label = heading.get_text(" ", strip=True) if heading else source.stem
            destination = content_path / folder / source.name
            (output / destination).parent.mkdir(parents=True, exist_ok=True)
            external_links(soup)
            (output / destination).write_text(str(soup), encoding="utf-8")
            page = {"path": destination.as_posix(), "title": label, "section": section}
            if section == unit:
                topic = soup.find("meta", attrs={"name": "topic"})
                page["topic"] = (topic.get("content", "").strip() if topic else "") or "General"
            pages.append(page)
    pages.extend(resources)
    # Assets are opt-in; never copy credentials, learning records, or Kindle output.
    if (workspace / "assets").is_dir():
        shutil.copytree(workspace / "assets", content / "assets")
    return {"id": workspace.name, "title": title, "unit": unit, "pages": pages}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, action="append", help="Workspace to publish; repeat for multiple courses. Defaults to demo-workspace plus courses/*/MISSION.md and courses/*/BOOK.md.")
    parser.add_argument("--output", type=Path, default=ROOT / "build/site")
    args = parser.parse_args()
    workspaces = args.workspace or [ROOT / "demo-workspace", *sorted({path.parent for name in ("MISSION.md", "BOOK.md") for path in (ROOT / "courses").glob(f"*/{name}")})]
    workspaces = [path.resolve() for path in workspaces]
    output = args.output.resolve()
    # The generated directory is replaced on every build; never delete source content.
    if output == ROOT or output in ROOT.parents or any(output == workspace or output in workspace.parents or workspace in output.parents for workspace in workspaces):
        parser.error("Output must be separate from the workspaces and must not contain the repository.")
    if output.exists() and not ((output / ".nojekyll").is_file() and (output / "course.json").is_file()):
        parser.error("Refusing to replace a directory that is not a generated lesson site.")
    if len({path.name for path in workspaces}) != len(workspaces):
        parser.error("Course workspace folder names must be unique.")
    for workspace in workspaces:
        if not (workspace / overview_file(workspace)).is_file():
            parser.error(f"Missing MISSION.md or BOOK.md in {workspace}")
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(ROOT / "site", output)
    courses = []
    for index, workspace in enumerate(workspaces):
        # Keep the original course's published lesson URLs unchanged.
        content_path = Path("content") if index == 0 else Path("content/courses") / workspace.name
        courses.append(build_course(workspace, output, content_path))
    (output / "course.json").write_text(json.dumps({"courses": courses}, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / ".nojekyll").touch()
    print(f"Built {sum(len(course['pages']) for course in courses)} pages across {len(courses)} courses → {output}")


if __name__ == "__main__":
    main()
