# Phase 6 organization ecology

Phase 6 separates political support, organizational capacity, and armed
strength. A dissatisfied community is not automatically an insurgency, and an
armed formation is not itself the organization that sustains it.

## State

Every armed organization carries four bounded capital stocks: social,
political, organizational, and material. It also carries ideology, lifecycle
status, ancestry, an explicit leadership agent, and an eight-dimensional
strategic phenotype: centralization, political and governance investment,
dispersion, risk tolerance, discipline, local embeddedness, and resource
dependence. These are broad organizational traits, not character simulation.

`ProtoOrganization` represents the intermediate state between mobilized social
cluster and durable armed organization. `OrganizationTransition` is the causal
and genealogical record for birth, proto-collapse, succession, split, merger,
and organizational collapse.

## Onset

Community mobilization combines grievance, social cohesion, insurgent sympathy,
and bridge reach. Repression risk lowers a probabilistic proto-organization
hazard. A second probabilistic hazard converts accumulated capital and
leadership potential into a durable organization. Most eligible clusters do
not mature. Zero hazards preserve a peaceful no-insurgency null, while an
intermediate regime produces mixed onset outcomes across seeds.

Birth draws members from the actual mobilized community, finances initial
material capacity from member contributions, creates a bounded formation, and
connects that formation to a real command node. It does not instantiate a
pre-scripted national insurgency.

## Membership, adaptation, and leadership

Recruitment depends on grievance, network exposure, ideological compatibility,
social capital, and fear. Recruits bring represented manpower, but compositional
diversity can reduce cohesion. Exit can therefore change organization and
formation size without deleting either directly.

Organization cohesion evolves from social capital, member identity variance,
and accumulated Phase 5 military losses. Phenotypes imitate apparently
successful peers imperfectly, with bounded mutation and heterogeneous learning.
Phenotype feeds command reliability, dispersion/mobility, discipline, and local
embeddedness. Leadership succession creates a new explicit leader, preserves
traits partially, and records the succession event.

## Fragmentation, merger, and collapse

Splits assign members by their real social-community and geographic structure.
Resources follow faction membership shares; formations and supply sources
follow local faction support. Child traits are inherited with mutation, and
each child receives a related but distinct leader. Nothing is divided by a
fixed 50/50 rule.

Mergers conserve members, organization resources, formations, and supply-source
ownership. Parent phenotypes blend with mutation and the merged organization
pays an initial cohesion integration cost.

Collapse can follow insolvency, cohesion failure, social-base loss, or sustained
military degradation. It releases members and disables formations but can occur
while nonzero manpower remains. Historical organizations remain in the world as
inactive genealogy nodes rather than being erased.

## Conservation and analysis

Transitions explicitly record parent/child IDs, member assignments, resource
assignments, formation assignments, inherited traits, and causal variables.
World invariants prohibit duplicate active membership and require reciprocal
person–organization membership. Existing population and supply conservation
remain active across every lifecycle operation.

`organization_ecology.json` exports lifecycle counts and reconstructable
genealogy. `organization_transitions.jsonl` provides the transition ledger.
All parameters are exposed under `SimulationConfig.organization_ecology` and
remain uncalibrated scientific priors.
