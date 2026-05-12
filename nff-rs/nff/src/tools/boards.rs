use serialport::available_ports;

pub const BOARD_MAP: &[(u16, u16, &str, &str, Option<&str>)] = &[
    (0x2341, 0x0043, "Arduino Uno",       "arduino:avr:uno",         Some("wokwi-arduino-uno")),
    (0x2341, 0x0010, "Arduino Mega 2560", "arduino:avr:mega",        Some("wokwi-arduino-mega")),
    (0x2341, 0x0036, "Arduino Leonardo",  "arduino:avr:leonardo",    Some("wokwi-arduino-leonardo")),
    (0x2341, 0x0058, "Arduino Nano",      "arduino:avr:nano",        Some("wokwi-arduino-nano")),
    (0x10c4, 0xea60, "ESP32 (CP210x)",    "esp32:esp32:esp32",       Some("wokwi-esp32-devkit-v1")),
    (0x1a86, 0x7523, "ESP32 (CH340)",     "esp32:esp32:esp32",       Some("wokwi-esp32-devkit-v1")),
    (0x0403, 0x6001, "ESP8266 (FTDI)",    "esp8266:esp8266:generic", Some("wokwi-esp8266")),
];

#[derive(Debug, Clone)]
pub struct DetectedDevice {
    pub port: String,
    pub board: String,
    pub fqbn: String,
    pub vendor_id: String,
    pub product_id: String,
    pub wokwi_chip: Option<String>,
}

pub fn list_devices() -> Vec<DetectedDevice> {
    let ports = match available_ports() {
        Ok(p) => p,
        Err(_) => return vec![],
    };

    let mut devices = Vec::new();
    for info in ports {
        if let serialport::SerialPortType::UsbPort(usb) = &info.port_type {
            let vid = usb.vid;
            let pid = usb.pid;
            if let Some(&(_, _, name, fqbn, wokwi)) =
                BOARD_MAP.iter().find(|&&(v, p, _, _, _)| v == vid && p == pid)
            {
                devices.push(DetectedDevice {
                    port: info.port_name.clone(),
                    board: name.to_string(),
                    fqbn: fqbn.to_string(),
                    vendor_id: format!("{:04x}", vid),
                    product_id: format!("{:04x}", pid),
                    wokwi_chip: wokwi.map(String::from),
                });
            }
        }
    }
    devices
}

pub fn find_device(port: Option<&str>) -> Option<DetectedDevice> {
    list_devices()
        .into_iter()
        .find(|d| port.is_none() || Some(d.port.as_str()) == port)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn board_map_contains_arduino_uno() {
        assert!(
            BOARD_MAP.iter().any(|&(vid, pid, _, fqbn, _)| {
                vid == 0x2341 && pid == 0x0043 && fqbn == "arduino:avr:uno"
            }),
            "Arduino Uno (2341:0043) missing from BOARD_MAP"
        );
    }

    #[test]
    fn board_map_contains_esp32_cp210x() {
        assert!(
            BOARD_MAP.iter().any(|&(vid, pid, _, fqbn, _)| {
                vid == 0x10c4 && pid == 0xea60 && fqbn == "esp32:esp32:esp32"
            }),
            "ESP32 CP210x (10c4:ea60) missing from BOARD_MAP"
        );
    }

    #[test]
    fn board_map_all_entries_have_wokwi_chip() {
        for &(vid, pid, name, _, wokwi) in BOARD_MAP {
            assert!(
                wokwi.is_some(),
                "BOARD_MAP entry {name} ({vid:04x}:{pid:04x}) has no wokwi chip"
            );
        }
    }

    #[test]
    fn board_map_vendor_product_ids_nonzero() {
        for &(vid, pid, name, _, _) in BOARD_MAP {
            assert!(vid > 0, "vid == 0 for {name}");
            assert!(pid > 0, "pid == 0 for {name}");
        }
    }

    #[test]
    fn board_map_fqbns_have_two_colons() {
        for &(_, _, name, fqbn, _) in BOARD_MAP {
            assert_eq!(
                fqbn.chars().filter(|&c| c == ':').count(),
                2,
                "FQBN '{fqbn}' for {name} should have exactly 2 colons"
            );
        }
    }

    #[test]
    fn list_devices_does_not_panic() {
        let devices = list_devices();
        // No assert on count — hardware may or may not be present.
        for d in &devices {
            assert!(!d.port.is_empty(), "device port should not be empty");
            assert!(!d.fqbn.is_empty(), "device fqbn should not be empty");
            assert_eq!(d.vendor_id.len(), 4, "vendor_id should be 4 hex chars");
            assert_eq!(d.product_id.len(), 4, "product_id should be 4 hex chars");
        }
    }

    #[test]
    fn find_device_with_explicit_port_returns_none_when_not_connected() {
        // A port that almost certainly doesn't exist.
        let result = find_device(Some("COM_FAKE_999"));
        assert!(result.is_none());
    }
}
