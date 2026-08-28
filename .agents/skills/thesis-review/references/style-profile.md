# Initial Style Profile

Inferred on 2026-08-26 from representative prose in `Latex/main.tex`, including the introduction, background, methodology, evaluation, and conclusion. Treat this as an initial model of the author's preferences and refine it only from explicit feedback.

## Voice and stance

- Use restrained, formal academic prose with first-person plural (`we`) for the thesis's choices, procedures, and evaluations.
- Prefer precise claims over promotional language. State limitations and non-deployable conditions directly.
- Distinguish controlled benchmark results from operational implications. Qualify generalization claims by the data, network geometry, forward model, and evaluation setting.
- Use cautious but concrete modal language: `may`, `could`, `suggests`, `does not establish`, and `would require` when evidence is incomplete.

## Sentence and paragraph movement

- Favor medium-length explanatory sentences, with occasional longer sentences when a comparison or qualification must remain logically connected.
- Use short declarative sentences to define a quantity, establish a transition, or clarify an interpretation.
- Make logical relations explicit with connectors such as `because`, `therefore`, `while`, `whereas`, `rather than`, `consequently`, and `at the same time`.
- Build paragraphs in a visible sequence: introduce the object or question, explain the mechanism or method, then state the consequence, comparison, or limitation.
- Use signposting when it names real structure (`We first report...`, `We next ask...`), but avoid generic roadmap filler.

## Technical exposition

- Define specialized terms and abbreviations before relying on them.
- Introduce equations with prose, define symbols locally, and interpret metrics after presenting them.
- Keep comparisons explicit: name both methods, the metric or criterion, and the relevant experimental scope.
- Report numerical results with units, sample context, and threshold definitions. Keep benchmark-dependent thresholds visibly qualified.
- Prefer concrete methodological descriptions over compressed jargon.

## Established terminology

- Preserve terms such as `commercial microwave link (CML)`, `rainfall field`, `rainfall map`, `rain rate`, `rain-induced attenuation`, `radar-derived ground truth`, `forward model`, `benchmark patch`, `link path`, and the solver names used in the thesis.
- Preserve established compounds and hyphenation, including `optimization-based`, `interpolation-based`, `path-averaged`, `patch-level`, `pixel-level`, `wet/dry`, `ground-truth` when adjectival, and `near-real-time`.
- Do not vary terminology merely for stylistic variety when the terms denote technical concepts.

## Editing preferences inferred from the draft

- Prefer direct explanation over ornamental phrasing, rhetorical questions, or dramatic framing.
- Prefer sentences that are clear on the first reading and easy to understand. In background and related-work summaries, state the thesis-relevant methodological idea directly and introduce specialized terms only when they advance the argument.
- Avoid vague intensifiers (`very`, `clearly`, `significantly`) unless they have a defined statistical or technical meaning.
- Avoid generic AI-style conclusions such as `This highlights the importance of...` when the specific implication can be stated.
- Avoid converting clear verbs into unnecessary nominalizations.
- Do not split a logically connected qualification into choppy sentences solely to shorten the prose.
- Remove repetition only when it does not erase a needed reminder of experimental scope.

## Style-check decision rule

Prioritize, in order: factual fidelity, claim strength, mathematical and LaTeX correctness, clarity, then stylistic similarity. If a style-matched sentence remains ambiguous, propose a clearer alternative and explain the tradeoff rather than imitating the ambiguity.
