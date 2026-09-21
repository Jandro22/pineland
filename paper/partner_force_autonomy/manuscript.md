---
title: "Suffering from Success: Security Assistance, Constraint Migration, and Partner-Force Autonomy"
author: "Alejandro Grenier"
affiliation: "Virginia Tech"
bibliography: references.bib
status: "Working manuscript, Draft 0.4"
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
services, and expose another constraint. A prospectively frozen experiment in
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
whole-system autonomy unchanged. The results explain why successful assistance
may stall rather than compound.

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
[@rolandsen2026]. U.S. government evaluations similarly continue to identify
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
of the adapted system falls. The same logic also identifies a possible escape
condition. If indigenous production rises across the set of complementary
services that are close to binding, the whole feasible frontier can move
outward rather than merely shifting the identity of the bottleneck. That
coordinated-development implication is tested prospectively in a separately
frozen Stage-5 extension; the completed Stage-4 evidence establishes the causal
problem that motivates it.

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
generated directly from the tracked Stage-4 compact evidence package.

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

These results make four contributions. First, they separate **constraint
relief, system yield, and retention**, showing why success on the first outcome
does not establish success on the other two. Second, they distinguish
**supported capability** from **indigenous autonomy** and show why the former
cannot serve as a sufficient proxy for the latter. Third, they identify
constraint migration as an endogenous consequence of successful assistance and
show that migration can occur with very different amounts of system gain.
Fourth, they distinguish local capacity development from system autonomy. A
partner can become much better at producing one military input without becoming
more capable of sustaining the whole force independently.

The argument is not that politics ceases to matter once military production is
modeled. Recipient incentives, donor leverage, organizational design, and
political institutions determine whether reforms occur and how assistance is
used. The constraint-migration mechanism is conditional on changes in military
service production actually taking place. It therefore complements rather than
displaces agency and influence theories of security assistance.

The article is deliberately limited in one important respect. The experiments
establish causal relationships inside a synthetic model. They do not estimate
historical treatment effects or identify empirical threshold values for
Afghanistan, Iraq, Mali, or another real partner force. The final manuscript
will therefore treat historical evidence as a separate external-validation
exercise rather than using historical anecdotes to retroactively validate the
simulation.

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

## 2.3 From static capacity to a moving constraint

Military capability is jointly produced. Personnel without logistics cannot
operate. Logistics without command cannot reliably translate resources into
coordinated action. Command without force generation cannot replace losses or
expand the force. If these functions are complements, the effective capacity of
the whole system depends disproportionately on the service channel with the
lowest indigenous coverage of demand.

This logic is consistent with a broader economics of organizational
complementarity in which the return to one practice depends on the presence of
others [@milgromroberts1990]. The military application adds a dynamic scarcity
problem. A complementary input that is nonbinding today can become decisive
after another input improves. The marginal value of capacity building therefore
depends not only on the amount added to one subsystem, but on the configuration
of the remaining constraints.

Most assistance evaluations nevertheless measure inputs or outputs attached to
the intervention itself. A training program is evaluated through graduates. An
equipment program is evaluated through deliveries and readiness. An advisory
mission is evaluated through tactical or organizational performance. Those
measures can be appropriate for the intervention's proximal objective while
remaining incomplete measures of system autonomy.

The missing dynamic is that assistance changes the system it evaluates. If
external logistics allows a force to conduct more operations, logistics demand
can rise. If training increases available personnel, sustainment demand can
rise. If command assistance increases coordination, the force may begin to use
personnel and supplies at a level that reveals a different shortage. The
binding constraint is therefore endogenous to assistance.

# 3. Theory

## 3.1 Indigenous autonomy as service coverage

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
service limits the adapted force, while headroom determines how much immediate
gain can be unlocked before the next constraint binds.](figures/figure1_conceptual.png)

## 3.5 Falsifiable implications and scope conditions

The theory is not a claim that every successful assistance program must produce
constraint migration, dependence, or declining autonomy. Several observations
would narrow or contradict its stronger forms.

First, the migration mechanism is weakened if targeted assistance repeatedly
relieves an observed binding service without changing the identity or relative
importance of any complementary constraint, especially when operating scale and
service demand rise substantially. Second, the autonomy-trap mechanism is
weakened if increases in supported operating requirements are consistently
matched or exceeded by indigenous service production at the binding channels.
Third, the local-system divergence claim is weakened if improvements in a
nonbinding subsystem continue to generate large whole-system autonomy gains
after another service has clearly become limiting.

The coordinated-development extension adds a sharper prospective test. Under a
fixed total developmental effort, broad allocation is predicted to be most
valuable when several services are close to binding. When one service is far
more restrictive than all others, concentrating development on that dominant
constraint can be more efficient than spreading the same effort across
nonbinding functions. If Stage 5 instead shows that intervention breadth has no
relationship to starting constraint structure, the rising-tide scope condition
is not supported.

Finally, nothing in the theory requires logistics to be the terminal constraint.
The repeated emergence of logistics in Stage 4 is an empirical property of the
current model architecture and treatment domain. A structural environment in
which command or force generation remains terminal would narrow the logistics-
specific interpretation without contradicting the more general claim that the
identity of the binding constraint can change.

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
after Stage-4 results were known, it is treated as a separate prospective
extension rather than retrofitted into the original design.

Stage 5 contains 92 cells and 16 matched seeds per cell, for 1,472 production
worlds. It tests all nonempty combinations of indigenous force-generation,
logistics, and command development across four starting structures: one
force-generation bottleneck, one logistics bottleneck, one command bottleneck,
and a low-capacity near-tie structure in which all three services begin close to
binding. Two developmental intensities are used.

The design deliberately separates two questions. Under **equal total effort**,
a fixed normalized developmental dose is divided across the active channels.
For two active services each receives one-half of the single-channel reference
dose; for three active services each receives one-third. This tests whether
breadth itself can improve allocation efficiency. Under **equal channel dose**,
each active service receives the full single-channel dose. Multi-channel arms
therefore use more total effort, allowing direct estimation of pairwise and
three-way factorial interactions without interpreting raw outcome differences
as cost efficiency.

The primary Stage-5 endpoint is capped indigenous whole-system feasibility on
the `SUPPORT_OFF` branch at +360 days. All arms receive the same 120-day
developmental prehistory. At the branch split, additional donor-driven
development stops in `SUPPORT_OFF` while the indigenous productive capacity
already accumulated remains. The endpoint therefore measures retention of
partner-owned capacity rather than continued donor input. The precommitted
analyses include retained autonomy and capability gains, pairwise and three-way
factorial interactions, equal-total-effort breadth premiums, and bottleneck
migration or persistence.

The Stage-5 protocol, contract, analysis code, execution wrappers, and inherited
scientific foundation were cryptographically frozen before any Stage-5
production outcome was observed. Stage 4 was explicitly used to motivate the
question; Stage-5 outcomes were not used to select cells, doses, hypotheses, or
estimands. At Draft 0.4, Stage-5 results are therefore intentionally omitted
from the Results section. They will be inserted only after the frozen campaign
and postprocessing checks complete.

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

# 6. Discussion

## 6.1 What the results add to security-assistance theory

The findings refine, rather than replace, existing explanations of security
assistance. Interest misalignment, political incentives, weak institutions,
fragmented security sectors, and donor-recipient dependence remain central
problems [@biddle2018; @metz2023; @harkness2022; @sandnes2024]. The present
results identify a production dynamic that can operate even when assistance
does what donors intend at the targeted military function.

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

## 6.3 Headroom determines whether constraint relief matters

The migration result should not be interpreted as a claim that a force returns
to square one whenever the bottleneck moves. If the original bottleneck lies
far below the next constraint, relieving it can unlock a large amount of system
capability before the second service becomes limiting. If the first two
constraints are almost tied, the same successful intervention can change the
identity of the bottleneck while barely moving the system outcome.

That distinction is captured by headroom. In a strongly complementary system,
the gap between the lowest and second-lowest service coverage is the immediate
space through which a single-channel improvement can raise the system before
the next constraint takes over, absent induced changes elsewhere. The Stage-4
force-generation migration results are consistent with very low realized
headroom: the bottleneck moved in every observed-matched case while the average
short-run composite-capability effect was effectively zero. Command relief
produced modest positive yield. Logistics support produced larger supported
yield despite no persistent migration. The identity of the next bottleneck and
the distance to it therefore matter at least as much as whether migration occurs.

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

## 6.5 When a rising tide can lift the whole system

The Stage-4 evidence establishes the failure mode of narrow development but does
not imply that capacity building must chase bottlenecks indefinitely. In a
complementary production system, several services can be jointly or nearly
binding. Developing one alone may have little system effect because the next
constraint immediately takes over. Developing several together can, in
principle, move the minimum itself.

This is the rising-tide possibility. Its strongest form predicts positive
complementarity: the whole-system gain from developing two or three near-binding
services together exceeds the additive gain expected from developing them one
at a time. A weaker but policy-relevant form predicts an allocation benefit:
even with the same total developmental effort, spreading resources across
several near-binding services can outperform concentrating them in one when
headroom is small.

The theory does not predict that broad development is always superior. If one
service is far more restrictive than all others, dividing a fixed budget across
nonbinding functions should waste effort that could have been concentrated on
the dominant constraint. The appropriate breadth of development should
therefore depend on the breadth of the binding-constraint set. That scope
condition is the central purpose of the prospectively frozen Stage-5 extension.

The broader implication is a shift from static assistance packages toward
constraint-aware development. A program should diagnose which services bind,
how much headroom exists above them, how intervention changes demand, and
whether partner-owned production is keeping pace across the set of services
that become limiting. The model does not yet establish an optimal real-world
allocation rule, but it identifies the variables such a rule would have to
track.

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

The protocol freezes four cases before systematic coding is completed:
Afghanistan, Iraq, Mali, and Colombia. They are selected for theoretical
variation rather than because all four are expected to support the argument.

| Case | Intended evidentiary role | Main question for the theory |
|---|---|---|
| Afghanistan | High-support, high-substitution episode with a major withdrawal shock | Can supported sophistication outrun indigenous replacement even when the externally supplied function remains the core constraint? |
| Iraq | Force-generation and institutional expansion under heavy external assistance | Does improvement in force generation reveal sustainment or logistics as a subsequent system constraint? |
| Mali | Politically fragmented, multi-provider and difficult case | Does the production mechanism survive where political fragmentation and provider diversity complicate a clean constraint sequence? |
| Colombia | Comparatively durable long-run development case | Can indigenous institutions and sustainment grow fast enough for capability gains to become retained rather than externally reproduced? |

Preliminary coding under that frozen protocol already produces meaningful
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

| Case | Preliminary constraint sequence | Indigenous replacement | Support-change evidence | Preliminary theory fit |
|---|---|---|---|---|
| Afghanistan | Aviation maintenance/logistics remained limiting beneath external substitution | Negative or incomplete | Abrupt contractor and U.S. support reduction followed by severe degradation | Strong for substitution/retention; partial for migration |
| Iraq | Rapid force generation followed by lagging logistics and sustainment | Incomplete in coded 2005-2008 episode | No clean withdrawal shock in coded episode | Strongest migration analogue, with political confounding |
| Mali | Basic unit skills improved while pre-existing logistics, maintenance, and C2 weaknesses remained | Mixed | No clean support shock in coded 2013-2015 episode | Partial; strongest for local-system divergence |
| Colombia | Externally enabled aviation expansion initially outran pilots, mechanics, maintenance, and logistics, followed by phased nationalization | Positive and substantial over time | Phased transfer rather than abrupt withdrawal | Strong positive retention case; partial for discrete migration |

**Table 5. Preliminary historical process evidence under the frozen external-
validation protocol.** The table is a structured plausibility and process test,
not a causal estimate of security-assistance effects. Coding remains subject to
the protocol's source-audit and rival-explanation requirements.

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
were frozen before systematic case coding. The completed case table will report
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

Sixth, the relief-yield-retention framework and the weighted comparison of
system yield across observed-matched Migration targets are post-completion
syntheses of precommitted Stage-4 outputs. They sharpen the interpretation of
the completed experiment but were not themselves named as primary Stage-4
estimands before production. The manuscript labels them accordingly. The
Stage-5 coordinated-development test is separate and prospective.

Seventh, the static-headroom quantity is a local diagnostic rather than a full
dynamic causal parameter. Assistance can change service demand, force size,
operational tempo, stocks, and interactions among channels, so realized system
yield can differ from the initial distance between the first and second
constraints. Headroom is useful because it clarifies why relief can have very
different returns; it should not be treated as a deterministic prediction by
itself.

Finally, the model isolates a production mechanism that can operate alongside
political mechanisms, not instead of them. Real partner forces are organizations
embedded in regimes, bureaucracies, patronage networks, coalitions, and wars.
The value of the present framework is to identify one source of endogenous
failure even under successful technical assistance. It does not imply that
technical diagnosis can substitute for political analysis.

# 9. Conclusion

Security assistance should not be judged by a single question: did the program
work? A program can work at the level it directly targets and still produce very
different outcomes for the force as a whole. The central distinctions are
whether the intervention **relieves** the original constraint, how much system
**yield** that relief unlocks, and how much of the resulting capability the
partner **retains** through indigenous production.

The integrated Stage-4 experiment shows why these outcomes diverge. Direct
external service provision produced a near-term capability gain in most treated
phase-map cells, yet 90.6 percent of those effective cells had lower indigenous
autonomy one year later. Observed command and force-generation bottlenecks
migrated consistently after targeted assistance, but the system gain associated
with that migration varied sharply. Force-generation relief could change the
binding service while producing essentially no composite-capability gain.
Logistics support produced substantially more short-run capability while
leaving logistics itself binding and reducing long-run indigenous autonomy.
Developmental logistics substantially improved terminal autonomy relative to
substitution, while large indigenous gains in force generation could remain
stranded behind a logistics constraint.

The paper's core claim is therefore not that assistance creates dependence.
That problem is already well established. The contribution is a production
mechanism explaining why **successful** assistance can generate disappointing
autonomy outcomes. Success changes what the force can do. What the force can do
changes what it requires. Those changing requirements can move the constraint
that determines the marginal value of further development.

This mechanism also leaves room for a positive outcome. If indigenous
production grows across the set of services that are jointly close to binding,
the whole frontier may move outward rather than one bottleneck merely replacing
another. The prospectively frozen Stage-5 extension tests that rising-tide
possibility directly. Whatever its result, the Stage-4 evidence already implies
a different standard for evaluating security assistance: measure the constraint
that binds, the headroom above it, the whole-system yield created by relief, and
the indigenous production that remains after support stops.

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
analysis code, merge code, and ARC execution wrappers. Stage-5 results are not
incorporated into Draft 0.4.

# Disclosure

The author designed and developed the Pineland simulation and conducted the
analysis described here. The historical-validation exercise is being conducted
after the synthetic Stage-4 results were observed and is therefore labeled as
external validation rather than prospective confirmation. The manuscript makes
no claim that synthetic numerical thresholds are empirical estimates for any
historical security force. The relief-yield-retention framing and the weighted
cross-target yield comparison were developed after Stage-4 completion and are
labeled as post-completion synthesis. The coordinated-development Stage-5
experiment was motivated by those completed results but prospectively frozen
before any Stage-5 production outcome was observed.
