# Pineland General Theory v1

General Theory v1 is Pineland's synthetic theory-extraction program. Its goal is
**explanatory compression**: determine whether the full agent-based model can be
reduced to a smaller conditional theory of competitive local reproduction, then
try to break that reduction before transporting it to historical cases.

This directory is a scientific workspace, not a historical calibration surface.
Synthetic experiments may select or refute candidate theory structures.
Historical outcomes may confront a frozen theory, but they may not choose its
mechanisms, functional forms, or parameters.

## Program logic

The program follows a prospective sequence:

1. map executable Rust state/processes to candidate theoretical quantities;
2. define rival reduced-form architectures before evaluating them;
3. test state sufficiency, closure, transport, and scale dependence;
4. preserve negative and falsifying results in explicit ledgers;
5. freeze surviving theory coordinates and code;
6. evaluate preregistered holdouts;
7. only then permit historical transport.

This ordering is intended to make "theory discovery" distinguishable from
post-hoc curve fitting.

## Core contracts

- **general_theory_contract_v1.json** — substantive theory candidates and the
  promotion firewall.
- **model_to_theory_map_v2.json** — audited executable-state/process mapping.
- **rival_reproduction_architectures_v1.json** — OR/MAX, additive,
  complementary, bottleneck, and threshold rivals.
- **macrostate_closure_contract_v1.json** — state sufficiency and coarse-graining
  tests.
- **multitype_reproduction_operator_contract_v1.json** — endogenous reproduction
  accounting and criticality.
- **dimensionless_groups_v1.json** — candidate timescale/capacity groups and
  phase regimes.
- **competitive_reproduction_contract_v1.json** — state-side reproduction
  extension.
- **experiment_registry_v2.json** — current dependency/order registry.
- **falsification_ledger_v4.json** — retained failures and theory revisions.

Older contract and registry versions remain in place for provenance.

## Current research threads

### Competitive reproduction and closure

The main theory line tests whether insurgent and state-side persistence can be
described with a compact set of stock, flow, transport, network, and timescale
coordinates. Closure tests ask whether those coordinates remain predictive
when hidden executable details change.

### Mobilization runway

The mobilization-runway work tests a resource/capital bottleneck hypothesis for
organizational survival and growth. Prospective contracts, source audits,
phase-law artifacts, and held-out transport results are kept in this directory
rather than summarized away.

### Local-flow and graph transport

Local-flow and causal-cone experiments test whether neighboring stock/flow
information is sufficient, or whether nonlocal network structure carries
irreducible predictive information. Development batteries and equivalence
audits are intentionally separated from confirmatory artifacts.

### Partner-force autonomy

[partner_force_autonomy/](partner_force_autonomy/) is a contained Stage-3
program studying externally supported performance versus autonomous partner
capacity. It has its own preregistration, output schema, holdouts, resolution
audit, and analysis code.

## Evidence conventions

Generated panels can be large and are not automatically Git-worthy. The
repository retains compact contracts, audit records, falsification ledgers,
equivalence certificates, and result summaries that support scientific claims;
large raw panels remain local when they can be deterministically regenerated.

Do not delete an apparently "failed" result merely because it is negative. A
falsification can be more scientifically valuable than a successful screen.
Repository-wide evidence rules are documented in
[docs/repository-layout.md](../../../docs/repository-layout.md).

## Historical firewall

General Theory v1 does **not** authorize new Nepal, Afghanistan, or other
historical tuning. Historical outcomes may be used only at the stage allowed by
the relevant frozen contract. If a synthetic result changes the theory, the
change must be recorded before historical evaluation.
