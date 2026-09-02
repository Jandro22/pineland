# Social-network semantics and weighted-agent scaling

## What one edge means

A `SocialEdge` is a **sampled aggregate channel of social influence between two representative agents**. It is not interpreted as exactly one literal friendship in the represented population. Its layers identify the mechanisms that sustain the channel: household membership, ordinary community contact, or cross-community bridging.

The model stores three distinct quantities:

- `language_compatibility`: potential mutual comprehension, calculated from the best shared language.
- `trust`: source acceptance, determined independently from language.
- `weight`: channel strength after a bounded language-comprehension adjustment.

Shared language therefore does not create trust. Language mismatch does not eliminate communication: the current formula retains a 0.35 floor before other mechanisms are applied. Household, repeated community contact, and bridge structure remain independently consequential.

## Representative weights

For endpoints with representative weights (w_i) and (w_j), the edge carries a represented-relationship multiplicity equal to their harmonic mean:

\[
m_{ij} = \frac{2w_iw_j}{w_i+w_j}.
\]

Neighbor contributions use:

\[
q_{ij} = m_{ij}\,W_{ij}\,T_{ij},
\]

and exposure is normalized by the sum of (q_{ij}) around the receiving agent. With equal weights, the common scale cancels. With unequal weights, a larger representative neighbor contributes proportionally more social mass without turning the absolute agent count into unbounded influence.

## Exposure is not persuasion or participation

Network exposure is a bounded signal. Public-behavior utility separately includes private preference, perceived grievance, expected control, fear, efficacy, displacement, and organization membership. Exposure enters through the configurable `behavior_exposure_weight`.

Recruitment is another transition. It separately includes grievance, expected control, fear, broad organization prevalence, organization cohesion/resources, and the smaller `recruitment_exposure_weight`. An edge never directly makes a person a participant.

The causal chain is therefore:

```text
edge and neighbor signal
-> normalized exposure
-> behavior/recruitment utility
-> stochastic choice or hazard
-> aggregate control-relevant behavior
-> causal-ledger contribution
```

## Resolution sensitivity

Use `pineland-sim scale-check` to compare fixed-population scenarios at multiple agent counts. The final two-day 25,000-versus-75,000 check found a maximum public-behavior share difference of 0.00332 and a government-control difference of approximately 0.00000610. This is a preliminary engineering check, not evidence of long-horizon scale invariance. Longer ensembles and multiple seeds remain required.
