---
title: "Suffering from Success: Security Assistance, Constraint Migration, and Partner-Force Autonomy"
author: "Alejandro Grenier"
affiliation: "Virginia Tech"
bibliography: references.bib
status: "Review draft"
date: "2026-09-21"
keywords: "security assistance; military effectiveness; partner forces; autonomy; logistics; agent-based modeling"
---

# Abstract

Security assistance can work and still leave a partner unable to reproduce the
capability that assistance helped create. This article separates three outcomes
often treated as one: **constraint relief**, whether assistance fixes the
problem initially limiting a force; **system yield**, how much whole-force
capability that relief unlocks; and **retention**, how much resulting capability
remains indigenously reproducible. Successful assistance can remove one binding
limitation, expand the operating envelope, raise demand for complementary
services, and expose another constraint. The bottleneck logic, recurrent-cost
problem, and distinction between supported and sustainable performance each
have important antecedents in operations management, development economics,
foreign-aid research, and security-assistance scholarship. The contribution is
their dynamic integration in a military production system in which selective
external substitution can itself change the identity of the binding indigenous
service. A prospectively frozen experiment in
the Pineland agent-based model generated 2,808 worlds. Among 106 treated cells
where continued direct assistance increased 30-day capability, 96, or 90.6
percent, had lower indigenous autonomy at 360 days. Targeted support produced
persistent constraint migration in 38 of 38 observed-matched command worlds and
46 of 46 force-generation worlds, but 0 of 85 logistics worlds. Yet migration
did not imply equal system gain: force-generation relief changed the binding
service while producing virtually no short-run composite gain, whereas
logistics support produced larger gains while deepening long-run dependence.
Developmental logistics improved terminal autonomy relative to substitution by
0.132 to 0.433, while substantial indigenous force-generation gains could leave
whole-system autonomy unchanged. A separately frozen 1,472-world follow-up then
tested whether coordinated indigenous development could escape this pattern.
Fixed-budget breadth never significantly outperformed the best included
single-channel intervention and significantly underperformed it in 21 of 32
precommitted comparisons. At equal channel dose, however, two high-intensity
pairwise interactions in the nominal near-tie structure were significantly
positive, while the three-way interaction was significantly negative. The
results therefore support selective complementarity but not a general
"rising-tide" allocation rule. A final 32-world structural sidecar also showed
that command and force generation are dynamically reachable terminal
constraints, rejecting the narrow claim that logistics is hard-coded as the
unique terminal state.

# 1. Introduction

Security assistance occupies an increasingly important place in contemporary
statecraft. States train, equip, advise, fund, and otherwise support foreign
security forces in order to influence conflicts without assuming the full cost
of direct intervention. Yet the record of such efforts is mixed. Existing
research identifies several recurring explanations for disappointing outcomes:
provider-recipient interest misalignment, weak political institutions,
insufficient leverage over recipient leaders, fragmented security sectors,
fragile elite units, poor absorptive capacity, and dependence on external
resources [@biddle2017; @biddle2018; @metz2023; @matisek2018; @knowlesmatisek2019;
@harkness2022; @sandnes2024]. Recent scholarship has pushed further by treating
security assistance as a relational practice that can reshape authority,
alignment, and dependency rather than merely transfer technical capability
[@rolandsen2021; @rolandsen2026]. U.S. government evaluations similarly continue to identify
absorptive capacity and sustainment as recurring weaknesses in train-and-equip
programs [@gao2023].

This literature establishes that security assistance can fail, distort, or
create dependency. A 2026 synthesis makes the novelty boundary especially
clear: contemporary work already treats assistance as a relational practice
that can generate dependency, fragmentation, and dissonance between intention
and outcome [@rolandsen2026]. The contribution here is therefore not another
claim that support can produce dependence. The article instead asks a narrower
question that becomes important precisely when assistance works: **what happens
after a real military constraint is successfully relieved?**

That question also has important antecedents outside security studies. Theory
of Constraints treats whole-system throughput as governed by a binding
constraint and expects successful improvement of that constraint to reveal
another [@watson2007]. Hirschman's theory of unbalanced growth likewise treats
successful expansion in one activity as a source of new shortages and demands
for complementary investment [@hirschman1958]. Foreign-aid scholarship goes
further by showing how donor-financed projects can increase claims on scarce
recipient administrative or recurrent resources [@roodman2006;
@arimotokono2009]. The argument here therefore does not claim bottleneck
migration, complementarity, or aid-induced recurrent requirements as new
general mechanisms. Its proposed contribution is the conjunction of those
ideas in partner-force production: selective external assistance can relieve a
real military constraint, expand feasible operational scale or complexity,
increase demand for a different indigenous service, and thereby widen the gap
between capability available under support and capability reproducible without
it.

Three outcomes must be separated. **Constraint relief** asks whether the
intervention actually fixes the service that limits the force. **System yield**
asks how much additional whole-force capability that relief unlocks before some
other limitation binds. **Retention** asks how much of the resulting capability
the partner can continue to reproduce from indigenous production after
additional donor input stops. These outcomes need not move together. A program
can relieve the intended bottleneck yet produce little system gain because the
next constraint was already close. It can produce a large supported gain yet
leave little retained capacity because the new operating requirement depends on
external service. It can also improve indigenous production substantially in a
single subsystem while leaving whole-system autonomy unchanged because a
different subsystem becomes limiting.

The mechanism linking these outcomes is **constraint migration**. If a partner
force is initially constrained by command, training throughput, or logistics,
successful assistance can raise the level or complexity of operations the force
is capable of attempting. That success changes demand for complementary
services. The old bottleneck can disappear while another service becomes
binding. The paper therefore uses bottleneck migration as a mechanism, not as a
synonym for failure. Whether migration represents major progress or almost no
progress depends in part on **headroom**, the distance between the most binding
service and the next one, and on whether indigenous production grows fast
enough to meet the new demand created by success.

This dynamic creates the possibility captured by the title, **Suffering from
Success**. Assistance can raise current performance and simultaneously make the
resulting military system harder to reproduce independently. The corresponding
autonomy trap occurs when supported capability rises while indigenous coverage
of the adapted system falls. The same logic also identifies a possible escape condition. If indigenous
production rises across the right set of complementary services, the whole
feasible frontier can move outward rather than merely shifting the identity of
the bottleneck. A separately frozen Stage-5 experiment tests that possibility.
Its completed results show that such complementarity is conditional rather than
automatic: some coordinated pairs interact positively, but broad allocation of
a fixed developmental budget does not generally outperform concentrating the
same effort in the best single channel.

The argument is evaluated using Pineland, a partially observed agent-based model
that explicitly represents military personnel, formations, logistics,
readiness, command reliability and latency, external support, force generation,
governance, armed organizations, and territorial competition. The integrated
experiment contains three coordinated modules. First, an Autonomy-Trap Phase
Map varies indigenous capacity and direct support intensity across balanced,
command-constrained, force-generation-constrained, and logistics-constrained
systems. Second, a Bottleneck Migration experiment targets different service
constraints and tracks whether the limiting constraint changes. Third, a
Substitution versus Development experiment compares direct external service
provision with assistance that expands partner-owned production.

Figure 1 summarizes the mechanism conceptually. Figures 2 through 6 are
generated directly from the tracked Stage-4 evidence package; Figure 7 reports
the separately frozen Stage-5 coordinated-development experiment.

The evidence is strongly asymmetric. Of 106 treated Phase-Map cells in which
continued direct assistance improved composite capability at 30 days, 96
produced lower indigenous autonomy at 360 days. Fifty-three cells were robust
autonomy traps under precommitted bootstrap and median criteria; no cell was a
robust autonomy-building case. The average autonomy penalty also became much
larger at high levels of direct support. In the migration experiment, every
observed-matched command and force-generation case migrated persistently away
from its starting constraint, while no observed-matched logistics case did.
Both command and force-generation relief overwhelmingly exposed logistics as
the next binding constraint. In the treatment-mode experiment, developmental
logistics assistance substantially outperformed direct substitution on terminal
autonomy, but force-generation development could create large indigenous gains
without improving whole-system autonomy because logistics had become binding.

The paper makes one primary theoretical contribution and three related
measurement contributions. The theoretical contribution is a dynamic theory of
military production under external substitution: assistance can succeed on its
proximate task and still create a new autonomy problem because success changes
the production requirement. The measurement contributions separate
**constraint relief, system yield, and retention**; distinguish **supported
capability** from **independently reproducible capability** at the same point in
time; and distinguish local indigenous output from whole-system autonomy. These
claims are intentionally narrower than a general theory of dependency or
bottlenecks.

The argument is not that politics ceases to matter once military production is
modeled. Recipient incentives, donor leverage, organizational design, and
political institutions determine whether reforms occur and how assistance is
used. The constraint-migration mechanism is conditional on changes in military
service production actually taking place. It therefore complements rather than
displaces agency and influence theories of security assistance.

The article is deliberately limited in one important respect. The experiments
establish causal relationships inside a synthetic model. They do not estimate
historical treatment effects or identify empirical threshold values for
Afghanistan, Iraq, Mali, or another real partner force. Historical evidence is therefore treated as a separate external-validation
exercise rather than as retrospective confirmation of the simulation.

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
lie in the mechanism producing divergence between supported and autonomous
capability, not in noticing that such divergence can exist.

Policy and evaluation literatures make a related point in the language of
absorptive capacity and sustainment. RAND research on defense institution
building stresses the organizational and institutional foundations required to
convert external assistance into durable partner capability [@mcnerney2016].
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
dependency. That point is well established. The unresolved theoretical problem
is how dependency changes as assistance succeeds, indigenous production
changes, and the force's limiting constraint moves.

It is also useful to separate three forms of dependence that are often collapsed
into one label. **Operational dependence** means that a specified military
output cannot be generated without continuing foreign service or input
provision. **Institutional dependence** means that external provision weakens
or displaces the development of indigenous organizations. **Relational
dependence** means that reliance on an external actor creates asymmetric
bargaining power. The mechanism tested here is fundamentally operational. It
can coexist with the institutional and relational forms, but does not require
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
reduce the return to excellence elsewhere [@kremer1993], while military
effectiveness research has long treated armed forces as complex organizations
whose aggregate performance cannot be inferred from isolated attributes
[@millett1986]. Military logistics scholarship likewise demonstrates that
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
autonomy. The empirical burden here is to show a different sequence: the
assisted function improves, operations expand or change, a complementary service
requirement rises, and that service then becomes limiting.

## 2.4 From static capacity to a moving constraint

Military capability is jointly produced. Personnel without logistics cannot
operate. Logistics without command cannot reliably translate resources into
coordinated action. Command without force generation cannot replace losses or
expand the force. If these functions are complements, the effective capacity of
the whole system depends disproportionately on the service channel with the
lowest indigenous coverage of demand.

The missing dynamic is that assistance changes the system it evaluates. If
external logistics allows a force to conduct more operations, logistics demand
can rise. If training increases available personnel, sustainment demand can
rise. If command assistance increases coordination, the force may begin to use
personnel and supplies at a level that reveals a different shortage. The
binding constraint is therefore endogenous to assistance.

The resulting novelty claim is deliberately conjunctive. No individual link is
new. The candidate contribution is a security-assistance theory that jointly
specifies **selective external substitution, successful relief of a binding
military-production constraint, endogenous expansion of operational
requirements, migration of the binding constraint into another indigenous
service, and divergence between supported and independently reproducible
capability**.

# 3. Theory

## 3.1 Indigenous autonomy as service coverage

The theory begins by distinguishing the capability a force can generate with
external support from the capability it can reproduce from indigenous
production alone. Let an operation of scale or complexity \(x\) require
service \(j\) in quantity \(r_j(x)\). Let \(I_{j,t}\) denote indigenous
production and \(E_{j,t}\) external provision. Supported feasible capability is

\[
C_t^{S}=\max x
\quad\text{s.t.}\quad
r_j(x)\leq I_{j,t}+E_{j,t}
\quad \forall j,
\]

while independently reproducible capability is

\[
C_t^{A}=\max x
\quad\text{s.t.}\quad
r_j(x)\leq I_{j,t}
\quad \forall j.
\]

These are simultaneous state variables, not merely current success and future
sustainability. Assistance can therefore produce

\[
\frac{dC^{S}}{dA}>0
\quad\text{while}\quad
\frac{dC^{A}}{dA}\approx 0,
\]

or a widening capability gap

\[
\frac{d(C^{S}-C^{A})}{dA}>0.
\]

The model operationalizes this production logic through service coverage.

Let a partner force require a set of military services indexed by (j). For
service (j) at time (t), let (D_{j,t}) denote demand, (I_{j,t}) denote
indigenous service production, and (E_{j,t}) denote external service. Define
indigenous coverage as

\[
q_{j,t}^{I}=\frac{I_{j,t}}{D_{j,t}}
\]

for active channels with positive demand, and supported coverage as

\[
q_{j,t}^{S}=\frac{I_{j,t}+E_{j,t}}{D_{j,t}}.
\]

The structural indigenous-autonomy coordinate is

\[
q_t^{I}=\min_j q_{j,t}^{I},
\]

with capped feasible autonomy

\[
A_t=\min(q_t^{I},1).
\]

The minimum is a formal expression of complementarity: the system cannot be
fully autonomous if any required service remains below demand. Because a hard
minimum can mechanically emphasize one channel, the empirical analysis also
uses arithmetic, geometric, and harmonic feasibility aggregators as robustness
checks.

The observed binding constraint is

\[
B_t=\arg\min_j q_{j,t}^{I}.
\]

This definition converts a static idea of "capacity" into a dynamic production
problem. The relevant unit is not the amount of any one military input. It is
indigenous coverage of the service that limits the whole system at time (t).

## 3.2 Relief, yield, and retention

Assistance should not be evaluated as a single binary success or failure. Three
distinct outcomes matter.

**Constraint relief** asks whether the targeted limitation actually ceases to
bind. If the initial bottleneck is service (j), relief occurs when intervention
raises its effective coverage enough that another service becomes at least as
restrictive.

**System yield** asks how much whole-system capability is unlocked by that
relief. A bottleneck can move after a very small gain if the next service was
already almost equally restrictive. Let the ordered indigenous service coverage
levels at time (t) be

\[
q_{(1),t}^{I} \leq q_{(2),t}^{I} \leq \cdots \leq q_{(J),t}^{I}.
\]

Define the initial **static headroom** above the binding service as

\[
H_t=q_{(2),t}^{I}-q_{(1),t}^{I}.
\]

Holding all other services and demands fixed, headroom approximates the maximum
immediate whole-system gain available from improving only the currently binding
service before the second constraint takes over. It is a structural diagnostic,
not a fixed treatment-effect bound, because real interventions can also change
demand, service interactions, and the ordering of constraints.

**Retention** asks how much of the resulting gain remains reproducible from
partner-owned production once additional donor-driven growth or substitution
stops. Relief without yield means the intervention changed the identity of the
problem without materially improving the force. Yield without retention means
the intervention created useful capability that remains dependent on external
production. Durable capacity building requires improvement on all three
dimensions.

This distinction prevents a common interpretive error. Bottleneck migration is
evidence that the system changed. It is not, by itself, evidence that the system
improved substantially or that the improvement became autonomous.

## 3.3 The autonomy trap and constraint migration

Suppose external assistance raises supported capability by supplying service at
the current bottleneck. If the partner's indigenous production does not expand
at the same pace as the supported operating requirement, then supported
capability can rise while indigenous autonomy falls.

For any service with positive demand before and after an intervention, the
channel-level autonomy condition is exact:

\[
\frac{I_{j,0}}{D_{j,0}} < \frac{I_{j,1}}{D_{j,1}}
\quad \Longleftrightarrow \quad
I_{j,0}D_{j,1} < I_{j,1}D_{j,0}.
\]

This equivalence is formally verified in the model's Lean theory layer. It
states that indigenous coverage improves only when indigenous service growth
outruns growth in the corresponding service requirement. In proportional terms,
the autonomy-eroding case is

\[
\frac{\Delta I_{B,t}}{I_{B,t}} <
\frac{\Delta D_{B,t}}{D_{B,t}},
\]

where (B) denotes the relevant binding service. Indigenous coverage can
therefore decline even while indigenous service increases in absolute terms.
Assistance can enlarge both the numerator and the denominator of the capacity
problem.

Successful assistance can also eliminate the constraint that initially
justified intervention. If service (j) binds at time (t), but assistance raises
its effective coverage, another service (k) can become the minimum:

\[
B_t=j \quad \rightarrow \quad B_{t+h}=k.
\]

This is constraint migration. Migration is most consequential when relief opens
substantial headroom and the expanded operating envelope then increases demand
on the newly binding service. It can be nearly inconsequential when the first
and second constraints are already close.

**Proposition 1, Autonomy Trap.** External assistance can increase near-term
operational capability while decreasing later indigenous autonomy when the
supported operating requirement grows faster than indigenous production at the
binding constraint.

**Proposition 2, Intensity Effect.** Conditional on a substitutive assistance
architecture, larger external support can deepen the autonomy penalty when it
raises the supported operating envelope faster than it induces indigenous
replacement.

**Proposition 3, Constraint Migration.** Assistance that successfully relieves a
nonterminal binding constraint increases the probability that a different
service becomes the limiting constraint of the partner force.

The intensity proposition is conditional rather than globally monotonic, and
the migration proposition makes no claim that every migrated bottleneck implies
the same amount of system gain.

## 3.4 Substitution, development, and coordinated growth

Direct substitution supplies (E). Developmental assistance instead seeks to
raise the partner's own production function, increasing (I). These approaches
can generate similar near-term supported capability while producing very
different retention.

If development targets the service that remains binding, it should increase the
partner's coverage of demand and therefore improve whole-system autonomy
relative to substitution. If it targets a transient bottleneck, its local effect
may be large while its system effect remains small.

**Proposition 4, Development at the Binding Constraint.** Developmental
assistance should outperform direct substitution on terminal autonomy when it
increases indigenous production at a service that remains system-binding.

**Proposition 5, Local-System Divergence.** Developmental assistance can produce
large indigenous gains in a targeted subsystem without increasing whole-system
autonomy when successful development causes another service to become binding.

The same complementarity that creates local-system divergence also implies a
possible positive case. If several services are jointly or nearly binding,
developing them together may raise the minimum more than developing any one in
isolation. For two services, the system-level complementarity of coordinated
development can be represented by the factorial interaction

\[
I_{AB}=Q_{AB}-Q_A-Q_B+Q_0,
\]

where (Q) is terminal whole-system indigenous feasibility. A positive
(I_{AB}) means the combined intervention yields more autonomy than the additive
effects of the two single-service interventions. This rising-tide implication
is not inferred from Stage 4. It is tested prospectively in the separately
frozen Stage-5 experiment described below.

![Figure 1. Assistance should be evaluated as constraint relief, system yield,
and retention. Constraint migration links these outcomes by changing which
service limits the adapted force. Static headroom describes initial constraint
spacing but does not determine realized dynamic yield by itself.](figures/figure1_conceptual.png)

## 3.5 Falsifiable implications and scope conditions

The theory does not predict that every successful assistance program must
produce migration, dependence, or declining autonomy. It is weakened when a
binding service is repeatedly relieved, operating demands rise, and no new
constraint appears; when indigenous production consistently keeps pace with the
new requirement; or when improvements in a clearly nonbinding subsystem continue
to generate large whole-system autonomy gains.

The coordinated-development extension adds two sharper tests. Positive technical
complementarity requires multi-channel development to outperform the additive
expectation at equal channel dose. A fixed-budget allocation advantage requires
broader development to outperform the best included single-channel intervention
when total effort is held constant. Finally, nothing in the general theory
requires logistics to be terminal. A structural environment in which command or
force generation remains terminal would narrow the logistics-specific Stage-4
interpretation without contradicting the broader constraint-migration mechanism.

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
foreign assistance. The partner-force layer tracks three formally comparable
service channels that are central to the present paper: force generation,
logistics, and command. For each channel the model records service demand,
indigenous service, and removable external service.

Force-generation service is tied to replacement and training output. Logistics
service represents indigenous sustainment production and external delivery.
Command service combines command opportunities with indigenous reliability and
latency, with advisory assistance represented as a removable supported-service
overlay. The formal service adapter is separately specified in Lean and the
production runtime is tested against the same nonnegativity and feasibility
semantics.

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
| Autonomy-Trap Phase Map | 140 | 12 | 1,680 | Vary starting structure, indigenous capacity, and direct support intensity |
| Bottleneck Migration | 52 | 12 | 624 | Target observed and nominal constraints and track persistent migration |
| Substitution vs Development | 42 | 12 | 504 | Compare no aid, direct substitution, indigenous development, and hybrid assistance |
| **Total** | **234** | **12** | **2,808** | Integrated test of phenomenon, dynamics, and mechanism |

**Table 1. Integrated Stage-4 experimental design.** Each production world uses
one frozen seed within a precommitted cell. The three modules separate the
existence of the autonomy trap, the dynamics of constraint migration, and the
mechanism-level contrast between substitution and indigenous development.

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

The primary paper-level estimands were fixed before Stage-4 production
completed. The early operational effect is the continued-support minus
withdrawal difference in composite capability at +30 days. The terminal
autonomy effect is the corresponding difference in capped indigenous autonomy
at +360 days.

With epsilon (10^{-6}), an **effective autonomy trap** is a world or cell with
a positive early operational effect and a negative terminal autonomy effect. An
**effective autonomy-building** case has positive effects on both. Cell-level
robust classification additionally requires the corresponding 95 percent
bootstrap interval to exclude zero and the median to have the same sign as the
mean.

Cell summaries report means, medians, 10th and 90th percentiles, and directional
seed fractions because prior experiments showed material heavy-tail behavior.
Mean uncertainty is estimated with a deterministic 10,000-resample percentile
bootstrap using frozen seed 20260920. Proportions use Wilson 95 percent
intervals. No world is removed as an outlier and no primary result is
winsorized.

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

Postprocessing repairs were isolated from production. The final accepted
production commit is `e369c107f4465ce8cd385a366cafca8c28c04b65`; the final
postprocessing commit is `7697e6eac83248c7bc03830e58d94a2d878c6635`; and the
precommitted paper-analysis commit is
`9b0e975c7e4073f2f5abd94e72cd125beb75f20d`.

## 4.6 Proposition-to-test correspondence

The three modules were designed to separate the existence of the autonomy trap
from the mechanism that produces it. Proposition 1 is tested in the Phase Map
by the joint sign of the +30-day capability effect and +360-day indigenous
autonomy effect. Proposition 2 is evaluated as a conditional intensity pattern,
not as a claim of global monotonicity. Proposition 3 is tested in the Migration
module using the frozen persistent-migration definition and the observed
pre-withdrawal bottleneck. Propositions 4 and 5 are tested in the mechanism
module through matched development-minus-substitution contrasts and the
relationship between targeted indigenous output and whole-system autonomy.

This separation matters for inference. A Phase-Map autonomy trap establishes
that supported capability and indigenous autonomy can diverge. It does not by
itself identify bottleneck migration as the cause. The Migration and mechanism
modules provide the stronger tests of the moving-constraint explanation.

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
precommitted analyses therefore estimate retained autonomy and capability gains,
pairwise and three-way factorial interactions, equal-total-effort breadth
premiums, and bottleneck dynamics.

The Stage-5 protocol, contract, analysis code, execution wrappers, and inherited
scientific foundation were cryptographically frozen before any Stage-5 production
outcome was observed at repository commit
`8d342c982e385699e76c766ec06ae991bc451876`. The campaign completed all 1,472
worlds and the frozen postprocessing pipeline produced a READY manifest tying
production and analysis to that same commit.

A manipulation check is essential for interpretation. The nominal multiplier
structures do not always remain the observed formal bottleneck after the common
120-day developmental prehistory. At the split, logistics is the observed
bottleneck in all 368 nominal force-generation-constrained worlds, all 368
logistics-constrained worlds, and 365 of 368 nominal near-tie worlds. The nominal
command-constrained structure preserves command as the split-point bottleneck in
100 of 368 worlds and logistics in the remainder. Stage-5 structure labels are
therefore reported as **nominal design factors**, not as validated observed
bottleneck identities. This weakens any causal interpretation of the preregistered
headroom scope-condition test while leaving the randomized paired treatment
contrasts themselves intact.

# 5. Results

## 5.1 Effective direct support usually reduces terminal autonomy

The Phase Map contains 120 treated cells and 20 zero-support controls. Of the
120 treated cells, 106 had a positive mean composite-capability effect at +30
days. Ninety-six of those 106 effective cells were autonomy traps at +360 days:

\[
96/106=0.9057.
\]

Only 10 effective cells had a positive mean terminal-autonomy effect. None met
the precommitted robust autonomy-building criterion. By contrast, 53 cells met
the robust autonomy-trap criterion.

This asymmetry appears across most starting structures. All 30 effective
force-generation-constrained cells were traps. All 20 effective
logistics-constrained cells were traps. Twenty-nine of 30 effective balanced
cells were traps. Command-constrained systems generated the only substantial
set of positive-mean islands, with nine descriptive building cells, but these
positive regions were statistically unstable and none was robust.

The result is therefore not a clean phase boundary separating large positive
and negative regions under direct substitution. The dominant surface is
autonomy-eroding, with narrow uncertain positive islands in command-constrained
systems.

![Figure 2. Autonomy effects across the Phase Map. Cell shading reports the
mean continued-support minus withdrawal effect on capped indigenous autonomy at
+360 days. T denotes a robust autonomy trap, + denotes a descriptive
autonomy-building cell, and x denotes a cell without a positive mean +30-day
capability effect.](figures/figure2_phase_map.png)

## 5.2 The autonomy penalty generally increases with direct-support intensity

Aggregating across starting structures and capacity levels reveals a strong
intensity pattern. At 0.25 times support, the mean cell-level +30-day capability
effect was approximately +0.0061 and the mean +360-day autonomy effect was
-0.0250. At 2 times support, the corresponding effects were approximately
+0.0334 and -0.1323. Thus the average terminal autonomy penalty at the highest
tested intensity was about 5.3 times the penalty at the lowest positive
intensity.

At 2 times support, 18 of 20 cells were initially effective. All 18 were
autonomy traps and 15 met the robust trap criterion. No cell at that intensity
had a positive mean autonomy effect.

This relationship is not perfectly monotonic at every intermediate level, and
the preregistered analysis does not impose a global monotonic boundary. The
substantive pattern is nevertheless clear: larger direct-support packages
produce positive short-run capability effects while the average long-run
indigenous-autonomy effect becomes increasingly negative.

![Figure 3. Mean +30-day capability and +360-day indigenous-autonomy effects by
direct support intensity, averaged across treated Phase-Map cells.](figures/figure3_intensity_tradeoff.png)

## 5.3 Nominal weakness is a poor proxy for the observed bottleneck

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

## 5.4 Constraint migration and system yield are not the same outcome

The dedicated Migration module provides the strongest direct evidence for the
moving-constraint mechanism. Among worlds where the treatment target matched
the observed pre-withdrawal bottleneck, command and force generation behaved
very differently from logistics.

When command assistance matched an observed command bottleneck, 38 of 38 worlds
experienced persistent migration. The Wilson 95 percent interval for the
migration probability is approximately 90.8 to 100 percent. Median detected
migration time was seven days. All 38 had logistics as the modal post-support
bottleneck.

When force-generation assistance matched an observed force-generation
bottleneck, 46 of 46 worlds migrated persistently. The corresponding Wilson 95
percent interval is approximately 92.3 to 100 percent, and the median detected
migration time was again seven days. All 46 had logistics as the modal
post-support bottleneck.

Matched logistics cases produced the opposite result. None of 85 worlds
migrated persistently. The Wilson 95 percent upper bound on the migration rate
is approximately 4.3 percent. Continued logistics support improved +30-day
capability on average by approximately +0.0170, but reduced terminal indigenous
autonomy by approximately -0.2215.

The intensity pattern within matched logistics cases is particularly stark.
Mean terminal autonomy effects were approximately -0.149 at 0.5 times support,
-0.202 at 1.0 times support, and -0.320 at 1.5 times support, while the mean
+30-day capability effect rose from about +0.0084 to +0.0260.

These results reject a simplistic statement that relieving any bottleneck must
cause migration. In the tested architecture, command and force generation are
readily displaced constraints. Logistics is much more persistent.

They also reject the opposite simplification that migration necessarily means a
large material improvement. A post-completion descriptive aggregation of the
precommitted observed-matched cell summaries shows sharply different system
yields across the three targets. Matched command relief migrated in 38 of 38
worlds and produced an average +30-day composite-capability effect of about
+0.00354. Its average +360-day indigenous-autonomy effect was about +0.0555.
Matched force-generation relief migrated in 46 of 46 worlds, yet its average
+30-day composite-capability effect was approximately +0.00000021 and its
average +360-day autonomy effect was exactly zero at the reported precision.
The intervention changed which service bound the system without materially
raising the composite outcome. By contrast, matched logistics support produced
the largest mean +30-day gain of the three groups, about +0.0170, even though
the logistics constraint did not migrate and the +360-day autonomy effect was
strongly negative.

| Observed-matched target | Persistent migration | Mean +30d capability effect | Mean +360d indigenous-autonomy effect |
|---|---:|---:|---:|
| Command | 38/38 | +0.00354 | +0.0555 |
| Force generation | 46/46 | approximately 0.00000021 | 0.0000 |
| Logistics | 0/85 | +0.01699 | -0.2215 |

**Table 2. Relief, migration, system yield, and terminal autonomy in
observed-matched Migration worlds.** The weighted means are a post-completion
descriptive synthesis of frozen cell summaries. They were not themselves a
precommitted primary estimand.

The distinction is central to the theory. Moving from one bottleneck to another
can represent large progress when substantial headroom is unlocked, or almost
no progress when the next constraint was already close. Conversely, failure of
the bottleneck to migrate does not imply failure of the intervention to raise
supported capability. Relief, yield, migration, and retention must therefore be
reported separately.

![Figure 4. Persistent bottleneck migration among treatments that matched the
observed pre-withdrawal constraint.](figures/figure4_matched_migration.png)

## 5.5 Developmental logistics sharply outperforms direct substitution

The Substitution versus Development module identifies the clearest mechanism
contrast. Direct logistics substitution is strongly autonomy-eroding at +360
days. Developmental logistics assistance remains slightly negative in absolute
terms in the tested cells, but it reduces the autonomy penalty dramatically.

For moderate logistics weakness at intensity 0.5, development improves terminal
autonomy relative to substitution by approximately +0.1316, with a 95 percent
bootstrap interval of +0.1245 to +0.1398. At moderate weakness and intensity
1.0, the contrast is approximately +0.1853 [0.1236, 0.2398]. At severe weakness
and intensity 0.5, it is approximately +0.2542 [0.2388, 0.2687]. At severe
weakness and intensity 1.0, it reaches approximately +0.4328 [0.4169, 0.4516].

All four bootstrap intervals exclude zero. Expressed as attenuation of the
absolute autonomy penalty, developmental logistics reduces the harm associated
with direct substitution by approximately 76 to 94 percent across the four
cells.

The indigenous-production mechanism is also visible directly. Relative to
substitution, developmental logistics generates approximately +172,859 to
+1,249,115 additional units of indigenous cumulative logistics service across
the tested conditions. Capped indigenous coverage of cumulative logistics
demand improves by approximately +0.114 to +0.411.

Development is therefore not simply another route to the same supported
capability. It changes who produces the service needed to sustain the force.

![Figure 5. Matched treatment-mode contrasts on +360-day capped indigenous
autonomy. Points show mean development-minus-substitution or
hybrid-minus-substitution effects; bars show frozen 95 percent bootstrap
intervals.](figures/figure5_mode_contrasts.png)

## 5.6 Local development does not guarantee system autonomy

Force generation provides a clean test of Proposition 5. Developmental
force-generation assistance produces large indigenous gains relative to direct
substitution. The matched development-minus-substitution contrasts in cumulative
indigenous force-generation output range from approximately +121 to +674 across
the four severity and intensity conditions, with narrow bootstrap intervals.

Yet the corresponding whole-system terminal-autonomy contrast is exactly zero
in all four cells. By +360 days, every force-generation-targeted world in the
mechanism experiment is logistics-bottlenecked. The intervention succeeds in
the subsystem it targets, but the targeted subsystem no longer limits the
system.

Command development generates the same logic in a less uniform form. It raises
indigenous command service and coverage, but command-development worlds migrate
away from command as the binding constraint, overwhelmingly toward logistics.
In the moderate-weakness, high-intensity condition, development produces a
terminal system-autonomy contrast of approximately -0.132 relative to
substitution, with a bootstrap interval of about -0.231 to -0.046, despite
improving the indigenous command subsystem.

The result should not be read as evidence that command development is generally
harmful. It shows that improving a nonbinding or transient capacity can have a
low system return. Once another service binds, further improvements in the
relieved subsystem cannot raise whole-system feasibility by themselves.

![Figure 6. Indigenous coverage gains in the targeted subsystem versus
whole-system terminal-autonomy gains for development relative to substitution.
Force-generation cases illustrate that large local gains can coexist with zero
system-autonomy gain.](figures/figure6_local_system_divergence.png)

## 5.7 Integrated evidence across the three modules

The modules converge on a single mechanism but contribute different forms of
evidence. The Phase Map establishes the capability-autonomy divergence, the
Migration module identifies the changing constraint, and the mechanism module
shows when indigenous development does and does not translate into system
autonomy.

| Result | Estimate | Inference status |
|---|---:|---|
| Initially effective treated Phase-Map cells with lower terminal autonomy | 96/106, 90.6% | Precommitted sign classification |
| Robust autonomy traps | 53 cells | Precommitted bootstrap and median rule |
| Robust autonomy-building cells | 0 cells | Precommitted bootstrap and median rule |
| Observed-matched command cases with persistent migration | 38/38 | Wilson 95% interval approximately 90.8% to 100%; median detection 7 days |
| Observed-matched force-generation cases with persistent migration | 46/46 | Wilson 95% interval approximately 92.3% to 100%; median detection 7 days |
| Observed-matched logistics cases with persistent migration | 0/85 | Wilson 95% upper bound approximately 4.3% |
| Logistics development minus substitution on terminal autonomy | +0.1316 to +0.4328 | All four matched bootstrap intervals exclude zero |
| Force-generation development minus substitution on whole-system autonomy | 0 in all four cells | Targeted indigenous output still rises by approximately +121 to +674 |

**Table 3. Headline evidence from the integrated Stage-4 experiment.** Numerical
values are synthetic-model effects. The table does not convert them into
historical treatment-effect estimates.

The constraint-migration result is also highly insensitive to replacing the hard
minimum autonomy coordinate with smooth service aggregators in the Migration
module. Across the 169 worlds in which the assistance target matched the
observed pre-withdrawal bottleneck, the sign of the +360-day autonomy effect
agrees between the hard-minimum measure and each of the arithmetic, geometric,
and harmonic smooth measures in 167 worlds, or 98.8 percent. The two discordant
worlds are one command-targeted world and one logistics-targeted world.

| Observed-matched target | Worlds | Hard minimum vs arithmetic | Hard minimum vs geometric | Hard minimum vs harmonic |
|---|---:|---:|---:|---:|
| Command | 38 | 37/38, 97.4% | 37/38, 97.4% | 37/38, 97.4% |
| Force generation | 46 | 46/46, 100% | 46/46, 100% | 46/46, 100% |
| Logistics | 85 | 84/85, 98.8% | 84/85, 98.8% | 84/85, 98.8% |
| **Total** | **169** | **167/169, 98.8%** | **167/169, 98.8%** | **167/169, 98.8%** |

**Table 4. Sign robustness of terminal-autonomy effects to smooth feasibility
aggregation in observed-matched Migration worlds.** This check is specific to
the Migration evidence package and should not be read as a robustness result
for every Phase-Map or mechanism-module estimand.

## 5.8 Coordinated development produces selective complementarity, not a general rising tide

The prospectively frozen Stage-5 experiment does not support the simple claim
that broader indigenous development is generally more efficient. Under the
**equal-total-effort** regime, broader development never produced a positive
breadth premium whose 95 percent paired bootstrap interval excluded zero in any
of the 32 preregistered structure-by-intensity-by-subset comparisons. Twenty-one
of the 32 comparisons significantly favored concentration in the best included
single channel. Averaged across the eight breadth comparisons within each nominal
structure, mean breadth premiums were -0.0459 for command-constrained, -0.1257
for force-generation-constrained, -0.0432 for logistics-constrained, and -0.0760
for the near-tie structure.

This is a direct rejection of the strongest "rising tide" allocation claim. When
total developmental effort is fixed, dividing it across more channels usually
reduces retained whole-system autonomy relative to concentrating the same effort
in the best included single service. The result is especially strong in nominal
force-generation- and logistics-constrained structures, where six of eight and
eight of eight breadth comparisons, respectively, have bootstrap intervals
strictly below zero.

The **equal-channel-dose** regime tells a more qualified story. Most pairwise and
three-way factorial interactions are small and statistically compatible with
zero. Two interactions are significantly positive, both in the nominal near-tie
structure at intensity 1.0: force generation plus logistics has a mean interaction
of +0.0247 with a 95 percent bootstrap interval of +0.0007 to +0.0539, and
logistics plus command has a mean interaction of +0.1717 with an interval of
+0.0609 to +0.2922. The corresponding three-way interaction is significantly
negative, -0.0561 with a 95 percent interval of -0.0989 to -0.0157. No dominant-
bottleneck structure has a significantly positive factorial interaction.

The Stage-5 hypotheses therefore receive differentiated support. **H_D1 receives
conditional support**: positive pairwise complementarity exists, but only in two
high-intensity near-tie comparisons. **H_D2 is not supported**: no fixed-budget
breadth premium is significantly positive. **H_D3 is not cleanly supported**:
the only significantly positive interactions occur in the nominal near-tie
structure, but the split-point manipulation check shows that those worlds are
almost uniformly logistics-bottlenecked by the time treatment retention is
measured. **H_D4 is not supported**: broader development does not systematically
reduce bottleneck change, and logistics remains the modal +360-day bottleneck in
all nominal force-generation, logistics, and near-tie structures.

These results sharpen rather than reverse the Stage-4 conclusion. Complementary
indigenous development can matter, and some pairs display genuine superadditive
retention effects when each receives a full dose. But complementarity does not
imply that a donor should spread a fixed development budget broadly. The relevant
policy distinction is between **joint technical complementarity** and **allocation
efficiency under scarcity**. Stage 5 finds evidence for the former in a narrow
set of conditions and rejects a general version of the latter.

![Figure 7. Stage-5 coordinated-development results. The left panel summarizes
mean equal-total-effort breadth premiums by nominal starting structure; all are
negative on average and no preregistered breadth comparison has a positive 95
percent interval. The right panel shows the high-intensity near-tie factorial
interactions, including two positive pairwise interactions and a negative
three-way interaction.](figures/figure7_stage5_complementarity.png)

## 5.9 Structural falsification rejects a uniquely hard-coded logistics terminal state

Stage 4 and Stage 5 both make logistics unusually persistent, raising the
possibility that the result is an architectural artifact rather than a property
of the tested parameter domain. A separate post-Stage-4 structural sidecar was
therefore frozen before outcome observation at commit
`4ffe67de2b4a55919e22048467527e01e76934df`. It contains four deliberately
adversarial structures and eight common-random-number seeds per structure, for 32
worlds. Two structures make logistics highly abundant while weakening either
force generation or command; two place logistics below an intentionally strong
alternative channel and apply the Stage-4 high developmental logistics dose.

All 32 jobs completed from the frozen commit with the same production-binary hash
used by the Stage-5 build. Twenty-four worlds matched their nominal pre-relief
constraint. Among those matched worlds, eight terminate at +30 days with command
as the formal bottleneck, eight with force generation, and eight with logistics.
The prospectively frozen narrow rejection rule is therefore satisfied: command
and force generation are dynamically reachable terminal constraints, so
logistics is **not hard-coded as the unique terminal state**.

The sidecar does not show that the four intended migration paths occurred. In the
force-generation-to-command design, all eight matched worlds remained
force-generation-bound; in the command-to-force-generation design, all eight
remained command-bound; and the matched logistics-development worlds remained
logistics-bound. The defensible conclusion is consequently narrow. The formal
architecture permits all three services to be terminal, which weakens the
strongest coding-artifact objection. It does not establish that Stage-4's
specific migration-to-logistics pattern would reverse under nearby plausible
parameter changes.

# 6. Discussion

## 6.1 What the results add to security-assistance theory

The findings refine, rather than replace, existing explanations of security
assistance. Interest misalignment, political incentives, weak institutions,
fragmented security sectors, and donor-recipient dependence remain central
problems [@biddle2018; @metz2023; @harkness2022; @sandnes2024]. The present
results identify a production dynamic that can operate even when assistance
does what donors intend at the targeted military function.

The literature review also narrows the paper's novelty claim. Bottleneck
migration is established in operations management [@watson2007]. Successful
expansion generating new complementary shortages is central to Hirschman's
unbalanced-growth logic [@hirschman1958]. Donor-financed activity creating
recipient-side recurrent or administrative requirements is established in aid
research [@roodman2006; @arimotokono2009]. Security-assistance scholarship
already distinguishes current performance from sustainability or autonomy
[@karlin2018; @sandnes2024; @reynolds2025]. None of those propositions should be
presented individually as the paper's discovery.

What the Stage-4 results add is evidence for their interaction inside a
military production system. Selective external support can remove an actual
constraint, change what the force is capable of doing, alter the demand placed
on complementary services, and thereby change which indigenous service limits
the adapted force. This creates a specific reason why supported capability and
independently reproducible capability can diverge even when the original
assistance succeeds. The novelty is therefore the causal sequence and the
donor-recipient production boundary, not the existence of bottlenecks or
dependency in the abstract.

The central distinction is no longer simply between "assistance" and
"dependence." It is between three stages of success. A donor can relieve the
problem it intended to solve, obtain little or substantial system-level yield,
and then retain little or much of that gain in indigenous production. The
Stage-4 experiments demonstrate that those stages can separate sharply. Force
generation provides the clearest example: treatment can change the binding
constraint almost immediately while producing virtually no composite-capability
gain because another service takes over. Logistics shows the reverse pattern:
supported capability rises materially even though the bottleneck does not move,
while long-run indigenous autonomy falls.

This produces a recursive view of partner-force development:

\[
B_t \rightarrow \text{assistance} \rightarrow \text{relief} \rightarrow
\text{yield} \rightarrow \text{system adaptation} \rightarrow B_{t+h}
\rightarrow \text{retention}.
\]

The central object of analysis is therefore not a static inventory of military
capabilities. It is the evolving relationship among service coverage, the
distance to the next constraint, the operating demand enabled by assistance,
and the indigenous production needed to sustain the adapted force.

## 6.2 Why supported capability can be a misleading success metric

Supported capability is not an invalid outcome. A donor may rationally value
what a partner can accomplish while assistance is present. The problem is using
that metric as evidence of autonomous capacity. The Phase Map shows that these
two outcomes can move in opposite directions systematically.

This distinction also clarifies the relationship between absorptive capacity
and sustainment. A force may be able to absorb enough external support to
operate at a higher level while remaining unable to produce the recurrent
services that the higher operating level requires. In that sense, the autonomy
trap is not merely a shortage of maintenance or funding. It is a mismatch
between the supported operating envelope and the indigenous production system.

The same logic also clarifies why conventional output metrics can overstate the
value of a successful program. More trained personnel, more reliable command,
or more delivered logistics are meaningful local achievements. Their marginal
system value depends on whether the improved service still limits the force.
Once another function binds, additional gains in the relieved subsystem can be
real and measurable while adding almost nothing to whole-system autonomous
capability.

## 6.3 Headroom describes static constraint spacing, not realized yield by itself

The migration result should not be interpreted as a claim that a force returns
to square one whenever the bottleneck moves. If the original bottleneck lies
far below the next constraint, relieving it can unlock a large amount of system
capability before the second service becomes limiting. If the first two
constraints are almost tied, the same successful intervention can change the
identity of the bottleneck while barely moving the system outcome.

That static distinction is captured by headroom. In a strongly complementary
system, the gap between the lowest and second-lowest service coverage describes
the immediate space through which a single-channel improvement could raise the
system **if other service levels and demands were held fixed**. Stage 4 allows a
direct check of how far that intuition travels in a dynamic setting. A
post-completion reconstruction from the frozen Migration trajectory ledger
recovers the full pre-withdrawal service vector in all 624 worlds and reproduces
the frozen pre-bottleneck label with zero mismatches. Among the 169 treated
observed-target-matched worlds, headroom is defined for 126 worlds in which at
least two formal services have positive demand in the pre-withdrawal window.

Headroom alone does **not** monotonically predict realized +30-day composite
yield in those worlds. The pooled Pearson association is -0.083 and the Spearman
rank association is 0.187, while mean yield is non-monotonic across headroom
quartiles. This negative result is theoretically useful. Once assistance changes
force activity, losses, logistics demand, command opportunities, and the
identity of active constraints, initial spacing is only a structural diagnostic.
Realized yield depends jointly on constraint spacing, the channel being treated,
treatment intensity, and the endogenous demand response.

The force-generation result therefore should not be reverse-engineered into a
claim that it had little yield because headroom must have been small. Its
observed-matched worlds actually have mean reconstructed headroom of about 0.536,
similar to command worlds at about 0.541. Yet force-generation support produces
essentially zero mean +30-day composite gain while command support produces a
modest positive gain. The contrast reinforces the broader argument: **the
configuration of constraints matters, but a static snapshot does not substitute
for tracing the adapted production system**.

This yields a straightforward measurement implication. Assistance evaluations
should report the pre-intervention first and second constraints, the local
improvement in the targeted service, the resulting whole-system gain, and the
post-intervention binding service. Without those four quantities, a program can
look highly successful or highly disappointing depending on which layer of the
system is measured.

## 6.4 Development should be evaluated at the system level

The mechanism experiment warns against equating indigenous output with system
autonomy. Developmental force generation clearly increases indigenous output.
That improvement is real. It simply has no marginal effect on the whole system
once logistics binds.

This suggests a different way to evaluate development programs. Rather than ask
only whether indigenous output increased in the targeted function, evaluation
should ask whether the targeted function remained binding after the increase,
whether another constraint emerged, and whether the force can sustain the
operating demand created by the improvement.

The logistics-development result shows the positive side of the same mechanism.
When logistics remains the system constraint, replacing external substitution
with indigenous production has a large effect on terminal autonomy. Development
works at the system level not merely because it is "local" or "owned," but
because it raises indigenous production where whole-system feasibility is still
being determined.

## 6.5 Coordinated development is complementary in some combinations but not a free rising tide

Stage 5 places a useful limit on the intuition that several weak services should
simply be developed together. The experiment distinguishes a technical question
from an allocation question. The technical question is whether simultaneous
improvement in two services can be superadditive. The allocation question is
whether dividing a fixed amount of developmental effort across several services
outperforms concentrating that effort in the best single channel.

The answer to the first question is **sometimes**. At high intensity in the
nominal near-tie structure, force generation plus logistics and logistics plus
command produce positive pairwise factorial interactions in terminal retained
autonomy. The three-way interaction is negative, and no other nominal structure
has a significantly positive interaction. Complementarity is therefore
configuration-specific rather than an automatic property of adding channels.

The answer to the second question is **no in this experiment**. None of the 32
precommitted fixed-effort breadth comparisons favors breadth with a positive 95
percent interval, while 21 significantly favor concentration. Even when several
capacities are weak, spreading a scarce developmental budget can dilute effort
below the level required to move the system minimum. The implication is not that
broad institution building is undesirable. It is that complementarity and budget
allocation are different problems. A donor may need to improve several services
eventually while still sequencing or concentrating scarce effort at any given
moment.

The nominal near-tie result also illustrates why observed constraints must be
measured rather than assumed from design labels. By the treatment split,
logistics is already the formal bottleneck in 365 of 368 nominal near-tie worlds.
This limits the clean test of the preregistered headroom scope condition. The
positive pairwise interactions remain valid randomized treatment contrasts within
that nominal structure, but they should not be interpreted as definitive evidence
that a contemporaneously observed three-way near tie causes complementarity.

Together with Stage 4, the result suggests a more conservative rule: develop
indigenous production where it is binding or predictably about to bind, test for
complementarity among specific services, and do not infer from complementarity
that an equal or broad allocation of a fixed budget is efficient. That rule is a
measurement implication of the model, not a validated real-world optimizer.

## 6.6 A diagnostic framework for evaluating security assistance

The theory implies that evaluation should distinguish assisted-subsystem output,
whole-system throughput, and the indigenous production frontier that can
reproduce that throughput. A constraint-aware assessment therefore asks five
questions at multiple points in time: what actually bound the force before
assistance; did the targeted service improve; how much whole-system capability
did that relief unlock; what binds the adapted force afterward; and how much of
the required service can the partner generate without the donor?

| Evaluation question | Quantity of interest | Why the conventional metric can mislead |
|---|---|---|
| What limited the force before assistance? | Observed binding service and distance to the next constraint | Program labels may not identify the service governing system output |
| Did the intervention work locally? | Change in targeted-service production or coverage | A large local gain can be stranded behind another constraint |
| How much did the force actually improve? | Whole-system capability yield | Constraint relief can occur with almost no increase in throughput |
| What limits the adapted force now? | Post-intervention binding service and service demand | Successful assistance can change the marginal problem |
| Can the partner reproduce the result? | Indigenous production relative to the adapted requirement | Supported readiness can remain high while independent reproducibility stagnates or falls |

**Table 5. Constraint-aware evaluation framework.** The framework is diagnostic,
not an optimal-allocation rule. It allows apparently contradictory assessments
to coexist: a donor can correctly report higher readiness or operational reach
while another assessment correctly finds continued external dependence because
they are measuring different production frontiers.

## 6.7 Distinguishing the mechanism from rival explanations

Several established theories can produce weak autonomy after large amounts of
security assistance. The present mechanism is most diagnostic when the targeted
function genuinely improves first and the autonomy problem emerges afterward in
a different service. Principal-agent failure predicts resistance or distortion
of the assisted reform; low absorptive capacity predicts weak first-stage use of
the assistance; institutional dependence emphasizes political or organizational
erosion; and inappropriate force design can make recurring requirements
unsustainable from the outset. Constraint migration instead predicts an ordered
sequence of real relief, operating expansion, induced demand, a new binding
service, and divergence between supported and reproducible capability.

| Explanation | Characteristic first-stage observation | What should happen next if that explanation dominates? | Distinctive evidence for the present mechanism |
|---|---|---|---|
| Principal-agent failure | Targeted reform is resisted, distorted, or only superficially adopted | Assisted function remains weak or politically constrained | Targeted function genuinely improves before the autonomy problem emerges elsewhere |
| Low absorptive capacity | Recipient cannot effectively employ the assisted capability | Weak first-stage performance | High first-stage performance followed by insufficient complementary indigenous production |
| Institutional or relational dependence | External provision changes incentives, ownership, or bargaining power | Indigenous institutions or autonomy weaken through political/institutional channels | Measurable operating expansion raises demand on a distinct service that becomes limiting |
| Inappropriate force design | Recurring requirements exceed feasible local capacity from the outset | Persistent dependence on the same imported system | The binding service changes after successful relief and operational expansion |
| Constraint migration under external substitution | A real binding service is successfully relieved | Operating scale or complexity expands; another indigenous service becomes limiting | Ordered sequence of relief, induced demand, new constraint, and supported/autonomous divergence |

**Table 6. Observable differences between the proposed production mechanism and
major rival explanations.** The mechanisms are not mutually exclusive. The
table identifies the temporal evidence needed to attribute a case specifically
to assistance-induced constraint migration.

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
[@gao2007iraqlog; @gao2007iraqcc; @gao2007iraqindependent].

Mali is a harder and less supportive case. RAND's field research found that
EUTM-trained GTIAs improved basic soldier skills, but logistics, maintenance,
command, and coordinated operations remained major limits [@shurkin2017]. Those
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

| Case | Audited constraint sequence | Indigenous replacement | Support-change evidence | Audited theory fit |
|---|---|---|---|---|
| Afghanistan | Aviation maintenance/logistics remained limiting beneath external substitution | Negative or incomplete | Abrupt contractor and U.S. support reduction followed by severe degradation | Strong for substitution/retention; partial for migration |
| Iraq | Rapid force generation followed by lagging logistics and sustainment | Incomplete in coded 2005-2008 episode | No clean withdrawal shock in coded episode | Strongest migration analogue, with political confounding |
| Mali | Basic unit skills improved while pre-existing logistics, maintenance, and C2 weaknesses remained | Mixed | No clean support shock in coded 2013-2015 episode | Partial; strongest for local-system divergence |
| Colombia | Externally enabled aviation expansion initially outran pilots, mechanics, maintenance, and logistics, followed by phased nationalization | Positive and substantial over time | Phased transfer rather than abrupt withdrawal | Strong positive retention case; partial for discrete migration |

**Table 7. Source-audited historical process evidence under the frozen external-
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

First, Pineland is a synthetic model. Its numerical transition points are not
empirical thresholds and should not be interpreted as estimates of the support
level at which a historical force becomes dependent.

Second, the formal autonomy coordinate treats military services as strongly
complementary. The analysis includes smooth feasibility aggregators to test
whether headline directions depend entirely on the hard minimum, but the model
still embeds assumptions about the degree to which service deficits can
substitute for one another.

Third, the striking persistence of logistics is a finding inside the current
architecture. It is not yet a general empirical law. Other force structures,
technologies, political institutions, or logistical arrangements could produce
a different terminal constraint.

Fourth, Stage 4 analyzes a bounded set of direct and developmental assistance
architectures. It does not exhaust assistance design, sequencing, volatility,
multi-donor interaction, adversary adaptation, fiscal incentives, or political
control. Several of those mechanisms belong in later experiments rather than
being inferred from the present evidence.

Fifth, developmental assistance is modeled as a change in productive capacity.
Real-world institution building is slower, politically contested, and often
nonlinear. The model therefore isolates the production consequence of
development more cleanly than historical interventions usually can.

Sixth, the relief-yield-retention framework, weighted cross-target yield
comparison, and static-headroom reconstruction are post-completion syntheses of
precommitted Stage-4 outputs. They sharpen interpretation of the completed
experiment but were not named as primary Stage-4 estimands before production.
The manuscript labels them accordingly. Stage 5 is a separately prospectively
frozen follow-up, while the structural terminal-constraint sidecar was frozen
after Stage-4 results were known but before its own outcomes were observed.

Seventh, the static-headroom quantity is a local diagnostic rather than a full
dynamic causal parameter. The post-completion Stage-4 reconstruction confirms
this empirically: headroom does not monotonically predict realized +30-day
composite yield. Assistance changes service demand, force size, operational
tempo, stocks, and interactions among channels, so realized yield can differ
substantially from the initial distance between the first and second constraints.
The headroom analysis is therefore retained as a falsifying qualification rather
than promoted into a new predictive result.

Eighth, Stage 5's nominal starting structures are imperfect manipulation checks.
After the common 120-day developmental prehistory, logistics is the observed
split-point bottleneck in virtually all nominal force-generation, logistics, and
near-tie worlds. The paired treatment contrasts and factorial estimands remain
well defined, but the preregistered claim that breadth should depend on observed
initial headroom cannot be tested as cleanly as intended. The manuscript therefore
treats H_D3 as unresolved rather than converting nominal labels into observed
constraint identities.

Ninth, the structural sidecar rejects only the strongest hard-coding objection.
It shows that command, force generation, and logistics can each be terminal under
adversarial structures, but it does not show that the Stage-4 migration paths
would reverse under empirically plausible neighboring parameter values.

Finally, the model isolates a production mechanism that can operate alongside
political mechanisms, not instead of them. Real partner forces are organizations
embedded in regimes, bureaucracies, patronage networks, coalitions, and wars.
The value of the present framework is to identify one source of endogenous
failure even under successful technical assistance. It does not imply that
technical diagnosis can substitute for political analysis.

# 9. Conclusion

Security assistance should not be judged by a single question: did the program
work? A program can succeed at the function it directly targets and still
produce very different outcomes for the force as a whole. The central
distinctions are whether the intervention **relieves** the original constraint,
how much system **yield** that relief unlocks, and how much of the resulting
capability the partner **retains** through indigenous production.

The integrated Stage-4 experiment shows why these outcomes diverge. Direct
external service provision produced a near-term capability gain in most treated
phase-map cells, yet 90.6 percent of those effective cells had lower indigenous
autonomy one year later. Observed command and force-generation bottlenecks
migrated consistently after targeted assistance, but the system gain associated
with migration varied sharply. Force-generation relief could change the binding
service while producing essentially no composite-capability gain. Logistics
support produced substantially more short-run capability while leaving logistics
itself binding and reducing long-run indigenous autonomy. Developmental logistics
substantially improved terminal autonomy relative to substitution, while large
indigenous gains in force generation could remain stranded behind a logistics
constraint.

The prospective Stage-5 follow-up adds an important qualification. Coordinated
indigenous development can generate positive pairwise complementarities, but it
does not create a general rising tide. Two high-intensity pairwise interactions
in the nominal near-tie structure are significantly positive, while the
three-way interaction is negative. More importantly, broad development never
beats the best included single-channel intervention with a positive bootstrap
interval when total developmental effort is held fixed, and 21 of 32 fixed-budget
comparisons significantly favor concentration. Complementarity therefore does
not imply equal or broad allocation of scarce developmental resources.

The structural falsification further narrows the interpretation of logistics.
Command and force generation are both reachable terminal constraints in the same
formal architecture, so logistics is not hard-coded as the unique endpoint.
Stage 4's migration toward logistics should therefore be treated as a result of
the tested production environment rather than a universal law. At the same time,
the sidecar does not establish that nearby realistic configurations would reverse
those migration paths.

The paper's core claim is consequently narrower than the familiar proposition
that assistance creates dependence. The contribution is a production mechanism
for understanding why **successful** assistance can generate disappointing
autonomy outcomes. Success changes what the force can do. What the force can do
changes what it requires. Those changing requirements can alter which indigenous
service determines the capability the partner can reproduce without the donor.
The practical implication is diagnostic rather than prescriptive: measure the
binding service, the local effect of assistance, the whole-system yield, the
post-relief constraint, and indigenous replacement. Supported performance and
independently reproducible capability are different outcomes, and policy should
stop treating one as evidence of the other.

# Data, Code, and Reproducibility

The production experiment, freeze contracts, analysis code, run ledger, and
compact paper-level evidence are maintained in the Pineland repository. The
Stage-4 campaign completed 2,808 of 2,808 production worlds. A final integrity
audit verified complete logical-task coverage, file hashes, row counts, source
commit, freeze hash, and contract hash with zero integrity errors. Large raw HPC
panels are retained outside ordinary Git history, while the integrated READY
manifests and the compact tables required to verify the headline manuscript
claims are tracked in the repository.

The production simulator commit is
`e369c107f4465ce8cd385a366cafca8c28c04b65`. The final postprocessing commit is
`7697e6eac83248c7bc03830e58d94a2d878c6635`. The precommitted paper-analysis
commit is `9b0e975c7e4073f2f5abd94e72cd125beb75f20d`. The repository consolidation
commit from which this manuscript branch begins is
`73b92e5420a2929bdf8eaec8d570a181acf87870`.

The separately prospective Stage-5 coordinated-development extension was frozen
before production in repository commit
`8d342c982e385699e76c766ec06ae991bc451876`. Its freeze re-hashes the inherited
scientific foundation together with the Stage-5 protocol, 92-cell contract,
analysis code, merge code, and ARC execution wrappers. The campaign completed
1,472 of 1,472 worlds; the READY manifest records the same commit for production
and analysis and hashes the merged primary, trajectory, and analysis artifacts.

The post-Stage-4 structural falsification was independently frozen before its own
outcomes at commit `4ffe67de2b4a55919e22048467527e01e76934df`. All 32 frozen
worlds completed. Task metadata record the frozen commit, contract hash, freeze
hash, and per-file output hashes; the sidecar used a production binary with the
same SHA-256 as the Stage-5 production build.

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
before any Stage-5 production outcome was observed.
