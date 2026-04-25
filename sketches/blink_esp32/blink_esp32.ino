// ESP32 LED blink — nff flash test sketch.
// Built-in LED is GPIO 2 on most ESP32 dev boards (DOIT DevKit, NodeMCU-32S, etc.).
// Change LED_PIN if your board uses a different pin.

#define LED_PIN    2
#define BAUD_RATE  115200
#define INTERVAL   500   // ms per blink half-cycle

void setup() {
  Serial.begin(BAUD_RATE);
  pinMode(LED_PIN, OUTPUT);
  Serial.println("nff blink test — ready");
}

void loop() {
  digitalWrite(LED_PIN, HIGH);
  Serial.println("LED ON");
  delay(INTERVAL);

  digitalWrite(LED_PIN, LOW);
  Serial.println("LED OFF");
  delay(INTERVAL);
}
