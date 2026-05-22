#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set

SUPPORTED_SUFFIXES = {
    ".txt",
    ".md",
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".xml",
    ".log",
    ".edf",
    ".ini",
    ".cfg",
    ".conf",
    ".properties",
    ".sql",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".sh",
}
TEXT_ENCODINGS = ("utf-8", "utf-8-sig", "gb18030")


def normalize_extensions(values: Optional[Sequence[str]]) -> Set[str]:
    if not values:
        return set(SUPPORTED_SUFFIXES)

    extensions: Set[str] = set()
    for value in values:
        for part in value.split(","):
            cleaned = part.strip().lower()
            if not cleaned:
                continue
            if not cleaned.startswith("."):
                cleaned = f".{cleaned}"
            extensions.add(cleaned)
    return extensions or set(SUPPORTED_SUFFIXES)


def text_files(root: Path, extensions: Optional[Sequence[str]] = None) -> List[Path]:
    allowed = normalize_extensions(extensions)
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in allowed
    )


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in TEXT_ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(
        f"Could not decode {path} with supported encodings: {', '.join(TEXT_ENCODINGS)}"
    )


def iter_lines(text: str) -> Iterable[tuple[int, str]]:
    for line_number, line in enumerate(text.splitlines(), start=1):
        yield line_number, line


def search_text(path: Path, needle: str) -> List[Dict[str, object]]:
    folded = needle.casefold()
    matches: List[Dict[str, object]] = []
    for line_number, line in iter_lines(read_text(path)):
        if folded in line.casefold():
            matches.append(
                {
                    "file": str(path),
                    "line": line_number,
                    "snippet": line,
                }
            )
    return matches


def search_tree(
    root: Path, needle: str, extensions: Optional[Sequence[str]] = None
) -> List[Dict[str, object]]:
    matches: List[Dict[str, object]] = []
    for path in text_files(root, extensions):
        matches.extend(search_text(path, needle))
    return matches


def command_list(args: argparse.Namespace) -> int:
    files = text_files(Path(args.root).resolve(), args.extensions)
    if args.json:
        print(json.dumps([str(path) for path in files], indent=2))
        return 0
    if not files:
        print("No supported text files found.")
        return 0
    for path in files:
        print(path)
    return 0


def command_preview(args: argparse.Namespace) -> int:
    path = Path(args.file).resolve()
    lines = []
    for line_number, line in iter_lines(read_text(path)):
        lines.append({"line": line_number, "text": line})
        if len(lines) >= args.lines:
            break

    if args.json:
        print(json.dumps({"file": str(path), "lines": lines}, indent=2, ensure_ascii=False))
        return 0

    print(f"File: {path}")
    if not lines:
        print("(empty file)")
        return 0
    for item in lines:
        print(f"{item['line']}: {item['text']}")
    return 0


def emit_matches(matches: List[Dict[str, object]], needle: str, as_json: bool) -> int:
    if as_json:
        print(json.dumps(matches, indent=2, ensure_ascii=False))
        return 0
    if not matches:
        print(f'No matches found for "{needle}".')
        return 0
    for match in matches:
        print(f"{match['file']} | line={match['line']} | {match['snippet']}")
    return 0


def command_search_file(args: argparse.Namespace) -> int:
    matches = search_text(Path(args.file).resolve(), args.needle)
    return emit_matches(matches, args.needle, args.json)


def command_search_tree(args: argparse.Namespace) -> int:
    matches = search_tree(Path(args.root).resolve(), args.needle, args.extensions)
    return emit_matches(matches, args.needle, args.json)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List, preview, and search plain text files from the command line."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser(
        "list", help="List supported text files below a root directory."
    )
    list_parser.add_argument("--root", default=".", help="Directory to search from.")
    list_parser.add_argument(
        "--extensions",
        nargs="*",
        help="Optional file extensions to include, such as .edf .txt or csv,json.",
    )
    list_parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    list_parser.set_defaults(func=command_list)

    preview_parser = subparsers.add_parser("preview", help="Preview a text file.")
    preview_parser.add_argument("file", help="Path to a text file.")
    preview_parser.add_argument(
        "--lines", type=int, default=20, help="Maximum number of lines to preview."
    )
    preview_parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    preview_parser.set_defaults(func=command_preview)

    search_file_parser = subparsers.add_parser(
        "search-file", help="Search for text in a specific file."
    )
    search_file_parser.add_argument("needle", help="Case-insensitive text to search for.")
    search_file_parser.add_argument("file", help="Path to a text file.")
    search_file_parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    search_file_parser.set_defaults(func=command_search_file)

    search_tree_parser = subparsers.add_parser(
        "search-tree", help="Search for text across supported files below a root directory."
    )
    search_tree_parser.add_argument("needle", help="Case-insensitive text to search for.")
    search_tree_parser.add_argument("--root", default=".", help="Directory to search from.")
    search_tree_parser.add_argument(
        "--extensions",
        nargs="*",
        help="Optional file extensions to include, such as .edf .txt or csv,json.",
    )
    search_tree_parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    search_tree_parser.set_defaults(func=command_search_tree)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
