# wokwi-diagram-extended — Wokwi Component Reference (Extended)

Additional component pinouts and wiring snippets for Wokwi `diagram.json`.
Load alongside `/wokwi-diagram` for full coverage.

---

### wokwi-buzzer (full reference)

> Also documented in `/wokwi-diagram` — this entry adds the `mode` attr.

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
