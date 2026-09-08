//! Monte-Carlo standard-error stopping diagnostics.

#[derive(Clone, Debug, PartialEq)]
pub struct McseMonitor {
    pub target: f64,
    pub minimum_samples: usize,
    pub samples: Vec<f64>,
}
#[derive(Clone, Debug, PartialEq)]
pub struct McseStatus {
    pub mean: f64,
    pub variance: f64,
    pub mcse: f64,
    pub converged: bool,
    pub count: usize,
}
impl McseMonitor {
    pub fn new(target: f64, minimum_samples: usize) -> Self {
        Self {
            target: target.max(0.0),
            minimum_samples: minimum_samples.max(1),
            samples: Vec::new(),
        }
    }
    pub fn push(&mut self, value: f64) {
        if value.is_finite() {
            self.samples.push(value)
        }
    }
    pub fn status(&self) -> McseStatus {
        let count = self.samples.len();
        if count == 0 {
            return McseStatus {
                mean: 0.0,
                variance: 0.0,
                mcse: f64::INFINITY,
                converged: false,
                count: 0,
            };
        }
        let mean = self.samples.iter().sum::<f64>() / count as f64;
        let variance = if count > 1 {
            self.samples.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / (count - 1) as f64
        } else {
            f64::INFINITY
        };
        let mcse = (variance / count as f64).sqrt();
        McseStatus {
            mean,
            variance,
            mcse,
            converged: count >= self.minimum_samples && mcse <= self.target,
            count,
        }
    }
}
