---
title: "Suffering from Success: Relief, Yield, and Retention in Security Assistance"
bibliography: references.bib
date: "September 21, 2026"
keywords: "security assistance; military effectiveness; partner forces; sustainment; logistics; agent-based modeling"
---

# Abstract

Security assistance often improves partner performance during deployment without building durable capability. This article separates **relief** (improving a limiting service), **yield** (resulting whole-force capability), and **retention** (capability surviving withdrawal). I evaluate this framework in the Pineland agent-based simulation across a 2,808-world Stage-4 campaign, a 1,472-world coordinated-development extension, and matched no-aid controls. At +30 days post-withdrawal, 26 of 120 treated cells exhibit supported capability above no aid but retained capability below no aid; 30 improve in both branches and 51 fall below in both. Bottleneck migration readily occurs in command and force generation but generates little whole-force yield. A demand-clamp ablation confirms capability sensitivity to operational requirements, though harness measurement limitations leave coverage mediation unconfirmed. Developmental assistance builds partner-owned sustainment but trades off against immediate capability and cost. The contribution is a diagnostic production framework demonstrating why local assistance success, whole-force effectiveness, and autonomous retention diverge.

# 1. Introduction

Security assistance is often evaluated through related but non-identical questions: Did the donor relieve the targeted military constraint? Did whole-force capability improve? Could the partner reproduce that capability after external assistance ended? Existing scholarship explains disappointing assistance outcomes through provider-recipient interest misalignment, weak institutions, limited leverage, fragmented security sectors, poor absorptive capacity, and dependence on foreign patronage [@biddle2017; @biddle2018; @metz2023; @matisek2018; @knowlesmatisek2019; @harkness2022; @sandnes2024]. Recent work also treats security assistance as a relational practice reshaping authority, alignment, and dependency [@rolandsen2021; @rolandsen2026].

This article addresses a narrower production problem: even when assistance succeeds in the function it targets, three outcomes can diverge. **Relief** concerns the targeted bottleneck. **Yield** concerns whole-force capability. **Retention** concerns what survives after external provision stops. Collapsing these into a single metric obscures assistance dynamics. A program can resolve a training deficit without raising force effectiveness because logistics binds next; it can raise supported output without creating a retained gain because operational requirements outpace indigenous sustainment; or it can improve both supported and retained capability.

These mechanisms draw on established theoretical foundations. Theory of Constraints notes that relieving one bottleneck exposes another [@watson2007]. Hirschman's unbalanced-growth framework treats expansion in one activity as inducing complementary shortages elsewhere [@hirschman1958]. Foreign-aid research demonstrates that external inputs often increase claims on scarce local administrative or recurrent resources [@roodman2006; @arimotokono2009]. The contribution here is translating these insights into a military production model that separates outcomes and subjects candidate mechanisms to distinct empirical tests.

The first mechanism is **requirement expansion**. External aid enables larger formations, greater mobility, patrols, or combat, generating complementary service requirements. If demand for a complementary indigenous service expands faster than indigenous production, partner coverage of that requirement falls even as absolute delivery rises. This is a numerator-denominator dynamic that does not require the binding service to change. The second is **constraint displacement**: relieving the limiting service shifts the bottleneck to another channel, yielding little whole-system return until the new constraint is resolved.

These mechanisms necessitate a rigorous benchmark. Comparing continued support to withdrawal after shared assistance isolates a dependency gap, but does not prove assistance improved performance relative to no aid. The revised analysis therefore evaluates supported effects relative to matched zero-support trajectories ($S_h = C_h^{ON} - C_h^0$), retained effects after withdrawal ($R_h = C_h^{OFF} - C_h^0$), and the dependency gap ($G_h = C_h^{ON} - C_h^{OFF}$). A strict "success without retention" case requires supported capability above no aid and retained capability below no aid.

I evaluate this framework using Pineland, a partially observed agent-based model simulating military formations, logistics, command, recruitment, and territorial control. Stage 4 comprises 2,808 prospectively frozen production worlds across a Phase Map, a targeted bottleneck-displacement module, and a substitution-versus-development module. Stage 5 adds 1,472 frozen worlds testing coordinated development. Post-review analyses use frozen telemetry for matched no-aid comparisons and supply-demand decompositions, while a separately frozen demand-clamp experiment tests whether requirement expansion causally mediates terminal coverage gaps.

The revised evidence qualifies early headline claims. At +30 days, 26 of 120 treated Phase-Map cells exhibit the strict pattern: positive supported capability above no aid and negative retained capability after withdrawal. Thirty cells improve in both branches, 51 fall below no aid in both, one is negative under support but positive after withdrawal, and 12 are neutral. Support-induced dependence is thus a real, but not universal, regime.

Mechanism tests separate asymmetrically. Among worlds with negative terminal logistics coverage, supported branches face larger requirements, and descriptive standardization attributes more of the mean coverage gap to demand expansion than to indigenous production decline. However, the prospectively frozen demand clamp fails to validate that interpretation causally: while its manipulation succeeds, the ablation harness recorded a static pre-split baseline coordinate that structurally guaranteed a zero coverage branch difference, even as dynamic capability effects diverged. Requirement expansion remains descriptively plausible rather than causally identified. Conversely, the Migration module demonstrates that command and force-generation bottlenecks displace readily while logistics persists. Relieving force generation shifts the binding constraint while generating virtually zero capability gain. Constraint displacement thus explains relief without yield, not the terminal retention penalty.

Assistance architectures reveal further tradeoffs. Developmental logistics generates far more partner-owned capacity and superior terminal coverage than substitution, but requires higher modeled cost and does not dominate near-term capability, placing assistance modes on a capability-retention-cost frontier. Stage 5 detects selective two-way complementarities, but because its nominal near-tie worlds become logistics-bound before comparison, fixed-budget breadth findings apply to realized single bottlenecks rather than the intended multi-constraint condition.

The paper makes three contributions. First, it formalizes a minimal military production model distinguishing supported capability, retained capability, service coverage, and dependency gaps. Second, it separates empirical tests for requirement growth and constraint displacement, reporting confirmatory and disconfirmatory findings alike. Third, it provides a diagnostic evaluation framework measuring relief, yield, retention, demand, and sustainment separately. The scope is bounded: Pineland is a causal laboratory, not an empirical forecasting engine. Case studies of South Vietnam, Afghanistan, Iraq, Colombia, and Mali serve as structured external validation, preserving historical and political explanations alongside production dynamics.

# 2. Security Assistance, Dependence, and the Missing Production Dynamic

## 2.1 Interest misalignment and influence

A prominent strand of security-force-assistance scholarship treats suboptimal outcomes as an agency problem. Biddle, Macdonald, and Baker argue that external assistance frequently confronts systematic interest misalignment with host governments, limiting the military effectiveness achievable through small-footprint advising [@biddle2017; @biddle2018]. Metz expands on this through the lens of influence: recipient regimes often possess domestic political incentives to protect corrupt or patrimonial military arrangements, while foreign advisers routinely default to teaching and persuasion over stringent conditionality [@metz2023]. This work demonstrates why recipients resist reforms even when donors possess technical expertise. This article accepts that political foundation and asks a distinct, complementary question: conditional on assistance successfully improving a targeted military function, how does the recipient's internal production structure adapt afterward?

## 2.2 Fragile forces, weak institutions, and dependence

A second literature highlights the vulnerability of forces constructed without durable political or institutional roots. Matisek characterizes externally constructed militaries as brittle "Faberge Egg" forces liable to collapse upon donor departure [@matisek2018]. Knowles and Matisek similarly observe that technical training cannot substitute for local political settlement [@knowlesmatisek2019]. Harkness demonstrates that concentrating assistance in elite enclave formations creates localized operational proficiency while distorting broader civil-military stability [@harkness2022]. Sandnes conceptualizes relations between donors and the G5 Sahel Joint Force as asymmetric interdependence, highlighting structural barriers to autonomous sustainability [@sandnes2024].

Scholarship in international security has long distinguished immediate battlefield performance from long-term sustainability. Karlin incorporates the capacity to sustain forces independently into the core definition of successful military development [@karlin2018], while Reynolds proposes a Security Autonomy Index to assess whether recipients internalize external military models [@reynolds2025]. Policy and defense evaluations underscore similar themes. RAND analyses emphasize that converting foreign inputs into durable capacity requires institutional absorption [@mcnerney2016; @paul2013]. A GAO review of Section 333 train-and-equip proposals revealed that 42 of 46 proposals lacked documentation for sustainment or absorptive capacity [@gao2023].

State-capacity research sharpens this diagnosis. Pritchett, Woolcock, and Andrews define **premature load bearing** as placing operational demands on organizations that outstrip their institutional capabilities [@pritchett2013; @andrews2017]. The present theory operationalizes this dynamic mechanistically: successful external assistance can itself expand the operational requirements placed on a partner military, shifting which complementary service limits the force.

To clarify mechanisms, I distinguish three forms of dependency. **Operational dependence** occurs when military output cannot be sustained without continuing foreign service inputs. **Institutional dependence** arises when external provision displaces the development of indigenous administrative bodies. **Relational dependence** stems from unequal bargaining leverage. The framework here is fundamentally operational: while institutional and relational dynamics frequently interact with operational dependence, requirement expansion and constraint displacement do not require them.

## 2.3 Bottlenecks, recurrent costs, and complementary production

The primary theoretical antecedent is the Theory of Constraints: system output is determined by the active bottleneck; relieving a non-binding constraint yields little whole-system gain, while elevating the binding constraint inevitably exposes another [@watson2007]. Hirschman's unbalanced-growth framework provides a parallel macroeconomic logic: expansion in one activity induces bottlenecks and shortages across complementary sectors [@hirschman1958]. Development economics similarly explores recurrent-cost burdens. Roodman shows how donor projects overload recipient administrative capacity [@roodman2006], Arimoto and Kono model how donor capital investments generate recurrent liabilities that recipients cannot sustain [@arimotokono2009], and Morss highlights institutional decay under donor project proliferation [@morss1984].

In military production, this problem operates across functional domains. Upgrading command enables larger tactical formations; expanding recruitment increases logistics demands; and providing tactical mobility multiplies fuel, maintenance, and distribution requirements. This logic aligns with foundational theories of complementary production: Kremer's O-ring model demonstrates how failure in one indispensable task diminishes returns across all others [@kremer1993], and organizational economics demonstrates how returns to one practice depend on complementary capabilities [@milgromroberts1990]. Military scholarship has long recognized that combat power depends on complex organizational synthesis [@millett1986], operational employment [@biddle2004], and sustainment throughput [@vancreveld2004].

This focus separates the theory from standard accounts of absorptive capacity and aid dependence. Absorptive capacity concerns assimilating external knowledge [@cohenlevinthal1990]; here, a recipient can successfully assimilate assistance in one subsystem while failing to sustain the broader operational demands that success unlocks. Similarly, aid-dependence theories emphasize political distortions and weakened accountability [@knack2001; @brautigamknack2004; @moss2006]. The operational sequence examined here is distinct: assistance expands supported operations, service requirements outpace indigenous delivery, and local relief shifts the binding constraint without guaranteeing whole-system yield.

## 2.4 From static capacity to endogenous production dynamics

Military capability is jointly produced across force generation, logistics, and command. Assistance alters this production surface by enabling operations that enlarge complementary service demands. The analytical task is therefore developing a framework that models **supported capability, retained capability, service demand, indigenous delivery, and constraint migration** within an integrated production system.

# 3. Theory

## 3.1 A minimal complementary-production model

Consider a military system that requires services indexed by $j$. An
operation of scale or complexity $x$ requires $r_j(x)$ units of service
$j$. Indigenous production is $I_j$ and external provision is $E_j$.
Supported feasible capability and independently reproducible capability are



$$
C^{S}=\max x \quad \text{s.t.} \quad r_j(x)\le I_j+E_j \quad \forall j,
$$



and



$$
C^{A}=\max x \quad \text{s.t.} \quad r_j(x)\le I_j \quad \forall j.
$$



For the useful special case $r_j(x)=a_jx$, these reduce to



$$
C^{S}=\min_j\frac{I_j+E_j}{a_j},
\qquad
C^{A}=\min_j\frac{I_j}{a_j}.
$$



The result is elementary but important. A force can possess a high supported
capability and a much lower independently reproducible capability at the same
point in time. The gap $C^S-C^A$ is therefore a production property, not a
claim that indigenous capability has necessarily been destroyed.

The empirical analysis also records **indigenous coverage** of an observed
service requirement. For any active service with demand $D_j>0$,



$$
q_j^I=\frac{I_j}{D_j},
\qquad
q_j^S=\frac{I_j+E_j}{D_j}.
$$



The structural coverage coordinate is $q^I=\min_j q_j^I$, and the observed
binding service is $B=\arg\min_j q_j^I$. Coverage is deliberately kept
distinct from absolute capability. A lower $I/D$ ratio can reflect lower
indigenous service, a larger requirement, or both. It should not be described
as indigenous capability loss without decomposing its numerator and
denominator.

## 3.2 Relief, yield, and retention

Security-assistance performance is decomposed into three outcomes.

**Relief** asks whether an intervention improves or removes the service that was
limiting the system. **Yield** asks how much whole-force capability the
intervention produces. **Retention** asks how much of that capability remains
after the additional external service stops.

These quantities can be represented against a common no-aid benchmark. Let
$C_h^0$ be capability at horizon $h$ under matched no aid, $C_h^{ON}$
capability with continued support after the split, and $C_h^{OFF}$ capability
after the same supported prehistory followed by withdrawal. Then



$$
S_h=C_h^{ON}-C_h^0
$$



is the supported effect,



$$
R_h=C_h^{OFF}-C_h^0
$$



is the retained effect, and



$$
G_h=C_h^{ON}-C_h^{OFF}=S_h-R_h
$$



is the dependency gap between continued support and withdrawal. A strong
success-without-retention case requires $S_h>0$ and $R_h<0$. This is a
stricter condition than simply observing $C_h^{ON}>C_h^{OFF}$, because the
latter can arise when withdrawal harms a force that was not outperforming the
matched no-aid trajectory.

The three-part framework also separates two system dynamics that the original
draft treated as one. **Requirement expansion** can create yield without
retention. **Constraint displacement** can create relief without much yield.
Neither mechanism logically requires the other.

## 3.3 Requirement expansion and indigenous coverage

Suppose assistance allows the force to operate at a higher supported scale
$C^S$. Service demand may then rise with that operating scale. Write the
requirement for service $j$ as $D_j=g_j(C^S)$, with $g_j'\ge0$. Indigenous
coverage is



$$
q_j^I=\frac{I_j}{g_j(C^S)}.
$$



For positive values, the change in log coverage decomposes exactly as



$$
\Delta\ln q_j^I=\Delta\ln I_j-\Delta\ln D_j.
$$



Coverage therefore falls whenever proportional growth in the service
requirement exceeds proportional growth in indigenous service. This can occur
even when $I_j$ increases in absolute terms. It can also occur while the same
service remains binding throughout. Requirement expansion is therefore a
distinct mechanism from bottleneck migration.

**Proposition 1, Requirement Expansion.** Conditional on an assistance-induced
increase in operating requirements, indigenous coverage of service $j$ falls
when $D_j$ grows faster than $I_j$.

**Proposition 2, Supported-Retained Divergence.** Assistance can generate a
positive supported effect $S_h$ while producing a smaller or negative retained
effect $R_h$ when the supported system depends on service production that the
partner does not reproduce after withdrawal.

## 3.4 Constraint displacement and system yield

Requirement expansion is not the only reason local improvement can fail to
translate into system performance. In the linear special case, suppose service
$k$ is the unique supported bottleneck. Increasing external service $E_k$
raises $C^S$ only until



$$
\frac{I_k+E_k}{a_k}
=
\min_{j\ne k}\frac{I_j+E_j}{a_j}.
$$



Beyond that threshold, another service binds and the marginal system return to
additional service $k$ is zero unless the new constraint is also relieved.
This is **constraint displacement**. It is the standard bottleneck logic applied
to a partner force whose service levels can be altered selectively by external
assistance.

The distance between the lowest and second-lowest service coverage levels can
describe the initial spacing of constraints, but it does not determine realized
yield once assistance changes operations and demand. The paper therefore treats
static headroom as a descriptive diagnostic rather than a causal predictor.

**Proposition 3, Constraint Displacement.** Assistance that relieves a binding
service can shift the limiting constraint to another service; once displaced,
additional improvement of the relieved service can have little or no
whole-system yield.

This proposition does not predict a retention penalty. Migration can accompany
positive, zero, or negative retained outcomes.

## 3.5 Substitution, development, and coordinated growth

Direct substitution increases $E_j$. Developmental assistance seeks to raise
$I_j$. Development at a persistently binding service can therefore improve
indigenous coverage, but it need not dominate substitution on near-term
capability or modeled donor cost. The relevant policy object is a frontier among
supported capability, retained capability, indigenous service, time, and cost,
not a single ranking of assistance modes.

If several services are genuinely near binding, coordinated development may
generate technical complementarity. For two services, the equal-dose factorial
interaction is



$$
I_{AB}=Q_{AB}-Q_A-Q_B+Q_0,
$$



where $Q$ is the prespecified terminal system coordinate. A positive
interaction identifies complementarity on that outcome. A different question
is whether spreading a fixed total developmental dose across services beats
concentrating it on the best single channel. The latter requires a valid
near-tie manipulation and cannot be inferred from complementarity alone.

![Figure 1. Security assistance can separate relief, yield, and retention.
Requirement expansion affects the transition from supported yield to retained
capability when service demand grows faster than indigenous production.
Constraint displacement affects the transition from local relief to system
yield when another complementary service becomes binding.](figures/figure1_conceptual.png)

## 3.6 Empirical implications

The two mechanisms imply different observable patterns. Requirement expansion
is supported when the continued-support branch generates a larger service
requirement than its matched withdrawal branch and clamping that excess demand
attenuates the terminal coverage gap. Constraint displacement is supported when
the targeted service ceases to bind but system yield remains limited by a
different service. Neither pattern is sufficient evidence for the other.

The framework is weakened if continued support does not enlarge relevant
requirements, if clamping the requirement leaves the coverage gap unchanged,
or if the reportedly displaced service remains the marginal determinant of
whole-system output. These tests are reported separately rather than combining
them into a single migration-mediated theory of dependence.

# 4. Research Design

## 4.1 Why use a synthetic experiment?

The primary variables in the theory are difficult to isolate observationally. External inputs, indigenous outputs, operational requirements, and counterfactual trajectories following withdrawal are rarely observed at comparable temporal and functional granularity. Partner forces also select into foreign assistance non-randomly, donor packages fluctuate with tactical conditions, and withdrawal decisions reflect political calculations.

Pineland functions as a causal laboratory rather than an empirical forecasting engine. It explicitly tracks service flows, enables exact cloning of world states at withdrawal, and allows researchers to manipulate individual assistance components while holding background environments and stochastic sequences constant. This design provides causal identification of mechanisms that remain unobservable in historical records, though it does not directly estimate historical effect magnitudes.

## 4.2 Pineland partner-force architecture

Pineland is a partially observed agent-based simulation of insurgency, governance, logistics, command, and foreign assistance, documented under the ODD protocol [@grimm2020odd]. This paper analyzes an embedded partner-force production layer comprising three complementary service channels: force generation, logistics, and command. Each channel tracks demand, indigenous capacity, and external provision in common units.

| Channel | Demand Functional Form | Indigenous Service Form | External Service Form |
|---|---|---|---|
| Force generation | $D_{\text{fg}} = L_{\Delta t}$ (realized military losses) | $I_{\text{fg}} = \mu_{\text{fg}} K_{\text{fg}}$ (training pipeline throughput) | $E_{\text{fg}}$ (externally enabled incremental graduates) |
| Logistics | $D_{\text{log}} = \sum_t (c_{\text{pres}} P_t \Delta t + c_{\text{move}} M_t + c_{\text{patrol}} H_t^{\text{patrol}} + c_{\text{combat}} H_t^{\text{combat}})$ | $I_{\text{log}} = \min(S_t^{\text{depot}}, \mu_{\text{log}} K_{\text{log}})$ (depot deliveries) | $E_{\text{log}}$ (direct external logistics delivered) |
| Command | $D_{\text{cmd}} = \kappa O_{\Delta t}$ ($\kappa = 0.5$ per order opportunity) | $I_{\text{cmd}} = \mu_{\text{cmd}} O_{\Delta t}$ (indigenous headquarters execution) | $E_{\text{cmd}}$ (external advisory / C2 service) |

Structural coverage is evaluated across active channels with positive demand ($D_j > 0$). The binding bottleneck is the active channel with the lowest indigenous coverage ratio:

$$
q^I = \min_{j \in \{\text{fg}, \text{log}, \text{cmd}\}} \frac{I_j}{D_j}, \qquad B = \arg\min_j \frac{I_j}{D_j}.
$$

Logistics demand $D_{\text{log}} = g_{\text{log}}(C^S)$ is endogenous, accumulating through presence consumption ($c_{\text{pres}}$ per person-day for active forces $P_t$), movement ($c_{\text{move}}$ per person-km for maneuvers $M_t$), patrols ($c_{\text{patrol}}$ per patrol hour $H_t^{\text{patrol}}$), and combat consumption ($c_{\text{combat}}$ per contact hour $H_t^{\text{combat}}$). Force generation demand $D_{\text{fg}}$ equals realized casualties $L_{\Delta t}$. Command demand $D_{\text{cmd}}$ reflects order opportunities $O_{\Delta t}$ with $\kappa = 0.5$. Because external aid expands force size, mobility, patrols, and engagements, service demand is an endogenous system outcome.

Whole-force capability is measured separately via composite retention. Let $g$, $p$, $f$, $c$, and $r$ denote government control, personnel retention, formation survival, geographic coverage, and operational readiness, each bounded to $[0,1]$ relative to the pre-split baseline. The primary composite is

$$
C = (gpfcr)^{1/5}.
$$

Reported capability differences reflect changes on this unit-scale geometric index rather than percentage changes in combat effectiveness.

Developmental assistance augments partner productive capacity ($I_j$) on a weekly schedule; direct substitution supplies removable external service ($E_j$). At simulated day 120, each world branches into continued-support (`SUPPORT_ON`) and withdrawal (`SUPPORT_OFF`) arms. The withdrawal branch removes foreign assistance while preserving accumulated indigenous capacity, stocks, and random seeds. Outcomes are recorded at +7, +30, +90, +180, and +360 days.

## 4.3 Integrated Stage-4 design

Stage 4 comprises 234 cells and 2,808 production worlds (12 seeds per cell).

**Table 1. Integrated Stage-4 experimental design.** Each production world executes one frozen seed in a prospectively frozen cell, separating branch divergence, bottleneck migration, and assistance architecture.

| Module | Cells | Seeds per cell | Worlds | Purpose |
|---|---:|---:|---:|---|
| Phase Map | 140 | 12 | 1,680 | Vary starting structure, indigenous capacity, and direct support intensity |
| Bottleneck Migration | 52 | 12 | 624 | Target observed and nominal constraints and track persistent migration |
| Substitution vs Development | 42 | 12 | 504 | Compare no aid, direct substitution, indigenous development, and hybrid assistance |
| **Total** | **234** | **12** | **2,808** | Integrated test of phenomenon, dynamics, and mechanism |

The Phase Map crosses four starting structural families with five capacity levels and seven support intensities (0 to 2.0). The Migration module evaluates force-generation, logistics, command, balanced, and no-support packages across three intensities, identifying targets by observed pre-withdrawal bottlenecks. The Mechanism module contrasts direct substitution, indigenous development, and hybrid assistance across moderate and severe weakness.

## 4.4 Estimands and uncertainty

The preregistered Stage-4 estimands evaluate early composite capability branch divergence ($C_{30}^{ON} - C_{30}^{OFF}$) and terminal indigenous coverage divergence ($q_{360}^{I,ON} - q_{360}^{I,OFF}$). Post-review analyses add two diagnostics on frozen telemetry: matching treated worlds to zero-support controls ($S_h$, $R_h$, $G_h$), and decomposing terminal coverage into demand and indigenous service components. For logistics-bound terminal worlds, descriptive standardizations evaluate supported production under withdrawal demand and vice versa.

Analyses report cell means, medians, 10th-90th percentiles, and directional fractions. Bootstrap intervals serve as descriptive sampling dispersion metrics rather than population hypothesis tests.

## 4.5 Reproducibility and production integrity

Simulation code, parameters, and analysis contracts were locked under cryptographic freeze prior to execution. An independent audit confirmed complete task coverage, row counts, and checksum hashes across all 2,808 worlds with zero missing or duplicate records. Full provenance and replication instructions are detailed in Appendix A.

## 4.6 Proposition-to-test correspondence

The research design maps distinct tests to theoretical propositions. The Phase Map establishes branch divergence and supplies telemetry for supply-demand decomposition. A separately frozen demand-clamp experiment tests Proposition 1 by dynamically constraining supported logistics demand to match withdrawal requirements. Control-matched contrasts evaluate Proposition 2 ($S_h$, $R_h$, $G_h$). The Migration module tests Proposition 3, establishing whether relieving a bottleneck displaces the limiting constraint and how displacement affects system yield. The Mechanism module evaluates the capability-retention-cost frontier under alternative assistance modes.

## 4.7 Prospectively frozen coordinated-development extension

Stage 5 evaluates whether developing multiple complementary capacities simultaneously expands whole-force output more effectively than single-channel interventions. The campaign comprises 92 cells and 16 matched seeds per cell (1,472 worlds), testing all combinations of force-generation, logistics, and command development across four starting structures under two dose allocations:

1. **Equal total effort:** Divides a fixed developmental investment across active channels to test allocation breadth efficiency.
2. **Equal channel dose:** Provides the full single-channel dose to each active service, enabling direct estimation of factorial interactions ($I_{AB} = Q_{AB} - Q_A - Q_B + Q_0$).

All arms undergo 120 days of development before donor support ceases. Pre-registered endpoints measure retained feasibility ($Q$) at +360 days.

A manipulation check reveals that nominal design structures do not uniformly persist as active bottlenecks at split: logistics binds at day 120 in all 368 nominal force-generation worlds, all 368 logistics worlds, and 365 of 368 near-tie worlds, while command binds in 100 of 368 command-constrained worlds. Nominal structures are therefore reported as design factors rather than verified bottleneck states, qualifying the scope condition for multi-constraint near-ties.

# 5. Results

Throughout this section, cell-level classifications aggregate across simulation seeds to characterize experimental factor combinations ($n = 120$ treated cells; 20 zero-support control cells), whereas world-level statistics describe individual seed runs (up to $n = 1,440$ treated seed runs in the Phase Map, or 1,680 across all 140 cells) to preserve full distributional variation.

## 5.1 Supported effect, retained effect, and dependency gap are different quantities

The original frozen Stage-4 analysis compared continued support with withdrawal
after both branches had already experienced 120 days of support. Under that
branch contrast, 106 of 120 treated cells had a positive mean +30-day capability
gap and 96 of those 106 had lower +360-day indigenous coverage under continued
support. That result remains correct for its frozen branch estimand. It does not,
however, establish that continued support improved capability relative to no
aid.

The post-review control-matched analysis uses the 20 zero-support cells to make
that distinction explicit. At +30 days, the 120 treated cells divide as follows:

| Supported effect vs no aid | Retained effect after withdrawal vs no aid | Cells |
|---|---|---:|
| Positive | Negative | 26 |
| Positive | Positive | 30 |
| Negative | Negative | 51 |
| Negative | Positive | 1 |
| At least one effect within the epsilon-neutral band |  | 12 |

The strong success-without-retention pattern therefore appears in 26 of 120
treated cells at +30 days, not in 96 of 106 cells. The latter count describes a
different quantity: whether continued support outperforms withdrawal after a
common supported prehistory.

The 51 cells in which assistance fails to outperform no aid in either branch (42.5 percent of treated cells) represent a major empirical category that differs sharply from the 26-cell success-without-retention bucket. Examining cell-level covariates reveals that the both-negative outcome is heavily concentrated in command-constrained forces and low-to-moderate assistance intensities. Fully 21 of the 30 command-constrained cells (70.0 percent) fall into this both-negative bucket, comprising 41.2 percent of all 51 cells. When command capacity is severely limited, external material or logistics provision cannot be coordinated effectively across operational formations, leaving the force more vulnerable to attrition and fragmentation than in the unassisted counterfactual. Furthermore, 24 of the 51 both-negative cells (47.1 percent) occur at low or moderate support intensities (0.25 and 0.50), where external service is insufficient to overcome baseline operational drag. By sharp contrast, the 26 "suffering from success" cells are heavily concentrated at high support intensities: 18 of the 26 cells (69.2 percent) occur at intensities 1.5 and 2.0. True success-without-retention in the model is thus a high-dose phenomenon, where massive external substitution temporarily elevates operational capability while building a heavy logistics footprint that collapses once support ends.

A single cell (`phase_094`: command-constrained, capacity level 0.55, support intensity 0.5) exhibits a nominally negative supported effect (-0.00054) and a positive retained effect (+0.00263). This result does not reflect a substantive dynamic where withdrawal improved the force. Both effects lie within a fraction of a percentage point of zero, and seed-level supported effects range widely from -0.067 to +0.052 across its 12 seeds. The cell is functionally neutral and falls into the upper-left quadrant solely due to minute seed-level sampling jitter around the origin.

The mean decomposition reinforces the distinction. Across all treated worlds at
+30 days, continued support is only +0.00036 above the matched no-aid trajectory
on the unit-scale composite-capability index, while the withdrawal branch is
-0.02378 below no aid. Their mean dependency gap is +0.02414. At +360 days, the
corresponding means are -0.00326, -0.02443, and +0.02118. Thus a positive
continued-support-minus-withdrawal contrast can coexist with little or no net
supported advantage over no aid because part of the gap reflects deterioration
after withdrawal.

This result changes the interpretation of the Phase Map. It identifies a set of
genuine success-without-retention cases, a set in which both supported and
retained capability improve, and a large set in which neither branch beats the
matched no-aid benchmark. The paper therefore treats the three quantities
separately rather than calling every positive branch gap a successful program.

![Figure 2. Supported capability relative to matched no aid versus retained
capability after withdrawal relative to matched no aid at +30 days. Each point
is a treated Phase-Map cell. Marker shape identifies the nominal starting
structure and marker size increases with support intensity.](figures/figure2_supported_retained.png)

## 5.2 The terminal coverage gap is produced by both indigenous service and demand

The endogenous denominator of the coverage ratio is substantively important.
Among 1,189 treated Phase-Map worlds with a negative +360-day indigenous-
coverage branch contrast, 1,174 end with the same binding service in both
branches, almost entirely logistics. Within those same-terminal worlds, 95.9
percent have higher logistics demand under continued support, whereas 19.8
percent have lower indigenous logistics delivery. Both lower indigenous service
and higher demand occur in 15.8 percent.

For worlds with positive quantities, the exact decomposition



$$
\Delta\ln q = \Delta\ln I-\Delta\ln D
$$



gives a mean indigenous-service term of -0.0733 and a mean demand term of
+0.0820, producing a mean log coverage gap of approximately -0.1553. In other
words, requirement expansion contributes slightly more than indigenous-service
decline to the average log gap in this subset.

A second descriptive standardization puts the two components back onto the
capped coverage scale. Among the 823 worlds that both improve composite
capability at +30 days relative to withdrawal and have lower terminal logistics
coverage, the observed mean coverage contrast is -0.0823. Evaluating the
continued-support indigenous service against withdrawal-branch demand leaves a
mean production-only contrast of -0.0301. Holding indigenous service at the
withdrawal level while imposing the continued-support requirement produces a
mean demand-only contrast of -0.0534. Because the capped ratio is nonlinear,
these terms are not perfectly additive, but the comparison shows that most of
the average gap in this subset is associated with the larger operating
requirement rather than with lower indigenous service alone.

These calculations are post-completion diagnostics, not the direct mechanism
experiment. A separately frozen demand-clamp ablation reported below intervenes
on the simulated requirement itself.

![Figure 3. Requirement-expansion evidence. Panel A decomposes the terminal
logistics-coverage gap in worlds with positive +30-day branch capability and
negative +360-day coverage. Panel B reports the separately frozen prospective
demand-clamp test and its effect on +30-day composite capability.](figures/figure3_requirement_expansion.png)

## 5.3 The prospective demand clamp does not identify the retention mechanism

The post-review ablation directly intervenes on the demand side of the proposed
requirement-expansion mechanism. Four Phase-Map cells were selected before the
new outcomes were observed. On their original Stage-4 seeds, their mean +360-day
coverage branch effects were approximately -0.106, -0.105, -0.106, and -0.134.[^clampcells]
The ablation reruns those exact cell parameters under a fresh seed namespace,
with paired normal and demand-clamped arms across 48 matched seeds. The experiment
executed under git commit `a24b4811`, which introduced the bisection demand-matching
search loop to the runner while inheriting the identical core simulation rules,
parameters, and agent behaviors from Stage 4.

The manipulation itself succeeds. Across 2,640 post-split telemetry intervals,
the median relative mismatch between clamped supported-branch logistics demand
and the paired withdrawal requirement is 0.46 percent, the 95th percentile is
1.30 percent, the maximum is 2.05 percent, and every interval lies within the
precommitted 5 percent tolerance.

The primary coverage estimand, however, yielded an uninformative zero result across all worlds. In all 48
fresh-seed normal worlds, the capped indigenous-coverage branch gap is exactly
zero at +7, +30, +90, +180, and +360 days. The demand-clamped worlds are also
zero at every registered horizon. There is therefore no normal-arm coverage branch
difference for the clamp to attenuate. The precommitted +360-day attenuation
estimate is exactly zero, but that value cannot be interpreted as evidence that
requirement expansion is causally irrelevant to the Stage-4 penalty.

A structural inspection of the ablation runner clarifies why this exact zero occurs.
In the primary output shards, the summary field `formal_q_indigenous` recorded the
pre-split baseline structural coordinate evaluated at withdrawal day 120. Because both
`SUPPORT_ON` and `SUPPORT_OFF` branches share the identical 120-day prehistory, their
pre-split structural coordinates are identical by construction, producing an exact zero
branch difference across all 48 seeds and all five horizons. In contrast, dynamic
post-split service flows and capability assays were updated continuously at each horizon.
On the capability side, the fresh-seed normal arms retain positive mean +30-day
composite-capability branch effects in all four scenarios, approximately +0.226,
+0.083, +0.008, and +0.013. Clamping logistics demand materially changes that
capability effect, reducing the pooled branch contrast by about 0.093 at +30
days, 0.212 at +90, 0.213 at +180, and 0.147 at +360.

This diagnostic scrutiny also addresses the baseline stability of the four selected cells.
In the original Stage-4 production runs, each cell's 12 seeds exhibited consistent
negative coverage penalties rather than hovering ambiguously around zero: M1 had 12 of 12
seeds negative (range -0.132 to -0.094); M2 had 12 of 12 negative (range -0.114 to -0.097);
M3 had 11 of 12 negative (range -0.443 to 0.000); and M4 had 10 of 12 negative (range -0.484
to +0.195). Thus, the Stage-4 penalties were not boundary artifacts of a single noisy seed.
Nevertheless, because the prospective ablation harness did not evaluate dynamic post-split
coverage ratios in its primary estimand, it does not identify requirement expansion as the
mediator of the Stage-4 retention pattern. Requirement expansion remains a plausible,
descriptively supported hypothesis whose causal validation requires a unified harness
tracking dynamic post-withdrawal coverage ratios under fresh seed ensembles.

[^clampcells]: The near-identical baseline coverage effects for M1 (-0.1056), M2 (-0.1050), and M3 (-0.1061) are not duplicate reporting artifacts. They represent three distinct Phase-Map cells with different nominal starting structures (`logistics_constrained`, `balanced_capacity`, and `forcegen_constrained`) and capacity levels (0.40, 0.40, and 0.25) whose independently simulated 12-seed Stage-4 coverage penalties clustered around the -0.105 to -0.106 band.

## 5.4 Supported capability advantages evolve over time

The +30-day horizon also understates the temporal structure of the branch gap.
Among the 1,064 Phase-Map worlds with a positive continued-support-minus-
withdrawal capability contrast at +30 days, the mean gap is +0.0106 at day 7,
+0.0335 at day 30, +0.0395 at day 90, +0.0340 at day 180, and +0.0298 at day
360. The fraction of those worlds with a positive branch gap declines from 100
percent at day 30 to 63.1 percent at one year.

That trajectory is evidence that continued support can maintain capability
relative to withdrawal for extended periods. It should not be confused with a
net treatment effect over no aid. Across all treated cells, mean supported
capability relative to the matched no-aid control is +0.00782 at day 7,
+0.00036 at day 30, -0.01005 at day 90, -0.00768 at day 180, and -0.00326 at
day 360. The synthetic experiment therefore contains strong positive cases,
neutral cases, and harmful cases rather than one uniformly successful support
regime.

![Figure 4. Mean supported effect relative to no aid, retained effect after
withdrawal relative to no aid, and the dependency gap across all treated
Phase-Map cells at each registered horizon. Shaded bands show the interquartile
range across cells.](figures/figure4_capability_trajectories.png)

## 5.5 Nominal weakness is a poor proxy for the observed bottleneck

The Phase Map also shows why static labels are inadequate. As nominal
force-generation capacity rises, the observed bottleneck frequently shifts to
logistics before treatment. At the 0.60 force-generation multiplier, all 84
sampled worlds across support conditions were already logistics-bottlenecked.
Balanced systems likewise became increasingly logistics-bound as overall
capacity increased, reaching 84 of 84 logistics bottlenecks at balanced
capacity 1.0.

Command-constrained systems remained command-bound over lower capacity levels,
but at command capacity 0.70, 61 of 84 worlds were logistics-bottlenecked and
only 23 remained command-bottlenecked. These patterns establish an important
measurement point: the target named in an assistance program or experimental
design need not be the service that actually limits the system.

## 5.6 Constraint displacement explains low yield, not the terminal coverage penalty

The dedicated Migration module shows that bottleneck displacement is real, but
it does not mediate the terminal coverage penalty. Among worlds where the
treatment target matched the observed pre-withdrawal bottleneck, command and
force generation behave very differently from logistics.

When command assistance matched an observed command bottleneck, all 38 worlds
experienced persistent migration; median detected migration time was seven days,
and logistics was the modal post-support bottleneck in all 38. When force-
generation assistance matched an observed force-generation bottleneck, all 46
worlds migrated persistently; median detected migration time was again seven
days, and logistics was the modal post-support bottleneck in all 46.

Matched logistics cases produced the opposite result: none of 85 worlds migrated
persistently. Continued logistics support improved +30-day
capability on average by approximately +0.0170, while the terminal indigenous-
coverage branch contrast was approximately -0.2215.

The key finding is the separation between migration and the coverage gap.
Matched command relief migrates in 38 of 38 worlds and has a mean +360-day
coverage effect of +0.0555. Matched force-generation relief migrates in 46 of 46
worlds and has a mean terminal effect of zero at reported precision. Matched
logistics relief migrates in 0 of 85 worlds and has the large negative terminal
effect, -0.2215. The full Phase Map shows the same direction: among worlds with
a positive +30-day branch capability effect, migrated worlds have a less
negative mean terminal coverage contrast than non-migrated worlds.

Migration therefore cannot be the cause of the coverage penalty in these
experiments. What it does identify is **relief without yield**. Matched force-
generation assistance changes which service binds in all 46 worlds while its
mean +30-day composite-capability effect is approximately +0.00000021. Command
relief also migrates universally but yields only +0.00354 on average. Logistics
support produces the largest +30-day branch gain, about +0.01699, despite no
persistent migration.

**Table 2. Relief, migration, system yield, and terminal indigenous coverage in observed-matched Migration worlds.** The weighted means are a post-completion descriptive synthesis of frozen cell summaries. They were not themselves a prospectively frozen primary estimand.

| Observed-matched target | Persistent migration | Mean +30d capability effect | Mean +360d indigenous-coverage effect |
|---|---:|---:|---:|
| Command | 38/38 | +0.00354 | +0.0555 |
| Force generation | 46/46 | +0.00000021 | 0.0000 |
| Logistics | 0/85 | +0.01699 | -0.2215 |

The result supports a narrower role for constraint displacement than the
original manuscript proposed. Moving from one bottleneck to another shows that
the targeted constraint was structurally displaced. It does not explain the
supported-retained gap. Relief, yield, constraint identity, and retention must
therefore be reported separately.

## 5.7 Substitution and development lie on a capability-retention-cost frontier

The Substitution versus Development module should not be read as a cost-equated
horse race. Development is modeled as partner-owned capacity growth, whereas
substitution provides removable external service, and the donor-cost schedules
are different. The useful comparison is therefore a frontier among early
capability, terminal indigenous coverage, local production, and modeled cost.

For moderate logistics weakness at intensity 0.5, development improves terminal
indigenous coverage relative to substitution by approximately +0.1316, with a 95 percent
bootstrap interval of +0.1245 to +0.1398. At moderate weakness and intensity
1.0, the contrast is approximately +0.1853 [0.1236, 0.2398]. At severe weakness
and intensity 0.5, it is approximately +0.2542 [0.2388, 0.2687]. At severe
weakness and intensity 1.0, it reaches approximately +0.4328 [0.4169, 0.4516].

Across logistics-targeted cells, development has a less negative mean terminal
coverage effect than substitution and increases indigenous logistics service
substantially, but it is also slightly more expensive on the model's donor-cost
ledger and does not dominate on early capability in every condition. Averaged
over the logistics-targeted cells, the mean +30-day capability effects are
approximately +0.038 for development, +0.070 for hybrid assistance, and +0.047
for substitution. The corresponding mean +360-day coverage effects are -0.033,
-0.129, and -0.284, while modeled cumulative donor costs are approximately 3.32,
3.28, and 3.24 million units.

The indigenous-production mechanism is also visible directly. Relative to
substitution, developmental logistics generates approximately +172,859 to
+1,249,115 additional units of indigenous cumulative logistics service across
the tested conditions. Capped indigenous coverage of cumulative logistics
demand improves by approximately +0.114 to +0.411.

Development is therefore not simply another route to the same supported
capability, but neither is it a free improvement. It changes who produces the
service and moves the modeled capability-retention-cost frontier.

![Figure 5. Logistics-targeted assistance on the capability-retention-cost
frontier. Horizontal position is the mean +30-day capability branch effect,
vertical position is the mean +360-day indigenous-coverage branch effect, and
marker area scales with modeled cumulative donor cost.](figures/figure5_assistance_frontier.png)

## 5.8 Local development does not guarantee system yield

Force generation provides a clean test of Proposition 5. Developmental
force-generation assistance produces large indigenous gains relative to direct
substitution. The matched development-minus-substitution contrasts in cumulative
indigenous force-generation output range from approximately +121 to +674 across
the four severity and intensity conditions, with narrow bootstrap intervals.

Yet the corresponding whole-system terminal-coverage contrast is exactly zero
in all four cells. By +360 days, every force-generation-targeted world in the
mechanism experiment is logistics-bottlenecked. The intervention succeeds in
the subsystem it targets, but the targeted subsystem no longer limits the
system.

Command development generates the same logic in a less uniform form. It raises
indigenous command service and coverage, but command-development worlds migrate
away from command as the binding constraint, overwhelmingly toward logistics.
In the moderate-weakness, high-intensity condition, development produces a
terminal system-coverage contrast of approximately -0.132 relative to
substitution, with a bootstrap interval of about -0.231 to -0.046, despite
improving the indigenous command subsystem.

The result should not be read as evidence that command development is generally
harmful. It shows that improving a nonbinding or transient capacity can have a
low system return. Once another service binds, further improvements in the
relieved subsystem cannot raise whole-system feasibility by themselves.

## 5.9 Integrated evidence: separate outcomes and uneven mechanism evidence

The revised evidence no longer supports a single migration-mediated retention
mechanism, and it does not support equally strong claims about the two candidate
production dynamics. Constraint displacement is directly demonstrated and helps
explain why successful local relief can produce little whole-system yield.
Requirement expansion is descriptively consistent with the Stage-4 supply-demand
decomposition, but the prospective clamp test evaluated a static pre-split baseline coordinate rather than dynamic coverage flows and therefore does not identify requirement expansion as its cause.

**Table 3. Headline evidence after separating outcomes from mechanism claims.** The matched-control and supply-demand decompositions were added after external review and are labeled post-completion diagnostics. The demand-clamp rows come from a separately frozen post-review experiment and show a successful demand manipulation alongside an uninformative coverage test: the ablation runner recorded the pre-split baseline coordinate evaluated at withdrawal day 120, structurally guaranteeing a zero branch difference, while dynamic capability effects diverged significantly.

| Result | Estimate | Status |
|---|---:|---|
| +30d cells with supported capability above no aid and retained capability below no aid | 26/120 | Post-completion matched-control diagnostic |
| +30d cells with both supported and retained capability above no aid | 30/120 | Post-completion matched-control diagnostic |
| Same-terminal coverage-penalty worlds with higher continued-support logistics demand | 95.9% of 1,174 | Post-completion telemetry decomposition |
| Mean standardized coverage effect in +30d-effective logistics-penalty worlds | observed -0.0823; production-only -0.0301; demand-only -0.0534 | Post-completion diagnostic |
| Fresh-seed normal worlds with nonzero coverage branch gap in static-field ablation test | 0/48 at every registered horizon | Post-review ablation harness artifact (evaluated static pre-split baseline coordinate) |
| Demand-clamp manipulation intervals within 5% of paired withdrawal demand | 2,640/2,640 | Post-review prospectively frozen manipulation check |
| Observed-matched command migration | 38/38 | Frozen Stage-4 Migration module |
| Observed-matched force-generation migration | 46/46 | Frozen Stage-4 Migration module |
| Observed-matched logistics migration | 0/85 | Frozen Stage-4 Migration module |
| Force-generation development minus substitution on terminal system coverage | 0 in all four cells | Frozen Stage-4 mechanism module |

The constraint-displacement result is also highly insensitive to replacing the hard
minimum coverage coordinate with smooth service aggregators in the Migration
module. Across the 169 worlds in which the assistance target matched the
observed pre-withdrawal bottleneck, the sign of the +360-day coverage effect
agrees between the hard-minimum measure and each of the arithmetic, geometric,
and harmonic smooth measures in 167 worlds, or 98.8 percent. The two discordant
worlds are one command-targeted world and one logistics-targeted world.

**Table 4. Sign robustness of terminal-coverage effects to smooth feasibility aggregation in observed-matched Migration worlds.** This check is specific to the Migration evidence package and should not be read as a robustness result for every Phase-Map or mechanism-module estimand.

| Observed-matched target | Worlds | Hard minimum vs arithmetic | Hard minimum vs geometric | Hard minimum vs harmonic |
|---|---:|---:|---:|---:|
| Command | 38 | 37/38, 97.4% | 37/38, 97.4% | 37/38, 97.4% |
| Force generation | 46 | 46/46, 100% | 46/46, 100% | 46/46, 100% |
| Logistics | 85 | 84/85, 98.8% | 84/85, 98.8% | 84/85, 98.8% |
| **Total** | **169** | **167/169, 98.8%** | **167/169, 98.8%** | **167/169, 98.8%** |

## 5.10 Stage 5 identifies selective complementarity but does not validate the intended near-tie allocation test

Stage 5 separates equal-channel-dose technical complementarity from fixed-budget
allocation efficiency. Its intended scope-condition manipulation fails: 365 of
368 nominal near-tie worlds are logistics-bound by the split, so most fixed-
effort comparisons occur in realized single-bottleneck regimes. In those
regimes, none of 32 breadth comparisons has an interval entirely above zero and
21 have intervals entirely below zero. This shows that spreading a fixed dose
can be costly when one service already dominates, not that breadth would fail
under a genuine near-tie.

Equal-channel-dose results show narrower complementarity. Two high-intensity
pairwise interactions in the nominal near-tie design are positive, about +0.025
for force generation plus logistics and +0.172 for logistics plus command, while
the corresponding three-way interaction is negative (-0.056). However, this pattern
must be interpreted with caution. In any bounded $[0, 1]$ metric, two strong positive
pairwise interventions can push system feasibility close to its theoretical upper bound.
When an outcome approaches saturation, the incremental gain available to a three-way
combination is mechanically capped, producing a negative three-way interaction as a generic
mathematical signature of compressive ceiling effects rather than genuine destructive
interference among the three investments. Combined with multiplicity and the failed
near-tie manipulation, this ceiling confound means that the conditional allocation question
for a verified multi-constraint near-tie remains open.

## 5.11 Supplemental robustness

Alternative service aggregators, the adversarial structural sidecar, complete Stage-5 contrasts, and distributional diagnostics are reported in the supplementary appendix. The sidecar establishes only that all three service channels can be terminal under adversarial structures; it is not treated as a global sensitivity analysis.

# 6. Discussion

## 6.1 Separate outcomes, uneven mechanism identification

The revised evidence changes the causal interpretation of the paper. The original manuscript treated constraint migration as the mechanism linking successful relief to lower indigenous coverage. The data do not support that claim. Migration is common when command or force generation is targeted, but the strongest terminal coverage penalties occur where logistics remains binding. In the Phase Map, migrated worlds with a positive early branch capability gap have a less negative mean terminal coverage contrast than non-migrated worlds. Constraint displacement is therefore not the mediator of the retention penalty.

What survives is more useful because it is more specific. The framework identifies two separate production problems, but the experiments identify them with different strength. Requirement expansion concerns the scale of service demand relative to indigenous production. The Stage-4 telemetry is consistent with that process, but the prospective demand-clamp test evaluated a static pre-split baseline coordinate rather than dynamic post-split coverage flows, preventing it from testing mediation. Constraint displacement concerns the marginal value of improving one complementary service after another becomes limiting and is directly observed in the Migration module. It can produce relief without material whole-force yield and without any negative retention effect.

This distinction connects security-assistance research to established theories without claiming novelty for generic bottleneck logic or donor dependence. Operations management already expects changing constraints [@watson2007]. Development economics already treats expansion as a source of new complementary requirements [@hirschman1958]. Aid research already recognizes recurrent-cost and absorptive-capacity problems [@roodman2006; @arimotokono2009]. The contribution is a military-production formulation that places supported capability, retained capability, service demand, indigenous production, and changing constraints in the same analytic framework, while making explicit what evidence would actually identify each proposed mechanism.

## 6.2 Why the no-aid benchmark matters

The distinction between a dependency gap and a net treatment effect is substantively important. If continued support outperforms withdrawal after 120 days of prior support, the donor is supplying something the withdrawal branch no longer has. That difference may represent valuable ongoing support. It may also reflect deterioration caused by the removal of an externally supported operating system. Without a matched no-aid benchmark, those possibilities cannot be separated.

The Phase Map demonstrates the point. The original frozen branch contrast classified 106 treated cells as having a positive mean +30-day continued-support advantage over withdrawal. The stricter no-aid comparison finds only 26 cells in which supported capability is above no aid while post-withdrawal capability is below no aid. Thirty cells are above no aid in both branches. Fifty-one are below no aid in both. A useful evaluation framework must therefore report at least three quantities: the supported effect relative to no aid, the retained effect relative to no aid, and the gap between continued support and withdrawal.

This also clarifies the meaning of the phrase **Suffering from Success**. It is not a description of every assistance program in the model. It denotes a conditional regime in which support produces a real capability gain but the supported system is not reproduced after withdrawal. The regime is analytically important precisely because it can be distinguished from simple program failure.

## 6.3 Requirement expansion remains a candidate retention mechanism

The post-completion telemetry analysis shows why the indigenous-coverage coordinate must be decomposed. In same-terminal logistics worlds with a negative coverage contrast, the continued-support branch usually faces higher logistics demand, while a smaller share also has lower indigenous delivery. On the log scale, both components matter, and requirement growth contributes slightly more to the average gap than indigenous-service decline. The standardized capped-coverage calculation points in the same direction. These are descriptive decompositions of realized Stage-4 trajectories, not causal mediation estimates.

The prospective demand-clamp experiment was intended to provide the stronger test and does not do so. Its manipulation check passes, and clamping logistics demand materially changes composite capability, especially in the M1 and M2 scenarios. However, the ablation runner evaluated the static pre-split baseline coordinate (`formal_q_indigenous` at withdrawal day 120) rather than dynamic post-split coverage flows. Because both branches share an identical 120-day prehistory, their pre-split structural coordinates were identical by construction, structurally guaranteeing a zero branch gap across all 48 seeds and all five horizons. The zero attenuation estimate is thus an artifact of the static metric rather than evidence that requirement expansion is irrelevant or that fresh seeds failed to reproduce retention dynamics. The direct experiment therefore leaves requirement expansion unconfirmed as a causally identified retention mechanism.

That result does not imply that demand should be held fixed in substantive policy. A larger requirement can be the consequence of more activity, more surviving formations, more territory, or other real operational gains. The point is diagnostic. A falling service-to-demand ratio is not equivalent to destroyed indigenous capacity. It can instead mean that the force has grown into a larger sustainment problem. The policy question then becomes whether indigenous production can catch up with the supported operating requirement, not merely whether the ratio fell.

This is why the paper reports absolute capability alongside coverage and why the final interpretation does not equate a decomposed association with mechanism identification. A donor can improve supported capability, leave indigenous service unchanged or higher, and still create a larger post-support shortfall if the new operating system requires more service than the partner can produce alone. The Stage-4 telemetry contains that pattern, but confirming it causally requires a unified harness tracking dynamic post-withdrawal coverage ratios. Conversely, a coverage decline with no supported capability gain is not a success-induced retention problem. It is simply a poor outcome.

## 6.4 Constraint displacement is mainly a yield problem

The Migration module gives bottleneck logic a different role. Command and force-generation constraints are easy to displace in the tested parameter region. Force-generation relief is the cleanest example: 46 of 46 observed-matched worlds migrate, yet the average +30-day composite-capability effect is essentially zero. The system changes, but the force barely improves because another service is already limiting.

This is the practical value of tracking constraint identity. Assistance can report a successful local output, such as more trained personnel or better command performance, while whole-force output remains flat. A program manager looking only at the treated subsystem would record progress. A system-level evaluation would ask whether the intervention changed the limiting service and whether any capability gain followed.

Static headroom is only a partial diagnostic for this problem. The post-completion reconstruction does not show a monotonic relationship between initial coverage spacing and realized yield. Once operations, losses, movement, stocks, and service demand respond endogenously, the initial distance between the first and second constraints is not a sufficient predictor. For applied use, direct measurement of the current constraint and the realized system response is more defensible than a simple headroom rule.

## 6.5 Assistance modes lie on a frontier

The substitution-versus-development results also become clearer under the revised framework. Developmental logistics assistance produces more indigenous service and much better terminal coverage than substitution, but it is not uniformly superior on early capability and it carries a somewhat higher modeled donor cost. The relevant comparison is therefore not "development good, substitution bad." It is a frontier among immediate supported performance, retained capability, indigenous service production, cost, and time.

This matters because real assistance programs face different objectives. A donor trying to prevent an immediate battlefield collapse may rationally value rapid substitution. A donor trying to reduce long-run external dependence should care more about partner-owned production. The model cannot assign the political value of those objectives. It can make the tradeoff visible and prevent one outcome from being mislabeled as another.

The force-generation result adds a systems warning. Development can succeed locally and still have zero whole-system return when a different service binds. Capacity building should therefore be evaluated both at the targeted subsystem and at the force level.

## 6.6 Coordinated development remains an open allocation problem

Stage 5 does not provide the clean near-tie test originally intended because its nominal near-tie worlds become logistics-bound before the main comparison. The fixed-effort results are still informative about the realized single-bottleneck regimes: spreading a fixed dose across several services rarely beats concentrating it in the best included channel. But that result should not be generalized to genuinely co-binding systems.

The equal-dose factorial results offer narrower evidence that technical complementarities can exist. A small number of pairwise interactions are positive, including one materially large logistics-command interaction. Those interactions do not imply that broad allocation is efficient under a fixed budget, and multiplicity and ceiling effects limit strong claims. A future experiment should create and verify true near-ties at the treatment split before testing whether breadth becomes advantageous as the number of binding constraints increases.

## 6.7 What a security-assistance evaluation should measure

The results suggest a practical diagnostic sequence rather than a universal prescription:

1. Identify the service actually limiting whole-force performance, not only the service named in the program design.
2. Measure the local treatment effect on that service.
3. Measure the whole-force capability effect relative to a credible no-aid benchmark where possible.
4. Track how the intervention changes service requirements as well as indigenous production.
5. After support changes, measure retained capability relative to the same benchmark.
6. Record whether another service becomes limiting and whether that displacement materially changes system yield.
7. Compare assistance architectures on capability, retention, time, and cost rather than one metric alone.

This framework is compatible with political explanations rather than a substitute for them. Recipient incentives determine whether capacity investments are adopted and maintained. Patronage, corruption, command politics, coalition dynamics, and donor leverage shape both indigenous production and the operating requirement. The production model isolates one set of mechanisms conditional on those political processes. It should be combined with, not used to displace, agency and institutional analysis.

# 7. External Validity and Historical Validation

The synthetic experiments are designed to establish internal causal logic under
explicit model assumptions. External validity requires a different evidentiary
strategy. Historical validation should therefore test observable implications
of the mechanism rather than search for cases that merely resemble the model.

The historical unit of analysis is an **assistance episode by military-service
constraint by time**. For each episode, the protocol asks whether seven
observable implications can be identified: the initial limiting service, the
assistance directed at it, improvement in the targeted function, expansion or
change in the operating requirement, migration or persistence of the limiting
constraint, the degree of indigenous replacement, and the response to a support
reduction or withdrawal shock. The purpose is process validation. Historical
evidence can show that the proposed sequence exists outside the model and can
identify important scope conditions. It cannot convert the synthetic treatment
effects into empirical causal estimates.

The protocol froze four cases before systematic coding:
Afghanistan, Iraq, Mali, and Colombia. They are selected for theoretical
variation rather than because all four are expected to support the argument.

| Case | Intended evidentiary role | Main question for the theory |
|---|---|---|
| Afghanistan | High-support, high-substitution episode with a major withdrawal shock | Can supported sophistication outrun indigenous replacement even when the externally supplied function remains the core constraint? |
| Iraq | Force-generation and institutional expansion under heavy external assistance | Does improvement in force generation reveal sustainment or logistics as a subsequent system constraint? |
| Mali | Politically fragmented, multi-provider and difficult case | Does the production mechanism survive where political fragmentation and provider diversity complicate a clean constraint sequence? |
| Colombia | Comparatively durable long-run development case | Can indigenous institutions and sustainment grow fast enough for capability gains to become retained rather than externally reproduced? |

Source-audited coding under that frozen protocol produces meaningful
variation. Afghanistan provides strong evidence of persistent external
substitution in aviation maintenance and logistics rather than a clean migration
away from the original constraint. SIGAR found that the Afghan Air Force
remained heavily dependent on contractor maintenance and that the broader ANDSF
had failed to become independent and self-sustaining before the 2021 withdrawal
shock [@sigar2021air; @sigar2023collapse]. Iraq provides a clearer sequential
case. By late 2006, DOD reported hundreds of thousands of trained and equipped
Iraqi personnel, while GAO identified logistics and sustainment as a serious
shortcoming and documented lagging national and regional support institutions
[@gao2007iraqlog; @gao2007iraqcc; @gao2007iraqindependent]. A later Department
of Defense Inspector General lessons-learned review likewise emphasized the need
to develop logistics and sustainment concurrently with operational forces rather
than treating support capacity as a downstream problem [@dodig2015].

Mali is a harder and less supportive case. RAND's field research found that
EUTM-trained GTIAs improved basic soldier skills, but logistics, maintenance,
command, and coordinated operations remained major limits [@shurkin2017]. Marsh
and Rolandsen further show how multiple, weakly coordinated assistance providers
can fragment recipient-force cohesion, supplying a political-organizational
rival to a production-constraint explanation [@marshrolandsen2021]. Those
weaknesses were already present during the assistance effort, so the evidence is
better interpreted as local-system divergence than as a clean case in which
assistance caused a new bottleneck to emerge. Colombia provides the strongest
positive retention case. U.S. assistance initially supplied contractor pilots,
mechanics, maintenance, logistics, and training to an aviation system that
Colombia could not yet sustain independently. Over a long phased transition,
Colombian personnel and institutions assumed progressively more responsibility;
GAO later reported that Colombia had taken over full maintenance and operations
for the Army aviation program, while also noting slower nationalization in a
related helicopter training center [@gao2009colombia; @gao2013colombia;
@gao2018colombia].

**Table 5. Source-audited historical process evidence under the frozen external-validation protocol.** The table is a structured plausibility and process test, not a causal estimate of security-assistance effects. The source audit preserves mixed and adverse evidence rather than upgrading ambiguous cases to full support.

| Case | Audited constraint sequence | Indigenous replacement | Support-change evidence | Strongest rival explanation | Audited theory fit |
|---|---|---|---|---|---|
| Afghanistan | Aviation maintenance/logistics remained limiting beneath external substitution | Negative or incomplete | Abrupt contractor and U.S. support reduction followed by severe degradation | Political collapse, morale and leadership failure, corruption, strategy, and Taliban adaptation | Strong for substitution/retention; partial for discrete constraint displacement |
| Iraq | Rapid force generation followed by lagging logistics and sustainment | Incomplete in coded 2005-2008 episode | No clean withdrawal shock in coded episode | Sectarian politics, militia penetration, absenteeism, command problems, corruption, and intelligence weakness | Strongest sequential-constraint analogue, with major political confounding |
| Mali | Basic unit skills improved while pre-existing logistics, maintenance, and C2 weaknesses remained | Mixed | No clean support shock in coded 2013-2015 episode | Political fragmentation, provider fragmentation, command weakness, and institutional instability | Partial; strongest for local-system divergence |
| Colombia | Externally enabled aviation expansion initially outran pilots, mechanics, maintenance, and logistics, followed by phased nationalization | Positive and substantial over time | Phased transfer rather than abrupt withdrawal | Stronger institutions, fiscal capacity, political commitment, long duration, and continued external partnership | Strong positive retention case; partial for discrete constraint displacement |

This case set allows the historical exercise to test more than simple
similarity. Afghanistan can support the substitution and replacement mechanism
even if constraint migration is weak. Iraq provides a stronger opportunity to
observe sequential constraint change. Mali is useful precisely because rival
political explanations may dominate. Colombia provides a positive case in which
the theory should be able to accommodate sustained indigenous development
rather than predicting dependency everywhere.

Evidence is ranked in a frozen source hierarchy: oversight and audit material;
contemporaneous official or declassified records; peer-reviewed research with
primary evidence; major research institutions; and high-quality journalism.
Every episode must also record the strongest plausible rival explanation.
Political leadership, corruption, force design, morale, sectarian or factional
control, donor strategy, adversary adaptation, and changes in the threat are not
treated as residual noise. If they explain an episode better than the proposed
production sequence, the case should count against the scope of the mechanism.

The historical test therefore has three possible outcomes. **Process support**
occurs when the initial constraint, targeted relief, demand change, subsequent
constraint, and indigenous replacement pattern appear in the expected order.
**Partial support** occurs when only part of that sequence is observable, such
as persistent substitution without clear migration. **Disconfirmation** occurs
when the targeted function improves but neither demand, the binding constraint,
nor retention behaves as the mechanism predicts, or when an identified rival
account better explains the sequence.

Because the Stage-4 synthetic results were already known and the researcher had
broad prior familiarity with these cases, the historical exercise is described
as structured external validation rather than an untouched confirmatory test.
Its coding protocol, case set, source hierarchy, and disconfirming-evidence rule
were frozen before systematic case coding. The source-audited case table reports
supportive, mixed, and adverse evidence rather than selecting only episodes that
confirm the model.

Two important methodological limitations qualify these historical findings. First, all four
cases were coded by a single author without an independent second coder, leaving open single-coder
confirmation risk despite the frozen source hierarchy. Second, because the theoretical framework
encompasses multiple distinct production paths (persistent substitution in Afghanistan, sequential
constraint migration in Iraq, local-system divergence in Mali, and phased nationalization in Colombia),
accommodating each case under a different branch of the theory creates a soft qualitative test.
While the source audit preserves adverse evidence and rival political accounts rather than forcing
uniformity, these case studies serve as structured process plausibility checks rather than independent
confirmatory tests.

# 8. Limitations

First, Pineland is a synthetic model. The numerical effects reported here are consequences of a specified simulated production system, not empirical treatment effects or historical threshold estimates. The model is useful for mechanism isolation because states can be cloned and assistance components manipulated independently. That same control limits direct external validity.

Second, indigenous coverage is a ratio with an endogenous denominator. The revised paper treats this as a substantive object rather than a hidden assumption, but the ratio still depends on how service demand is represented. The no-aid capability comparison and supply-demand decomposition reduce the risk of mistaking denominator growth for destroyed indigenous capacity. The prospective demand clamp does not validate the denominator mechanism: although the manipulation succeeds, the ablation runner recorded a static pre-split baseline coordinate that structurally guaranteed a zero coverage branch difference. The simulated demand functions therefore remain a model assumption whose causal mediation must be tested with dynamic post-withdrawal coverage tracking.

Third, the structural coordinate assumes strong complementarity among force generation, logistics, and command. Smooth arithmetic, geometric, and harmonic alternatives show that many Stage-4 sign results are not unique to a hard minimum, but the model still imposes a limited set of military-production relationships. A richer model could allow more substitution among services or additional channels such as maintenance specialization, intelligence, finance, or officer quality.

Fourth, composite capability is itself a modeled construct. It is the geometric mean of five unit-scale retention components: government control, military personnel, operational formations, geographic coverage, and readiness. This measure makes whole-force performance transparent and bounded, but it is not a validated empirical index of combat effectiveness. The paper therefore reports component and service-level results alongside the composite rather than treating one number as ground truth.

Fifth, the no-aid benchmark is a matched simulation trajectory, not an observational estimate. Matching by structure, capacity, seed, and horizon provides a clean model counterfactual, but it does not reproduce the selection processes that determine which historical partners receive assistance. The distinction between supported effect, retained effect, and dependency gap is analytically useful even where a real-world no-aid counterfactual cannot be estimated cleanly.

Sixth, several important revised analyses are post-completion diagnostics. The matched no-aid comparison, supply-demand decomposition, five-horizon synthesis, migration-yield comparison, and capability-retention-cost framing were developed after the Stage-4 production campaign and after external review. They use frozen telemetry and are labeled as exploratory or post-completion rather than retroactively described as prospectively frozen. The demand-clamp experiment is different: its contract, analysis rules, seeds, and code were frozen before its own production outcomes were observed. That design revealed a measurement limitation in the ablation harness: the primary output shard recorded the static pre-split baseline coordinate at withdrawal day 120 rather than dynamic post-withdrawal service flows. Because both arms share identical prehistory, the branch difference in that field was structurally guaranteed to be zero across all 48 seeds and all five horizons. While dynamic capability effects diverged as expected, the static coverage metric prevented the experiment from testing mediation.

Seventh, assistance architectures are stylized. Development changes partner-owned production on a specified cadence, while substitution supplies removable external service. Real institutional development is politically contested, path dependent, and often much slower. The modeled donor-cost ledger is useful for internal tradeoffs but is not a dollar estimate and should not be used for empirical cost-effectiveness rankings.

Eighth, Stage 5 does not cleanly test its intended scope condition. Its nominal near-tie worlds become almost uniformly logistics-bound before the main treatment comparison. The paired factorial contrasts remain valid for the realized states, but the claim that breadth should become more efficient under a verified multi-constraint near-tie remains unresolved.

Ninth, the structural sidecar rejects only a literal hard-coding claim. It demonstrates that command, force generation, and logistics can each be terminal under adversarial structures, but the intended migration paths do not occur. It is not a global sensitivity analysis of the Stage-4 logistics attractor.

Tenth, the historical case analysis is structured external validation rather than causal confirmation. Afghanistan, Iraq, Mali, and Colombia contain political, organizational, strategic, and adversarial dynamics that the synthetic production model does not identify separately. The historical coding therefore preserves rival explanations and mixed evidence rather than treating resemblance to a simulated mechanism as proof.

Finally, the framework concerns production conditional on political decisions. Recipient incentives, command politics, corruption, patronage, donor leverage, coalition management, and adversary adaptation can determine whether a technically feasible development path is ever pursued. Relief, yield, requirement expansion, constraint displacement, and retention are therefore complements to political analysis, not substitutes for it.

# 9. Conclusion

Security assistance should not be evaluated with a single question such as whether a program "worked." The more useful questions are whether it relieved the intended constraint, how much whole-force capability followed, how the operating requirement changed, and how much capability remained after external service stopped.

The revised Pineland evidence shows why those questions must be separated. Continued support often outperforms withdrawal after a shared period of assistance, but that dependency gap is not the same as a net gain over no aid. At +30 days, 26 of 120 treated Phase-Map cells show the strict success-without-retention pattern of supported capability above matched no aid and post-withdrawal capability below matched no aid. Thirty cells improve relative to no aid in both branches, while 51 are below no aid in both. Dependence is therefore a meaningful modeled regime, not the universal result of direct support.

The mechanism evidence is also more specific than the original manuscript claimed. In the Stage-4 telemetry, terminal logistics-coverage gaps reflect both indigenous service and the scale of the operating requirement. Descriptive standardization attributes a larger share of the average gap to requirement differences than to lower indigenous delivery. That pattern is consistent with requirement expansion, but the prospective demand-clamp test does not causally confirm it. The clamp matches the withdrawal requirement closely and materially changes capability, yet the ablation harness evaluated a static pre-split baseline coordinate rather than dynamic post-split coverage, structurally guaranteeing an exact-zero coverage branch gap. Requirement expansion therefore remains a plausible interpretation of the Stage-4 trajectories rather than a causally identified mediator.

Constraint displacement is a separate dynamic. Targeted command and force-generation assistance frequently changes which service binds, yet those migrations are associated with little whole-force yield and do not explain the strongest retention penalties. Force-generation relief can therefore be locally successful while producing almost no composite-capability gain. The policy lesson is not that moving bottlenecks are inherently harmful. It is that local relief, whole-system yield, and retention are different outcomes.

Assistance architecture adds another tradeoff. Development can build partner-owned service and substantially improve terminal coverage relative to substitution, but it need not maximize immediate capability and it is not costless in the model. Stage 5 further shows that technical complementarity does not automatically imply that a fixed developmental budget should be spread broadly, especially when one service is already the realized bottleneck. The untested case that now matters most is a verified multi-constraint near-tie.

The paper's contribution is therefore narrower and stronger than the claim that "support builds dependence." It provides a production framework for distinguishing supported effects, retained effects, dependency gaps, and successful local relief that merely shifts the limiting constraint. It also shows why mechanism claims require tests beyond outcome decomposition and why those tests can fail even when the original pattern looks persuasive. The practical implication is straightforward: measure absolute supported capability, retained capability, service demand, indigenous service production, the current binding constraint, and cost separately. A force that performs well with the donor and a force that can reproduce that performance without the donor are not the same outcome, and assistance evaluation should not treat them as if they were.

# Data, Code, and Reproducibility

The Pineland repository contains the model source, frozen experiment contracts,
analysis code, compact evidence tables, figure-generation code, and integrity
validators needed to reproduce the manuscript results. Stage 4 completed 2,808
production worlds, Stage 5 completed 1,472, and the post-review demand-clamp
experiment completed 96 worlds under a separately frozen contract and fresh
seed namespace. Each
production campaign records task-level source and contract provenance, and the
tracked compact evidence is regenerated from immutable raw shards before final
manuscript validation. Exact commit identifiers, artifact hashes, cluster
commands, and file-level provenance are reported in the supplementary
reproducibility appendix rather than in the substantive article.

# Disclosure

The author designed and developed the Pineland simulation and conducted the
analysis described here. The historical-validation exercise was conducted after
the synthetic Stage-4 results were observed and is therefore labeled as external
validation rather than prospective confirmation. The manuscript makes
no claim that synthetic numerical thresholds are empirical estimates for any
historical security force. The relief-yield-retention framing and the weighted
cross-target yield comparison were developed after Stage-4 completion and are
labeled as post-completion synthesis. The coordinated-development Stage-5
experiment was motivated by those completed results but prospectively frozen
before any Stage-5 production outcome was observed. The post-review demand-clamp
experiment was likewise prospectively frozen before its production outcomes;
its harness measurement limitation and zero precommitted coverage attenuation are
reported without redesigning the experiment around the result.
