//! Rao--Blackwellized activity likelihoods for count/occurrence observations.

#[derive(Clone, Debug, PartialEq)]
pub struct RaoBlackwellizedActivityLikelihood {
    pub exposure_days: f64,
    pub false_positive_rate: f64,
    pub detection_rate: f64,
}

impl Default for RaoBlackwellizedActivityLikelihood {
    fn default() -> Self {
        Self {
            exposure_days: 1.0,
            false_positive_rate: 0.01,
            detection_rate: 0.5,
        }
    }
}

impl RaoBlackwellizedActivityLikelihood {
    pub fn probability_from_hazard(&self, hazard: f64) -> f64 {
        1.0 - (-hazard.max(0.0) * self.exposure_days.max(0.0)).exp()
    }
    pub fn probability_from_opportunities(
        &self,
        opportunities: f64,
        success_probability: f64,
    ) -> f64 {
        1.0 - (1.0 - success_probability.clamp(0.0, 1.0)).powf(opportunities.max(0.0))
    }
    pub fn probability(&self, hazard: f64, opportunities: f64) -> f64 {
        let hazard_probability = self.probability_from_hazard(hazard);
        let opportunity_probability =
            self.probability_from_opportunities(opportunities, self.detection_rate);
        let latent = 1.0 - (1.0 - hazard_probability) * (1.0 - opportunity_probability);
        (latent + self.false_positive_rate.clamp(0.0, 1.0) * (1.0 - latent))
            .clamp(1e-15, 1.0 - 1e-15)
    }
    pub fn log_likelihood(&self, observed: bool, hazard: f64, opportunities: f64) -> f64 {
        let p = self.probability(hazard, opportunities);
        if observed {
            p.ln()
        } else {
            (1.0 - p).ln()
        }
    }
    pub fn score(&self, observed: bool, hazards: &[f64], opportunities: &[f64]) -> f64 {
        hazards
            .iter()
            .zip(opportunities)
            .map(|(h, o)| self.log_likelihood(observed, *h, *o))
            .sum()
    }
}
