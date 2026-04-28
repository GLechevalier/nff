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

### wokwi-slide-switch (SPDT slide switch — extended)

Pin `2` is the common. The handle position determines which terminal is connected to `2`:

| Handle | Connection |
|---|---|
| Left | `1`–`2` shorted |
| Right | `3`–`2` shorted |

| Attr | Default | Description |
|---|---|---|
| `value` | `""` | Initial position: `""` = left (pin 1–2), `"1"` = right (pin 3–2) |
| `bounce` | `""` | Default: simulates contact bounce. Set `"0"` to disable. |

```json
{ "type": "wokwi-slide-switch", "id": "sw1", "top": 10, "left": 180, "attrs": { "bounce": "0" } }
```

**Toggle LED (switch between GND and signal on pin 5):**
```json
["sw1:2", "uno:GND.1", "black", []],
["sw1:3", "uno:5",     "green", []]
```

**Route signal to one of two LEDs (pin 5 → red LED in left, green LED in right):**
```json
["sw1:1", "led1:A",    "blue",  []],
["sw1:2", "r1:1",      "blue",  []],
["sw1:3", "led2:A",    "blue",  []],
["r1:2",  "uno:13",    "red",   []],
["uno:GND.1", "led1:C","black", []],
["uno:GND.1", "led2:C","black", []]
```
> `r1` is a 220 Ω current-limiting resistor in series with the common pin.

**Read switch state with MCU (pin 1 → VCC, pin 3 → GND, pin 2 → digital input):**
```json
["sw1:1", "esp:3V3",   "red",   []],
["sw1:3", "esp:GND.1", "black", []],
["sw1:2", "esp:D4",    "green", []]
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

10 individual LEDs in one package. Each LED `n` has anode `An` and cathode `Cn` (n = 1–10, top to bottom).

| Pin | Role |
|---|---|
| `A1`–`A10` | Anodes (positive pins) |
| `C1`–`C10` | Cathodes (negative pins) |

| Attr | Default | Description |
|---|---|---|
| `color` | `"red"` | Color of all segments — named (`"red"`, `"yellow"`, `"green"`, `"lime"`, …), hex (`"#9EFF3C"`), or pattern: `"GYR"` (Green→Yellow→Red top to bottom) or `"BCYR"` (Blue→Cyan→Yellow→Red top to bottom) |

---

**Pattern A — anode control (each anode to MCU pin, cathodes via resistors to GND):**
Drive anode HIGH to light the LED. Use one 220 Ω resistor per cathode.

```json
{ "type": "wokwi-led-bar-graph", "id": "bar1", "top": 0, "left": 200, "attrs": { "color": "GYR" } }
```
```json
["bar1:A1",  "uno:11", "green", []],
["bar1:A2",  "uno:10", "green", []],
["bar1:A3",  "uno:9",  "green", []],
["bar1:A4",  "uno:8",  "green", []],
["bar1:A5",  "uno:7",  "green", []],
["bar1:A6",  "uno:6",  "green", []],
["bar1:A7",  "uno:5",  "green", []],
["bar1:A8",  "uno:4",  "green", []],
["bar1:A9",  "uno:3",  "green", []],
["bar1:A10", "uno:2",  "green", []],
["bar1:C1",  "r1:1",   "black", []],
["bar1:C2",  "r2:1",   "black", []],
["bar1:C3",  "r3:1",   "black", []],
["bar1:C4",  "r4:1",   "black", []],
["bar1:C5",  "r5:1",   "black", []],
["bar1:C6",  "r6:1",   "black", []],
["bar1:C7",  "r7:1",   "black", []],
["bar1:C8",  "r8:1",   "black", []],
["bar1:C9",  "r9:1",   "black", []],
["bar1:C10", "r10:1",  "black", []],
["r1:2",  "r2:2",      "black", []],
["r2:2",  "r3:2",      "black", []],
["r3:2",  "r4:2",      "black", []],
["r4:2",  "r5:2",      "black", []],
["r5:2",  "r6:2",      "black", []],
["r6:2",  "r7:2",      "black", []],
["r7:2",  "r8:2",      "black", []],
["r8:2",  "r9:2",      "black", []],
["r9:2",  "r10:2",     "black", []],
["uno:GND.1", "r1:2",  "black", []]
```

> `r1`–`r10` are `wokwi-resistor` parts with `"value": "220"`. Chaining all `r*:2` pins together saves wires — one GND connection for all 10 resistors.

---

**Pattern B — cathode control (all anodes chained to VCC, cathodes driven LOW from MCU):**
Drive cathode LOW to light the LED. Saves MCU pins if the bar never needs individual control.

```json
{ "type": "wokwi-led-bar-graph", "id": "bar1", "top": 0, "left": 200, "rotate": 90, "attrs": { "color": "BCYR" } }
```
```json
["uno:5V",   "bar1:A1",  "red",   []],
["bar1:A1",  "bar1:A2",  "red",   []],
["bar1:A2",  "bar1:A3",  "red",   []],
["bar1:C1",  "uno:2",    "green", []],
["bar1:C2",  "uno:3",    "green", []]
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

### wokwi-pi-pico (Raspberry Pi Pico — RP2040)

Dual-core ARM Cortex-M0+ at 133 MHz, 264 KB RAM, flexible PIO. Only a **single core** is simulated.

| Pin group | Names | Notes |
|---|---|---|
| Digital GPIO | `GP0`–`GP22` | |
| Analog+digital | `GP26` (ADC ch 0), `GP27` (ADC ch 1), `GP28` (ADC ch 2) | |
| Power | `3V3`, `VSYS`, `VBUS` | |
| Ground | `GND.1`–`GND.8` | physical pins 3, 8, 13, 18, 23, 28, 33, 38 |
| Hidden (diagram.json only) | `TP4` = GPIO23, `TP5` = GPIO25 + onboard LED | |

**Onboard LED:** GPIO 25 / `LED_BUILTIN` — HIGH = lit.

**`env` attr:**

| Value | Framework |
|---|---|
| *(omit)* | MicroPython (default) |
| `"arduino-community"` | Arduino-Pico core |

**Simulated peripherals:** GPIO, PIO (+ PIO Debugger), USB CDC Serial, UART, I2C (master), SPI (master), PWM, DMA (PIO only), Timer, RTC, ADC, GDB debugging.
Not simulated: ADC temperature sensor (always 0), multi-core, SSI (partial).

**Serial Monitor — USB (default):** USB setup takes time; wait for connection before printing:
```cpp
Serial.begin(115200);
while (!Serial) delay(10);
Serial.println("Ready");
```

**Serial Monitor — UART (Serial1 on GP0/GP1):**
```json
["$serialMonitor:RX", "pico:GP0", "", []],
["$serialMonitor:TX", "pico:GP1", "", []]
```
```cpp
Serial1.begin(115200);
Serial1.println("Hello");
```

```json
{ "type": "wokwi-pi-pico", "id": "pico", "top": 0, "left": 0, "attrs": { "env": "arduino-community" } }
```

**Traffic-light wiring (GP1=red, GP5=yellow, GP9=green, direct to LED anodes):**
```json
["pico:GND.1", "led1:C", "black", []],
["pico:GP1",   "led1:A", "red",   []],
["pico:GND.2", "led2:C", "black", []],
["pico:GP5",   "led2:A", "gold",  []],
["pico:GND.3", "led3:C", "black", []],
["pico:GP9",   "led3:A", "green", []]
```

**LCD1602 parallel wiring (RS=GP12, E=GP11, D4–D7=GP10–GP7, backlight via 220Ω):**
```json
["pico:GND.1", "lcd:VSS", "black",  []],
["pico:GND.1", "lcd:RW",  "black",  []],
["pico:GND.1", "lcd:K",   "black",  []],
["pico:VSYS",  "lcd:VDD", "red",    []],
["pico:VSYS",  "r1:2",    "red",    []],
["r1:1",       "lcd:A",   "pink",   []],
["pico:GP12",  "lcd:RS",  "blue",   []],
["pico:GP11",  "lcd:E",   "purple", []],
["pico:GP10",  "lcd:D4",  "green",  []],
["pico:GP9",   "lcd:D5",  "brown",  []],
["pico:GP8",   "lcd:D6",  "gold",   []],
["pico:GP7",   "lcd:D7",  "gray",   []]
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

### wokwi-neopixel (single WS2812 addressable LED)

Single WS2812B/NeoPixel compatible RGB LED. Chain multiple units by connecting `DOUT` → `DIN` of the next; all LEDs are addressed sequentially from a single data line.

| Pin | Role |
|---|---|
| `VDD` | Power (5V) |
| `VSS` | Ground |
| `DIN` | Data input (connect to MCU GPIO) |
| `DOUT` | Data output — connect to next NeoPixel's `DIN` when chaining |

No configurable attrs.

> For larger arrays use `wokwi-led-strip`, `wokwi-led-ring`, or `wokwi-led-matrix` instead.

```json
{ "type": "wokwi-neopixel", "id": "rgb1", "top": 82.9, "left": 133.4, "rotate": 180, "attrs": {} }
```

ESP32 (`board-esp32-devkit-c-v4`) wiring — DIN on GPIO 5, 5V power:
```json
["esp:GND.3", "rgb1:VSS", "black", ["h0"]],
["esp:5",     "rgb1:DIN", "green", ["h14.44", "v-19.2"]],
["rgb1:VDD",  "esp:5V",   "red",   ["h0.2", "v122.4", "h-163.2", "v-19.2"]]
```

Library: `Adafruit_NeoPixel`. Use `NEO_GRB + NEO_KHZ800`.

```cpp
#include <Adafruit_NeoPixel.h>
Adafruit_NeoPixel pixel(1, 5, NEO_GRB + NEO_KHZ800);
// setup: pixel.begin();
// set color: pixel.setPixelColor(0, pixel.Color(150, 0, 0)); // Red
// push: pixel.show();
```

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

### wokwi-led-matrix (WS2812B NeoPixel matrix panel)

Configurable WS2812B NeoPixel matrix. Supports chaining via `DOUT`. Similar to `wokwi-neopixel-canvas` but adds layout, shape, and size options for matching real-world panels.

| Pin | Role |
|---|---|
| `DIN` | Data input (connect to MCU GPIO) |
| `VDD` | Power (5V) |
| `VSS` | Ground |
| `DOUT` | Data output — chain to next panel's `DIN` |

| Attr | Default | Description |
|---|---|---|
| `rows` | `"8"` | Number of rows |
| `cols` | `"8"` | Number of columns |
| `layout` | `""` | `""` = progressive (all rows left-to-right); `"serpentine"` = alternating direction. **Most real WS2812 panels use `"serpentine"`** |
| `brightness` | `"1"` | Brightness multiplier (e.g. `"6"` for brighter sim output) |
| `pixelShape` | `""` | `""` = default rendering; `"square"` or `"circle"` |
| `pixelSize` | `"5050"` | LED package size: `"5050"`, `"3535"`, or `"2020"` |

> `wokwi-led-matrix` vs `wokwi-neopixel-canvas`: use `wokwi-led-matrix` when you need `serpentine` layout, pixel shape/size control, or panel chaining (`DOUT`). Use `wokwi-neopixel-canvas` for simple grids where those features aren't needed.

```json
{ "type": "wokwi-led-matrix", "id": "matrix1", "top": -54, "left": 63,
  "attrs": { "rows": "8", "cols": "8", "layout": "serpentine", "brightness": "6" } }
```

ESP32 wiring (DIN on GPIO 2, 5V power):
```json
["matrix1:DIN", "esp:2",     "green", []],
["matrix1:VDD", "esp:5V",    "red",   []],
["matrix1:VSS", "esp:GND.2", "black", []]
```

Chaining two panels (panel 1 DOUT → panel 2 DIN, shared power):
```json
["matrix1:DOUT", "matrix2:DIN",  "green", []],
["matrix1:VDD",  "matrix2:VDD",  "red",   []],
["matrix1:VSS",  "matrix2:VSS",  "black", []]
```

Library: `Adafruit_NeoPixel`. Use `NEO_GRB + NEO_KHZ800`. Pixel index 0 = top-left for progressive layout; for serpentine, row 1 goes right-to-left.

```cpp
#include <Adafruit_NeoPixel.h>
Adafruit_NeoPixel matrix(8 * 8, 2, NEO_GRB + NEO_KHZ800);
// setup: matrix.begin(); matrix.setBrightness(50);
// set pixel: matrix.setPixelColor(i, matrix.Color(0, 0, 150));
// push: matrix.show();
```

---

### wokwi-led-ring (WS2812B NeoPixel ring)

Circular WS2812B NeoPixel ring. Supports chaining via `DOUT`. Same `Adafruit_NeoPixel` library as `wokwi-led-matrix`.

| Pin | Role |
|---|---|
| `GND` | Ground |
| `VCC` | Power (5V) |
| `DIN` | Data input (connect to MCU GPIO) |
| `DOUT` | Data output — chain to next ring's `DIN` |

| Attr | Default | Description |
|---|---|---|
| `pixels` | `"16"` | Number of LEDs in the ring |

```json
{ "type": "wokwi-led-ring", "id": "ring1", "top": -18, "left": 30, "attrs": { "pixels": "16" } }
```

ESP32 wiring (DIN on GPIO 15, 5V power):
```json
["ring1:GND", "esp:GND.2", "black", []],
["ring1:VCC", "esp:5V",    "red",   []],
["ring1:DIN", "esp:15",    "green", []]
```

Chaining two rings (ring 1 DOUT → ring 2 DIN, shared power):
```json
["ring1:DOUT", "ring2:DIN", "green", []],
["ring1:VCC",  "ring2:VCC", "red",   []],
["ring1:GND",  "ring2:GND", "black", []]
```

Library: `Adafruit_NeoPixel`. Pixel index 0 is the first LED after `DIN` entry point, incrementing clockwise.

```cpp
#include <Adafruit_NeoPixel.h>
Adafruit_NeoPixel ring(16, 15, NEO_GRB + NEO_KHZ800);
// setup: ring.begin(); ring.setBrightness(50);
// set pixel: ring.setPixelColor(i, ring.Color(0, 150, 0));
// push: ring.show();
```

> When chaining, pass the total pixel count to the constructor: `Adafruit_NeoPixel allPixels(16 + 12, PIN, ...)` for a 16-pixel ring chained to a 12-pixel ring.

---

### wokwi-led-strip (WS2812B NeoPixel strip)

Linear WS2812B NeoPixel strip. Exposes both input and output power/ground pins for easy chaining.

| Pin | Role |
|---|---|
| `VDD` | Power input (5V) |
| `DIN` | Data input (connect to MCU GPIO) |
| `VSS` | Ground input |
| `VDD.2` | Power output — connect to next strip's `VDD` when chaining |
| `DOUT` | Data output — connect to next strip's `DIN` when chaining |
| `VSS.2` | Ground output — connect to next strip's `VSS` when chaining |

| Attr | Default | Description |
|---|---|---|
| `pixels` | `"8"` | Number of LEDs in the strip |
| `pixelShape` | `""` | `""` = smooth (scaled up); `"square"` = square pixel; `"circle"` = circular pixel |
| `pixelSize` | `"5050"` | Package size: `"5050"` (23 px), `"3535"` (16 px), `"2020"` (9 px) |

```json
{ "type": "wokwi-led-strip", "id": "strip1", "top": -74, "left": -297, "attrs": { "pixels": "8" } }
```

ESP32 wiring (DIN on GPIO 2, 5V power):
```json
["strip1:DIN", "esp:2",     "green", []],
["strip1:VDD", "esp:5V",    "red",   []],
["strip1:VSS", "esp:GND.2", "black", []]
```

Chaining two strips (strip 1 output side → strip 2 input side):
```json
["strip1:DOUT",  "strip2:DIN",  "green", []],
["strip1:VDD.2", "strip2:VDD",  "red",   []],
["strip1:VSS.2", "strip2:VSS",  "black", []]
```

Library: `Adafruit_NeoPixel`. Pixel index 0 = LED closest to `DIN`.

```cpp
#include <Adafruit_NeoPixel.h>
Adafruit_NeoPixel strip(8, 2, NEO_GRB + NEO_KHZ800);
// setup: strip.begin(); strip.setBrightness(50);
// set pixel: strip.setPixelColor(i, strip.Color(150, 0, 0));
// push: strip.show();
```

> `wokwi-led-strip` vs `wokwi-led-matrix` vs `wokwi-led-ring`: use strip for linear runs, matrix for 2D grids (with optional serpentine layout), ring for circular arrangements. All use `Adafruit_NeoPixel` and chain the same way via `DOUT` → `DIN`.

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

### board-nokia-5110 (84×48 monochrome LCD)

Nokia 5110 / PCD8544 graphic LCD. SPI interface. **Power with 3.3V only — not 5V.** `BL` (backlight) can be connected to 3.3V to enable the backlight, or to a PWM pin for dimming.

| Pin | Role |
|---|---|
| `RST` | Reset (active low) |
| `CE` | Chip enable / chip select (active low) |
| `DC` | Data / command select |
| `DIN` | SPI data input (MOSI) |
| `CLK` | SPI clock |
| `VCC` | Power (**3.3V only**) |
| `BL` | Backlight — connect to 3.3V to enable, or PWM pin for dimming |
| `GND` | Ground |

No configurable attrs.

Library: `Adafruit PCD8544` (+ `Adafruit_GFX`). Key calls: `display.begin()`, `display.clearDisplay()`, `display.setCursor()`, `display.println()`, `display.display()`.

```json
{ "type": "board-nokia-5110", "id": "lcd", "top": 49.02, "left": 139.2, "attrs": {} }
```

Arduino Uno wiring (CLK=3, DIN=4, DC=5, RST=6, CE=7, 3.3V power):
```json
["lcd:CLK", "uno:3",    "orange", []],
["lcd:DIN", "uno:4",    "green",  []],
["lcd:DC",  "uno:5",    "purple", []],
["lcd:RST", "uno:6",    "violet", []],
["lcd:CE",  "uno:7",    "blue",   []],
["lcd:VCC", "uno:3.3V", "red",    []],
["lcd:GND", "uno:GND.1","black",  []]
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

### wokwi-nlsf595 (serial tri-color LED driver)

SPI shift register designed to drive common-anode RGB LEDs. One unit controls 2 RGB LEDs (uses QA–QF); chain two units for up to 5 RGB LEDs via `SQH` → `SI`.

| Pin | Role |
|---|---|
| `SI` | Serial data input (connect to MCU GPIO) |
| `SCK` | Serial clock |
| `RCK` | Storage / latch clock — pulse to push shift register to outputs |
| `OE` | Output enable, active low — **connect to GND** to permanently enable |
| `SCLR` | Reset, active low — **connect to VCC** to disable reset |
| `QA`–`QH` | Parallel outputs (connect to RGB LED pins via resistors) |
| `SQH` | Serial output — chain to next unit's `SI` |
| `VCC` | Power |
| `GND` | Ground |

**Output mapping for 2 RGB LEDs (common-anode):** LED cathodes connect to `QA`–`QF` via resistors (active low = segment lit). `QG`/`QH` unused for 2-LED configs.

| Output | Role |
|---|---|
| `QA` | RGB2 Blue |
| `QB` | RGB2 Green |
| `QC` | RGB2 Red |
| `QD` | RGB1 Blue |
| `QE` | RGB1 Green |
| `QF` | RGB1 Red |

```json
{ "type": "wokwi-nlsf595", "id": "sr1", "top": 102.5, "left": 182.16, "rotate": 90, "attrs": {} }
```

Arduino Uno wiring (SI=2, SCK=3, RCK=4, OE→GND, SCLR→VCC):
```json
["sr1:GND",  "uno:GND.1", "black",  ["h0"]],
["sr1:VCC",  "uno:5V",    "red",    []],
["sr1:OE",   "uno:GND.1", "black",  []],
["sr1:SI",   "uno:2",     "blue",   []],
["sr1:SCK",  "uno:3",     "purple", []],
["sr1:RCK",  "uno:4",     "gray",   []]
```

Wire `QA`–`QF` to RGB LED cathode pins via 220 Ω resistors; connect both `COM` pins to 5V.

**Chaining (shared SCK/RCK — SQH → SI of next chip):**
```json
["sr1:SQH", "sr2:SI", "orange", []]
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

8×8 LED matrix driven by MAX7219 over SPI. Each unit is one 8×8 grid; chain multiple units for wider displays.

| Pin | Role |
|---|---|
| `DIN` | SPI data in |
| `CS` | Chip select |
| `CLK` | SPI clock |
| `V+` | Power (5V) — input side |
| `GND` | Ground — input side |
| `DOUT` | SPI data out — connect to next unit's `DIN` for manual chaining |
| `V+.2` | Power — output side (pass-through for chaining) |
| `GND.2` | Ground — output side (pass-through for chaining) |
| `CS.2` | CS — output side (pass-through for chaining) |
| `CLK.2` | CLK — output side (pass-through for chaining) |

| Attr | Default | Description |
|---|---|---|
| `chain` | `"1"` | Number of 8×8 units chained side-by-side (e.g. `"4"` = 32×8). All units share one `type` entry. |
| `color` | `"red"` | LED color when lit (e.g. `"green"`, `"#ff8800"`) |
| `layout` | `"parola"` | Pixel wiring pattern: `"parola"` (Parola-compatible modules) or `"fc16"` (FC-16 modules from AliExpress/eBay). Wrong layout = text rotated or mirrored. |

**Single unit or `chain`-based wiring (Arduino Uno, CS=10, DIN=11, CLK=13):**
```json
{ "type": "wokwi-max7219-matrix", "id": "mat1", "top": 0, "left": 200, "attrs": { "chain": "4", "layout": "parola" } }
```
```json
["mat1:DIN", "uno:11",    "orange", []],
["mat1:CS",  "uno:10",    "green",  []],
["mat1:CLK", "uno:13",    "blue",   []],
["mat1:V+",  "uno:5V",    "red",    []],
["mat1:GND", "uno:GND.1", "black",  []]
```

**Manual chaining (separate units — e.g. different colors per row, vertical stacking):**
Connect `DOUT`→`DIN`, `CLK.2`→`CLK`, `CS.2`→`CS`, and pass-through power via `V+.2`/`GND.2`:
```json
["mat1:DOUT",  "mat2:DIN",  "blue",   []],
["mat1:CLK.2", "mat2:CLK",  "orange", []],
["mat1:CS.2",  "mat2:CS",   "green",  []],
["mat1:V+.2",  "mat2:V+",   "red",    []],
["mat1:GND.2", "mat2:GND",  "black",  []]
```

> Libraries: `MD_MAX72XX` (low-level) and `MD_Parola` (scrolling text, animations). For FC-16 modules use `MD_MAX72XX::FC16_HW` hardware type in code. The `chain` attr sets the display width — `MD_Parola` constructor must receive the same count.

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

### wokwi-hx711 (load cell amplifier)

HX711 24-bit ADC for load cells / strain gauges. Connects via a Wheatstone bridge (E+/E-/A+/A-/B+/B- pins are rendered visually based on `type` attr but are non-interactive in diagram.json — do not wire them).

| Pin | Role |
|---|---|
| `VCC` | Power (5V) |
| `DT` | Serial data out → MCU input |
| `SCK` | Serial clock → MCU output |
| `GND` | Ground |

| Attr | Default | Options |
|---|---|---|
| `type` | `"50kg"` | `"50kg"`, `"5kg"`, `"gauge"` |

Raw ADC range: 0–2 100 for `"5kg"`, 0–21 000 for `"50kg"`. Channel B and gain settings (32/64/128) are **not simulated**.

Library: `HX711` (Bogdan Necula). Use `scale.begin(DT_PIN, SCK_PIN)`, then `scale.tare()` and `scale.get_units()`.

Automation control: `load` (float, kg) — sets the simulated weight.

```json
{ "type": "wokwi-hx711", "id": "hx711", "top": 0, "left": 200, "attrs": { "type": "50kg" } }
```

```json
["hx711:VCC", "uno:5V",    "red",   []],
["hx711:GND", "uno:GND.1", "black", []],
["hx711:DT",  "uno:A1",    "green", []],
["hx711:SCK", "uno:A0",    "blue",  []]
```

---

### wokwi-ili9341 (240×320 color TFT LCD)

Full-color 2.8" SPI TFT display. **RST and LED (backlight) pins are not simulated — do not wire them.** MISO can be left unconnected unless reading data back from the display.

| Pin | Role | Notes |
|---|---|---|
| `VCC` | Power (5V) | |
| `GND` | Ground | |
| `CS` | SPI chip select | Any digital pin |
| `RST` | Reset | **Not simulated — leave unconnected** |
| `D/C` | Data / command | Any digital pin |
| `MOSI` | SPI data MCU → LCD | |
| `SCK` | SPI clock | |
| `LED` | Backlight | **Not simulated — leave unconnected** |
| `MISO` | SPI data LCD → MCU | Optional — omit if not reading back |

| Attr | Default | Description |
|---|---|---|
| `flipHorizontal` | `""` | Set `"1"` to flip display horizontally |
| `flipVertical` | `""` | Set `"1"` to flip display vertically |
| `swapXY` | `""` | Set `"1"` to swap X/Y axes |

Libraries: `Adafruit_ILI9341` (with `Adafruit_GFX`), `lcdgfx`.

```json
{ "type": "wokwi-ili9341", "id": "lcd1", "top": 0, "left": 200, "attrs": {} }
```

Arduino Uno wiring (CS = 10, D/C = 9 — these can be any digital pins):
```json
["lcd1:VCC",  "uno:5V",    "red",       []],
["lcd1:GND",  "uno:GND.1", "black",     []],
["lcd1:SCK",  "uno:13",    "green",     []],
["lcd1:MOSI", "uno:11",    "green",     []],
["lcd1:MISO", "uno:12",    "limegreen", []],
["lcd1:CS",   "uno:10",    "orange",    []],
["lcd1:D/C",  "uno:9",     "purple",    []]
```

ESP32 wiring (hardware SPI — CS = D5, D/C = D4):
```json
["lcd1:VCC",  "esp:3V3",   "red",       []],
["lcd1:GND",  "esp:GND.1", "black",     []],
["lcd1:SCK",  "esp:D18",   "green",     []],
["lcd1:MOSI", "esp:D23",   "green",     []],
["lcd1:MISO", "esp:D19",   "limegreen", []],
["lcd1:CS",   "esp:D5",    "orange",    []],
["lcd1:D/C",  "esp:D4",    "purple",    []]
```

---

### wokwi-ir-receiver + wokwi-ir-remote (38 kHz infrared)

Always used together. The remote sends NEC-encoded IR signals; the receiver decodes them.

#### wokwi-ir-receiver

| Pin | Role |
|---|---|
| `VCC` | Power (5V) |
| `GND` | Ground |
| `DAT` | Digital output → MCU input (active low) |

| Attr | Default | Description |
|---|---|---|
| `color` | `""` | Visual color of the receiver body (e.g. `"green"`) |

During simulation you can also **click the receiver** to manually send an arbitrary NEC-encoded signal (specify address + command fields in the pop-up UI).

Libraries: `IRremote`, `IRMP`.

```json
{ "type": "wokwi-ir-receiver", "id": "ir1", "top": 0, "left": 300, "attrs": { "color": "green" } }
```

```json
["ir1:VCC", "uno:5V",    "red",   []],
["ir1:GND", "uno:GND.1", "black", []],
["ir1:DAT", "uno:2",     "green", []]
```

#### wokwi-ir-remote

No wiring needed — the remote communicates with the receiver automatically in simulation. Just place it in the `parts` array next to the receiver.

NEC address is always `0`. Commands and keyboard shortcuts:

| Key | Command | NEC encoded | Keyboard shortcut |
|---|---|---|---|
| Power | 162 | `0xFFA25D` | O |
| Menu | 226 | `0xFFE21D` | M |
| Test | 34 | `0xFF22DD` | T |
| Plus | 2 | `0xFF02FD` | + |
| Back | 194 | `0xFFC23D` | B |
| Previous | 224 | `0xFFE01F` | Left arrow |
| Play | 168 | `0xFFA857` | P |
| Next | 144 | `0xFF906F` | Right arrow |
| 0 | 104 | `0xFF6897` | 0 |
| Minus | 152 | `0xFF9867` | - |
| C | 176 | `0xFFB04F` | C |
| 1 | 48 | `0xFF30CF` | 1 |
| 2 | 24 | `0xFF18E7` | 2 |
| 3 | 122 | `0xFF7A85` | 3 |
| 4 | 16 | `0xFF10EF` | 4 |
| 5 | 56 | `0xFF38C7` | 5 |
| 6 | 90 | `0xFF5AA5` | 6 |
| 7 | 66 | `0xFF42BD` | 7 |
| 8 | 74 | `0xFF4AB5` | 8 |
| 9 | 82 | `0xFF52AD` | 9 |

```json
{ "type": "wokwi-ir-remote", "id": "remote1", "top": 0, "left": 450, "attrs": {} }
```

**Minimal IR receiver circuit (Uno, DAT on pin 2):**
```json
[
  { "type": "wokwi-arduino-uno",  "id": "uno",     "top": 200, "left": 0,   "attrs": {} },
  { "type": "wokwi-ir-receiver",  "id": "ir1",     "top": 0,   "left": 100, "attrs": {} },
  { "type": "wokwi-ir-remote",    "id": "remote1", "top": 0,   "left": 300, "attrs": {} }
]
```
```json
["ir1:VCC", "uno:5V",    "red",   []],
["ir1:GND", "uno:GND.1", "black", []],
["ir1:DAT", "uno:2",     "green", []]
```

---

### wokwi-rgb-led (5mm common-anode/cathode RGB LED)

Single 5mm RGB LED with a shared common pin. Each color channel needs a ~220 Ω series resistor.

| Pin | Role |
|---|---|
| `R` | Red channel |
| `G` | Green channel |
| `B` | Blue channel |
| `COM` | Common — anode (VCC) by default, or cathode (GND) when attr is `"cathode"` |

| Attr | Default | Description |
|---|---|---|
| `common` | `"anode"` | `"anode"`: COM → VCC, drive R/G/B LOW to light. `"cathode"`: COM → GND, drive R/G/B HIGH to light. |

```json
{ "type": "wokwi-rgb-led", "id": "rgb1", "top": 0, "left": 200, "attrs": { "common": "cathode" } }
```

**Common-cathode wiring (COM → GND, drive pins HIGH to light — use PWM for color mixing):**
```json
["rgb1:COM", "uno:GND.1", "black",  []],
["r1:2",     "rgb1:R",    "red",    []],
["r2:2",     "rgb1:G",    "green",  []],
["r3:2",     "rgb1:B",    "blue",   []],
["uno:11",   "r1:1",      "red",    []],
["uno:10",   "r2:1",      "green",  []],
["uno:9",    "r3:1",      "blue",   []]
```

**Common-anode wiring (COM → 3.3V or 5V, drive pins LOW to light):**
```json
["rgb1:COM", "uno:3.3V",  "red",   []],
["r1:2",     "rgb1:R",    "red",   []],
["r2:2",     "rgb1:G",    "green", []],
["r3:2",     "rgb1:B",    "blue",  []],
["uno:11",   "r1:1",      "red",   []],
["uno:10",   "r2:1",      "green", []],
["uno:9",    "r3:1",      "blue",  []]
```

> `r1`, `r2`, `r3` are `wokwi-resistor` parts with `"value": "220"`. Use PWM-capable pins (3, 5, 6, 9, 10, 11 on Uno) for smooth `analogWrite()` color mixing.

---

### wokwi-relay-module (single-channel relay module)

Electrically operated SPDT switch. COM switches between NC and NO depending on the IN signal and the `transistor` attr.

| Pin | Role |
|---|---|
| `VCC` | Power |
| `GND` | Ground |
| `IN` | Control signal from MCU |
| `COM` | Common (switched) terminal |
| `NC` | Normally closed — connected to COM when relay is **not** activated |
| `NO` | Normally open — connected to COM when relay is **activated** |

| Attr | Default | Description |
|---|---|---|
| `transistor` | `"npn"` | `"npn"` (active-high): IN high or floating → COM-NC; IN low → COM-NO. `"pnp"` (active-low): IN low or floating → COM-NC; IN high → COM-NO. |

**State table:**

| `transistor` | IN | COM connects to |
|---|---|---|
| `"npn"` (default) | HIGH or floating | NC |
| `"npn"` (default) | LOW | NO |
| `"pnp"` | LOW or floating | NC |
| `"pnp"` | HIGH | NO |

```json
{ "type": "wokwi-relay-module", "id": "relay1", "top": 0, "left": 200, "attrs": {} }
```

Basic wiring — MCU drives IN, load switched on COM/NC/NO:
```json
["relay1:VCC", "uno:5V",    "red",   []],
["relay1:GND", "uno:GND.1", "black", []],
["relay1:IN",  "uno:8",     "green", []]
```

Switching two LEDs (orange on NC = default on, green on NO = activates when IN goes LOW):
```json
["relay1:COM", "vcc2:VCC",  "red",   []],
["relay1:NC",  "led1:A",    "gold",  []],
["relay1:NO",  "led2:A",    "green", []],
["led1:C",     "gnd2:GND",  "black", []],
["led2:C",     "gnd2:GND",  "black", []]
```

> Use `wokwi-vcc` / `wokwi-gnd` power symbols (see above) to avoid long power wires in the diagram.

---

### wokwi-ks2e-m-dc5 (DPDT relay)

Double Pole Double Throw relay. Two independent poles (P1/P2), each switching between a Normally Closed (NC) and Normally Open (NO) contact.

| Pin | Role |
|---|---|
| `COIL1` | Coil terminal 1 — connect to MCU GPIO (or transistor collector) |
| `COIL2` | Coil terminal 2 — connect to GND |
| `P1` | Pole 1 (common) |
| `NC1` | Normally closed 1 — connected to P1 when coil **un**powered |
| `NO1` | Normally open 1 — connected to P1 when coil powered |
| `P2` | Pole 2 (common) |
| `NC2` | Normally closed 2 — connected to P2 when coil **un**powered |
| `NO2` | Normally open 2 — connected to P2 when coil powered |

**State summary:**

| Coil | P1 connects to | P2 connects to |
|---|---|---|
| Unpowered | `NC1` | `NC2` |
| Powered | `NO1` | `NO2` |

```json
{ "type": "wokwi-ks2e-m-dc5", "id": "relay1", "top": 0, "left": 200, "attrs": {} }
```

**Basic example — GPIO controls which LED lights (red = off, green = on):**
```json
["relay1:COIL1", "uno:13",    "purple", []],
["relay1:COIL2", "uno:GND.1", "black",  []],
["relay1:P1",    "uno:5V",    "red",    []],
["relay1:NC1",   "r1:1",      "gray",   []],
["relay1:NO1",   "r2:1",      "gray",   []],
["r1:2",         "led1:A",    "gray",   []],
["led1:C",       "uno:GND.1", "black",  []],
["r2:2",         "led2:A",    "gray",   []],
["led2:C",       "uno:GND.1", "black",  []]
```

> Both poles are independent — use P2/NC2/NO2 to switch a second circuit simultaneously with no extra GPIO pin.

---

### wokwi-ky-040 (rotary encoder)

KY-040 module, 20 steps per revolution. Internal pull-ups on CLK and DT — no external resistors needed, VCC can be left floating.

| Pin | Role |
|---|---|
| `CLK` | Encoder pin A — goes LOW first on CW rotation |
| `DT` | Encoder pin B — goes LOW first on CCW rotation |
| `SW` | Push button — shorted to GND when pressed; use `INPUT_PULLUP` |
| `VCC` | Power (3.3V or 5V) |
| `GND` | Ground |

**Direction decoding:** when CLK falls LOW, read DT — `HIGH` = clockwise, `LOW` = counterclockwise.

**Keyboard shortcuts** (click encoder first to focus):

| Key | Action |
|---|---|
| Right / Up | One step clockwise (hold for continuous) |
| Left / Down | One step counterclockwise (hold for continuous) |
| Spacebar | Press button |

> Connect CLK to an interrupt-capable pin and use `attachInterrupt(digitalPinToInterrupt(CLK), handler, FALLING)` — polling in `loop()` misses steps if anything uses `delay()`.

```json
{ "type": "wokwi-ky-040", "id": "enc1", "top": 0, "left": 200, "attrs": {} }
```

Arduino Uno wiring (CLK = 2, DT = 3, SW = 4 — CLK/DT on interrupt pins):
```json
["enc1:VCC", "uno:5V",    "red",    []],
["enc1:GND", "uno:GND.2", "black",  []],
["enc1:CLK", "uno:2",     "blue",   []],
["enc1:DT",  "uno:3",     "green",  []],
["enc1:SW",  "uno:4",     "purple", []]
```

---

### wokwi-membrane-keypad (4×4 / 4×3 matrix keypad)

Standard membrane keypad. Rows and columns are scanned by the MCU to detect key presses.

| Pin | Role |
|---|---|
| `R1` | Row 1 (top row) |
| `R2` | Row 2 |
| `R3` | Row 3 |
| `R4` | Row 4 (bottom row) |
| `C1` | Column 1 (left) |
| `C2` | Column 2 |
| `C3` | Column 3 |
| `C4` | Column 4 (right) — not present when `columns` = `"3"` |

| Attr | Default | Description |
|---|---|---|
| `columns` | `"4"` | `"4"` for 4×4 keypad, `"3"` for 4×3 keypad (no C4/R* column) |
| `keys` | `["1","2","3","A","4","5","6","B","7","8","9","C","*","0","#","D"]` | Flat array of key labels, row-major order. Must be exactly `rows × columns` entries. Unicode supported (e.g. `"★"`, `"Ⓐ"`). |

> Key labels in `keys` define what `keypad.getKey()` returns in code — they must be single ASCII characters for the `Keypad` library. Label and return value can differ but keeping them consistent avoids confusion.

**Keyboard shortcuts** (click keypad to focus): press `0–9`, `A`, `B`, `C`, `D`, `*`, `#` to activate the corresponding key.

```json
{ "type": "wokwi-membrane-keypad", "id": "keypad1", "top": 0, "left": 94, "attrs": {} }
```

Arduino Uno wiring (R1–R4 = pins 9–6, C1–C4 = pins 5–2):
```json
["keypad1:R1", "uno:9", "gold",   []],
["keypad1:R2", "uno:8", "purple", []],
["keypad1:R3", "uno:7", "green",  []],
["keypad1:R4", "uno:6", "blue",   []],
["keypad1:C1", "uno:5", "pink",   []],
["keypad1:C2", "uno:4", "orange", []],
["keypad1:C3", "uno:3", "gray",   []],
["keypad1:C4", "uno:2", "brown",  []]
```

Library: `Keypad` (Mark Stanley). Constructor takes key map, row pins, col pins, and dimensions:
```cpp
#include <Keypad.h>
const uint8_t ROWS = 4, COLS = 4;
char keys[ROWS][COLS] = {
  {'1','2','3','A'}, {'4','5','6','B'},
  {'7','8','9','C'}, {'*','0','#','D'}
};
uint8_t rowPins[ROWS] = {9, 8, 7, 6};
uint8_t colPins[COLS] = {5, 4, 3, 2};
Keypad keypad = Keypad(makeKeymap(keys), rowPins, colPins, ROWS, COLS);
// loop: char key = keypad.getKey(); if (key != NO_KEY) Serial.println(key);
```

4×3 variant (omit C4, set `"columns": "3"`, use 3-entry `colPins`):
```json
{ "type": "wokwi-membrane-keypad", "id": "keypad1", "top": 0, "left": 94, "attrs": { "columns": "3" } }
```

---

### wokwi-microsd-card (SPI microSD card)

SPI-interface microSD card socket. Wokwi automatically creates a FAT16 filesystem (up to 8 MB) and pre-populates it with your project files at simulation start.

| Pin | Role |
|---|---|
| `CD` | Card detect — LOW when no card present. **Always disconnected in simulation** (card is always inserted). |
| `DO` | SPI data output (MISO) |
| `GND` | Ground |
| `SCK` | SPI clock |
| `VCC` | Power (5V) |
| `DI` | SPI data input (MOSI) |
| `CS` | Chip select (active low) |

No configurable attrs — the filesystem is managed automatically by the simulator.

```json
{ "type": "wokwi-microsd-card", "id": "sd1", "top": -33, "left": 14, "rotate": 90, "attrs": {} }
```

Arduino Uno wiring (hardware SPI — SCK=13, MISO=12, MOSI=11, CS=10):
```json
["sd1:SCK", "uno:13",    "green", []],
["sd1:DO",  "uno:12",    "green", []],
["sd1:DI",  "uno:11",    "green", []],
["sd1:CS",  "uno:10",    "green", []],
["sd1:VCC", "uno:5V",    "red",   []],
["sd1:GND", "uno:GND.1", "black", []]
```

Libraries: `SD` (built-in Arduino) or `SdFat` (recommended — faster, more features). `SdFat` example:
```cpp
#include "SdFat.h"
SdFat sd;
void setup() {
  if (!sd.begin(10, SD_SCK_MHZ(4))) { /* handle error */ }
  sd.ls(LS_R | LS_SIZE);  // list all files with sizes
}
```

> `SD_SCK_MHZ(4)` keeps clock at 4 MHz which is reliable in simulation. `LS_R` recurses subdirectories; `LS_SIZE` prints file sizes. Use `sd.open("file.txt")` / `file.read()` / `file.write()` for file I/O.

---

### wokwi-ntc-temperature-sensor (NTC thermistor module)

10K NTC thermistor in series with a 10K resistor. `OUT` produces an analog voltage proportional to temperature — read with `analogRead()` on any ADC pin.

| Pin | Role |
|---|---|
| `VCC` | Power (3.3V or 5V) |
| `OUT` | Analog output — connect to ADC pin |
| `GND` | Ground |

| Attr | Default | Description |
|---|---|---|
| `temperature` | `"24"` | Initial temperature (°C) |
| `beta` | `"3950"` | Beta coefficient of the thermistor — match to your conversion formula |

**Temperature conversion (°C):**
```cpp
const float BETA = 3950; // match the beta attr value
int raw = analogRead(A0);
float celsius = 1 / (log(1 / (1023.0 / raw - 1)) / BETA + 1.0 / 298.15) - 273.15;
```

```json
{ "type": "wokwi-ntc-temperature-sensor", "id": "ntc1", "top": -130.63, "left": 11.15,
  "attrs": { "beta": "3950", "temperature": "24" } }
```

Arduino Uno wiring (OUT on A0, powered from VIN):
```json
["ntc1:VCC", "uno:VIN",   "red",   []],
["ntc1:GND", "uno:GND.1", "black", []],
["ntc1:OUT", "uno:A0",    "green", []]
```

ESP32 wiring (OUT on GPIO34 — ADC-only pin):
```json
["ntc1:VCC", "esp:3V3",   "red",   []],
["ntc1:GND", "esp:GND.1", "black", []],
["ntc1:OUT", "esp:D34",   "green", []]
```

> The simulator supports the `temperature` automation control — use `set-control` in simulation scenarios to animate temperature changes at runtime.

---

### wokwi-tm1637-7segment (TM1637 4-digit 7-segment display)

4-digit 7-segment display driven by the TM1637 chip over a 2-wire interface (CLK + DIO). Not I2C-compatible — use a TM1637-specific library.

| Pin | Role |
|---|---|
| `CLK` | Clock input |
| `DIO` | Bidirectional data (also used for ACK) |
| `VCC` | Power (5V) |
| `GND` | Ground |

| Attr | Default | Description |
|---|---|---|
| `color` | `"red"` | Segment LED color (e.g. `"green"`, `"blue"`) |

Libraries: `TM1637_RT` (RobTillaart) or `Grove 4-Digit Display`. Both are available in Wokwi's library manager.

```json
{ "type": "wokwi-tm1637-7segment", "id": "sevseg1", "top": -124, "left": 7,
  "attrs": { "color": "red" } }
```

Arduino Uno wiring (CLK=2, DIO=3):
```json
["sevseg1:CLK", "uno:2",    "green", []],
["sevseg1:DIO", "uno:3",    "green", []],
["sevseg1:VCC", "uno:5V",    "red",   []],
["sevseg1:GND", "uno:GND.1", "black", []]
```

Pi Pico wiring (CLK=GP16, DIO=GP17, powered from VBUS):
```json
["sevseg1:CLK", "pico:GP16",  "green", []],
["sevseg1:DIO", "pico:GP17",  "green", []],
["sevseg1:VCC", "pico:VBUS",  "red",   []],
["sevseg1:GND", "pico:GND.8", "black", []]
```

> Any two digital GPIO pins work for CLK/DIO — no hardware I2C/SPI pins required.

---

### wokwi-pir-motion-sensor (PIR motion sensor)

Passive Infrared motion sensor. `OUT` goes **HIGH** when motion is detected, stays HIGH for `delayTime` seconds, then goes LOW. After going LOW the sensor ignores further input for `inhibitTime` seconds before sensing again.

| Pin | Role |
|---|---|
| `VCC` | Power (5V) |
| `GND` | Ground |
| `OUT` | Digital output — HIGH = motion detected |

| Attr | Default | Description |
|---|---|---|
| `delayTime` | `"5"` | Seconds `OUT` stays HIGH after motion |
| `inhibitTime` | `"1.2"` | Seconds the sensor ignores motion after `OUT` returns LOW |
| `retrigger` | `""` | Default (enabled): delay resets each time new motion is detected while `OUT` is HIGH. Set `"0"` to disable retriggering. |

**Triggering in simulation:** click the sensor while running → pop-up → **"Simulate Motion"**.

```json
{ "type": "wokwi-pir-motion-sensor", "id": "pir1", "top": -42, "left": 25.81, "attrs": {} }
```

Arduino Uno wiring (OUT on pin 2, indicator LED on pin 13):
```json
["pir1:VCC", "uno:5V",    "red",   []],
["pir1:GND", "uno:GND.1", "black", []],
["pir1:OUT", "uno:2",     "green", []]
```

---

### wokwi-photoresistor-sensor (LDR module)

LDR in series with a 10K resistor. `AO` is an analog voltage that falls as illumination rises. `DO` goes **HIGH in darkness, LOW in light** (threshold-controlled); the onboard DO LED lights when `DO` is LOW.

| Pin | Role |
|---|---|
| `VCC` | Power (5V) |
| `GND` | Ground |
| `AO` | Analog output — connect to ADC pin |
| `DO` | Digital output — HIGH = dark, LOW = light |

| Attr | Default | Description |
|---|---|---|
| `lux` | `"500"` | Initial illumination (lux) |
| `threshold` | `"2.5"` | Voltage threshold for `DO` (V) — default ≈ 100 lux |
| `rl10` | `"50"` | LDR resistance at 10 lux (kΩ) |
| `gamma` | `"0.7"` | Slope of log(R)/log(lux) curve |

**Lux reference (VCC = 5V, default gamma/rl10):**

| Condition | Lux | analogRead() |
|---|---|---|
| Full moon | 0.1 | 1016 |
| Twilight | 10 | 853 |
| Office lighting | 400 | 281 |
| Full daylight | 10 000 | 39 |

**Analog → lux conversion:**
```cpp
const float GAMMA = 0.7, RL10 = 50;
int raw = analogRead(A0);
float voltage    = raw / 1024.0 * 5;
float resistance = 2000 * voltage / (1 - voltage / 5);
float lux        = pow(RL10 * 1e3 * pow(10, GAMMA) / resistance, 1.0 / GAMMA);
// guard: if (!isfinite(lux)) lux = 0;
```

```json
{ "type": "wokwi-photoresistor-sensor", "id": "ldr1", "top": -62.39, "left": 70.26, "attrs": {} }
```

Arduino Uno wiring (AO on A0, DO on pin 2):
```json
["ldr1:VCC", "uno:5V",    "red",   []],
["ldr1:GND", "uno:GND.1", "black", []],
["ldr1:AO",  "uno:A0",    "green", []],
["ldr1:DO",  "uno:2",     "blue",  []]
```

Automation control: `lux` (float) — set illumination at runtime with `set-control`.

---
