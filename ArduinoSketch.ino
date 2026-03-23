#include <WiFiNINA.h> // Connect to Wifi
#include <ArduinoHttpClient.h> // Used to GET/POST via HTTP 

// Packages used by Carr et al. to connect Accelerometer
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_ADXL345_U.h>

const int ledPin = 13; // LED Indicator
Adafruit_ADXL345_Unified accel = Adafruit_ADXL345_Unified(); // Accelerometer client

const char* ssid = "AirPennNet-Device"; // Wifi username
const char* password = "penn1740wifi"; // Wifi password 

WiFiClient wifiClient; // Stores client for Wifi connection
HttpClient client(wifiClient, "10.103.199.147", 8000);  // your Pi IP, port; Uses the WiFi client to talk to the server running at 10.103.222.105 on port 8000, using HTTP

void setup() {
  connectWifi(); // Calls function to connect to Wifi
  getHealth(); // Test connection with Raspberry PI
  
  saveVideo();
  //pinMode(ledPin, OUTPUT);

  //while(!accel.begin()); // Wait for accelerometer to connect
}

void loop() {
  readAccel(); // Read accelerometer
  //delay(500); // Small delay before the next reading 
}

// read accelerometer, if significant, send message to PI
void readAccel(){
  sensors_event_t event; 
  accel.getEvent(&event);

  // Check if the z-axis value exceeds 0.1
  if (event.acceleration.z > 0.12 || event.acceleration.z < -0.12) {
    // Send alert to Raspberry PI to save buffer
    saveVideo();

    //Flashing Onboard LED
    int count = 0;
    while (count < 6) {
      digitalWrite(ledPin, HIGH);
      delay(300);
      digitalWrite(ledPin, LOW);
      delay(300);
      count++;
    }
    
    delay(60000); // Delay to prevent sending multiple emails for the same thump
  }
}

// Connect to WiFi
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

void saveVideo() {
  client.post("/save");
  int statusCode = client.responseStatusCode();
  String response = client.responseBody();
}

// GET to /health, tests connection with Raspberry PI, print response
void getHealth() {
  client.get("/health");

  int statusCode = client.responseStatusCode();
  String response = client.responseBody();

  client.stop();
}
