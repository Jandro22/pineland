# Subsystem status and research role

This page answers a different question from the feature list in the README:
**which parts of Pineland are currently carrying scientific claims, and what
kind of evidence exists for them?**

The labels below are descriptive rather than quality scores. "Implemented"
means executable code exists. "Research-load-bearing" means the current
research program directly depends on the subsystem. Neither label is a claim of
historical validity.

| Subsystem | Current role | Evidence visible in repository | Current boundary |
|---|---|---|---|
| Deterministic runtime, scheduler, RNG, checkpointing | Research-load-bearing infrastructure | Rust core, checkpoint/state-hash contracts, regression tests, native validation artifacts | Engineering reproducibility does not validate substantive model assumptions |
| Physical presence and territorial control | Research-load-bearing mechanism | `docs/physical-model.md`, resolution tests, causal/invariant tests | Historical control remains latent unless linked to observed measurements |
| Logistics and readiness | Research-load-bearing mechanism | `docs/logistics-model.md`, conserved-flow diagnostics, causal-integrity tests | Parameter values are not empirical findings by default |
| Organization ecology and mobilization | Research-load-bearing in General Theory v1 | `docs/organization-ecology.md`, theory contracts, falsification ledgers, mobilization experiments | Synthetic mechanism evidence precedes historical transport |
| Information, observation, and actor beliefs | Research-load-bearing | `docs/information-model.md`, observation/relay outputs, truth-firewall tests | Actor belief, latent truth, and recorded observables remain distinct |
| State estimation / particle filtering | Research-load-bearing inference layer | `docs/state-estimation.md`, recovery tests, Research-v1 recovery artifacts, MCSE/ESS infrastructure | Historical latent-state recovery remains a harder external-validation problem |
| Organized action and combat | Implemented; used by active studies | `docs/action-model.md`, `docs/combat-model.md`, mechanism/invariant tests | Tactical realism is not equivalent to validated real-world prediction |
| Political order and governance | Implemented; secondary to current first-paper inference program | `docs/political-order.md`, implementation audit, regression tests | Not every political mechanism is currently identifiable from historical data |
| Foreign affairs and external support | Implemented; active in partner-force research | `docs/foreign-affairs.md`, withdrawal/support mechanisms, Partner-Force contracts | Partner-force Stage 3 is synthetic discovery, not policy evaluation |
| Peace-process mechanisms | Implemented; currently peripheral | `docs/peace-process.md`, regression coverage | Not currently a primary source of first-paper claims |
| Historical case adapters | Active external-validation layer | case READMEs/manifests, empirical and historical tests, Afghanistan/Nepal diagnostics | Case quality and transportability vary; cases should not be treated as interchangeable |

## Reading the table

Three kinds of maturity must not be collapsed:

1. **implementation maturity** - whether the mechanism is coded, tested, and
   computationally stable;
2. **synthetic scientific validation** - whether the mechanism or inference
   method survives known-truth, falsification, sensitivity, and holdout tests;
3. **historical validity** - whether the same quantity can be measured,
   transported, and defended against real-world evidence.

A subsystem can be strong on the first two and still weak on the third. That is
expected in a partially observed conflict model and should be stated rather
than hidden.

## Canonicality

The standalone Rust workspace under `rust/` owns the high-performance
simulation and inference path. The Python package under `src/pineland_sim/`
remains the transparent reference and analysis-facing implementation. Exactness
and parity claims should always identify the specific tested boundary; do not
assume that two implementations are equivalent merely because both exist.

The separate `native/pineland_kernels.rs` source is still used to build the
Python native-kernel acceleration/exactness path. It is retained for active
verification and should not be mistaken for an abandoned copy of the
standalone Rust workspace.

This page should be updated when a subsystem becomes newly load-bearing, is
retired, or receives a materially stronger or weaker validation status.

For the current mechanical inventory of selected test counts and concrete evidence
paths, see [docs/subsystem-evidence-index.md](subsystem-evidence-index.md).
