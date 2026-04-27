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

---

## Serial Monitor (always wire this for ESP32/Arduino)

```json
["esp:TX0", "$serialMonitor:RX", "", []],
["esp:RX0", "$serialMonitor:TX", "", []]
```

---

## MCU Pin Reference

### board-franzininho-wifi (ESP32-S2)

Open-source Brazilian ESP32-S2 board. Pin names are **numeric without `D` prefix** (e.g. `esp:1`, `esp:8`).

| Pin group | Names |
|---|---|
| GPIO | `1`–`21`, `33`–`40` (numeric, no `D` prefix) |
| UART | `TX`, `RX` |
| I2C default | `SDA = 8`, `SCL = 9` |
| Power | `3V3`, `5V.1`, `5V.2`, `GND.1`, `GND.2` |

Built-in LEDs (no wiring needed):
- Pin `33` → orange LED
- Pin `21` → blue LED

CircuitPython: set `attrs: { "env": "circuitpython-7.2.0" }`.

```json
{ "type": "board-franzininho-wifi", "id": "esp", "top": 0, "left": 0, "attrs": {} }
```

Serial monitor:
```json
["esp:TX", "$serialMonitor:RX", "", []],
["esp:RX", "$serialMonitor:TX", "", []]
```

I2C (e.g. LCD, BMP180):
```json
["dev1:SDA", "esp:8", "goldenrod", []],
["dev1:SCL", "esp:9", "purple",    []]
```

---

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

### board-st-nucleo-l031k6 (STM32 Nucleo-32)

ARM Cortex-M0+, 32 MHz, 32 KB Flash, 8 KB RAM, 1 KB EEPROM.

Onboard LED: `PB3` = `D13` = `LED_BUILTIN` — lit when driven HIGH.

Pin naming: STM32-style (`PA2`, `PB3`…) and Arduino-style (`D0`, `D1`, `D13`, `A0`…) both work.
Power: `VIN`, `5V.1`, `GND.1`–`GND.9`.

Serial monitor uses **VCP pin names** (different from C031C6 which uses `PA2`/`PA3`):
```json
["$serialMonitor:TX", "nucleo:VCP_RX", "", []],
["$serialMonitor:RX", "nucleo:VCP_TX", "", []]
```

Default I2C: `SDA = D0`, `SCL = D1`.
```json
["dev1:SDA", "nucleo:D0", "green", []],
["dev1:SCL", "nucleo:D1", "gold",  []],
["dev1:VCC", "nucleo:VIN","red",   []],
["dev1:GND", "nucleo:GND.2","black",[]]
```

Simulated peripherals: GPIO, USART, I2C (master only), SPI (master only), ADC, EEPROM, TIM2/21/22 (analogWrite), CRC, EXTI, RCC, GDB debugging.
Partial: SYSCFG (EXTICRn only), WWDG (untested).
Not simulated: DMA, IWDG, RTC, PWR, Comparator, LPTIM, LPUART.

---

### board-stm32-bluepill (STM32 Blue Pill)

ARM Cortex-M3, 72 MHz, 64 KB Flash, 20 KB RAM.

Onboard LED: `PC13` — lit when driven HIGH.

Pin naming: short-form without port letter — `A0` (not `PA0`), `B6` (not `PB6`), `C13` (not `PC13`).
Power: `3V3.1`, `3V3.2`, `GND.1`, `GND.2` (numbered suffixes).

Serial monitor (USART1 = PA9 TX, PA10 RX):
```json
["stm32:A9",  "$serialMonitor:RX", "", []],
["stm32:A10", "$serialMonitor:TX", "", []]
```

Example — potentiometer on A0:
```json
["pot1:SIG", "stm32:A0",    "green", []],
["pot1:VCC", "stm32:3V3.2", "red",   []],
["pot1:GND", "stm32:GND.2", "black", []]
```

Simulated peripherals: GPIO, USART, I2C, SPI, TIM1/2/3/4 (analogWrite), CRC, EXTI, RCC, AFIO, WWDG, GDB debugging.
Partial: ADC1 (basic conversion only — ADC2 not implemented), DBG (DWT only).
Not simulated: DMA, IWDG, RTC, PWR.

---

### board-st-nucleo-c031c6 (STM32 Nucleo-64)

ARM Cortex-M0+, 48 MHz, 32 KB Flash, 12 KB RAM.

Onboard LED: `PA5` = `D13` = `LED_BUILTIN` — lit when driven HIGH.

Pin naming: STM32-style (`PA2`, `PB6`…) **and** Arduino-style (`D13`, `A0`…) both work.
GND: numbered suffix up to at least `GND.9` — use `GND.1` as default.

Serial monitor (USART2 = PA2/PA3):
```json
["$serialMonitor:TX", "nucleo:PA3", "", []],
["$serialMonitor:RX", "nucleo:PA2", "", []]
```

Example — LED on D13:
```json
["led1:A", "nucleo:D13",  "green", []],
["led1:C", "nucleo:GND.1","black", []]
```

Simulated peripherals: GPIO, USART, I2C (master only), SPI (master only), ADC, TIM1/3/14/16/17 (analogWrite), CRC, EXTI, GDB debugging.
Not simulated: DMA, IWDG, RTC, PWR, SYSCFG.

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

Colors: `"red"`, `"green"`, `"blue"`, `"yellow"`, `"white"`, `"orange"`, `"limegreen"`

Attrs: `"flip": "1"` mirrors the LED horizontally (useful when placing left of MCU).

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

### wokwi-potentiometer

| Pin | Role |
|---|---|
| `VCC` | Power |
| `GND` | Ground |
| `SIG` | Wiper output (analog voltage) |

```json
{ "type": "wokwi-potentiometer", "id": "pot1", "top": 100, "left": 200, "attrs": {} }
```

```json
["pot1:SIG", "esp:D34",   "green", []],
["pot1:VCC", "esp:3V3",   "red",   []],
["pot1:GND", "esp:GND.1", "black", []]
```

Add `"rotate": 270` for vertical orientation. Use an ADC-capable pin for `SIG`.

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

### wokwi-lcd1602 / wokwi-lcd2004 (I2C LCD)

Character LCD: 16×2 (`wokwi-lcd1602`) or 20×4 (`wokwi-lcd2004`). Set `attrs: { "pins": "i2c" }` to use I2C mode (default is parallel — always use I2C in Wokwi).

| Pin | Role |
|---|---|
| `VCC` | Power (5V) |
| `GND` | Ground |
| `SDA` | I2C data |
| `SCL` | I2C clock |

```json
{ "type": "wokwi-lcd2004", "id": "lcd1", "top": 100, "left": 200, "attrs": { "pins": "i2c" } }
```

ESP32 wiring (I2C default D21/D22):
```json
["lcd1:SDA", "esp:D21",   "green", []],
["lcd1:SCL", "esp:D22",   "gold",  []],
["lcd1:VCC", "esp:VIN",   "red",   []],
["lcd1:GND", "esp:GND.1", "black", []]
```

---

### wokwi-dht22

| Pin | Role |
|---|---|
| `VCC` | Power |
| `GND` | Ground |
| `SDA` | Data (connect to GPIO, no extra resistor needed in Wokwi) |

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

### board-mfrc522 (RFID/NFC reader)

SPI (Mode 0) RFID reader for 13.56 MHz MIFARE cards. Libraries: `MFRC522` (Miguel Balboa) or `Arduino_MFRC522v2`.

| Pin | Role |
|---|---|
| `3.3V` | Power |
| `GND` | Ground |
| `RST` | Reset (active low) |
| `SDA` | SPI chip select (active low) |
| `SCK` | SPI clock |
| `MOSI` | SPI data in |
| `MISO` | SPI data out |
| `IRQ` | Interrupt (active low, optional) |

| Attr | Default | Description |
|---|---|---|
| `uid` | `""` | Custom UID for Blue Card only — format `"01:02:03:04"` (4-byte) or `"04:11:22:33:44:55:66"` (7-byte) |

Built-in card presets (selectable in simulator control panel):

| Index | Card | UID | Type |
|---|---|---|---|
| `0` | Blue (customizable) | `01:02:03:04` | MIFARE Classic 1K |
| `1` | Green | `11:22:33:44` | MIFARE Classic 1K |
| `2` | Yellow | `55:66:77:88` | MIFARE Classic 1K |
| `3` | Red | `AA:BB:CC:DD` | MIFARE Classic 1K |
| `4` | NFC Tag | `04:11:22:33:44:55:66` | MIFARE Ultralight |
| `5` | Key Fob | `C0:FF:EE:99` | MIFARE Mini |

Automation controls: `card` (int 0–5), `tagPresent` (0 = remove, 1 = present).

ESP32 default SPI wiring (GPIO 5 = CS, GPIO 21 = RST):

```json
{ "type": "board-mfrc522", "id": "rfid1", "top": 100, "left": 200, "attrs": { "uid": "DE:AD:BE:EF" } }
```

```json
["rfid1:SDA",  "esp:5",     "green",  []],
["rfid1:SCK",  "esp:18",    "orange", []],
["rfid1:MISO", "esp:19",    "blue",   []],
["rfid1:MOSI", "esp:23",    "yellow", []],
["rfid1:RST",  "esp:21",    "purple", []],
["rfid1:3.3V", "esp:3V3",   "red",    []],
["rfid1:GND",  "esp:GND.2", "black",  []]
```

Arduino Uno wiring: CS = D10, RST = D9, MISO = D12, MOSI = D11, SCK = D13.

---

### board-grove-oled-sh1107 (128×128 OLED)

Monochrome 128×128 I2C OLED. **SPI not supported.** Note the `.1` suffixes on `SCL` and `GND`.

| Pin | Role |
|---|---|
| `SCL.1` | I2C clock — **NOT `SCL`** |
| `SDA` | I2C data |
| `VCC` | Power (3.3V) |
| `GND.1` | Ground — **NOT `GND`** |

Default I2C on ESP32 (`board-esp32-devkit-c-v4`): SCL = `22`, SDA = `21`.

```json
{ "type": "board-grove-oled-sh1107", "id": "oled1", "top": 100, "left": 200, "attrs": {} }
```

```json
["oled1:SCL.1", "esp:22",    "green", []],
["oled1:SDA",   "esp:21",    "blue",  []],
["oled1:VCC",   "esp:3V3",   "red",   []],
["oled1:GND.1", "esp:GND.1", "black", []]
```

---

### wokwi-74hc165 (8-bit PISO shift register — input expander)

Reads 8 parallel inputs serially. Use to expand input pins. For output expansion see `wokwi-74hc595`.

| Pin | Role |
|---|---|
| `D0`–`D7` | Parallel inputs (D7 = MSB, first bit out) |
| `PL` | Parallel load, active low — pulse LOW to sample inputs, then HIGH to shift |
| `CP` | Serial clock — pulse HIGH to advance to next bit |
| `CE` | Clock enable, active low — **connect to GND**, never leave floating |
| `Q7` | Serial output → MCU input (or next chip's `DS` in chain) |
| `Q7_N` | Inverted serial output (usually unused) |
| `DS` | Serial input for daisy-chaining — connect previous chip's `Q7` here; leave open for first/only chip |
| `VCC` | Power |
| `GND` | Ground |

**Single chip wiring (Arduino Uno):**
```json
["sr1:Q7", "uno:D2",   "limegreen", []],
["sr1:CP", "uno:D3",   "gold",      []],
["sr1:PL", "uno:D4",   "purple",    []],
["sr1:CE", "uno:GND.1","black",     []],
["sr1:VCC","uno:5V",   "red",       []],
["sr1:GND","uno:GND.1","black",     []]
```

**Daisy-chain (n chips → read 8×n bits, shared PL/CP/CE):**
```json
["in1:Q7", "in2:DS",  "limegreen", []],
["in2:Q7", "in3:DS",  "limegreen", []],
["in3:Q7", "uno:D2",  "limegreen", []]
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
{ "type": "wokwi-text", "id": "lbl1", "top": 0, "left": 200, "attrs": { "text": "Channel 0" } }
```

---

### wokwi-hc-sr04 (ultrasonic)

| Pin | Role |
|---|---|
| `VCC` | 5V |
| `GND` | Ground |
| `TRIG` | Trigger pulse (GPIO output) |
| `ECHO` | Echo return (GPIO input) |

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
