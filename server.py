from pypylon import pylon
import cv2
from collections import deque
import threading
import time
import os
import json
import csv
import uuid
from datetime import datetime

from googleDriveUpload import upload_to_drive

from flask import Flask, request, jsonify, render_template_string, redirect, url_for, send_file

# -------------- CONFIG --------------
BUFFER_SECONDS = 30
TARGET_FPS     = 20
POST_SECONDS   = 10

MAX_FRAMES     = BUFFER_SECONDS * TARGET_FPS
VIDEO_DIR      = "videos"
CSV_FILE       = "../events.csv"

os.makedirs(VIDEO_DIR, exist_ok=True)

CSV_FIELDS = [
    "event_id",
    "timestamp",
    "device_id",
    "x",
    "y",
    "z",
    "rms_z",
    "peak_abs_dz",
    "peak_signed_dz",
    "video_file",
    "drive_file_id",
    "status",
    "outcome",
    "species",
]

STATUS_CHOICES = [
    "confirmed_collision",
    "near_miss",
    "false_positive",
    "unknown",
]

OUTCOME_CHOICES = [
    "flew_away",
    "stunned",
    "injured",
    "fatal",
    "unknown",
]

# -------------- CAMERA SETUP --------------
print("Initializing camera...")
camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateFirstDevice())
camera.Open()

camera.Width.Value  = 1920
camera.Height.Value = 1080
camera.ExposureTime.SetValue(5000)
camera.AcquisitionFrameRateEnable.Value = True
camera.AcquisitionFrameRate.Value       = TARGET_FPS

converter = pylon.ImageFormatConverter()
converter.OutputPixelFormat  = pylon.PixelType_BGR8packed
converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned

# -------------- RING BUFFER --------------
frame_buffer = deque(maxlen=MAX_FRAMES)
buffer_lock  = threading.Lock()
save_lock    = threading.Lock()
csv_lock     = threading.Lock()

capture_running = True

def camera_capture_loop():
    global capture_running

    camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
    print("Camera capture loop started...")

    try:
        while capture_running and camera.IsGrabbing():
            try:
                grab_result = camera.RetrieveResult(1000, pylon.TimeoutHandling_ThrowException)
            except Exception as e:
                print("Error in RetrieveResult:", e)
                continue

            if grab_result.GrabSucceeded():
                image = converter.Convert(grab_result)
                frame = image.GetArray()
                ts = time.time()

                ok, enc = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
                if ok:
                    with buffer_lock:
                        frame_buffer.append((ts, enc))
                else:
                    print("JPEG encode failed")
            else:
                print("Grab failed:", grab_result.ErrorDescription)

            grab_result.Release()

    finally:
        camera.StopGrabbing()
        camera.Close()
        print("Camera capture loop stopped.")

capture_thread = threading.Thread(target=camera_capture_loop, daemon=True)
capture_thread.start()

# -------------- CSV HELPERS --------------
def ensure_csv_exists():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()

def append_event_to_csv(row, csv_file=CSV_FILE):
    ensure_csv_exists()
    normalized = {field: row.get(field, "") for field in CSV_FIELDS}

    with csv_lock:
        with open(csv_file, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writerow(normalized)

def load_events(csv_file=CSV_FILE):
    ensure_csv_exists()
    with csv_lock:
        with open(csv_file, "r", newline="") as f:
            reader = csv.DictReader(f)
            return list(reader)

def save_events(rows, csv_file=CSV_FILE):
    with csv_lock:
        with open(csv_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for row in rows:
                normalized = {field: row.get(field, "") for field in CSV_FIELDS}
                writer.writerow(normalized)

# -------------- FLASK APP --------------
app = Flask(__name__)

REVIEW_TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Bird Collision Review</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 24px; }
    table { border-collapse: collapse; width: 100%; margin-top: 16px; }
    th, td { border: 1px solid #ccc; padding: 8px; vertical-align: top; }
    th { background: #f5f5f5; }
    form { margin: 0; }
    input[type=text], select { width: 100%; padding: 6px; box-sizing: border-box; }
    .topbar { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; }
    .small { color: #666; font-size: 0.9rem; }
    button { padding: 6px 10px; cursor: pointer; }
  </style>
</head>
<body>
  <div class="topbar">
    <h1 style="margin:0;">Bird Collision Review</h1>
    <a href="{{ url_for('download_csv') }}"><button type="button">Download CSV</button></a>
  </div>

  <p class="small">
    Editable fields: status, outcome, species.
  </p>

  <table>
    <thead>
      <tr>
        <th>event_id</th>
        <th>timestamp</th>
        <th>device_id</th>
        <th>x</th>
        <th>y</th>
        <th>z</th>
        <th>rms_z</th>
        <th>peak_abs_dz</th>
        <th>peak_signed_dz</th>
        <th>video_file</th>
        <th>drive_file_id</th>
        <th>status</th>
        <th>outcome</th>
        <th>species</th>
        <th>save</th>
      </tr>
    </thead>
    <tbody>
      {% for row in events %}
      <tr>
        <form method="POST" action="{{ url_for('update_event', event_id=row['event_id']) }}">
          <td>{{ row["event_id"] }}</td>
          <td>{{ row["timestamp"] }}</td>
          <td>{{ row["device_id"] }}</td>
          <td>{{ row["x"] }}</td>
          <td>{{ row["y"] }}</td>
          <td>{{ row["z"] }}</td>
          <td>{{ row["rms_z"] }}</td>
          <td>{{ row["peak_abs_dz"] }}</td>
          <td>{{ row["peak_signed_dz"] }}</td>
          <td>{{ row["video_file"] }}</td>
          <td>{{ row["drive_file_id"] }}</td>

          <td>
            <select name="status">
              {% for choice in status_choices %}
                <option value="{{ choice }}" {% if row["status"] == choice %}selected{% endif %}>{{ choice }}</option>
              {% endfor %}
            </select>
          </td>

          <td>
            <select name="outcome">
              {% for choice in outcome_choices %}
                <option value="{{ choice }}" {% if row["outcome"] == choice %}selected{% endif %}>{{ choice }}</option>
              {% endfor %}
            </select>
          </td>

          <td>
            <input type="text" name="species" value="{{ row['species'] }}">
          </td>

          <td>
            <button type="submit">Save</button>
          </td>
        </form>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</body>
</html>
"""

@app.route("/save", methods=["POST"])
def save_clip():
    if not save_lock.acquire(blocking=False):
        return jsonify({
            "status": "busy",
            "message": "A save is already in progress; ignoring this request."
        }), 429

    try:
        data = request.get_json(silent=True) or {}

        device_id = data.get("device_id", "unknown")
        x = data.get("x", "")
        y = data.get("y", "")
        z = data.get("z", "")
        rms_z = data.get("rms_z", "")
        peak_abs_dz = data.get("peak_abs_dz", "")
        peak_signed_dz = data.get("peak_signed_dz", "")

        time.sleep(POST_SECONDS)

        with buffer_lock:
            frames = list(frame_buffer)

        if not frames:
            return jsonify({"error": "No frames in buffer"}), 400

        t0 = frames[0][0]
        t1 = frames[-1][0]
        duration = t1 - t0 if t1 > t0 else BUFFER_SECONDS
        fps = len(frames) / duration if duration > 0 else TARGET_FPS

        _, first_enc = frames[0]
        first_frame = cv2.imdecode(first_enc, cv2.IMREAD_COLOR)
        if first_frame is None:
            return jsonify({"error": "Failed to decode first frame"}), 500

        height, width = first_frame.shape[:2]

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        event_id = str(uuid.uuid4())[:8]

        safe_device_id = str(device_id).replace(":", "")
        filename = os.path.join(VIDEO_DIR, f"{timestamp_str}_{safe_device_id}_{event_id}.avi")

        metadata_file = filename.replace(".avi", ".json")

        print(f"Saving {len(frames)} frames (~{duration:.1f}s) at {fps:.1f} fps to:")
        print(" ", filename)

        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        out = cv2.VideoWriter(filename, fourcc, fps, (width, height))

        if not out.isOpened():
            print("ERROR: VideoWriter failed to open output file!")
            return jsonify({"error": "VideoWriter failed"}), 500

        for _, enc in frames:
            frame = cv2.imdecode(enc, cv2.IMREAD_COLOR)
            if frame is None:
                print("Warning: failed to decode a frame, skipping")
                continue
            out.write(frame)

        out.release()
        print(f"Saved clip: {filename}")

        drive_file_id = ""
        try:
            drive_file_id = upload_to_drive(filename)
        except Exception as e:
            print("Error uploading video to Google Drive:", e)

        metadata = {
            "event_id": event_id,
            "timestamp": timestamp_str,
            "device_id": device_id,
            "x": x,
            "y": y,
            "z": z,
            "rms_z": rms_z,
            "peak_abs_dz": peak_abs_dz,
            "peak_signed_dz": peak_signed_dz,
            "video_file": filename,
            "drive_file_id": drive_file_id,
            "status": "unknown",
            "outcome": "unknown",
            "species": "",
        }

        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)
        print("Metadata file saved")

        try:
            upload_to_drive(metadata_file)
        except Exception as e:
            print("Error uploading metadata to Google Drive:", e)

        append_event_to_csv(metadata)

        try:
            os.remove(filename)
            print(f"Deleted local video file: {filename}")
        except Exception as e:
            print(f"Could not delete local video file: {e}")

        try:
            os.remove(metadata_file)
            print(f"Deleted local metadata file: {metadata_file}")
        except Exception as e:
            print(f"Could not delete local metadata file: {e}")

        return jsonify({
            "status": "ok",
            "event_id": event_id,
            "file": filename,
            "frames": len(frames),
            "duration_sec": duration,
            "fps": fps,
            "drive_file_id": drive_file_id,
        }), 200

    finally:
        save_lock.release()

@app.route("/health", methods=["GET"])
def health():
    with buffer_lock:
        n = len(frame_buffer)
    return jsonify({"status": "running", "buffer_frames": n}), 200

@app.route("/review", methods=["GET"])
def review():
    events = load_events()
    return render_template_string(
        REVIEW_TEMPLATE,
        events=events,
        status_choices=STATUS_CHOICES,
        outcome_choices=OUTCOME_CHOICES,
    )

@app.route("/update/<event_id>", methods=["POST"])
def update_event(event_id):
    events = load_events()

    new_status = request.form.get("status", "unknown")
    new_outcome = request.form.get("outcome", "unknown")
    new_species = request.form.get("species", "").strip()

    if new_status not in STATUS_CHOICES:
        new_status = "unknown"
    if new_outcome not in OUTCOME_CHOICES:
        new_outcome = "unknown"

    for row in events:
        if row["event_id"] == event_id:
            row["status"] = new_status
            row["outcome"] = new_outcome
            row["species"] = new_species
            break

    save_events(events)
    return redirect(url_for("review"))

@app.route("/download/events.csv", methods=["GET"])
def download_csv():
    ensure_csv_exists()
    return send_file(
        CSV_FILE,
        as_attachment=True,
        download_name="events.csv",
        mimetype="text/csv"
    )

# -------------- CLEAN SHUTDOWN --------------
def shutdown():
    global capture_running
    capture_running = False
    capture_thread.join(timeout=2)
    cv2.destroyAllWindows()

if __name__ == "__main__":
    try:
        ensure_csv_exists()
        app.run(host="0.0.0.0", port=8000, debug=False)
    finally:
        shutdown()
