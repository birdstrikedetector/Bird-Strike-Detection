#include <WiFiNINA.h>
#include <ArduinoHttpClient.h>

WiFiClient wifiClient;

const char* ssid = "AirPennNet-Device";
const char* password = "penn1740wifi";


const char testPing[] = "test.mosquitto.org"; // Arduino Nano pings this address to ensure Wifi is connected

HttpClient client(wifiClient, "10.103.222.105", 80);  // your Pi IP, port

void setup() {
  // put your setup code here, to run once:
  Serial.begin(9600);
  while (!Serial); // Wait for Serial monitor
  Serial.println("Starting...");

  connectWifi();
  long pingResult = WiFi.ping(testPing);
  if (pingResult >= 0) {
    Serial.print("Ping successful! RTT = ");
    Serial.print(pingResult);
    Serial.println(" ms");
  } else {
    Serial.println("Ping failed!");
  }


  getHealth();

}

void loop() {
  // Insert Accelometer Detection Code
  // When accelometer is triggered:
  // delay (10000); this makes it so that the buffer on Raspberry PI 5 includes 20 seconds prior to trigger and 10 seconds after
  //saveVideo();
}

// Connect to WiFi
void connectWifi() {
  Serial.print("Connecting to WiFi: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.print(".");
    retries++;
    if (retries > 20) {
      Serial.println("Failed to connect to WiFi.");
      return;
    }
  }
  Serial.println("\nWiFi connected!");
}

void saveVideo() {
  client.post("/save");
  int statusCode = client.responseStatusCode();
  String response = client.responseBody();

  Serial.print("Status code: ");
  Serial.println(statusCode);

  Serial.print("Response: ");
  Serial.println(response);
}

void getHealth() {
  client.get("/health");

  int statusCode = client.responseStatusCode();
  String response = client.responseBody();

  Serial.print("Status code: ");
  Serial.println(statusCode);

  Serial.print("Response: ");
  Serial.println(response);

  client.stop();
}
