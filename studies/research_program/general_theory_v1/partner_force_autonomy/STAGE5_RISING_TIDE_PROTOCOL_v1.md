# Stage 5 Coordinated Indigenous Development Protocol v1

Status: **PROSPECTIVE FOLLOW-UP, TO BE FROZEN BEFORE PRODUCTION**

Date: 2026-09-21

## Motivation and disclosure

Stage 4 established that narrow assistance can improve a targeted subsystem
without improving whole-system autonomy, and that successful relief can shift
the binding service constraint. Those completed results motivated the present
follow-up. Stage 5 is therefore not part of the original Stage-4
preregistration.

The prospective question is whether coordinated growth of partner-owned
capacity across complementary services can avoid this failure mode. All Stage-5
cells, hypotheses, estimands, dose rules, and analysis rules are fixed before
any Stage-5 production outcome is observed.

## Core question

Can a rising tide of indigenous development lift the whole partner-force
production frontier, rather than merely moving the identity of the binding
constraint?

The experiment distinguishes three concepts:

1. **Constraint relief:** whether a targeted service ceases to bind.
2. **System yield:** how much whole-system capability or autonomy the relief
   actually unlocks.
3. **Retention:** how much of that gain remains partner-owned after additional
   development stops.

## Starting structures

Four starting structures are frozen:

| Structure | Force generation | Logistics | Command | Purpose |
|---|---:|---:|---:|---|
| forcegen_constrained | 0.15 | 1.40 | 1.40 | one dominant bottleneck |
| logistics_constrained | 1.40 | 0.25 | 1.40 | one dominant bottleneck |
| command_constrained | 1.40 | 1.40 | 0.30 | one dominant bottleneck |
| near_tie_low | 0.55 | 0.55 | 0.55 | multiple nearby constraints |

The first three provide scope-condition tests. Broad development should be less
efficient when one service is clearly binding and the other services have large
headroom. The near-tie structure is the strongest test of complementarity.

## Development combinations

Every nonempty combination of the three modeled indigenous service channels is
tested:

- force generation;
- logistics;
- command;
- force generation + logistics;
- force generation + command;
- logistics + command;
- force generation + logistics + command.

A no-development control is included for every starting structure.

## Dose levels

Two normalized developmental intensity levels are frozen: 0.50 and 1.00.

The single-channel reference rate is:

`0.08 x intensity per 30 days`.

Two multi-channel dosing regimes separate complementarity from simply spending
more resources.

### Regime A: equal total effort

For `k` active channels, each channel receives `intensity / k` of the normalized
single-channel dose. Total normalized developmental effort is therefore held
constant as intervention breadth increases.

This regime asks whether spreading the same total developmental effort across
complementary services can outperform concentrating it in one service.

### Regime B: equal channel dose

Every active channel receives the full single-channel normalized dose.

This regime asks whether developing complementary services together generates
factorial interaction effects. It deliberately spends more total effort as more
channels are included, so raw outcome differences in this regime are not
interpreted as cost efficiency.

## Scale and common random numbers

- 92 cells
- 16 seeds per cell
- 1,472 production worlds
- identical seed identities across all arms within each starting structure
- 1,000 agents and 72 localities per world
- 120-day developmental prehistory
- confirmatory horizons at +7, +30, +90, +180, and +360 days

## Primary branch and retention interpretation

The primary endpoint is the `SUPPORT_OFF` branch at +360 days. All development
arms receive the common 120-day prehistory. At the split, the `SUPPORT_OFF`
branch stops additional donor-driven developmental growth while preserving the
capacity already built. It therefore measures retained partner-owned capacity,
not continued donor input.

The `SUPPORT_ON` branch is secondary and measures the effect of continued
development after the split.

## Primary estimands

### 1. Retained autonomy gain

For each treatment arm and matched seed:

`G_Q = Q_arm,off,+360 - Q_control,off,+360`

where `Q` is capped indigenous whole-system coverage.

### 2. Retained capability gain

The corresponding matched effect on composite capability in `SUPPORT_OFF` at
+360 days.

### 3. Pairwise factorial complementarity

Under equal channel dose:

`I_AB = Q_AB - Q_A - Q_B + Q_0`

Positive `I_AB` means the combined intervention produces more whole-system
autonomy than the additive effects of the two single-channel interventions.

### 4. Three-way factorial interaction

Under equal channel dose:

`I_ABC = Q_ABC - Q_AB - Q_AC - Q_BC + Q_A + Q_B + Q_C - Q_0`

### 5. Fixed-effort breadth premium

Under equal total effort:

`B_S = Q_S - max(Q_j for j in S)`

with all terms matched on starting structure, seed, intensity, branch, and
horizon. Positive `B_S` means broader development uses the same normalized
effort more effectively than concentrating it in the best included single
channel.

## Hypotheses

**H_D1. Complementarity.** Multi-channel indigenous development produces
positive factorial interactions in terminal retained whole-system autonomy when
multiple services are jointly constraining.

**H_D2. Fixed-effort breadth.** Under fixed total normalized effort, broader
development can outperform concentrated development when the first and second
constraints are close.

**H_D3. Headroom scope condition.** The benefit of breadth is larger in the
near-tie structure than in single-dominant-bottleneck structures.

**H_D4. Constraint dynamics.** Broader indigenous development reduces or delays
bottleneck migration and improves retained capability when multiple services
would otherwise become sequentially binding.

## Inference

All treatment contrasts are paired by seed. Report means, medians, seed-level
distributions, and 95 percent paired bootstrap intervals. All preregistered
structure-by-intensity cells are reported. No result may be selected for the
paper solely because its sign is favorable.

The primary scientific emphasis is effect magnitude, sign consistency, and
whether the near-tie scope condition behaves differently from dominant-
bottleneck structures.

## Interpretation boundaries

The experiment can establish complementarity and constraint dynamics inside the
Pineland synthetic system. It cannot establish that real partner forces should
receive equal investment across these three services, that these are the only
relevant real-world services, or that the simulated dose is a real-world budget
recommendation.

Stage-5 results must be labeled as a prospective follow-up motivated by Stage 4,
not as part of the original Stage-4 preregistration.
