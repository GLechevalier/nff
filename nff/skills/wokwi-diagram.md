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
  "parts": [],
  "connections": []
}
```

- `"version"` is always `1`
- `"author"` is the creator name
- `"editor"` is always `"wokwi"`
- Optional `"serialMonitor"` section configures the Serial Monitor:
  ```json
  "serialMonitor": { "display": "plotter", "newline": "lf", "convertEol": false }
  ```
  `display`: `"terminal"` (default) or `"plotter"`. `newline`: `"lf"`, `"crlf"`, `"cr"`, or `"none"`.

### Parts

Each part object:

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | yes | Unique identifier (e.g. `"led1"`) |
| `type` | string | yes | Component type (e.g. `"wokwi-led"`) |
| `left` | number | no | X canvas coordinate (pixels) |
| `top` | number | no | Y canvas coordinate (pixels) |
| `attrs` | object | no | Component-specific attributes |
| `rotate` | number | no | Rotation in degrees (e.g. `90`) |
| `hide` | boolean | no | If `true`, part is invisible |

> Every `id` must be unique — duplicate IDs break simulation.

### Connections

Each connection: `["partId:pin", "partId:pin", "color", [waypoints]]`
- `color`: any CSS color string, or `""` to hide the wire
- `waypoints`: `[]` for auto-route, or wire placement instructions

### Wire Placement Mini-Language

Instructions control how the wire is drawn from source to target:

| Instruction | Effect |
|---|---|
| `"v<N>"` | Move N pixels vertically (positive = down) |
| `"h<N>"` | Move N pixels horizontally (positive = right) |
| `"*"` | Separator: instructions before apply to source pin, instructions after apply to target pin (in reverse order) |

Example: `["v10", "h5", "*", "v-15", "h10"]` — from source: down 10, right 5; from target: right 10, up 15; simulator bridges the gap.

### Supported MCUs

| Type | Board |
|---|---|
| `wokwi-attiny85` | ATtiny85 |
| `wokwi-arduino-nano` | Arduino Nano |
| `wokwi-arduino-mega` | Arduino Mega 2560 |
| `wokwi-arduino-uno` | Arduino Uno R3 |
| `wokwi-pi-pico` | Raspberry Pi Pico |
| `board-esp32-devkit-c-v4` | ESP32 official devkit |
| `wokwi-esp32-devkit-v1` | ESP32 unofficial devkit |
| `board-esp32-c3-devkitm-1` | ESP32-C3 |
| `board-esp32-c6-devkitc-1` | ESP32-C6 |
| `board-esp32-h2-devkitm-1` | ESP32-H2 |
| `board-esp32-s2-devkitm-1` | ESP32-S2 |
| `board-esp32-s3-devkitc-1` | ESP32-S3 |
| `board-esp32-p4-preview` | ESP32-P4 |
| `board-xiao-esp32-c3` | XIAO ESP32-C3 |
| `board-xiao-esp32-c6` | XIAO ESP32-C6 |
| `board-xiao-esp32-s3` | XIAO ESP32-S3 |
| `board-st-nucleo-c031c6` | STM32 Nucleo-64 STM32C031C6 |
| `board-st-nucleo-l031k6` | STM32 Nucleo-32 STM32L031K6 |
| `board-franzininho-wifi` | ESP32-S2 (Franzininho WiFi) |
| `board-stm32-bluepill` | STM32 Blue Pill |

> ATtiny85, Pi Pico, Franzininho WiFi, STM32 Nucleo, Blue Pill pin details → `/wokwi-diagram-extended`

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

ATmega328p, 16 MHz, 32 KB Flash, 2 KB SRAM, 1 KB EEPROM.
Pin naming: **numeric without prefix** (`2`, `13`) — NOT `D2`/`D13`.

| Pin group | Names |
|---|---|
| Digital | `0`–`13` |
| Analog | `A0`–`A5` (also usable as digital GPIO) |
| PWM | `3`, `5`, `6`, `9`, `10`, `11` |
| GND | `GND.1` (top, near pin 13), `GND.2`, `GND.3` (bottom) |
| Power | `5V`, `VIN` |
| I2C | SDA = `A4`, SCL = `A5` |
| SPI | SS = `10`, MOSI = `11`, MISO = `12`, SCK = `13` |
| Interrupts | INT0 = `2`, INT1 = `3` |

Onboard LED: pin `13` = `LED_BUILTIN`.
Attr: `"frequency"`: `"8m"`, `"16m"` (default), `"20m"` — changing breaks most libraries.
Simulation: I2C/SPI master only; Analog Comparator not implemented.

### wokwi-arduino-mega

ATmega2560, 16 MHz, 256 KB Flash, 8 KB SRAM, 4 KB EEPROM.
Pin naming: **numeric without prefix** (`2`, `13`, `A0`) — same as Uno.

| Pin group | Names |
|---|---|
| Digital | `0`–`53` |
| Analog | `A0`–`A15` |
| PWM | `2`–`13`, `44`, `45`, `46` |
| GND | `GND.1` (near pin 13), `GND.2`/`GND.3` (near Vin), `GND.4`/`GND.5` (dual-row header) |
| Power | `5V`, `VIN`, `5V.1`, `5V.2` (dual-row header) |
| I2C | SDA = `20`, SCL = `21` |
| SPI | MISO = `50`, MOSI = `51`, SCK = `52` |
| Serial1 | TX = `18`, RX = `19` |
| Serial2 | TX = `16`, RX = `17` |
| Serial3 | TX = `14`, RX = `15` |

Onboard LED: pin `13` = `LED_BUILTIN`.
Simulation: I2C and SPI are master-only; 16-bit timer input capture not implemented.

Serial monitor (Serial0, same as Uno):
```json
["mega:0", "$serialMonitor:TX", "", []],
["mega:1", "$serialMonitor:RX", "", []]
```

---

### wokwi-arduino-nano

ATmega328p — same as Uno (32 KB Flash, 2 KB SRAM, 1 KB EEPROM). Pin naming: numeric without prefix.
Power: `5V`, `3V3`, `GND.1`, `GND.2`. Same I2C/SPI pins as Uno (A4/A5, 12/11/13).

Difference from Uno: adds `A6` and `A7` — **analog input only**, cannot be used as digital GPIO.

> ATtiny85, Pi Pico, Franzininho WiFi, STM32 Nucleo/Blue Pill → `/wokwi-diagram-extended`

---

## Component Pin Reference

### wokwi-led

| Pin | Role |
|---|---|
| `A` | Anode (positive, connect toward GPIO via resistor) |
| `C` | Cathode (negative, connect to GND) — **NOT `K`** |

| Attr | Default | Description |
|---|---|---|
| `color` | `"red"` | LED body color — named (`"red"`, `"green"`, `"blue"`, `"yellow"`, `"white"`, `"orange"`, `"limegreen"`) or hex (`"#FFFF00"`) |
| `lightColor` | *(derived from `color`)* | Emitted light color override — useful when body color and light color differ (e.g. white body with `"lightColor": "orange"` for warm-white) |
| `label` | `""` | Text displayed below the LED in the diagram |
| `gamma` | `"2.8"` | Gamma correction factor — makes low `analogWrite()` values visibly light the LED (mimics real LED behavior). Set `"1.0"` to disable. |
| `fps` | `"80"` | LED brightness update rate. Lower (e.g. `"30"`) reduces PWM flicker; raise (e.g. `"10000"`) to prevent ghosting in LED scanning / Charlieplexing. |
| `flip` | `""` | Set `"1"` to mirror the LED horizontally — useful when placing to the left of the MCU |

> To rotate a LED, set `"rotate": 90` (or 180, 270) in the part object.

```json
{ "type": "wokwi-led", "id": "led1", "top": 100, "left": 200, "attrs": { "color": "red" } }
```

Custom light color example (white body, orange light):
```json
{ "type": "wokwi-led", "id": "led1", "top": 0, "left": 120, "attrs": { "color": "white", "lightColor": "orange", "label": "Status" } }
```

**Standard blink circuit (GPIO → R → LED → GND):**
```json
["esp:D2",  "r1:1",   "green", []],
["r1:2",    "led1:A", "green", []],
["led1:C",  "esp:GND.1", "black", []]
```

---

### wokwi-resistor

> Wokwi has only basic analog simulation — resistors work correctly as pull-ups/pull-downs and in LED current-limiting circuits, but cannot be used in full analog divider calculations with components like potentiometers or NTC sensors.

| Pin | Role |
|---|---|
| `1` | Terminal 1 |
| `2` | Terminal 2 |

| Attr | Default | Common values |
|---|---|---|
| `value` | `"1000"` | `"220"` (LED), `"1000"`, `"4700"` (1-Wire pull-up), `"10000"` (pull-up/down) |

```json
{ "type": "wokwi-resistor", "id": "r1", "top": 100, "left": 150, "rotate": 90, "attrs": { "value": "220" } }
```

Add `"rotate": 90` to orient vertically (typical when bridging between two horizontal pins).

**External pull-down for active-HIGH button (button → pin 2, GND via R):**
```json
["btn1:1.l", "uno:5V",    "red",   []],
["btn1:2.r", "uno:2",     "green", []],
["r1:1",     "btn1:2.r",  "green", []],
["r1:2",     "uno:GND.1", "black", []]
```

---

### wokwi-potentiometer

Also applies to `wokwi-slide-potentiometer` (same pins, attrs, and controls).

| Pin | Role |
|---|---|
| `VCC` | Power |
| `GND` | Ground |
| `SIG` | Wiper output — connect to ADC pin |

> GND/VCC are optional in simulation (no full analog sim), but always wire them for real-hardware parity.

| Attr | Default | Description |
|---|---|---|
| `value` | `"0"` | Initial wiper position (0–1023) |

**Keyboard shortcuts** (click pot to focus): Left/Right — fine · PageUp/PageDown — coarse · Home/End — 0 or 1023.

**Automation control:** `position` (float 0.0–1.0) — e.g. `value: 0.5` = middle.

```json
{ "type": "wokwi-potentiometer", "id": "pot1", "top": 100, "left": 200, "attrs": { "value": "0" } }
```

ESP32 wiring (SIG on GPIO34 — ADC-only pin):
```json
["pot1:SIG", "esp:D34",   "green", []],
["pot1:VCC", "esp:3V3",   "red",   []],
["pot1:GND", "esp:GND.1", "black", []]
```

Arduino Uno + servo (potentiometer on A0, servo on pin 9):
```json
["pot1:SIG", "uno:A0",    "green", []],
["pot1:VCC", "uno:5V",    "red",   []],
["pot1:GND", "uno:GND.1", "black", []],
["uno:9",    "srv1:PWM",  "orange",[]],
["uno:5V",   "srv1:V+",   "red",   []],
["uno:GND.1","srv1:GND",  "black", []]
```

Add `"rotate": 90` (or `270`) for vertical orientation.

---

### wokwi-slide-potentiometer

Same pins (`VCC`, `GND`, `SIG`), same `value` attr, same keyboard shortcuts and automation control (`position` float 0.0–1.0) as `wokwi-potentiometer`. Only difference: the `travelLength` attr controls the physical width of the slider.

| Attr | Default | Common values |
|---|---|---|
| `travelLength` | `"30"` | `"15"`, `"20"`, `"30"`, `"45"`, `"60"`, `"100"` (mm) |

```json
{ "type": "wokwi-slide-potentiometer", "id": "pot1", "top": 79, "left": 400,
  "attrs": { "travelLength": "30", "value": "0" } }
```

Add `"rotate": 270` to orient the slider vertically (tip at top). Wiring is identical to `wokwi-potentiometer` — see above.

---

### wokwi-pushbutton

| Pin | Role |
|---|---|
| `1.l` / `1.r` | Contact 1 — left / right lead (always shorted together) |
| `2.l` / `2.r` | Contact 2 — left / right lead (always shorted together) |

Pressing the button connects contact 1 to contact 2. Use any `.l` or `.r` variant — both sides of the same contact are equivalent.

| Attr | Default | Description |
|---|---|---|
| `color` | `"red"` | Button color (named or hex) |
| `label` | `""` | Text displayed below the button |
| `key` | | Keyboard shortcut — letters/numbers are case-insensitive; special keys (`"Escape"`, `"ArrowUp"`, `"F8"`, `" "`) are case-sensitive |
| `bounce` | `""` | Default: simulates contact bounce (~10–100 transitions over ~1 ms). Set `"0"` to disable. |
| `xray` | `""` | Set `"1"` to show internal wiring |

**Active-LOW wiring (INPUT_PULLUP — reads LOW when pressed):**
```json
["btn1:1.l", "esp:D4",    "green", []],
["btn1:2.l", "esp:GND.1", "black", []]
```

**Active-HIGH wiring (external pull-down, reads HIGH when pressed):**
```json
["btn1:1.r", "uno:5V",    "red",   []],
["btn1:2.l", "uno:8",     "green", []],
["btn1:2.l", "r1:1",      "green", []],
["r1:2",     "uno:GND.2", "black", []]
```
> `r1` is a 10 kΩ pull-down resistor.

```json
{ "type": "wokwi-pushbutton", "id": "btn1", "top": 100, "left": 200,
  "attrs": { "color": "blue", "label": "SET", "key": "s", "bounce": "0" } }
```

**Tip:** Ctrl-click (Cmd-click on Mac) to latch the button pressed until the next click — useful when two buttons must be held simultaneously.

**Automation control:** `pressed` (int) — `1` = press, `0` = release.

---

### wokwi-servo

Range of motion: 0°–180° (hard stops at both ends).

| Pin | Role |
|---|---|
| `PWM` | Control signal (connect to GPIO — use PWM-capable pin) |
| `V+` | Power (**5V**) |
| `GND` | Ground |

| Attr | Default | Description |
|---|---|---|
| `horn` | `"single"` | Horn shape: `"single"`, `"double"`, or `"cross"` |
| `hornColor` | `"#ccc"` | Horn color (any CSS color, e.g. `"black"` or `"#000088"`) |

```json
{ "type": "wokwi-servo", "id": "srv1", "top": 200, "left": 400, "attrs": { "horn": "single", "hornColor": "#ccc" } }
```

**Arduino Uno wiring (PWM pin 9):**
```json
["uno:9",     "srv1:PWM", "orange", []],
["uno:5V",    "srv1:V+",  "red",    []],
["uno:GND.1", "srv1:GND", "black",  []]
```

**ESP32 (`board-esp32-devkit-c-v4`) wiring (pin 18):**
```json
["esp:18",    "srv1:PWM", "green", []],
["esp:5V",    "srv1:V+",  "red",   []],
["esp:GND.2", "srv1:GND", "black", []]
```

**Potentiometer knob → servo (Uno, pot on A0, servo on pin 9):**
```json
["uno:A0",    "pot1:SIG", "green", []],
["uno:5V",    "pot1:VCC", "red",   []],
["uno:GND.1", "pot1:GND", "black", []],
["uno:9",     "srv1:PWM", "orange",[]],
["uno:5V",    "srv1:V+",  "red",   []],
["uno:GND.1", "srv1:GND", "black", []]
```

> For ESP32 use the built-in LEDC peripheral — see CLAUDE.md for duty values and `ledcAttach` / `ledcWrite` details. The `Servo` library works on Uno/Nano without extra config.

---

### wokwi-7segment (7-segment LED display)

| Pin | Role |
|---|---|
| `A`–`G` | Segments (Top, Top-R, Bottom-R, Bottom, Bottom-L, Top-L, Middle) |
| `DP` | Decimal point |
| `COM` | Common pin — single-digit only |
| `DIG1`–`DIG4` | Digit select — multi-digit (replaces `COM`) |
| `CLN` | Colon — only when `colon` attr is set |

| Attr | Default | Values |
|---|---|---|
| `common` | `"anode"` | `"anode"` or `"cathode"` |
| `digits` | `"1"` | `"1"` `"2"` `"3"` `"4"` |
| `colon` | `""` | `"1"` or `"true"` to enable colon between digit 2 and 3 |
| `color` | `"red"` | Any CSS color e.g. `"green"`, `"#0f0"` |

**Default anode mode:** `DIG*` pins go HIGH to select a digit; segment pins `A`–`G` go LOW to light a segment. Each segment needs a ~180Ω resistor in series.

Single digit (anode, COM → 5V, segments via resistors):
```json
{ "type": "wokwi-7segment", "id": "seg1", "top": 0, "left": 200, "attrs": { "digits": "1", "common": "anode" } }
```
```json
["seg1:COM", "uno:5V",    "red",   []],
["seg1:A",   "r1:2",      "green", []],
["r1:1",     "uno:6",     "green", []]
```

4-digit clock display (anode, DIG1–4 → MCU, CLN enabled):
```json
{ "type": "wokwi-7segment", "id": "seg1", "top": 0, "left": 200, "attrs": { "digits": "4", "colon": "1", "common": "anode" } }
```
```json
["seg1:DIG1", "uno:2",  "blue",   []],
["seg1:DIG2", "uno:3",  "orange", []],
["seg1:DIG3", "uno:4",  "red",    []],
["seg1:DIG4", "uno:5",  "purple", []],
["seg1:A",    "uno:6",  "gray",   []],
["seg1:B",    "uno:7",  "green",  []],
["seg1:C",    "uno:8",  "blue",   []],
["seg1:D",    "uno:9",  "orange", []],
["seg1:E",    "uno:10", "red",    []],
["seg1:F",    "uno:11", "purple", []],
["seg1:G",    "uno:12", "gray",   []],
["seg1:CLN",  "uno:13", "cyan",   []]
```

> Using a 74HC595 shift register to drive segments saves 5 MCU pins — see `wokwi-74hc595` in `/wokwi-diagram-extended`.
> For Arduino: `SevSeg` library handles multiplexing.

---

### wokwi-buzzer

| Pin | Role |
|---|---|
| `1` | Ground side |
| `2` | Signal (connect to MCU GPIO) |

```json
{ "type": "wokwi-buzzer", "id": "bz1", "top": 100, "left": 200, "attrs": { "volume": "0.1" } }
```

Attrs: `"volume"` (default `"1.0"`, use `"0.1"` for quiet simulation). `"mode"`: `"smooth"` (default, best for `tone()`) or `"accurate"` (complex waveforms, adds click noise).
```json
["bz1:1", "esp:GND.1", "black",  []],
["bz1:2", "esp:D18",   "orange", []]
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

### wokwi-lcd1602 / wokwi-lcd2004 (character LCD)

| Type | Size |
|---|---|
| `wokwi-lcd1602` | 16 characters × 2 lines |
| `wokwi-lcd2004` | 20 characters × 4 lines |

Same HD44780 controller — identical pins, attrs, and wiring. Supports two wiring modes controlled by the `pins` attr.

| Attr | Default | Description |
|---|---|---|
| `pins` | `"full"` | `"full"` = standard parallel, `"i2c"` = I2C via PCF8574T |
| `i2cAddress` | `"0x27"` | I2C address (I2C mode only) |
| `color` | `"black"` | Text color |
| `background` | `"green"` | Backlight color (e.g. `"blue"` with `"white"` text) |
| `variant` | `"A00"` | Font ROM: `"A00"` (Japanese katakana), `"A02"` (Western European + Cyrillic) |

---

#### I2C mode (`"pins": "i2c"`) — preferred, 2 wires

Library: `LiquidCrystal_I2C`. Default address `0x27`.

| Pin | Role |
|---|---|
| `VCC` | Power (5V) |
| `GND` | Ground |
| `SDA` | I2C data |
| `SCL` | I2C clock |

```json
{ "type": "wokwi-lcd1602", "id": "lcd1", "top": 100, "left": 200, "attrs": { "pins": "i2c" } }
```

Arduino Uno (I2C — SDA = A4, SCL = A5):
```json
["lcd1:VCC", "uno:5V",    "red",   []],
["lcd1:GND", "uno:GND.1", "black", []],
["lcd1:SDA", "uno:A4",    "blue",  []],
["lcd1:SCL", "uno:A5",    "gold",  []]
```

ESP32 (I2C — SDA = D21, SCL = D22):
```json
["lcd1:VCC", "esp:VIN",   "red",   []],
["lcd1:GND", "esp:GND.1", "black", []],
["lcd1:SDA", "esp:D21",   "blue",  []],
["lcd1:SCL", "esp:D22",   "gold",  []]
```

---

#### Standard mode (`"pins": "full"`) — 4-bit parallel, 6 wires to MCU

Library: `LiquidCrystal(RS, E, D4, D5, D6, D7)`. **Always connect `RW` to GND.** `V0` (contrast) and `D0`–`D3` are not needed in 4-bit mode.

| Pin | Role | Notes |
|---|---|---|
| `VSS` | Ground | |
| `VDD` | Power (5V) | |
| `V0` | Contrast | Not simulated — leave unconnected |
| `RS` | Command / data select | Any digital pin |
| `RW` | Read / Write | **Must connect to GND** |
| `E` | Enable | Any digital pin |
| `D4`–`D7` | Data (4-bit mode) | Any digital pins |
| `D0`–`D3` | Data (8-bit mode) | Leave unconnected in 4-bit mode |
| `A` | Backlight anode | 5V (or GPIO for dimming) |
| `K` | Backlight cathode | GND |

```json
{ "type": "wokwi-lcd1602", "id": "lcd1", "top": 100, "left": 200, "attrs": {} }
```

Arduino Uno wiring (RS=12, E=11, D4=10, D5=9, D6=8, D7=7):
```json
["lcd1:VSS", "uno:GND.1", "black",  []],
["lcd1:VDD", "uno:5V",    "red",    []],
["lcd1:RW",  "uno:GND.1", "black",  []],
["lcd1:RS",  "uno:12",    "blue",   []],
["lcd1:E",   "uno:11",    "purple", []],
["lcd1:D4",  "uno:10",    "green",  []],
["lcd1:D5",  "uno:9",     "brown",  []],
["lcd1:D6",  "uno:8",     "gold",   []],
["lcd1:D7",  "uno:7",     "gray",   []],
["lcd1:A",   "uno:5V",    "red",    []],
["lcd1:K",   "uno:GND.1", "black",  []]
```

> Custom characters: use `lcd.createChar(index, bitmap)` (indexes 0–7), print with `lcd.write(index)`. Characters can be updated at runtime for simple animations.

**wokwi-lcd2004 part declaration (4-line, 20-char):**
```json
{ "type": "wokwi-lcd2004", "id": "lcd1", "top": 8, "left": 20, "attrs": {} }
```

I2C mode:
```json
{ "type": "wokwi-lcd2004", "id": "lcd1", "top": 8, "left": 20, "attrs": { "pins": "i2c" } }
```

All wiring is identical to `wokwi-lcd1602` — substitute `"wokwi-lcd2004"` as the `type` and reuse the connections above verbatim.

---

### wokwi-dht22

| Pin | Role |
|---|---|
| `VCC` | Power (3.3V or 5V) |
| `GND` | Ground |
| `SDA` | Data — no pull-up resistor needed in Wokwi |
| `NC` | Not connected |

| Attr | Default |
|---|---|
| `temperature` | `"24"` (°C) |
| `humidity` | `"40"` (%) |

> On ESP32 use the **"DHT sensor library for ESPx"** library — generic DHT22 libraries are unreliable on ESP32.

```json
["dht1:VCC", "esp:3V3",   "red",   []],
["dht1:GND", "esp:GND.1", "black", []],
["dht1:SDA", "esp:D15",   "green", []]
```

---

### wokwi-ssd1306 / board-ssd1306 (128×64 OLED)

Monochrome 128×64 I2C OLED. Both type names are valid; `board-ssd1306` is the current name.

| Pin | Role | Arduino Uno |
|---|---|---|
| `VCC` | Power (3.3V or 5V) | 5V |
| `GND` | Ground | GND |
| `SCL` | I2C clock | A5 |
| `SDA` | I2C data | A4 |

| Attr | Default | Description |
|---|---|---|
| `i2cAddress` | `"0x3c"` | I2C address — use `"0x3d"` for modules with alternate address |

Default I2C on ESP32 (`wokwi-esp32-devkit-v1`): `SCL = D22`, `SDA = D21`.

Compatible libraries (all available on Wokwi): `Adafruit SSD1306`, `U8g2`, `U8glib`, `lcdgfx`, `ssd1306`, `SSD1306Ascii`, `Tiny4kOLED` (ATtiny85).

```json
{ "type": "board-ssd1306", "id": "oled1", "top": 100, "left": 200, "attrs": { "i2cAddress": "0x3c" } }
```

```json
["oled1:SCL", "esp:D22",   "purple", []],
["oled1:SDA", "esp:D21",   "blue",   []],
["oled1:VCC", "esp:3V3",   "red",    []],
["oled1:GND", "esp:GND.1", "black",  []]
```

---

### wokwi-slide-switch

SPDT slide switch. Pin `2` is the common (wiper); pins `1` and `3` are the two positions.
- Switch toward `1`: pins `1`–`2` connected
- Switch toward `3`: pins `2`–`3` connected

| Pin | Role |
|---|---|
| `1` | Position A terminal |
| `2` | Common (wiper) — connect to signal |
| `3` | Position B terminal |

Attr: `"value": "1"` sets initial position (`"1"` = toward pin 1, `"0"` = toward pin 3).

Typical use (HIGH/LOW input to MCU):
```json
["sw1:1", "esp:3V3",   "red",   []],
["sw1:3", "esp:GND.1", "black", []],
["sw1:2", "esp:D4",    "green", []]
```

---

### wokwi-text (label)

Visual text label — no electrical pins. Use for annotating diagrams.

```json
{ "type": "wokwi-text", "id": "lbl1", "top": 0, "left": 200, "attrs": { "text": "Line 1\nLine 2" } }
```

`\n` in the `text` attr creates multi-line labels.

---

### wokwi-hc-sr04 (ultrasonic distance sensor)

| Pin | Role |
|---|---|
| `VCC` | 5V |
| `GND` | Ground |
| `TRIG` | Trigger — pulse HIGH for ≥10 µs to start measurement |
| `ECHO` | Echo — HIGH pulse length proportional to distance |

Attr: `"distance"` sets initial distance in cm (default `"400"`, range 2–400).

Distance conversion: `cm = pulseIn(ECHO, HIGH) / 58` · `inches = pulseIn(ECHO, HIGH) / 148`

```json
{ "type": "wokwi-hc-sr04", "id": "sonar1", "top": 0, "left": 200, "attrs": { "distance": "100" } }
```
```json
["sonar1:VCC",  "uno:5V",    "red",    []],
["sonar1:GND",  "uno:GND.1", "black",  []],
["sonar1:TRIG", "uno:3",     "purple", []],
["sonar1:ECHO", "uno:2",     "green",  []]
```

---

### board-bmp180 (barometric pressure + temperature)

I2C address `0x77`. Compatible with BMP085 libraries (e.g. `Adafruit_BMP085`).

| Pin | Role |
|---|---|
| `VCC` | Voltage supply |
| `3.3V` | 3.3V supply (use this on ESP32) |
| `GND` | Ground |
| `SCL` | I2C clock |
| `SDA` | I2C data |

| Attr | Default | Range |
|---|---|---|
| `temperature` | `"24"` | -40 to 85 °C |
| `pressure` | `"101325"` | 30000–110000 Pa |

> Also available as `wokwi-bmp180` (legacy type name).

Default I2C on ESP32 (`board-esp32-devkit-c-v4`): SCL = pin `22`, SDA = pin `21`.

```json
{ "type": "board-bmp180", "id": "bmp1", "top": 100, "left": 200, "attrs": { "temperature": "24", "pressure": "101325" } }
```

```json
["bmp1:SCL", "esp:22",    "green", []],
["bmp1:SDA", "esp:21",    "green", []],
["bmp1:3.3V","esp:3V3",   "red",   []],
["bmp1:GND", "esp:GND.2", "black", []]
```

Supports simulation controls (sliders) and automation `set-control` for `temperature` and `pressure`.

### wokwi-gas-sensor (MQ2 gas sensor)

Detects combustible gases (LPG, propane, hydrogen, methane, CO). Analog output for concentration, digital output for threshold detection.

| Pin | Role |
|---|---|
| `VCC` | Power (5V or 3.3V) |
| `GND` | Ground |
| `AOUT` | Analog output — voltage rises with gas concentration |
| `DOUT` | Digital output — goes **LOW** when ppm exceeds threshold |

> Pin names in diagram.json are `AOUT` and `DOUT` — **not** `AO`/`DO` as the datasheet labels suggest.

| Attr | Default | Description |
|---|---|---|
| `ppm` | `"400"` | Initial gas concentration in parts per million |
| `threshold` | `"4.4"` | Voltage threshold for `DOUT` to go LOW |

```json
{ "type": "wokwi-gas-sensor", "id": "gas1", "top": 100, "left": 200, "attrs": { "ppm": "400", "threshold": "4.4" } }
```

```json
["gas1:VCC",  "uno:3.3V",  "red",    []],
["gas1:GND",  "uno:GND.3", "black",  []],
["gas1:AOUT", "uno:A0",    "green",  []],
["gas1:DOUT", "uno:8",     "violet", []]
```

Use `analogRead(A0)` for relative concentration; `digitalRead(8)` reads LOW when threshold is exceeded.

---

### wokwi-mpu6050 (6-axis IMU — accelerometer + gyroscope)

3-axis accelerometer, 3-axis gyroscope, and temperature sensor in one I2C package.

| Pin | Role |
|---|---|
| `VCC` | Power (3.3V) |
| `GND` | Ground |
| `SCL` | I2C clock |
| `SDA` | I2C data |
| `AD0` | Address select — float = `0x68`, connect to VCC = `0x69` |
| `INT` | Interrupt output (active low) |
| `XDA` / `XCL` | Auxiliary I2C master — not implemented in simulator |

| Attr | Default | Description |
|---|---|---|
| `accelX` | `"0"` | X acceleration (g-force, 1 g = 9.80665 m/s²) |
| `accelY` | `"0"` | Y acceleration (g) |
| `accelZ` | `"1"` | Z acceleration (g) — default 1g simulates sensor lying flat |
| `rotationX` | `"0"` | X angular rate (deg/s) |
| `rotationY` | `"0"` | Y angular rate (deg/s) |
| `rotationZ` | `"0"` | Z angular rate (deg/s) |
| `temperature` | `"24"` | Temperature (°C) |

All attrs are also available as **automation controls** (type `float`) — use `set-control` in simulation scenarios to animate sensor values at runtime.

```json
{ "type": "wokwi-mpu6050", "id": "mpu1", "top": 264, "left": 96, "attrs": { "accelZ": "1" } }
```

Arduino Uno wiring (SDA = A4, SCL = A5, **3.3V power**):
```json
["mpu1:VCC", "uno:3.3V",  "red",        []],
["mpu1:GND", "uno:GND.2", "black",      []],
["mpu1:SCL", "uno:A5",    "darkorange", []],
["mpu1:SDA", "uno:A4",    "yellow",     []]
```

ESP32 wiring (SDA = D21, SCL = D22):
```json
["mpu1:VCC", "esp:3V3",   "red",        []],
["mpu1:GND", "esp:GND.1", "black",      []],
["mpu1:SCL", "esp:D22",   "darkorange", []],
["mpu1:SDA", "esp:D21",   "yellow",     []]
```

Library: `Adafruit MPU6050` (+ `Adafruit_Sensor` + `Wire`). Key calls:
```cpp
Adafruit_MPU6050 mpu;
mpu.begin();                                          // default addr 0x68
mpu.getAccelerometerSensor()->getEvent(&accel_event); // accel_event.acceleration.x/y/z  [m/s²]
mpu.getGyroSensor()->getEvent(&gyro_event);           // gyro_event.gyro.x/y/z  [rad/s]
mpu.getTemperatureSensor()->getEvent(&temp_event);    // temp_event.temperature  [°C]
```

> For multiple sensors on the same bus, set one to `AD0` = VCC (`0x69`) and leave the other floating (`0x68`). Pass the address to `mpu.begin(0x69)`.

---

### wokwi-logic-analyzer (8-channel digital logic analyzer)

Captures digital signals to a VCD file for offline analysis. Does not affect circuit behavior — purely observational.

| Pin | Role |
|---|---|
| `D0`–`D7` | Input channels (connect to any digital signal to monitor) |
| `GND` | Digital ground reference — **always connect** |

| Attr | Default | Description |
|---|---|---|
| `bufferSize` | `"1000000"` | Max samples to capture (each slot = 9 bytes RAM; 1 M ≈ 9 MB) |
| `channelNames` | `"D0,D1,D2,D3,D4,D5,D6,D7"` | Comma-separated labels written into the VCD file — use signal names for readability (e.g. `"SCL,SDA,CS,MOSI"`) |
| `filename` | `"wokwi-logic"` | Base name of the downloaded VCD file (web only; VS Code uses `vcdFile` in `wokwi.toml`) |
| `triggerMode` | `"off"` | `"off"` = capture always; `"edge"` = start when `triggerPin` reaches `triggerLevel`; `"level"` = capture only while `triggerPin` holds `triggerLevel` |
| `triggerPin` | `"D7"` | Channel that activates the trigger (`"D0"`–`"D7"`) |
| `triggerLevel` | `"high"` | Trigger threshold: `"high"` or `"low"` |

**Trigger modes summary:**

| `triggerMode` | Behavior |
|---|---|
| `"off"` | All data recorded from simulation start |
| `"edge"` | Recording starts when `triggerPin` transitions to `triggerLevel`; continues until simulation ends |
| `"level"` | Recording starts on that transition, pauses when `triggerPin` changes again |

```json
{ "type": "wokwi-logic-analyzer", "id": "logic1", "top": 38, "left": 355,
  "attrs": { "channelNames": "SCL,SDA,CS,MOSI,MISO" } }
```

Minimal wiring — just GND and the channels you need:
```json
["uno:GND.2",  "logic1:GND", "black",  []],
["uno:A5",     "logic1:D0",  "gold",   []],
["uno:A4",     "logic1:D1",  "green",  []],
["uno:13",     "logic1:D2",  "orange", []]
```

> The logic analyzer saves a `.vcd` file when you stop the simulation. Open it in PulseView (free, cross-platform) or any VCD viewer. In VS Code, configure the output path with `vcdFile = "wokwi.vcd"` in `wokwi.toml`.

---

---

### wokwi-stepper-motor

Bipolar stepper motor — 1.8°/step, 200 steps/revolution. Supports half-stepping (0.9°/step). Typically driven by a `wokwi-a4988` driver, but can be wired directly to MCU GPIO pins in simulation (coil current is not simulated).

| Pin | Role |
|---|---|
| `A+` | Coil A positive |
| `A-` | Coil A negative |
| `B+` | Coil B positive |
| `B-` | Coil B negative |

| Attr | Default | Description |
|---|---|---|
| `display` | `"steps"` | Readout on motor body: `"steps"`, `"angle"` (degrees), or `"none"` |
| `arrow` | `""` | Show a direction arrow — set to a CSS color e.g. `"orange"` |
| `gearRatio` | `"1:1"` | Gear ratio — `"1:1"` = 200 steps/rev, `"2:1"` = 400 steps/rev |
| `size` | `"23"` | NEMA frame size: `"8"`, `"11"`, `"14"`, `"17"`, `"23"`, `"34"` |

```json
{ "type": "wokwi-stepper-motor", "id": "stepper1", "top": 0, "left": 200,
  "attrs": { "display": "angle", "arrow": "orange" } }
```

**Direct GPIO wiring (Arduino Uno, Arduino `Stepper` library — pins 8–11):**
```json
["stepper1:A+", "uno:10", "green", []],
["stepper1:A-", "uno:11", "green", []],
["stepper1:B+", "uno:9",  "green", []],
["stepper1:B-", "uno:8",  "green", []]
```
```cpp
#include <Stepper.h>
Stepper stepper(200, 8, 9, 10, 11);
// setup: stepper.setSpeed(60); // RPM
// loop:  stepper.step(200);    // one full revolution
```

**A4988 driver wiring** — see `wokwi-a4988` in `/wokwi-diagram-extended` for the full driver pin table and microstepping config.

> Libraries: `Stepper` (built-in), `AccelStepper` (acceleration/deceleration support). For `AccelStepper` use `FULL4WIRE` or `HALF4WIRE` mode with pin order `A+, A-, B+, B-`.

---

> Niche components (shift registers, RFID, matrix displays, joystick, RTC, NeoPixel, SH1107, HX711 load cell, ILI9341 TFT, IR receiver/remote, DPDT relay, KY-040 rotary encoder) → `/wokwi-diagram-extended`

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
| `esp:GPIO2` | `esp:D2` — ESP32 prefixes GPIO numbers with `D` |
| `esp:TX` in connections | `esp:TX0` — don't forget the number suffix for UART pins |
| `uno:D2` | `uno:2` — Arduino Uno/Mega/Nano use numeric pins, no `D` prefix |
