//! Guided proposals and importance corrections.

#[derive(Clone, Debug, PartialEq)]
pub struct GuidedProposal {
    pub strength: f64,
    pub floor: f64,
}
impl Default for GuidedProposal {
    fn default() -> Self {
        Self {
            strength: 0.5,
            floor: 1e-9,
        }
    }
}
#[derive(Clone, Debug, PartialEq)]
pub struct GuidedProposalCorrection {
    pub proposal_log_probability: f64,
    pub target_log_probability: f64,
    pub correction: f64,
}
impl GuidedProposal {
    pub fn weight(
        &self,
        prior_log_weight: f64,
        log_likelihood: f64,
        observed_signal: f64,
        predicted_signal: f64,
    ) -> GuidedProposalCorrection {
        let delta = (observed_signal - predicted_signal) * self.strength;
        let target = log_likelihood + delta;
        let proposal = delta - 0.5 * delta * delta;
        let prior = if prior_log_weight.is_finite() {
            prior_log_weight
        } else {
            self.floor.max(1e-300).ln()
        };
        GuidedProposalCorrection {
            proposal_log_probability: proposal,
            target_log_probability: target,
            correction: target - proposal + prior,
        }
    }
}
