# Phase 9: Bargaining, Settlement, Demobilization, and Recurrence

Phase 9 supplies an endogenous political route from armed conflict to durable or failed peace. It is a monthly process operating on the same organizations, persons, formations, institutions, parties, and foreign states used by earlier phases.

## Bargaining

Each government and active insurgent organization receives an expected war value, peace value, bargaining surplus, and expected future-power estimate. Battlefield strength, territorial control, violence, grievance, political capital, sanctuary, accountability, and foreign pressure enter those estimates. A positive surplus raises negotiation probability but does not guarantee talks or agreement.

Negotiation credibility depends on government accountability, insurgent discipline, foreign monitoring, and organizational fragmentation. Agreement hazards separately include mutual surplus, credibility, fragmentation, spoilers, and foreign mediation. Sponsor preferences enter faction-level consent, so sponsor and client preferences may diverge.

## Agreements and implementation

Every agreement contains six independently implemented provisions: ceasefire, security reform, political incorporation, power sharing, demobilization, and grievance redress. Each has explicit government will, insurgent will, institutional resistance, monitoring, target, progress, and status. Implementation is gradual and may advance, stall, complete, or ultimately fail.

Fragmented movements decide at faction level. Signatories enter a ceasefire while rejecting factions remain armed. Ceasefires can be violated; signing is therefore neither implementation nor conflict termination.

## DDR and political incorporation

Demobilization transfers personnel and arms out of formations into conserved demobilized stocks. It never deletes them. Political incorporation creates a descendant party and local branches while retaining configured shares of members, ideology, resources, legitimacy, organizational capital, and local network reach. The armed parent persists as a provenance record and becomes political only after full implementation.

## Recurrence

After one year of apparent peace, recurrence risk responds to unmet terms, rejecting factions, ceasefire violations, and changes in relative power. Recurrence reactivates signatory armed organizations and records the causal hazard and its components. Grievance can survive settlement and declines only as grievance-redress provisions are implemented.

## Diagnostics and experiment

`peace_diagnostics.json`, `peace_agreements.jsonl`, and `peace_transitions.jsonl` expose negotiations, provisions, signatures, violations, DDR, transformations, completion, failure, and recurrence.

`run_fragmentation_comparison` creates matched unified and fragmented scenarios. Combined starting military resources and demands are held constant, settlement opportunity and random seeds are matched, and agreement, completion, recurrence, implementation, time-to-agreement, and peace duration are measured across replications. Results validate mechanisms under priors; they are not calibrated forecasts.
