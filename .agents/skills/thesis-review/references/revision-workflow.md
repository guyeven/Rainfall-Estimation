# Color-Coded Revision Workflow

Use this workflow when the author wants old wording retained visibly while reviewing proposed text, followed by an explicit accept or reject step.

## Markup

The thesis preamble defines:

```latex
\reviewreplace{old text}{proposed text}
\reviewadd{proposed text}
\reviewdelete{old text}
```

During review, old or deleted text is dark red and proposed or added text is vivid blue. Accepted text is plain LaTeX and therefore inherits the surrounding document color, normally black.

Preserve spaces needed around the macro invocation. Do not nest review macros. Avoid wrapping only part of a LaTeX command, citation, reference, label, or math delimiter. For display mathematics, tables, captions, and other fragile structures, stage the smallest complete syntactic unit and compile afterward.

## Propose revisions

1. Read the style profile and any relevant evidence policy before drafting.
2. Use `\reviewreplace` for substitutions, `\reviewadd` for insertions, and `\reviewdelete` for deletions.
3. Do not change the original text outside the review macro.
4. Compile the thesis and inspect any warnings or errors caused by the staged markup.

## List revisions

From the repository root:

```bash
python3 .agents/skills/thesis-review/scripts/revision_tool.py list Latex/main.tex
```

The tool assigns temporary numeric IDs in source order and reports each revision's type, line, and preview. IDs can change after revisions are accepted or rejected, so list again before every new operation.

## Preview and apply decisions

Preview acceptance of selected revisions:

```bash
python3 .agents/skills/thesis-review/scripts/revision_tool.py accept Latex/main.tex --id 1 --id 3
```

Apply after reviewing the diff:

```bash
python3 .agents/skills/thesis-review/scripts/revision_tool.py accept Latex/main.tex --id 1 --id 3 --write
```

Use `reject` instead of `accept` to restore the old wording. Use `--all` only when the author explicitly asks to accept or reject every staged revision:

```bash
python3 .agents/skills/thesis-review/scripts/revision_tool.py accept Latex/main.tex --all --write
```

Acceptance behavior:

- `\reviewreplace{old}{new}` becomes `new`.
- `\reviewadd{new}` becomes `new`.
- `\reviewdelete{old}` is removed.

Rejection performs the inverse. The helper defaults to a diff preview and never writes without `--write`. After applying decisions, list revisions again, inspect the Git diff, and compile the thesis.
