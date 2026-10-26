# Appendix A. Model and Reproducibility Details

## A1. Purpose and model boundary

Pineland is a partially observed agent-based model of insurgency, counterinsurgency, political order, logistics, information, mobility, foreign assistance, and security-force development. The present paper uses a narrow partner-force production layer embedded within that broader model. The analysis does not claim that the full Pineland state space is required to generate every result reported here. Instead, the broader simulation supplies endogenous personnel survival, readiness, territorial control, movement, patrol, combat, command, and logistics states that feed the three service channels used in the paper.

The full repository contains an ODD-style model description and parameter documentation. This appendix summarizes the parts required to interpret the paper's experiments.

## A2. Entities, state, and scheduling

The production experiments use 1,000 agents distributed across 72 localities. The simulated world contains civilians, military and police personnel, armed organizations, political actors, localities, road and movement networks, territorial-control variables, logistics stocks and flows, command state, force-generation processes, and external-assistance overlays.

The model advances through deterministic seeded event scheduling. Combat, movement, patrol, logistics, command, recruitment/training, and political processes update the world state. The partner-force experiments introduce a common supported prehistory and then branch the same seed into continued-support and withdrawal trajectories. Stage 4 uses a support/withdrawal split at day 120 and observes outcomes at +7, +30, +90, +180, and +360 days. The structural service window begins at day 60 so pre-split constraint identity is measured over an active supported period rather than initialization.

## A3. Partner-force service channels

| Service | Demand | Indigenous service | External service |
|---|---|---|---|
| Force generation | Military losses during the measurement window | Indigenous training graduates | Incremental graduates enabled by external training support |
| Logistics | Military logistics demanded by presence, movement, patrols, and combat | Indigenous logistics delivered | External logistics delivered |
| Command | Command opportunities multiplied by a fixed 0.5 service requirement per opportunity | Indigenous command service | Supported command service above the indigenous level |

For service j with positive demand D_j, indigenous coverage is q_j^I = I_j / D_j and supported coverage is q_j^S = (I_j + E_j) / D_j. Zero-demand channels are inactive rather than assigned an arbitrary coverage value. The structural indigenous-coverage coordinate is the minimum active service ratio. The observed bottleneck is the active service with the lowest indigenous ratio.

The paper also reports smoother arithmetic, geometric, and harmonic feasibility aggregators in robustness analysis. These alternatives test whether qualitative signs depend entirely on a hard minimum.

## A4. Composite capability

Whole-force capability is distinct from service coverage. The primary composite is the geometric mean of five unit-scale retention components relative to the split-time reference state:

1. government-control retention;
2. military-personnel retention;
3. operational-formation survival;
4. geographic-coverage retention; and
5. operational-readiness retention.

If these components are g, p, f, c, and r, the primary composite is C = (g p f c r)^(1/5). Each component is bounded to [0,1]. Differences reported in the paper are therefore unit-scale synthetic-model effects, not percentage changes in historical combat effectiveness.

## A5. Stage-4 production campaigns

Stage 4 contains three frozen modules and 2,808 production worlds total.

| Module | Cells | Seeds per cell | Worlds | Core factors |
|---|---:|---:|---:|---|
| Autonomy Phase Map | 140 | 12 | 1,680 | Four nominal structures; five capacity levels per structure; support intensity 0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0 |
| Bottleneck Migration | 52 | 12 | 624 | Four starting structures; targeted force-generation, logistics, command, balanced, or no support; intensity 0, 0.5, 1.0, 1.5 |
| Substitution vs Development | 42 | 12 | 504 | Force-generation, logistics, or command target; moderate or severe weakness; substitution, development, hybrid, or no aid; intensity 0, 0.5, 1.0 |

The Phase Map balanced-support profile scales force-generation training support, logistics delivery/capacity, and command reliability/latency together. Exact cell coefficients are stored in `stage4_autonomy_phase_map_v1.json` and are not reconstructed from prose during analysis.

The Migration module uses target-specific substitution profiles. For example, the 1.0 force-generation substitution profile adds a 0.035 training-rate boost; the corresponding logistics and command profiles use their own delivery and reliability/latency parameters. The mechanism module uses mode-specific contracts. Development raises partner-owned productive capacity on a weekly cadence; substitution supplies removable external service; hybrid assistance combines the two.

## A6. Matched no-aid and post-completion diagnostics

The original frozen Stage-4 estimand compares continued support with withdrawal after a common supported prehistory. External review identified the need for a stricter benchmark. The revised analysis therefore matches every treated Phase-Map world to a zero-support control with the same nominal structure, capacity level, seed, and horizon.

For horizon h, supported effect S_h = C_h^ON - C_h^0, retained effect R_h = C_h^OFF - C_h^0, and dependency gap G_h = C_h^ON - C_h^OFF. These matched-control calculations were developed after Stage-4 completion and are labeled post-completion diagnostics throughout the paper.

A second post-completion diagnostic decomposes terminal service coverage. In worlds where logistics binds in both terminal branches, continued-support indigenous service is evaluated once against its observed supported demand and once against withdrawal-branch demand. Withdrawal indigenous service is likewise evaluated against supported-branch demand. These standardizations are descriptive calculations on frozen telemetry, not runtime interventions.

## A7. Prospectively frozen demand-clamp ablation

After external review, a separate mechanism experiment was designed to intervene directly on the requirement-expansion channel. Four representative Stage-4 scenarios were selected before production outcome observation. Each scenario is run in paired normal and demand-clamped form on 12 fresh seeds, yielding 8 cells and 96 worlds.

The demand-clamped runner advances the matched withdrawal branch and dynamically rescales the supported branch's logistics-consumption channels so that supported logistics demand tracks the withdrawal requirement while the original assistance package remains otherwise active. An engineering-only scratch seed was used before the freeze to verify numerical matching. The production seed namespace is separate from that calibration seed.

The frozen ablation uses the same 1,000-agent, 72-locality environment, day-120 split, and +7/+30/+90/+180/+360 observation horizons as Stage 4. Its contract, analysis script, runner, ARC wrapper, and inherited Stage-4 scientific foundation were frozen before production outcomes were observed. The first ARC submission failed at the freeze-validation gate and produced zero scientific shards; the corrected 64-artifact freeze was committed before the successful production launch.

The final 96-world production campaign passed the demand-matching manipulation check: median relative mismatch was 0.46 percent, the 95th percentile was 1.30 percent, and all 2,640 post-split intervals were within 5 percent. However, all 48 fresh-seed normal pairs produced a zero capped indigenous-coverage branch gap at every registered horizon, as did the clamped pairs. The precommitted attenuation is therefore zero but is not interpretable as evidence against requirement expansion, because the normal-arm retention outcome failed to reproduce. The clamp did materially change composite capability, confirming that the intervention itself was consequential.

## A8. Stage 5 coordinated-development extension

Stage 5 contains 92 cells and 16 matched seeds per cell, for 1,472 worlds. It crosses four nominal starting structures with single-, pair-, and triple-channel indigenous development. Two dose regimes are distinguished:

- equal channel dose, in which each active channel receives the full singleton dose and multi-channel arms therefore cost more; and
- equal total effort, in which a fixed normalized effort is divided across active channels.

The primary terminal outcome is +360-day retained partner-owned feasibility after the common developmental prehistory stops. The design prospectively specifies pairwise and three-way factorial interactions for equal-channel-dose complementarity and breadth premiums for equal-total-effort allocation.

The manipulation check is substantively important. By the treatment split, the nominal near-tie worlds are almost uniformly logistics-bound. The main paper therefore treats fixed-effort breadth results as evidence from realized single-bottleneck regimes rather than a clean test of the intended near-tie scope condition.

## A9. Historical validation

Historical validation follows a frozen four-case protocol covering Afghanistan, Iraq, Mali, and Colombia. The unit is assistance episode by military-service constraint by time. The coding records the initial bottleneck, assistance type, targeted improvement, demand expansion, post-relief bottleneck, indigenous replacement, support shock, observed response, strongest rival explanation, and source quality.

Sources are prioritized in the following order: oversight/audit material; contemporaneous official or declassified records; peer-reviewed research with primary evidence; major research institutions; and high-quality journalism. The historical analysis is used for process plausibility and scope conditions, not for population treatment-effect estimation.

## A10. Reproducibility and provenance

The repository stores machine-readable contracts, freeze manifests, analysis code, figure-generation code, compact evidence tables, and validators. Large raw HPC shards are retained outside ordinary Git history but are hash-addressed in task metadata. Production tasks record the source commit, contract hash, freeze hash, output hash, seed, and logical task index.

Terminology in the paper follows four distinct statuses:

- **prospectively frozen**: design or analysis artifacts committed before the corresponding production outcomes were observed;
- **precommitted**: an estimand or analysis rule contained in those frozen artifacts;
- **post-completion diagnostic**: an analysis developed after the original production campaign but computed only from frozen telemetry;
- **post-review prospectively frozen**: a new experiment motivated by external review but frozen before its own outcomes were observed.

Formal verification in the repository checks selected implementation invariants and algebraic consistency. It is an engineering assurance that the runtime follows the specified semantics, not empirical validation of the military theory.


