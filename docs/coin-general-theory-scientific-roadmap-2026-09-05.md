# From Pineland v5 to a general theory of COIN: scientific roadmap

Prepared 2026-09-05. This is a proposed research sequence, not a finding of efficacy or an amendment to the frozen historical contracts.

## Current execution and scientific position

At approximately 17:10 EDT, no Pineland simulation worker, coordinator, or readout watcher remained alive. The `running` status file was stale. Four complete Nepal trajectories survived and passed the original execution-contract model/diff checks: seeds 20011126, 20021133, 20031140, and 20041147, each covering 1,821 simulated days. Their runtimes were 35.9–39.9 minutes. The other four seeds had no saved result. The termination cause is unknown; the available log does not establish a simulation exception or out-of-memory event.

The missing seeds were resumed using a detached launcher under the original certified v5 core. The completed files were preserved. The scorer must wait for all eight members. Afghanistan has not yet begun its v5 ladder. The separate `codex/exact-performance` implementation has a 1.53x measured speedup on a 180-day comparison with exact matched hashes, but is not the source used by this historical execution contract.

Scientifically, v5 has established software correctness and synthetic architectural support, not historical predictive superiority or intervention validity. Nepal v4 remains a predictive failure. Calibration and COIN inference remain unlicensed. Some older case-ladder prose still refers to v2/v3; the live v5 freeze and case-specific artifact provenance take precedence over those historical labels.

The desired endpoint is a **small, falsifiable set of causal mechanisms and scope conditions explaining durable political/security outcomes across settings**, with independently supported intervention predictions. A large ABM, a convincing historical narrative, or a violence-forecast improvement is insufficient by itself.

## 1. Define the theory's explanatory target and causal estimands

Specify units, scales, population of settings, exposure histories, and evaluation horizons before further fitting: organization–locality–time for mechanisms; case-native administrative units for observations; actor networks for spillovers. Define how aggregation maps between them.

Retain the outcome vector:

\[
Y=(V,C,H,I,G,D,R),
\]

where V is violence, C multidimensional control, H civilian harm, I institutional capacity, G insurgent regeneration, D foreign dependence, and R recurrence. Distinguish quiet caused by organizational loss, accommodation, clandestine survival, displacement, reporting failure, and dominance. Define persistence and recurrence windows independently of observed fit.

For intervention policies g and g0, specify the vector estimand

\[
\Delta_c(g,g_0;T)=E[Y_T^{g}-Y_T^{g_0}\mid\text{target population in case }c].
\]

Policies can depend on measured past history; do not silently grant them access to simulated hidden truth. Define resource constraints and the population over which the expectation is taken. A scalar welfare function requires explicit substantive weights; it is not implicit in lower violence.

**Gate:** an estimand registry with observable definitions, denominators, horizons, and falsifiers. The existing outcome and intervention contracts are the starting point, not replacements for this specification.

## 2. Finish the once-only historical confrontation

Complete the remaining Nepal seeds, verify the full ensemble's identities, source hashes, case inputs and split hashes, and score the same 19,575 district-week rows against exactly the preserved competitors. Apply the existing all-holdout Brier/log-score rule unchanged. Preserve raw predictions and unsuccessful results.

Then execute Afghanistan initialization → smoke → one year → full horizon → identical-row competition, retaining the independent control assessment. Structural preflights establish executable, conserved dynamics; they do not establish historical fit. The three Afghanistan initial-strength conditions quantify a slice of initialization uncertainty, not three independent stochastic replications.

Use the declared diagnostic decomposition to separate rate error, discrimination, latent-to-recorded information loss, and model-implied control signal. Aggregate action-funnel counts cannot identify locality-specific belief or support errors. A pass motivates further testing; a failure requires a localized, independently justified hypothesis rather than event-rate tuning.

**Gate:** provenance-bound case decisions and diagnostic reports, with no promotion of a partial ensemble.

## 3. Establish construct validity and independent observation models

Build an actor-resolved, dated measurement system for organizational presence/capacity, mobilization, institutional continuity, territorial control, support dependence, civilian harm, and recurrence. Separate source records from latent constructs. Record actor splits/mergers, changing boundaries, reporting access, assignment uncertainty and missingness.

Model observations explicitly, for example

\[
X_{t+1}\sim p_\theta(X_{t+1}\mid X_t,A_t,E_t),\qquad
O_t\sim p_\phi(O_t\mid X_t,E_t),
\]

where X is latent state, A actions, E environment, and phi measurement parameters. Distinguish actors' own observations/beliefs from the researcher's historical records. Multiple sources can share reporting bias; source count is not independence. Assess nonrandom missingness and test sensitivity to plausible selection processes. Validate ordinal control operators against independent evidence; recovering labels generated by the same synthetic operator validates computation, not the historical construct.

**Gate:** case-specific measurement/crosswalk manifests, frozen operators and success criteria, independent control/presence evidence, and uncertainty intervals. Missing capacity data remain missing; event recurrence must not substitute for them.

## 4. Specify competing causal explanations before adding mechanisms

Turn competitive local reproduction into explicit rival models: persistent organizational stocks; renewed recruitment; relocation; political accommodation; external replenishment; differential state presence; and persistence in reporting. Specify which temporal sequences and joint outcomes distinguish them.

Draw a time-indexed causal graph connecting capacity, access, information, beliefs, action choice, execution, control, civilian response and future capacity. Mark direct assumptions separately from emergent simulator behavior. Include feedback, endogenous government action, actor heterogeneity, and network interference. Government, police, foreign actors and insurgents should share comparable accounting and decision semantics where constructs overlap; actor symmetry does not require identical parameters.

**Gate:** a mechanism registry mapping each claim to an equation/process, rival explanation, observable implication, discriminating experiment, and failure criterion. Complexity is admitted only when a demonstrated explanatory gap warrants it.

## 5. Demonstrate structural and practical identifiability

Ask two separate questions: could distinct parameters/mechanisms produce indistinguishable observations even with unlimited data, and can the available finite noisy data distinguish them? Use matched synthetic worlds, parameter-recovery experiments, sensitivity/Jacobian rank where applicable, likelihood/profile or posterior geometry, and adversarial observational-equivalence examples.

Recover local ignition, parent-attributed colonization, fielding/deepening and survival separately. Preserve multi-parent uncertainty, censoring and competing activation risks. Relocation must not count as reproduction; survival of an existing organization must not be counted again as new organizational births. Separate action feasibility, choice, execution success and recording.

Follow the existing question-level parameter budgets instead of a global parameter search. If a Bayesian estimator is used, simulation-based calibration checks the inference algorithm; it does not establish identifiability or historical truth. [Talts et al., simulation-based calibration](https://arxiv.org/abs/1804.06788).

**Gate:** recover identifiable estimands and calibrated uncertainty under known truth, reject specified nulls, and report nonidentifiable combinations or bounds. Do not obtain apparent identification merely by imposing narrow priors.

## 6. Build a defensible estimation and uncertainty workflow

Only after the relevant recovery gate, estimate permitted parameters on training data, using sourced priors and explicit case inputs. Choose likelihood-based or simulation-based inference according to the measurement model; validate any approximation or emulator against simulator outputs before using it for inference.

Separate stochastic simulation, parameter, initialization, measurement, structural and numerical uncertainty. Report Monte Carlo error separately from empirical uncertainty. For future experiments, preregister seed budgets or valid precision-based stopping rules; never stop when a favored result first appears. The current eight-seed historical contract remains fixed.

**Gate:** recovery/coverage evidence, convergence or approximation diagnostics, sensitivity to priors and missingness assumptions, and uncertainty sufficient to resolve the declared scientific question. If the data cannot resolve it, the result is an interval or an unresolved claim.

## 7. Establish incremental predictive value on genuinely informative tests

Require improvements over relevant reduced structural models as well as statistical competitors: persistence, renewal, diffusion, static geography, force ratios, manpower and event-history models. Match information access and forecast origin; a simulator using future case covariates is not directly comparable to a predictor denied them.

Score calibration and discrimination separately. Use proper scores for probability forecasts, while retaining the frozen current scoring implementation; future smoothing or predictive-distribution changes require prospective specification. [Gneiting and Raftery, proper scoring rules](https://sites.stat.washington.edu/people/raftery/Research/PDF/Gneiting2007jasa.pdf).

Evaluate control/presence and joint outcomes, not violence alone. Handle spatial/temporal dependence in uncertainty estimates; thousands of rows from one conflict are not thousands of independent cases. Evaluate regime transitions and quiet periods as well as average performance.

Crucially, Nepal outcomes have already informed development and diagnosis. A new core freeze does not make previously inspected holdouts pristine. Afghanistan also contains previously inspected evidence. Maintain an exposure ledger and reserve genuinely untouched cases, periods or data sources for stronger confirmation.

**Gate:** meaningful out-of-sample improvement beyond simpler models, uncertainty-aware comparisons, and explicit disclosure of which tests are developmental versus confirmatory.

## 8. Identify which mechanisms actually carry the improvement

Use preregistered ablations and factorial contrasts to separate capacity persistence, information, political access, sustainment, recruitment and observation. Hold stocks and exposure budgets comparable where that is part of the estimand. Verify that removing a mechanism does not merely break accounting or make the comparison physically incoherent.

Distinguish a fixed-parameter ablation (the implemented model depends on this component) from a separately trained reduced model (the component adds explanatory value beyond re-estimation). Both can be informative, but answer different questions. A successful package does not establish every constituent mechanism.

Where mechanisms interact, estimate the interaction rather than adding isolated effects. Use common random numbers only with verified unchanged marginal distributions; matching seed labels alone does not guarantee effective pairing after event schedules diverge.

**Gate:** mechanism-specific incremental value and stable directions on independent control/joint outcomes, with alternative mechanisms and measurement explanations still represented where observationally equivalent.

## 9. Connect simulated intervention effects to empirical causal evidence

Randomized interventions inside an ABM identify effects under the ABM's equations. They do not establish effects in historical populations. Obtain independent evidence for the relevant causal links using defensible historical/natural-experiment designs, longitudinal records, and institutional/process evidence.

Specify a target-trial-style protocol where useful: eligibility, time zero, interventions, assignment assumptions, follow-up and outcomes. Address confounding by indication, time-varying confounders affected by prior action, differential measurement, positivity/overlap and interference. Use longitudinal causal methods only when their assumptions are supportable; otherwise present sensitivity analyses or partial-identification bounds. [Hernán and Robins, Causal Inference: What If](https://miguelhernan.org/whatifbook).

**Gate:** an empirical identification argument for intervention-relevant relationships, or an explicit statement that the effect remains model-conditional. Forecast accuracy cannot substitute for this gate.

## 10. Run the preregistered COIN counterfactual program

Once licensed, evaluate the existing contrasts covering sustained presence, information quality, indigenous capacity versus foreign substitution, political access, local security continuity, rotation, logistics, sanctuary dependence and withdrawal. Define interventions at the institutional/policy level and retain equalized resource constraints where specified.

Evaluate trajectories of all seven outcomes, distributed effects, spillovers/displacement and post-support durability. Include adaptive responses by all actors; a policy comparison against an artificially nonresponding opponent answers a narrower question. Test apparent success after the intervention ends, not just during its application.

Do not optimize a policy on the same simulated conditions used to report its performance. Reserve separate scenario/parameter regimes for policy evaluation. Report Pareto tradeoffs rather than hiding harm or dependency inside a violence objective.

**Gate:** predeclared outcome-vector effects with uncertainty, persistence after withdrawal/support changes, and no claim resting solely on a reduction in recorded attacks.

## 11. Test transportability across the case ladder

Complete Colombia, Iraq and Vietnam case construction before transfer claims: source inventories, longitudinal actor/control crosswalks, population/geography, observation models, frozen forecast origins and case-input uncertainty. A harmonized schema or isolated control snapshot does not establish a usable longitudinal test.

Separate mechanisms proposed as invariant from case-specific inputs, parameters and measurement processes. Predeclare any hierarchical partial pooling; compare transport without holdout refitting. Explain heterogeneity using independently measured moderators, not case labels added after a reversal.

Cross-case prediction and causal transportability are different questions. A causal effect can transfer only under justified assumptions about which mechanisms and population features differ. [Pearl and Bareinboim, transportability](https://arxiv.org/abs/1503.01603).

**Gate:** replicated conditional claims across genuinely different settings and independent control/joint outcomes. The program's minimum of two transfer cases is an administrative floor, not a statistical theorem that two cases establish a general theory.

## 12. Test structural robustness and intervention disagreement

Maintain a set of empirically plausible model structures and observation models, not just parameter draws from one favored architecture. Check whether they agree on the sign, magnitude and ranking of intervention effects. Structural disagreement among equally predictive models is itself an important result.

Stress-test resolution, calendar-time discretization, actor aggregation, network topology, missingness, reporting changes, initial conditions and external support. Use synthetic falsifiers and efficient experimental designs first; reserve expensive full simulations for distinctions that remain unresolved. Emulators may screen designs but must not silently replace final mechanistic evidence.

**Gate:** intervention conclusions survive relevant plausible alternatives, or the report identifies the information needed to discriminate them. Narrow posterior intervals within one assumed structure do not resolve between-structure uncertainty.

## 13. Reduce the surviving results to a compact conditional theory

Extract a minimal dynamical representation linking organizational renewal/loss, local access, belief formation, institutional competition and durable outcomes. Derive statements about when effects change sign, when quiet is reversible, when capacity is self-sustaining, and when externally supported control persists after support removal.

A reproduction threshold may be useful only after its offspring unit, risk set and generational accounting are defined. A candidate next-generation matrix K could support a local threshold based on its spectral radius under an appropriate branching/linearization approximation. It is not automatically a universal insurgency reproduction number: immigration, relocation, nonlinear feedback, finite populations and changing policy can invalidate that interpretation. In an open system, zero activity need not be an absorbing state.

Seek explanatory compression: fewer independently supported mechanisms should reproduce the distinguishing patterns and counterfactual differences. If a much simpler model matches them, simplify the theory. Publish scope conditions and unresolved equivalence classes alongside the retained laws.

**Gate:** a small set of testable conditional propositions whose predictions survive the evidence above and whose failure conditions are known. Do not elevate an appealing threshold or simulation regularity into a historical law without identification.

## 14. Obtain independent replication and new predictions

Release a complete model/experiment specification, versioned data transformations, source/measurement audits, run manifests, negative results and reproduction code. An ODD-style description should expose initialization, scheduling, submodels and rationale sufficiently for independent implementation. [Grimm et al., ODD update](https://www.jasss.org/23/2/7.html).

Seek independent implementation and evaluation on unexamined settings or subsequently available observations. Pre-register novel discriminating predictions rather than only reproducing fitted histories. Replication should challenge both the substantive mechanism and the observation process.

**Gate:** others reproduce the result and the theory survives predictions it did not help select. Generality is accumulated evidence with explicit scope, never a final software flag.

## Efficient dependency order from here

| Priority | Work | What it decides |
|---|---|---|
| Now | Finish original Nepal ensemble and staged Afghanistan confrontation | Whether v5 adds predictive information under the declared evaluation |
| In parallel | Measurement/actor-history construction; untouched-data ledger; identifiability designs | Whether the important latent states and mechanisms can be tested at all |
| After results | Diagnose the earliest unsupported causal link; compare reduced explanations | Which theoretical bottleneck deserves the next experiment |
| After recovery | Question-specific estimation and uncertainty propagation | Which parameters/estimands can be learned without invented precision |
| After transfer and causal support | Preregistered policy contrasts and structural robustness | Which intervention effects are defensible beyond one simulator |
| Finally | Theory reduction, new predictions, independent replication | Whether a compact conditional general theory survives |

Historical failure can still yield a major scientific advance if it rules out an attractive mechanism or demonstrates that a policy-relevant estimand is unidentifiable. The target is reliable explanatory and causal information per experiment, not more mechanisms or more computation.

## Repository contracts used

- `studies/research_program/core_freeze.json`
- `studies/research_program/historical_revalidation_v5/execution_contract.json`
- `studies/research_program/v5_theory_discrimination_contract.json`
- `studies/research_program/predictive_competition_gate.json`
- `studies/research_program/outcome_measurement_contract.json`
- `studies/research_program/identifiability_plan.json` and `identifiability_triage.json`
- `studies/research_program/theory_extraction_protocol.json`
- `studies/research_program/coin_interventions.json`
- `studies/research_program/case_ladder.json`

The methodological references support the proposed research methods; none is offered as evidence that Pineland has already established a substantive COIN mechanism.
