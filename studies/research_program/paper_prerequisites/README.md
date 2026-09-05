# Paper prerequisites for the eventual substantive general-theory / methods paper

This directory is **paper infrastructure, not a manuscript and not a result**.
It exists so work that is safe under an unfinished research program can be
completed early without converting provisional mechanisms, synthetic
identification, or legacy historical runs into stronger claims than the
evidence supports.

## Target contribution

The intended eventual contribution has three inseparable layers:

1. **Substantive theory**: a transferable account of how insurgent
   organizations establish, reproduce, persist, relocate, lose, and regain
   viable local political-military presence and control.
2. **General method**: a partially observed, mechanism-explicit simulation and
   identification framework that separates latent state, actor belief,
   researcher observation, measurement error, and recorded evidence.
3. **Comparative empirical adjudication**: frozen, case-specific observation
   operators and holdouts that can reject the model or individual mechanisms,
   with simpler statistical and reduced-mechanism competitors.

None of those three layers is currently declared complete. The research
program remains in progress and the candidate theory can still change.

## Safe to build now

The following are deliberately independent of whether the current candidate
theory ultimately survives:

- the contribution and non-claim contract;
- claim-language and evidence-promotion rules;
- manuscript section architecture and completion gates;
- figure and table shells with explicit data dependencies;
- construct / estimand / observation-operator inventories;
- the reproducibility appendix contract;
- the negative-result reporting requirement;
- the literature-gap work plan;
- an automatically regenerated prerequisite-status artifact.

These can be revised for clarity, but they should not be revised merely
because a historical result is inconvenient.

## Deliberately blocked

The following are not safe to finalize while the research program is still
moving:

- the paper title as a statement of a discovered general law;
- the final abstract;
- the final theory proposition set;
- historical effect-size or predictive-performance tables;
- claims of generality, causal efficacy, or policy effectiveness;
- a final mechanism ranking;
- a final cross-case synthesis;
- a final discussion or conclusion that presumes the theory survived.

## Relationship to the research program

The paper layer consumes the existing research contracts rather than replacing
them. In particular, it must remain consistent with:

- `../theory_extraction_protocol.json`;
- `../mechanism_registry.json`;
- `../outcome_measurement_contract.json`;
- `../case_ladder.json`;
- `../comparative_theory_promotion_matrix.json`;
- `../core_freeze.json`;
- `../program_audit.json`.

The status builder in `../scripts/build_paper_prerequisite_status.py` reads
those artifacts and fails closed: stale core provenance, no eligible transfer
cases, or an unlicensed general-theory promotion leaves the corresponding
paper claims blocked.

## Rule for future drafting

Paper prose must be downstream of evidence status. A sentence is not promoted
because it is rhetorically attractive, because a mechanism is plausible, or
because a single historical case appears to fit. Claim strength is determined
by the evidence ladder in `claim_language_contract.json`, and every eventual
result figure or table must name the artifact(s) that produced it.

