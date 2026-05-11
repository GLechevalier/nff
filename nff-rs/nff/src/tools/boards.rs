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
