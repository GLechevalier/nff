# nff — Wokwi Simulation Context

## Hard Rules
- Always use `nff flash --sim` to compile — never call arduino-cli directly.
- Always use `nff wokwi run` or `nff wokwi run --gui` to simulate.
- Never install libraries with arduino-cli. Use built-in ESP32 APIs only,
  or ask the user to install the library first.
- For ESP32 servo/PWM use ledcAttach + ledcWrite (built-in LEDC, no library).

## Project
- Board : arduino:avr:uno
- FQBN  : arduino:avr:uno
- Chip  : wokwi-arduino-uno

---

## Simulation Pipeline

```
1. Write sketch      sketches/<name>/<name>.ino
2. Edit circuit      diagram.json  (add components + wiring)
3. Compile           nff flash --sim sketches/<name> --board arduino:avr:uno
4. Visual sim        nff wokwi run --gui
   Headless sim      nff wokwi run [--timeout MS] [--serial-log FILE]
5. Fix bugs, repeat from step 3
```

wokwi.toml must point to the compiled ELF:
  firmware = "sketches/<name>/build/arduino.avr.uno/<name>.elf/<name>.ino.elf"

---

## diagram.json — Component Wiring

Always wire the serial monitor:
  ["esp:TX0", "$serialMonitor:RX", "", []]
  ["esp:RX0", "$serialMonitor:TX", "", []]

ESP32 pin names: esp:D<gpio>  esp:GND.1  esp:GND.2  esp:3V3  esp:VIN

Common components:
  wokwi-led          attrs: color (red/green/blue/yellow)
  wokwi-pushbutton   attrs: color — pins: btn:1.l (gpio side), btn:2.l (GND side)
  wokwi-servo        attrs: minAngle "-90", maxAngle "90" — pins: PWM, V+, GND
  wokwi-resistor     attrs: value (ohms)

Pushbutton wiring (with INPUT_PULLUP in sketch):
  ["esp:D15", "btn1:1.l", "green", []]
  ["esp:GND.2", "btn1:2.l", "black", []]

Servo connection:
  ["esp:D18",  "srv1:PWM", "orange", []]
  ["esp:3V3",  "srv1:V+",  "red",    []]
  ["esp:GND.1","srv1:GND", "black",  []]

---

## ESP32 Servo — LEDC (no library required)

Wokwi servo maps its full range to 500 µs – 2500 µs.
50 Hz / 16-bit resolution (max count 65 535, period 20 000 µs):

  −90°  →  duty 1638   (500 µs)
    0°  →  duty 4915  (1500 µs)
  +90°  →  duty 8192  (2500 µs)

```cpp
ledcAttach(SERVO_PIN, 50, 16);   // ESP32 Arduino core 3.x
ledcWrite(SERVO_PIN, 4915);      // center
```

Always set minAngle: "-90" and maxAngle: "90" on wokwi-servo in diagram.json.

---

## Debugging

- Compile error     → fix sketch, re-run nff flash --sim
- Wrong output      → nff wokwi run --serial-log out.txt, inspect out.txt
- Component silent  → check diagram.json pin names and connection direction
- Servo wrong angle → verify duty values match the 500–2500 µs Wokwi range
- Button not firing → INPUT_PULLUP + wiring gpio→btn:1.l, GND→btn:2.l
