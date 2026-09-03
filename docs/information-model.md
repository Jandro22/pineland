# Phase 4 information model

Phase 4 makes partial information explicit without adding detailed combat. The
information chain is:

```text
true world state -> source observation -> actor/node belief -> action
```

The true state is consulted only while the environment samples a source. The
stored `Observation` contains an estimated value, confidence, source type,
timestamp, quality, provenance, target, and location. It does not contain the
underlying truth label. Analysts can compare the observation-derived belief to
truth through `information_diagnostics`; simulated actors cannot use that
diagnostic.

## Sources

The runtime distinguishes patrol, fixed-post, civilian, social-network,
administrative, organization-member, political-elite, interpreter, and contact
channels. Each source has configurable coverage, trust, latency, and a distinct
confidence-decay rate. Social cooperation changes the probability that a
civilian or network report is available; it does not create physical presence.
Language compatibility reduces effective comprehension while retaining a
nonzero transmission floor. Interpreter channels improve comprehension but
remain noisy.

## Detection and false information

Formation detection uses a bounded logit model conditioned on observer
readiness/pressure, local observability, language comprehension, target
embeddedness, and terrain. True positives and false negatives are recorded when
a target is present. False positives are observations with no
`target_formation_id`; they never instantiate an insurgent formation. The
configured attribution-error rate can assign a positive report to the wrong
organization without creating a new entity. The `information_detections`
counters are analyst diagnostics.

## Fusion and aging

Evidence weight is:

```text
observation confidence × source quality × source trust
× language comprehension × age decay × corroboration bonus
```

Control and presence beliefs use confidence-weighted updating. Contradictory
reports increase `contradiction_index` and reduce confidence rather than using
last-write-wins. Belief estimates are retained as they age, while confidence
decays. `information_age` reports the elapsed time since the last reliable
observation for an actor and locality.

## Organizational propagation

An observation is available to its local organization/node immediately. A
`InformationRelay` then follows the organization’s command graph to
`CMD:<organization>`, compounding edge reliability and adding edge plus source
latency. A local formation can therefore know about a locality before its
headquarters. Formation movement does not rewrite prior beliefs, so leaving a
locality produces stale estimates until new evidence arrives.

## Contact

The scheduler still creates candidate contacts from physical co-location. The
contact handler now samples source detections for both formations and applies a
contact hazard based on proximity, detection factor, activity, and
`contact_rate`. It records who detected whom, observation IDs, hazard, and
information asymmetry before retaining the
small inherited combat placeholder for backward compatibility. Detailed
engagement resolution remains a Phase 5 task.

## Outputs

Each run writes:

- `observations.jsonl` — first-class source observations.
- `information_relays.jsonl` — command-network transmission attempts.
- `information_diagnostics.json` — source mix, confidence, age, detection
  counts, local presence beliefs, and analyst-only belief error.

All information state uses deterministic named random streams and is covered by
the reproducibility, null-model, conservation, language, cooperation,
contradiction, relay, and scale tests.
