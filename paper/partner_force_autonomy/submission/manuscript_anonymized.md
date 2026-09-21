---
title: "Suffering from Success: Relief, Yield, and Retention in Security Assistance"
bibliography: references.bib
date: "September 21, 2026"
keywords: "security assistance; military effectiveness; partner forces; sustainment; logistics; agent-based modeling"
---

# Abstract

Security assistance can improve a force while support is available without showing how much capability the partner can reproduce after external service stops. This article separates **relief**, whether assistance improves a limiting service; **yield**, how much whole-force capability follows; and **retention**, how much remains after support ends. I evaluate this framework in the Pineland agent-based model using a frozen 2,808-world Stage-4 campaign, a 1,472-world coordinated-development extension, matched no-aid controls, and a prospectively frozen post-review demand-clamp test. At +30 days, 26 of 120 treated Phase-Map cells show supported capability above matched no aid but post-withdrawal capability below no aid; 30 improve in both branches and 51 are below no aid in both. Frozen-telemetry decomposition associates terminal logistics-coverage gaps with both indigenous service and the supported operating requirement. A direct demand clamp passes its manipulation check but does not identify requirement expansion as the cause of those gaps because the fresh-seed normal arms reproduce positive capability effects but no coverage penalty to attenuate. Constraint displacement is better identified: command and force-generation bottlenecks migrate frequently but produce little system yield and do not explain the strongest retention penalties. Developmental assistance improves partner-owned service but lies on a capability-retention-cost frontier rather than uniformly dominating substitution. The contribution is therefore a diagnostic production framework for showing why local assistance success, whole-force performance, dependence on continuing support, and post-support retention need not coincide.
# 1. Introduction

Security assistance is often assessed through outcomes that are related but not identical. Did the donor fix the targeted military problem? Did the force become more capable? Could the partner reproduce that capability after external support stopped? Existing research explains disappointing assistance outcomes through provider-recipient interest misalignment, weak institutions, limited leverage, fragmented security sectors, poor absorptive capacity, fragile elite formations, and dependence on external resources [@biddle2017; @biddle2018; @metz2023; @matisek2018; @knowlesmatisek2019; @harkness2022; @sandnes2024]. Recent work also treats security assistance as a relational practice that can reshape authority, alignment, and dependency rather than merely transfer technical inputs [@rolandsen2021; @rolandsen2026].

This article addresses a narrower production problem. Even when assistance changes the military function it targets, three outcomes can diverge. **Relief** concerns the targeted constraint. **Yield** concerns whole-force capability. **Retention** concerns what remains after the donor's additional service stops. Treating these as one outcome obscures both successful and unsuccessful assistance. A program can fix a training bottleneck without raising whole-force performance because logistics binds next. It can raise supported performance without creating a retained gain because the operating requirement grows faster than indigenous sustainment. It can also improve both supported and retained capability.

The underlying ideas are not individually new. Theory of Constraints expects relief of one bottleneck to expose another [@watson2007]. Hirschman's unbalanced-growth logic treats expansion in one activity as a source of new complementary shortages [@hirschman1958]. Foreign-aid research shows that donor-financed activity can increase claims on scarce recurrent or administrative resources [@roodman2006; @arimotokono2009]. Security-assistance scholarship has long distinguished current performance from sustainability and independent capacity. The contribution here is to translate those insights into a military-production framework that separates outcomes first and then assigns distinct empirical tests to candidate explanations for their divergence.

The first is **requirement expansion**. Assistance can enable a force to sustain more personnel, movement, patrols, combat, or command activity. Those operations generate service requirements. If the requirement for a complementary indigenous service grows faster than indigenous production, the partner's coverage of the supported operating requirement falls even if indigenous service itself increases. This is a numerator-denominator mechanism. It does not require the binding service to change.

The second is **constraint displacement**. Assistance can successfully improve the service that currently limits the force, only for another service to become binding. Once that happens, further improvement of the relieved service can have little whole-system return. This is a bottleneck mechanism. It explains relief without yield, but it does not by itself imply a retention penalty.

These mechanisms imply a stricter empirical standard than the original manuscript used. Comparing continued support with withdrawal after a common period of support identifies a dependency gap, but it does not establish that support improved capability relative to no aid. The revised analysis therefore distinguishes the supported effect relative to a matched zero-support trajectory, the retained effect after withdrawal relative to the same benchmark, and the gap between continued support and withdrawal. A strong success-without-retention case requires supported capability above no aid and post-withdrawal capability below no aid.

I evaluate the framework using Pineland, a partially observed agent-based model that represents military personnel, formations, readiness, logistics, command, external support, force generation, governance, armed organizations, and territorial competition. Stage 4 contains 2,808 prospectively frozen production worlds across a Phase Map, a targeted bottleneck-displacement module, and a substitution-versus-development module. Stage 5 adds 1,472 separately frozen worlds testing coordinated indigenous development. Post-review analyses use only frozen telemetry for matched no-aid comparisons and service-demand decomposition, while a separately frozen demand-clamp experiment tests whether requirement expansion actually mediates the terminal coverage gap.

The revised evidence is more qualified than the original branch-contrast headline. At +30 days, 26 of 120 treated Phase-Map cells meet the strict pattern of positive supported capability relative to no aid and negative retained capability after withdrawal. Thirty cells improve relative to no aid in both branches, 51 are below no aid in both branches, one is negative under support but positive after withdrawal, and 12 are neutral on at least one contrast. Thus support-induced dependence is a meaningful regime in the model, not its universal outcome.

The mechanism evidence also separates, but asymmetrically. Among worlds with negative terminal logistics coverage, the continued-support branch usually faces a larger logistics requirement, and descriptive standardization attributes a larger share of the mean coverage gap to demand than to indigenous-service decline. The prospectively frozen clamp test, however, does not causally validate that interpretation. Its demand manipulation succeeds, but the fresh-seed normal arms reproduce positive capability effects without reproducing any indigenous-coverage branch gap, leaving no retention penalty to attenuate. Requirement expansion therefore remains a plausible production dynamic supported descriptively, not an identified cause of the Stage-4 retention pattern. By contrast, the Migration module directly shows that command and force-generation constraints are readily displaced while logistics is persistent. Force-generation relief can change the binding service while producing essentially no composite-capability gain. Constraint displacement therefore explains relief without yield, not the terminal retention penalty.

The treatment-mode results add a further qualification. Developmental logistics assistance produces much more partner-owned logistics service and much better terminal coverage than substitution, but it is somewhat more expensive in the model and does not uniformly dominate on near-term capability. Assistance design therefore lies on a capability-retention-cost frontier. Stage 5 likewise finds a small number of positive equal-dose complementarities, but its intended near-tie structure becomes logistics-bound before the main comparison. The fixed-budget breadth result consequently applies to the realized single-bottleneck regimes rather than cleanly testing the intended near-tie hypothesis.

The paper makes three contributions. First, it provides a minimal production model separating supported capability, retained capability, service coverage, and the dependency gap. Second, it demonstrates why requirement growth and constraint displacement require different empirical tests and reports both supportive and failed tests rather than inferring mechanism from outcome patterns alone. Third, it offers a measurement framework for evaluating security assistance through relief, yield, retention, service demand, indigenous production, and cost rather than treating supported performance as a proxy for autonomous capacity.

The scope is limited. Pineland is a synthetic laboratory, not a forecasting system. Numerical effects are model outcomes, not estimates for Afghanistan, Iraq, Mali, Colombia, or any other historical force. Historical cases are used only as structured external validation, with rival political explanations preserved rather than treated as noise.

# 2. Security Assistance, Dependence, and the Missing Production Dynamic

## 2.1 Interest misalignment and influence

A major strand of security-force-assistance research treats poor outcomes as an
agency problem. Biddle, Macdonald, and Baker argue that U.S. efforts frequently
encounter systematic interest misalignment with recipients, which limits the
military effectiveness achievable through small-footprint assistance
[@biddle2017; @biddle2018]. Metz develops a related account centered on influence. Recipient
leaders may have political incentives to preserve military practices that
external advisers seek to reform, while U.S. organizations often prefer
teaching and persuasion to more coercive forms of conditionality [@metz2023].

This work explains why recipients may fail to adopt reforms even when donors
possess technical expertise. It also guards against an overly technocratic
interpretation of military weakness. A partner force can remain ineffective
because the political system that produces it rewards behaviors that donors
regard as pathologies. The present article accepts that insight. It asks a
different question: conditional on assistance actually improving a targeted
military function, what happens to the production structure of the partner
force afterward?

## 2.2 Fragile forces, weak institutions, and dependence

A second literature emphasizes the fragility of forces built without
corresponding political and institutional foundations. Matisek describes
externally constructed but brittle militaries as "Faberge Egg" forces whose
apparent capability can collapse when external support is removed
[@matisek2018]. Knowles and Matisek similarly argue that technical assistance
cannot substitute for political settlement and local ownership in weak states
[@knowlesmatisek2019]. Harkness shows that concentrating assistance in enclave
units can create effective pockets of force while generating political and
institutional consequences for the broader security system [@harkness2022].
Sandnes conceptualizes the G5 Sahel Joint Force's relationship with external
actors as asymmetric interdependence and emphasizes the difficulty of reaching
an autonomous endpoint under such a relationship [@sandnes2024].

Security-assistance scholarship also already treats independence or
sustainability as a distinct outcome from current battlefield performance.
Karlin includes the ability to sustain a partner military without continuing
U.S. support in the outcome concept for successful military building
[@karlin2018]. Reynolds similarly proposes an explicit Security Autonomy Index
for assessing whether recipient institutions can internalize and sustain
security models [@reynolds2025]. These works occupy important conceptual ground
that the present article does not claim as new. The contribution must therefore
lie in the production mechanisms separating supported from retained capability,
not in noticing that such divergence can exist.

Policy and evaluation literatures make a related point in the language of
absorptive capacity and sustainment. RAND research on defense institution
building stresses the organizational and institutional foundations required to
convert external assistance into durable partner capability [@mcnerney2016].
Earlier RAND work on building partnership capacity likewise emphasizes that
assistance effectiveness depends on context, recipient capacity, and the type of
capability being built rather than the transfer of resources alone [@paul2013].
GAO's review of Section 333 train-and-equip proposals found that 42 of 46
reviewed proposals did not fully document sustainment, absorptive capacity, or
measurable objectives [@gao2023]. These literatures make it clear that durable
capacity cannot be inferred from equipment delivery or tactical proficiency.

An adjacent state-capacity literature sharpens the same warning. Pritchett,
Woolcock, and Andrews describe **premature load bearing** as a condition in which
organizations are asked to perform functions beyond the capabilities they have
actually developed [@pritchett2013]. Andrews, Pritchett, and Woolcock develop
that argument into a broader account of capability traps and problem-driven
institution building [@andrews2017]. The present theory is narrower and more
mechanistic. It asks how successful assistance can itself alter the service
requirements placed on a military organization, and how the identity of the
binding production constraint changes as a result. In that sense, support-
enabled demand is not merely an external burden placed on a weak organization;
it can be an endogenous consequence of prior success.

The contribution here is therefore not the claim that assistance can create
dependency. That point is well established. The narrower problem is how to
separate current supported performance from retained capability while identifying
whether a gap arises because operating requirements expand, because indigenous
production changes, or because a different complementary service becomes
binding.

It is also useful to separate three forms of dependence that are often collapsed
into one label. **Operational dependence** means that a specified military
output cannot be generated without continuing foreign service or input
provision. **Institutional dependence** means that external provision weakens
or displaces the development of indigenous organizations. **Relational
dependence** means that reliance on an external actor creates asymmetric
bargaining power. The production framework here is fundamentally operational.
Requirement expansion and constraint displacement can coexist with the
institutional and relational forms, but neither mechanism logically requires
them.

## 2.3 Bottlenecks, recurrent costs, and complementary production

The closest general antecedent is the Theory of Constraints. In that tradition,
system throughput is governed by the active constraint; improving a
nonconstraint yields little whole-system benefit, while successful elevation of
the current constraint eventually causes another to become limiting
[@watson2007]. That logic is almost an abstract statement of constraint
migration. It should therefore be treated as a theoretical foundation rather
than claimed as an original discovery.

Hirschman's unbalanced-growth framework provides a second close precedent.
Expansion in one sector creates shortages, pressures, and inducements for
complementary investment elsewhere [@hirschman1958]. The key similarity is
endogeneity: the next shortage is generated or made salient by successful
expansion in the first activity. The difference is that Hirschman's mechanism
is normally developmental and economy-wide, whereas the present argument
focuses on selective foreign substitution inside a military production system
and on the possibility that observed performance rises faster than indigenous
reproduction.

Foreign-aid research comes closer still to the support-induced demand problem.
Roodman models donor aid and scarce recipient-side resources as complementary
inputs and shows how project proliferation can overload the local resources
needed to administer assistance [@roodman2006]. Arimoto and Kono model
donor-financed investment that generates recurrent-cost obligations which the
recipient must supply if project benefits are to persist
[@arimotokono2009]. Morss's earlier work on donor and project proliferation
similarly emphasizes the burden placed on scarce recipient administrative
capacity [@morss1984]. These are direct precedents for the proposition that an
external input can increase the requirement for a scarce indigenous complement.

The military contribution is narrower. The relevant complement need not be a
recurrent cost attached directly to the donated asset. Assistance to one
service can enable a broader change in operating scale or complexity whose
demands spill onto a different service. More reliable command can make larger
formations usable. More force generation can increase logistics and
replacement demand. More mobility can increase maintenance, fuel,
communications, medical evacuation, and distribution requirements. The object
of interest is therefore a changing constraint set in which the service that
limits the whole force is itself endogenous to successful intervention.

This point is consistent with mature theories of complementarity. Kremer's
O-ring model shows why weak performance in one indispensable task can sharply
reduce the return to excellence elsewhere [@kremer1993], and organizational
complementarity research shows how returns to one practice can depend on the
presence of others [@milgromroberts1990], while military
effectiveness research has long treated armed forces as complex organizations
whose aggregate performance cannot be inferred from isolated attributes
[@millett1986]. Biddle's force-employment account similarly demonstrates that
material inputs do not map mechanically into military capability because their
effect depends on how forces employ them [@biddle2004]. Military logistics
scholarship likewise demonstrates that
movement and sustainment can delimit operational possibility [@vancreveld2004].
The paper therefore makes no generic claim that militaries are systems, that
logistics matters, or that nonbinding improvements can have low system returns.

Absorptive capacity is adjacent but distinct. In its classic organizational
form, absorptive capacity concerns the ability to recognize, assimilate, and
exploit external knowledge [@cohenlevinthal1990]. A partner can display high
absorptive capacity in an assisted subsystem and still fail to reproduce the
larger military system that successful absorption makes possible. The most
diagnostic cases for the present theory are therefore not failed absorption,
but successful first-stage absorption followed by insufficient indigenous
production in another complementary service.

Aid-dependence research also offers a competing route to superficially similar
outcomes. High external financing can weaken accountability, distort incentives,
or inhibit long-run institution building [@knack2001; @brautigamknack2004;
@moss2006]. Those mechanisms can also produce high supported output and weak
post-support retention. The empirical burden here is to show a different production sequence:
assistance changes supported operations and service requirements, indigenous
production may fail to keep pace, and local constraint relief may or may not
translate into whole-system yield.

## 2.4 From static capacity to endogenous production dynamics

Military capability is jointly produced: personnel, logistics, command, and
force generation are complements, so improving one function need not increase
whole-force output. Assistance can also change the system it evaluates by
enabling more personnel, movement, coordination, or operations, which can alter
service requirements and the identity of the binding constraint. The narrow
contribution is therefore a measurement framework that places **supported
capability, retained capability, service requirements, indigenous production,
and changing constraints** in one production system while keeping candidate
mechanisms empirically separable.

# 3. Theory

## 3.1 A minimal complementary-production model

Consider a military system that requires services indexed by \(j\). An
operation of scale or complexity \(x\) requires \(r_j(x)\) units of service
\(j\). Indigenous production is \(I_j\) and external provision is \(E_j\).
Supported feasible capability and independently reproducible capability are

\[
C^{S}=\max x \quad \text{s.t.} \quad r_j(x)\le I_j+E_j \quad \forall j,
\]

and

\[
C^{A}=\max x \quad \text{s.t.} \quad r_j(x)\le I_j \quad \forall j.
\]

For the useful special case \(r_j(x)=a_jx\), these reduce to

\[
C^{S}=\min_j\frac{I_j+E_j}{a_j},
\qquad
C^{A}=\min_j\frac{I_j}{a_j}.
\]

The result is elementary but important. A force can possess a high supported
capability and a much lower independently reproducible capability at the same
point in time. The gap \(C^S-C^A\) is therefore a production property, not a
claim that indigenous capability has necessarily been destroyed.

The empirical analysis also records **indigenous coverage** of an observed
service requirement. For any active service with demand \(D_j>0\),

\[
q_j^I=\frac{I_j}{D_j},
\qquad
q_j^S=\frac{I_j+E_j}{D_j}.
\]

The structural coverage coordinate is \(q^I=\min_j q_j^I\), and the observed
binding service is \(B=\arg\min_j q_j^I\). Coverage is deliberately kept
distinct from absolute capability. A lower \(I/D\) ratio can reflect lower
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
\(C_h^0\) be capability at horizon \(h\) under matched no aid, \(C_h^{ON}\)
capability with continued support after the split, and \(C_h^{OFF}\) capability
after the same supported prehistory followed by withdrawal. Then

\[
S_h=C_h^{ON}-C_h^0
\]

is the supported effect,

\[
R_h=C_h^{OFF}-C_h^0
\]

is the retained effect, and

\[
G_h=C_h^{ON}-C_h^{OFF}=S_h-R_h
\]

is the dependency gap between continued support and withdrawal. A strong
success-without-retention case requires \(S_h>0\) and \(R_h<0\). This is a
stricter condition than simply observing \(C_h^{ON}>C_h^{OFF}\), because the
latter can arise when withdrawal harms a force that was not outperforming the
matched no-aid trajectory.

The three-part framework also separates two system dynamics that the original
draft treated as one. **Requirement expansion** can create yield without
retention. **Constraint displacement** can create relief without much yield.
Neither mechanism logically requires the other.

## 3.3 Requirement expansion and indigenous coverage

Suppose assistance allows the force to operate at a higher supported scale
\(C^S\). Service demand may then rise with that operating scale. Write the
requirement for service \(j\) as \(D_j=g_j(C^S)\), with \(g_j'\ge0\). Indigenous
coverage is

\[
q_j^I=\frac{I_j}{g_j(C^S)}.
\]

For positive values, the change in log coverage decomposes exactly as

\[
\Delta\ln q_j^I=\Delta\ln I_j-\Delta\ln D_j.
\]

Coverage therefore falls whenever proportional growth in the service
requirement exceeds proportional growth in indigenous service. This can occur
even when \(I_j\) increases in absolute terms. It can also occur while the same
service remains binding throughout. Requirement expansion is therefore a
distinct mechanism from bottleneck migration.

**Proposition 1, Requirement Expansion.** Conditional on an assistance-induced
increase in operating requirements, indigenous coverage of service \(j\) falls
when \(D_j\) grows faster than \(I_j\).

**Proposition 2, Supported-Retained Divergence.** Assistance can generate a
positive supported effect \(S_h\) while producing a smaller or negative retained
effect \(R_h\) when the supported system depends on service production that the
partner does not reproduce after withdrawal.

## 3.4 Constraint displacement and system yield

Requirement expansion is not the only reason local improvement can fail to
translate into system performance. In the linear special case, suppose service
\(k\) is the unique supported bottleneck. Increasing external service \(E_k\)
raises \(C^S\) only until

\[
\frac{I_k+E_k}{a_k}
=
\min_{j\ne k}\frac{I_j+E_j}{a_j}.
\]

Beyond that threshold, another service binds and the marginal system return to
additional service \(k\) is zero unless the new constraint is also relieved.
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

Direct substitution increases \(E_j\). Developmental assistance seeks to raise
\(I_j\). Development at a persistently binding service can therefore improve
indigenous coverage, but it need not dominate substitution on near-term
capability or modeled donor cost. The relevant policy object is a frontier among
supported capability, retained capability, indigenous service, time, and cost,
not a single ranking of assistance modes.

If several services are genuinely near binding, coordinated development may
generate technical complementarity. For two services, the equal-dose factorial
interaction is

\[
I_{AB}=Q_{AB}-Q_A-Q_B+Q_0,
\]

where \(Q\) is the prespecified terminal system coordinate. A positive
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

The central quantities in the theory are difficult to identify directly in
historical data. Donor service, indigenous service, latent demand, and the
counterfactual state of the same force after withdrawal are rarely observed at
the same temporal and functional resolution. Historical forces also select into
assistance nonrandomly, donor packages change with battlefield conditions, and
the withdrawal of support is usually endogenous to political events.

Pineland is used here as a causal laboratory rather than a forecasting system.
The model makes service flows explicit, permits exact cloning at withdrawal,
and allows one component of external support to be removed while preserving the
rest of the simulated state and random streams. This provides causal leverage
over mechanisms that are difficult to isolate observationally. It does not by
itself provide empirical estimates for real-world cases.

## 4.2 Pineland partner-force architecture

Pineland is a partially observed agent-based model of insurgency,
counterinsurgency, political order, logistics, information, mobility, and
foreign assistance. The complete model is documented using the ODD structure
for agent-based model reporting [@grimm2020odd] in the replication materials.
The present paper uses a narrower partner-force
layer with three service channels: force generation, logistics, and command.
Each channel records demand, indigenous service, and removable external service
in like-for-like units.

| Channel | Demand | Indigenous service | External service |
|---|---|---|---|
| Force generation | military losses during the measurement window | indigenous training graduates | externally enabled incremental graduates |
| Logistics | military logistics demanded | indigenous logistics delivered | external logistics delivered |
| Command | command opportunities multiplied by a fixed 0.5 service requirement per opportunity | indigenous command service | supported command service above the indigenous amount |

The structural coverage coordinate is computed only for channels with positive
demand. A zero-demand channel is inactive rather than assigned an arbitrary
coverage value. The binding service is the active channel with the lowest
indigenous service-to-demand ratio.

Logistics demand is endogenous to the simulated force. It accumulates through
presence consumption, movement, patrol activity, and combat supply
requirements. Force generation demand is realized military loss. Command demand
is generated by command opportunities. Assistance can therefore alter service
requirements indirectly by changing personnel survival, readiness, movement,
patrols, combat, and other operational states. The demand side of the coverage
ratio is not an exogenous treatment label.

Whole-force capability is measured separately from service coverage. Let
\(g\), \(p\), \(f\), \(c\), and \(r\) denote government-control retention,
military-personnel retention, operational-formation survival, geographic
coverage retention, and operational-readiness retention, each bounded to
\([0,1]\) relative to the split-time reference state. The primary composite is

\[
C=(gpfcr)^{1/5}.
\]

Thus a reported capability difference of 0.02 is a two-hundredths difference on
a unit-scale geometric retention index, not a two-percent estimate of historical
combat effectiveness. An earlier four-component version excluding readiness is
retained in telemetry for audit but is not the paper's primary capability
coordinate.

Developmental assistance alters partner-owned productive capacity on a weekly
cadence. Direct substitution instead supplies removable external service. The
specific treatment coefficients and all model parameters used in production are
reported in the archived contracts and parameter table. The formal adapter is
also checked against a small Lean specification for nonnegativity and service
feasibility. That verification establishes implementation consistency, not the
empirical validity of the model.

At simulated day 120, each Stage-4 world is cloned into continued-support and
withdrawal branches. The branches are identical at the split. The withdrawal
branch removes the designated external continuation while preserving indigenous
formations, personnel, accumulated developmental capacity, stocks, governance
state, topology, and random streams. Outcomes are measured 7, 30, 90, 180, and
360 days after the split.

## 4.3 Integrated Stage-4 design

The experiment contains 234 cells and 2,808 production worlds, with 12 seeds
per cell.

| Module | Cells | Seeds per cell | Worlds | Purpose |
|---|---:|---:|---:|---|
| Phase Map | 140 | 12 | 1,680 | Vary starting structure, indigenous capacity, and direct support intensity |
| Bottleneck Migration | 52 | 12 | 624 | Target observed and nominal constraints and track persistent migration |
| Substitution vs Development | 42 | 12 | 504 | Compare no aid, direct substitution, indigenous development, and hybrid assistance |
| **Total** | **234** | **12** | **2,808** | Integrated test of phenomenon, dynamics, and mechanism |

**Table 1. Integrated Stage-4 experimental design.** Each production world uses
one frozen seed within a prospectively frozen cell. The three modules separate
branch divergence, constraint displacement, and the assistance-architecture
contrast between substitution and indigenous development.

The Phase Map crosses four starting structural families with five indigenous
capacity levels and seven direct-support intensities from 0 to 2 times the
balanced service package. The Migration module contains force-generation,
logistics, command, balanced-targeted, and no-support conditions across three
treatment intensities. The treatment target is evaluated against the **observed
pre-withdrawal bottleneck**, not assumed to be correct because of the nominal
cell label.

The mechanism module varies force-generation, logistics, and command weakness;
moderate and severe starting conditions; treatment mode; and low or high
intensity. Direct substitution provides external service. Developmental
assistance increases partner-owned productive capacity on a fixed treatment
cadence. Hybrid assistance combines both. Development accumulated before
withdrawal remains in the withdrawal branch, while future donor-funded
development stops.

## 4.4 Estimands and uncertainty

The original Stage-4 estimands were frozen before production. The early branch
contrast is continued support minus withdrawal in composite capability at +30
days. The terminal structural contrast is continued support minus withdrawal in
capped indigenous coverage at +360 days. The original analysis called the joint
pattern of a positive early branch contrast and a negative terminal coverage
contrast an autonomy trap. The revised analysis retains those results as
frozen branch contrasts but does not equate them with net benefit over no
aid.

Two post-completion analyses were added after external review and are labeled as
such throughout. First, each treated Phase-Map world is matched by structure,
capacity, seed, and horizon to its zero-support control. This yields the
supported effect \(S_h\), retained effect \(R_h\), and dependency gap \(G_h\)
defined in Section 3.2. Second, the terminal coverage contrast is decomposed
into indigenous-service and demand components. For worlds in which logistics
binds in both terminal branches, two standardized quantities are also reported:
continued-support indigenous service evaluated at withdrawal-branch demand, and
withdrawal-branch indigenous service evaluated at continued-support demand.
These standardizations are descriptive counterfactual calculations, not runtime
interventions.

The revised paper therefore distinguishes three classes of evidence: frozen
Stage-4 estimands, explicitly labeled post-completion diagnostics from frozen
telemetry, and a separately frozen post-review mechanism ablation that directly
intervenes on logistics demand.

Cell summaries report means, medians, 10th and 90th percentiles, and directional
seed fractions because prior experiments showed material heavy-tail behavior.
Bootstrap intervals are retained as descriptive stability summaries, not as
population-sampling significance tests. No world is removed as an outlier and
no primary result is winsorized. The revised text emphasizes effect sizes,
directions, and robustness across conditions rather than treating the number of
simulation seeds as inferential sample size.

For the mechanism experiment, development-minus-substitution and
hybrid-minus-substitution contrasts use matched seed indices within the same
target, severity, and intensity condition. These are common-random-number
contrasts, not exact cloned counterfactuals across treatment modes because the
pre-withdrawal treatment histories differ.

## 4.5 Reproducibility and production integrity

The production simulator, contracts, and selected runtime artifacts were locked
under a cryptographic freeze before production. Engineering calibration used a
disjoint seed namespace from the production experiment. All 2,808 production
worlds completed. An independent final audit re-hashed every primary and
trajectory shard and verified exact logical-task coverage, row counts,
filenames, production commit, freeze hash, and contract hash. The audit found
zero missing task IDs, zero duplicate task IDs, and zero integrity errors.

Postprocessing repairs were isolated from production. Exact commits, artifact
hashes, seed namespaces, task ledgers, and reproduction commands are reported
in the online replication appendix rather than in the substantive argument.

## 4.6 Proposition-to-test correspondence

The revised theory assigns different tests to the two mechanisms. The Phase Map
establishes branch divergence and supplies the frozen telemetry for the
post-review supply-demand decomposition. A separate prospectively frozen
demand-clamp experiment directly tests Proposition 1 by preventing the
continued-support branch from generating a larger logistics requirement than
its matched withdrawal branch. The no-aid controls in the Phase Map identify
the supported effect, retained effect, and dependency gap in Proposition 2.

The Migration module tests Proposition 3. Its purpose is not to explain the
coverage penalty. It asks whether successful relief displaces the binding
service and whether such displacement is associated with material system yield.
The substitution-versus-development module then shows how local indigenous
production, system capability, terminal coverage, and modeled donor cost move
together under different assistance architectures.

This mapping is intentionally asymmetric. Requirement expansion can reduce
coverage without migration, and migration can occur without a negative terminal
coverage effect. The empirical analysis treats those possibilities as competing
observations rather than forcing them into one causal chain.

## 4.7 Prospectively frozen coordinated-development extension

The completed Stage-4 findings raise an additional question that was not part of
the original preregistration: can several complementary indigenous capacities
be developed together so that the whole production frontier moves outward rather
than one bottleneck simply replacing another? Because this question emerged
after Stage-4 results were known, it was treated as a separate prospective
extension rather than retrofitted into the original design.

Stage 5 contains 92 cells and 16 matched seeds per cell, for 1,472 production
worlds. It tests all nonempty combinations of indigenous force-generation,
logistics, and command development across four nominal starting structures: one
force-generation bottleneck, one logistics bottleneck, one command bottleneck,
and a low-capacity near-tie structure in which all three service multipliers begin
at the same level. Two developmental intensities are used.

The design deliberately separates two questions. Under **equal total effort**,
a fixed normalized developmental dose is divided across the active channels.
This tests whether breadth itself improves allocation efficiency. Under **equal
channel dose**, each active service receives the full single-channel dose.
Multi-channel arms therefore use more total effort, allowing direct estimation
of pairwise and three-way factorial interactions without interpreting raw outcome
differences as cost efficiency.

The primary endpoint is capped indigenous whole-system feasibility on the
`SUPPORT_OFF` branch at +360 days. All arms receive the same 120-day developmental
prehistory. At the split, additional donor-driven development stops while the
indigenous productive capacity accumulated during the prehistory remains. The
prospectively frozen analyses therefore estimate retained coverage and capability gains,
pairwise and three-way factorial interactions, equal-total-effort breadth
premiums, and bottleneck dynamics.

The Stage-5 protocol, contract, analysis code, and inherited scientific
foundation were prospectively frozen before any Stage-5 production outcome was
observed. The campaign completed all 1,472 worlds. Exact source commits, hashes,
and execution provenance are reported in the replication appendix.

A manipulation check is essential for interpretation. The nominal multiplier
structures do not always remain the observed formal bottleneck after the common
120-day developmental prehistory. At the split, logistics is the observed
bottleneck in all 368 nominal force-generation-constrained worlds, all 368
logistics-constrained worlds, and 365 of 368 nominal near-tie worlds. The nominal
command-constrained structure preserves command as the split-point bottleneck in
100 of 368 worlds and logistics in the remainder. Stage-5 structure labels are therefore reported as **nominal design factors**,
not as validated observed bottleneck identities. This weakens any causal
interpretation of the intended near-tie scope-condition test while leaving the
paired treatment contrasts themselves intact.

# 5. Results

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

\[
\Delta\ln q = \Delta\ln I-\Delta\ln D
\]

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
coverage branch effects were approximately -0.106, -0.105, -0.106, and -0.134.
The ablation reruns those exact cell parameters under a fresh seed namespace,
with paired normal and demand-clamped arms across 48 matched seeds.

The manipulation itself succeeds. Across 2,640 post-split telemetry intervals,
the median relative mismatch between clamped supported-branch logistics demand
and the paired withdrawal requirement is 0.46 percent, the 95th percentile is
1.30 percent, the maximum is 2.05 percent, and every interval lies within the
precommitted 5 percent tolerance.

The primary outcome, however, fails its replication prerequisite. In all 48
fresh-seed normal worlds, the capped indigenous-coverage branch gap is exactly
zero at +7, +30, +90, +180, and +360 days. The demand-clamped worlds are also
zero at every registered horizon. There is therefore no normal-arm retention
penalty for the clamp to attenuate. The precommitted +360-day attenuation
estimate is exactly zero, but that value cannot be interpreted as evidence that
requirement expansion is causally irrelevant to the Stage-4 penalty.

The failure is specific to the retention outcome rather than to the assistance
effect generally. The fresh-seed normal arms retain positive mean +30-day
composite-capability branch effects in all four scenarios, approximately +0.226,
+0.083, +0.008, and +0.013. Clamping logistics demand materially changes that
capability effect, reducing the pooled branch contrast by about 0.093 at +30
days, 0.212 at +90, 0.213 at +180, and 0.147 at +360. Thus the demand
intervention is operationally consequential, but it does not identify the cause
of a coverage gap that is absent in the fresh-seed normal arm.

This result narrows the paper's mechanism claim. The frozen Stage-4 telemetry
remains descriptively consistent with requirement expansion, but the prospective
ablation does not establish requirement expansion as the mediator of the
retention pattern. It also reveals a seed-domain transport problem for the
selected coverage effects that future experiments must treat as a first-order
robustness question.

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

| Observed-matched target | Persistent migration | Mean +30d capability effect | Mean +360d indigenous-coverage effect |
|---|---:|---:|---:|
| Command | 38/38 | +0.00354 | +0.0555 |
| Force generation | 46/46 | approximately 0.00000021 | 0.0000 |
| Logistics | 0/85 | +0.01699 | -0.2215 |

**Table 2. Relief, migration, system yield, and terminal indigenous coverage in
observed-matched Migration worlds.** The weighted means are a post-completion
descriptive synthesis of frozen cell summaries. They were not themselves a
prospectively frozen primary estimand.

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
decomposition, but the prospective clamp test fails to reproduce a normal-arm
coverage penalty and therefore does not identify requirement expansion as its
cause.

| Result | Estimate | Status |
|---|---:|---|
| +30d cells with supported capability above no aid and retained capability below no aid | 26/120 | Post-completion matched-control diagnostic |
| +30d cells with both supported and retained capability above no aid | 30/120 | Post-completion matched-control diagnostic |
| Same-terminal coverage-penalty worlds with higher continued-support logistics demand | 95.9% of 1,174 | Post-completion telemetry decomposition |
| Mean standardized coverage effect in +30d-effective logistics-penalty worlds | observed -0.0823; production-only -0.0301; demand-only -0.0534 | Post-completion diagnostic |
| Fresh-seed normal worlds reproducing a nonzero coverage branch gap in the demand-clamp test | 0/48 at every registered horizon | Post-review prospectively frozen replication failure |
| Demand-clamp manipulation intervals within 5% of paired withdrawal demand | 2,640/2,640 | Post-review prospectively frozen manipulation check |
| Observed-matched command migration | 38/38 | Frozen Stage-4 Migration module |
| Observed-matched force-generation migration | 46/46 | Frozen Stage-4 Migration module |
| Observed-matched logistics migration | 0/85 | Frozen Stage-4 Migration module |
| Force-generation development minus substitution on terminal system coverage | 0 in all four cells | Frozen Stage-4 mechanism module |

**Table 3. Headline evidence after separating outcomes from mechanism claims.**
The matched-control and supply-demand decompositions were added after external
review and are labeled post-completion diagnostics. The demand-clamp rows come
from a separately frozen post-review experiment and show both a successful
manipulation and a failed retention-outcome replication.

The constraint-displacement result is also highly insensitive to replacing the hard
minimum coverage coordinate with smooth service aggregators in the Migration
module. Across the 169 worlds in which the assistance target matched the
observed pre-withdrawal bottleneck, the sign of the +360-day coverage effect
agrees between the hard-minimum measure and each of the arithmetic, geometric,
and harmonic smooth measures in 167 worlds, or 98.8 percent. The two discordant
worlds are one command-targeted world and one logistics-targeted world.

| Observed-matched target | Worlds | Hard minimum vs arithmetic | Hard minimum vs geometric | Hard minimum vs harmonic |
|---|---:|---:|---:|---:|
| Command | 38 | 37/38, 97.4% | 37/38, 97.4% | 37/38, 97.4% |
| Force generation | 46 | 46/46, 100% | 46/46, 100% | 46/46, 100% |
| Logistics | 85 | 84/85, 98.8% | 84/85, 98.8% | 84/85, 98.8% |
| **Total** | **169** | **167/169, 98.8%** | **167/169, 98.8%** | **167/169, 98.8%** |

**Table 4. Sign robustness of terminal-coverage effects to smooth feasibility
aggregation in observed-matched Migration worlds.** This check is specific to
the Migration evidence package and should not be read as a robustness result
for every Phase-Map or mechanism-module estimand.

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
the corresponding three-way interaction is negative. Multiplicity, outcome
ceiling effects, and the failed near-tie manipulation limit stronger inference.
The conditional allocation question for a verified multi-constraint near-tie
therefore remains open.

## 5.11 Supplemental robustness

Alternative service aggregators, the adversarial structural sidecar, complete Stage-5 contrasts, and distributional diagnostics are reported in the supplementary appendix. The sidecar establishes only that all three service channels can be terminal under adversarial structures; it is not treated as a global sensitivity analysis.

# 6. Discussion

## 6.1 Separate outcomes, uneven mechanism identification

The revised evidence changes the causal interpretation of the paper. The original manuscript treated constraint migration as the mechanism linking successful relief to lower indigenous coverage. The data do not support that claim. Migration is common when command or force generation is targeted, but the strongest terminal coverage penalties occur where logistics remains binding. In the Phase Map, migrated worlds with a positive early branch capability gap have a less negative mean terminal coverage contrast than non-migrated worlds. Constraint displacement is therefore not the mediator of the retention penalty.

What survives is more useful because it is more specific. The framework identifies two separate production problems, but the experiments identify them with different strength. Requirement expansion concerns the scale of service demand relative to indigenous production. The Stage-4 telemetry is consistent with that process, but the fresh-seed demand-clamp test does not reproduce the coverage penalty required to test mediation. Constraint displacement concerns the marginal value of improving one complementary service after another becomes limiting and is directly observed in the Migration module. It can produce relief without material whole-force yield and without any negative retention effect.

This distinction connects security-assistance research to established theories without claiming novelty for generic bottleneck logic or donor dependence. Operations management already expects changing constraints [@watson2007]. Development economics already treats expansion as a source of new complementary requirements [@hirschman1958]. Aid research already recognizes recurrent-cost and absorptive-capacity problems [@roodman2006; @arimotokono2009]. The contribution is a military-production formulation that places supported capability, retained capability, service demand, indigenous production, and changing constraints in the same analytic framework, while making explicit what evidence would actually identify each proposed mechanism.

## 6.2 Why the no-aid benchmark matters

The distinction between a dependency gap and a net treatment effect is substantively important. If continued support outperforms withdrawal after 120 days of prior support, the donor is supplying something the withdrawal branch no longer has. That difference may represent valuable ongoing support. It may also reflect deterioration caused by the removal of an externally supported operating system. Without a matched no-aid benchmark, those possibilities cannot be separated.

The Phase Map demonstrates the point. The original frozen branch contrast classified 106 treated cells as having a positive mean +30-day continued-support advantage over withdrawal. The stricter no-aid comparison finds only 26 cells in which supported capability is above no aid while post-withdrawal capability is below no aid. Thirty cells are above no aid in both branches. Fifty-one are below no aid in both. A useful evaluation framework must therefore report at least three quantities: the supported effect relative to no aid, the retained effect relative to no aid, and the gap between continued support and withdrawal.

This also clarifies the meaning of the phrase **Suffering from Success**. It is not a description of every assistance program in the model. It denotes a conditional regime in which support produces a real capability gain but the supported system is not reproduced after withdrawal. The regime is analytically important precisely because it can be distinguished from simple program failure.

## 6.3 Requirement expansion remains a candidate retention mechanism

The post-completion telemetry analysis shows why the indigenous-coverage coordinate must be decomposed. In same-terminal logistics worlds with a negative coverage contrast, the continued-support branch usually faces higher logistics demand, while a smaller share also has lower indigenous delivery. On the log scale, both components matter, and requirement growth contributes slightly more to the average gap than indigenous-service decline. The standardized capped-coverage calculation points in the same direction. These are descriptive decompositions of realized Stage-4 trajectories, not causal mediation estimates.

The prospective demand-clamp experiment was intended to provide the stronger test and does not do so. Its manipulation check passes, and clamping logistics demand materially changes composite capability, especially in the M1 and M2 scenarios. But the fresh-seed normal arms reproduce no indigenous-coverage branch gap at any registered horizon. Because the outcome to be mediated is absent before the clamp is applied, the zero attenuation estimate cannot distinguish "requirement expansion does not matter" from "this fresh-seed ensemble did not enter the Stage-4 retention regime." The direct experiment therefore leaves requirement expansion unconfirmed as a retention mechanism and exposes a new seed-domain robustness problem for the coverage result.

That result does not imply that demand should be held fixed in substantive policy. A larger requirement can be the consequence of more activity, more surviving formations, more territory, or other real operational gains. The point is diagnostic. A falling service-to-demand ratio is not equivalent to destroyed indigenous capacity. It can instead mean that the force has grown into a larger sustainment problem. The policy question then becomes whether indigenous production can catch up with the supported operating requirement, not merely whether the ratio fell.

This is why the paper reports absolute capability alongside coverage and why the final interpretation does not equate a decomposed association with mechanism identification. A donor can improve supported capability, leave indigenous service unchanged or higher, and still create a larger post-support shortfall if the new operating system requires more service than the partner can produce alone. The Stage-4 telemetry contains that pattern, but the prospective fresh-seed test shows that it is not automatically portable across simulated worlds. Conversely, a coverage decline with no supported capability gain is not a success-induced retention problem. It is simply a poor outcome.

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

| Case | Audited constraint sequence | Indigenous replacement | Support-change evidence | Strongest rival explanation | Audited theory fit |
|---|---|---|---|---|---|
| Afghanistan | Aviation maintenance/logistics remained limiting beneath external substitution | Negative or incomplete | Abrupt contractor and U.S. support reduction followed by severe degradation | Political collapse, morale and leadership failure, corruption, strategy, and Taliban adaptation | Strong for substitution/retention; partial for discrete constraint displacement |
| Iraq | Rapid force generation followed by lagging logistics and sustainment | Incomplete in coded 2005-2008 episode | No clean withdrawal shock in coded episode | Sectarian politics, militia penetration, absenteeism, command problems, corruption, and intelligence weakness | Strongest sequential-constraint analogue, with major political confounding |
| Mali | Basic unit skills improved while pre-existing logistics, maintenance, and C2 weaknesses remained | Mixed | No clean support shock in coded 2013-2015 episode | Political fragmentation, provider fragmentation, command weakness, and institutional instability | Partial; strongest for local-system divergence |
| Colombia | Externally enabled aviation expansion initially outran pilots, mechanics, maintenance, and logistics, followed by phased nationalization | Positive and substantial over time | Phased transfer rather than abrupt withdrawal | Stronger institutions, fiscal capacity, political commitment, long duration, and continued external partnership | Strong positive retention case; partial for discrete constraint displacement |

**Table 5. Source-audited historical process evidence under the frozen external-
validation protocol.** The table is a structured plausibility and process test,
not a causal estimate of security-assistance effects. The source audit preserves
mixed and adverse evidence rather than upgrading ambiguous cases to full support.

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
fit the model.

# 8. Limitations

First, Pineland is a synthetic model. The numerical effects reported here are consequences of a specified simulated production system, not empirical treatment effects or historical threshold estimates. The model is useful for mechanism isolation because states can be cloned and assistance components manipulated independently. That same control limits direct external validity.

Second, indigenous coverage is a ratio with an endogenous denominator. The revised paper treats this as a substantive object rather than a hidden assumption, but the ratio still depends on how service demand is represented. The no-aid capability comparison and supply-demand decomposition reduce the risk of mistaking denominator growth for destroyed indigenous capacity. The prospective demand clamp does not validate the denominator mechanism: although the manipulation succeeds, its fresh-seed normal arms do not reproduce the Stage-4 coverage penalty. The simulated demand functions therefore remain a model assumption whose empirical relevance must be established outside this experiment.

Third, the structural coordinate assumes strong complementarity among force generation, logistics, and command. Smooth arithmetic, geometric, and harmonic alternatives show that many Stage-4 sign results are not unique to a hard minimum, but the model still imposes a limited set of military-production relationships. A richer model could allow more substitution among services or additional channels such as maintenance specialization, intelligence, finance, or officer quality.

Fourth, composite capability is itself a modeled construct. It is the geometric mean of five unit-scale retention components: government control, military personnel, operational formations, geographic coverage, and readiness. This measure makes whole-force performance transparent and bounded, but it is not a validated empirical index of combat effectiveness. The paper therefore reports component and service-level results alongside the composite rather than treating one number as ground truth.

Fifth, the no-aid benchmark is a matched simulation trajectory, not an observational estimate. Matching by structure, capacity, seed, and horizon provides a clean model counterfactual, but it does not reproduce the selection processes that determine which historical partners receive assistance. The distinction between supported effect, retained effect, and dependency gap is analytically useful even where a real-world no-aid counterfactual cannot be estimated cleanly.

Sixth, several important revised analyses are post-completion diagnostics. The matched no-aid comparison, supply-demand decomposition, five-horizon synthesis, migration-yield comparison, and capability-retention-cost framing were developed after the Stage-4 production campaign and after external review. They use frozen telemetry and are labeled as exploratory or post-completion rather than retroactively described as prospectively frozen. The demand-clamp experiment is different: its contract, analysis rules, seeds, and code were frozen before its own production outcomes were observed. That stronger design produced an adverse robustness result: the four source cells had negative mean coverage effects on the original Stage-4 seeds, but all 48 fresh-seed normal worlds had zero coverage branch effect at every registered horizon. This seed-domain non-reproduction limits generalization of the Stage-4 retention surface and prevents the clamp experiment from identifying mediation.

Seventh, assistance architectures are stylized. Development changes partner-owned production on a specified cadence, while substitution supplies removable external service. Real institutional development is politically contested, path dependent, and often much slower. The modeled donor-cost ledger is useful for internal tradeoffs but is not a dollar estimate and should not be used for empirical cost-effectiveness rankings.

Eighth, Stage 5 does not cleanly test its intended scope condition. Its nominal near-tie worlds become almost uniformly logistics-bound before the main treatment comparison. The paired factorial contrasts remain valid for the realized states, but the claim that breadth should become more efficient under a verified multi-constraint near-tie remains unresolved.

Ninth, the structural sidecar rejects only a literal hard-coding claim. It demonstrates that command, force generation, and logistics can each be terminal under adversarial structures, but the intended migration paths do not occur. It is not a global sensitivity analysis of the Stage-4 logistics attractor.

Tenth, the historical case analysis is structured external validation rather than causal confirmation. Afghanistan, Iraq, Mali, and Colombia contain political, organizational, strategic, and adversarial dynamics that the synthetic production model does not identify separately. The historical coding therefore preserves rival explanations and mixed evidence rather than treating resemblance to a simulated mechanism as proof.

Finally, the framework concerns production conditional on political decisions. Recipient incentives, command politics, corruption, patronage, donor leverage, coalition management, and adversary adaptation can determine whether a technically feasible development path is ever pursued. Relief, yield, requirement expansion, constraint displacement, and retention are therefore complements to political analysis, not substitutes for it.

# 9. Conclusion

Security assistance should not be evaluated with a single question such as whether a program "worked." The more useful questions are whether it relieved the intended constraint, how much whole-force capability followed, how the operating requirement changed, and how much capability remained after external service stopped.

The revised Pineland evidence shows why those questions must be separated. Continued support often outperforms withdrawal after a shared period of assistance, but that dependency gap is not the same as a net gain over no aid. At +30 days, 26 of 120 treated Phase-Map cells show the strict success-without-retention pattern of supported capability above matched no aid and post-withdrawal capability below matched no aid. Thirty cells improve relative to no aid in both branches, while 51 are below no aid in both. Dependence is therefore a meaningful modeled regime, not the universal result of direct support.

The mechanism evidence is also more specific than the original manuscript claimed. In the Stage-4 telemetry, terminal logistics-coverage gaps reflect both indigenous service and the scale of the operating requirement. Descriptive standardization attributes a larger share of the average gap to requirement differences than to lower indigenous delivery. That pattern is consistent with requirement expansion, but the prospective demand-clamp test does not causally confirm it. The clamp matches the withdrawal requirement closely and materially changes capability, yet its fresh-seed normal arms reproduce no coverage penalty at any horizon. Requirement expansion therefore remains a plausible interpretation of the Stage-4 trajectories rather than an identified cause of the retention gap.

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
its failed fresh-seed coverage replication and zero precommitted attenuation are
reported without redesigning the experiment around the result.
