use dirs::home_dir;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use thiserror::Error;

#[derive(Error, Debug)]
pub enum ConfigError {
    #[error("Could not read config: {0}")]
    Read(#[from] std::io::Error),
    #[error("Could not parse config: {0}")]
    Parse(#[from] serde_json::Error),
    #[error("{0}")]
    #[allow(dead_code)]
    Other(String),
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct Config {
    pub version: String,
    pub default_device: DeviceConfig,
    pub wokwi: WokwiConfig,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct DeviceConfig {
    pub port: Option<String>,
    pub board: Option<String>,
    pub fqbn: Option<String>,
    #[serde(default = "default_baud")]
    pub baud: u32,
}

impl Default for DeviceConfig {
    fn default() -> Self {
        DeviceConfig {
            port: None,
            board: None,
            fqbn: None,
            baud: 9600,
        }
    }
}

fn default_baud() -> u32 {
    9600
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct WokwiConfig {
    pub api_token: Option<String>,
    #[serde(default = "default_timeout_ms")]
    pub default_timeout_ms: u32,
    pub diagram_path: Option<String>,
}

fn default_timeout_ms() -> u32 {
    5000
}

impl Default for WokwiConfig {
    fn default() -> Self {
        WokwiConfig {
            api_token: None,
            default_timeout_ms: 5000,
            diagram_path: None,
        }
    }
}

impl Default for Config {
    fn default() -> Self {
        Config {
            version: "1".into(),
            default_device: DeviceConfig::default(),
            wokwi: WokwiConfig::default(),
        }
    }
}

pub fn config_path() -> PathBuf {
    home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".nff")
        .join("config.json")
}

pub fn exists() -> bool {
    config_path().exists()
}

pub fn load() -> Result<Config, ConfigError> {
    let path = config_path();
    if !path.exists() {
        return Ok(Config::default());
    }
    let raw = fs::read_to_string(&path)?;
    Ok(serde_json::from_str(&raw)?)
}

pub fn save(config: &Config) -> Result<(), ConfigError> {
    let path = config_path();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let tmp = path.with_extension("json.tmp");
    fs::write(&tmp, serde_json::to_string_pretty(config)?)?;
    fs::rename(&tmp, &path)?;
    Ok(())
}

pub fn get_default_device() -> Result<DeviceConfig, ConfigError> {
    Ok(load()?.default_device)
}

pub fn set_default_device(
    port: &str,
    board: &str,
    fqbn: &str,
    baud: u32,
) -> Result<(), ConfigError> {
    let mut config = load()?;
    config.default_device = DeviceConfig {
        port: if port.is_empty() { None } else { Some(port.into()) },
        board: if board.is_empty() { None } else { Some(board.into()) },
        fqbn: if fqbn.is_empty() { None } else { Some(fqbn.into()) },
        baud,
    };
    save(&config)
}

pub fn get_wokwi_config() -> Result<WokwiConfig, ConfigError> {
    Ok(load()?.wokwi)
}

pub fn set_wokwi_token(token: Option<&str>) -> Result<(), ConfigError> {
    let mut config = load()?;
    config.wokwi.api_token = token.map(String::from);
    save(&config)
}

#[allow(dead_code)]
pub fn set_wokwi_diagram_path(path: Option<&str>) -> Result<(), ConfigError> {
    let mut config = load()?;
    config.wokwi.diagram_path = path.map(String::from);
    save(&config)
}

#[allow(dead_code)]
pub fn set_wokwi_timeout(ms: u32) -> Result<(), ConfigError> {
    let mut config = load()?;
    config.wokwi.default_timeout_ms = ms;
    save(&config)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_config_round_trips() {
        let config = Config::default();
        let json = serde_json::to_string_pretty(&config).unwrap();
        let parsed: Config = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed.version, "1");
        assert_eq!(parsed.default_device.baud, 9600);
        assert_eq!(parsed.wokwi.default_timeout_ms, 5000);
    }
}
