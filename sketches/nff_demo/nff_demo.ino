// nff demo — flashed to a real ESP32 via the nff MCP `flash` tool.
// Prints a heartbeat over serial at 115200 and blinks the onboard LED (GPIO 2).

const int LED = 2;
unsigned long n = 0;

void setup() {
  Serial.begin(115200);
  pinMode(LED, OUTPUT);
  delay(200);
  Serial.println();
  Serial.println("nff live on ESP32 — flashed by Claude via nff");
}

void loop() {
  digitalWrite(LED, HIGH);
  delay(150);
  digitalWrite(LED, LOW);
  Serial.print("heartbeat ");
  Serial.println(n++);
  delay(350);
}
