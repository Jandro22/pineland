"""Pineland COIN-SIM research engine."""

from .config import (CombatConfig, ForeignAffairsConfig, GeographyConfig, InformationConfig, OrganizationEcologyConfig, PeaceProcessConfig,
                     PoliticalOrderConfig, SimulationConfig)
from .entities import (BorderSegment, DiasporaLink, Election, Engagement, ExternalSupport,
                       ExternalTransfer, ForeignBelief, ForeignIntervention, ForeignState,
                       InterpreterBroker, LeadershipAgent, LocalElite, Observation,
                       OrganizationTransition, PartyBranch, PoliticalInstitution,
                       PoliticalTransfer, PolicyImplementation, ProtoOrganization)
from .entities import AgreementProvision, Negotiation, PeaceAgreement, PeaceTransition
from .entities import StateBasedEvent
from .generator import generate_pineland
from .simulation import Simulation, SimulationParticle, SimulationResult
from .state_estimation import (
    AssimilationObservation,
    FilterUpdateDiagnostics,
    Particle,
    PosteriorSupportExhausted,
    SequentialParticleFilter,
)
from .validation import (ParameterSpec, empirical_target_contract, parameter_registry,
                         model_ladder_holdout)
from .empirical import (CasePackage, ConstructCorrespondence, EmpiricalTarget, RawObservation, TransformationRecord,
                        aggregate_observations, build_case_package, first_paper_experiment_spec, load_case_package,
                        load_raw_observations, recorded_vs_true_metrics, build_construct_correspondence)
from .research_audit import (causal_ledger_audit, foreign_withdrawal_diagnostics,
                             initialization_ensemble, long_horizon_diagnostics,
                             fragmentation_bargaining_ablation, language_factorial,
                             mechanism_ablation, morris_sensitivity, null_and_extreme_checks,
                             parameter_recovery_ensemble, recording_calibration,
                             resolution_ladder, scheduler_audit, truth_firewall_check,
                             truth_firewall_battery, representative_agent_audit,
                             topology_ablation, variance_sensitivity, publication_readiness_report,
                             long_horizon_ensemble)
from .research_audit import output_mode_benchmark

__all__ = ["BorderSegment", "CombatConfig", "DiasporaLink", "Engagement", "ExternalSupport",
           "ExternalTransfer", "ForeignAffairsConfig", "ForeignBelief", "ForeignIntervention",
           "ForeignState", "GeographyConfig", "InformationConfig", "InterpreterBroker", "LeadershipAgent", "Observation",
           "OrganizationEcologyConfig", "OrganizationTransition", "PartyBranch",
           "PoliticalInstitution", "PoliticalOrderConfig", "PoliticalTransfer",
           "PolicyImplementation", "ProtoOrganization", "LocalElite", "Election",
           "StateBasedEvent",
           "Simulation", "SimulationConfig",
           "SimulationParticle", "SimulationResult", "generate_pineland"]
__all__ += [
    "AssimilationObservation", "FilterUpdateDiagnostics", "Particle",
    "PosteriorSupportExhausted", "SequentialParticleFilter",
]
__all__ += ["AgreementProvision", "Negotiation", "PeaceAgreement", "PeaceProcessConfig",
            "PeaceTransition"]
__all__ += ["ParameterSpec", "empirical_target_contract", "parameter_registry"]
__all__ += ["CasePackage", "ConstructCorrespondence", "EmpiricalTarget", "RawObservation", "TransformationRecord",
            "aggregate_observations", "build_case_package", "load_case_package",
            "first_paper_experiment_spec",
            "load_raw_observations", "recorded_vs_true_metrics", "build_construct_correspondence",
            "model_ladder_holdout", "causal_ledger_audit", "foreign_withdrawal_diagnostics",
            "initialization_ensemble", "long_horizon_diagnostics", "mechanism_ablation",
            "fragmentation_bargaining_ablation", "language_factorial",
            "morris_sensitivity", "null_and_extreme_checks", "parameter_recovery_ensemble",
            "recording_calibration", "resolution_ladder", "scheduler_audit",
            "truth_firewall_check", "truth_firewall_battery", "representative_agent_audit",
            "variance_sensitivity", "publication_readiness_report", "long_horizon_ensemble"]
__all__ += ["topology_ablation", "output_mode_benchmark"]
__version__ = "0.13.0"
