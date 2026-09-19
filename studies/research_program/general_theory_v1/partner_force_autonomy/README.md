# Partner-Force Autonomy: Stage-3 Discovery & Program Architecture

## 1. Central Scientific Question

> **When does security-force assistance create autonomous military capability, and when does it create only externally supported performance?**

Security-force assistance (SFA) often produces partner formations that fight effectively while embedded with external enablers (air support, logistics push, advisory command), only to suffer rapid collapse or severe performance cliffs once foreign assistance is withdrawn. Traditional modeling frequently obscures this dynamic with post-hoc scalar fudge factors (e.g. arbitrary "morale" decay or unmeasurable "corruption" coefficients).

The Pineland Partner-Force Autonomy Program provides an instrumented, structural, paired counterfactual framework to investigate how external assistance composition interacts with indigenous regenerative capacity.

---

## 2. Program Stage Architecture: Stage 3 vs Stage 4

This program enforces a strict scientific boundary between **mechanistic discovery** and **policy comparison**:

| Dimension | Stage 3: Discovery (Active) | Stage 4: Policy Comparison (Blocked) |
|---|---|---|
| **Objective** | Identify autonomy coordinates ($\Omega$), test bottleneck vs mean models, measure dependence under removable substitution. | Compare adaptive, persistent, or conditioned assistance policy rules under equal donor budgets. |
| **Mechanisms** | Removable external assistance overlays only. Indigenous capacity parameters are synthetic discovery coordinates. | Preregistered persistent capacity-building laws or adaptive allocation algorithms. |
| **Policy Firewalls** | No claims of policy superiority, efficiency, or optimal allocation. | Explicitly blocked until Stage 3 discovery coordinates are frozen and holdouts verified. |
| **Configs** | `configs/stage3_discovery_cells_v1.csv` (60 cells) | `capacity_heavy_v1.json`, `bottleneck_targeted_v1.json`, `calendar_transition_v1.json`, `capability_conditioned_v1.json` are `BLOCKED_*` with `enabled = false`. |

---

## 3. Core Theoretical Distinctions

The research program rigorously separates four operational concepts:

```
+-------------------------------------------------------------------------+
| Supported Performance != Organic Capacity != Autonomy != Resilience     |
+-------------------------------------------------------------------------+
```

1. **Supported Performance ($C_{ON}$)**: Observed capability while external donor support channels are active ($T - 60 \to T$ or post-withdrawal ON branch).
2. **Organic Capacity ($\Omega$)**: Partner-owned stocks (depots, formations, reserves) and endogenous regeneration flows (recruitment, training graduation, logistics production).
3. **Autonomy after Withdrawal ($R_h$)**: Post-withdrawal retention measured counterfactually against the paired supported branch:
   $$R_h = \frac{C_{OFF}(T+h)}{\max(C_{ON}(T+h), \epsilon)}$$
4. **Long-Horizon Resilience**: Persistence and renewal of autonomous performance over longer horizons ($h \in \{7, 30, 90, 180\}$ days) following operational friction and combat losses.

---

## 4. Paired Counterfactual Branching & Common Random Numbers

At withdrawal time $T = 120\text{d}$, an identical simulation world state $W_T$ is cloned into two paired trajectories:

$$
W_T \longrightarrow
\begin{cases}
W^{ON}_{T+h} & \text{(external assistance continues)} \\
W^{OFF}_{T+h} & \text{(designated external assistance channels removed at } T\text{)}
\end{cases}
$$

### Immediate Diff Allowlist Invariant
Calling `withdraw_external_partner_support()` at step $T$ mutates **only**:
- `particle.config.partner_support.enabled = false`
- `particle.partner_support.support_withdrawn = true`
- `particle.partner_support.withdrawal_time = Some(T)`
- `particle.partner_support.window_snapshots` (records withdrawal state)

All indigenous physical state arrays—formations, people, organizations, leaders, command edges, supply inventories, governance control, and RNG streams—are **bit-for-bit identical** immediately upon withdrawal.

---

## 5. Assistance Channels & Governing Mechanics

External assistance operates as a non-invasive environmental and resource overlay across four structural channels:

| Channel | Module | Governing Equation | Accounting Invariant |
|---|---|---|---|
| **Air Support** (`air`) | `combat.rs` | $A_{\rm total} = A_{\rm organic} + A_{\rm external}$ | Firepower increment during contacts; metered per assisted contact. |
| **Logistics Support** (`logistics`) | `logistics.rs` | $Q_{\rm offered} = Q_{\rm delivered} + Q_{\rm rejected} + Q_{\rm lost}$ | Conserved supply push up to `max_daily_capacity`; insurgent flows strictly excluded from partner metrics. |
| **Command Advisory** (`command`) | `movement.rs` | $r_{\rm eff} = 1 - (1 - r_i)(1 - b_r)$<br>$L_{\rm eff} = \max(L_{\min}, L_i(1 - b_L))$ | Bounded reliability and fractional latency reduction without mutating underlying topology. |
| **Force Generation** (`force_generation`) | `state_regeneration.rs` | $k_{\rm total} = k_{\rm indig} + k_{\rm boost}$ | Removable training-throughput assistance; separates organic vs incremental graduates. Persistent capacity-building is firewalled. |

---

## 6. Behavioral Capability Assay

To eliminate tautological leakage, outcome capability $C(t)$ is measured via a frozen behavioral assay (`pineland.partner_force_capability_assay.v1`) evaluated relative to a shared baseline:

$$C(t) = \left( c_{\rm gov}(t) \cdot c_{\rm personnel}(t) \cdot c_{\rm formation}(t) \cdot c_{\rm coverage}(t) \right)^{1/4}$$

- $c_{\rm gov}(t)$: Effective government territorial control ($\in [0, 1]$).
- $c_{\rm personnel}(t)$: Fielded military personnel retention relative to baseline ($\in [0, 1]$).
- $c_{\rm formation}(t)$: Operational military formation survival relative to baseline ($\in [0, 1]$).
- $c_{\rm coverage}(t)$: Geographic locality coverage retention relative to baseline ($\in [0, 1]$).
- **Predictor Firewall**: Autonomy predictors (stocks, flows, command edge parameters, training throughput) are strictly excluded from $C(t)$.
- **Degenerate Baseline Rule**: If baseline personnel or operational formations $\le 10^{-12}$, retention and composite capability evaluate to `0.0`.

---

## 7. Experimental Design (Stage 3)

The Stage-3 design manifest (`configs/stage3_discovery_cells_v1.csv`) specifies 60 prospective cells:
- **10 Capacity Profiles**: Uniform strong (1.4, 1.4, 1.4), baseline (1.0, 1.0, 1.0), mediocre (0.6, 0.6, 0.6), single bottlenecks (forcegen 0.4, logistics 0.4, command 0.4), dual bottlenecks, and sub-baseline profiles, designed to separate $\Omega_{\min}$, $\Omega_{\rm mean}$, and $\Omega_{\rm geo}$.
- **6 Support Compositions**: `none` (negative control), `balanced`, `air_heavy`, `logistics_heavy`, `command_heavy`, `forcegen_heavy`.
- **Negative Control Invariant**: Cells with profile `none` assert identical $C_{ON} = C_{OFF}$ across all horizons.

---

## 8. Usage & Verification Commands

### A. Pre-Flight Environment Validation
```powershell
python studies/research_program/general_theory_v1/partner_force_autonomy/validate_partner_force_autonomy_environment.py
```

### B. Rust Unit Tests
```powershell
cargo test --manifest-path rust/Cargo.toml
```

### C. Safety Gate Check (Zero Compute)
```powershell
cargo run --manifest-path rust/Cargo.toml -p pineland-model --example partner_force_autonomy_stage3
```
*Outputs design summary and exits with `NO COMPUTE: --execute not supplied` without instantiating simulation engines.*

### D. Plumbing Smoke Test (Allowed Tiny Run)
```powershell
cargo run --manifest-path rust/Cargo.toml -p pineland-model --example partner_force_autonomy_stage3 -- --smoke --execute
```
*Simulates 1 cell, 1 seed, $h=7\text{d}$ to verify end-to-end execution, negative control assertion, and raw output formatting.*

### E. Python Analysis Pipeline Dry-Run
```powershell
python studies/research_program/general_theory_v1/partner_force_autonomy/analysis/evaluate_partner_force_autonomy.py --dry-run
python studies/research_program/general_theory_v1/partner_force_autonomy/analysis/partner_force_autonomy_holdouts.py --dry-run
```
*Validates pairing, metric derivation, coordinate computation, and holdout evaluation without writing scientific output files.*

### F. Launching Stage-3 Discovery (When Greenlit for Compute)
```powershell
cargo run --release --manifest-path rust/Cargo.toml -p pineland-model --example partner_force_autonomy_stage3 -- --execute
python studies/research_program/general_theory_v1/partner_force_autonomy/analysis/evaluate_partner_force_autonomy.py \
  --input-csv studies/research_program/general_theory_v1/partner_force_autonomy/outputs/partner_force_autonomy_stage3_raw_v2.csv
```
