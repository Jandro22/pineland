# Phase 4 information model

The information subsystem makes partial information explicit inside the current
combat-capable model. Its actor-facing chain is

```text
latent world state -> source sampling -> Observation -> node/actor belief -> decision
```

That chain is distinct from the researcher-facing recording process:

```text
latent event -> synthetic recording operator -> recorded observable
```

An `Observation` is simulated evidence available to an actor. A
`SyntheticRecord` is an imperfect researcher-visible historical record. The
two are not interchangeable.

## Truth, belief, and record firewall

`WorldState` contains the authoritative latent simulation state, but decision code
should consume the narrowest view available:

- `WorldTruthView` is privileged for environment evolution, source sampling, and
  analyst diagnostics.
- `ActorBeliefView` exposes actor/person estimates without realized control.
- `EmpiricalRecordView` exposes only synthetic records that passed the recording
  operator.

The environment may inspect true target presence in order to generate a noisy
positive, negative, or false report. The resulting actor does not receive the
truth label. Initial actor control beliefs are broad 0.5 priors, not copies of
realized control. Actor-controlled mobility, force allocation, contact
initiation, disengagement, bargaining, and foreign decisions must therefore use
beliefs, directly experienced events, or public/common information rather than
hidden simulator truth.

Analyst diagnostics such as belief error and contact funnels may compare these
layers. Their availability to the researcher does not make them actor-known.

## Sources

The runtime distinguishes patrol, fixed-post, civilian, social-network,
administrative, organization-member, political-elite, interpreter, and contact
channels. Each source has configurable coverage, trust, latency, correlation,
and confidence decay. Social cooperation changes the probability that a
civilian or network report is available; it does not create physical presence.
Language compatibility affects comprehension without deleting communication,
and interpreter channels remain noisy.

## Detection and target exposure

Formation detection is a source/observation model, not a combat-capability
equation. For a present target, the true-positive probability is the logistic
transform of

\[
\operatorname{logit}(p_0)
+\beta_P P_o+\beta_E E_t+\beta_L L+\beta_O O
+\beta_R R_o^{fatigue}-\beta_T T,
\]

with an additional concealment penalty for insurgent targets. In the live
implementation:

\[
P_o=
\frac{N_o^{deployable}}{N_o}
\,Q_o\,K_o\,\frac{0.5+I_o}{2},
\]

where the product is clamped to \([0,1]\), and

\[
E_t=\operatorname{clamp}(0.35+0.45O-0.25B_t).
\]

Here \(Q_o\) is observer quality, \(K_o\) cohesion, \(I_o\) information
capacity, \(O\) zone observability when available, \(B_t\) target
embeddedness, and \(R_o^{fatigue}\) is stored readiness after fatigue but
before supply and command multipliers. The terrain penalty is the locality
terrain friction divided by 2.5 and clamped.

This placement is deliberate. Observer readiness enters detection once;
availability enters through deployable search pressure; supply and command are
not silently re-applied through `effective_readiness`. Target readiness,
availability, supply, and command do **not** directly reduce the probability
that another actor detects or attacks it. A poorly supplied or resting target
is not made physically unexposed by its own lack of readiness.

When a target is absent, the source uses the false-positive model instead.
Positive and negative claims are both evidence. Positive personnel estimates
are coarse and noisy, attribution can be wrong, and a false positive does not
instantiate a phantom formation.

## Belief fusion and aging

Evidence weight combines observation confidence, source quality, source trust,
language comprehension, age decay, source dependence/correlation, and
corroboration. Contradictory reports raise the contradiction index and reduce
confidence rather than using last-write-wins. Presence beliefs may be
formation-specific, microzone-specific, node-local, or organization-level.

Belief estimates remain stored as evidence ages while confidence decays.
`information_age` reports time since the last reliable observation; it is an
analyst diagnostic, not an actor shortcut to truth.

## Organizational propagation

An observation is available at its local organization/node before headquarters
necessarily receives it. An `InformationRelay` follows the organization's command
graph toward `CMD:<organization>`. Reliability compounds across edges and
latency adds across hops. A local formation can therefore possess a fresher
presence belief than headquarters. Movement does not rewrite prior beliefs, so
departing a locality can leave stale estimates until evidence updates them.

## Contact uses beliefs; it does not resense by scan

The production `directional_pairwise` contact handler does not perform a new
detection draw merely because the contact scheduler scans again. For each
same-microzone opposing formation pair it consumes the freshest usable
formation-node or organization-level `PresenceBelief`. A presence estimate of
at least 0.5 counts as that side detecting the opponent for contact initiation
and surprise metadata.

New `observe_target` draws during contact are retained only for forced component
tests and the `legacy_symmetric` compatibility branch. This separation prevents
changing `intervals.contact` from manufacturing extra sensing opportunities.

## Research recording is a separate stochastic layer

Each process event type owns two deterministic random namespaces:

```text
process:<event_type>
recording:<event_type>
```

Latent transitions consume the process stream. Event inclusion, severity
measurement error, geocoding error, and optional false recorded events consume
the recording stream after the latent handler. Changing output mode or
recording parameters therefore must not advance the scientific transition RNG
or change the latent trajectory. False recorded events enter only the recorded
layer, never latent truth or the causal ledger.

For contact, the recording draw is still consumed for common-random-number
comparisons, but a failed latent contact opportunity cannot become a recorded
engagement.

## Outputs

The principal information/measurement outputs are:

- `observations.jsonl`: actor-facing source evidence and provenance.
- `information_relays.jsonl`: command-network transmission attempts.
- `information_diagnostics.json`: source mix, confidence, age, detection
  counts, presence beliefs, and analyst-only belief error.
- `synthetic_records.jsonl`: imperfect researcher-visible event records.
- `recording_diagnostics.json`: generated-versus-recorded measurement
  behavior.

For empirical comparison, use the recorded layer when the historical target is
itself generated by a reporting/recording process. Do not silently compare
latent model truth to an incomplete historical event dataset.
