# Evidence and Citation Policy

Use this policy for claim audits, citation checks, literature verification, and citation-safe editing.

## Mechanical audit

Run:

```bash
python3 .agents/skills/thesis-review/scripts/citation_audit.py Latex/main.tex
```

The helper checks citation keys against discovered BibTeX files, duplicate keys, unused entries, essential metadata, and whether entries contain a DOI, URL, ISBN, or eprint. These checks establish bibliography consistency only; they do not verify semantic support.

## Claims that deserve scrutiny

Prioritize claims that are quantitative, causal, comparative, universal or broad, historically specific, attributed to prior work, operational, safety-relevant, or unusually novel. Also inspect sentences whose citation appears to support several independent propositions at once.

Claims derived directly from the thesis's own equations, code, tables, figures, or reported experiments may use internal evidence instead of an external citation. Identify the exact internal artifact and check that the prose does not exceed it.

## Verification levels

1. `metadata only`: title, authors, venue, year, DOI, or URL match a real record.
2. `source inspected`: abstract, full text, official standard, or dataset documentation was inspected.
3. `claim verified`: the inspected source directly supports the proposition at the stated scope.

Never report level 3 based only on metadata or a search-result snippet. If only an abstract is available, say so and avoid claiming support for details not present there.

## Source handling

- Prefer the cited paper, official standard, official dataset documentation, or publisher record.
- Record enough provenance for review: citation key, source title, DOI or stable URL when available, and page, section, table, or equation for semantic verification.
- When a cited source cannot be accessed, classify support as unclear rather than assuming agreement.
- When a source supports only part of a sentence, identify the supported and unsupported propositions separately.
- Do not add a citation suggested from memory. Verify its identity and relevance first, then use the existing key or propose a complete BibTeX entry for user review.
- Do not change an existing bibliography entry solely because external metadata uses different capitalization or punctuation; distinguish cosmetic normalization from identity errors.

## Claim-strength checks

Compare the thesis wording to the evidence along these dimensions:

- population or geographic scope;
- selected events versus continuous operation;
- simulated versus operational measurements;
- correlation or association versus causation;
- average performance versus every case;
- benchmark performance versus general deployability;
- model-consistent data versus noisy real-world data;
- proposed future work versus demonstrated capability.

Suggest the smallest correction that makes the claim defensible. Do not dilute a well-supported claim merely because cautious wording sounds more academic.

## Audit output

For each material finding, provide:

```text
severity | label | file:line
claim: concise paraphrase or short excerpt
evidence: citation key or internal artifact inspected
assessment: why support is missing, partial, or adequate
action: smallest safe revision or verification step
```

Keep a separate summary for mechanical citation results. Do not silently edit the thesis during an audit.
