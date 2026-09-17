# Paper 1 claim matrix

This document is a claim firewall for **Inferring the Hidden War**. It separates
what the observation design identifies from what Pineland dynamics or priors
help estimate. It is deliberately stricter than ordinary model-output language.

## Claim classes

### A. Observation-identifiable named coordinates

A named latent coordinate belongs here only if its unit basis vector lies in the
row space of the declared mixed-proxy snapshot measurement design. Equivalently,
that coordinate is unchanged by every vector in the design null space.

Current mixed-proxy design: **4 / 18 named coordinates**.

- `government.physical`
- `government.administrative`
- `insurgent.physical`
- `insurgent.administrative`

A successful recovery experiment may support a statement that reports contain
information about these coordinates, subject to finite-sample calibration and
misspecification tests. Structural identifiability alone is not a recovery
result.

### B. Measurement-aligned latent estimands

These are the scalar latent combinations directly declared by report channels.
They belong to the observable measurement space even when their decomposition
into named coordinates is not unique.

- `security_presence_report`
- `administrative_function_report`
- `taxation_coercion_report`
- `public_alignment_report`
- `organizational_presence_report`
- `logistics_readiness_report`
- `government_admin_anchor`
- `insurgent_physical_anchor`

Paper 1 should report recovery of these estimands separately from coordinate
recovery. A strong measurement-space result with weak coordinate recovery is an
identification finding, not an estimator failure.

### C. Model-assisted named coordinates

These coordinates are not uniquely identified by the current mixed-proxy
snapshot design. They may nevertheless become estimable in a dynamic model
because transition equations, temporal persistence, cross-state relationships,
and priors add restrictions. Any claim about them must therefore be labeled
**model-assisted** rather than attributed to observation information alone.

Current members include:

- `government.formal`
- `government.legal`
- `government.fiscal`
- `government.social`
- `government.expected`
- `insurgent.formal`
- `insurgent.legal`
- `insurgent.fiscal`
- `insurgent.social`
- `insurgent.expected`
- `insurgent.foothold`
- `insurgent.embeddedness`
- `insurgent.fighter_capacity`
- `insurgent.supply_capacity`

Some of these have nonzero proxy loadings but remain entangled in a null-space
tradeoff. Others have no direct loading at all. Those are different reasons for
non-identification and should not be conflated.

### D. Historical latent truth claims

Historical Afghanistan or Nepal does not provide known ground truth for latent
organizational strength or multidimensional political control. Paper 1 must not
turn historical fit into statements such as ?the model recovered the true
Taliban strength in district X.? Historical cases can confront held-out
**observable** evidence and test transfer/prediction. Synthetic known-truth
experiments are the place where latent-state recovery can be scored directly.

## Structural facts of the current mixed-proxy design

- latent coordinates: **18**
- scalar report channels: **8**
- snapshot design rank: **8**
- nullity: **10**
- individually observation-identifiable named coordinates: **4**
- minimum number of additional independent scalar equations required for full
  18-coordinate snapshot rank: **10**

The last number is an information bound. No particle count, optimizer, neural
network, or more detailed agent-based model can remove a ten-dimensional null
space without additional information or additional assumptions.

## Paper-language rule

Each substantive result should be tagged internally with one of the following:

- `OBSERVATION_IDENTIFIED`
- `MEASUREMENT_ESTIMAND`
- `MODEL_ASSISTED`
- `HISTORICAL_OBSERVABLE_ONLY`

If a result does not fit one of these classes, it is not ready to become a
paper claim.
