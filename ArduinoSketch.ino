#include <WiFiNINA.h>
#include <ArduinoHttpClient.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_ADXL345_U.h>
#include <math.h>

const int ledPin = 13;
Adafruit_ADXL345_Unified accel = Adafruit_ADXL345_Unified();

const char* ssid = "AirPennNet-Device";
const char* password = "penn1740wifi";

WiFiClient wifiClient;
HttpClient client(wifiClient, "10.103.199.147", 8000);

float baselineZ = 0.0;

const float rmsThresholdZ = 0.10;
const float releaseThresholdZ = 0.08;

unsigned long lastTrigger = 0;
const unsigned long cooldownMs = 1000;
bool armed = true;

struct KnockMetrics {
  float rms;
  float peakAbsDZ;
  float peakSignedDZ;
  float xAtPeak;
  float yAtPeak;
  float zAtPeak;
  float magAtPeak;
  unsigned long eventMillis;
};

void connectWifi();
void saveVideo(KnockMetrics k);
float calibrateZ();
KnockMetrics measureKnockMetrics(unsigned long windowMs);

void setup() {
  connectWifi();

  while (!accel.begin()) {
    delay(500);
  }

  baselineZ = calibrateZ();
}

void loop() {
  KnockMetrics k = measureKnockMetrics(60);

  unsigned long now = millis();

  if (armed && k.rms > rmsThresholdZ) {
    armed = false;
    lastTrigger = now;

    saveVideo(k);
  }

  if (!armed && (now - lastTrigger >= cooldownMs) && k.rms < releaseThresholdZ) {
    armed = true;
  }
}

KnockMetrics measureKnockMetrics(unsigned long windowMs) {
  KnockMetrics k;
  k.rms = 0.0;
  k.peakAbsDZ = 0.0;
  k.peakSignedDZ = 0.0;
  k.xAtPeak = 0.0;
  k.yAtPeak = 0.0;
  k.zAtPeak = 0.0;
  k.magAtPeak = 0.0;
  k.eventMillis = millis();

  float sumSq = 0.0;
  int n = 0;
  unsigned long start = millis();

  while (millis() - start < windowMs) {
    sensors_event_t event;
    accel.getEvent(&event);

    float deltaZ = event.acceleration.z - baselineZ;
    float absDeltaZ = fabs(deltaZ);

    sumSq += deltaZ * deltaZ;
    n++;

    if (absDeltaZ > k.peakAbsDZ) {
      k.peakAbsDZ = absDeltaZ;
      k.peakSignedDZ = deltaZ;
      k.xAtPeak = event.acceleration.x;
      k.yAtPeak = event.acceleration.y;
      k.zAtPeak = event.acceleration.z;
      k.magAtPeak = sqrt(
        event.acceleration.x * event.acceleration.x +
        event.acceleration.y * event.acceleration.y +
        event.acceleration.z * event.acceleration.z
      );
      k.eventMillis = millis();
    }
  }

  if (n > 0) {
    k.rms = sqrt(sumSq / n);
  }

  return k;
}

void connectWifi() {
  WiFi.begin(ssid, password);

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    retries++;


    if (retries > 20) {
      return;
    }
  }
}

void saveVideo(KnockMetrics k) {
  uint8_t macBytes[6];
  WiFi.macAddress(macBytes);

  char macStr[13];
  snprintf(macStr, sizeof(macStr),
          "%02X%02X%02X%02X%02X%02X",
          macBytes[5], macBytes[4], macBytes[3],
          macBytes[2], macBytes[1], macBytes[0]);

  String mac = String(macStr);
  
  String body = "{";
  body += "\"device_id\":\"" + mac + "\",";
  body += "\"x\":" + String(k.xAtPeak, 3) + ",";
  body += "\"y\":" + String(k.yAtPeak, 3) + ",";
  body += "\"z\":" + String(k.zAtPeak, 3) + ",";
  body += "\"rms_z\":" + String(k.rms, 3) + ",";
  body += "\"peak_abs_dz\":" + String(k.peakAbsDZ, 3) + ",";
  body += "\"peak_signed_dz\":" + String(k.peakSignedDZ, 3);
  body += "}";

  client.beginRequest();
  client.post("/save");
  client.sendHeader("Content-Type", "application/json");
  client.sendHeader("Content-Length", body.length());
  client.beginBody();
  client.print(body);
  client.endRequest();
}

float calibrateZ() {
  float sum = 0.0;
  const int samples = 50;

  for (int i = 0; i < samples; i++) {
    sensors_event_t event;
    accel.getEvent(&event);
    sum += event.acceleration.z;
    delay(20);
  }

  return sum / samples;
}
