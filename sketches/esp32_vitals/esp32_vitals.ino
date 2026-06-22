// ESP32 vitals — a self-check for the nff loop: compile -> flash -> serial.
// No extra parts needed: the onboard LED (GPIO 2) toggles each second while
// serial prints live, changing telemetry (uptime + free heap), so you can see
// it's actually running on the chip, not replaying a cached build.

#define LED_PIN    2
#define BAUD_RATE  115200

unsigned long beats = 0;

void setup() {
  Serial.begin(BAUD_RATE);
  pinMode(LED_PIN, OUTPUT);
  Serial.println("nff vitals — online (built by the Rust nff binary)");
}

void loop() {
  beats++;
  digitalWrite(LED_PIN, beats % 2);          // onboard LED heartbeat
  Serial.print("beat=");
  Serial.print(beats);
  Serial.print("  uptime_s=");
  Serial.print(millis() / 1000);
  Serial.print("  free_heap=");
  Serial.println(ESP.getFreeHeap());
  delay(1000);
}
