// Talaria robot firmware: turns an ESP32 + PCA9685 servo robot into a robot Hermes can move.
// Derived from the Caduceus Body firmware. robot_config.h (generated from the robot spec with
// `hermes talaria firmware <robot> <out_dir>`) describes the robot; this file never changes per robot.
//
// HTTP + JSON on port 80 (the same API as `hermes talaria sim`):
//   GET  /info   robot name, joints with ranges and speed limits
//   GET  /state  current angles, what is playing
//   POST /play   {"name", "loops", "easing": "smoothstep"|"linear", "frames": [{"ms", "hold", "joints": {name: deg}}]}
//   POST /pose   {"joints": {name: deg}, "ms"}
//   POST /stop   {"home": bool}
//
// Moves are data, never code. The robot enforces its own limits whatever a request says: every angle
// is clamped to its joint's range and every transition is stretched so no joint exceeds its max_speed.
// Timing is honest: PWM ticks are written directly (the prescale is read once at boot, never per write),
// so a move plays at the timing it was checked at in simulation. Playback is non-blocking, so /stop
// always answers at once.
//
// Libraries (Arduino Library Manager): Adafruit PWM Servo Driver Library, ArduinoJson (v7).
// Board: ESP32 Dev Module (esp32 by Espressif). Copy secrets.example.h to secrets.h and fill it in.

#include <WiFi.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#include <ArduinoJson.h>
#include "robot_config.h"
#include "secrets.h"

#define FIRMWARE_VERSION "talaria-robot/0.1.0"
#define API_VERSION 1
#define MAX_FRAMES 64
#define MAX_JOINTS 16
#define MAX_LOOPS 10
#define MIN_FRAME_MS 20
#define MAX_FRAME_MS 10000
#define MAX_HOLD_MS 10000
#define MAX_BODY_BYTES 16384

static const int NJ = sizeof(JOINTS) / sizeof(JOINTS[0]);
static_assert(sizeof(JOINTS) / sizeof(JOINTS[0]) <= MAX_JOINTS, "at most 16 joints");

WebServer server(80);
Adafruit_PWMServoDriver pwm(PCA9685_ADDR);
float usPerTick = 0;        // microseconds per PCA9685 tick, from the prescale read once at boot

// ─── Motion state ────────────────────────────────────────────────────────────────────────────────

struct Frame {
  uint16_t ms;
  uint16_t hold;
  bool has[MAX_JOINTS];
  float target[MAX_JOINTS];
};

Frame program[MAX_FRAMES];
int programLen = 0;
int programLoops = 1;
bool linearEasing = false;  // false: smoothstep (ease in/out), true: one constant speed per transition
int frameIndex = 0;
int loopIndex = 0;
bool playing = false;
bool holding = false;
unsigned long phaseStart = 0;
unsigned long phaseDuration = 0;
float phaseSpeed = 0;       // deg per ms, linear easing
float pose[MAX_JOINTS];
float startPose[MAX_JOINTS];
float targetPose[MAX_JOINTS];
float writtenPose[MAX_JOINTS];
char moveName[33] = "";
char stopReason[16] = "";
unsigned long bootMillis = 0;

// ─── Helpers ─────────────────────────────────────────────────────────────────────────────────────

float clampf(float v, float lo, float hi) { return v < lo ? lo : (v > hi ? hi : v); }

float smoothstep(float t) {
  t = clampf(t, 0.0f, 1.0f);
  return t * t * (3.0f - 2.0f * t);
}

int jointIndex(const char* name) {
  for (int i = 0; i < NJ; i++) {
    if (strcmp(JOINTS[i].name, name) == 0) return i;
  }
  return -1;
}

void writeServo(int j, float deg) {
  const JointConfig& c = JOINTS[j];
  float us = c.centerUs + (c.invert ? -deg : deg) * c.usPerDeg;
  us = clampf(us, SERVO_MIN_US, SERVO_MAX_US);
  uint16_t ticks = (uint16_t)clampf(us / usPerTick + 0.5f, 0.0f, 4095.0f);
  pwm.setPWM(c.channel, 0, ticks);   // one I2C write, no prescale read
  writtenPose[j] = deg;
}

void writePose(bool force) {
  for (int j = 0; j < NJ; j++) {
    if (force || fabsf(pose[j] - writtenPose[j]) >= 0.05f) writeServo(j, pose[j]);
  }
}

// How long a transition really takes: at least `ms`, and long enough that no joint exceeds max_speed
// on average (the same rule as the simulator's plan_move).
unsigned long transitionMs(const Frame& f) {
  float needed = 0;
  for (int j = 0; j < NJ; j++) {
    if (!f.has[j]) continue;
    float delta = fabsf(f.target[j] - pose[j]);
    float t = delta / JOINTS[j].maxSpeed * 1000.0f;
    if (t > needed) needed = t;
  }
  unsigned long ms = f.ms;
  if ((unsigned long)ceilf(needed) > ms) ms = (unsigned long)ceilf(needed);
  return ms < MIN_FRAME_MS ? MIN_FRAME_MS : ms;
}

void beginFrame(unsigned long now) {
  const Frame& f = program[frameIndex];
  float biggest = 0;
  for (int j = 0; j < NJ; j++) {
    startPose[j] = pose[j];
    targetPose[j] = f.has[j] ? f.target[j] : pose[j];
    float d = fabsf(targetPose[j] - startPose[j]);
    if (d > biggest) biggest = d;
  }
  phaseDuration = transitionMs(f);
  phaseSpeed = phaseDuration ? biggest / (float)phaseDuration : 0;
  holding = false;
  phaseStart = now;
}

void stopMotion(const char* reason) {
  if (playing) strlcpy(stopReason, reason, sizeof(stopReason));
  playing = false;
  programLen = 0;
  moveName[0] = '\0';
}

void startProgram(int loops, const char* name) {
  programLoops = loops < 1 ? 1 : (loops > MAX_LOOPS ? MAX_LOOPS : loops);
  frameIndex = 0;
  loopIndex = 0;
  stopReason[0] = '\0';
  strlcpy(moveName, name ? name : "", sizeof(moveName));
  playing = programLen > 0;
  if (playing) beginFrame(millis());
}

void tickMotion() {
  if (!playing) return;
  unsigned long now = millis();
  // Catch up through every boundary that has passed, so a slow loop never skips a frame.
  for (int guard = 0; guard < 4 * MAX_FRAMES && playing; guard++) {
    unsigned long elapsed = now - phaseStart;
    const Frame& f = program[frameIndex];
    if (!holding) {
      float t = phaseDuration ? (float)elapsed / (float)phaseDuration : 1.0f;
      if (linearEasing) {
        // every moving joint turns at the same speed and stops when it arrives (like smoothMove)
        float step = phaseSpeed * (float)(elapsed < phaseDuration ? elapsed : phaseDuration);
        for (int j = 0; j < NJ; j++) {
          float d = targetPose[j] - startPose[j];
          float m = fabsf(d) < step ? fabsf(d) : step;
          pose[j] = startPose[j] + (d < 0 ? -m : m);
        }
      } else {
        float e = smoothstep(t);
        for (int j = 0; j < NJ; j++) pose[j] = startPose[j] + (targetPose[j] - startPose[j]) * e;
      }
      if (t < 1.0f) break;
      for (int j = 0; j < NJ; j++) pose[j] = targetPose[j];
      holding = true;
      phaseStart += phaseDuration;
      continue;
    }
    if (elapsed < f.hold) break;
    unsigned long boundary = phaseStart + f.hold;
    frameIndex++;
    if (frameIndex >= programLen) {
      frameIndex = 0;
      loopIndex++;
      if (loopIndex >= programLoops) {
        playing = false;
        programLen = 0;
        moveName[0] = '\0';
        break;
      }
    }
    beginFrame(boundary);
  }
  writePose(false);
}

// ─── HTTP ────────────────────────────────────────────────────────────────────────────────────────

void sendJson(int code, JsonDocument& doc) {
  String out;
  serializeJson(doc, out);
  server.send(code, "application/json", out);
}

void sendError(int code, const char* message) {
  JsonDocument doc;
  doc["ok"] = false;
  doc["error"] = message;
  sendJson(code, doc);
}

void sendOk() {
  JsonDocument doc;
  doc["ok"] = true;
  sendJson(200, doc);
}

bool authorized() {
  const char* token = ROBOT_TOKEN;
  size_t n = strlen(token);
  if (n == 0) return true;
  String given = server.header("X-Robot-Token");
  if (given.length() != n) {
    sendError(401, "unauthorized");
    return false;
  }
  uint8_t diff = 0;
  for (size_t i = 0; i < n; i++) diff |= (uint8_t)given[i] ^ (uint8_t)token[i];
  if (diff != 0) {
    sendError(401, "unauthorized");
    return false;
  }
  return true;
}

bool readBody(JsonDocument& doc) {
  String body = server.arg("plain");
  if (body.length() > MAX_BODY_BYTES) {
    sendError(413, "request too large");
    return false;
  }
  DeserializationError err = deserializeJson(doc, body);
  if (err || !doc.is<JsonObject>()) {
    sendError(400, "body must be a JSON object");
    return false;
  }
  return true;
}

// Parse one frame; unknown joints are ignored and angles are clamped to each joint's range.
void parseFrame(JsonObject src, Frame& f) {
  long ms = src["ms"] | 400L;
  long hold = src["hold"] | 0L;
  f.ms = (uint16_t)(ms < MIN_FRAME_MS ? MIN_FRAME_MS : (ms > MAX_FRAME_MS ? MAX_FRAME_MS : ms));
  f.hold = (uint16_t)(hold < 0 ? 0 : (hold > MAX_HOLD_MS ? MAX_HOLD_MS : hold));
  for (int j = 0; j < NJ; j++) f.has[j] = false;
  JsonObject joints = src["joints"].as<JsonObject>();
  if (joints.isNull()) return;
  for (JsonPair kv : joints) {
    int j = jointIndex(kv.key().c_str());
    if (j < 0 || !kv.value().is<float>()) continue;
    f.has[j] = true;
    f.target[j] = clampf(kv.value().as<float>(), JOINTS[j].minDeg, JOINTS[j].maxDeg);
  }
}

void handleInfo() {
  if (!authorized()) return;
  JsonDocument doc;
  doc["ok"] = true;
  doc["name"] = ROBOT_NAME;
  doc["firmware"] = FIRMWARE_VERSION;
  doc["api"] = API_VERSION;
  doc["spec_hash"] = ROBOT_SPEC_HASH;
  doc["simulated"] = false;
  doc["max_frames"] = MAX_FRAMES;
  JsonArray joints = doc["joints"].to<JsonArray>();
  for (int j = 0; j < NJ; j++) {
    JsonObject o = joints.add<JsonObject>();
    o["name"] = JOINTS[j].name;
    o["min"] = JOINTS[j].minDeg;
    o["max"] = JOINTS[j].maxDeg;
    o["home"] = JOINTS[j].homeDeg;
    o["max_speed"] = JOINTS[j].maxSpeed;
  }
  sendJson(200, doc);
}

void handleState() {
  if (!authorized()) return;
  JsonDocument doc;
  doc["ok"] = true;
  JsonObject p = doc["pose"].to<JsonObject>();
  for (int j = 0; j < NJ; j++) p[JOINTS[j].name] = roundf(pose[j] * 100.0f) / 100.0f;
  doc["busy"] = playing;
  if (playing && moveName[0]) doc["move"] = moveName; else doc["move"] = nullptr;
  doc["frame"] = playing ? frameIndex + 1 : 0;
  doc["frames"] = playing ? programLen : 0;
  doc["loop"] = playing ? loopIndex + 1 : 0;
  doc["loops"] = playing ? programLoops : 0;
  float progress = playing && programLen ? (float)(loopIndex * programLen + frameIndex) / (programLen * programLoops) : 0;
  doc["progress"] = roundf(progress * 1000.0f) / 1000.0f;
  if (stopReason[0]) doc["stop_reason"] = stopReason; else doc["stop_reason"] = nullptr;
  doc["uptime_ms"] = millis() - bootMillis;
  doc["rssi"] = WiFi.RSSI();
  sendJson(200, doc);
}

void handlePlay() {
  if (!authorized()) return;
  JsonDocument doc;
  if (!readBody(doc)) return;
  JsonArray frames = doc["frames"].as<JsonArray>();
  if (frames.isNull() || frames.size() == 0) return sendError(400, "frames must be a non-empty list");
  if (frames.size() > MAX_FRAMES) return sendError(400, "too many frames");
  stopMotion("replaced");
  int n = 0;
  for (JsonVariant v : frames) {
    if (!v.is<JsonObject>()) continue;
    parseFrame(v.as<JsonObject>(), program[n++]);
  }
  programLen = n;
  const char* easing = doc["easing"] | "smoothstep";
  linearEasing = strcmp(easing, "linear") == 0;
  int loops = doc["loops"] | 1;
  startProgram(loops, doc["name"] | "");
  JsonDocument out;
  out["ok"] = true;
  out["frames"] = n;
  out["loops"] = programLoops;
  out["easing"] = linearEasing ? "linear" : "smoothstep";
  sendJson(200, out);
}

void handlePose() {
  if (!authorized()) return;
  JsonDocument doc;
  if (!readBody(doc)) return;
  if (!doc["joints"].is<JsonObject>()) return sendError(400, "joints must be an object");
  stopMotion("replaced");
  parseFrame(doc.as<JsonObject>(), program[0]);
  program[0].hold = 0;
  programLen = 1;
  linearEasing = false;
  startProgram(1, "pose");
  sendOk();
}

void handleStop() {
  if (!authorized()) return;
  JsonDocument doc;
  String body = server.arg("plain");
  bool home = false;
  if (body.length() && !deserializeJson(doc, body)) home = doc["home"] | false;
  stopMotion("stopped");
  if (home) {
    Frame& f = program[0];
    f.ms = 600;
    f.hold = 0;
    for (int j = 0; j < NJ; j++) {
      f.has[j] = true;
      f.target[j] = JOINTS[j].homeDeg;
    }
    programLen = 1;
    linearEasing = false;
    startProgram(1, "home");
  }
  writePose(false);
  sendOk();
}

// ─── Setup / loop ────────────────────────────────────────────────────────────────────────────────

unsigned long lastWifiCheck = 0;
bool mdnsStarted = false;

void announceAddress() {
  if (!mdnsStarted && MDNS.begin(ROBOT_HOSTNAME)) {
    MDNS.addService("http", "tcp", 80);
    mdnsStarted = true;
  }
  String ip = "http://" + WiFi.localIP().toString();
  Serial.printf("%s ready at %s (also http://%s.local)\n", ROBOT_NAME, ip.c_str(), ROBOT_HOSTNAME);
  Serial.printf("In Hermes: set the Talaria Bench robot URL to %s\n", ip.c_str());
}

void connectWifi(unsigned long waitMs) {
  WiFi.setHostname(ROBOT_HOSTNAME);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < waitMs) delay(250);
}

void setup() {
  Serial.begin(115200);
  bootMillis = millis();
  Wire.begin(I2C_SDA, I2C_SCL);
  pwm.begin();
#ifdef PCA9685_OSC_HZ
  pwm.setOscillatorFrequency(PCA9685_OSC_HZ);
#endif
  pwm.setPWMFreq(SERVO_FREQ_HZ);
  // One prescale read at boot; every later write is a single setPWM with ticks.
  float osc = pwm.getOscillatorFrequency();
  usPerTick = 1000000.0f * ((float)pwm.readPrescale() + 1.0f) / osc;
  for (int j = 0; j < NJ; j++) {
    pose[j] = JOINTS[j].homeDeg;
    writtenPose[j] = 9999;
  }
  writePose(true);
  connectWifi(20000);

  const char* headers[] = {"X-Robot-Token"};
  server.collectHeaders(headers, 1);
  server.on("/info", HTTP_GET, handleInfo);
  server.on("/state", HTTP_GET, handleState);
  server.on("/play", HTTP_POST, handlePlay);
  server.on("/pose", HTTP_POST, handlePose);
  server.on("/stop", HTTP_POST, handleStop);
  server.onNotFound([]() { sendError(404, "not found"); });
  server.begin();

  if (WiFi.status() == WL_CONNECTED) announceAddress();
  else Serial.println("Wi-Fi not connected yet; retrying in the background.");
}

void loop() {
  server.handleClient();
  tickMotion();
  unsigned long now = millis();
  if (now - lastWifiCheck > 10000) {
    lastWifiCheck = now;
    if (WiFi.status() != WL_CONNECTED) WiFi.reconnect();
    else if (!mdnsStarted) announceAddress();
  }
  delay(2);
}
