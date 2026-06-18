/**
 * arduino_bootstrap.ino — nff platform onboarding firmware.
 *
 * `nff init` fills in the three values below (WiFi SSID/password from this computer's
 * network, and the nff cloud broker host), drops in a freshly provisioned credentials.h,
 * compiles, and flashes this to your board. On first boot the device joins WiFi, connects
 * to the cloud broker on the SHARED batch credential, announces itself, and — because the
 * project auto-accepts during onboarding — the fleet rolls it a unique per-device cert and
 * it reboots CLAIMED. It then shows up in your dashboard automatically.
 *
 * You normally never edit this by hand; `nff init` rewrites the three #defines and provides
 * credentials.h. NFF_BOOTSTRAP_ENABLED=1 is set globally via build_opt.h so the flag reaches
 * the nff library translation units (nff_claim.c), not just this sketch. Keep Serial baud at
 * 115200 (matches `nff monitor`) or the onboarding log is garbled.
 */

#include <WiFi.h>
#include <nff.h>
#include "credentials.h"    // provisioned by `nff init` (shared batch bootstrap header)

// ---- Filled in by `nff init` --------------------------------------------
#define WIFI_SSID  "YOUR_WIFI_SSID"
#define WIFI_PASS  "YOUR_WIFI_PASS"
#define HOST_IP    "152.228.219.243"   // nff cloud fleet broker (mTLS :8883)

// ---- nff bootstrap config ------------------------------------------------
// device_id is left empty on purpose; nff_init() fills it with the board's hardware id
// (efuse / WiFi MAC) so this image is identical across the whole batch.

static nff_config_t g_cfg = NFF_BOOTSTRAP_CONFIG_INITIALIZER(HOST_IP);

// --------------------------------------------------------------------------

void setup() {
    Serial.begin(115200);

    Serial.printf("Connecting to WiFi %s...\n", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    uint32_t t0 = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - t0 < 30000) {
        delay(250);
        Serial.print(".");
    }
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("\nWiFi failed — restarting");
        ESP.restart();
    }
    Serial.printf("\nWiFi connected, IP: %s\n", WiFi.localIP().toString().c_str());

    // NVS-first: if a per-device operational cert is already stored, come up CLAIMED.
    if (nff_init(&g_cfg) != NFF_OK) {
        Serial.println("nff_init failed");
        return;
    }

    if (nff_get_mode() == NFF_MODE_BOOTSTRAP) {
        // Unclaimed: connect on the shared batch credential, announce, await rollover.
        // Reboots into CLAIMED mode once the fleet delivers the per-device cert.
        Serial.println("nff: BOOTSTRAP mode — announcing for enrollment");
        nff_bootstrap_run();
    } else {
        // Already claimed (cert loaded from NVS): connect operationally.
        Serial.println("nff: CLAIMED mode — connecting operationally");
        nff_connect();
    }
}

void loop() {
    nff_loop();
    delay(10);
}
