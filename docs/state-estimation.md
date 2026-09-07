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
training boundary, and emits both a latent mechanistic field and the primary
observed province-week predictive field. The latter applies the declared
Bernoulli observation operator, including its false-positive floor, on the
complete province-week surface.
It is separate from the consumed frozen-core 2005 scorer.
The command-line default is 128 posterior particles; smaller counts remain
available for bounded smoke tests through the --particles option.

Afghanistan's pre-period spatial prior has two levels: high-precision 2003
events inform occupancy/foothold, while fielded and equipped-clandestine force
mass is allocated independently conditional on that occupancy. Lower-precision
events contribute only province/background occupancy evidence. Sourced Taliban
strength is conserved as fielded personnel plus equipped clandestine fighter
equivalents; supporters are not silently counted as fighters. The Pakistan
mapping separates a spatial sponsor-links access relation from political or
resource sponsor-dependence.

Training assimilation uses short nested continuations from each latent state
to estimate P(observation | state) before applying the measurement operator.
This keeps aleatory event draws separate from epistemic state weights. The
filter raises a hard support-exhaustion diagnostic instead of silently
uniformizing an impossible posterior, and reports ESS plus distinct root
ancestors, lineage entropy, resampling count, and maximum ancestry
concentration.
An information-matched comparator scorer is prepared at
`studies/research_program/scripts/score_afghanistan_information_matched_competition.py`.
It exposes global, province/region-shrunk, persistence, temporal, spatial,
topology, and preperiod-plus-training-history baselines with the same
preperiod evidence and source-grounded geography. It requires an explicit
holdout-reveal flag and was not run during this architecture pass.
Independent terrain, transport, language, and preperiod facility/deployment
layers remain explicitly unidentified; no later-outcome proxy was substituted
for them.
Representative-agent convergence is outcome-blind and can be run with
`studies/research_program/scripts/run_afghanistan_resolution_convergence.py`.
It keeps the 401-district geography fixed while comparing probability-field
stability, spatial concentration, Moran's I, local reproduction, recruitment
geography, movement destinations, and organizational embeddedness.
