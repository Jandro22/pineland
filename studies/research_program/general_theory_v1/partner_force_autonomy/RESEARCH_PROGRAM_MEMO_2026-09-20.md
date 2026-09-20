# Partner-Force Autonomy Research Program Memo — 2026-09-20

> **Purpose.** Preserve the scientific findings, caveats, theory development,
> literature-adjusted priorities, repair requirements, and post-repair ARC
> experiment plan that emerged from the September 20 Stage-3 analysis.
>
> **Status boundary.** The numerical findings in this memo are **exploratory,
> pre-repair evidence only**. A real command-support monotonicity defect was
> discovered after these results were generated. They motivate the next
> experiments but must **not** be quoted as final Stage-3 estimates. Final
> inference requires a clean, single-commit, post-repair 720/720 rerun.

## 1. Research objective

The project should not stop at the familiar claim that partner forces need
"indigenous capacity" or that foreign assistance can create dependence. Those
ideas are already well represented in the security-force-assistance (SFA),
security-sector-reform, defense-institution-building, principal-agent, and
sustainment literatures.

The stronger target is a dynamic theory:

> **External assistance is an endogenous intervention into a partner's
> capability-production system. It changes not only current capability, but
> future indigenous production, operational demand, the location of binding
> constraints, organizational structure, and the trajectory by which external
> support can or cannot be replaced.**

The one-paper objective is therefore to identify **when effective assistance
builds autonomy and when it erodes autonomy**, then explain the transition with
two mechanisms:

1. **indigenous response versus assistance-enabled demand growth**, and
2. **migration of the binding constraint after successful bottleneck relief**.

The intended causal chain is:

```text
external support
    -> relief of the current binding constraint
    -> immediate operational capability gain
    -> expansion/change in operational demand
    -> indigenous production response (or substitution)
    -> autonomy gain or autonomy erosion
    -> migration of the binding constraint
```

This is the organizing theory for the next major ARC program.

---

## 2. Critical Stage-3 design interpretation

Stage 3 does **not** compare "supported from the beginning" with "never
supported."

All experimental worlds receive their configured support through day 120.
At day 120 the simulation state is cloned:

- `SUPPORT_ON`: support continues;
- `SUPPORT_OFF`: the designated external support is withdrawn.

The two branches therefore share the same supported prehistory. Stage 3
directly estimates the effect of **continuing support versus withdrawing it
after a common 120-day supported period**.

This matters for interpretation:

- it can identify the effects of continued support after a common assisted
  history;
- it cannot by itself identify the effect of assistance from the start versus
  a truly never-supported counterfactual;
- a later design should include a `NO_SUPPORT_FROM_START` branch when the
  scientific question requires that distinction.

The post-repair program should preserve this estimand distinction explicitly.

---

## 3. Formal autonomy concept

The formal adapter represents force generation, logistics, and command as
service channels with demand `D`, indigenous service `I`, and external service
`E`.

For active channels:

```text
q_indigenous_j = I_j / D_j
q_supported_j  = (I_j + E_j) / D_j
```

Structural mission-scale coordinates are the minimum active-channel ratios:

```text
q_indigenous = min_j(q_indigenous_j)
q_supported  = min_j(q_supported_j)
```

The channel attaining the indigenous minimum is the current formal bottleneck.

Regimes:

- **AUTONOMOUS** — indigenous service meets every active requirement;
- **DEPENDENT** — indigenous service does not meet every requirement, but
  indigenous plus external service does;
- **OVERMATCHED** — even supported service fails at least one requirement;
- `NO_ACTIVE_DEMAND` is a telemetry sentinel, not a fourth mathematical regime.

### Important measurement refinement

Autonomy ratios must never be interpreted alone. A force can improve `I/D`
either by increasing indigenous capacity **or by shrinking demand**.

Every autonomy result should therefore report at least:

```text
Delta I
Delta D
Delta (I / D)
Delta operational capability
```

Use the following qualitative classification:

| Indigenous capacity | Demand | Interpretation |
|---|---|---|
| rises | stable or falls | genuine autonomy building |
| rises | rises faster | capacity growth but deepening dependency |
| falls | rises | dependency/autonomy trap |
| falls | falls faster | apparent autonomy through force contraction |

The scientifically interesting quadrant is especially:

```text
operational capability rises
while
indigenous autonomy falls
```

That is the phenomenon the next paper should explain.

---

## 4. Exploratory evidence that motivated the theory

### 4.1 Temporal capability effect

An interim set of completed paired trajectories showed a strong short-run
advantage to continuing support that eroded over time. These are **pre-repair
diagnostics**, not final estimates:

| Days after day-120 split | Mean SUPPORT_ON - SUPPORT_OFF capability | Fraction SUPPORT_ON better |
|---:|---:|---:|
| 7 | +0.00174 | 98.7% |
| 30 | +0.00576 | 94.9% |
| 90 | +0.00570 | 81.0% |
| 180 | -0.00642 | 57.0% |
| 360 | -0.01636 | 45.6% |

The medians were often near zero at long horizons, meaning late negative means
were partly heavy-tail driven. The correct interpretation is **heterogeneity and
temporal reversal**, not "aid universally makes forces worse."

### 4.2 Formal support lift versus long-run effect

In an earlier completed subset:

- correlation between final empirical capability difference and formal
  `support_lift` was only about **+0.165**;
- many worlds with positive formal support lift nevertheless had a negative
  long-run empirical SUPPORT_ON minus SUPPORT_OFF effect.

This is the key conceptual distinction:

> **Relieving the bottleneck now is not the same thing as building durable
> indigenous capacity.**

### 4.3 Preliminary autonomy split among effective-support cases

As the repaired-runtime tranche accumulated, the latest pre-repair diagnostic
classification contained **267 worlds in which continued support improved
30-day capability**. At +360 days:

- **186 / 267 (69.7%)** had lower capped indigenous `q` under continued
  support;
- **37 / 267 (13.9%)** had higher indigenous `q`;
- **44 / 267 (16.5%)** were effectively unchanged under the diagnostic
  tolerance.

Again: these observations are scientifically suggestive but **must be rerun
after the semantic repair**.

### 4.4 Supply-demand decomposition

The pre-repair mechanism decomposition was particularly informative.

Among the 186 effective-support / autonomy-eroding diagnostic cases, the
continued-support branch showed, on average in the final interval:

- approximately **3,465 fewer units of indigenous logistics delivery**;
- approximately **959 more units of logistics demand**;
- higher logistics demand in **94.6%** of cases;
- higher indigenous logistics delivery in only **1.6%** of cases;
- approximately **278 fewer indigenous graduates cumulatively**;
- approximately **86,133 more units of cumulative logistics consumption**.

Among the 37 effective-support / autonomy-building diagnostic cases:

- indigenous logistics delivery was approximately **8,809 units higher** in
  the final interval;
- logistics demand was approximately **524 units lower** on average;
- indigenous logistics delivery was higher in approximately **86.5%** of
  cases.

This suggests a candidate mechanism:

```text
AUTONOMY-ERODING SUPPORT:
    indigenous provision down / insufficient
    + supported operational demand up

AUTONOMY-BUILDING SUPPORT:
    indigenous provision catches up or expands
    relative to demand
```

The strongest working proposition is therefore:

> **Effective foreign assistance increases autonomy when the indigenous
> capacity it induces or preserves grows at least as fast as the operational
> demand the assistance enables. It decreases autonomy when support expands
> demand faster than indigenous production can replace the external
> contribution.**

### 4.5 Logistics-heavy diagnostic signal

The logistics-heavy profile showed an especially interesting pattern in an
earlier partial panel:

- very strong and persistent early/medium support advantage;
- at +180 days, continued support still usually outperformed withdrawal;
- by +360 days the **mean** effect was substantially negative while a majority
  of worlds remained slightly positive.

This implies a potentially important catastrophic tail: a minority of worlds
may undergo large late failures even when the typical world changes little.

Future analysis should inspect the tail directly rather than relying on means.

---

## 5. Candidate theory

### 5.1 Bottleneck Relief Principle

Assistance should have its largest immediate marginal effect when it relieves
the currently binding service constraint.

This by itself is not the main contribution; it establishes the local
mechanism.

### 5.2 Autonomy-Trap mechanism

Let:

- `I_t` = indigenous service-producing capacity;
- `D_t` = operational requirement/demand;
- `E_t` = external service;
- `B_t` = current binding capacity channel.

Assistance can produce:

```text
E_t
 -> relief of B_t
 -> C_t rises
 -> D_(t+1) rises
```

At the same time, indigenous production may respond:

```text
I_(t+1) - I_t
```

If indigenous response outruns induced demand, assistance can build autonomy.
If demand outruns indigenous response, assistance can produce an autonomy trap.

A useful candidate diagnostic is an indigenous-response elasticity:

```text
lambda = (% change in indigenous service capacity) /
         (% change in operational demand)
```

Do **not** preregister a theoretical threshold of exactly `lambda = 1` without
testing the measurement definition first. The repaired discovery run should
estimate whether a stable transition region exists and whether the statistic
predicts out of sample.

### 5.3 Substitutive versus developmental assistance

**Substitutive assistance** directly supplies the missing service.

**Developmental assistance** changes the partner's ability to produce that
service indigenously.

Two programs can therefore have similar near-term capability effects while
producing very different terminal autonomy:

```text
C_substitution(t0) ~= C_development(t0)

but

I_development(t1) >> I_substitution(t1)
```

The paper should treat this primarily as a **mechanism discriminator**, not as
the novel claim that institution building matters.

### 5.4 Bottleneck Migration Principle

If successful assistance relieves the current binding constraint, a different
constraint may become binding:

```text
B_1 -> B_2 -> B_3 -> ...
```

The implication is stronger than "partners have multiple weaknesses":

> **The marginal return to a fixed assistance package should be state
> dependent, because successful intervention changes which capacity is
> scarce.**

If robust to alternative capability aggregators and substitution structures,
this could be one of the project's strongest original theoretical results.

### 5.5 Hysteresis / path dependence

A never-supported force at a given present support level need not be equivalent
to a formerly supported force brought back to that same support level.

Formally, state may depend on support history, not only present support:

```text
X_t = F(E_t, E_(t-1), E_(t-2), ...)
```

The decisive experiment holds terminal external support equal while changing
the path by which that state was reached.

### 5.6 Long-run control implication

The highest-novelty policy extension is a feedback rule that removes external
production only as indigenous production safely replaces it.

A simple prototype is:

```text
E_(t+1) = E_t - alpha * Delta I_t
```

But the theory suggests a channel-specific controller may eventually be needed:

```text
E_(j,t+1) = E_(j,t) - alpha_j * Delta I_(j,t)

subject to

I_(j,t) / D_(j,t) >= theta_j
```

If bottlenecks migrate, the controller may also need to retarget assistance,
not merely taper it.

This should be a later experiment after the regime map and migration dynamics
are empirically characterized.

---

## 6. Runtime defect discovered by the formal invariant

### 6.1 Failure

Stage-3 task 444 failed reproducibly:

```text
cell index: 37
cell_id: log_08
support profile: logistics_heavy
seed: 2026120000

Error: formal service external must be nonnegative (Lean domain is Nat)
```

The isolated reproduction failed during early trajectory telemetry before a
complete primary output could be produced.

### 6.2 Root cause

The command advisory overlay currently computes a reduced latency candidate and
then applies the configured minimum latency floor with a `max(floor)`.

If indigenous command latency is **already below the configured adviser floor**,
that logic can increase latency under "assistance." In other words, assistance
can make supported command service worse than indigenous command service.

That violates the intended monotonicity condition:

```text
supported reliability >= indigenous reliability
supported latency     <= indigenous latency
```

and therefore violates the formal service interpretation in which external
service is a nonnegative increment.

### 6.3 Required semantic repair

The floor must constrain how far assistance can reduce latency; it must never
raise an already-better indigenous latency. The equivalent semantic form is:

```text
effective_floor = min(configured_floor, indigenous_latency)
supported_latency = max(reduced_candidate, effective_floor)
```

with the explicit invariant:

```text
supported_latency <= indigenous_latency
```

Do **not** hide this defect by broadening the floating-point tolerance or by
clamping materially negative external service to zero.

### 6.4 Clean-foundation gate

No new scientific experiment should be treated as valid until all of the
following hold:

1. command-overlay monotonicity semantics repaired;
2. regression/property tests prove assistance cannot worsen command service;
3. task 444 succeeds through all horizons;
4. Rust format/clippy/tests pass;
5. formal adapter and Lean conformance pass;
6. Python analysis/environment tests pass;
7. a new documented runtime amendment/freeze is generated;
8. all **720 worlds are rerun fresh** under the repaired commit;
9. `720 COMPLETED`, `0 FAILED`, IDs `0..719` complete;
10. every primary shard, trajectory shard, and metadata sidecar verifies;
11. all 720 task metadata records identify the same repaired scientific commit;
12. merge/evaluation/trajectory diagnostics pass;
13. a new READY artifact is produced;
14. discovery hypotheses/predictors are frozen before confirmatory runs.

Existing pre-repair shards should be retained as forensic evidence but not
pooled into the final repaired scientific panel.

---

## 7. Literature-adjusted experiment portfolio

These scores are scoping-review judgments, not objective measurements. They
should be revisited before manuscript submission with a systematic literature
review.

**Potential** = chance of a robust, falsifiable, generalizable, paper-useful
Pineland result.

**Novelty** = distance from the existing SFA/security-assistance literature,
with a modest penalty when the same mechanism is mature in adjacent fields.

| # | Experiment | Potential | Novelty | Intended role |
|---:|---|---:|---:|---|
| 1 | Autonomy-Trap Phase Diagram | **9.7** | **8.6** | flagship regime map |
| 2 | Indigenous-Replacement Control Rule | **9.5** | **9.4** | later policy/control culmination |
| 3 | Substitution vs Developmental Assistance | **9.5** | **7.6** | core mechanism discriminator |
| 4 | Withdrawal Hysteresis | **9.4** | **8.7** | path-dependence bridge |
| 5 | Bottleneck Migration Cascade | **9.6** | **9.2** | flagship dynamic mechanism |
| 6 | Support Reliability / Volatility | **9.1** | **8.0** | dynamic extension |
| 7 | Adversary Adaptation to Dependency | **9.2** | **9.0** | major coevolution extension |
| 8 | Network Centralization Trap | **9.1** | **8.2** | topology extension |
| 9 | Elite-Island vs Broad-Force Assistance | **9.0** | **6.9** | established-mechanism formalization |
| 10 | Assistance Sequencing | **8.9** | **7.2** | non-commutativity/path extension |
| 11 | Build While Fighting vs Protected Build Window | **8.7** | **6.3** | moderator / validation |
| 12 | Partner Fiscal Moral Hazard | **8.5** | **5.6** | mature-mechanism validation |
| 13 | Multi-Donor Interoperability Trap | **8.7** | **5.8** | fragmentation validation/thresholds |
| 14 | Coup-Proofing x External Assistance | **8.8** | **5.4** | principal-agent validation |
| 15 | Maintenance / Capability Depreciation | **9.0** | **4.6** | model qualification benchmark |

### Literature-adjusted hierarchy

**Theory-generating core**

- #1 Autonomy-Trap Phase Diagram
- #5 Bottleneck Migration
- #2 Indigenous-Replacement Control
- #4 Withdrawal Hysteresis
- #7 Adversary Adaptation

**Mechanism / bridge experiments**

- #3 Substitution vs Developmental Assistance
- #6 Support Reliability / Volatility
- #8 Network Centralization
- #10 Assistance Sequencing

**Qualification / validation / moderators**

- #9 Elite-Island Assistance
- #11 Build While Fighting
- #12 Fiscal Moral Hazard
- #13 Multi-Donor Fragmentation
- #14 Coup-Proofing
- #15 Maintenance / Depreciation

### Literature anchors to verify formally before manuscript use

The scoping review that motivated the adjusted scores identified the following
important bodies of work. Exact bibliographic metadata should be verified in a
formal paper bibliography before citation:

- Biddle, Macdonald, Baker and related SFA principal-agent / interest-alignment
  literature;
- Rachel Tecott Metz on adviser influence and security assistance;
- Marie Sandnes on autonomy/asymmetric interdependence and the G5 Sahel Joint
  Force;
- Matisek on brittle or "Faberge Egg" partner forces;
- Harkness on externally supported enclave/elite units;
- Mali, Gambia, and Somalia work on fragmented intervention / fragmented
  security sectors;
- Boutton and the wider aid-shock / military-aid political-economy literature;
- military network-resilience work on hub efficiency versus targeted-attack
  fragility;
- RAND defense-institution-building and security-cooperation research;
- GAO Section 333 / BPC sustainment and absorptive-capacity reviews;
- current DSCA Section 333 guidance on institutional capacity, sustainment, and
  dependencies;
- the 2026 security-assistance synthesis/forum literature on relational effects,
  fragmentation, authority, and mutual dependency.

The important novelty boundary is:

> The project should **not** claim to discover that SFA can produce dependency,
> weak sustainment, fragmentation, political distortion, or elite enclaves.
> Those mechanisms are already populated literatures. The originality target
> is the dynamic conditional theory connecting production, induced demand,
> moving constraints, path dependence, and replacement of external service.

---

## 8. One-paper ARC program after the clean-foundation gate

The next major allocation should be designed as **one integrated experiment
family**, not seven unrelated paper runs.

### Paper-level central claim to test

> **External assistance becomes autonomy-eroding when successful bottleneck
> relief expands operational demand faster than indigenous capacity adapts;
> whether assistance builds or erodes autonomy therefore depends on the
> interaction between indigenous responsiveness, support-enabled demand, and
> migration of the binding constraint.**

### Module A — Autonomy-Trap Phase Map

**Role:** principal result / regime map.

Primary dimensions:

- indigenous capacity responsiveness;
- support intensity;
- support-enabled demand responsiveness;
- strategically selected starting bottleneck structures;
- matched seeds/common random numbers.

Do not turn this into an indiscriminate high-dimensional sweep. Use an efficient
grid or space-filling design around the theoretically important dimensions.

Primary outputs:

- `Delta capability`;
- `Delta I` by service channel;
- `Delta D` by service channel;
- `Delta q_indigenous`;
- regime transition;
- bottleneck identity;
- donor share/cost;
- tail risk / collapse indicators.

Signature figure target: a phase diagram identifying regions in which
assistance is autonomy-building, approximately neutral, or autonomy-eroding.

### Module B — Bottleneck Migration

**Role:** dynamic explanation for the phase boundary.

Construct matched starting worlds with clearly identified:

- logistics bottleneck;
- command bottleneck;
- force-generation bottleneck;
- mixed / near-tie bottleneck.

Compare at least:

1. no targeted relief;
2. relief of the true binding bottleneck;
3. equal support applied to a nonbinding capacity;
4. continued static support of the original bottleneck after it ceases to bind.

Record the full bottleneck path:

```text
B_0, B_1, B_2, ...
```

and time to migration.

Critical robustness requirement: repeat the inference under alternative
capability aggregators / substitution structures so bottleneck migration cannot
be dismissed as a tautology induced by a hard `min()` production function.

### Module C — Substitution vs Development

**Role:** causal mechanism discriminator.

For matched initial partner weakness and approximately equal donor expenditure,
compare:

1. direct external substitution;
2. developmental aid that raises indigenous production capability;
3. hybrid aid that starts with substitution and transfers toward indigenous
   production.

Tune the design so early supported capability overlaps where practical. The
strong comparison is:

```text
early operational performance approximately equal
but
later indigenous production/autonomy diverges
```

That demonstrates why current supported capability is not equivalent to future
partner-owned productive capacity.

---

## 9. ARC concurrency policy

**64 concurrent tasks is not a scientific or technical ceiling.** It was a
temporary conservative throttle used during the repair/resume run.

After the foundation is clean, concurrent experiment arrays may use **more than
64 aggregate one-core tasks** when ARC account policy, fair share, node
availability, and allocation budget permit.

Important rules:

- retain one `(cell, seed)` world per one-core Slurm task unless profiling shows
  a reason to change;
- increase array concurrency rather than requesting unnecessarily large
  multicore tasks for single-threaded worlds;
- do not make the scientific design depend on the scheduler throttle;
- keep each module in a distinct array/output namespace;
- preserve matched seed/world identities across modules where causal comparison
  requires them;
- use independent preregistration/manifests even when modules run concurrently;
- total concurrent throughput may exceed 64, but must respect ARC/account
  policies and should not monopolize a shared system without justification.

### Preferred post-repair launch shape

For one-paper optimization, run the three modules concurrently. A reasonable
throughput target is **roughly 96-128 total concurrent one-core tasks** if ARC
availability/fair-share permits, rather than hard-coding 64.

Illustrative 112-task split:

| Module | Concurrent tasks | Share |
|---|---:|---:|
| A. Autonomy Phase Map | 48 | 42.9% |
| B. Bottleneck Migration | 40 | 35.7% |
| C. Substitution vs Development | 24 | 21.4% |
| **Total** | **112** | **100%** |

The exact throttle is an operational choice, not part of the scientific
preregistration. If the queue permits 128 or more without violating account
policy, the arrays can be raised further. If fair share penalizes the jobs,
reduce the throttle without changing the experimental design.

### Qualification sidecar

Maintenance / capability depreciation (#15) is valuable as a known-mechanism
qualification test. It can run as a small sidecar array if spare concurrency is
available, but it should **not** displace the main three-module paper design.

If it fails to reproduce the expected qualitative sustainment/depreciation
pattern, pause interpretation of the more novel experiments and investigate
model validity.

---

## 10. One-paper result structure

The intended paper should read as one theory with multiple tests:

### Result 1 — Capability and autonomy can diverge

```text
Delta C > 0
```

does not imply:

```text
Delta autonomy > 0
```

### Result 2 — There is a conditional autonomy boundary

Map:

```text
Delta autonomy = f(indigenous responsiveness,
                   demand responsiveness,
                   support intensity,
                   starting constraint structure,
                   ...)
```

and estimate where the sign changes.

### Result 3 — Indigenous response versus induced demand explains the boundary

Test whether relative growth in indigenous service versus demand predicts which
side of the boundary a world enters.

### Result 4 — Successful assistance migrates the binding constraint

Test whether relieving the true bottleneck changes the identity of the next
binding channel and causes the marginal value of static support to decay.

### Result 5 — Substitution and development can look similar early but diverge later

Hold near-term supported capability and donor expenditure as comparable as
practicable, then test whether indigenous production and terminal autonomy
diverge.

### Paper-level implication

Security assistance should be evaluated not only by capability delivered, but
by how it changes:

- indigenous productive capacity;
- support-enabled operational demand;
- the identity and migration of binding constraints;
- future replaceability of external services.

This is an analytic implication. Any real-world policy recommendation requires
external validation and a separately justified measurement/transport design.

---

## 11. Experiments deliberately deferred from the first paper

Do **not** expand the first paper into all of the following unless the core
theory requires a specific robustness test:

- Indigenous-Replacement Controller (#2) — best as the next policy/control
  paper after the dynamics are known;
- Withdrawal Hysteresis (#4) — high-value bridge/follow-up;
- Support Reliability / Volatility (#6);
- Adversary Adaptation (#7) — strongest major extension after the base theory;
- Network Centralization (#8);
- Elite-Island concentration (#9);
- Assistance Sequencing (#10);
- Build While Fighting (#11);
- Fiscal Moral Hazard (#12);
- Multi-Donor Fragmentation (#13);
- Coup-Proofing (#14).

These should remain in the research backlog so the project can expand after the
first coherent paper rather than dilute it.

---

## 12. Future extension sequence

If the first paper succeeds, the strongest scientific progression is:

```text
Bottleneck Migration / Autonomy Phase Map
    -> Substitution mechanism
    -> Withdrawal Hysteresis
    -> Indigenous-Replacement Controller
    -> Adversary Adaptation / coevolution
```

Conceptually:

```text
regime
 -> mechanism
 -> constraint dynamics
 -> path dependence
 -> control
 -> adversarial coevolution
```

That sequence is more coherent than treating the portfolio as a collection of
independent small papers.

---

## 13. Evidence and reproducibility rules for future agents

1. Never promote the exploratory numbers in this memo to final findings without
   reproducing them on the clean post-repair 720-world panel.
2. Preserve common random numbers / matched branches wherever causal comparison
   relies on them.
3. Keep supported capability, indigenous production, operational demand, and
   autonomy separate in both code and prose.
4. Distinguish formal `support_lift` from an empirical paired treatment effect.
5. Analyze medians, distributions, and tails in addition to means; previous
   logistics-heavy diagnostics showed strong heavy-tail behavior.
6. Never infer "crowding out" solely from lower indigenous output if the code
   mechanically substitutes external service. Trace the implementation and
   state-feedback pathway first.
7. Treat bottleneck migration as nontrivial only if it survives alternative
   production/capability structures.
8. Pre-register holdouts and zero-refit predictions before inspecting their
   outcomes.
9. Keep runtime amendments separate from scientific hypothesis changes.
10. Preserve failed tasks and invariant violations as forensic artifacts rather
    than silently dropping them.

---

## 14. Current handoff state

At the time this memo was written:

- the Stage-3 runtime repair worktree is the intended isolated workspace;
- task 444's command-support monotonicity defect has been identified and
  reproduced;
- existing Stage-3 numerical findings remain **pre-repair exploratory**;
- a clean post-repair 720/720 run is required before final scientific claims;
- additional v5 / experiment implementation files may be under active work by
  another agent and should not be overwritten casually;
- the next major scientific target is **one integrated paper**, not many small
  unrelated runs;
- the preferred post-repair ARC program consists of the Phase Map,
  Bottleneck-Migration, and Substitution-vs-Development modules run concurrently;
- aggregate ARC concurrency is **not limited to 64** and may be increased when
  operationally appropriate.

This memo is intentionally a scientific planning/provenance document. Frozen
experiment contracts, runtime amendments, exact grids, seeds, stopping rules,
and job manifests remain the authoritative machine-readable records once they
are created.

