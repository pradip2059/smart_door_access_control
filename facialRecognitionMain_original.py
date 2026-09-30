import face_recognition
import cv2
import numpy as np
from picamera2 import Picamera2
import time
import pickle
from gpiozero import Button, LED, OutputDevice
from RPLCD.gpio import CharLCD
import RPi.GPIO as GPIO

# -----------------------------
# GPIO SETUP
# -----------------------------
START_BUTTON_PIN = 17
STOP_BUTTON_PIN = 27
LED_PIN = 22
LOCK_RELAY_PIN = 5

# LCD pins
LCD_RS = 25
LCD_E = 24
LCD_D4 = 23
LCD_D5 = 18
LCD_D6 = 15
LCD_D7 = 14

start_button = Button(START_BUTTON_PIN, pull_up=True, bounce_time=0.2)
stop_button = Button(STOP_BUTTON_PIN, pull_up=True, bounce_time=0.2)
status_led = LED(LED_PIN)

# Relay for 12V solenoid lock
# CHANGED: active_high=False reverses the relay logic
lock_relay = OutputDevice(LOCK_RELAY_PIN, active_high=False, initial_value=False)

lcd = CharLCD(
    numbering_mode=GPIO.BCM,
    cols=16,
    rows=2,
    pin_rs=LCD_RS,
    pin_e=LCD_E,
    pins_data=[LCD_D4, LCD_D5, LCD_D6, LCD_D7],
    compat_mode=True
)

# -----------------------------
# LOAD FACE ENCODINGS
# -----------------------------
print("[INFO] loading encodings...")
with open("encodings.pickle", "rb") as f:
    data = pickle.loads(f.read())

known_face_encodings = data["encodings"]
known_face_names = data["names"]

# -----------------------------
# CAMERA SETUP
# -----------------------------
picam2 = Picamera2()
picam2.configure(
    picam2.create_preview_configuration(
        main={"format": "XRGB8888", "size": (1280, 720)}
    )
)
picam2.start()
time.sleep(2)

# -----------------------------
# VARIABLES
# -----------------------------
cv_scaler = 4
face_locations = []
face_encodings = []
face_names = []

frame_count = 0
fps_start_time = time.time()
fps = 0.0

recognition_enabled = False
last_lcd_line1 = ""
last_lcd_line2 = ""

# CHANGED: keep lock open for 4 seconds after last recognized face
LOCK_HOLD_TIME = 4
lock_hold_until = 0

# -----------------------------
# LCD FUNCTION
# -----------------------------
def update_lcd(line1, line2):
    global last_lcd_line1, last_lcd_line2

    line1 = line1[:16].ljust(16)
    line2 = line2[:16].ljust(16)

    if line1 == last_lcd_line1 and line2 == last_lcd_line2:
        return

    lcd.clear()
    lcd.cursor_pos = (0, 0)
    lcd.write_string(line1)
    lcd.cursor_pos = (1, 0)
    lcd.write_string(line2)

    last_lcd_line1 = line1
    last_lcd_line2 = line2

# -----------------------------
# BUTTON ACTIONS
# -----------------------------
def start_recognition():
    global recognition_enabled
    recognition_enabled = True
    print("[INFO] recognition started")
    update_lcd("Recognition ON", "Scanning...")
    status_led.off()
    lock_relay.off()

def stop_recognition():
    global recognition_enabled, face_locations, face_encodings, face_names, lock_hold_until
    recognition_enabled = False
    face_locations = []
    face_encodings = []
    face_names = []
    lock_hold_until = 0
    status_led.off()
    lock_relay.off()
    print("[INFO] recognition stopped")
    update_lcd("Recognition OFF", "Press START")

start_button.when_pressed = start_recognition
stop_button.when_pressed = stop_recognition

# -----------------------------
# FACE PROCESSING
# -----------------------------
def process_frame(frame):
    global face_locations, face_encodings, face_names

    resized_frame = cv2.resize(
        frame, (0, 0), fx=(1 / cv_scaler), fy=(1 / cv_scaler)
    )

    rgb_resized_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)

    face_locations = face_recognition.face_locations(rgb_resized_frame)
    face_encodings = face_recognition.face_encodings(
        rgb_resized_frame,
        face_locations,
        model="large"
    )

    face_names = []

    for face_encoding in face_encodings:
        matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
        name = "Unknown"

        face_distances = face_recognition.face_distance(
            known_face_encodings, face_encoding
        )

        if len(face_distances) > 0:
            best_match_index = np.argmin(face_distances)
            if matches[best_match_index]:
                name = known_face_names[best_match_index]

        face_names.append(name)

# -----------------------------
# DRAW RESULTS ON VIDEO
# -----------------------------
def draw_results(frame):
    for (top, right, bottom, left), name in zip(face_locations, face_names):
        top *= cv_scaler
        right *= cv_scaler
        bottom *= cv_scaler
        left *= cv_scaler

        if name == "Unknown":
            color = (0, 0, 255)
            label = "Unknown"
        else:
            color = (0, 255, 0)
            label = name

        cv2.rectangle(frame, (left, top), (right, bottom), color, 3)
        cv2.rectangle(frame, (left - 3, top - 35), (right + 3, top), color, cv2.FILLED)
        cv2.putText(
            frame,
            label,
            (left + 6, top - 8),
            cv2.FONT_HERSHEY_DUPLEX,
            0.8,
            (255, 255, 255),
            1
        )

    return frame

# -----------------------------
# UPDATE LED + LCD + SOLENOID LOCK
# -----------------------------
def update_outputs():
    global lock_hold_until

    if not recognition_enabled:
        status_led.off()
        lock_relay.off()
        update_lcd("Recognition OFF", "Press START")
        return

    recognized_found = any(name != "Unknown" for name in face_names)

    # CHANGED: when a face is recognized, reset the 4-second timer
    if recognized_found:
        lock_hold_until = time.time() + LOCK_HOLD_TIME

        status_led.on()
        lock_relay.on()

        recognized_name = next((name for name in face_names if name != "Unknown"), "User")
        update_lcd("Face:", recognized_name)
        return

    # CHANGED: keep solenoid unlocked until 4 seconds after last recognition
    if time.time() < lock_hold_until:
        status_led.on()
        lock_relay.on()
        update_lcd("Unlocked", "Hold Time")
        return

    status_led.off()
    lock_relay.off()

    if len(face_names) == 0:
        update_lcd("Scanning...", "No Face")
    else:
        update_lcd("Face Status:", "Not Recognized")

# -----------------------------
# FPS
# -----------------------------
def calculate_fps():
    global frame_count, fps_start_time, fps

    frame_count += 1
    elapsed = time.time() - fps_start_time

    if elapsed > 1:
        fps = frame_count / elapsed
        frame_count = 0
        fps_start_time = time.time()

    return fps

# -----------------------------
# INITIAL LCD MESSAGE
# -----------------------------
update_lcd("Recognition OFF", "Press START")

# -----------------------------
# MAIN LOOP
# -----------------------------
try:
    while True:
        frame = picam2.capture_array()

        if recognition_enabled:
            process_frame(frame)
        else:
            face_locations = []
            face_names = []

        display_frame = draw_results(frame)
        update_outputs()
        current_fps = calculate_fps()

        mode_text = "ON" if recognition_enabled else "OFF"

        cv2.putText(
            display_frame,
            f"Recognition: {mode_text}",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 255, 255),
            2
        )

        cv2.putText(
            display_frame,
            f"FPS: {current_fps:.1f}",
            (display_frame.shape[1] - 150, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 255, 0),
            2
        )

        #cv2.imshow("Video", display_frame)

        #if cv2.waitKey(1) & 0xFF == ord("q"):
        #    break

except KeyboardInterrupt:
    print("\n[INFO] stopped by user")

finally:
    status_led.off()
    lock_relay.off()
    lcd.clear()
    lcd.write_string("System Stopped")
    time.sleep(1)
    lcd.clear()
    picam2.stop()