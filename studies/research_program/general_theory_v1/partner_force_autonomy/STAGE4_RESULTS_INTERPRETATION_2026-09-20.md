# Stage 4 integrated partner-force results — post-completion interpretation

Status: **POST-COMPLETION INTERPRETATION**

This memo is deliberately separated from the frozen production,
postprocessing, and precommitted paper-analysis branches.  It summarizes what
the completed Stage-4 experiment found and therefore must not be treated as a
preregistration artifact.

## Provenance

- production commit:
  `e369c107f4465ce8cd385a366cafca8c28c04b65`
- final postprocessing commit:
  `7697e6eac83248c7bc03830e58d94a2d878c6635`
- precommitted paper-analysis commit:
  `9b0e975c7e4073f2f5abd94e72cd125beb75f20d`
- production worlds: **2,808 / 2,808**
- integrated status: `STAGE4_INTEGRATED_PROGRAM_COMPLETE`
- paper-analysis status: `STAGE4_PAPER_SECONDARY_COMPLETE`

An independent final integrity sweep re-hashed every completed primary and
trajectory shard, checked all row counts, exact logical-task coverage, source
commit, freeze hash, contract hash, and filename/metadata mapping.  It found
**zero integrity errors across all 2,808 worlds**.

## Executive result

The cleanest result is not merely that external support can create dependence.
It is that **direct substitutive assistance is overwhelmingly autonomy-eroding
when it is operationally effective, while developmental assistance only helps
system autonomy when it expands the indigenous capacity that remains binding
after the system adapts.**

In other words, the relevant condition is dynamic:

```text
current bottleneck
    -> assistance relieves it
    -> operational system adapts
    -> a new bottleneck may become binding
    -> autonomy depends on whether indigenous production grows at that
       now-binding constraint faster than assistance-enabled demand/obligation.
```

This is stronger than a generic substitution/dependency story because Stage 4
contains direct evidence for all three pieces:

1. effective direct service support usually lowers terminal indigenous
   autonomy;
2. developmental support can dramatically improve indigenous production in a
   target subsystem;
3. those local gains do not necessarily improve system autonomy because the
   bottleneck frequently migrates, most often to logistics.

## 1. Autonomy-Trap Phase Map

Module A contained 140 cells: 20 zero-support controls and 120 treated cells.

Among the **120 treated cells**:

- 106 were initially operationally effective at +30d;
- 96 were effective autonomy traps at +360d;
- 10 were descriptive effective autonomy-building cells;
- 14 were not initially effective.

Thus, among cells in which continued direct service support was initially
effective,

```text
96 / 106 = 90.57%
```

ended with a lower capped indigenous-autonomy metric than the matched
withdrawal branch.

The uncertainty-qualified result is even more asymmetric:

- **53 robust effective autonomy traps**;
- **0 robust effective autonomy-building cells**.

All ten descriptive autonomy-building cells fail the precommitted robust
building criterion.  Their bootstrap intervals include zero and/or their
medians do not support the positive mean direction.  Most are narrow,
high-variance islands in command-constrained systems.

### Support intensity

The average autonomy penalty grows substantially with direct support intensity:

| Intensity | Effective cells | Trap cells | Building cells | Robust traps | Mean Δ capability +30d | Mean Δ autonomy +360d |
|---:|---:|---:|---:|---:|---:|---:|
| 0.25 | 16/20 | 15 | 1 | 10 | +0.0061 | -0.0250 |
| 0.50 | 18/20 | 17 | 1 | 8 | +0.0165 | -0.0334 |
| 0.75 | 17/20 | 13 | 4 | 6 | +0.0196 | -0.0379 |
| 1.00 | 19/20 | 18 | 1 | 6 | +0.0290 | -0.0605 |
| 1.50 | 18/20 | 15 | 3 | 8 | +0.0403 | -0.0828 |
| 2.00 | 18/20 | 18 | 0 | 15 | +0.0334 | -0.1323 |

The important pattern is not that every intensity monotonically worsens every
world.  It is that the **average autonomy cost becomes increasingly negative at
higher direct-support intensity even while the short-run operational effect is
positive.**

At intensity `2.0`, every initially effective cell is an autonomy trap and 15
of 18 effective cells meet the robust-trap rule.

### Indigenous starting capacity

Higher balanced indigenous capacity mitigates but does not eliminate the trap.
Across the six treated intensities, robust-trap counts fall from 6/6 effective
cells at balanced capacity 0.40 and 0.55 to 2/6 at capacity 1.00.

The implication is not simply "low capacity is bad."  Stronger indigenous
capacity makes external substitution less dangerous because the system has more
domestic production behind the externally enabled operating level.

### The apparent positive region

The descriptive autonomy-building cells are almost entirely command-constrained
and are unstable across adjacent intensity/capacity cells.  There is only one
balanced-capacity positive-mean cell (`capacity=1.0`, `intensity=0.75`).  None
has a robust positive autonomy effect.

This means Stage 4 does **not** support a clean positive "substitutive aid builds
autonomy" region.  The more defensible conclusion is:

> Under the tested direct-service architecture, effective continued support is
> usually autonomy-eroding; apparent positive regions are narrow and
> statistically unstable.

That result should replace any earlier expectation of a smooth sign-changing
phase boundary for direct substitution alone.

## 2. Nominal weakness is not the same as the binding constraint

Observed bottlenecks matter more than experiment labels.

Examples from the Phase Map:

- nominal `forcegen_constrained` worlds increasingly become logistics-bound as
  force-generation capacity rises;
- at force-generation multiplier 0.60, **84/84** sampled worlds are already
  logistics-bottlenecked;
- balanced-capacity worlds increasingly become logistics-bottlenecked as
  general capacity rises, reaching **84/84 logistics bottlenecks at capacity
  1.0**;
- command-constrained worlds remain command-bottlenecked through multipliers
  0.20–0.55, then mostly transition to logistics at 0.70.

This is important methodologically: policy or experimental labels such as
"training problem" or "command problem" are poor substitutes for observing the
actual binding production constraint.

## 3. Substitution versus developmental assistance

Module C provides the strongest mechanism evidence.

### Logistics: developmental assistance is dramatically better than substitution

Direct logistics substitution is strongly autonomy-eroding at +360d.

Absolute mean terminal autonomy effects:

| Logistics weakness | Intensity | Substitution | Development | Hybrid |
|---|---:|---:|---:|---:|
| Severe | 0.5 | -0.2897 | -0.0355 | -0.1596 |
| Severe | 1.0 | -0.4603 | -0.0275 | -0.2000 |
| Moderate | 0.5 | -0.1415 | -0.0098 | -0.0746 |
| Moderate | 1.0 | -0.2430 | -0.0577 | -0.0830 |

Relative to substitution, developmental logistics reduces the absolute autonomy
penalty by approximately:

- **87.7%** at severe / 0.5;
- **94.0%** at severe / 1.0;
- **93.0%** at moderate / 0.5;
- **76.2%** at moderate / 1.0.

The matched-seed contrasts are large and precise.  Development minus
substitution raises terminal `q` by approximately:

- +0.254 at severe / 0.5;
- +0.433 at severe / 1.0;
- +0.132 at moderate / 0.5;
- +0.185 at moderate / 1.0.

The corresponding bootstrap intervals exclude zero.

Development also generates very large additional indigenous logistics
production relative to substitution: roughly +173k to +1.25M units across the
tested cells.

The caveat is important: **development generally makes continued support much
less autonomy-eroding; it does not generally make continued support absolutely
autonomy-positive relative to withdrawal.**

That is a more interesting result than a simple "development good" finding.

### Force generation: local capacity can improve without system autonomy moving

Developmental force-generation assistance produces large indigenous gains
relative to substitution.  At +360d, mean indigenous force-generation effects
under development range from roughly +62 to +383, while substitution produces
negative indigenous effects ranging from roughly -58 to -291 in the matched
cells.

Yet system-level capped `q` and composite capability are essentially unchanged
by the development-minus-substitution contrast.

Why?  By +360d, **every Module-C force-generation world is logistics
bottlenecked.**  The force-generation subsystem can genuinely improve while the
whole force gains no additional autonomous operating capacity because force
generation is no longer binding.

This is direct evidence for a distinction between:

```text
subsystem development != system autonomy
```

The force-generation cumulative coverage metric is undefined in these cells
because the post-split cumulative force-generation demand denominator is zero;
this is the source of the benign all-NaN warnings in the paper-analysis run.

### Command: development solves command, then exposes logistics

Command-targeted development increases indigenous command service/coverage, but
the system-autonomy result is mixed.

At +360d, **100% of command-development worlds have switched away from command
as the bottleneck**, overwhelmingly to logistics.  This is exactly what a
bottleneck-migration theory predicts: successful development can remove the
targeted constraint without raising system autonomy if another constraint takes
over.

At moderate weakness / high intensity, development performs significantly worse
than substitution on terminal system `q` in the matched contrast
(`development - substitution ≈ -0.132`, bootstrap interval approximately
`[-0.231, -0.046]`) despite improving the command subsystem itself.

This should not be interpreted as "command development is harmful" in a generic
sense.  It means **command-only development is insufficient once logistics
becomes the new binding constraint.**

## 4. Bottleneck migration is strongly channel-dependent

Among worlds receiving targeted assistance that matched the observed
pre-withdrawal bottleneck:

| Matched target | Worlds | Persistent migration | Median migration time | Modal post bottleneck | Mean Δ capability +30d | Mean Δ autonomy +360d |
|---|---:|---:|---:|---|---:|---:|
| Command | 38 | 100% | 7d | Logistics | +0.00354 | +0.0555 |
| Force generation | 46 | 100% | 7d | Logistics | ~0 | 0 |
| Logistics | 85 | 0% | — | Logistics | +0.0170 | -0.2215 |

Thus the result is **not** "relieving any bottleneck causes migration."

It is:

> Command and force-generation bottlenecks are readily displaced by successful
> assistance, after which logistics becomes binding; logistics behaves as a
> terminal or sink bottleneck in the tested architecture.

Every observed-matched command and force-generation world has logistics as its
modal post-support bottleneck.  Matched logistics worlds also remain logistics
bottlenecked.

This asymmetry is one of the strongest findings in the run and should become a
major part of the paper rather than averaging migration rates across channels.

## 5. Revised theoretical claim

The Stage-4 evidence suggests a tighter theory than the original broad Autonomy
Trap framing:

> **External assistance becomes autonomy-eroding when it raises the supported
> operating envelope faster than indigenous production at the constraint that
> ultimately binds the adapted system.  Assistance that develops a transient
> bottleneck can succeed locally yet fail systemically because successful
> relief moves scarcity elsewhere.**

This produces three qualitatively different assistance outcomes:

### A. Substitutive trap

The donor directly supplies missing service.  Short-run capability rises, but
indigenous coverage of the supported operating burden falls.  Higher support
intensity generally increases the autonomy penalty.

### B. Developmental relief of the terminal bottleneck

The donor increases indigenous production at a constraint that remains binding.
This can sharply reduce the autonomy penalty.  Logistics development is the
strongest example in Stage 4.

### C. Developmental bottleneck migration

The donor successfully develops one indigenous subsystem, but that subsystem
ceases to bind.  Another constraint—most often logistics—takes over, so local
capacity growth does not translate one-for-one into system autonomy.

Force generation and command provide the clean examples.

## 6. Implication for the next experiment: adaptive indigenous-replacement control

The results strengthen the case for the planned controller experiment.  A
static assistance package is solving the wrong optimization problem because the
identity of the binding constraint is endogenous.

The strongest next policy experiment is therefore not merely "taper aid as
indigenous capacity rises."  It is an **adaptive bottleneck-aware replacement
controller**:

```text
1. observe the current indigenous bottleneck;
2. allocate developmental assistance to that bottleneck;
3. reduce direct substitution only as indigenous replacement emerges;
4. detect bottleneck migration;
5. reallocate developmental effort to the newly binding constraint;
6. repeat until no externally enabled operating requirement exceeds the
   indigenous sustainable envelope.
```

This directly combines the strongest Stage-4 results:

- direct substitution produces the autonomy trap;
- development can reduce that trap;
- development of a nonbinding capacity has low system return;
- successful development itself changes what is binding.

That makes the controller experiment a natural synthesis rather than a separate
small paper.

## 7. Claims Stage 4 does *not* establish

The following should remain explicit limitations:

1. These numerical thresholds are properties of the synthetic Pineland model,
   not empirical cutoff values for a historical security force.
2. Module A tests a particular direct balanced-service architecture; it does not
   establish that every possible external-assistance design erodes autonomy.
3. The absence of a robust autonomy-building region under direct service support
   is evidence against that treatment architecture, not proof that autonomy
   building is impossible.
4. Logistics behaving as a terminal bottleneck is a powerful model finding that
   requires historical/external validation before being generalized broadly.
5. The hard-minimum formal bottleneck definition is supplemented by smooth
   arithmetic/geometric/harmonic robustness metrics, but bottleneck identity
   remains a structural modeling choice.
6. Several descriptive command-positive cells are mean-driven and uncertain;
   they should not be presented as a confirmed positive phase.

## 8. Paper-level takeaway

The best current one-sentence statement is:

> **The effect of external security assistance on partner autonomy depends less
> on how much capability the donor supplies than on whether indigenous
> production keeps pace with the system's moving binding constraint; direct
> substitution usually expands capability at the cost of autonomy, while
> development only translates into system autonomy when it follows bottleneck
> migration.**

That is substantially more specific than "aid can create dependency," and it
connects the Phase Map, developmental-assistance experiment, and Bottleneck
Migration experiment into one theory rather than three disconnected results.

