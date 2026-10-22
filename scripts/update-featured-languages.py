#!/usr/bin/env python3
"""Build a profile language chart from selected, original project source trees.

Selection follows the GitHub repositories linked from README.md. Each repository
has equal weight so one large repository cannot dominate the result. This measures
source files, not personally authored commits or programming proficiency.
"""
from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from pathlib import Path
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape

OWNER = "sguzman"
ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
OUTPUT = ROOT / "assets" / "featured-languages.svg"

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

def featured_repositories() -> list[str]:
    text = README.read_text(encoding="utf-8")
    # Only owned repositories explicitly featured in the profile are counted.
    names = re.findall(r"https://github\.com/sguzman/([A-Za-z0-9_.-]+)", text)
    return list(dict.fromkeys(names))

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
    for name in featured_repositories():
        base = f"https://api.github.com/repos/{OWNER}/{name}"
        repo = github_json(base)
        if repo["fork"] or repo["archived"] or repo["private"]:
            continue
        branch = repo["default_branch"]
        tree = github_json(f"{base}/git/trees/{branch}?recursive=1")
        by_language = source_bytes(tree)
        total = sum(by_language.values())
        if not total:
            continue
        included += 1
        for language, size in by_language.items():
            scores[language] += size / total
    if not included:
        raise RuntimeError("No source files found in featured public repositories")
    return {key: val * 100 / included for key, val in scores.items()}, included

def render(scores: dict[str, float], included: int) -> str:
    entries = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))[:8]
    # Percentages are percentages of equally weighted per-repository shares.
    # A tiny trailing language may be below 0.01% and show as <0.01%.
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="448" height="206" viewBox="0 0 448 206" role="img" aria-label="Languages in featured non-fork repositories">',
        '<title>Languages in featured projects, equally weighted by repository</title>',
        '<rect x="0.5" y="0.5" width="447" height="205" rx="6" fill="#ffffff" stroke="#e2e5e9"/>',
        '<text x="22" y="31" font-family="Arial,Helvetica,sans-serif" font-size="16" font-weight="600" fill="#2675d8">Languages in featured projects</text>',
        f'<text x="22" y="53" font-family="Arial,Helvetica,sans-serif" font-size="11" fill="#576274">{included} original repos · equal weight per repo · source only</text>',
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
    print(f"Updated {OUTPUT}: {included} original repositories; " +
          ", ".join(f"{k}={v:.2f}%" for k, v in sorted(scores.items(), key=lambda x: -x[1])[:8]))

if __name__ == "__main__":
    main()
