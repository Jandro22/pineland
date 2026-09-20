//! Formal-theory adapter for partner-force structural autonomy.
//!
//! The corresponding Lean development proves the exact discrete/rational
//! theory. This module is the floating-point telemetry adapter used by the
//! simulator. It deliberately uses only like-for-like service units and keeps
//! stock buffers outside the flow-feasibility coordinate.

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ServiceChannel {
    pub demand: f64,
    pub indigenous: f64,
    pub external: f64,
}

impl ServiceChannel {
    pub fn new(demand: f64, indigenous: f64, external: f64) -> Self {
        Self {
            demand,
            indigenous,
            external,
        }
    }

    pub fn active(self) -> bool {
        self.demand > 0.0
    }

    pub fn indigenous_ratio(self) -> Option<f64> {
        self.active().then(|| self.indigenous / self.demand)
    }

    pub fn supported_ratio(self) -> Option<f64> {
        self.active()
            .then(|| (self.indigenous + self.external) / self.demand)
    }

    pub fn deficit(self) -> f64 {
        (self.demand - self.indigenous).max(0.0)
    }

    pub fn useful_external(self) -> f64 {
        self.external.min(self.deficit())
    }

    pub fn redundant_external(self) -> f64 {
        (self.external - self.useful_external()).max(0.0)
    }

    pub fn external_share(self) -> f64 {
        let total = self.indigenous + self.external;
        if total > 0.0 {
            (self.external / total).clamp(0.0, 1.0)
        } else {
            0.0
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StructuralRegime {
    Autonomous,
    Dependent,
    Overmatched,
    /// Telemetry sentinel for the case excluded by Lean's `HasDemand`
    /// precondition on `missionScale`. This is not a fourth mathematical
    /// regime: with an all-zero requirement vector, requirement feasibility is
    /// vacuous, while q/bottleneck are intentionally undefined.
    NoActiveDemand,
}

impl StructuralRegime {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Autonomous => "AUTONOMOUS",
            Self::Dependent => "DEPENDENT",
            Self::Overmatched => "OVERMATCHED",
            Self::NoActiveDemand => "NO_ACTIVE_DEMAND",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BottleneckChannel {
    ForceGeneration,
    Logistics,
    Command,
    None,
}

impl BottleneckChannel {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::ForceGeneration => "forcegen",
            Self::Logistics => "logistics",
            Self::Command => "command",
            Self::None => "none",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct StructuralServiceWindow {
    pub forcegen: ServiceChannel,
    pub logistics: ServiceChannel,
    pub command: ServiceChannel,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct StructuralAutonomyMetrics {
    pub q_indigenous: f64,
    pub q_supported: f64,
    pub support_lift: f64,
    pub regime: StructuralRegime,
    pub bottleneck: BottleneckChannel,
    pub forcegen_ratio_indigenous: Option<f64>,
    pub logistics_ratio_indigenous: Option<f64>,
    pub command_ratio_indigenous: Option<f64>,
}

impl StructuralServiceWindow {
    pub fn metrics(self) -> Result<StructuralAutonomyMetrics, String> {
        let channels = [
            (BottleneckChannel::ForceGeneration, self.forcegen),
            (BottleneckChannel::Logistics, self.logistics),
            (BottleneckChannel::Command, self.command),
        ];
        for (_, c) in channels {
            for (name, value) in [
                ("demand", c.demand),
                ("indigenous", c.indigenous),
                ("external", c.external),
            ] {
                if !value.is_finite() {
                    return Err(format!("formal service {name} must be finite"));
                }
                if value < 0.0 {
                    return Err(format!(
                        "formal service {name} must be nonnegative (Lean domain is Nat)"
                    ));
                }
            }
            let supported = c.indigenous + c.external;
            if !supported.is_finite() {
                return Err(
                    "formal supported service must be finite; indigenous + external overflowed"
                        .to_string(),
                );
            }
        }
        let mut active = channels.into_iter().filter(|(_, c)| c.active()).map(
            |(name, c)| -> Result<_, String> {
                let qi = c.indigenous_ratio().unwrap();
                let qs = c.supported_ratio().unwrap();
                if !qi.is_finite() || !qs.is_finite() {
                    return Err(format!(
                        "formal service ratio for {} must be finite",
                        name.as_str()
                    ));
                }
                Ok((name, qi, qs))
            },
        );
        let Some(first) = active.next() else {
            return Ok(StructuralAutonomyMetrics {
                q_indigenous: -1.0,
                q_supported: -1.0,
                support_lift: 0.0,
                regime: StructuralRegime::NoActiveDemand,
                bottleneck: BottleneckChannel::None,
                forcegen_ratio_indigenous: None,
                logistics_ratio_indigenous: None,
                command_ratio_indigenous: None,
            });
        };
        let (mut bottleneck, mut q_indigenous, first_q_supported) = first?;
        let mut q_supported = first_q_supported;
        for next in active {
            let (name, qi, qs) = next?;
            if qi < q_indigenous {
                q_indigenous = qi;
                bottleneck = name;
            }
            q_supported = q_supported.min(qs);
        }
        let support_lift = q_supported.min(1.0) - q_indigenous.min(1.0);
        if q_supported < q_indigenous {
            return Err(
                "formal monotonicity violated: supported mission scale is below indigenous scale"
                    .to_string(),
            );
        }

        // Classify from the primitive feasibility inequalities proved in Lean,
        // not from an epsilon-perturbed ratio threshold. This preserves the
        // exact regime partition for the represented nonnegative values.
        let indigenous_feasible = channels.iter().all(|(_, c)| c.demand <= c.indigenous);
        let supported_feasible = channels
            .iter()
            .all(|(_, c)| c.demand <= c.indigenous + c.external);
        let regime = if indigenous_feasible {
            StructuralRegime::Autonomous
        } else if supported_feasible {
            StructuralRegime::Dependent
        } else {
            StructuralRegime::Overmatched
        };
        Ok(StructuralAutonomyMetrics {
            q_indigenous,
            q_supported,
            support_lift,
            regime,
            bottleneck,
            forcegen_ratio_indigenous: self.forcegen.indigenous_ratio(),
            logistics_ratio_indigenous: self.logistics.indigenous_ratio(),
            command_ratio_indigenous: self.command.indigenous_ratio(),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dependent_example_matches_lean_regression_shape() {
        let w = StructuralServiceWindow {
            forcegen: ServiceChannel::new(10.0, 12.0, 0.0),
            logistics: ServiceChannel::new(25.0, 20.0, 5.0),
            command: ServiceChannel::new(10.0, 10.0, 0.0),
        };
        let m = w.metrics().unwrap();
        assert!((m.q_indigenous - 0.8).abs() < 1e-12);
        assert!((m.q_supported - 1.0).abs() < 1e-12);
        assert!((m.support_lift - 0.2).abs() < 1e-12);
        assert_eq!(m.regime, StructuralRegime::Dependent);
        assert_eq!(m.bottleneck, BottleneckChannel::Logistics);
        assert!((w.logistics.useful_external() - 5.0).abs() < 1e-12);
        assert!(w.logistics.redundant_external().abs() < 1e-12);
    }

    #[test]
    fn zero_demand_channel_is_not_a_bottleneck() {
        let w = StructuralServiceWindow {
            forcegen: ServiceChannel::new(0.0, 0.0, 50.0),
            logistics: ServiceChannel::new(100.0, 80.0, 0.0),
            command: ServiceChannel::new(10.0, 20.0, 0.0),
        };
        let m = w.metrics().unwrap();
        assert_eq!(m.bottleneck, BottleneckChannel::Logistics);
        assert_eq!(m.forcegen_ratio_indigenous, None);
    }

    #[test]
    fn surplus_external_is_exposure_not_dependence() {
        let c = ServiceChannel::new(100.0, 500.0, 500.0);
        assert_eq!(c.deficit(), 0.0);
        assert_eq!(c.useful_external(), 0.0);
        assert_eq!(c.redundant_external(), 500.0);
        assert_eq!(c.external_share(), 0.5);
    }

    #[test]
    fn all_zero_demand_is_explicitly_undefined() {
        let w = StructuralServiceWindow {
            forcegen: ServiceChannel::new(0.0, 10.0, 0.0),
            logistics: ServiceChannel::new(0.0, 10.0, 0.0),
            command: ServiceChannel::new(0.0, 10.0, 0.0),
        };
        let m = w.metrics().unwrap();
        assert_eq!(m.q_indigenous, -1.0);
        assert_eq!(m.q_supported, -1.0);
        assert_eq!(m.regime, StructuralRegime::NoActiveDemand);
        assert_eq!(m.bottleneck, BottleneckChannel::None);
    }

    #[test]
    fn no_epsilon_deadband_at_feasibility_boundary() {
        let w = StructuralServiceWindow {
            forcegen: ServiceChannel::new(1.0, 1.0 - 5.0e-10, 0.0),
            logistics: ServiceChannel::new(0.0, 0.0, 0.0),
            command: ServiceChannel::new(0.0, 0.0, 0.0),
        };
        let m = w.metrics().unwrap();
        assert!(m.q_indigenous < 1.0);
        assert_eq!(m.regime, StructuralRegime::Overmatched);
    }

    #[test]
    fn tiny_positive_demand_remains_formally_active() {
        let w = StructuralServiceWindow {
            forcegen: ServiceChannel::new(5.0e-10, 0.0, 5.0e-10),
            logistics: ServiceChannel::new(0.0, 0.0, 0.0),
            command: ServiceChannel::new(0.0, 0.0, 0.0),
        };
        let m = w.metrics().unwrap();
        assert_eq!(m.q_indigenous, 0.0);
        assert_eq!(m.q_supported, 1.0);
        assert_eq!(m.regime, StructuralRegime::Dependent);
        assert_eq!(m.bottleneck, BottleneckChannel::ForceGeneration);
    }

    #[test]
    fn rejects_values_outside_lean_nonnegative_domain() {
        let negative = StructuralServiceWindow {
            forcegen: ServiceChannel::new(1.0, -0.1, 0.0),
            logistics: ServiceChannel::new(0.0, 0.0, 0.0),
            command: ServiceChannel::new(0.0, 0.0, 0.0),
        };
        assert!(negative.metrics().is_err());

        let nonfinite = StructuralServiceWindow {
            forcegen: ServiceChannel::new(f64::NAN, 0.0, 0.0),
            logistics: ServiceChannel::new(0.0, 0.0, 0.0),
            command: ServiceChannel::new(0.0, 0.0, 0.0),
        };
        assert!(nonfinite.metrics().is_err());
    }

    #[test]
    fn exhaustive_small_integer_domain_matches_lean_definitions() {
        let values = [0.0, 1.0, 2.0];
        for d1 in values {
            for i1 in values {
                for e1 in values {
                    for d2 in values {
                        for i2 in values {
                            for e2 in values {
                                let w = StructuralServiceWindow {
                                    forcegen: ServiceChannel::new(d1, i1, e1),
                                    logistics: ServiceChannel::new(d2, i2, e2),
                                    command: ServiceChannel::new(0.0, 0.0, 0.0),
                                };
                                let m = w.metrics().unwrap();
                                let channels = [w.forcegen, w.logistics, w.command];
                                let has_demand = channels.iter().any(|c| c.demand > 0.0);

                                if !has_demand {
                                    assert_eq!(m.regime, StructuralRegime::NoActiveDemand);
                                    assert_eq!(m.q_indigenous, -1.0);
                                    assert_eq!(m.q_supported, -1.0);
                                    continue;
                                }

                                let expected_autonomous =
                                    channels.iter().all(|c| c.demand <= c.indigenous);
                                let expected_supported = channels
                                    .iter()
                                    .all(|c| c.demand <= c.indigenous + c.external);
                                let expected_regime = if expected_autonomous {
                                    StructuralRegime::Autonomous
                                } else if expected_supported {
                                    StructuralRegime::Dependent
                                } else {
                                    StructuralRegime::Overmatched
                                };
                                assert_eq!(m.regime, expected_regime);
                                assert!(m.q_supported >= m.q_indigenous);
                                assert!((0.0..=1.0).contains(&m.support_lift));
                                assert_eq!(m.q_indigenous >= 1.0, expected_autonomous);
                                assert_eq!(m.q_supported >= 1.0, expected_supported);
                                if expected_autonomous {
                                    assert_eq!(m.support_lift, 0.0);
                                }
                                if expected_regime == StructuralRegime::Dependent {
                                    assert!(m.support_lift > 0.0);
                                    assert_eq!(m.support_lift, 1.0 - m.q_indigenous);
                                }
                                for c in channels {
                                    assert_eq!(
                                        c.useful_external() + c.redundant_external(),
                                        c.external
                                    );
                                    assert!(c.useful_external() <= c.external);
                                    assert!(c.useful_external() <= c.deficit());
                                    if c.demand <= c.indigenous {
                                        assert_eq!(c.useful_external(), 0.0);
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    #[test]
    fn positive_per_channel_rescaling_preserves_q_regime_and_bottleneck_ratio() {
        let w = StructuralServiceWindow {
            forcegen: ServiceChannel::new(12.0, 9.0, 3.0),
            logistics: ServiceChannel::new(25.0, 20.0, 8.0),
            command: ServiceChannel::new(7.0, 14.0, 2.0),
        };
        let scaled = StructuralServiceWindow {
            forcegen: ServiceChannel::new(12.0 * 2.0, 9.0 * 2.0, 3.0 * 2.0),
            logistics: ServiceChannel::new(25.0 * 5.0, 20.0 * 5.0, 8.0 * 5.0),
            command: ServiceChannel::new(7.0 * 11.0, 14.0 * 11.0, 2.0 * 11.0),
        };
        let a = w.metrics().unwrap();
        let b = scaled.metrics().unwrap();
        assert_eq!(a.q_indigenous, b.q_indigenous);
        assert_eq!(a.q_supported, b.q_supported);
        assert_eq!(a.support_lift, b.support_lift);
        assert_eq!(a.regime, b.regime);
        assert_eq!(a.bottleneck, b.bottleneck);
    }
}
