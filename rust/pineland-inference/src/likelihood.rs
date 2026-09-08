//! General observation likelihood contract.

use crate::rao_blackwell::RaoBlackwellizedActivityLikelihood;

#[derive(Clone, Debug, PartialEq)]
pub enum Observation {
    BinaryActivity {
        observed: bool,
        hazard: f64,
        opportunities: f64,
    },
    GaussianControl {
        actor: u8,
        observed: f64,
        sigma: f64,
    },
    GaussianInsurgentPersonnel {
        observed: f64,
        sigma: f64,
    },
}

#[derive(Clone, Debug, PartialEq)]
pub struct ObservationLikelihood {
    pub activity: RaoBlackwellizedActivityLikelihood,
    pub gaussian_sigma: f64,
}
impl Default for ObservationLikelihood {
    fn default() -> Self {
        Self {
            activity: RaoBlackwellizedActivityLikelihood::default(),
            gaussian_sigma: 0.25,
        }
    }
}
impl ObservationLikelihood {
    pub fn log_binary(&self, observed: bool, hazard: f64, opportunities: f64) -> f64 {
        self.activity
            .log_likelihood(observed, hazard, opportunities)
    }
    pub fn log_gaussian(&self, observed: f64, predicted: f64) -> f64 {
        let sigma = self.gaussian_sigma.max(1e-12);
        let z = (observed - predicted) / sigma;
        -0.5 * z * z - sigma.ln() - 0.5 * std::f64::consts::TAU.ln()
    }
}
