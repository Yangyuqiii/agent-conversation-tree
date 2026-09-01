#!/usr/bin/env python3
"""Extract forkable points from an assistant message."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

NUMBERED_LINE = re.compile(
    r"^(?P<indent>[ \t]*)(?:"
    r"(?P<num>\d+)\s*[\.、\)]\s*"
    r"|\((?P<num2>\d+)\)\s*"
    r")(?P<body>\S.*)$"
)
HEADING_LINE = re.compile(r"^(#{2,3})[ \t]+(.+?)\s*#*\s*$")
MD_DECORATION = re.compile(r"[*_`]+")


def strip_md(text: str) -> str:
    cleaned = MD_DECORATION.sub("", text or "")
    return re.sub(r"\s+", " ", cleaned).strip()


def strip_leader(text: str) -> str:
    cleaned = strip_md(text)
    cleaned = re.sub(r"^#{1,6}\s*", "", cleaned)
    cleaned = re.sub(r"^(?:\d+\s*[.、.)]\s*|\(\d+\)\s*)", "", cleaned)
    return cleaned.strip()


def _title_and_excerpt(block: str) -> tuple[str, str]:
    lines = [line.rstrip() for line in block.strip().splitlines() if line.strip()]
    if not lines:
        return "", ""
    title = strip_leader(lines[0])
    if len(title) > 80:
        title = title[:77].rstrip() + "..."
    excerpt_source = " ".join(strip_md(line) for line in lines)
    excerpt = excerpt_source[:240].rstrip()
    if len(excerpt_source) > 240:
        excerpt += "..."
    return title, excerpt


def _collect_blocks(lines: list[str], starts: list[tuple[int, int]]) -> list[dict]:
    points: list[dict] = []
    for i, (line_index, number) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(lines)
        block = "\n".join(lines[line_index:end])
        title, excerpt = _title_and_excerpt(block)
        if len(title) < 2:
            continue
        points.append(
            {
                "index": number,
                "title": title,
                "excerpt": excerpt,
                "heading": title,
            }
        )
    return points


def extract_numbered(text: str) -> list[dict]:
    lines = (text or "").splitlines()
    matches: list[tuple[int, int, int]] = []
    for i, line in enumerate(lines):
        match = NUMBERED_LINE.match(line)
        if not match:
            continue
        raw_num = match.group("num") or match.group("num2")
        matches.append((len(match.group("indent") or ""), i, int(raw_num)))
    if not matches:
        return []
    min_indent = min(item[0] for item in matches)
    starts = [(i, number) for indent, i, number in matches if indent == min_indent]
    return _collect_blocks(lines, starts)


def extract_headings(text: str) -> list[dict]:
    lines = (text or "").splitlines()
    starts: list[tuple[int, int]] = []
    for i, line in enumerate(lines):
        match = HEADING_LINE.match(line)
        if match:
            starts.append((i, len(starts) + 1))
    return _collect_blocks(lines, starts)


def extract_points(text: str) -> list[dict]:
    numbered = extract_numbered(text or "")
    if len(numbered) >= 1:
        return numbered
    headings = extract_headings(text or "")
    if len(headings) >= 2:
        return headings
    return []


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract forkable points from markdown text.")
    parser.add_argument("--text-file", help="UTF-8 text file. Use - for stdin.")
    parser.add_argument("--text", help="Raw message text. Ignored when --text-file is set.")
    return parser.parse_args(argv)


def read_input(args: argparse.Namespace) -> str:
    if args.text_file:
        if args.text_file == "-":
            return sys.stdin.read()
        return Path(args.text_file).read_text(encoding="utf-8")
    if args.text:
        return args.text
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    text = read_input(args)
    points = extract_points(text)
    json.dump({"ok": True, "points": points, "count": len(points)}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if points else 2


if __name__ == "__main__":
    raise SystemExit(main())
