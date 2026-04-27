# wokwi-diagram-extended — Wokwi Component Reference (Extended)

Additional component pinouts and wiring snippets for Wokwi `diagram.json`.
Load alongside `/wokwi-diagram` for full coverage.

---

### wokwi-buzzer (extended — `mode` attr)

| Pin | Role |
|---|---|
| `1` | Negative / black (connect to GND) |
| `2` | Positive / red (connect to MCU GPIO) |

| Attr | Default | Description |
|---|---|---|
| `volume` | `"1.0"` | Loudness `"0.01"`–`"1.0"`. Use `"0.1"`–`"0.2"` for comfortable simulation. |
| `mode` | `"smooth"` | `"smooth"`: better audio, ideal for `tone()` and single-frequency melodies. `"accurate"`: precise waveform, needed for complex/polyphonic sounds but adds audible click noise. |

```json
{ "type": "wokwi-buzzer", "id": "bz1", "top": 100, "left": 200, "attrs": { "volume": "0.1", "mode": "smooth" } }
```

```json
["bz1:1", "uno:GND.1", "black",  []],
["bz1:2", "uno:8",     "purple", []]
```

Use Arduino `tone(pin, frequency, duration)` to drive the buzzer. Pin 2 connects to the tone pin.

---

### wokwi-clock-generator

Outputs a configurable clock signal. Single pin: `CLK` (output only).

| Attr | Default | Description |
|---|---|---|
| `frequency` | `"10k"` | Hz with `k`/`m` suffix: `"10k"` = 10 kHz, `"1.3m"` = 1.3 MHz, `"1"` = 1 Hz. Numeric strings also work: `"10000"`. |

> Frequencies above 100 kHz slow down the simulation.

```json
{ "type": "wokwi-clock-generator", "id": "clk1", "top": 0, "left": 0, "attrs": { "frequency": "10k" } }
```
```json
["clk1:CLK", "esp:D2", "blue", []]
```

---

### wokwi-vcc / wokwi-gnd (standalone power symbols)

Floating power/ground nodes — clean up power rail wiring without routing long wires.

| Type | Pin |
|---|---|
| `wokwi-vcc` | `VCC` |
| `wokwi-gnd` | `GND` |

```json
{ "type": "wokwi-vcc", "id": "pwr1", "top": -100, "left": 0, "attrs": {} },
{ "type": "wokwi-gnd", "id": "gnd1", "top":  100, "left": 0, "attrs": {} }
```

---

### wokwi-dip-switch-8 (8-position DIP switch)

8 independent SPST switches. Each switch `n`: pins `na` (side A) and `nb` (side B) connected when ON. Toggle with keyboard keys `1`–`8` while focused.

**Typical wiring — chain one side to GND, other side to MCU inputs:**
```json
["uno:GND.1", "sw1:1b", "black", []],
["sw1:2b",    "sw1:1b", "black", []],
["sw1:3b",    "sw1:2b", "black", []],
["sw1:8b",    "sw1:7b", "black", []],
["sw1:1a", "uno:7", "green", []],
["sw1:2a", "uno:6", "green", []],
["sw1:8a", "uno:0", "green", []]
```

Use `INPUT_PULLUP` on MCU pins when `nb` side is GND. Or chain `na` to VCC and use `INPUT` on `nb`.

```json
{ "type": "wokwi-dip-switch-8", "id": "sw1", "top": 0, "left": 0, "attrs": {} }
```

---

### wokwi-led-bar-graph (10-segment LED bar)

10 individual LEDs. Each LED `n` has anode `An` and cathode `Cn`.

| Pins | Role |
|---|---|
| `A1`–`A10` | Anodes — typically chained together to VCC |
| `C1`–`C10` | Cathodes — connect to MCU outputs or switch/driver |

Attr: `"color"` sets color pattern (e.g. `"BCYR"` = Blue/Cyan/Yellow/Red cycling across segments).

Chain all anodes to VCC, drive cathodes LOW to light each LED:
```json
{ "type": "wokwi-led-bar-graph", "id": "bar1", "top": 0, "left": 200, "rotate": 90, "attrs": { "color": "BCYR" } }
```
```json
["uno:5V",   "bar1:A10", "red",   []],
["bar1:A10", "bar1:A9",  "red",   []],
["bar1:C10", "uno:2",    "green", []],
["bar1:C9",  "uno:3",    "green", []]
```

---

### wokwi-ds1307 (RTC — Real Time Clock)

I2C address `0x68`. Auto-initializes to current system time on simulation start.

| Pin | Role |
|---|---|
| `GND` | Ground |
| `5V` | Power (5V only — not 3.3V) |
| `SDA` | I2C data |
| `SCL` | I2C clock |
| `SQW` | Square wave / interrupt output |

| Attr | Default | Description |
|---|---|---|
| `initTime` | `"now"` | `"now"` = system time, `"0"` = 2000-01-01T00:00:00Z, or ISO 8601: `"2024-06-15T08:30:00Z"` (append `Z` for UTC, omit for local time) |

**SQW pin modes** (via `RTClib` `rtc.writeSqwPinMode()`):

| Constant | Output |
|---|---|
| `DS1307_OFF` | LOW |
| `DS1307_ON` | HIGH |
| `DS1307_SquareWave1HZ` | 1 Hz |
| `DS1307_SquareWave4kHz` | 4.096 kHz |
| `DS1307_SquareWave8kHz` | 8.192 kHz |
| `DS1307_SquareWave32kHz` | 32.768 kHz |

```json
{ "type": "wokwi-ds1307", "id": "rtc1", "top": 100, "left": 200, "attrs": { "initTime": "now" } }
```
```json
["rtc1:GND", "uno:GND.2", "black",  []],
["rtc1:5V",  "uno:5V",    "red",    []],
["rtc1:SDA", "uno:A4",    "blue",   []],
["rtc1:SCL", "uno:A5",    "gold",   []]
```

---

### wokwi-gate-not / wokwi-gate-and / wokwi-gate-or (logic gates)

| Pin | Role |
|---|---|
| `IN` | Input (all gates) |
| `IN2` | Second input (AND, OR, XOR, NAND, NOR — not on NOT) |
| `OUT` | Output |

Available types: `wokwi-gate-not`, `wokwi-gate-and`, `wokwi-gate-or`, `wokwi-gate-xor`, `wokwi-gate-nand`, `wokwi-gate-nor`.

```json
{ "type": "wokwi-gate-not", "id": "not1", "top": 0, "left": 200, "attrs": {} }
```
```json
["not1:IN",  "esp:D2", "green", []],
["not1:OUT", "esp:D3", "blue",  []]
```

---

## Niche MCU Pin Reference

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

### wokwi-franzininho (ATtiny85-based board)

Brazilian open-source ATtiny85 board. Same chip as `wokwi-attiny85` — see that entry for library and limitation details. Type name is `wokwi-franzininho`.

Pin naming in diagram.json: **`PB0`–`PB5`** (not board pin numbers 0–5).
Power: `VCC.1`/`VCC.2` and `GND.1`/`GND.2` — **always use the numbered suffixes**.

| Board pin | Pin name | ATtiny85 | Functions | PWM |
|---|---|---|---|---|
| 0 | `PB0` | PB0 | SPI MOSI, I2C SDA | Yes |
| 1 | `PB1` | PB1 | SPI MISO, **LED1 (yellow onboard)** | Yes |
| 2 | `PB2` | PB2 | SPI SCK, I2C SCL | - |
| 3 | `PB3` | PB3 | | - |
| 4 | `PB5` | PB5 | Reset / ADC0 | - |
| 5 | `PB4` | PB4 | ADC2 | Yes |

Onboard LEDs (no wiring needed):
- **ON** (green) — power LED, always lit
- **LED1** (yellow) — connected to `PB1`

```json
{ "type": "wokwi-franzininho", "id": "franzininho", "top": 0, "left": 0, "attrs": {} }
```

I2C (SDA=PB0, SCL=PB2):
```json
["franzininho:PB0", "dev1:SDA", "orange", []],
["franzininho:PB2", "dev1:SCL", "purple", []],
["franzininho:VCC.2","dev1:VCC", "red",   []],
["franzininho:GND.2","dev1:GND", "black", []]
```

74HC595 shift register (DS=PB5, STCP=PB3, SHCP=PB4):
```json
["franzininho:PB5", "sr1:DS",   "yellow", []],
["franzininho:PB3", "sr1:STCP", "orange", []],
["franzininho:PB4", "sr1:SHCP", "purple", []],
["franzininho:VCC.2","sr1:VCC", "red",    []],
["franzininho:VCC.2","sr1:MR",  "red",    []],
["franzininho:GND.2","sr1:GND", "black",  []],
["franzininho:GND.2","sr1:OE",  "black",  []]
```

HC-SR04 ultrasonic (TRIG=PB5, ECHO=PB3):
```json
["franzininho:PB5",  "ultrasonic1:TRIG", "orange", []],
["franzininho:PB3",  "ultrasonic1:ECHO", "yellow", []],
["franzininho:VCC.2","ultrasonic1:VCC",  "red",    []],
["franzininho:GND.2","ultrasonic1:GND",  "black",  []]
```

---

### wokwi-attiny85

8-bit AVR, 8 KB Flash, 512 B SRAM, 512 B EEPROM. Default clock: 8 MHz.
Attr: `"frequency"`: `"1m"`, `"8m"` (default), `"16m"`, `"20m"`.

| Pin | Name | Functions |
|---|---|---|
| `PB0` | Digital/PWM | SPI MOSI, I2C SDA |
| `PB1` | Digital/PWM | SPI MISO |
| `PB2` | Digital/ADC1 | SPI SCK, I2C SCL |
| `PB3` | Digital/ADC3 | |
| `PB4` | Digital/ADC2 | |
| `PB5` | RESET/ADC0 | |
| `VCC` | Power | |
| `GND` | Ground | |

PWM: `PB0` and `PB1` only (Timer0). Timer1 not simulated.
I2C library: `TinyWireM`. No UART — use `TinyDebug` for serial output (no pins needed, uses internal simulator interface).

```json
{ "type": "wokwi-attiny85", "id": "tiny", "top": 0, "left": 0, "attrs": {} }
```

I2C wiring (SDA=PB0, SCL=PB2):
```json
["tiny:PB0", "dev1:SDA", "orange", []],
["tiny:PB2", "dev1:SCL", "purple", []],
["tiny:VCC", "dev1:VCC", "red",    []],
["tiny:GND", "dev1:GND", "black",  []]
```

---

### wokwi-pi-pico (Raspberry Pi Pico)

| Pin group | Names |
|---|---|
| GPIO | `GP0`–`GP28` |
| UART default | `GP0` (TX → `$serialMonitor:RX`), `GP1` (RX ← `$serialMonitor:TX`) |
| Power | `3V3`, `VSYS`, `VBUS`, `GND.1`–`GND.8` |

Attrs: `"env": "arduino-community"` to use Arduino framework instead of MicroPython.

Serial monitor:
```json
["pico:GP0", "$serialMonitor:RX", "", []],
["pico:GP1", "$serialMonitor:TX", "", []]
```

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
["dev1:SDA", "nucleo:D0",   "green", []],
["dev1:SCL", "nucleo:D1",   "gold",  []],
["dev1:VCC", "nucleo:VIN",  "red",   []],
["dev1:GND", "nucleo:GND.2","black", []]
```

Simulated peripherals: GPIO, USART, I2C (master only), SPI (master only), ADC, EEPROM, TIM2/21/22 (analogWrite), CRC, EXTI, RCC, GDB debugging.
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
["led1:A", "nucleo:D13",   "green", []],
["led1:C", "nucleo:GND.1", "black", []]
```

Simulated peripherals: GPIO, USART, I2C (master only), SPI (master only), ADC, TIM1/3/14/16/17 (analogWrite), CRC, EXTI, GDB debugging.
Not simulated: DMA, IWDG, RTC, PWR, SYSCFG.

---

## Niche Components

### wokwi-biaxial-stepper (concentric dual stepper)

Two stepper motors in one enclosure sharing the same axis — outer shaft and inner shaft. Drive with two separate `wokwi-a4988` drivers.

| Pins | Motor |
|---|---|
| `A1-` `A1+` `B1+` `B1-` | Outer shaft (coils A and B) |
| `A2-` `A2+` `B2+` `B2-` | Inner shaft (coils A and B) |

| Attr | Default | Options |
|---|---|---|
| `outerHandLength` | `"30"` | `"20"`–`"70"` |
| `outerHandColor` | `"gold"` | any CSS color |
| `outerHandShape` | `"plain"` | `"plain"`, `"arrow"`, `"ornate"` |
| `innerHandLength` | `"30"` | `"20"`–`"70"` |
| `innerHandColor` | `"silver"` | any CSS color |
| `innerHandShape` | `"plain"` | `"plain"`, `"arrow"`, `"ornate"` |

**In simulation, coils can be wired directly to MCU GPIO pins — no A4988 needed.**
For real hardware, use two A4988 drivers (one per motor).

Direct wiring to Arduino Uno (outer = pins 8–11, inner = pins 2–5):
```json
["stepper1:B1-", "uno:8",  "black", []],
["stepper1:B1+", "uno:9",  "green", []],
["stepper1:A1+", "uno:10", "red",   []],
["stepper1:A1-", "uno:11", "blue",  []],
["stepper1:B2-", "uno:2",  "black", []],
["stepper1:B2+", "uno:3",  "green", []],
["stepper1:A2+", "uno:4",  "red",   []],
["stepper1:A2-", "uno:5",  "blue",  []]
```

```json
{ "type": "wokwi-biaxial-stepper", "id": "stepper1", "top": 0, "left": 200,
  "attrs": { "outerHandShape": "arrow", "innerHandShape": "arrow", "outerHandColor": "gold", "innerHandColor": "silver" } }
```

---

### wokwi-a4988 + wokwi-stepper-motor

Always used together. The A4988 drives the stepper motor.

**wokwi-a4988 pins:**

| Pin | Role | Default |
|---|---|---|
| `ENABLE` | Enable, active low | LOW (enabled) |
| `SLEEP` | Sleep, active low | HIGH (awake) |
| `RESET` | Reset, active low | floating — **must connect to SLEEP** |
| `MS1`/`MS2`/`MS3` | Microstepping select | all LOW = full step |
| `STEP` | Step pulse input (MCU output) | — |
| `DIR` | Direction: HIGH = CW, LOW = CCW | — |
| `VDD` | Logic power (3.3V or 5V) | — |
| `GND` | Ground | — |
| `1A` | Motor coil B+ | — |
| `1B` | Motor coil B- | — |
| `2A` | Motor coil A+ | — |
| `2B` | Motor coil A- | — |
| `VMOT` | Motor power (not simulated) | — |

Microstepping: MS1=0,MS2=0,MS3=0 → full (200 steps/rev) · MS1=1 → half · MS2=1 → 1/4 · MS1+MS2=1 → 1/8 · all=1 → 1/16.

> Modes 1/4, 1/8, 1/16 are partially supported: step count is correct but angle updates every half step only.

**wokwi-stepper-motor attrs:** `"display": "angle"` shows current angle; `"arrow": "green"` shows a colored direction arrow.

```json
{ "type": "wokwi-a4988",       "id": "drv1",     "top": 0,    "left": 200, "attrs": {} },
{ "type": "wokwi-stepper-motor","id": "stepper1", "top": -150, "left": 150, "attrs": { "display": "angle" } }
```

**Wiring (RESET → SLEEP shortcut, STEP/DIR to MCU):**
```json
["drv1:SLEEP",  "drv1:RESET",  "green",  []],
["drv1:STEP",   "uno:2",       "purple", []],
["drv1:DIR",    "uno:3",       "orange", []],
["drv1:VDD",    "uno:5V",      "red",    []],
["drv1:GND",    "uno:GND.1",   "black",  []],
["drv1:1B",     "stepper1:B-", "black",  []],
["drv1:1A",     "stepper1:B+", "green",  []],
["drv1:2A",     "stepper1:A+", "blue",   []],
["drv1:2B",     "stepper1:A-", "red",    []]
```

**Multi-driver chains:** SLEEP→RESET per driver; share ENABLE across drivers; each driver needs its own STEP/DIR pins.

---

### wokwi-neopixel-canvas (NeoPixel LED matrix)

Configurable WS2812B NeoPixel grid. Single data wire, no per-LED resistors needed.

| Pin | Role |
|---|---|
| `DIN` | Data in (connect to MCU GPIO) |
| `VDD` | Power (5V) |
| `VSS` | Ground |

| Attr | Description |
|---|---|
| `rows` | Number of rows |
| `cols` | Number of columns |
| `matrixBrightness` | Initial brightness 0–255 (e.g. `"10"` for dim) |

```json
{ "type": "wokwi-neopixel-canvas", "id": "leds1", "top": 0, "left": 200, "attrs": { "rows": "8", "cols": "8", "matrixBrightness": "10" } }
```
```json
["leds1:DIN", "esp:D2",    "green", []],
["leds1:VDD", "esp:VIN",   "red",   []],
["leds1:VSS", "esp:GND.1", "black", []]
```

---

### board-mfrc522 (RFID/NFC reader)

SPI (Mode 0) RFID reader for 13.56 MHz MIFARE cards. Libraries: `MFRC522` (Miguel Balboa) or `Arduino_MFRC522v2`.

| Pin | Role |
|---|---|
| `3.3V` | Power |
| `GND` | Ground |
| `RST` | Reset (active low) |
| `SDA` | SPI chip select (active low) — **not I2C** |
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

Arduino Uno wiring: CS = `10`, RST = `9`, MISO = `12`, MOSI = `11`, SCK = `13`.

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

### wokwi-74hc595 (8-bit SIPO shift register — output expander)

Drives 8 parallel outputs from 3 MCU pins. Use for LEDs, 7-segment displays. For input expansion see `wokwi-74hc165`.

| Pin | Role |
|---|---|
| `DS` | Serial data input |
| `SHCP` | Serial clock |
| `STCP` | Storage/latch clock — pulse HIGH to push shift register to outputs |
| `OE` | Output enable, active low — **connect to GND** to permanently enable |
| `MR` | Master reset, active low — **connect to VCC** to disable reset |
| `Q0`–`Q7` | Parallel outputs (Q0 = LSB first with `LSBFIRST`) |
| `Q7S` | Serial output for daisy-chaining → connect to next chip's `DS` |
| `VCC` | Power |
| `GND` | Ground |

**Single chip wiring (Arduino Uno, DS=8, STCP=9, SHCP=10):**
```json
["uno:8",     "sr1:DS",   "orange", []],
["uno:9",     "sr1:STCP", "purple", []],
["uno:10",    "sr1:SHCP", "brown",  []],
["uno:GND.2", "sr1:OE",   "black",  []],
["uno:5V",    "sr1:MR",   "red",    []],
["uno:5V",    "sr1:VCC",  "red",    []],
["uno:GND.2", "sr1:GND",  "black",  []]
```

**Daisy-chain (shared STCP/SHCP, n chips → 8×n outputs):**
```json
["sr1:Q7S", "sr2:DS", "orange", []]
```

**Q0–Q7 → LED via resistor pattern:**
```json
["sr1:Q0", "r1:1",   "green", []],
["r1:2",   "led1:A", "green", []],
["led1:C", "uno:GND.2", "black", []]
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
["sr1:Q7", "uno:2",    "limegreen", []],
["sr1:CP", "uno:3",    "gold",      []],
["sr1:PL", "uno:4",    "purple",    []],
["sr1:CE", "uno:GND.1","black",     []],
["sr1:VCC","uno:5V",   "red",       []],
["sr1:GND","uno:GND.1","black",     []]
```

**Daisy-chain (n chips → read 8×n bits, shared PL/CP/CE):**
```json
["in1:Q7", "in2:DS", "limegreen", []],
["in2:Q7", "in3:DS", "limegreen", []],
["in3:Q7", "uno:2",  "limegreen", []]
```

---

### wokwi-analog-joystick

| Pin | Role |
|---|---|
| `VCC` | Power (5V) |
| `VERT` | Vertical axis — analog 0 (bottom) to VCC (top) |
| `HORZ` | Horizontal axis — analog 0 (**right**) to VCC (**left**) — **axis is inverted** |
| `SEL` | Push button — shorts to GND when pressed; use `INPUT_PULLUP` |
| `GND` | Ground |

Attr: `"bounce": "0"` disables button bounce on SEL.
Automation controls: `x` / `y` (float -1 to 1, 0 = center), `pressed` (int 0/1).

```json
{ "type": "wokwi-analog-joystick", "id": "joy1", "top": 0, "left": 200, "attrs": {} }
```
```json
["joy1:VCC",  "uno:5V",    "red",    []],
["joy1:GND",  "uno:GND.1", "black",  []],
["joy1:VERT", "uno:A0",    "purple", []],
["joy1:HORZ", "uno:A1",    "green",  []],
["joy1:SEL",  "uno:2",     "blue",   []]
```

> `analogRead(HORZ)` returns 0 when pushed right, 1023 when pushed left. Use `map(val, 0, 1023, -100, 100)` to get a centered range.

---

### wokwi-max7219-matrix (LED dot matrix)

8×8 LED matrix driven by MAX7219 over SPI. Supports chaining.

| Pin | Role |
|---|---|
| `DIN` | SPI data in |
| `CS` | Chip select |
| `CLK` | SPI clock |
| `V+` | Power (5V) |
| `GND` | Ground |

Attr: `"chain": "2"` chains N matrices side-by-side (e.g. `"2"` = 16×8).

```json
{ "type": "wokwi-max7219-matrix", "id": "mat1", "top": 0, "left": 200, "attrs": { "chain": "1" } }
```
```json
["mat1:DIN", "uno:11",   "green",  []],
["mat1:CS",  "uno:10",   "blue",   []],
["mat1:CLK", "uno:13",   "orange", []],
["mat1:V+",  "uno:5V",   "red",    []],
["mat1:GND", "uno:GND.1","black",  []]
```

---

### wokwi-ds18b20 (1-Wire temperature sensor)

Digital temperature sensor, -55°C to 125°C. Uses 1-Wire protocol — multiple sensors can share the same data pin, each addressed by unique `deviceID`.

| Pin | Role |
|---|---|
| `VCC` | Power (3.3V or 5V) |
| `DQ` | 1-Wire data line — **requires 4.7 kΩ pull-up to VCC** |
| `GND` | Ground |

| Attr | Default | Description |
|---|---|---|
| `temperature` | `"22"` | Initial temperature in °C (-55 to 125) |
| `deviceID` | `"010203040506"` | 12-char hex 1-Wire address — must be unique per bus |
| `familyCode` | `"28"` | 1-Wire family code |

Library: `OneWire` + `DallasTemperature`. Call `sensors.requestTemperatures()` then `sensors.getTempCByIndex(0)`.

> `DallasTemperature` cannot read exactly -55°C (reserved sentinel for disconnected sensor). Use `OneWire` directly if you need that exact value.

**Single sensor (Arduino Uno, DQ on pin 12, 4.7 kΩ pull-up):**
```json
{ "type": "wokwi-ds18b20", "id": "temp1", "top": 0, "left": 200, "attrs": { "temperature": "23.5" } },
{ "type": "wokwi-resistor", "id": "r1", "top": -50, "left": 150, "attrs": { "value": "4700" } }
```
```json
["temp1:VCC", "uno:5V",    "red",   []],
["temp1:GND", "uno:GND.1", "black", []],
["temp1:DQ",  "uno:12",    "green", []],
["r1:1",      "uno:5V",    "red",   []],
["r1:2",      "temp1:DQ",  "green", []]
```

**Multiple sensors (same bus — chain VCC/GND, share DQ and pull-up):**
```json
{ "type": "wokwi-ds18b20", "id": "temp1", "top": 0, "left": 100, "attrs": { "deviceID": "111111111111" } },
{ "type": "wokwi-ds18b20", "id": "temp2", "top": 0, "left": 150, "attrs": { "deviceID": "222222222222" } },
{ "type": "wokwi-ds18b20", "id": "temp3", "top": 0, "left": 200, "attrs": { "deviceID": "333333333333" } }
```
```json
["temp1:VCC", "temp2:VCC", "red",   []],
["temp2:VCC", "temp3:VCC", "red",   []],
["temp1:GND", "temp2:GND", "black", []],
["temp2:GND", "temp3:GND", "black", []],
["temp1:DQ",  "temp2:DQ",  "green", []],
["temp2:DQ",  "temp3:DQ",  "green", []]
```

---
