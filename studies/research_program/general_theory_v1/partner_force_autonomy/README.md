# Partner-Force Autonomy Experiment

## 1. Central Research Question

> **When does security-force assistance create autonomous military capability, and when does it create only externally supported performance?**

Security-force assistance (SFA) often produces partner formations that fight effectively while embedded with external enablers, only to suffer rapid disintegration once foreign combat, logistics, or advisory support is withdrawn. Traditional modeling attempts frequently obscure this dynamic by relying on post-hoc scalar fudge factors (such as unmeasurable "corruption" coefficients or blanket "morale" multipliers).

The Pineland Partner-Force Autonomy Experiment provides an instrumented, structural, paired counterfactual framework to investigate how different assistance architectures influence post-withdrawal autonomous capability and long-horizon resilience.

---

## 2. Core Theoretical Distinctions

This experiment rigorously separates four distinct operational concepts:

```
+-------------------------------------------------------------------------+
| Supported Performance != Organic Capacity != Autonomy != Resilience     |
+-------------------------------------------------------------------------+
```

1. **Supported Performance ($C_{ON}$)**:
   - Observed battlefield performance while external donor support channels are fully active.
   - Masks underlying organic deficits through external air sorties, push-logistics delivery, and advisory command transmission.
2. **Organic Capacity**:
   - Partner-owned stocks (depots, indigenous formations, reserves) and endogenous regeneration flows (recruit graduation throughput, administrative standard, depot replenishment).
3. **Autonomy after Withdrawal ($R_h$)**:
   - Post-withdrawal performance retention measured counterfactually against the paired supported branch:
     $$R_h = \frac{C_{OFF}(T+h)}{\max(C_{ON}(T+h), \epsilon)}$$
4. **Long-Horizon Resilience**:
   - Persistence and renewal of autonomous performance over longer horizons ($h \in \{90, 180\}$ days) following combat losses, turnover, and operational friction.

---

## 3. Paired Counterfactual Branching Design

At withdrawal time $T$, an identical simulation world state $W_T$ is branched into two trajectories using Common Random Numbers (CRN):

$$
W_T \longrightarrow
\begin{cases}
W^{ON}_{T+h} & \text{(external assistance continues)} \\
W^{OFF}_{T+h} & \text{(designated external channels removed at } T\text{)}
\end{cases}
$$

### Immediate Diff Allowlist Invariant
Calling `withdraw_external_partner_support()` at step $T$ mutates **only**:
- `particle.config.partner_support.enabled = false`
- `particle.partner_support.support_withdrawn = true`
- `particle.partner_support.withdrawal_time = Some(T)`
- `particle.partner_support.window_snapshots` (appends withdrawal snapshot)

All indigenous physical state arrays—including formations, people, organizations, leaders, command edges, supply depot inventories, political/governance state, and the random number generator state—are **bit-for-bit identical** immediately upon withdrawal.

---

## 4. The Four Assistance Channels

External assistance operates as a non-invasive environmental and resource overlay across four structural channels:

| Channel | Module | Governing Mechanism | Metered Donor Cost |
|---|---|---|---|
| **Air Support** (`air`) | `combat.rs` | $A_{total} = A_{organic} + A_{external}$. Contact firepower overlay without billing organic government capital. | Sorties flown $\times$ cost per strike. |
| **Logistics Support** (`logistics`) | `logistics.rs` | Conserved flow delivery: $Q_{offered} = Q_{delivered} + Q_{rejected} + Q_{lost}$. Direct unit push or depot replenishment up to `max_daily_capacity`. | Supplies delivered $\times$ cost per supply unit. |
| **Command Advisory** (`command`) | `movement.rs` | Non-mutating order transmission overlay: boosted reliability ($r^{eff} = r + \text{boost}$) and reduced latency ($L^{eff} = \max(L - \text{reduction}, \text{floor})$). Persistent graph unmutated. | Daily advisory fixed cost + assisted orders. |
| **Force Generation** (`force_generation`) | `state_regeneration.rs` | Training pipeline throughput boost ($k_{total} = k_{indig} + \text{boost}$). Separates organic vs incremental graduates. | Incremental graduates $\times$ training cost + advisory cadre fixed cost. |

---

## 5. Primary Pre-Registered Hypotheses

* **PF-H1 (Performance Masking)**: Supported performance ($C_{ON}$) substantially overstates post-withdrawal retention under substitution-heavy assistance.
* **PF-H2 (Autonomy Bottleneck)**: Post-withdrawal retention is better predicted by the binding subsystem constraint ($\Omega_{\min} = \min(\Omega_M, \Omega_F, \Omega_G, \Omega_C)$) than by arithmetic mean capability ($\Omega_{\text{mean}}$).
* **PF-H3 (Regeneration vs Stocks)**: Long-horizon withdrawal resilience (90d, 180d) is governed by indigenous regeneration flows rather than withdrawal-day stocks.
* **PF-H4 (Complexity-Capacity Mismatch)**: Inducing high-tempo operational complexity with weak indigenous sustainment capacity accelerates post-withdrawal collapse rates.

---

## 6. Historical Case Firewall

In accordance with `partner_force_autonomy_program_contract_v1.json`, historical cases (e.g., the August 2021 Afghan National Army collapse) are strictly firewalled:
- **Prohibited**: Tuning simulation parameters, thresholds, or mechanics to match specific historical episodes.
- **Permitted**: Out-of-sample diagnostic consistency checks *after* synthetic mechanism forms and evaluation code are frozen.

---

## 7. Directory Structure

```
studies/research_program/general_theory_v1/partner_force_autonomy/
|-- contracts/
|   `-- partner_force_autonomy_output_schema_v1.json   # Draft 2020-12 output schema
|-- configs/
|   |-- substitution_heavy_v1.json                     # High air/logistics, zero force gen
|   |-- capacity_heavy_v1.json                         # High training/command, minimal air
|   |-- bottleneck_targeted_v1.json                    # Relieves measured binding constraint
|   |-- calendar_transition_v1.json                    # Phased step-down by calendar time
|   `-- capability_conditioned_v1.json                 # Gated on indigenous autonomy metrics
|-- fixtures/
|   |-- synthetic_pairing_fixture_v1.csv               # Paired counterfactual panel fixture
|   `-- synthetic_pairing_fixture_v1.json              # Schema-compliant nested JSON fixture
|-- outputs/
|   |-- .gitkeep
|   |-- partner_force_autonomy_metrics_v1.json         # Summary metrics & hypothesis verdicts
|   `-- partner_force_autonomy_evaluation_report_v1.md # Formatted Markdown evaluation report
|-- analysis/
|   |-- partner_force_metrics.py                       # Autonomy ratio, decay rate, efficiency
|   |-- partner_force_regenerative_coordinates.py      # State space (M, F, G, C) & Omega analysis
|   |-- partner_force_transport.py                     # Spatial mobility & relocation flux
|   `-- evaluate_partner_force_autonomy.py             # Standalone CLI evaluation pipeline
|-- validate_partner_force_autonomy_environment.py     # Pre-flight environment verification script
`-- README.md                                          # This documentation
```

---

## 8. Usage & Verification

### Run Pre-Flight Environment Validation
```bash
python studies/research_program/general_theory_v1/partner_force_autonomy/validate_partner_force_autonomy_environment.py
```

### Run Evaluation CLI (Dry-Run / Fixture Mode)
```bash
python studies/research_program/general_theory_v1/partner_force_autonomy/analysis/evaluate_partner_force_autonomy.py --dry-run
```

### Single-Command Battery Launch (When Greenlit for Compute)
```bash
python studies/research_program/general_theory_v1/partner_force_autonomy/analysis/evaluate_partner_force_autonomy.py \
  --config-dir studies/research_program/general_theory_v1/partner_force_autonomy/configs \
  --output-dir studies/research_program/general_theory_v1/partner_force_autonomy/outputs
```
