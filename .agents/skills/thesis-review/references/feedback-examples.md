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

## Explain why selectively cited related works were chosen

- Context: the reconstruction discussion selected Zinevich et al. and Bianchi et al. from a much larger CML rainfall literature without first stating the methodological reason for discussing those papers.
- Proposed direction: identify the specific feature that makes each selected work relevant to the thesis, such as joint forward-model-based inversion or explicit cost-function optimization, before explaining how its setup differs.
- Outcome: requested as a requirement for the next revision of the related-work comparison.
- Author feedback: when only a few papers are mentioned, the reader should understand why those works were selected instead of the many other CML mapping studies.
- Reusable preference: justify selective examples by a verified thesis-relevant property, avoid implying exhaustiveness, and do not group papers under a methodological label that does not accurately apply to every paper in the group.

## Avoid redundant method catalogues

- Context: a related-work paragraph already introduced why four reconstruction papers were selected and then described the concrete formulation used by each.
- Proposed wording: close by cataloguing the papers as combinations of iterative equation solving, sparse recovery, dynamic estimation, and sensor fusion.
- Outcome: rejected; the closing sentence was removed.
- Author feedback: the summary sentence was not liked after the individual descriptions.
- Reusable preference: when a paragraph's opening and examples already establish its organizing claim, do not end with a second abstract taxonomy of the same methods.

## Separate literature overview from thesis positioning

- Context: the reconstruction background followed an overview of prior inverse and optimization-based methods with a second paragraph that justified which papers were closest to the thesis and listed pairwise differences.
- Proposed wording: present the prior methods once as a chronological overview, then introduce the thesis formulation, benchmark, and evaluated baseline without defending its difference from each paper.
- Outcome: accepted and finalized in the background revision.
- Author feedback: an overview of work taking the optimization route was preferred to repeated statements that the thesis differs from each selected study.
- Reusable preference: use related-work paragraphs to explain the development of a methodological line, then position the thesis concisely; avoid turning the thesis-positioning paragraph into a paper-by-paper defense.

## Avoid a second closing summary after thesis positioning

- Context: a concise closing paragraph repeated the controlled benchmark, optimization-based reconstruction, and comparison with IDW immediately after a fuller thesis-positioning paragraph had been added.
- Proposed revision: delete the repeated closing paragraph and allow the thesis-positioning paragraph to close the background section.
- Outcome: accepted and finalized; the repeated paragraph was deleted.
- Author feedback: the former closing sentence reads as extra after the revised positioning paragraph.
- Reusable preference: once the final related-work paragraph clearly states the thesis setup and comparison, do not follow it with a shorter restatement of the same research question.

## Explain observation models concretely

- Context: the reconstruction problem concluded that mapping requires a ``physical observation model,'' a technically accurate but unexplained term at that point in the background.
- Proposed wording: describe it as ``a mathematical model relating rainfall to link attenuation.''
- Outcome: accepted and finalized as part of a shorter reconstruction-problem paragraph.
- Author feedback: the clearer wording was preferred when revising the reconstruction-problem paragraph.
- Reusable preference: when a specialized modeling term is not needed for later exposition, state directly which underlying quantity the model relates to which observation.

## Restate only the premise needed for a new conceptual point

- Context: the reconstruction-problem paragraph repeated that CML measurements cover paths and again described endpoint, frequency, and polarization metadata after those ideas had already been introduced or would be explained later.
- Proposed wording: retain the path-level observation as a brief premise, then focus on non-uniqueness, unsampled areas, and the need for spatial assumptions.
- Outcome: accepted and finalized in a compressed three-sentence paragraph.
- Author feedback: some of the fuller explanation appeared to be implied by the preceding background.
- Reusable preference: when earlier prose already establishes the measurement mechanism, restate only what is necessary to support the next methodological consequence.

## State why a comparison paper is cited

- Context: Eshel et al. was cited in a long clause about evaluating IDW and ordinary kriging on the same CML datasets against radar reference fields.
- Proposed wording: state separately that the paper directly compared IDW and ordinary kriging for CML rainfall mapping, then use that fact to motivate the methods as references.
- Outcome: accepted and finalized.
- Author feedback: retaining Eshel was acceptable once its distinct role in the paragraph was made clear.
- Reusable preference: when citing a direct comparison to justify reference methods, state the compared methods plainly and omit experimental detail that does not serve that justification.

## Prefer prose compression for small page overflows

- Context: the background chapter spilled only its closing lines onto a third page.
- Proposed wording: tighten the radar explanation, condense the Eshel comparison rationale, and shorten the thesis-positioning paragraph without changing the chapter's chronological structure.
- Outcome: accepted provisionally, with the preceding version retained in a Git checkpoint in case the two-page layout is later reconsidered.
- Author feedback: the revised chapter should fit naturally on two pages, but the earlier wording may be restored if the result feels too compressed.
- Reusable preference: when a chapter narrowly exceeds its intended length, first remove repetition and compress supporting detail while preserving the central explanation and narrative structure; avoid changing global typography or margins.

## Keep background positioning focused

- Context: the final background paragraph stated both the thesis's reconstruction comparison and how radar-derived fields were used to generate observations and evaluate results.
- Proposed revision: delete the sentence explaining the radar-derived fields' benchmark roles.
- Outcome: accepted and finalized.
- Author feedback: the radar-derived-field sentence should be removed.
- Reusable preference: close the background with the thesis's methodological question and evaluated comparison; defer benchmark-construction details that are explained in the methodology.

## Combine conceptual positioning with supporting metrics

- Context: a conclusion sentence described ILDW as a useful link-aware modification of IDW.
- Proposed wording: replace that conceptual description with its RMSE, correlation, and signed-bias comparison against IDW.
- Outcome: accepted and finalized after the conceptual description and comparison were combined into one sentence.
- Author feedback: both ideas should remain, but repeating the full explanation of midpoint-based interpolation made the conclusion unnecessarily long.
- Reusable preference: when a conclusion establishes a method's conceptual role and comparative performance, combine them concisely when the underlying mechanism has already been explained.

## Match the verb to the depth of coverage

- Context: Chapter 2 stated that ordinary kriging was ``discussed for context'' although it received only brief contextual coverage.
- Proposed wording: replace ``discussed'' with ``mentioned.''
- Outcome: accepted and finalized.
- Author feedback: ``discussed'' sounded stronger than the treatment ordinary kriging actually receives.
- Reusable preference: use ``mentioned'' rather than ``discussed'' when a method is included briefly for completeness but is not explained or analyzed in depth.

## Avoid unquantified result intensifiers

- Context: the abstract stated that optimization-based reconstruction ``substantially improves upon IDW'' before naming the evaluated metrics.
- Proposed wording: remove ``substantially'' while retaining the reported improvement in patch-level RMSE and Pearson correlation.
- Outcome: accepted and finalized.
- Author feedback: the less promotional, metric-specific wording should be used.
- Reusable preference: avoid qualitative effect-size adjectives in result summaries unless they are defined or quantified; state the metric comparison directly.

## Separate benchmark runtime from operational suitability

- Context: the evaluation summary said that a 76.03-second mean benchmark runtime suggested potential for near-real-time use.
- Proposed wording: describe the runtime as an initial computational reference and leave compatibility with near-real-time operation conditional on the update interval and end-to-end latency.
- Outcome: accepted and finalized.
- Author feedback: the operational implication should be made more cautious.
- Reusable preference: report benchmark runtime directly without inferring operational suitability unless the target update interval and full processing latency are established.

## Add a focused bridge without expanding the paragraph

- Context: the thesis-positioning paragraph followed related work that retained complete link paths, but did not explicitly connect the thesis formulation to that discussion.
- Proposed wording: expand the methodological sentence to enumerate path-based attenuation disagreement, spatial changes, oscillation, and rainfall magnitude.
- Outcome: rejected and replaced with the short sentence ``The formulation likewise retains the complete link paths within the reconstruction,'' preserving the original paragraph structure and level of detail.
- Author feedback: the intended change was to make the transition from the preceding reconstruction discussion smoother, not to add a fuller summary of the objective; an attempted explanation about predicting attenuation from the reconstructed field was also unnecessarily difficult to understand.
- Reusable preference: when continuity is the issue and the mechanism has already been explained, add one focused bridging sentence rather than restating the mechanism or overloading the following paragraph with methodological detail.

## State benchmark scope instead of unnecessary grid detail

- Context: the final background paragraph described estimating each rainfall field ``independently on a uniform grid.''
- Proposed wording: ``We estimate each rainfall field in the benchmark from simulated link attenuations by balancing attenuation agreement against spatial smoothness.''
- Outcome: accepted and finalized with the surrounding revised paragraph.
- Author feedback: naming the uniform grid was unnecessary here; identifying the fields as belonging to the benchmark made the scope clearer without introducing methodological detail.
- Reusable preference: in concise thesis-positioning prose, state the experimental scope directly and defer representation details such as grid structure to the methodology unless they support an explicit comparison.

## Prefer simple related-work descriptions

- Context: the Roy et al. summary described a constrained optimization problem through ``agreement with link attenuations, temporal evolution, sparsity, and non-negativity.''
- Proposed wording: describe the work as dynamic rainfall reconstruction combining agreement with link attenuations with a model of rainfall evolution over time.
- Outcome: accepted and finalized.
- Author feedback: the simpler sentence was preferred, where ``simpler'' specifically means clear on the first reading and easy to understand; this preference should be retained in the thesis-review skill.
- Reusable preference: prefer sentences that communicate their meaning on the first reading; in related-work summaries, describe the thesis-relevant methodological idea directly and omit specialized objective terms when they are not needed for the comparison.

## Keep historical milestones concise

- Context: the historical overview described Giuli et al. as showing through simulation that measurements from several microwave paths could be combined to reconstruct a spatial rainfall field.
- Proposed wording: expand the sentence to describe a tomographic formulation based on multiple path-integrated attenuation measurements and its simulated feasibility.
- Outcome: rejected; the existing shorter sentence was retained.
- Author feedback: the existing wording was preferred.
- Reusable preference: in a chronological overview, keep a clear milestone description when additional methodological terminology does not materially improve the narrative.

## Describe the selected baseline without implying a hierarchy

- Context: the thesis-positioning paragraph called IDW ``the principal interpolation baseline'' while ordinary kriging was mentioned only for context.
- Proposed wording: remove ``principal'' and state directly that the solver variants are compared with IDW.
- Outcome: the hierarchical wording was rejected.
- Author feedback: ``principal'' was not considered justified because it could imply that IDW is generally more important than other interpolation methods.
- Reusable preference: identify a method as the baseline evaluated in this thesis without using hierarchical labels that could be read as broader claims about the literature.
