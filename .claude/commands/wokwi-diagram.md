# wokwi-diagram — Wokwi diagram.json Authoring Reference

Use this skill whenever writing or editing a Wokwi `diagram.json` schematic.
It is the ground-truth pin reference for all Wokwi components.

---

## diagram.json Structure

```json
{
  "version": 1,
  "author": "nff",
  "editor": "wokwi",
  "parts": [ ... ],
  "connections": [ ... ]
}
```

Each connection: `["partId:pin", "partId:pin", "color", [waypoints]]`
- `color`: any CSS color string, or `""` for default
- `waypoints`: `[]` for auto-route, or relative offsets like `["h30", "v-20"]`

---

## Serial Monitor (always wire this for ESP32/Arduino)

```json
["esp:TX0", "$serialMonitor:RX", "", []],
["esp:RX0", "$serialMonitor:TX", "", []]
```

---

## MCU Pin Reference

### wokwi-esp32-devkit-v1

| Pin group | Names |
|---|---|
| GPIO | `D0` `D1` `D2` `D4` `D5` `D12`–`D19` `D21`–`D23` `D25`–`D27` `D32`–`D35` |
| UART | `TX` (GPIO1), `RX` (GPIO3) |
| Analog-only | `VP` (GPIO36), `VN` (GPIO39), `D34`, `D35` |
| Power | `3V3`, `VIN`, `GND.1` (left-column GND), `GND.2` (right-column GND) |
| Other | `EN` |

> Use `GND.1` for most circuits — it is the left-column GND between D12 and D13.

### wokwi-arduino-uno

| Pin group | Names |
|---|---|
| Digital | `D0`–`D13` |
| Analog | `A0`–`A5` |
| Power | `5V`, `3V3`, `GND.1`, `GND.2` |
| Other | `AREF`, `IOREF`, `RESET` |

### wokwi-arduino-nano

Same as Uno plus `AREF`. Power: `5V`, `3V3`, `GND.1`, `GND.2`.

---

## Component Pin Reference

### wokwi-led

| Pin | Role |
|---|---|
| `A` | Anode (positive, connect toward GPIO via resistor) |
| `C` | Cathode (negative, connect to GND) — **NOT `K`** |

```json
{ "type": "wokwi-led", "id": "led1", "top": 100, "left": 200, "attrs": { "color": "red" } }
```

Colors: `"red"`, `"green"`, `"blue"`, `"yellow"`, `"white"`, `"orange"`

**Standard blink circuit (GPIO → R → LED → GND):**
```json
["esp:D2",  "r1:1",   "green", []],
["r1:2",    "led1:A", "green", []],
["led1:C",  "esp:GND.1", "black", []]
```

---

### wokwi-resistor

| Pin | Role |
|---|---|
| `1` | Terminal 1 |
| `2` | Terminal 2 |

```json
{ "type": "wokwi-resistor", "id": "r1", "top": 100, "left": 150, "attrs": { "value": "220" } }
```

Common values: `"220"` (LED current limit), `"1000"`, `"10000"` (pull-up/down)

Add `"rotate": 90` to orient vertically.

---

### wokwi-pushbutton

| Pin | Role |
|---|---|
| `1.l` | Side 1 left lead |
| `1.r` | Side 1 right lead |
| `2.l` | Side 2 left lead |
| `2.r` | Side 2 right lead |

`1.*` and `2.*` are shorted when button is pressed. Typical wiring with `INPUT_PULLUP`:
```json
["esp:D4",  "btn1:1.l", "green", []],
["esp:GND.1", "btn1:2.l", "black", []]
```

```json
{ "type": "wokwi-pushbutton", "id": "btn1", "top": 100, "left": 200, "attrs": { "color": "blue" } }
```

---

### wokwi-servo

| Pin | Role |
|---|---|
| `PWM` | Signal (connect to GPIO) |
| `V+` | Power (connect to 5V or 3V3) |
| `GND` | Ground |

```json
{ "type": "wokwi-servo", "id": "srv1", "top": 100, "left": 200, "attrs": { "minAngle": "-90", "maxAngle": "90" } }
```

```json
["esp:D18",    "srv1:PWM", "orange", []],
["esp:3V3",    "srv1:V+",  "red",    []],
["esp:GND.1",  "srv1:GND", "black",  []]
```

---

### wokwi-ntc-temperature-sensor

| Pin | Role |
|---|---|
| `VCC` | Power (3.3V or 5V) |
| `GND` | Ground |
| `OUT` | Analog output (connect to ADC pin) |

```json
["esp:3V3",   "tmp1:VCC", "red",   []],
["esp:GND.1", "tmp1:GND", "black", []],
["esp:D34",   "tmp1:OUT", "green", []]
```

---

### wokwi-dht22

| Pin | Role |
|---|---|
| `VCC` | Power |
| `GND` | Ground |
| `SDA` | Data (connect to GPIO, no extra resistor needed in Wokwi) |

---

### wokwi-ssd1306

| Pin | Role |
|---|---|
| `VCC` | Power (3.3V) |
| `GND` | Ground |
| `SCL` | I2C clock |
| `SDA` | I2C data |

Default I2C on ESP32: `SCL = D22`, `SDA = D21`.

---

### wokwi-hc-sr04 (ultrasonic)

| Pin | Role |
|---|---|
| `VCC` | 5V |
| `GND` | Ground |
| `TRIG` | Trigger pulse (GPIO output) |
| `ECHO` | Echo return (GPIO input) |

---

## Positioning Tips

- `top` / `left` are canvas pixels; `0,0` is top-left of the first placed part.
- ESP32 DevKit V1 occupies roughly 160 × 400 px.
- Place external components to the **right** of the ESP32 (left ≈ 200+) to align with the right-column pins (D2, GND.2, etc.).
- Place components to the **left** (left ≈ -150) to align with left-column pins (D32, GND.1, etc.).
- `"rotate": 90` rotates a component 90° clockwise.

---

## Common Mistakes

| Mistake | Correct |
|---|---|
| `led1:K` | `led1:C` — Wokwi uses `C` for cathode, not the standard `K` |
| `esp:GND` | `esp:GND.1` or `esp:GND.2` — always use the numbered suffix |
| `esp:GPIO2` | `esp:D2` — Wokwi prefixes GPIO numbers with `D` |
| `esp:TX0` in connections | `esp:TX` — omit the `0` suffix for UART pins |
