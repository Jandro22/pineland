# GENERAL THEORY OF COMPETITIVE LOCAL REPRODUCTION AND COUNTERINSURGENCY (v1.0)
## A Stabilized Reduced Dynamical System with Characterized Residual Uncertainty Compressed from Multi-Agent Pineland Simulations

**Classification**: SYNTHETIC MECHANISM RESULT  
**Schema Version**: `pineland.general_theory_monograph.v2`  
**License / Status**: Synthetic Mechanism Layer Complete — Reduced Theory Stabilized  
**Historical Firewall Status**: CERTIFIED (Zero Historical Outcomes or Empirical Tuning Used)  
**Complexity Bound**: CERTIFIED (10 State Dimensions: 6 Local + 1 Global + 3 Slow Memory Stocks)  
**Claim Language Governance**: Certified Level 1 (`synthetically_identified`) under `claim_language_contract.json`  

---

### Epistemic Guardrails & Category Definitions

Throughout this monograph, every claim is strictly classified according to the research program's evidence ladder:
- **[ENCODED MECHANISM]**: Direct consequence of native simulation transition equations.
- **[SYNTHETICALLY IDENTIFIED]**: Causal relationship verified through controlled counterfactual ablation, common-random-number (CRN) matching, and prospective pre-registered confirmation on untouched seed blocks.
- **[FALSIFIED / RETRACTED]**: Hypotheses permanently refuted by experimental gates (preserved in `falsification_ledger_v4.json`).
- **[HISTORICAL EVIDENCE]**: QUARANTINED. Strictly zero real-world data (Nepal, Afghanistan, Colombia, etc.) were used to calibrate parameters, fit functional forms, or select state coordinates.

---

## 1. Ontology: The Stabilized Reduced State Space

Earlier iterations of the general theory suffered from repeated state churn—appending new microscopic variables every few experiments in an attempt to achieve zero-variance deterministic Markov closure. On fresh confirmation support, this pursuit was falsified: high-activity combat encounters create genuine, irreversible micro-path-dependence.

The reduced theory permanently stabilizes on a **10-dimensional state space** whose residual uncertainty is explicitly characterized, bounded, and small enough to support decision-making without microscopic agent tracking.

### A. Local Coordinates $\mathbf{X}_i(t)$ (Locality $i$)
1. **$M^*_i(t)$ — Rooted Civilian Membership Mass** $[0, \infty)$:
   - *Operational Definition*: Log-mass of radicalized civilian population organized into the active political underground.
   - *Role*: Exclusive generative carrier of spatial reproduction and radicalization.
2. **$F_i(t)$ — Fielded Combatant Force** $[0, \infty)$:
   - *Operational Definition*: $\log(1 + f_{\text{effective}})$, representing armed insurgent combatants conducting operations.
   - *Role*: Generates tactical coercive pressure; sustains combat attrition and consumes operational supplies.
3. **$E_i(t)$ — Embedded Foothold Infrastructure** $[0, 1]$:
   - *Operational Definition*: Physical sanctuary depth, caches, fortified base networks, and local intelligence access.
   - *Role*: Lowers combat attrition, stabilizes local presence, and anchors organizational endurance.
4. **$C_i(t)$ — Net Territorial Governance Control Margin** $[-1, +1]$:
   - *Operational Definition*: Net institutional compliance differential $(c_{\text{ins},i} - c_{\text{gov},i})$.
   - *Role*: Primary order parameter governing civilian cooperation, intelligence production, and fiscal extraction.
5. **$\Phi_{\text{net},i}(t)$ — Signed Net Transport Flux** $(-\infty, +\infty)$:
   - *Operational Definition*: Conservative net spatial reallocation of armed forces into/out of locality $i$.
   - *Role*: Resolves spatial redeployment; achieves complete closure in intermediate activity regimes.
6. **$A_i(t)$ — Structural Administrative Capacity** $[0, 1]$:
   - *Operational Definition*: Physical state administrative infrastructure and bureaucratic machinery.
   - *Role*: Rebuilt through hierarchical state pipelines; slow-decaying institutional foundation.

### B. Global Coordinates
7. **$K_o(t)$ — Central Liquid Organizational Capital** $[0, \infty)$:
   - *Operational Definition*: Central insurgent treasury backing payroll, supply burn, and equipment procurement.
   - *Role*: Global solvency regulator. Governs operational runway; $K_o = 0$ triggers unconditional organizational collapse.

### C. Slow Memory Stocks
8. **$P_{G,i}(t)$ — Police Professionalism Standard** $[0, 1]$:
   - *Role*: Local procedural discipline and investigative competence independent of headcount; drives intelligence penetration and underground disruption.
9. **$V_{G,i}(t)$ — Government Formation Veterancy** $[0, 1]$:
   - *Role*: Accumulated combat experience; enhances tactical exchange performance but is diluted by green replacements.
10. **$V_{I,i}(t)$ — Insurgent Formation Veterancy** $[0, 1]$:
    - *Role*: Insurgent tactical experience modifier entering capability as $g(E) = 0.75 + 0.50 E$.

---

## 2. Core Governing Laws & Causal Identities

### A. Closed Organizational Resource & Runway Law
[SYNTHETICALLY IDENTIFIED — `mobilization_resource_results_v1.json`, `organizational_resource_identity_v1.json`]

The naive 1D scalar strain hypothesis $\sigma = (r \cdot f)/c$ was conclusively falsified (FALS-001). Under closed accounting, insurgent organizational survival is governed by a strict stock-flow capital ledger:
$$\frac{dK_o}{dt} = \sum_{i} \left[ \tau_{\text{tax}} \max(0, C_i) Y_i \right] - \text{Burn}(r, f)$$
where operational expenditure follows the 3-term burn law:
$$\text{Burn}(r, f) = \kappa_r r + \kappa_{rf} r f + \kappa_f f$$
Every observed collapse in the 960-trajectory factorial coincided exactly with $K_o = 0$. Solvency is governed by runway time $\tau_{\text{runway}} = K_o / \text{Burn}$, not instantaneous strain.

### B. Non-Local Recruitment & Propagation Kernel
[SYNTHETICALLY IDENTIFIED — `nonlocal_reproduction_confirmation_results_v1.json`, `reproduction_hazard_kernel_confirmation_results_v1.json`]

Nearest-neighbor adjacent reproduction was falsified (FALS-011): 75.95% of established offspring were non-adjacent, and 97.10% first appeared via civilian recruitment events. Non-local branching probability is governed by a dynamic hazard-augmented kernel:
$$\Pr(j \text{ establishment} \mid i \text{ parent}) = \sigma\Big( \alpha_0 + \alpha_{\text{geo}} \mathbf{x}_{\text{geo}, ij} + \alpha_{\text{soc}} \mathbf{x}_{\text{soc}, ij} + \alpha_{\text{haz}} \log(1 + H_{\text{rec}, ij}) \Big)$$
Early recruitment hazard mass $H_{\text{rec}, ij}$ provides statistically significant predictive gain over static geography and social networks alone (+0.0245 AUC at 90d, +0.0269 AUC at 180d, $p < 0.001$).

### C. Human Capital Turnover-Learning Tradeoff
[SYNTHETICALLY IDENTIFIED — `force_discrimination_results_v1.json`, `human_capital_absorption_confirmation_results_v1.json`]

Formation combat experience $E(t)$ satisfies the continuous turnover-learning balance:
$$\frac{dE}{dt} = \ell (1 - E) + \frac{I}{F} (E_r - E)$$
where $\ell$ is operational field learning, $I/F$ is the replacement turnover rate, and $E_r$ is replacement experience ($E_r = 0.10$).
- *Deficit Condition*: Experience declines whenever replacement rate exceeds field learning:
  $$\frac{I}{F} > \frac{\ell (1 - E)}{E - E_r}$$
- In fresh confirmation across 256 trajectories, accelerating the replacement pipeline (4x/4x vs 0.5x/0.5x) recovered +38.0 percentage points more headcount by day 360, but incurred a +10.1 percentage point larger veterancy-specific combat capability deficit at identical realized manpower.

### D. Dual-Channel State Capacity Divergence
[SYNTHETICALLY IDENTIFIED — `state_recovery_mechanism_factorial_results_v1.json`]

A critical empirical puzzle in synthetic state rebuilding—rising structural administrative capacity alongside stagnant or declining institutional governance—was resolved via 2x2 causal discrimination:
1. **Technical Administrative Rebuilding**:
   $$\frac{dA_i}{dt} = \text{AdminGain}(I_i, K_G) - \frac{1}{2} \text{Decay}_{\text{admin}}$$
   Explicit state regeneration reliably generates positive administrative stock recovery ($+0.1012$ gap closure on $Q$).
2. **Political Capacity Evolution**:
   $$\frac{dQ_{\text{inst}}}{dt} = \text{ServiceLearning} - \text{QualityDecay} - \text{PatronageDamage}$$
   Political order processes act as an endogenous erosion sink under shock conditions, producing $-0.1512$ net institutional capacity degradation. Structural administrative capacity and political institutional capacity are distinct dynamical stocks with opposing trajectories.

---

## 3. Strategic Closure & Characterized Residual Uncertainty

[SYNTHETICALLY IDENTIFIED — `strategic_closure_residual_uncertainty_v1.json`, `falsification_ledger_v4.json`]

To resolve the strategic closure bottleneck without unending state proliferation, 24 matched counterfactual pairs were evaluated across 32 common-random-number continuation branches over a 30-day decision horizon on untouched support:

```
+------------------+-----------------------+-----------------------+------------------------------------------+
| Activity Stratum | Sig & Large Pair Rate | Mean Control Diff SMD | Residual Characterization                |
+------------------+-----------------------+-----------------------+------------------------------------------+
| Low / Dormant    | 0.0% (0 / 8 pairs)    | 0.0028                | Exact Markov Closure                     |
| Intermediate     | 0.0% (0 / 8 pairs)*   | 0.0245                | Bounded Spatial Closure (under net flux) |
| High / Kinetic   | 37.5% (3 / 8 pairs)   | 0.0528                | Stochastic Innovation Closure            |
+------------------+-----------------------+-----------------------+------------------------------------------+
* In candidate `rootedstock_net12v3`.
```

### The Anatomy of High-Activity Residual Uncertainty
In high-activity localities, counterfactual divergence is strictly localized:
- **Net Territorial Control ($C$)**: Remains tightly bounded (SMD = 0.0528; zero pairs show significant control divergence).
- **Administrative Capacity ($A$)**: Completely stable (SMD < 0.02).
- **Kinetic Attrition & Force ($F, E$)**: Diverges due to discrete tactical combat encounters and stochastic casualty draws (mean SMD = 0.512 for $\log F$).

### Theoretical Resolution: Stochastic Differential Representation
Rather than seeking further unobservable microstates, the reduced theory models the macrostate as a stochastic dynamical system:
$$d\mathbf{X}_i = \mathbf{f}_i(\mathbf{X}, \boldsymbol{\theta})\,dt + \mathbf{G}_i(\mathbf{X}_i)\,d\mathbf{W}_i(t)$$
where the diffusion covariance $\boldsymbol{\Sigma}_{\text{res}}(\text{activity}) = \mathbf{G}_i \mathbf{G}_i^T$ is diagonal and non-zero only for kinetic force $F$ and foothold $E$ under high activity ($\sigma_F \approx 0.25, \sigma_E \approx 0.17$). 

This uncertainty is bounded, characterized, and small enough to support robust minimax policy decisions.

---

## 4. Operational & Policy Decision Guidance

Under this stabilized reduced theory:
1. **Force Ratios vs Institutional Control**: Pure kinetic attrition cannot secure stability; governance control margin $C_i$ governs recruitment and compliance, while force ratio $F/S$ determines immediate attrition rates.
2. **Replacement Strategy**: Pumping raw replacements into high-casualty units dilutes formation veterancy, reducing combat capability by up to 16% at equal headcount. Quality-sustainable replacement pacing must respect the threshold $I/F \le \ell (1-E)/(E-E_r)$.
3. **Fiscal Allocation**: Central fiscal subsidies saturate rapidly; state institutional rebuilding requires protecting local administrative integrity from political patronage extraction rather than purely expanding financial transfers.
4. **Counter-Insurgent Interdiction**: Interdiction is most effective when targeted at rooted membership underground networks ($M^*$) and central capital runway ($K_o$), which govern reproduction and macro-viability.

---

## 5. Certification Manifest

| Deliverable | Path | Status |
| :--- | :--- | :--- |
| Theory Status | `studies/research_program/general_theory_v1/theory_status_v6.json` | COMPLETE |
| Falsification Ledger | `studies/research_program/general_theory_v1/falsification_ledger_v4.json` | 17 Permanent Entries |
| Strategic Closure | `studies/research_program/general_theory_v1/strategic_closure_residual_uncertainty_v1.json` | Certified Bounded |
| Reduced Specification | `studies/research_program/general_theory_v1/reduced_theory_specification_v2.json` | Stabilized (10 Dim) |
| Factorial Evidence | `studies/research_program/general_theory_v1/state_recovery_mechanism_factorial_results_v1.json` | Both Gates Passed |
| Human Capital Evidence | `studies/research_program/general_theory_v1/human_capital_absorption_confirmation_results_v1.json` | Confirmed (3 Gates Passed) |
| Hazard Kernel Evidence | `studies/research_program/general_theory_v1/reproduction_hazard_kernel_confirmation_results_v1.json` | Confirmed (90d/180d Passed) |
