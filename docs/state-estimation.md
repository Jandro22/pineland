# Training-period latent-state estimation

The state-estimation layer separates transition structure from uncertainty about
the current latent world. `Particle` weights are updated by a declared
observation likelihood; no structural parameter is changed by assimilation.

`SimulationParticle` wraps a live `Simulation`, so a particle fork carries the
pending scheduler queue, current time, event counter, world state, and policy
hook. Resampling assigns each child a distinct stochastic stream namespace.
The `SequentialParticleFilter` is training-only by default and rejects an
observation labeled outside its declared split before advancing any particle.

The Afghanistan development runner is
`studies/research_program/scripts/run_afghanistan_filtered_prospective_2005.py`.
It uses complete 2004 province-week cells, freezes the posterior at the
training boundary, and emits a weighted 2005 latent event-probability field
including zero-risk cells on the complete province-week surface.
It is separate from the consumed frozen-core 2005 scorer.
The command-line default is 128 posterior particles; smaller counts remain
available for bounded smoke tests through `--particles`.

Afghanistan's pre-period spatial prior uses all available 2003 district
evidence to sample fielded locality presence, fielded/clandestine composition,
and clandestine local manpower. Sourced Taliban strength is conserved as
fielded personnel plus unfielded manpower pools. The Pakistan mapping stores
both organization-level sanctuary and the required `sponsor_dependence`
relation so the existing locality-specific sanctuary operator is active.

Representative-agent convergence is outcome-blind and can be run with
`studies/research_program/scripts/run_afghanistan_resolution_convergence.py`.
It keeps the 401-district geography fixed while comparing probability-field
stability, spatial concentration, Moran's I, local reproduction, recruitment
geography, movement destinations, and organizational embeddedness.
