import PinelandPartnerForceTheory.PartnerForce
import Mathlib.Algebra.BigOperators.Fin
import Mathlib.Tactic.FinCases
import Mathlib.Tactic.NormNum

open PartnerForce

abbrev Svc := Fin 3
abbrev Act := Fin 2

def tech (i : Svc) (j : Act) : Nat :=
  if i = 0 then
    if j = 0 then 2 else 1
  else if i = 1 then
    if j = 0 then 1 else 3
  else
    1

def mission (j : Act) : Nat :=
  if j = 0 then 10 else 5

def model : MissionModel (Service := Svc) (Activity := Act) :=
  ⟨tech, mission⟩

def indigenous (i : Svc) : Nat :=
  if i = 0 then 30 else 20

def external (i : Svc) : Nat :=
  if i = 1 then 5 else 0

def support : SupportState (Service := Svc) :=
  ⟨indigenous, external⟩

theorem activeDemand : HasDemand (requirement model) := by
  refine ⟨(0 : Svc), ?_⟩
  norm_num [requirement, model, tech, mission, Fin.sum_univ_two]

theorem logisticsBottleneckIndigenous :
    Bottleneck indigenous (requirement model) (1 : Svc) := by
  constructor
  · norm_num [requirement, model, tech, mission, Fin.sum_univ_two]
  · intro j hj
    fin_cases j <;>
      norm_num [serviceRatio, requirement, model, tech, mission, indigenous,
        Fin.sum_univ_two]

theorem logisticsBottleneckSupported :
    Bottleneck (supported support) (requirement model) (1 : Svc) := by
  constructor
  · norm_num [requirement, model, tech, mission, Fin.sum_univ_two]
  · intro j hj
    fin_cases j <;>
      norm_num [serviceRatio, requirement, model, tech, mission, supported, support,
        indigenous, external, Fin.sum_univ_two]

example : requirement model (0 : Svc) = 25 := by
  norm_num [requirement, model, tech, mission, Fin.sum_univ_two]

example : requirement model (1 : Svc) = 25 := by
  norm_num [requirement, model, tech, mission, Fin.sum_univ_two]

example : requirement model (2 : Svc) = 15 := by
  norm_num [requirement, model, tech, mission, Fin.sum_univ_two]

example : ¬ FullMissionFeasible model indigenous := by
  intro h
  have hlog := h (1 : Svc)
  norm_num [requirement, model, tech, mission, indigenous, Fin.sum_univ_two] at hlog

example : FullMissionFeasible model (supported support) := by
  intro i
  fin_cases i <;>
    norm_num [requirement, model, tech, mission, supported, support, indigenous, external,
      Fin.sum_univ_two]

example : Dependent model support := by
  constructor
  · intro h
    have hlog := h (1 : Svc)
    norm_num [requirement, model, tech, mission, support, indigenous, Fin.sum_univ_two] at hlog
  · intro i
    fin_cases i <;>
      norm_num [requirement, model, tech, mission, supported, support, indigenous, external,
        Fin.sum_univ_two]

theorem indigenousScaleExact :
    missionScale support.indigenous (requirement model) activeDemand = (4 : Rat) / 5 := by
  simp only [support]
  rw [missionScale_eq_serviceRatio_of_bottleneck _ _ _ logisticsBottleneckIndigenous]
  norm_num [serviceRatio, requirement, model, tech, mission, indigenous, Fin.sum_univ_two]

theorem supportedScaleExact :
    missionScale (supported support) (requirement model) activeDemand = (1 : Rat) := by
  rw [missionScale_eq_serviceRatio_of_bottleneck _ _ _ logisticsBottleneckSupported]
  norm_num [serviceRatio, requirement, model, tech, mission, supported, support,
    indigenous, external, Fin.sum_univ_two]

example : structuralSupportLift model support activeDemand = (1 : Rat) / 5 := by
  norm_num [structuralSupportLift, supportLift, cappedScale, indigenousScaleExact,
    supportedScaleExact]
