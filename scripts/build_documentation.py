"""Build docs/documentation.md: the technical documentation in one file, with a table of contents.

    uv run python scripts/build_documentation.py

The separate files stay the source: edit them, then run this again. Each file's headings move down one level under
its part, and relative links are rewritten so they still work from docs/ (see PARTS for what is included).
"""

from __future__ import annotations

import posixpath
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "documentation.md"

PARTS: list[tuple[str, list[str]]] = [
    ("Overview", ["README.md"]),
    ("Engineering rules", ["CLAUDE.md"]),
    ("Running and operating", ["commands.md", "docs/runbook.md"]),
    (
        "Components",
        [
            "apps/api/README.md",
            "apps/workers/README.md",
            "apps/web/README.md",
            "packages/core/README.md",
            "packages/asr/README.md",
            "packages/llm/README.md",
            "packages/analytics/README.md",
            "rubrics/README.md",
            "infra/README.md",
            "infra/annotation/README.md",
            "eval/README.md",
            "eval/goldset/README.md",
        ],
    ),
    ("Architecture decisions (ADRs)", sorted(f"docs/adr/{p.name}" for p in (ROOT / "docs" / "adr").glob("*.md"))),
    (
        "Technical reference",
        [
            "docs/llm-providers.md",
            "docs/webhooks.md",
            "docs/security/findings.md",
            "docs/security/permissions.yaml",
            "docs/design/tokens.md",
            "docs/setup/auth.md",
            "docs/setup/cloud-checklist.md",
        ],
    ),
]
"""Technical documents only. Left out on purpose: guides for raters, annotators and schools, rubric review sheets,
legal drafts, the 8-week plan prompts (history), docs/README.md (an index of the separate files) and the LLM prompt
templates in packages/analytics/prompts/ (code inputs)."""

TITLES = {"docs/rubrics/review-sheet.md": "Rubric review sheets (draft v0.1)"}
"""Titles for files whose own first heading is not a usable title."""

SOURCES = {source for _, sources in PARTS for source in sources}
_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^(#{1,6})(\s)")
_LINK = re.compile(r"(\]\()([^)\s]+)(\))")


def anchor(source: str) -> str:
    """A fixed link target per document, so equal titles never collide."""
    return "doc-" + re.sub(r"[^a-z0-9]+", "-", source.lower()).strip("-")


def fix_link(target: str, source: str) -> str:
    """A link to another document in this file jumps to it; any other relative link is made relative to docs/."""
    if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith(("#", "/")):
        return target
    path, _, fragment = target.partition("#")
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source), path))
    if resolved in SOURCES:
        return f"#{anchor(resolved)}"
    return posixpath.relpath(resolved, "docs") + (f"#{fragment}" if fragment else "")


def body(source: str) -> tuple[str, str]:
    """The file's title and its text with headings moved down one level and links fixed. A first heading that is
    only a draft notice ("DRAFT FOR LEGAL REVIEW") stays as a bold line, and the next heading becomes the title."""
    text = (ROOT / source).read_text(encoding="utf-8")
    if source.endswith(".yaml"):
        return Path(source).name, f"```yaml\n{text.rstrip()}\n```\n"
    lines: list[str] = []
    title, fenced, notice = TITLES.get(source, ""), False, False
    for line in text.splitlines():
        if _FENCE.match(line):
            fenced = not fenced
        elif not fenced:
            heading = _HEADING.match(line)
            if heading and not lines and not title and heading.group(1) == "#" and line[2:].startswith("DRAFT"):
                lines.append(f"**{line[2:].strip()}**")
                notice = True
                continue
            if heading and not title and (heading.group(1) == "#" or (notice and heading.group(1) == "##")):
                title = line.lstrip("#").strip()
                continue
            if heading and source in TITLES and heading.group(1) == "#" and line[2:].strip() and not fenced:
                line = f"**{line[2:].strip()}**"
                heading = None
            if heading:
                line = "#" * min(len(heading.group(1)) + 1, 6) + line[len(heading.group(1)) :]
            line = _LINK.sub(lambda m: m.group(1) + fix_link(m.group(2), source) + m.group(3), line)
        lines.append(line)
    return title or source, "\n".join(lines).strip() + "\n"


def main() -> None:
    contents = ["## Contents", ""]
    chapters: list[str] = []
    for n, (part, sources) in enumerate(PARTS, 1):
        contents.append(f"{n}. [{part}](#part-{n})")
        chapters.append(f'<a id="part-{n}"></a>\n\n# Part {n}. {part}\n')
        for source in sources:
            title, text = body(source)
            contents.append(f"   - [{title}](#{anchor(source)})")
            link = posixpath.relpath(source, "docs")
            chapters.append(f'<a id="{anchor(source)}"></a>\n\n## {title}\n\n*Source: [`{source}`]({link})*\n\n{text}')
    header = (
        "# Sabha technical documentation\n\n"
        "The technical documentation in one file: architecture, components, running and operating, decisions and "
        "reference. Built on "
        f"{date.today().isoformat()} by `scripts/build_documentation.py`. The separate files are the source: "
        "edit them, not this file, then run `uv run python scripts/build_documentation.py` again.\n"
    )
    OUT.write_text("\n".join([header, *contents, "", "---", "", *chapters]), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(SOURCES)} documents")


if __name__ == "__main__":
    main()
