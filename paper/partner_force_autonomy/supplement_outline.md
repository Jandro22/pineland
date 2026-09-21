# Supplementary Appendix

## Purpose and status

This file is the working architecture for the supplementary material to
**Suffering from Success: Security Assistance, Constraint Migration, and
Partner-Force Autonomy**. It separates material required for scientific audit
from the main-text argument. Sections tied to Stage-5 outcomes or unfinished
historical coding remain explicitly marked as pending until their frozen
analyses are complete.

## Appendix A. Model architecture and service semantics

### A.1 World, agents, and scheduler

Document the Pineland world, localities, population, organizations, event
scheduler, deterministic random-number handling, and the relationship between
the general insurgency model and the partner-force subsystem.

### A.2 Partner-force service channels

For force generation, logistics, and command, report:

- service-demand definition;
- indigenous-service definition;
- removable external-service definition;
- units and normalization;
- treatment levers;
- branch behavior at withdrawal;
- relevant runtime source locations.

### A.3 Capability and autonomy coordinates

Report the hard-minimum indigenous-autonomy coordinate, capped feasibility,
supported capability, and arithmetic, geometric, and harmonic robustness
aggregators. Distinguish structural coordinates from empirical estimands.

### A.4 Treatment timing and cloning

Describe the common 120-day prehistory, exact branch split, horizons at +7,
+30, +90, +180, and +360 days, and which state variables are preserved when
additional donor input stops.

## Appendix B. Formal theory

### B.1 Definitions

State the service coverage definitions, binding-constraint operator, and
nonnegativity/positive-demand assumptions.

### B.2 Capacity-growth versus demand-growth theorem

Include the exact Lean theorem corresponding to the cross-multiplied service
ratio condition and a plain-language interpretation. The appendix should report
the theorem name, source file, toolchain, and axiom audit without reproducing
irrelevant generated proof artifacts.

### B.3 Headroom as a local structural diagnostic

Define

\[
H_t=q_{(2),t}^{I}-q_{(1),t}^{I}
\]

and explain precisely why it is an immediate static diagnostic rather than a
dynamic causal bound once treatment changes demand or service ordering.

### B.4 Complementarity estimands

Define the Stage-5 pairwise and three-way factorial interaction terms and the
equal-total-effort breadth premium.

## Appendix C. Stage-4 design and complete results

### C.1 Cryptographic freeze and production provenance

List production commit, freeze hash, contracts, seed namespaces, task counts,
postprocessing commit, and READY manifests.

### C.2 Phase Map full results

Provide all 140 cell summaries, including controls, with means, medians,
quantiles, bootstrap intervals, seed fractions, and robust classifications.

### C.3 Migration full results

Provide all 52 cells and world-level observed-target-match summaries. Include
pre-treatment bottleneck, persistent migration, migration timing, modal
post-treatment bottleneck, path entropy, +30-day capability effect, and +360-day
autonomy effect.

### C.4 Relief-yield-retention synthesis

Reproduce the weighted observed-matched target table from the compact evidence
and label it as post-completion descriptive synthesis. Add a headroom analysis
only if it can be derived reproducibly from frozen telemetry without changing
the Stage-4 confirmatory status.

### C.5 Substitution versus development full results

Provide all treatment-mode contrasts for every target, weakness level, and
intensity, including local indigenous-output effects and whole-system autonomy
effects.

## Appendix D. Robustness and falsification

### D.1 Alternative feasibility aggregators

Report hard-minimum versus arithmetic, geometric, and harmonic sign
concordance, including the two discordant observed-matched worlds.

### D.2 Distributional sensitivity

Report medians, quantiles, seed-level sign fractions, and heavy-tail behavior in
addition to means.

### D.3 Observed versus nominal bottlenecks

Show why nominal starting labels are insufficient and reproduce the observed
pre-withdrawal constraint distributions.

### D.4 Structural-falsification status

Document any additional compact structural falsification test separately from
the original Stage-4 program. It must be capable of weakening the logistics-sink
interpretation and must not be presented as preregistered Stage-4 evidence.

## Appendix E. Stage-5 coordinated indigenous development

### E.1 Prospective status

Report the frozen commit, contract hash, protocol hash, analysis hash, and the
fact that Stage-4 outcomes motivated the question while Stage-5 outcomes were
unobserved at freeze.

### E.2 Design

List the 92 cells, four starting structures, two intensities, seven nonempty
channel combinations, equal-total-effort regime, equal-channel-dose regime, and
16 common-random-number seeds.

### E.3 Complete Stage-5 results

**Pending frozen production and postprocessing.** Report every preregistered
structure-by-intensity contrast regardless of direction.

### E.4 Complementarity and breadth

**Pending.** Report pairwise interactions, three-way interaction, fixed-effort
breadth premiums, retained capability, terminal autonomy, and constraint
dynamics.

## Appendix F. Historical external validation

### F.1 Frozen protocol and coding rules

Reproduce the unit of analysis, source hierarchy, observable implications,
evidence-strength scale, rival-explanation requirement, and amendment rule.

### F.2 Afghanistan

Insert the final coded episode table and narrative synthesis after source audit.

### F.3 Iraq

Insert the final coded episode table and narrative synthesis after source audit.

### F.4 Mali

Preliminary coding is complete in `historical_cases/mali_v1.md`. Finalize the
source-by-source audit, retain the pre-existing-constraint objection, and avoid
upgrading the case to clean migration evidence unless the chronology supports
it.

### F.5 Colombia

Preliminary coding is complete in `historical_cases/colombia_v1.md`. Finalize
the source audit around contractor reduction, Army aviation nationalization,
and the slower Regional Helicopter Training Center transition.

### F.6 Cross-case matrix

Report initial constraint, assistance type, targeted improvement, demand
expansion, post-relief constraint, indigenous replacement, withdrawal/support
shock, rival explanation, evidence strength, and theory fit for every coded
episode.

## Appendix G. Reproducibility

Provide exact commands for:

- regenerating contracts and cryptographic freezes;
- building the Rust production binary;
- launching or reproducing Stage-4 and Stage-5 tasks in an authorized compute
  environment;
- merging shards and verifying task metadata;
- reproducing compact evidence tables;
- regenerating manuscript figures;
- running manuscript and evidence validators;
- running the Lean build and axiom audit.

The public replication package should exclude credentials, cluster-specific
private paths, and publication-sensitive historical raw material while
preserving enough frozen artifacts to reproduce every manuscript number.

## Appendix H. Literature novelty map

### H.1 Security-assistance antecedents

Map principal-agent, influence, fragmentation, sustainability, autonomy, and
security-cooperation evaluation literatures against the paper's causal sequence.

### H.2 General systems and development antecedents

Summarize Theory of Constraints, Hirschman's unbalanced growth, recurrent-cost
and project-proliferation theories, premature load bearing, O-ring
complementarity, and absorptive capacity.

### H.3 Adversarial novelty scorecard

Reproduce the four-component scorecard from `literature_audit.md` so the
supplement makes explicit which component propositions are prior art and which
conjunction the paper claims as its contribution.
