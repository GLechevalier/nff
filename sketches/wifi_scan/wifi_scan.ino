#include "WiFi.h"

void setup() {
  Serial.begin(115200);
  delay(1000);

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(100);

  Serial.println("WIFI_SCAN_START");

  int n = WiFi.scanNetworks();

  if (n == 0) {
    Serial.println("NO_NETWORKS_FOUND");
  } else {
    Serial.print("NETWORKS_FOUND:");
    Serial.println(n);
    for (int i = 0; i < n; i++) {
      Serial.print("NET|");
      Serial.print(i + 1);
      Serial.print("|SSID:");
      Serial.print(WiFi.SSID(i));
      Serial.print("|RSSI:");
      Serial.print(WiFi.RSSI(i));
      Serial.print("|ENC:");
      switch (WiFi.encryptionType(i)) {
        case WIFI_AUTH_OPEN:            Serial.print("OPEN"); break;
        case WIFI_AUTH_WEP:             Serial.print("WEP"); break;
        case WIFI_AUTH_WPA_PSK:         Serial.print("WPA"); break;
        case WIFI_AUTH_WPA2_PSK:        Serial.print("WPA2"); break;
        case WIFI_AUTH_WPA_WPA2_PSK:    Serial.print("WPA/WPA2"); break;
        case WIFI_AUTH_WPA2_ENTERPRISE: Serial.print("WPA2-ENT"); break;
        case WIFI_AUTH_WPA3_PSK:        Serial.print("WPA3"); break;
        default:                        Serial.print("UNKNOWN"); break;
      }
      Serial.print("|CH:");
      Serial.print(WiFi.channel(i));
      Serial.println("|END");
      delay(10);
    }
  }

  Serial.println("WIFI_SCAN_DONE");
  WiFi.scanDelete();
}

void loop() {}
