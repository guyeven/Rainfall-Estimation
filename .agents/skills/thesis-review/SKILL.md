---
name: thesis-review
description: Review and revise this LaTeX thesis for questionable claims, citation integrity, consistency with the author's academic style, and color-coded tracked text replacements. Use for thesis audits, citation-safe revisions, staged edits, and accepting or rejecting proposed wording; do not use for unrelated repository documentation.
---

# Thesis Review

Review the thesis as a skeptical academic editor while preserving its technical meaning and the author's voice.

## Boundaries

- Default to a read-only report. Edit `.tex` or `.bib` files only when the user explicitly asks for edits.
- Never invent a source, citation key, bibliographic field, quotation, page number, result, or verification status.
- Keep citation attribution unambiguous. When a sentence contrasts papers, methods, or findings, attach each citation directly to the clause it supports rather than collecting unlike sources in one citation group.
- Do not silently strengthen a claim. Preserve distinctions between observation, inference, assumption, hypothesis, and proposed future work.
- Preserve LaTeX commands, labels, citations, equations, units, and established terminology unless a requested correction requires changing them.
- Treat the radar-derived benchmark as controlled and synthetic where the thesis does; do not imply operational validation.

## Choose the workflow

### Evidence or citation audit

Read [references/evidence-policy.md](references/evidence-policy.md). Run `scripts/citation_audit.py` on the main `.tex` file before semantic source checking. Use local source PDFs when available; use web research only when permitted and necessary.

### Style review or revision

Read [references/style-profile.md](references/style-profile.md). Apply the profile as a preference, not as a reason to preserve unclear prose. For each material rewrite, preserve the original claim strength and cite any uncertainty.

### Color-coded tracked revisions

Read [references/revision-workflow.md](references/revision-workflow.md). Stage proposed wording with the thesis's review macros. Before accepting or rejecting revisions, list them with `scripts/revision_tool.py`, confirm the intended scope, preview the diff, and mutate the source only after explicit authorization.

### Learn from feedback

Read [references/feedback-examples.md](references/feedback-examples.md). When the user explicitly accepts or rejects an edit, update that file with the smallest generalizable lesson. Do not infer a permanent rule from a single ambiguous reaction. Revise the style profile only after a preference is clear or repeated.

## Reporting

For audits, report findings in descending importance with the exact file and line number. Use these labels when applicable:

- `unsupported`: no supporting citation or internal result was found.
- `support unclear`: the source exists, but the available evidence does not establish the claim.
- `overstated`: the wording is stronger or broader than the evidence.
- `citation integrity`: a citation key, entry, identifier, or attribution is missing or inconsistent.
- `style mismatch`: wording departs materially from the established profile.
- `verified`: use only when the relevant source content, not merely its metadata, was inspected.

Separate mechanical bibliography findings from semantic claim-support findings. A valid DOI or existing paper does not prove that the cited source supports the sentence.
