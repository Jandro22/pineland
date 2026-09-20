# Pineland Partner-Force Theory (Lean 4)

This package is the machine-checked mathematical core of Pineland's partner-force autonomy framework.

The formalization separates **structural theorems** from **empirical Pineland claims**. Lean proves the accounting, feasibility, bottleneck, support, buffer, and horizon statements below. Lean does **not** prove that the ABM's behavioral outcomes must follow any particular function of these structural quantities; that remains an empirical simulation question.

## Toolchain

- Lean 4.34.0
- mathlib 4.34.0
- Apache-2.0

Build:

```text
lake build
```

Trust/axiom audit:

```text
lake env lean Audit.lean
```

The source contains no `sorry`, `admit`, custom `axiom`, or `unsafe` declarations.

## Core model

For service type `i` and mission activity `j`, the reference mission induces service demand

```text
d_i = sum_j A_ij m_j
```

implemented by `MissionModel` and `requirement`.

`FeasibleScale M s num den` means the exact rational mission fraction `num / den` is feasible without using floating point:

```text
num * d_i <= den * s_i   for every service i
```

Zero-demand services are explicitly nonbinding.

When at least one service is positively demanded, the structural mission scale is

```text
q = min_{i : d_i > 0} s_i / d_i
```

`missionScale` implements this exactly over rational numbers. The formalization proves:

1. a minimum-ratio bottleneck exists in every finite active service system;
2. all tied bottlenecks have the same ratio;
3. `q >= 1` iff every service requirement is covered;
4. `num / den` is feasible iff `num / den <= q`;
5. increasing usable service componentwise cannot decrease `q`;
6. simultaneous positive rescaling of supply and demand within any service
   channel leaves `q` unchanged, so the structural classification is
   dimensionless with respect to unit choice.

If all service demands are zero, the mission is proved vacuously feasible and `missionScale` is intentionally not invoked: the mathematical maximum scale would be unbounded, so assigning an arbitrary finite `q` would be misleading.

## Structural regimes

At a common state, `SupportState` separates indigenous usable service `s-` from external usable service `e`, with supported supply `s+ = s- + e`.

The three regimes are:

- `Autonomous`: indigenous supply covers the reference mission.
- `Dependent`: indigenous supply does not cover the mission, but supported supply does.
- `Overmatched`: even supported supply does not cover the mission.

Lean proves these regimes are exhaustive and pairwise incompatible in the expected directions. In scale form:

```text
Autonomous  <-> q- >= 1
Dependent   <-> q- < 1 <= q+
Overmatched <-> q+ < 1
```

## External support accounting

For one service channel:

```text
deficit = max(requirement - indigenous, 0)
useful_external = min(external, deficit)
redundant_external = external - useful_external
```

Lean proves:

```text
useful_external + redundant_external = external
```

and supported feasibility is equivalent to external support covering every indigenous deficit. A dependent world must contain at least one channel with strictly positive useful external substitution.

The bounded structural support lift is

```text
L = min(q+, 1) - min(q-, 1)
```

with proved bounds `0 <= L <= 1`. If the indigenous force is already autonomous, `L = 0`; if it is supported-dependent, `L = 1 - q- > 0`.

## Buffers

Buffers are **state stocks**, not universal capability dimensions. `bufferStep` applies only to storable resources such as trained reserve or supply inventory:

```text
b' = max(b + production + external - consumption, 0)
```

The formalization proves monotonicity with external replenishment and exact constant-deficit runway identities. Command reliability, latency, or other non-storable services must not be inserted into the buffer equation merely for symmetry.

## Horizon viability

`StructuralTrace` represents time-indexed supply and demand vectors. Lean proves:

```text
HorizonAutonomous trace
  <-> q_t >= 1 at every checkpoint t
```

and failure of horizon autonomy is equivalent to existence of a checkpoint with `q_t < 1`.

## What Lean does not prove

The following remain empirical/modeling questions and must not be presented as formal consequences of this package:

- that Pineland behavioral capability `C` is a deterministic function of `q`;
- that withdrawal loss is approximately a shadow-price dot product;
- that any particular service taxonomy is the uniquely correct taxonomy;
- that the ABM's behavioral policies optimize the reference mission;
- that a given historical partner force maps to a particular parameter vector;
- that Stage-3 hypotheses are true.

Those claims require simulation evidence or external empirical validation.

## Pineland implementation contract

Before connecting this theory to production simulations, the adapter must satisfy all of the following:

1. **Common units within each service.** `s_i` and `d_i` must measure the same usable service quantity.
2. **Explicit mission demand.** `d_i` must be derived from a declared reference mission, not inferred from whether the supported branch happened to consume a resource.
3. **Zero-demand exclusion.** Channels with `d_i = 0` cannot become bottlenecks.
4. **Indigenous/external separation.** Supported supply must decompose into indigenous and external contributions at the same state.
5. **Usable, not nominal, service.** Material that cannot reach formations, personnel that cannot deploy, or assistance that cannot act on an opportunity must not be counted as usable service.
6. **Buffers only where physically meaningful.** Stocks and flows must not be invented for non-storable services.
7. **Structural/behavioral separation.** `q`, deficits, and support lift are predictors/diagnostics. Outcome trajectories remain independently measured ABM results.
8. **Exact withdrawal pairing.** ON/OFF branches must begin from the identical state and only differ in the designated post-withdrawal external-support intervention.

### Frozen Stage-3 v3 adapter mapping

The production floating-point adapter is
rust/pineland-model/src/partner_force_formal.rs. It implements the same
minimum-ratio/deficit accounting for pre-withdrawal flow windows. The current
reference-mission mapping is frozen before Stage-3 v3 discovery:

| Service | Demand d_i | Indigenous service s_i^- | External service e_i |
| --- | --- | --- | --- |
| Force generation | military personnel losses requiring replacement | indigenous training graduates | external incremental graduates |
| Logistics | military logistics consumption | indigenous logistics delivered | external logistics delivered |
| Command | military movement-order opportunities x 0.5 timely-success equivalents | sum of r exp(-latency_hours/24) before partner overlay | supported command service minus indigenous command service |

The command reference requirement of **0.5 service-equivalents per military
order** is a preregistered reference-mission threshold, not an outcome-fitted
coefficient. It represents a more-likely-than-not, latency-discounted command
standard.

Air support is **not** inserted into q in Stage-3 v3. Pineland records air
opportunities, detected deliveries, firepower effect, and cost, but there is
not yet a defensible like-unit indigenous air-service denominator. Air therefore
remains a separate combat-augmentation mechanism.

Variables named external_share_* are exposure fractions only. They must not be
interpreted as structural dependence. Structural dependence is determined by
the proved deficit/mission-feasibility relationship.

When all three formal service demands are zero, q is mathematically undefined
rather than low. Production telemetry encodes q=-1, NO_ACTIVE_DEMAND, and
bottleneck=none. Those observations remain in the raw scientific record but
are excluded, by preregistered rule, from formal-q isotonic fitting, rank
correlations, and MAE calculations.

## Files

- `PinelandPartnerForceTheory/PartnerForce.lean` — formal definitions and proofs.
- `PinelandPartnerForceTheory.lean` — library entry point.
- `Audit.lean` — Lean axiom/trust audit for headline theorems.
- `lean-toolchain` / `lakefile.toml` / `lake-manifest.json` — reproducible toolchain metadata.
