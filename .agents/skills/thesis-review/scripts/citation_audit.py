#!/usr/bin/env python3
"""Mechanical LaTeX/BibTeX citation audit using only the Python standard library."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path


CITE_RE = re.compile(
    r"\\cite[a-zA-Z*]*\s*(?:\[[^\]]*\]\s*){0,2}\{([^{}]+)\}", re.DOTALL
)
INPUT_RE = re.compile(r"\\(?:input|include)\s*\{([^{}]+)\}")
BIBLIOGRAPHY_RE = re.compile(r"\\bibliography\s*\{([^{}]+)\}")
ADDBIB_RE = re.compile(r"\\addbibresource(?:\[[^\]]*\])?\s*\{([^{}]+)\}")
ENTRY_START_RE = re.compile(
    r"@(?!comment\b|preamble\b|string\b)([A-Za-z]+)\s*\{\s*([^,\s]+)\s*,", re.I
)
FIELD_RE = re.compile(
    r"(?ms)^\s*([A-Za-z][\w-]*)\s*=\s*(?:\{(.*?)\}|\"(.*?)\"|([^,\n]+))\s*,?"
)


def strip_comments(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        cut = len(line)
        for index, char in enumerate(line):
            if char != "%":
                continue
            backslashes = 0
            cursor = index - 1
            while cursor >= 0 and line[cursor] == "\\":
                backslashes += 1
                cursor -= 1
            if backslashes % 2 == 0:
                cut = index
                break
        lines.append(line[:cut])
    return "\n".join(lines)


def resolve_tex_tree(main_tex: Path) -> tuple[list[Path], str]:
    seen: set[Path] = set()
    ordered: list[Path] = []
    chunks: list[str] = []

    def visit(path: Path) -> None:
        path = path.resolve()
        if path in seen or not path.exists():
            return
        seen.add(path)
        ordered.append(path)
        text = strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        chunks.append(text)
        for raw_name in INPUT_RE.findall(text):
            candidate = path.parent / raw_name.strip()
            if not candidate.suffix:
                candidate = candidate.with_suffix(".tex")
            visit(candidate)

    visit(main_tex)
    return ordered, "\n".join(chunks)


def discover_bib_files(main_tex: Path, tex_text: str, explicit: list[str]) -> list[Path]:
    candidates: list[Path] = []
    if explicit:
        candidates.extend(Path(item) for item in explicit)
    else:
        names: list[str] = []
        for group in BIBLIOGRAPHY_RE.findall(tex_text):
            names.extend(part.strip() for part in group.split(","))
        names.extend(item.strip() for item in ADDBIB_RE.findall(tex_text))
        for name in names:
            path = Path(name)
            if not path.suffix:
                path = path.with_suffix(".bib")
            candidates.append(main_tex.parent / path)
        if not candidates:
            candidates.extend(sorted(main_tex.parent.glob("*.bib")))

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def split_bib_entries(text: str) -> list[tuple[str, str, str]]:
    entries: list[tuple[str, str, str]] = []
    for match in ENTRY_START_RE.finditer(text):
        depth = 1
        cursor = match.end()
        while cursor < len(text) and depth:
            if text[cursor] == "{":
                depth += 1
            elif text[cursor] == "}":
                depth -= 1
            cursor += 1
        body = text[match.end() : max(match.end(), cursor - 1)]
        entries.append((match.group(1).lower(), match.group(2), body))
    return entries


def parse_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for match in FIELD_RE.finditer(body):
        value = next((part for part in match.groups()[1:] if part is not None), "")
        fields[match.group(1).lower()] = re.sub(r"\s+", " ", value).strip()
    return fields


def audit(main_tex: Path, explicit_bibs: list[str]) -> dict[str, object]:
    tex_files, tex_text = resolve_tex_tree(main_tex)
    citations = [
        key.strip()
        for group in CITE_RE.findall(tex_text)
        for key in group.split(",")
        if key.strip()
    ]
    citation_counts = Counter(citations)
    bib_files = discover_bib_files(main_tex.resolve(), tex_text, explicit_bibs)

    entry_locations: dict[str, list[str]] = {}
    entry_fields: dict[str, dict[str, str]] = {}
    missing_bib_files: list[str] = []
    for bib_path in bib_files:
        if not bib_path.exists():
            missing_bib_files.append(str(bib_path))
            continue
        text = bib_path.read_text(encoding="utf-8", errors="replace")
        for _entry_type, key, body in split_bib_entries(text):
            entry_locations.setdefault(key, []).append(str(bib_path))
            entry_fields.setdefault(key, parse_fields(body))

    bib_keys = set(entry_locations)
    cited_keys = set(citation_counts)
    essential = ("author", "title", "year")
    identifiers = ("doi", "url", "isbn", "eprint")
    missing_metadata = {
        key: [field for field in essential if not entry_fields[key].get(field)]
        for key in sorted(bib_keys)
        if any(not entry_fields[key].get(field) for field in essential)
    }
    without_identifier = [
        key
        for key in sorted(bib_keys)
        if not any(entry_fields[key].get(field) for field in identifiers)
    ]

    return {
        "main_tex": str(main_tex.resolve()),
        "tex_files": [str(path) for path in tex_files],
        "bib_files": [str(path) for path in bib_files],
        "citation_occurrences": sum(citation_counts.values()),
        "unique_cited_keys": len(cited_keys),
        "bibliography_entries": len(bib_keys),
        "missing_citation_keys": sorted(cited_keys - bib_keys),
        "unused_bibliography_keys": sorted(bib_keys - cited_keys),
        "duplicate_bibliography_keys": {
            key: paths for key, paths in sorted(entry_locations.items()) if len(paths) > 1
        },
        "missing_essential_metadata": missing_metadata,
        "entries_without_stable_identifier": without_identifier,
        "missing_bibliography_files": missing_bib_files,
    }


def print_text(report: dict[str, object]) -> None:
    print(f"Main TeX: {report['main_tex']}")
    print(f"TeX files scanned: {len(report['tex_files'])}")
    print(f"Bib files: {len(report['bib_files'])}")
    print(f"Citation occurrences: {report['citation_occurrences']}")
    print(f"Unique cited keys: {report['unique_cited_keys']}")
    print(f"Bibliography entries: {report['bibliography_entries']}")
    sections = (
        ("Missing citation keys", "missing_citation_keys"),
        ("Unused bibliography keys", "unused_bibliography_keys"),
        ("Duplicate bibliography keys", "duplicate_bibliography_keys"),
        ("Missing essential metadata", "missing_essential_metadata"),
        ("Entries without stable identifier", "entries_without_stable_identifier"),
        ("Missing bibliography files", "missing_bibliography_files"),
    )
    for title, key in sections:
        value = report[key]
        print(f"\n{title} ({len(value)}):")
        if isinstance(value, dict):
            for item, detail in value.items():
                print(f"  - {item}: {detail}")
        else:
            for item in value:
                print(f"  - {item}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("main_tex", type=Path, help="Main LaTeX file")
    parser.add_argument("--bib", action="append", default=[], help="Explicit BibTeX file; repeatable")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()
    if not args.main_tex.exists():
        parser.error(f"TeX file does not exist: {args.main_tex}")
    report = audit(args.main_tex, args.bib)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text(report)
    return 1 if report["missing_citation_keys"] or report["missing_bibliography_files"] else 0


if __name__ == "__main__":
    sys.exit(main())
