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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=ROOT / "demo-workspace")
    parser.add_argument("--output", type=Path, default=ROOT / "build/site")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    output = args.output.resolve()
    # The generated directory is replaced on every build; never delete source content.
    if output == ROOT or output in ROOT.parents or output == workspace or output in workspace.parents or workspace in output.parents:
        parser.error("Output must be separate from the workspace and must not contain the repository.")
    if output.exists() and not ((output / ".nojekyll").is_file() and (output / "course.json").is_file()):
        parser.error("Refusing to replace a directory that is not a generated lesson site.")
    mission = (workspace / "MISSION.md").read_text(encoding="utf-8")
    heading = re.search(r"^#\s+(?:Mission:\s*)?(.+)$", mission, re.MULTILINE)
    title = heading.group(1).strip() if heading else workspace.name
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(ROOT / "site", output)
    content = output / "content"
    content.mkdir()
    pages = []
    for filename, label in [("MISSION.md", "Overview"), ("RESOURCES.md", "Resources")]:
        source = workspace / filename
        if not source.exists():
            continue
        destination = Path("content") / (source.stem.lower() + ".html")
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
        document = f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(label)}</title><link rel="stylesheet" href="../reading.css"><body><article>{soup}</article></body></html>'
        (output / destination).write_text(document, encoding="utf-8")
        pages.append({"path": destination.as_posix(), "title": label, "section": "Course" if label == "Overview" else "Resources"})

    resources = [page for page in pages if page["title"] == "Resources"]
    pages = [page for page in pages if page["title"] != "Resources"]
    for folder, pattern, section in [("lessons", "[0-9]*.html", "Lessons"), ("reference", "*.html", "Reference")]:
        for source in sorted((workspace / folder).glob(pattern)):
            soup = BeautifulSoup(source.read_text(encoding="utf-8"), "html.parser")
            heading = soup.find("h1") or soup.title
            label = heading.get_text(" ", strip=True) if heading else source.stem
            destination = Path("content") / folder / source.name
            (output / destination).parent.mkdir(parents=True, exist_ok=True)
            external_links(soup)
            (output / destination).write_text(str(soup), encoding="utf-8")
            pages.append({"path": destination.as_posix(), "title": label, "section": section})
    pages.extend(resources)
    # Assets are opt-in; never copy credentials, learning records, or Kindle output.
    if (workspace / "assets").is_dir():
        shutil.copytree(workspace / "assets", content / "assets")
    (output / "course.json").write_text(json.dumps({"title": title, "pages": pages}, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / ".nojekyll").touch()
    print(f"Built {len(pages)} pages → {output}")


if __name__ == "__main__":
    main()
