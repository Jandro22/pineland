# Resource-stock semantics

Pineland uses abstract resource-equivalent units for liquid economic/material
accounts. A unit is deliberately not a currency denomination. The accounting
contract is that quantities which are stocks use the same population-scale
unit and transfers do not depend on how many representative-agent tokens happen
to carry the represented population.

Person.resources is the liquid civilian stock owned by the population cohort
represented by that Person. Generation draws a heterogeneous per-capita
endowment and multiplies it by Person.weight exactly once. Any later transfer
to or from the person therefore uses Person.resources directly; multiplying
again by weight would double-scale the flow.

Household.resources is not a second account. It is the synchronized sum of the
member Person.resources values and represents the household-archetype /
kin-resource cell used by the social model. It is excluded from global stock
totals to prevent double counting.

Locality.economic_output is a population-scale productive-base/output quantity,
not a liquid account. The monthly economy process changes that base through
production, conflict damage, and depreciation. Taxation and insurgent
extraction are revenue flows derived from this population-scale output, so
their magnitudes are already independent of representative-agent resolution;
they are not additionally multiplied by civilian weights.

Foreign-state resources, organization resources, political-institution
resources, party-branch resources/patronage, local-elite broker resources, and
private diversion are explicit liquid/material accounts. Local elites begin
with a zero broker-account balance: the linked person's civilian wealth remains
owned by Person.resources and is not copied into the political ledger.

A DiasporaLink.financial_capacity is the represented migrant cohort's
remittance capacity. It is initialized from the already weighted civilian
stock. Remittances are conserved transfers from the foreign-state account to
the civilian account; no second population multiplier is applied.

Proto-organization material capital is dimensionless resource intensity. It is
computed from represented founder resources divided by represented founder
population, preserving the previous per-capita scale. On maturation,
onset_resource_fraction moves the specified fraction of founder civilian
stocks into the organization account. Startup supply then converts part of the
organization account into formation supply at the existing one-for-one abstract
material conversion. Both legs are stock transfers, not new resource creation.

Political patronage is budget redistribution. Government resources move into a
party-branch patronage stock and may then move into explicit local-elite broker
accounts. Public-service spending and patronage decay are modeled sinks/uses,
not transfers back into civilian liquid wealth. The global event ledger records
these stock deltas separately from locality productive output.
