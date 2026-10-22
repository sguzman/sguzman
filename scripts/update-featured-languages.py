#!/usr/bin/env python3
"""Build a language card from 100 recently pushed original public repositories.

Each repo gets equal weight: a large repository cannot dominate the result.
Only recognized source files count, not binaries, vendored code, or generated
directories. This is NOT a measurement of individually authored commits.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape

OWNER = "sguzman"
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets" / "featured-languages.svg"
MAX_REPOSITORIES = 100

EXTENSIONS = {
    "rs": "Rust", "py": "Python", "js": "JavaScript", "jsx": "JavaScript",
    "mjs": "JavaScript", "ts": "TypeScript", "tsx": "TypeScript",
    "css": "CSS", "scss": "CSS", "html": "HTML", "htm": "HTML",
    "c": "C", "h": "C", "cc": "C++", "cpp": "C++", "hpp": "C++",
    "java": "Java", "kt": "Kotlin", "swift": "Swift", "go": "Go",
    "sh": "Shell", "bash": "Shell", "fish": "Shell", "lua": "Lua",
    "sql": "SQL", "rb": "Ruby", "dart": "Dart", "svelte": "Svelte",
    "vue": "Vue",
}
IGNORED_DIRS = {
    "node_modules", "target", "dist", "build", "vendor", "third_party",
    "third-party", ".next", ".git", "coverage", "generated", "gen",
    "assets", "fixtures", "testdata",
}
COLORS = {
    "Rust": "#dea584", "Python": "#3572a5", "TypeScript": "#3178c6",
    "JavaScript": "#f1e05a", "Shell": "#89e051", "HTML": "#e34c26",
    "CSS": "#563d7c", "Lua": "#000080", "C": "#555555",
    "C++": "#f34b7d", "Go": "#00add8",
}

def github_json(url: str) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "sguzman-profile-language-card",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    with urlopen(Request(url, headers=headers), timeout=45) as response:
        return json.load(response)

def recent_repositories():
    """Yield original public repos in descending order of last push.

    GitHub paginates in blocks of up to 100, so keep paginating past
    forks, archived repos, and non-code repos until we have 100 with code.
    """
    page = 1
    while True:
        url = (
            f"https://api.github.com/users/{OWNER}/repos"
            f"?type=owner&sort=pushed&direction=desc&per_page=100&page={page}"
        )
        batch = github_json(url)
        if not batch:
            break
        for repo in batch:
            if repo["fork"] or repo["archived"] or repo["private"]:
                continue
            if repo["name"].casefold() == OWNER.casefold():
                # Profile README repository is not a software project.
                continue
            if not repo.get("default_branch"):
                continue
            yield repo
        if len(batch) < 100:
            break
        page += 1

def source_bytes(tree: dict) -> dict[str, int]:
    if tree.get("truncated"):
        raise RuntimeError("GitHub returned a truncated source tree")
    totals: dict[str, int] = defaultdict(int)
    for node in tree.get("tree", []):
        if node.get("type") != "blob" or not node.get("size"):
            continue
        path = node["path"].lower()
        if any(part in IGNORED_DIRS for part in path.split("/")):
            continue
        if path.endswith((".min.js", ".min.css")):
            continue
        language = EXTENSIONS.get(path.rsplit(".", 1)[-1])
        if language:
            totals[language] += node["size"]
    return totals

def gather() -> tuple[dict[str, float], int]:
    scores: dict[str, float] = defaultdict(float)
    included = 0
    for repo in recent_repositories():
        name = repo["name"]
        base = f"https://api.github.com/repos/{OWNER}/{quote(name, safe='')}"
        branch = quote(repo["default_branch"], safe="")
        try:
            tree = github_json(f"{base}/git/trees/{branch}?recursive=1")
        except HTTPError as error:
            if error.code in (404, 409, 422):
                # Repositories can be deleted, renamed, or have no commits.
                print(f"Skipping {name}: GitHub returned HTTP {error.code}")
                continue
            raise
        if tree.get("truncated"):
            # Do not treat a partial tree as a complete language breakdown.
            print(f"Skipping {name}: GitHub truncated its source tree")
            continue
        by_language = source_bytes(tree)
        total = sum(by_language.values())
        if not total:
            continue
        included += 1
        for language, size in by_language.items():
            scores[language] += size / total
        if included >= MAX_REPOSITORIES:
            break
    if not included:
        raise RuntimeError("No source files found in recent original public repositories")
    return {key: val * 100 / included for key, val in scores.items()}, included

def render(scores: dict[str, float], included: int) -> str:
    entries = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))[:8]
    # Percentages are percentages of equally weighted per-repository shares.
    # A tiny trailing language may be below 0.01% and show as <0.01%.
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="448" height="206" viewBox="0 0 448 206" role="img" aria-label="Languages in recently pushed original public repositories">',
        '<title>Languages in recent original projects, equally weighted by repository</title>',
        '<rect x="0.5" y="0.5" width="447" height="205" rx="6" fill="#ffffff" stroke="#e2e5e9"/>',
        '<text x="22" y="31" font-family="Arial,Helvetica,sans-serif" font-size="16" font-weight="600" fill="#2675d8">Languages in recent projects</text>',
        f'<text x="22" y="53" font-family="Arial,Helvetica,sans-serif" font-size="11" fill="#576274">{included} recent original repos · equal weight · source only</text>',
        '<rect x="22" y="68" width="404" height="10" rx="5" fill="#eef0f3"/>',
    ]
    cursor = 22.0
    # Bar displays all language scores, not just the eight labels.
    for language, pct in sorted(scores.items(), key=lambda item: -item[1]):
        width = 404 * pct / 100
        if width < .1:
            continue
        color = COLORS.get(language, "#718096")
        lines.append(f'<rect x="{cursor:.2f}" y="68" width="{width:.2f}" height="10" fill="{color}"/>')
        cursor += width
    for index, (language, pct) in enumerate(entries):
        column, row = index // 4, index % 4
        x = 22 + column * 211
        y = 108 + row * 25
        color = COLORS.get(language, "#718096")
        pct_text = "<0.01%" if pct < 0.01 else f"{pct:.2f}%"
        lines.append(f'<circle cx="{x+4}" cy="{y-4}" r="4" fill="{color}"/>')
        lines.append(f'<text x="{x+14}" y="{y}" font-family="Arial,Helvetica,sans-serif" font-size="12" fill="#354052">{escape(language)} {escape(pct_text)}</text>')
    lines.append("</svg>")
    return "\n".join(lines) + "\n"

def main() -> None:
    scores, included = gather()
    svg = render(scores, included)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != svg:
        OUTPUT.write_text(svg, encoding="utf-8")
    print(f"Updated {OUTPUT}: {included} recent original repositories; " +
          ", ".join(f"{k}={v:.2f}%" for k, v in sorted(scores.items(), key=lambda x: -x[1])[:8]))

if __name__ == "__main__":
    main()
