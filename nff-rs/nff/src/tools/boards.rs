use serialport::available_ports;

pub const BOARD_MAP: &[(u16, u16, &str, &str)] = &[
    (0x2341, 0x0043, "Arduino Uno", "arduino:avr:uno"),
    (0x2341, 0x0010, "Arduino Mega 2560", "arduino:avr:mega"),
    (0x2341, 0x0036, "Arduino Leonardo", "arduino:avr:leonardo"),
    (0x2341, 0x0058, "Arduino Nano", "arduino:avr:nano"),
    (0x10c4, 0xea60, "ESP32 (CP210x)", "esp32:esp32:esp32"),
    (0x1a86, 0x7523, "ESP32 (CH340)", "esp32:esp32:esp32"),
    (0x0403, 0x6001, "ESP8266 (FTDI)", "esp8266:esp8266:generic"),
    // STMicroelectronics ST-Link debug+VCP bridges (on-board on Nucleo/Discovery and most
    // STM32 dev boards) and the DFU bootloader. One VID:PID covers many distinct STM32
    // boards, so the fqbn is only a sensible default the user can override with --board.
    (0x0483, 0x3748, "STM32 (ST-Link V2)", "STMicroelectronics:stm32:Nucleo_64"),
    (0x0483, 0x374b, "STM32 (ST-Link V2-1)", "STMicroelectronics:stm32:Nucleo_64"),
    (0x0483, 0x374e, "STM32 (ST-Link V3)", "STMicroelectronics:stm32:Nucleo_64"),
    (0x0483, 0x374f, "STM32 (ST-Link V3)", "STMicroelectronics:stm32:Nucleo_64"),
    (0x0483, 0xdf11, "STM32 (DFU bootloader)", "STMicroelectronics:stm32:GenF1"),
];

/// PlatformIO board catalog: board id → platform. Supplies the platform for the common
/// families; any board id is still accepted (PlatformIO resolves + installs the platform
/// on first build), which is what makes nff board-universal.
pub const PIO_BOARD_CATALOG: &[(&str, &str)] = &[
    // ESP32 family
    ("esp32dev", "espressif32"),
    ("esp32-s3-devkitc-1", "espressif32"),
    ("esp32-c3-devkitm-1", "espressif32"),
    ("esp32-c6-devkitc-1", "espressif32"),
    ("esp32-s2-saola-1", "espressif32"),
    // ESP8266
    ("esp01_1m", "espressif8266"),
    ("nodemcuv2", "espressif8266"),
    // RP2040 / Raspberry Pi Pico
    ("pico", "raspberrypi"),
    ("rpipicow", "raspberrypi"),
    // STM32
    ("genericSTM32F103C8", "ststm32"),
    ("nucleo_f401re", "ststm32"),
    ("bluepill_f103c8", "ststm32"),
    // Classic AVR
    ("uno", "atmelavr"),
    ("megaatmega2560", "atmelavr"),
    ("nanoatmega328", "atmelavr"),
    ("leonardo", "atmelavr"),
];

/// Best-effort PlatformIO platform for a board id, or None if unknown.
pub fn pio_platform_for(board: &str) -> Option<&'static str> {
    PIO_BOARD_CATALOG
        .iter()
        .find(|(id, _)| *id == board)
        .map(|(_, platform)| *platform)
}

/// Map an arduino-cli FQBN to a sensible default PlatformIO board id, for `nff init`
/// to seed `build.board` from a USB-detected device. None when there's no obvious match
/// (the user can always pass `--board <pio-id>`).
pub fn fqbn_to_pio_board(fqbn: &str) -> Option<&'static str> {
    match fqbn {
        "esp32:esp32:esp32" => Some("esp32dev"),
        "esp8266:esp8266:generic" => Some("nodemcuv2"),
        "arduino:avr:uno" => Some("uno"),
        "arduino:avr:mega" => Some("megaatmega2560"),
        "arduino:avr:nano" => Some("nanoatmega328"),
        "arduino:avr:leonardo" => Some("leonardo"),
        _ => None,
    }
}

#[derive(Debug, Clone)]
pub struct DetectedDevice {
    pub port: String,
    pub board: String,
    pub fqbn: String,
    pub vendor_id: String,
    pub product_id: String,
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
            if let Some(&(_, _, name, fqbn)) =
                BOARD_MAP.iter().find(|&&(v, p, _, _)| v == vid && p == pid)
            {
                devices.push(DetectedDevice {
                    port: info.port_name.clone(),
                    board: name.to_string(),
                    fqbn: fqbn.to_string(),
                    vendor_id: format!("{:04x}", vid),
                    product_id: format!("{:04x}", pid),
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
            BOARD_MAP.iter().any(|&(vid, pid, _, fqbn)| {
                vid == 0x2341 && pid == 0x0043 && fqbn == "arduino:avr:uno"
            }),
            "Arduino Uno (2341:0043) missing from BOARD_MAP"
        );
    }

    #[test]
    fn board_map_contains_esp32_cp210x() {
        assert!(
            BOARD_MAP.iter().any(|&(vid, pid, _, fqbn)| {
                vid == 0x10c4 && pid == 0xea60 && fqbn == "esp32:esp32:esp32"
            }),
            "ESP32 CP210x (10c4:ea60) missing from BOARD_MAP"
        );
    }

    #[test]
    fn board_map_contains_stlink_v2_1() {
        assert!(
            BOARD_MAP.iter().any(|&(vid, pid, name, _)| {
                vid == 0x0483 && pid == 0x374b && name == "STM32 (ST-Link V2-1)"
            }),
            "STM32 ST-Link V2-1 (0483:374b) missing from BOARD_MAP"
        );
    }

    #[test]
    fn board_map_vendor_product_ids_nonzero() {
        for &(vid, pid, name, _) in BOARD_MAP {
            assert!(vid > 0, "vid == 0 for {name}");
            assert!(pid > 0, "pid == 0 for {name}");
        }
    }

    #[test]
    fn board_map_fqbns_have_two_colons() {
        for &(_, _, name, fqbn) in BOARD_MAP {
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

    #[test]
    fn pio_platform_lookup_known_and_unknown() {
        assert_eq!(pio_platform_for("esp32dev"), Some("espressif32"));
        assert_eq!(pio_platform_for("pico"), Some("raspberrypi"));
        assert_eq!(pio_platform_for("some_exotic_board"), None);
    }
}
