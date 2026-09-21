---
title: "The Moving Bottleneck: Security Assistance, Indigenous Capacity, and the Autonomy Trap"
author: "Alejandro Grenier"
affiliation: "Virginia Tech"
bibliography: references.bib
status: "Working manuscript, Draft 0.2"
date: "2026-09-21"
keywords: "security assistance; military effectiveness; partner forces; autonomy; logistics; agent-based modeling"
---

# Abstract

Security assistance is often evaluated by whether external training, equipment,
advising, or services improve a partner force's current performance. That
criterion can obscure a different outcome: assistance may increase supported
capability while reducing the share of the resulting military system that the
partner can generate and sustain independently. This article develops a dynamic
theory of the **autonomy trap** in which external assistance relieves a binding
constraint, expands the supported operating envelope, and changes the service
that limits indigenous military production. The theory is tested in Pineland, a
partially observed agent-based model of insurgency, counterinsurgency, state
capacity, logistics, command, and partner-force development. A prospectively
frozen three-module experiment generated 2,808 production worlds. Among 106
treated phase-map cells where continued direct assistance increased composite
capability at 30 days, 96, or 90.6 percent, produced lower indigenous autonomy
at 360 days. Fifty-three cells met the precommitted robust autonomy-trap
criterion and none met the robust autonomy-building criterion. When assistance
matched an observed command or force-generation bottleneck, persistent
bottleneck migration occurred in 38 of 38 and 46 of 46 worlds respectively;
matched logistics cases migrated in 0 of 85 worlds. Developmental logistics
assistance improved terminal autonomy relative to direct substitution by 0.132
to 0.433 on the capped indigenous-feasibility scale, with all four matched
bootstrap intervals excluding zero. Yet force-generation development could
substantially increase indigenous output while leaving whole-system autonomy
unchanged because logistics became binding. The results identify a moving
production constraint as a mechanism linking effective assistance to later
dependence. The numerical thresholds are synthetic-model results, not empirical
estimates for historical partner forces.

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
claim that assistance can create dependency. It is a dynamic production
mechanism linking successful assistance to later autonomy. If a partner force
is initially constrained by command, training throughput, or logistics,
successful assistance can raise the level of operations that the force is
capable of attempting. That success changes service demand and can expose a
different constraint. The relevant question becomes whether indigenous
production grows at the service constraint that binds the system after it has
adapted to assistance.

This article calls that process **bottleneck migration**. The core claim is that
partner-force autonomy is determined by indigenous service coverage at a
moving binding constraint. External assistance can therefore produce an
**autonomy trap**: supported capability rises in the short run while the
partner's indigenous capacity covers a smaller share of the operating system in
the long run. Conversely, developmental assistance can improve autonomy when it
increases indigenous production at the constraint that remains binding. The
same developmental intervention can have little system-level effect if it
successfully removes one bottleneck only to reveal another.

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

These results make three contributions. First, they separate **supported
capability** from **indigenous autonomy** and show why the former cannot be used
as a sufficient proxy for the latter. Second, they introduce bottleneck
migration as an endogenous consequence of successful assistance. Third, they
distinguish local capacity development from system autonomy. A partner can
become better at producing one military input without becoming more capable of
sustaining the whole force independently.

The argument is not that politics ceases to matter once military production is
modeled. Recipient incentives, donor leverage, organizational design, and
political institutions determine whether reforms occur and how assistance is
used. The moving-bottleneck mechanism is conditional on changes in military
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

## 3.2 The autonomy trap

Suppose external assistance raises supported capability by supplying service at
the current bottleneck. If the partner's indigenous production does not expand
at the same pace as the supported operating requirement, then supported
capability can rise while indigenous autonomy falls.

The simplest condition is

\[
\frac{\Delta I_{B,t}}{I_{B,t}} <
\frac{\Delta D_{B,t}}{D_{B,t}},
\]

where (B) denotes the relevant binding service. In that case indigenous
coverage (I/D) declines even if indigenous service does not decline in
absolute terms. This distinction matters because assistance can expand both the
numerator and the denominator. More indigenous capacity does not necessarily
mean more autonomy if the supported force's requirements expand faster.

**Proposition 1, Autonomy Trap.** External assistance can increase near-term
operational capability while decreasing later indigenous autonomy when the
supported operating requirement grows faster than indigenous production at the
binding constraint.

**Proposition 2, Intensity Effect.** Conditional on a substitutive assistance
architecture, larger external support can deepen the autonomy penalty when it
raises the supported operating envelope faster than it induces indigenous
replacement.

The second proposition is conditional rather than globally monotonic. Different
starting structures and nonlinear responses can produce local exceptions.

## 3.3 Bottleneck migration

Successful assistance can eliminate the constraint that justified the
intervention. If service (j) initially binds but assistance raises
(q_{j,t}^{I}) or (q_{j,t}^{S}), another service (k) can become the new
minimum:

\[
B_t=j \quad \rightarrow \quad B_{t+h}=k.
\]

This is bottleneck migration. It yields a strong implication for evaluation.
An intervention can succeed on its target metric and still have little effect
on whole-system autonomy if the target ceases to bind.

**Proposition 3, Bottleneck Migration.** Assistance that successfully relieves a
nonterminal binding constraint increases the probability that a different
service becomes the limiting constraint of the partner force.

## 3.4 Substitution and development

Direct substitution supplies (E). Developmental assistance instead seeks to
raise the partner's own production function, increasing (I). These two
approaches may generate similar near-term supported capability but have
different autonomy implications.

If development targets the service that remains binding, it should increase the
partner's coverage of demand and therefore improve whole-system autonomy
relative to substitution. If it targets a transient bottleneck, its local
effect may be large while its system effect is small.

**Proposition 4, Development at the Binding Constraint.** Developmental
assistance should outperform direct substitution on terminal autonomy when it
increases indigenous production at a service that remains system-binding.

**Proposition 5, Local-System Divergence.** Developmental assistance can produce
large indigenous gains in a targeted subsystem without increasing whole-system
autonomy when successful development causes another service to become binding.

![Figure 1. The moving-bottleneck mechanism. Assistance relieves a current
constraint, changes the supported operating envelope, and can alter which
service ultimately limits indigenous autonomy.](figures/figure1_conceptual.png)

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

## 5.4 Successful command and force-generation relief produces bottleneck migration

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

# 6. Discussion

## 6.1 What the results add to security-assistance theory

The findings refine, rather than replace, existing explanations of security
assistance. Interest misalignment, political incentives, weak institutions,
fragmented security sectors, and donor-recipient dependence remain central
problems [@biddle2018; @metz2023; @harkness2022; @sandnes2024]. The present
results identify a production dynamic that can operate even when assistance
does what donors intend at the targeted military function.

The key distinction is between **relieving a constraint** and **building an
autonomous system**. Direct service can relieve the current bottleneck and
increase battlefield capability. Development can also improve the partner's
own production of the targeted service. Neither outcome guarantees autonomy if
the intervention changes the level and composition of demand enough to reveal a
different limiting service.

This produces a recursive view of partner-force development:

\[
B_t \rightarrow \text{assistance} \rightarrow \text{relief} \rightarrow
\text{system adaptation} \rightarrow B_{t+h}.
\]

The central object of analysis is therefore the sequence of binding constraints,
not a static list of capabilities.

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

## 6.3 Development should be evaluated at the system level

The mechanism experiment warns against equating indigenous output with system
autonomy. Developmental force generation clearly increases indigenous output.
That improvement is real. It simply has no marginal effect on the whole system
once logistics binds.

This suggests a different way to evaluate development programs. Rather than ask
only whether indigenous output increased in the targeted function, evaluation
should ask whether the targeted function remained binding after the increase,
whether another constraint emerged, and whether the force can sustain the
operating demand created by the improvement.

## 6.4 A next-step implication: adaptive replacement

The results motivate, but do not yet validate, a bottleneck-aware assistance
strategy. A static package solves a problem defined at the beginning of an
intervention. A moving-constraint theory implies a feedback process instead:
observe the current bottleneck, develop indigenous production at that
bottleneck, reduce external substitution as replacement emerges, detect
migration, and redirect developmental effort if a new service becomes binding.

That controller is a logical next experiment rather than a result of the
present paper. Testing it should be treated as a separate confirmatory policy
experiment so that the current paper remains focused on the causal mechanism.

# 7. External Validity and Historical Validation

The synthetic experiments are designed to establish internal causal logic under
explicit model assumptions. External validity requires a different evidentiary
strategy. Historical validation should therefore test observable implications
of the mechanism rather than search for cases that merely resemble the model.

A structured historical test should ask, for each case:

1. What military service was plausibly binding before the assistance episode?
2. What external service or developmental intervention was provided?
3. Did the targeted function measurably improve?
4. Did the partner's operating scale, tempo, or service demand increase?
5. Did a different function subsequently become limiting?
6. Was the new constraint supplied externally or developed indigenously?
7. What happened when external support was reduced?

The historical-validation protocol is now frozen before systematic coding. It
specifies four cases: Afghanistan, Iraq, Mali, and Colombia. It also freezes the
unit of analysis, observable implications, source hierarchy, coding fields, and
disconfirming-evidence requirements. Because the synthetic results were already
known and the researcher had broad prior familiarity with these cases, the
historical exercise is described as structured external validation rather than
an untouched confirmatory test. Historical claims will be added only after the
case memos are coded under that protocol.

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

# 9. Conclusion

Security assistance can succeed operationally and fail autonomously. In the
integrated Stage-4 experiment, direct external service provision produced a
near-term capability gain in most treated phase-map cells, yet 90.6 percent of
those effective cells had lower indigenous autonomy one year later. Successful
relief also changed the system's constraint structure. Observed command and
force-generation bottlenecks migrated consistently after targeted assistance,
while logistics remained binding in the matched logistics cases. Developmental
assistance substantially reduced the autonomy penalty when it expanded
indigenous logistics production, but large local improvements in force
generation could leave system autonomy unchanged when logistics became the new
constraint.

These findings suggest that the core problem is not assistance volume alone.
Nor is it enough to distinguish external substitution from indigenous capacity
building in the abstract. The relevant question is whether indigenous
production keeps pace with demand at the service that binds the adapted force.

The resulting theory is a moving-bottleneck theory of partner-force autonomy.
Assistance changes the force it supports, successful development changes what
the force lacks, and autonomy depends on whether indigenous production can
follow that moving constraint.

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

# Disclosure

The author designed and developed the Pineland simulation and conducted the
analysis described here. The historical-validation exercise is being conducted
after the synthetic Stage-4 results were observed and is therefore labeled as
external validation rather than prospective confirmation. The manuscript makes
no claim that synthetic numerical thresholds are empirical estimates for any
historical security force.
