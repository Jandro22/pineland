//! Config-file helpers kept separate from simulation code.
use pineland_core::config::{ConfigError, SimulationConfig};
use pineland_core::json::{self, JsonValue};
use std::path::Path;
pub fn load(path: impl AsRef<Path>) -> Result<SimulationConfig, ConfigError> {
    SimulationConfig::load(path)
}
pub fn save(path: impl AsRef<Path>, config: &SimulationConfig) -> Result<(), String> {
    super::write_json(path, &config.to_json()).map_err(|e| e.to_string())
}
pub fn parse(text: &str) -> Result<JsonValue, String> {
    json::parse(text).map_err(|e| e.to_string())
}
