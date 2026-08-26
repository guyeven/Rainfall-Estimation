#!/usr/bin/env python3
"""List, accept, or reject color-coded LaTeX thesis revisions."""

from __future__ import annotations

import argparse
import difflib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


COMMAND_RE = re.compile(r"\\(reviewreplace|reviewadd|reviewdelete)(?![A-Za-z@])")
ARG_COUNTS = {"reviewreplace": 2, "reviewadd": 1, "reviewdelete": 1}


@dataclass(frozen=True)
class Revision:
    revision_id: int
    command: str
    start: int
    end: int
    line: int
    arguments: tuple[str, ...]


def is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def is_commented(text: str, index: int) -> bool:
    line_start = text.rfind("\n", 0, index) + 1
    cursor = line_start
    while cursor < index:
        if text[cursor] == "%" and not is_escaped(text, cursor):
            return True
        cursor += 1
    return False


def is_definition(text: str, start: int) -> bool:
    line_start = text.rfind("\n", 0, start) + 1
    prefix = text[line_start:start]
    return bool(
        re.search(
            r"\\(?:newcommand|renewcommand|providecommand|DeclareRobustCommand)\s*\{\s*$",
            prefix,
        )
    )


def skip_space(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def parse_group(text: str, start: int) -> tuple[str, int]:
    if start >= len(text) or text[start] != "{":
        raise ValueError("expected an opening brace")
    depth = 1
    cursor = start + 1
    while cursor < len(text):
        char = text[cursor]
        if char == "%" and not is_escaped(text, cursor):
            newline = text.find("\n", cursor)
            cursor = len(text) if newline < 0 else newline + 1
            continue
        if char == "{" and not is_escaped(text, cursor):
            depth += 1
        elif char == "}" and not is_escaped(text, cursor):
            depth -= 1
            if depth == 0:
                return text[start + 1 : cursor], cursor + 1
        cursor += 1
    raise ValueError("unclosed brace group")


def find_revisions(text: str) -> list[Revision]:
    revisions: list[Revision] = []
    for match in COMMAND_RE.finditer(text):
        if is_commented(text, match.start()) or is_definition(text, match.start()):
            continue
        command = match.group(1)
        cursor = match.end()
        arguments: list[str] = []
        try:
            for _ in range(ARG_COUNTS[command]):
                cursor = skip_space(text, cursor)
                argument, cursor = parse_group(text, cursor)
                arguments.append(argument)
        except ValueError:
            continue
        revisions.append(
            Revision(
                revision_id=len(revisions) + 1,
                command=command,
                start=match.start(),
                end=cursor,
                line=text.count("\n", 0, match.start()) + 1,
                arguments=tuple(arguments),
            )
        )
    return revisions


def preview(value: str, limit: int = 90) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def print_revisions(revisions: list[Revision]) -> None:
    if not revisions:
        print("No staged revisions found.")
        return
    for revision in revisions:
        if revision.command == "reviewreplace":
            detail = f'old="{preview(revision.arguments[0])}" new="{preview(revision.arguments[1])}"'
        elif revision.command == "reviewadd":
            detail = f'new="{preview(revision.arguments[0])}"'
        else:
            detail = f'old="{preview(revision.arguments[0])}"'
        kind = revision.command.removeprefix("review")
        print(f"{revision.revision_id}: {kind} at line {revision.line}: {detail}")


def replacement_for(revision: Revision, action: str) -> str:
    if action == "accept":
        if revision.command in {"reviewreplace", "reviewadd"}:
            return revision.arguments[-1]
        return ""
    if revision.command in {"reviewreplace", "reviewdelete"}:
        return revision.arguments[0]
    return ""


def select_revisions(
    revisions: list[Revision], ids: list[int], select_all: bool
) -> list[Revision]:
    if select_all:
        return revisions
    requested = set(ids)
    available = {revision.revision_id for revision in revisions}
    missing = sorted(requested - available)
    if missing:
        raise ValueError(f"unknown revision ID(s): {', '.join(map(str, missing))}")
    return [revision for revision in revisions if revision.revision_id in requested]


def apply_revisions(text: str, selected: list[Revision], action: str) -> str:
    updated = text
    for revision in sorted(selected, key=lambda item: item.start, reverse=True):
        updated = (
            updated[: revision.start]
            + replacement_for(revision, action)
            + updated[revision.end :]
        )
    return updated


def print_diff(path: Path, original: str, updated: str) -> None:
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile=str(path),
        tofile=str(path),
    )
    sys.stdout.writelines(diff)


def atomic_write(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.revision-tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("list", "accept", "reject"))
    parser.add_argument("tex_file", type=Path)
    parser.add_argument("--id", dest="ids", action="append", type=int, default=[])
    parser.add_argument("--all", action="store_true", help="select every staged revision")
    parser.add_argument("--write", action="store_true", help="apply instead of previewing")
    args = parser.parse_args()

    if not args.tex_file.exists():
        parser.error(f"TeX file does not exist: {args.tex_file}")
    if args.action == "list" and (args.ids or args.all or args.write):
        parser.error("list does not accept --id, --all, or --write")
    if args.action != "list" and not (args.ids or args.all):
        parser.error("accept and reject require at least one --id or --all")
    if args.ids and args.all:
        parser.error("use either --id or --all, not both")

    original = args.tex_file.read_text(encoding="utf-8")
    revisions = find_revisions(original)
    if args.action == "list":
        print_revisions(revisions)
        return 0

    try:
        selected = select_revisions(revisions, args.ids, args.all)
    except ValueError as error:
        parser.error(str(error))
    if not selected:
        print("No staged revisions selected.")
        return 0

    updated = apply_revisions(original, selected, args.action)
    print_diff(args.tex_file, original, updated)
    if args.write:
        atomic_write(args.tex_file, updated)
        print(f"Applied {args.action} to {len(selected)} revision(s) in {args.tex_file}.")
    else:
        print("Preview only; rerun with --write to modify the file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
