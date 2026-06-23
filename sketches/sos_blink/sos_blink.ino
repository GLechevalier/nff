// SOS Morse-code blinker for the ESP32 onboard LED (GPIO 2).
// SOS = ... --- ...  (3 short, 3 long, 3 short)

const int LED_PIN = 2;

const int DOT  = 200;   // short flash
const int DASH = 600;   // long flash (3x dot)
const int GAP_SYMBOL  = 200;   // gap between dots/dashes within a letter
const int GAP_LETTER  = 600;   // gap between letters
const int GAP_MESSAGE = 1400;  // gap before repeating the message

void flash(int duration) {
  digitalWrite(LED_PIN, HIGH);
  delay(duration);
  digitalWrite(LED_PIN, LOW);
  delay(GAP_SYMBOL);
}

void letter(const char *symbols) {
  for (int i = 0; symbols[i] != '\0'; i++) {
    flash(symbols[i] == '.' ? DOT : DASH);
  }
  delay(GAP_LETTER - GAP_SYMBOL);
}

void setup() {
  pinMode(LED_PIN, OUTPUT);
  Serial.begin(9600);
}

void loop() {
  Serial.println("SOS");
  letter("...");   // S
  letter("---");   // O
  letter("...");   // S
  delay(GAP_MESSAGE);
}
