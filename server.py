from pypylon import pylon
import cv2
from collections import deque
import threading
import time
import os
from datetime import datetime

from googleDriveUpload import upload_to_drive

from flask import Flask, request, jsonify

# -------------- CONFIG --------------
BUFFER_SECONDS = 30        # seconds of video history to keep
TARGET_FPS     = 20        # approximate capture FPS
MAX_FRAMES     = BUFFER_SECONDS * TARGET_FPS
VIDEO_DIR      = "videos"

os.makedirs(VIDEO_DIR, exist_ok=True)

# ---- Email Setup ----
SENDER   = "birdstrikedetector@gmail.com"
PASSWORD = "" # ASK JONAH
RECEIVER = "birdstrikedetector@gmail.com"

# -------------- CAMERA SETUP --------------
print("Initializing camera...")
camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateFirstDevice())
camera.Open()

# Set resolution / FPS
camera.Width.Value  = 1920 #max = 2616
camera.Height.Value = 1080 #max = 1960

camera.ExposureTime.SetValue(12000) # 5000 microseconds = 5 miliseconds

camera.AcquisitionFrameRateEnable.Value = True
camera.AcquisitionFrameRate.Value       = TARGET_FPS

converter = pylon.ImageFormatConverter()
converter.OutputPixelFormat   = pylon.PixelType_BGR8packed
converter.OutputBitAlignment  = pylon.OutputBitAlignment_MsbAligned

# -------------- RING BUFFER (JPEG-COMPRESSED) --------------
# Each entry: (timestamp, encoded_jpeg)
frame_buffer    = deque(maxlen=MAX_FRAMES)
buffer_lock     = threading.Lock()
capture_running = True

def camera_capture_loop():
    """Background thread: continuously grab frames into ring buffer."""
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
                ts    = time.time()

                # JPEG-compress to save RAM
                ok, enc = cv2.imencode(".jpg", frame,
                                       [int(cv2.IMWRITE_JPEG_QUALITY), 60])
                if not ok:
                    print("JPEG encode failed")
                else:
                    with buffer_lock:
                        frame_buffer.append((ts, enc))  # store encoded image
            else:
                print("Grab failed:", grab_result.ErrorDescription)

            grab_result.Release()

            # Optional: light throttle if CPU is too high
            # time.sleep(1.0 / TARGET_FPS)

    finally:
        camera.StopGrabbing()
        camera.Close()
        print("Camera capture loop stopped.")

# Start capture thread
capture_thread = threading.Thread(target=camera_capture_loop, daemon=True)
capture_thread.start()

# -------------- FLASK APP --------------
app = Flask(__name__)

@app.route("/save", methods=["POST"])
def save_clip():
    """
    On POST, save the last ~BUFFER_SECONDS of video buffer to a file,
    email it, and return JSON info.
    """
    with buffer_lock:
        frames = list(frame_buffer)

    if not frames:
        return jsonify({"error": "No frames in buffer"}), 400

    # Compute duration and FPS based on timestamps actually in buffer
    t0 = frames[0][0]
    t1 = frames[-1][0]
    duration = t1 - t0 if t1 > t0 else BUFFER_SECONDS
    fps      = len(frames) / duration if duration > 0 else TARGET_FPS

    # Decode first frame to get size
    first_ts, first_enc = frames[0]
    first_frame = cv2.imdecode(first_enc, cv2.IMREAD_COLOR)
    if first_frame is None:
        return jsonify({"error": "Failed to decode first frame"}), 500

    height, width = first_frame.shape[:2]

    # Output file name
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename      = os.path.join(VIDEO_DIR, f"clip_{timestamp_str}.avi")

    print(f"Saving {len(frames)} frames (~{duration:.1f}s) at {fps:.1f} fps to:")
    print(" ", filename)

    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    out    = cv2.VideoWriter(filename, fourcc, fps, (width, height))

    if not out.isOpened():
        print("ERROR: VideoWriter failed to open output file!")
        return jsonify({"error": "VideoWriter failed"}), 500

    # Decode and write each frame
    for ts, enc in frames:
        frame = cv2.imdecode(enc, cv2.IMREAD_COLOR)
        if frame is None:
            print("Warning: failed to decode a frame, skipping")
            continue
        out.write(frame)

    out.release()
    print(f"Saved clip: {filename}  ({len(frames)} frames, ~{duration:.1f}s, {fps:.1f} fps)")

    try:
        # If you have a specific folder, put its ID here:
        # folder_id = "YOUR_FOLDER_ID"
        # file_id = upload_to_drive(filename, folder_id=folder_id)
        file_id = upload_to_drive(filename)
    except Exception as e:
        print("Error uploading to Google Drive:", e)
        return jsonify({
            "status":        "saved_but_upload_failed",
            "file":          filename,
            "frames":        len(frames),
            "duration_sec":  duration,
            "fps":           fps,
            "upload_error":  str(e),
        }), 500

    # Optional: delete video after sending
    # try:
    #     os.remove(file_path)
    #     print(f"🗑️  Deleted video file: {filename}")
    # except Exception as e:
    #     print(f"⚠️  Could not delete file: {e}")

    return jsonify({
        "status":       "ok",
        "file":         filename,
        "frames":       len(frames),
        "duration_sec": duration,
        "fps":          fps,
    }), 200

@app.route("/health", methods=["GET"])
def health():
    """Simple endpoint to check the service is alive."""
    print("ALIVE")
    with buffer_lock:
        n = len(frame_buffer)
    return jsonify({"status": "running", "buffer_frames": n}), 200

# -------------- CLEAN SHUTDOWN --------------
def shutdown():
    global capture_running
    capture_running = False
    capture_thread.join(timeout=2)
    cv2.destroyAllWindows()

if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=8000, debug=False)
    finally:
        shutdown()

