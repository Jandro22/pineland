# Claim to evidence matrix

This file controls drafting and keeps frozen results, post-completion diagnostics, and post-review experiments distinct.

| Claim | Evidence | Status | Manuscript use |
|---|---|---|---|
| Continued support minus withdrawal is not the same estimand as support minus no aid | `evidence/review_revision/stage4_control_matched_*` | Post-completion matched-control diagnostic | Core measurement result |
| At +30d, 26/120 treated Phase-Map cells have supported capability above no aid and retained capability below no aid | `stage4_control_matched_summary_v1.csv` | Post-completion diagnostic | Strong success-without-retention regime |
| At +30d, 30/120 treated cells improve both supported and retained capability relative to no aid, while 51/120 are below no aid in both | Same matched-control evidence | Post-completion diagnostic | Heterogeneity result |
| The original frozen branch contrast gives 106/120 positive +30d continued-support-vs-withdrawal cells; 96/106 also have negative +360d indigenous coverage | Stage-4 Phase-Map evidence | Frozen Stage-4 estimand | Branch-gap result only, not net success vs no aid |
| Terminal logistics-coverage gaps reflect both indigenous service and service demand | `stage4_supply_demand_decomposition_v1.json` | Post-completion telemetry decomposition | Core mechanism diagnostic |
| In 1,174 same-terminal penalty worlds, 95.9% have higher supported-branch logistics demand and 19.8% have lower indigenous logistics delivery | Same evidence | Post-completion diagnostic | Requirement-expansion evidence |
| In +30d-effective logistics-penalty worlds, mean observed coverage gap is about -0.0823, production-only -0.0301, demand-only -0.0534 | `stage4_demand_standardization_summary_v1.csv` | Post-completion descriptive standardization | Not a runtime causal intervention |
| The 96-world demand clamp passes its manipulation check but all 48 fresh-seed normal pairs reproduce zero coverage branch gap at every registered horizon | `evidence/mechanism_ablation/` | Post-review prospectively frozen experiment | Failed outcome-replication prerequisite; does not identify requirement expansion as retention mediator |
| Matched command migrates 38/38, force generation 46/46, logistics 0/85 | `migration_target_match_summary_v1.csv` | Frozen Stage-4 Migration result | Constraint-displacement result |
| Constraint displacement does not explain the strongest terminal coverage penalty | Migration evidence plus `stage4_migration_penalty_summary_v1.csv` | Frozen result plus post-completion synthesis | Core revision |
| Force-generation relief can migrate universally while yielding approximately zero +30d composite-capability gain | Migration compact evidence | Post-completion aggregation of frozen summaries | Relief-without-yield illustration |
| Static headroom does not monotonically predict dynamic yield | `stage4_headroom_*` | Post-completion reconstruction | Qualifying negative result |
| Developmental logistics improves partner-owned service and terminal coverage relative to substitution but does not uniformly dominate on early capability or modeled donor cost | Stage-4 mechanism evidence | Frozen result plus frontier synthesis | Capability-retention-cost tradeoff |
| Force-generation development can raise local indigenous output with zero whole-system coverage improvement | Stage-4 mechanism evidence | Frozen contrast | Local-system divergence |
| Smooth aggregators agree in sign with the hard minimum in 167/169 observed-matched Migration worlds | Stage-4 robustness evidence | Frozen robustness analysis | Metric robustness |
| Stage 5 finds selective equal-dose pairwise complementarity | Stage-5 factorial interactions | Prospectively frozen result | Secondary result with multiplicity/ceiling caveats |
| Stage 5 does not cleanly test fixed-budget breadth under true near-ties because 365/368 nominal near-tie worlds are logistics-bound at the split | Stage-5 bottleneck paths | Prospectively frozen manipulation check | Scope limitation |
| Structural sidecar shows all three services are reachable terminal constraints but none of four intended migration paths occurs | structural-falsification evidence | Prospectively frozen sidecar | Supplemental architecture check only |
| Historical cases provide structured process plausibility and scope conditions, not causal estimates | source-audited case memos | Frozen case protocol plus source audit | External validation |
| Generic bottleneck migration, complementarity, recurrent-cost burdens, and supported-vs-sustainable distinctions are prior art | literature audit | External literature | Novelty boundary |
| Pineland numerical thresholds directly estimate real partner forces | none | Unsupported | Prohibited |
| The model identifies an optimal real-world donor allocation rule | none | Unsupported | Prohibited |
