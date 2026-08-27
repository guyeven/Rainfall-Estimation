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
- Proposed wording: remove the broad survey and close concisely by asking whether optimization-based reconstruction can improve upon IDW.
- Outcome: accepted in refined form and incorporated into the staged background revision.
- Author feedback: the earlier concise paragraph was already strong and aligned more directly with the thesis; naming IDW was preferred over the broader ``interpolation-based map construction,'' while repeating ``midpoint-based'' was unnecessary after its earlier definition.
- Reusable preference: close background sections by synthesizing the literature into the thesis's specific research question and name the evaluated baseline when a broader method-class label would overstate the experimental scope.

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

## Limit each citation to its verified claim

- Context: citations supporting the established use of IDW and ordinary kriging in rainfall interpolation appeared after sentences that also explained how the methods assign their weights.
- Proposed wording: place each citation immediately after the established-use claim, and present the uncited methodological explanation separately unless that explanation has also been verified from the source.
- Outcome: accepted and requested as an explicit thesis-review rule.
- Author feedback: a citation should always support the claim to which it is attached and should not appear to support more than the source establishes.
- Reusable preference: attach a citation to the smallest verified claim and separate adjacent definitions, mechanisms, comparisons, or consequences when their support differs.

## Organize related work around historical claims

- Context: the CML background followed the correct chronology but began to read as a sequence of equally weighted paper summaries after the rain-gauge and radar introduction.
- Proposed direction: retain the chronological progression while organizing the literature around a few claims: dedicated links established physical feasibility, operational CMLs established opportunistic feasibility, national studies established scalability, and reconstruction studies exposed the choice between interpolation and inverse methods.
- Outcome: accepted as the direction for the next staged revision.
- Author feedback: the diagnosis and proposed narrative spine were liked and should be retained in the review skill.
- Reusable preference: in historical related work, make each paragraph advance one interpretive claim and use individual papers as evidence for that claim; compress side details that do not move the thesis-specific narrative forward.

## Complete a methodological contrast before positioning the thesis

- Context: the interpolation paragraph ended by announcing the thesis baseline, after which the next paragraph resumed the earlier contrast with the abstract opening ``Inverse approaches instead retain the complete link paths.''
- Proposed wording: finish the interpolation discussion, introduce the alternative concretely as reconstructing a field directly from link attenuations rather than reducing links to points, and move the thesis baseline choice into the subsequent thesis-positioning paragraph.
- Outcome: the original transition was rejected as confusing and awkward; the clearer transition was staged for review.
- Author feedback: a new methodological category should connect naturally to the immediately preceding paragraph and should not begin with unexplained compressed terminology.
- Reusable preference: complete comparisons between method families before shifting to the thesis's choices, and introduce an unfamiliar method family through its concrete operation before applying an abstract label.

## Name all promised categories before discussing their members

- Context: a paragraph announced two broad reconstruction strategies and then immediately discussed IDW and ordinary kriging, both of which belong to the interpolation strategy; the second strategy appeared only in the following paragraph.
- Proposed wording: name both strategies in the opening sentence before explaining IDW and ordinary kriging as methods within the first strategy.
- Outcome: the original signposting was rejected as misleading; the explicit two-part preview was staged for review.
- Author feedback: when prose promises two strategies, the reader should not be left to mistake the first two algorithms mentioned for those strategies.
- Reusable preference: when announcing a fixed number of categories, identify every category before introducing subtypes or examples within the first category.

## Distinguish method origins from later applications

- Context: an appositive described IDW as an established rainfall-interpolation method and cited Ahrens (2006), whose paper applies IDW to rain-gauge data rather than introducing the method.
- Proposed wording: ``IDW assigns greater influence to nearby observations and has been applied to spatial rainfall interpolation (Ahrens, 2006).''
- Outcome: accepted and incorporated into the staged background revision; the broader attribution rule was also added to the thesis-review skill.
- Author feedback: citation wording and placement must not make a later application paper appear to have introduced or established a method.
- Reusable preference: distinguish foundational contributions from later uses; state whether a source introduced, adapted, applied, compared, or evaluated a method according to what it actually did.

## Do not force a binary taxonomy onto related reconstruction methods

- Context: the reconstruction discussion divided interpolation-based mapping and forward-model-based optimization into two broad strategies, then positioned the thesis as following the second strategy.
- Proposed framing: present the methods sequentially within the same reconstruction problem, describing their concrete modeling choices without first announcing a distinction between method families.
- Outcome: both the binary ``first strategy/second strategy'' framing and an explicit replacement distinction between two approaches were rejected as unnecessary; the sequential framing was accepted and incorporated into the staged background revision.
- Author feedback: interpolation also starts from link attenuation and reconstructs a rainfall field, so the discussion should move directly from interpolation methods to forward-model-based work without imposing a taxonomy.
- Reusable preference: when methods solve the same underlying problem through different approximations or representations, compare the concrete modeling choices without overstating them as mutually distinct strategies.
