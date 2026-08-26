# Confirmed Style Feedback

The initial profile is inferred from the existing thesis and should be treated as provisional.

When the author explicitly evaluates an edit, append a compact entry containing:

- context and original wording;
- proposed wording;
- accepted, rejected, or modified outcome;
- the author's stated reason, if any;
- one narrow reusable preference supported by that feedback.

Do not store whole chapters here. Prefer short representative excerpts and do not turn subject-matter corrections into general style rules.

## Revision-markup visibility

- Context: staged replacements initially displayed old text in grey and proposed text in blue.
- Outcome: modified to dark red for old text and vivid blue for proposed text.
- Author feedback: the grey/blue distinction was too difficult to see and much stronger contrast was requested.
- Reusable preference: use strongly contrasting colors for old and proposed wording in tracked thesis revisions.

## Name only the transformed quantity

- Context: repeated references to the benchmark link model after explaining the virtual-frequency and homotopy transformations.
- Proposed wording: describe the later evaluation as using the ``untransformed benchmark link model.''
- Outcome: rejected.
- Author feedback: only frequency is transformed; polarization remains unchanged, so ``untransformed'' is broader than the actual distinction and the full polarization provenance should not be repeated unnecessarily.
- Reusable preference: when a transformation changes only one model attribute, name that attribute directly and rely on an earlier definition for unchanged benchmark assumptions.

## Use benchmark-frequency terminology after definition

- Context: repeated explanation of how final reconstructions are evaluated after virtual-frequency or homotopy optimization.
- Proposed wording: refer to evaluation at each link's benchmark frequency, and use ``benchmark forward model'' where the frequency contrast does not need to be restated.
- Outcome: accepted and finalized.
- Author feedback: this wording preserves the frequency-specific distinction without repeatedly restating the assigned polarization.
- Reusable preference: after a benchmark assumption has been defined, use concise terminology that names the changing quantity instead of repeating unchanged metadata.

## Refer explicitly to both attenuation measures

- Context: the conclusion summarized the two reported attenuation-mismatch measures as a singular shared metric.
- Proposed wording: state that every optimization-based solver had lower mean mismatch than IDW on both reported measures, computed at the benchmark link frequencies.
- Outcome: accepted and finalized.
- Author feedback: the conclusion should not imply that only one attenuation metric was reported.
- Reusable preference: when a result is supported by multiple reported measures, refer to them in the plural or name them explicitly.

## Preserve the original closing synthesis

- Context: the final sentence of the conclusion summarized the purpose of the proposed future-work directions.
- Proposed wording: enumerate operational measurements, temporal behavior, sensor fusion, and broader inverse approaches.
- Outcome: rejected; the original sentence was restored.
- Author feedback: the original final line was preferred.
- Reusable preference: retain a concise outcome-oriented synthesis in the final sentence instead of replacing it with a list of the preceding directions.

## Close on the central operational question

- Context: the original final sentence said that all proposed directions would test whether controlled-benchmark improvements transfer to realistic settings.
- Proposed wording: identify persistence of the improvements over IDW with operational CML data as the central question for future validation.
- Outcome: accepted and finalized.
- Author feedback: only the operational-measurement direction directly tests this question, so the closing sentence should not attribute that purpose to all of the future-work directions.
- Reusable preference: when a conclusion presents several kinds of future work, close on the main unresolved research question without implying that every direction tests it directly.

## End background with the thesis question

- Context: the background ended with a broad survey of current CML research directions before returning to the thesis's reconstruction question.
- Proposed wording: remove the broad survey and close concisely on the methodological choice between optimization-based reconstruction and interpolation-based map construction.
- Outcome: accepted and finalized.
- Author feedback: the earlier concise paragraph was already strong and aligned more directly with the thesis.
- Reusable preference: close background sections by synthesizing the literature into the thesis's specific research question rather than introducing loosely related current directions.

## Distinguish literature context from evaluated baselines

- Context: the reconstruction discussion called IDW a standard baseline without explaining how IDW and ordinary kriging became recurring CML mapping references.
- Proposed wording: explain that point representations of link estimates allow established interpolation methods to be applied, mention ordinary kriging and GMZ for context, and identify IDW as the principal interpolation baseline evaluated in the thesis.
- Outcome: accepted in modified form and incorporated into the background.
- Author feedback: the literature should justify the baseline status of IDW and ordinary kriging while making clear that methods mentioned for completeness are not all evaluated in the benchmark.
- Reusable preference: when reviewing related methods, separate the broader methodological landscape from the methods actually used as experimental baselines in the thesis.

## Attach citations to the claims they support

- Context: one citation group followed a sentence contrasting ordinary kriging in the Netherlands studies with IDW in the Germany-wide study.
- Proposed wording: place the Overeem citations directly after the ordinary-kriging clause and the Graf citation directly after the IDW clause.
- Outcome: accepted and incorporated into the tracked background revision.
- Author feedback: grouping the unlike sources made it difficult to tell which paper supported which method.
- Reusable preference: when a sentence contrasts different methods or studies, attach each citation to its corresponding clause instead of grouping all sources at the end.

## Organize related work around historical claims

- Context: the CML background followed the correct chronology but began to read as a sequence of equally weighted paper summaries after the rain-gauge and radar introduction.
- Proposed direction: retain the chronological progression while organizing the literature around a few claims: dedicated links established physical feasibility, operational CMLs established opportunistic feasibility, national studies established scalability, and reconstruction studies exposed the choice between interpolation and inverse methods.
- Outcome: accepted as the direction for the next staged revision.
- Author feedback: the diagnosis and proposed narrative spine were liked and should be retained in the review skill.
- Reusable preference: in historical related work, make each paragraph advance one interpretive claim and use individual papers as evidence for that claim; compress side details that do not move the thesis-specific narrative forward.
