/-
Copyright (c) 2026 Pineland contributors. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: Pineland contributors
-/

import Mathlib.Data.Fin.Basic
import Mathlib.Data.Finset.Basic
import Mathlib.Algebra.BigOperators.Group.Finset.Basic
import Mathlib.Data.Set.Finite.Lemmas
import Mathlib.Algebra.Order.GroupWithZero.Basic
import Mathlib.Algebra.GroupWithZero.Units.Basic
import Mathlib.Algebra.Order.Ring.Rat
import Mathlib.Algebra.Field.Rat
import Mathlib.Data.Rat.Cast.Order

/-!
# Partner-force autonomy: deterministic formal core

This module formalizes the exact part of the partner-force framework that does
not depend on empirical Pineland behavior.

The primitive model is a finite mission-demand system:

* `technology i j` is the amount of service `i` required per unit of mission
  activity `j`;
* `mission j` is the required amount of mission activity `j`;
* `requirement i = Σ_j technology i j * mission j`;
* `indigenous i` is indigenous usable service `i`;
* `external i` is externally supplied usable service `i`;
* `supported i = indigenous i + external i`.

The formal theory deliberately separates propositions that are mathematical
consequences of these definitions from empirical claims about Pineland.
-/

namespace PartnerForce

open scoped BigOperators

section Mission

variable {Service Activity : Type}
variable [Fintype Activity]

/-- A reference mission and its fixed service-requirement technology. -/
structure MissionModel where
  technology : Service → Activity → Nat
  mission : Activity → Nat

/-- Total service requirement induced by the reference mission. -/
def requirement (M : MissionModel (Service := Service) (Activity := Activity))
    (i : Service) : Nat :=
  ∑ j : Activity, M.technology i j * M.mission j

/-- A fraction `num / den` of the reference mission is feasible when every
service can cover its correspondingly scaled requirement. This cross-multiplied
definition avoids division and therefore has no zero-denominator ambiguity. -/
def FeasibleScale (M : MissionModel (Service := Service) (Activity := Activity))
    (supply : Service → Nat) (num den : Nat) : Prop :=
  0 < den ∧ ∀ i, num * requirement M i ≤ den * supply i

/-- Full mission feasibility. -/
def FullMissionFeasible
    (M : MissionModel (Service := Service) (Activity := Activity))
    (supply : Service → Nat) : Prop :=
  ∀ i, requirement M i ≤ supply i

theorem feasibleScale_one_iff
    (M : MissionModel (Service := Service) (Activity := Activity))
    (supply : Service → Nat) :
    FeasibleScale M supply 1 1 ↔ FullMissionFeasible M supply := by
  constructor
  · intro h i
    simpa [FeasibleScale, FullMissionFeasible] using h.2 i
  · intro h
    constructor
    · decide
    · intro i
      simpa [FullMissionFeasible] using h i

end Mission

/-! ## Channel-level primitives -/

/-- Indigenous shortfall for one service channel. -/
def deficit (requirement indigenous : Nat) : Nat :=
  requirement - indigenous

section Support

variable {Service Activity : Type}
variable [Fintype Activity]

/-- Indigenous and external usable service at a common state. -/
structure SupportState where
  indigenous : Service → Nat
  external : Service → Nat

def supported (S : SupportState (Service := Service)) (i : Service) : Nat :=
  S.indigenous i + S.external i

theorem indigenous_le_supported (S : SupportState (Service := Service)) (i : Service) :
    S.indigenous i ≤ supported S i := by
  exact Nat.le_add_right _ _

/-- Organically feasible: the indigenous force can satisfy the reference mission. -/
def Autonomous
    (M : MissionModel (Service := Service) (Activity := Activity))
    (S : SupportState (Service := Service)) : Prop :=
  FullMissionFeasible M S.indigenous

/-- Supported dependence: indigenous service is insufficient, but external
augmentation makes the reference mission feasible. -/
def Dependent
    (M : MissionModel (Service := Service) (Activity := Activity))
    (S : SupportState (Service := Service)) : Prop :=
  ¬ FullMissionFeasible M S.indigenous ∧ FullMissionFeasible M (supported S)

/-- Overmatched: even supported service cannot satisfy the reference mission. -/
def Overmatched
    (M : MissionModel (Service := Service) (Activity := Activity))
    (S : SupportState (Service := Service)) : Prop :=
  ¬ FullMissionFeasible M (supported S)

theorem support_monotone_full_mission
    (M : MissionModel (Service := Service) (Activity := Activity))
    (S : SupportState (Service := Service)) :
    FullMissionFeasible M S.indigenous →
      FullMissionFeasible M (supported S) := by
  intro h i
  exact Nat.le_trans (h i) (indigenous_le_supported S i)

theorem autonomous_not_dependent
    (M : MissionModel (Service := Service) (Activity := Activity))
    (S : SupportState (Service := Service)) :
    Autonomous M S → ¬ Dependent M S := by
  intro ha hd
  exact hd.1 ha

theorem autonomous_not_overmatched
    (M : MissionModel (Service := Service) (Activity := Activity))
    (S : SupportState (Service := Service)) :
    Autonomous M S → ¬ Overmatched M S := by
  intro ha ho
  exact ho (support_monotone_full_mission M S ha)

theorem dependent_not_overmatched
    (M : MissionModel (Service := Service) (Activity := Activity))
    (S : SupportState (Service := Service)) :
    Dependent M S → ¬ Overmatched M S := by
  intro hd ho
  exact ho hd.2

/-- Exact regime partition: every world lies in at least one of the three
structural regimes. Pairwise-disjointness is established by the preceding
theorems. -/
theorem regime_exhaustive
    (M : MissionModel (Service := Service) (Activity := Activity))
    (S : SupportState (Service := Service)) :
    Autonomous M S ∨ Dependent M S ∨ Overmatched M S := by
  classical
  by_cases ha : FullMissionFeasible M S.indigenous
  · exact Or.inl ha
  · by_cases hs : FullMissionFeasible M (supported S)
    · exact Or.inr (Or.inl ⟨ha, hs⟩)
    · exact Or.inr (Or.inr hs)

/-- Full mission feasibility is monotone under an arbitrary componentwise
increase in usable service, not only under the particular support decomposition. -/
theorem feasibility_monotone
    (M : MissionModel (Service := Service) (Activity := Activity))
    {a b : Service → Nat}
    (hab : ∀ i, a i ≤ b i) :
    FullMissionFeasible M a → FullMissionFeasible M b := by
  intro ha i
  exact Nat.le_trans (ha i) (hab i)

/-- Supported feasibility is exactly equivalent to external augmentation
covering every indigenous service deficit. -/
theorem supported_feasible_iff_external_covers_deficit
    (M : MissionModel (Service := Service) (Activity := Activity))
    (S : SupportState (Service := Service)) :
    FullMissionFeasible M (supported S) ↔
      ∀ i, deficit (requirement M i) (S.indigenous i) ≤ S.external i := by
  constructor
  · intro h i
    exact (Nat.sub_le_iff_le_add').2 (h i)
  · intro h i
    exact (Nat.sub_le_iff_le_add').1 (h i)

/-- Organic autonomy is equivalent to having zero indigenous deficit in every
service channel. -/
theorem autonomous_iff_all_deficits_zero
    (M : MissionModel (Service := Service) (Activity := Activity))
    (S : SupportState (Service := Service)) :
    Autonomous M S ↔
      ∀ i, deficit (requirement M i) (S.indigenous i) = 0 := by
  constructor
  · intro h i
    exact Nat.sub_eq_zero_of_le (h i)
  · intro h i
    exact Nat.sub_eq_zero_iff_le.mp (h i)

/-- In a dependent regime, at least one service has a strictly positive
indigenous deficit. -/
theorem dependent_has_positive_deficit
    (M : MissionModel (Service := Service) (Activity := Activity))
    (S : SupportState (Service := Service))
    (h : Dependent M S) :
    ∃ i, 0 < deficit (requirement M i) (S.indigenous i) := by
  classical
  have hex : ∃ i, ¬ requirement M i ≤ S.indigenous i :=
    Classical.not_forall.mp h.1
  obtain ⟨i, hi⟩ := hex
  refine ⟨i, ?_⟩
  exact Nat.sub_pos_iff_lt.mpr (Nat.lt_of_not_ge hi)

/-- In a dependent regime, external support covers every service deficit. -/
theorem dependent_external_covers_all_deficits
    (M : MissionModel (Service := Service) (Activity := Activity))
    (S : SupportState (Service := Service))
    (h : Dependent M S) :
    ∀ i, deficit (requirement M i) (S.indigenous i) ≤ S.external i := by
  exact (supported_feasible_iff_external_covers_deficit M S).mp h.2

end Support

section ChannelAccounting

/-- The part of external support that can actually close an indigenous
shortfall. Support beyond the shortfall is redundant for full-mission
feasibility in the fixed-requirements model. -/
def usefulExternal (requirement indigenous external : Nat) : Nat :=
  min external (deficit requirement indigenous)

/-- External support delivered beyond the amount needed to close the current
indigenous deficit in this fixed-requirement channel. -/
def redundantExternal (requirement indigenous external : Nat) : Nat :=
  external - usefulExternal requirement indigenous external

theorem usefulExternal_le_external (r k e : Nat) :
    usefulExternal r k e ≤ e := by
  exact Nat.min_le_left _ _

theorem usefulExternal_le_deficit (r k e : Nat) :
    usefulExternal r k e ≤ deficit r k := by
  exact Nat.min_le_right _ _

theorem no_deficit_no_useful_external {r k e : Nat} (h : r ≤ k) :
    usefulExternal r k e = 0 := by
  simp [usefulExternal, deficit, Nat.sub_eq_zero_of_le h]

theorem zero_external_zero_useful (r k : Nat) :
    usefulExternal r k 0 = 0 := by
  simp [usefulExternal]

theorem usefulExternal_eq_deficit_of_covers {r k e : Nat}
    (h : deficit r k ≤ e) :
    usefulExternal r k e = deficit r k := by
  exact Nat.min_eq_right h

theorem usefulExternal_eq_external_of_external_le_deficit {r k e : Nat}
    (h : e ≤ deficit r k) :
    usefulExternal r k e = e := by
  exact Nat.min_eq_left h

/-- Every unit of external support decomposes exactly into a deficit-closing
part and a redundant-at-the-margin part. -/
theorem useful_add_redundant_eq_external (r k e : Nat) :
    usefulExternal r k e + redundantExternal r k e = e := by
  unfold redundantExternal
  exact Nat.add_sub_of_le (usefulExternal_le_external r k e)

theorem redundantExternal_eq_zero_of_external_le_deficit {r k e : Nat}
    (h : e ≤ deficit r k) :
    redundantExternal r k e = 0 := by
  rw [redundantExternal, usefulExternal_eq_external_of_external_le_deficit h]
  exact Nat.sub_self e

/-- A channel is deficient for the full mission when indigenous usable service
is below the requirement.  This is deliberately distinct from a *bottleneck*,
which is the channel with the minimum supply/requirement ratio. -/
def Deficient (requirement indigenous : Nat) : Prop :=
  indigenous < requirement

theorem positive_deficit_of_deficient {r k : Nat} (h : Deficient r k) :
    0 < deficit r k := by
  exact Nat.sub_pos_iff_lt.mpr h

theorem not_deficient_iff_no_deficit (r k : Nat) :
    ¬ Deficient r k ↔ deficit r k = 0 := by
  constructor
  · intro h
    apply Nat.sub_eq_zero_of_le
    exact Nat.le_of_not_gt h
  · intro h hk
    have hp : 0 < deficit r k := positive_deficit_of_deficient hk
    rw [h] at hp
    exact (Nat.lt_irrefl 0) hp

section DependentChannelConsequences

variable {Service Activity : Type}
variable [Fintype Activity]

/-- In a supported-dependent world at least one channel receives strictly
positive *useful* external substitution, not merely positive gross support. -/
theorem dependent_has_positive_useful_external
    (M : MissionModel (Service := Service) (Activity := Activity))
    (S : SupportState (Service := Service))
    (hd : Dependent M S) :
    ∃ i, 0 < usefulExternal (requirement M i) (S.indigenous i) (S.external i) := by
  obtain ⟨i, hdef⟩ := dependent_has_positive_deficit M S hd
  have hcover : deficit (requirement M i) (S.indigenous i) ≤ S.external i :=
    dependent_external_covers_all_deficits M S hd i
  refine ⟨i, ?_⟩
  rw [usefulExternal_eq_deficit_of_covers hcover]
  exact hdef

end DependentChannelConsequences

end ChannelAccounting

section Bottleneck

variable {Service : Type}

/-- At least one service is actually required by the reference mission.  Zero
demand in other channels is allowed and those channels do not constrain the
mission scale. -/
def HasDemand (demand : Service → Nat) : Prop :=
  ∃ i, 0 < demand i

/-- Change of measurement units for each service channel.  Supply and demand
must be rescaled by the same positive factor within a channel. -/
def rescaleVector (scale x : Service → Nat) (i : Service) : Nat :=
  scale i * x i

/-- Exact rational service-to-requirement ratio.  This definition is used only
in the positive-demand bottleneck theory below, so division by zero never enters
the corresponding theorems. -/
def serviceRatio (supply demand : Service → Nat) (i : Service) : Rat :=
  (supply i : Rat) / (demand i : Rat)

/-- Exact dynamic condition for channel-level autonomy improvement.  Between
two states with positive demand, the later indigenous service-to-demand ratio
is larger exactly when indigenous service growth outruns demand growth in the
cross-multiplied sense.  This is the formal core of the empirical distinction
between capacity-building support and a demand ratchet. -/
theorem serviceRatio_lt_iff_capacity_growth_beats_demand
    {supplyBefore demandBefore supplyAfter demandAfter : Service → Nat}
    {i : Service}
    (hBefore : 0 < demandBefore i) (hAfter : 0 < demandAfter i) :
    serviceRatio supplyBefore demandBefore i <
        serviceRatio supplyAfter demandAfter i ↔
      supplyBefore i * demandAfter i < supplyAfter i * demandBefore i := by
  unfold serviceRatio
  have hdb : (0 : Rat) < (demandBefore i : Rat) := Nat.cast_pos.2 hBefore
  have hda : (0 : Rat) < (demandAfter i : Rat) := Nat.cast_pos.2 hAfter
  rw [div_lt_div_iff₀ hdb hda]
  exact_mod_cast Iff.rfl

/-- `i` is a bottleneck exactly when it has positive demand and no other
positively demanded service has a smaller supply/requirement ratio. -/
def Bottleneck (supply demand : Service → Nat) (i : Service) : Prop :=
  0 < demand i ∧
    ∀ j, 0 < demand j → serviceRatio supply demand i ≤ serviceRatio supply demand j

/-- Every finite service system with at least one positively demanded channel
has a bottleneck among its positively demanded channels. -/
theorem bottleneck_exists [Finite Service]
    (supply demand : Service → Nat)
    (hactive : HasDemand demand) :
    ∃ i, Bottleneck supply demand i := by
  classical
  let active : Set Service := {i | 0 < demand i}
  have hfinite : active.Finite := Set.toFinite _
  have hnonempty : active.Nonempty := by
    rcases hactive with ⟨i, hi⟩
    exact ⟨i, hi⟩
  obtain ⟨i, _, hi⟩ :=
    Set.exists_min_image active (serviceRatio supply demand) hfinite hnonempty
  have hiPos : 0 < demand i := by
    simpa [active] using (show i ∈ active from ‹i ∈ active›)
  refine ⟨i, hiPos, ?_⟩
  intro j hj
  apply hi j
  simpa [active] using hj

/-- Covering a positive demand is equivalent to the corresponding exact
service ratio being at least one. -/
theorem one_le_serviceRatio_iff {supply demand : Service → Nat} {i : Service}
    (hpos : 0 < demand i) :
    (1 : Rat) ≤ serviceRatio supply demand i ↔ demand i ≤ supply i := by
  unfold serviceRatio
  have hd : (0 : Rat) < (demand i : Rat) := Nat.cast_pos.2 hpos
  rw [le_div_iff₀ hd]
  constructor
  · intro h
    have hnat : 1 * demand i ≤ supply i := by
      exact_mod_cast h
    simpa using hnat
  · intro h
    simpa using (Nat.cast_le.2 h : (demand i : Rat) ≤ supply i)

/-- Weakest-link theorem: if a genuine minimum-ratio bottleneck can cover its
own positive requirement, then every positively demanded service can cover its
requirement. -/
theorem bottleneck_cover_implies_all_cover
    (supply demand : Service → Nat) {i : Service}
    (hb : Bottleneck supply demand i)
    (hi : demand i ≤ supply i) :
    ∀ j, 0 < demand j → demand j ≤ supply j := by
  intro j hj
  have hone_i : (1 : Rat) ≤ serviceRatio supply demand i :=
    (one_le_serviceRatio_iff hb.1).2 hi
  have hratio : serviceRatio supply demand i ≤ serviceRatio supply demand j := hb.2 j hj
  have hone_j : (1 : Rat) ≤ serviceRatio supply demand j := le_trans hone_i hratio
  exact (one_le_serviceRatio_iff hj).1 hone_j

/-- Exact weakest-link equivalence for an all-positive-demand system: full
mission feasibility is determined by any bottleneck service alone. -/
theorem fullMissionFeasible_iff_bottleneck_covers
    {Activity : Type} [Fintype Activity]
    (M : MissionModel (Service := Service) (Activity := Activity))
    (supply : Service → Nat)
    {i : Service} (hb : Bottleneck supply (requirement M) i) :
    FullMissionFeasible M supply ↔ requirement M i ≤ supply i := by
  constructor
  · intro h
    exact h i
  · intro hi j
    by_cases hj : requirement M j = 0
    · simp [hj]
    · exact bottleneck_cover_implies_all_cover supply (requirement M) hb hi j
        (Nat.pos_of_ne_zero hj)

/-- Whenever at least one service is positively required, a bottleneck exists
and full mission feasibility has a finite weakest-link witness. -/
theorem fullMissionFeasible_has_bottleneck_characterization
    {Activity : Type} [Fintype Activity]
    [Finite Service]
    (M : MissionModel (Service := Service) (Activity := Activity))
    (supply : Service → Nat)
    (hactive : HasDemand (requirement M)) :
    ∃ i, Bottleneck supply (requirement M) i ∧
      (FullMissionFeasible M supply ↔ requirement M i ≤ supply i) := by
  obtain ⟨i, hb⟩ := bottleneck_exists supply (requirement M) hactive
  exact ⟨i, hb, fullMissionFeasible_iff_bottleneck_covers M supply hb⟩

/-- A canonical (classically chosen) bottleneck witness. The numerical ratio is
independent of which tied bottleneck is selected; see
`serviceRatio_eq_of_bottlenecks`. -/
noncomputable def chosenBottleneck [Finite Service]
    (supply demand : Service → Nat) (hactive : HasDemand demand) : Service :=
  Classical.choose (bottleneck_exists supply demand hactive)

theorem chosenBottleneck_spec [Finite Service]
    (supply demand : Service → Nat) (hactive : HasDemand demand) :
    Bottleneck supply demand (chosenBottleneck supply demand hactive) :=
  Classical.choose_spec (bottleneck_exists supply demand hactive)

/-- Tied bottlenecks have exactly the same service ratio, so the minimum ratio
is mathematically well-defined even if its witnessing service is not unique. -/
theorem serviceRatio_eq_of_bottlenecks
    (supply demand : Service → Nat) {i j : Service}
    (hi : Bottleneck supply demand i) (hj : Bottleneck supply demand j) :
    serviceRatio supply demand i = serviceRatio supply demand j := by
  apply le_antisymm
  · exact hi.2 j hj.1
  · exact hj.2 i hi.1

/-- Exact minimum service-to-requirement ratio.  This is the formal `q` used
by the deterministic mission-feasibility theory. -/
noncomputable def missionScale [Finite Service]
    (supply demand : Service → Nat) (hactive : HasDemand demand) : Rat :=
  serviceRatio supply demand (chosenBottleneck supply demand hactive)

theorem missionScale_le_serviceRatio [Finite Service]
    (supply demand : Service → Nat) (hactive : HasDemand demand)
    (j : Service) (hj : 0 < demand j) :
    missionScale supply demand hactive ≤ serviceRatio supply demand j := by
  exact (chosenBottleneck_spec supply demand hactive).2 j hj

theorem missionScale_eq_serviceRatio_of_bottleneck [Finite Service]
    (supply demand : Service → Nat) (hactive : HasDemand demand)
    {i : Service} (hi : Bottleneck supply demand i) :
    missionScale supply demand hactive = serviceRatio supply demand i := by
  exact serviceRatio_eq_of_bottlenecks supply demand
    (chosenBottleneck_spec supply demand hactive) hi

/-- Direct requirement-vector feasibility, independent of any particular
mission model used to generate the vector. -/
def RequirementFeasible (supply demand : Service → Nat) : Prop :=
  ∀ i, demand i ≤ supply i

/-- If no service is positively demanded, every channel demand is exactly zero. -/
theorem not_hasDemand_iff_all_zero (demand : Service → Nat) :
    ¬ HasDemand demand ↔ ∀ i, demand i = 0 := by
  constructor
  · intro h i
    apply Nat.eq_zero_of_not_pos
    intro hi
    exact h ⟨i, hi⟩
  · intro h hex
    obtain ⟨i, hi⟩ := hex
    rw [h i] at hi
    exact (Nat.lt_irrefl 0) hi

/-- The all-zero-demand edge case is vacuously mission-feasible.  `missionScale`
is intentionally reserved for the nontrivial case `HasDemand demand`. -/
theorem requirementFeasible_of_not_hasDemand
    (supply demand : Service → Nat) (h : ¬ HasDemand demand) :
    RequirementFeasible supply demand := by
  have hz := (not_hasDemand_iff_all_zero demand).1 h
  intro i
  simp [hz i]

/-- The minimum-ratio scale crosses one exactly when every positive service
requirement is covered. -/
theorem one_le_missionScale_iff_requirementFeasible
    [Finite Service]
    (supply demand : Service → Nat) (hactive : HasDemand demand) :
    (1 : Rat) ≤ missionScale supply demand hactive ↔ RequirementFeasible supply demand := by
  let i := chosenBottleneck supply demand hactive
  have hb : Bottleneck supply demand i := chosenBottleneck_spec _ _ hactive
  have hq : missionScale supply demand hactive = serviceRatio supply demand i := rfl
  rw [hq, one_le_serviceRatio_iff hb.1]
  constructor
  · intro hi j
    by_cases hj : demand j = 0
    · simp [hj]
    · exact bottleneck_cover_implies_all_cover supply demand hb hi j (Nat.pos_of_ne_zero hj)
  · intro h
    exact h i

/-- The core scalar theorem: when at least one service is positively demanded,
`q ≥ 1` if and only if the full reference mission is feasible. Zero-demand
channels are nonbinding. -/
theorem one_le_missionScale_iff_fullMissionFeasible
    {Activity : Type} [Fintype Activity]
    [Finite Service]
    (M : MissionModel (Service := Service) (Activity := Activity))
    (supply : Service → Nat)
    (hactive : HasDemand (requirement M)) :
    (1 : Rat) ≤ missionScale supply (requirement M) hactive ↔
      FullMissionFeasible M supply := by
  exact one_le_missionScale_iff_requirementFeasible supply (requirement M) hactive

/-- Equivalently, `q < 1` exactly characterizes structural mission
infeasibility. -/
theorem missionScale_lt_one_iff_not_fullMissionFeasible
    {Activity : Type} [Fintype Activity]
    [Finite Service]
    (M : MissionModel (Service := Service) (Activity := Activity))
    (supply : Service → Nat)
    (hactive : HasDemand (requirement M)) :
    missionScale supply (requirement M) hactive < (1 : Rat) ↔
      ¬ FullMissionFeasible M supply := by
  rw [← not_le, one_le_missionScale_iff_fullMissionFeasible M supply hactive]

/-- Increasing usable supply in any combination of channels cannot reduce an
individual service ratio. -/
theorem serviceRatio_mono_supply
    {a b demand : Service → Nat} {i : Service}
    (hpos : 0 < demand i) (hab : a i ≤ b i) :
    serviceRatio a demand i ≤ serviceRatio b demand i := by
  unfold serviceRatio
  have hd : (0 : Rat) < (demand i : Rat) := Nat.cast_pos.2 hpos
  apply (div_le_div_iff₀ hd hd).2
  have habq : (a i : Rat) ≤ (b i : Rat) := Nat.cast_le.2 hab
  exact mul_le_mul_of_nonneg_right habq hd.le

/-- A positive unit change leaves an individual service ratio exactly
unchanged. -/
theorem serviceRatio_rescale_invariant
    (scale supply demand : Service → Nat) (i : Service)
    (hscale : 0 < scale i) :
    serviceRatio (rescaleVector scale supply) (rescaleVector scale demand) i =
      serviceRatio supply demand i := by
  unfold serviceRatio rescaleVector
  simp only [Nat.cast_mul]
  rw [mul_div_mul_left]
  exact (Nat.cast_pos.2 hscale).ne'

theorem hasDemand_rescale
    (scale demand : Service → Nat) (hscale : ∀ i, 0 < scale i)
    (hactive : HasDemand demand) :
    HasDemand (rescaleVector scale demand) := by
  obtain ⟨i, hi⟩ := hactive
  exact ⟨i, Nat.mul_pos (hscale i) hi⟩

/-- A positive change of service units preserves bottleneck identity. -/
theorem bottleneck_rescale
    (scale supply demand : Service → Nat) (hscale : ∀ i, 0 < scale i)
    {i : Service} (hi : Bottleneck supply demand i) :
    Bottleneck (rescaleVector scale supply) (rescaleVector scale demand) i := by
  constructor
  · exact Nat.mul_pos (hscale i) hi.1
  · intro j hjScaled
    have hj : 0 < demand j := Nat.pos_of_mul_pos_left hjScaled
    rw [serviceRatio_rescale_invariant scale supply demand i (hscale i),
      serviceRatio_rescale_invariant scale supply demand j (hscale j)]
    exact hi.2 j hj

/-- The system mission scale `q` is dimensionless: simultaneous positive
rescaling of supply and demand within each service channel leaves it unchanged. -/
theorem missionScale_rescale_invariant [Finite Service]
    (scale supply demand : Service → Nat)
    (hscale : ∀ i, 0 < scale i)
    (hactive : HasDemand demand) :
    missionScale (rescaleVector scale supply) (rescaleVector scale demand)
        (hasDemand_rescale scale demand hscale hactive) =
      missionScale supply demand hactive := by
  let i := chosenBottleneck supply demand hactive
  have hi : Bottleneck supply demand i := chosenBottleneck_spec _ _ hactive
  have hiScaled : Bottleneck (rescaleVector scale supply) (rescaleVector scale demand) i :=
    bottleneck_rescale scale supply demand hscale hi
  calc
    missionScale (rescaleVector scale supply) (rescaleVector scale demand)
        (hasDemand_rescale scale demand hscale hactive)
        = serviceRatio (rescaleVector scale supply) (rescaleVector scale demand) i :=
          missionScale_eq_serviceRatio_of_bottleneck _ _ _ hiScaled
    _ = serviceRatio supply demand i :=
          serviceRatio_rescale_invariant scale supply demand i (hscale i)
    _ = missionScale supply demand hactive := by
          symm
          exact missionScale_eq_serviceRatio_of_bottleneck _ _ _ hi

/-- Increasing usable service componentwise cannot reduce the system mission
scale `q`. -/
theorem missionScale_mono_supply [Finite Service]
    {a b demand : Service → Nat} (hactive : HasDemand demand)
    (hab : ∀ i, a i ≤ b i) :
    missionScale a demand hactive ≤ missionScale b demand hactive := by
  let ib := chosenBottleneck b demand hactive
  have hb : Bottleneck b demand ib := chosenBottleneck_spec _ _ hactive
  calc
    missionScale a demand hactive
        ≤ serviceRatio a demand ib := missionScale_le_serviceRatio a demand hactive ib hb.1
    _ ≤ serviceRatio b demand ib := serviceRatio_mono_supply hb.1 (hab ib)
    _ = missionScale b demand hactive := rfl

/-- Exact optimization characterization of `q`: for a positive denominator,
the rational mission fraction `num / den` is feasible exactly when it is no
larger than the minimum service ratio. -/
theorem feasibleScale_iff_ratio_le_missionScale
    {Activity : Type} [Fintype Activity]
    [Finite Service]
    (M : MissionModel (Service := Service) (Activity := Activity))
    (supply : Service → Nat)
    (hactive : HasDemand (requirement M))
    (num den : Nat) (hden : 0 < den) :
    FeasibleScale M supply num den ↔
      (num : Rat) / (den : Rat) ≤ missionScale supply (requirement M) hactive := by
  constructor
  · intro h
    let i := chosenBottleneck supply (requirement M) hactive
    have hb : Bottleneck supply (requirement M) i := chosenBottleneck_spec _ _ hactive
    have hreq : 0 < requirement M i := hb.1
    have hdq : (0 : Rat) < (den : Rat) := Nat.cast_pos.2 hden
    have hrq : (0 : Rat) < (requirement M i : Rat) := Nat.cast_pos.2 hreq
    have hcrossNat : num * requirement M i ≤ supply i * den := by
      simpa [Nat.mul_comm] using h.2 i
    have hcrossRat : (num : Rat) * (requirement M i : Rat) ≤
        (supply i : Rat) * (den : Rat) := by
      exact_mod_cast hcrossNat
    have hratio : (num : Rat) / (den : Rat) ≤
        (supply i : Rat) / (requirement M i : Rat) :=
      (div_le_div_iff₀ hdq hrq).2 hcrossRat
    simpa [missionScale, serviceRatio, i] using hratio
  · intro hq
    refine ⟨hden, ?_⟩
    intro i
    by_cases hzero : requirement M i = 0
    · simp [hzero]
    · have hreq : 0 < requirement M i := Nat.pos_of_ne_zero hzero
      have hdq : (0 : Rat) < (den : Rat) := Nat.cast_pos.2 hden
      have hrq : (0 : Rat) < (requirement M i : Rat) := Nat.cast_pos.2 hreq
      have hmin : missionScale supply (requirement M) hactive ≤
          serviceRatio supply (requirement M) i :=
        missionScale_le_serviceRatio supply (requirement M) hactive i hreq
      have hratio : (num : Rat) / (den : Rat) ≤
          (supply i : Rat) / (requirement M i : Rat) := le_trans hq hmin
      have hcrossRat : (num : Rat) * (requirement M i : Rat) ≤
          (supply i : Rat) * (den : Rat) := by
        exact (div_le_div_iff₀ hdq hrq).1 hratio
      have hcrossNat : num * requirement M i ≤ supply i * den := by
        exact_mod_cast hcrossRat
      simpa [Nat.mul_comm] using hcrossNat

/-- `q` is therefore an upper bound on every feasible rational mission scale. -/
theorem feasibleScale_le_missionScale
    {Activity : Type} [Fintype Activity]
    [Finite Service]
    (M : MissionModel (Service := Service) (Activity := Activity))
    (supply : Service → Nat)
    (hactive : HasDemand (requirement M))
    {num den : Nat} (h : FeasibleScale M supply num den) :
    (num : Rat) / (den : Rat) ≤ missionScale supply (requirement M) hactive := by
  exact (feasibleScale_iff_ratio_le_missionScale M supply hactive num den h.1).1 h

section RegimesByScale

variable {Activity : Type} [Fintype Activity]
variable [Finite Service]

theorem autonomous_iff_one_le_indigenousScale
    (M : MissionModel (Service := Service) (Activity := Activity))
    (S : SupportState (Service := Service))
    (hactive : HasDemand (requirement M)) :
    Autonomous M S ↔
      (1 : Rat) ≤ missionScale S.indigenous (requirement M) hactive := by
  exact (one_le_missionScale_iff_fullMissionFeasible M S.indigenous hactive).symm

theorem overmatched_iff_supportedScale_lt_one
    (M : MissionModel (Service := Service) (Activity := Activity))
    (S : SupportState (Service := Service))
    (hactive : HasDemand (requirement M)) :
    Overmatched M S ↔
      missionScale (supported S) (requirement M) hactive < (1 : Rat) := by
  exact (missionScale_lt_one_iff_not_fullMissionFeasible M (supported S) hactive).symm

theorem dependent_iff_scale_crosses_one
    (M : MissionModel (Service := Service) (Activity := Activity))
    (S : SupportState (Service := Service))
    (hactive : HasDemand (requirement M)) :
    Dependent M S ↔
      missionScale S.indigenous (requirement M) hactive < (1 : Rat) ∧
      (1 : Rat) ≤ missionScale (supported S) (requirement M) hactive := by
  constructor
  · intro h
    exact ⟨
      (missionScale_lt_one_iff_not_fullMissionFeasible M S.indigenous hactive).2 h.1,
      (one_le_missionScale_iff_fullMissionFeasible M (supported S) hactive).2 h.2⟩
  · rintro ⟨hi, hs⟩
    exact ⟨
      (missionScale_lt_one_iff_not_fullMissionFeasible M S.indigenous hactive).1 hi,
      (one_le_missionScale_iff_fullMissionFeasible M (supported S) hactive).1 hs⟩

/-- Direct formal statement that partner support cannot reduce `q`. -/
theorem indigenousScale_le_supportedScale
    (M : MissionModel (Service := Service) (Activity := Activity))
    (S : SupportState (Service := Service))
    (hactive : HasDemand (requirement M)) :
    missionScale S.indigenous (requirement M) hactive ≤
      missionScale (supported S) (requirement M) hactive := by
  apply missionScale_mono_supply hactive
  intro i
  exact indigenous_le_supported S i

end RegimesByScale

section SupportLift

/-- Feasible mission fraction with surplus above full mission fulfillment
discarded. This keeps excess capacity from being mistaken for greater
autonomy once the reference mission is already fully coverable. -/
def cappedScale (q : Rat) : Rat := min q 1

theorem cappedScale_mono {q₁ q₂ : Rat} (h : q₁ ≤ q₂) :
    cappedScale q₁ ≤ cappedScale q₂ := by
  exact min_le_min h le_rfl

theorem cappedScale_le_one (q : Rat) : cappedScale q ≤ 1 := by
  exact min_le_right _ _

theorem serviceRatio_nonneg (supply demand : Service → Nat) (i : Service) :
    0 ≤ serviceRatio supply demand i := by
  unfold serviceRatio
  have hs : (0 : Rat) ≤ (supply i : Rat) := by
    exact_mod_cast (Nat.zero_le (supply i))
  have hd : (0 : Rat) ≤ (demand i : Rat) := by
    exact_mod_cast (Nat.zero_le (demand i))
  exact div_nonneg hs hd

theorem missionScale_nonneg [Finite Service]
    (supply demand : Service → Nat) (hactive : HasDemand demand) :
    0 ≤ missionScale supply demand hactive := by
  unfold missionScale
  exact serviceRatio_nonneg supply demand _

theorem cappedScale_nonneg {q : Rat} (hq : 0 ≤ q) : 0 ≤ cappedScale q := by
  unfold cappedScale
  exact le_min hq (by norm_num)

/-- Absolute increase in feasible reference-mission fraction attributable to
support, after capping both branches at complete mission feasibility. -/
def supportLift (qIndigenous qSupported : Rat) : Rat :=
  cappedScale qSupported - cappedScale qIndigenous

theorem supportLift_nonneg {qIndigenous qSupported : Rat}
    (h : qIndigenous ≤ qSupported) :
    0 ≤ supportLift qIndigenous qSupported := by
  exact sub_nonneg.mpr (cappedScale_mono h)

theorem supportLift_le_one {qIndigenous qSupported : Rat}
    (hi : 0 ≤ qIndigenous) :
    supportLift qIndigenous qSupported ≤ 1 := by
  unfold supportLift
  have hci : 0 ≤ cappedScale qIndigenous := cappedScale_nonneg hi
  calc
    cappedScale qSupported - cappedScale qIndigenous ≤ cappedScale qSupported :=
      sub_le_self _ hci
    _ ≤ 1 := cappedScale_le_one _

/-- Once the indigenous force already covers the whole reference mission,
additional supported surplus has zero bounded mission-feasibility lift. -/
theorem supportLift_eq_zero_of_autonomous
    {qIndigenous qSupported : Rat}
    (hi : 1 ≤ qIndigenous) (hmon : qIndigenous ≤ qSupported) :
    supportLift qIndigenous qSupported = 0 := by
  have hs : 1 ≤ qSupported := le_trans hi hmon
  simp [supportLift, cappedScale, min_eq_right hi, min_eq_right hs]

/-- In the supported-dependent regime, bounded support lift is exactly the
indigenous mission shortfall `1 - q⁻`, and is strictly positive. -/
theorem supportLift_of_dependent_scale
    {qIndigenous qSupported : Rat}
    (hi : qIndigenous < 1) (hs : 1 ≤ qSupported) :
    supportLift qIndigenous qSupported = 1 - qIndigenous ∧
      0 < supportLift qIndigenous qSupported := by
  have hminI : cappedScale qIndigenous = qIndigenous := by
    exact min_eq_left hi.le
  have hminS : cappedScale qSupported = 1 := by
    exact min_eq_right hs
  constructor
  · simp [supportLift, hminI, hminS]
  · rw [supportLift, hminI, hminS]
    exact sub_pos.mpr hi

section ModelSupportLift

variable {Activity : Type} [Fintype Activity]
variable [Finite Service]

/-- Bounded structural mission-feasibility contribution of external support at
a common state. -/
noncomputable def structuralSupportLift
    (M : MissionModel (Service := Service) (Activity := Activity))
    (S : SupportState (Service := Service))
    (hactive : HasDemand (requirement M)) : Rat :=
  supportLift
    (missionScale S.indigenous (requirement M) hactive)
    (missionScale (supported S) (requirement M) hactive)

theorem structuralSupportLift_nonneg
    (M : MissionModel (Service := Service) (Activity := Activity))
    (S : SupportState (Service := Service))
    (hactive : HasDemand (requirement M)) :
    0 ≤ structuralSupportLift M S hactive := by
  unfold structuralSupportLift
  exact supportLift_nonneg (indigenousScale_le_supportedScale M S hactive)

theorem structuralSupportLift_le_one
    (M : MissionModel (Service := Service) (Activity := Activity))
    (S : SupportState (Service := Service))
    (hactive : HasDemand (requirement M)) :
    structuralSupportLift M S hactive ≤ 1 := by
  unfold structuralSupportLift
  exact supportLift_le_one (missionScale_nonneg S.indigenous (requirement M) hactive)

theorem structuralSupportLift_eq_zero_of_autonomous
    (M : MissionModel (Service := Service) (Activity := Activity))
    (S : SupportState (Service := Service))
    (hactive : HasDemand (requirement M))
    (ha : Autonomous M S) :
    structuralSupportLift M S hactive = 0 := by
  unfold structuralSupportLift
  have hi : (1 : Rat) ≤ missionScale S.indigenous (requirement M) hactive :=
    (autonomous_iff_one_le_indigenousScale M S hactive).1 ha
  exact supportLift_eq_zero_of_autonomous hi
    (indigenousScale_le_supportedScale M S hactive)

theorem structuralSupportLift_pos_of_dependent
    (M : MissionModel (Service := Service) (Activity := Activity))
    (S : SupportState (Service := Service))
    (hactive : HasDemand (requirement M))
    (hd : Dependent M S) :
    0 < structuralSupportLift M S hactive := by
  unfold structuralSupportLift
  have hs := (dependent_iff_scale_crosses_one M S hactive).1 hd
  exact (supportLift_of_dependent_scale hs.1 hs.2).2

end ModelSupportLift

end SupportLift

end Bottleneck

section Buffers

/-!
Buffers are state variables, not universal capability dimensions. They are
appropriate only for physically storable resources such as trained reserves or
supply inventories.
-/

/-- One discrete stock-flow update. Natural-number subtraction is truncated at
zero, matching an inventory that cannot become physically negative. -/
def bufferStep (stock production external consumption : Nat) : Nat :=
  stock + production + external - consumption

/-- A buffer does not decline when current consumption is no greater than
current replenishment. -/
theorem buffer_nondec_of_consumption_le_replenishment
    {b p e c : Nat} (h : c ≤ p + e) :
    b ≤ bufferStep b p e c := by
  unfold bufferStep
  have hc : c ≤ b + p + e := by
    calc
      c ≤ p + e := h
      _ ≤ b + (p + e) := Nat.le_add_left _ _
      _ = b + p + e := by simp [Nat.add_assoc]
  have hbc : b + c ≤ b + p + e := by
    calc
      b + c ≤ b + (p + e) := Nat.add_le_add_left h b
      _ = b + p + e := by simp [Nat.add_assoc]
  exact (Nat.le_sub_iff_add_le hc).2 hbc

/-- Under zero consumption a buffer increases exactly by indigenous plus
external replenishment. -/
theorem bufferStep_zero_consumption (b p e : Nat) :
    bufferStep b p e 0 = b + p + e := by
  simp [bufferStep]

/-- External replenishment cannot reduce the next-period buffer. -/
theorem bufferStep_support_monotone (b p c e₁ e₂ : Nat) (h : e₁ ≤ e₂) :
    bufferStep b p e₁ c ≤ bufferStep b p e₂ c := by
  unfold bufferStep
  exact Nat.sub_le_sub_right (Nat.add_le_add_left h (b + p)) c

/-- Constant-deficit runway safety condition. It is deliberately a predicate,
not a claim that every Pineland process has constant flows. -/
def RunwaySafe (stock deficit days : Nat) : Prop :=
  days * deficit ≤ stock

theorem runwaySafe_zero_days (stock deficit : Nat) :
    RunwaySafe stock deficit 0 := by
  simp [RunwaySafe]

theorem runwaySafe_of_more_stock {stock₁ stock₂ deficit days : Nat}
    (hs : stock₁ ≤ stock₂) (h : RunwaySafe stock₁ deficit days) :
    RunwaySafe stock₂ deficit days := by
  exact Nat.le_trans h hs

theorem runwaySafe_of_shorter_horizon {stock deficit d₁ d₂ : Nat}
    (hd : d₁ ≤ d₂) (h : RunwaySafe stock deficit d₂) :
    RunwaySafe stock deficit d₁ := by
  unfold RunwaySafe at *
  exact Nat.le_trans (Nat.mul_le_mul_right deficit hd) h

/-- Closed-form stock remaining after `days` periods under a constant net
deficit. This is a diagnostic idealization, not an assumption about Pineland's
time-varying flows. -/
def stockAfterConstantDeficit (stock deficit days : Nat) : Nat :=
  stock - days * deficit

theorem stockAfterConstantDeficit_eq_zero_of_exhausted
    {stock deficit days : Nat} (h : stock ≤ days * deficit) :
    stockAfterConstantDeficit stock deficit days = 0 := by
  exact Nat.sub_eq_zero_of_le h

theorem stockAfterConstantDeficit_add_used_of_safe
    {stock deficit days : Nat} (h : RunwaySafe stock deficit days) :
    stockAfterConstantDeficit stock deficit days + days * deficit = stock := by
  unfold stockAfterConstantDeficit RunwaySafe at *
  exact Nat.sub_add_cancel h

/-- Removing an external replenishment flow cannot increase next-period stock. -/
theorem bufferStep_without_support_le_with_support (b p c e : Nat) :
    bufferStep b p 0 c ≤ bufferStep b p e c := by
  exact bufferStep_support_monotone b p c 0 e (Nat.zero_le e)

end Buffers

section Horizon

/-!
The horizon layer formalizes structural viability only.  It does not assert
that a Pineland behavioral outcome is a deterministic function of `q`; that
mapping remains an empirical question for the simulator.
-/

variable {Time Service : Type}
variable [Finite Service]

/-- A time-indexed structural service-demand trace. -/
structure StructuralTrace where
  supply : Time → Service → Nat
  demand : Time → Service → Nat
  demand_active : ∀ t, HasDemand (demand t)

noncomputable def structuralScaleAt (T : StructuralTrace (Time := Time) (Service := Service))
    (t : Time) : Rat :=
  missionScale (T.supply t) (T.demand t) (T.demand_active t)

/-- Structural autonomy over a horizon means that every checkpoint's service
requirements are fully covered by indigenous usable service. -/
def HorizonAutonomous (T : StructuralTrace (Time := Time) (Service := Service)) : Prop :=
  ∀ t, RequirementFeasible (T.supply t) (T.demand t)

theorem horizonAutonomous_iff_all_scales_ge_one
    (T : StructuralTrace (Time := Time) (Service := Service)) :
    HorizonAutonomous T ↔ ∀ t, (1 : Rat) ≤ structuralScaleAt T t := by
  constructor
  · intro h t
    exact (one_le_missionScale_iff_requirementFeasible
      (T.supply t) (T.demand t) (T.demand_active t)).2 (h t)
  · intro h t
    exact (one_le_missionScale_iff_requirementFeasible
      (T.supply t) (T.demand t) (T.demand_active t)).1 (h t)

/-- Failure of horizon autonomy is exactly the existence of at least one
checkpoint whose minimum service ratio is below one. -/
theorem not_horizonAutonomous_iff_exists_scale_lt_one
    (T : StructuralTrace (Time := Time) (Service := Service)) :
    ¬ HorizonAutonomous T ↔ ∃ t, structuralScaleAt T t < (1 : Rat) := by
  classical
  rw [horizonAutonomous_iff_all_scales_ge_one]
  constructor
  · intro h
    have hex : ∃ t, ¬ (1 : Rat) ≤ structuralScaleAt T t := Classical.not_forall.mp h
    obtain ⟨t, ht⟩ := hex
    exact ⟨t, lt_of_not_ge ht⟩
  · rintro ⟨t, ht⟩ hall
    exact (not_le_of_gt ht) (hall t)

end Horizon

section Dynamics

/-- An abstract Pineland transition wrapper. This is intentionally not a claim
that the ABM satisfies any particular smooth or stochastic equation; it merely
separates formal structural quantities from empirical state evolution. -/
structure DynamicModel (State Action Environment Noise : Type) where
  step : State → Action → Environment → Noise → State

/-- Potential-outcome experiment wrapper: both branches begin from an identical
state, while the caller supplies distinct action/support policies thereafter. -/
structure PairedInitialState (State : Type) where
  common : State

def PairedInitialState.on {State : Type} (P : PairedInitialState State) : State := P.common
def PairedInitialState.off {State : Type} (P : PairedInitialState State) : State := P.common

theorem paired_initial_states_identical {State : Type} (P : PairedInitialState State) :
    P.on = P.off := rfl

end Dynamics

end PartnerForce
