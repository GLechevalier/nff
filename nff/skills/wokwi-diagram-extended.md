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
