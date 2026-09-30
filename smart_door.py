"""Raspberry Pi facial-recognition smart door controller.

Hardware controlled by this script:
- Pi camera
- Start/stop push buttons
- Status LED
- Relay-controlled 12 V solenoid lock
- 16x2 character LCD
"""

import pickle
import time

import cv2
import face_recognition
import numpy as np
from gpiozero import Button, LED, OutputDevice
from picamera2 import Picamera2
from RPLCD.gpio import CharLCD
import RPi.GPIO as GPIO


# BCM GPIO assignments
START_BUTTON_PIN = 17
STOP_BUTTON_PIN = 27
LED_PIN = 22
LOCK_RELAY_PIN = 5

LCD_RS = 25
LCD_E = 24
LCD_D4 = 23
LCD_D5 = 18
LCD_D6 = 15
LCD_D7 = 14

LOCK_HOLD_TIME = 4
FRAME_SCALE = 4
ENCODINGS_FILE = "encodings.pickle"


start_button = Button(START_BUTTON_PIN, pull_up=True, bounce_time=0.2)
stop_button = Button(STOP_BUTTON_PIN, pull_up=True, bounce_time=0.2)
status_led = LED(LED_PIN)

# active_high=False matches an active-low relay module.
lock_relay = OutputDevice(
    LOCK_RELAY_PIN,
    active_high=False,
    initial_value=False,
)

lcd = CharLCD(
    numbering_mode=GPIO.BCM,
    cols=16,
    rows=2,
    pin_rs=LCD_RS,
    pin_e=LCD_E,
    pins_data=[LCD_D4, LCD_D5, LCD_D6, LCD_D7],
    compat_mode=True,
)


print("[INFO] Loading face encodings...")
with open(ENCODINGS_FILE, "rb") as file:
    data = pickle.load(file)

known_face_encodings = data["encodings"]
known_face_names = data["names"]

camera = Picamera2()
camera.configure(
    camera.create_preview_configuration(
        main={"format": "XRGB8888", "size": (1280, 720)}
    )
)
camera.start()
time.sleep(2)


face_locations = []
face_encodings = []
face_names = []

frame_count = 0
fps_start_time = time.time()
fps = 0.0

recognition_enabled = False
lock_hold_until = 0.0
last_lcd_line1 = ""
last_lcd_line2 = ""


def update_lcd(line1: str, line2: str) -> None:
    global last_lcd_line1, last_lcd_line2

    line1 = line1[:16].ljust(16)
    line2 = line2[:16].ljust(16)

    if (line1, line2) == (last_lcd_line1, last_lcd_line2):
        return

    lcd.clear()
    lcd.cursor_pos = (0, 0)
    lcd.write_string(line1)
    lcd.cursor_pos = (1, 0)
    lcd.write_string(line2)

    last_lcd_line1 = line1
    last_lcd_line2 = line2


def start_recognition() -> None:
    global recognition_enabled
    recognition_enabled = True
    status_led.off()
    lock_relay.off()
    update_lcd("Recognition ON", "Scanning...")
    print("[INFO] Recognition started.")


def stop_recognition() -> None:
    global recognition_enabled, face_locations, face_encodings, face_names
    global lock_hold_until

    recognition_enabled = False
    face_locations = []
    face_encodings = []
    face_names = []
    lock_hold_until = 0.0
    status_led.off()
    lock_relay.off()
    update_lcd("Recognition OFF", "Press START")
    print("[INFO] Recognition stopped.")


start_button.when_pressed = start_recognition
stop_button.when_pressed = stop_recognition


def process_frame(frame) -> None:
    global face_locations, face_encodings, face_names

    resized_frame = cv2.resize(
        frame, (0, 0), fx=(1 / FRAME_SCALE), fy=(1 / FRAME_SCALE)
    )
    rgb_resized_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)

    face_locations = face_recognition.face_locations(rgb_resized_frame)
    face_encodings = face_recognition.face_encodings(
        rgb_resized_frame,
        face_locations,
        model="large",
    )

    face_names = []

    for face_encoding in face_encodings:
        matches = face_recognition.compare_faces(
            known_face_encodings, face_encoding
        )
        name = "Unknown"

        distances = face_recognition.face_distance(
            known_face_encodings, face_encoding
        )

        if len(distances) > 0:
            best_match_index = int(np.argmin(distances))
            if matches[best_match_index]:
                name = known_face_names[best_match_index]

        face_names.append(name)


def draw_results(frame):
    for (top, right, bottom, left), name in zip(face_locations, face_names):
        top *= FRAME_SCALE
        right *= FRAME_SCALE
        bottom *= FRAME_SCALE
        left *= FRAME_SCALE

        color = (0, 0, 255) if name == "Unknown" else (0, 255, 0)

        cv2.rectangle(frame, (left, top), (right, bottom), color, 3)
        cv2.rectangle(
            frame,
            (left - 3, top - 35),
            (right + 3, top),
            color,
            cv2.FILLED,
        )
        cv2.putText(
            frame,
            name,
            (left + 6, top - 8),
            cv2.FONT_HERSHEY_DUPLEX,
            0.8,
            (255, 255, 255),
            1,
        )

    return frame


def update_outputs() -> None:
    global lock_hold_until

    if not recognition_enabled:
        status_led.off()
        lock_relay.off()
        update_lcd("Recognition OFF", "Press START")
        return

    recognized_name = next(
        (name for name in face_names if name != "Unknown"),
        None,
    )

    if recognized_name is not None:
        lock_hold_until = time.time() + LOCK_HOLD_TIME
        status_led.on()
        lock_relay.on()
        update_lcd("Face:", recognized_name)
        return

    if time.time() < lock_hold_until:
        status_led.on()
        lock_relay.on()
        update_lcd("Unlocked", "Hold Time")
        return

    status_led.off()
    lock_relay.off()

    if not face_names:
        update_lcd("Scanning...", "No Face")
    else:
        update_lcd("Face Status:", "Not Recognized")


def calculate_fps() -> float:
    global frame_count, fps_start_time, fps

    frame_count += 1
    elapsed = time.time() - fps_start_time

    if elapsed > 1:
        fps = frame_count / elapsed
        frame_count = 0
        fps_start_time = time.time()

    return fps


def cleanup() -> None:
    status_led.off()
    lock_relay.off()
    lcd.clear()
    lcd.write_string("System Stopped")
    time.sleep(1)
    lcd.clear()
    camera.stop()
    cv2.destroyAllWindows()


update_lcd("Recognition OFF", "Press START")

try:
    while True:
        frame = camera.capture_array()

        if recognition_enabled:
            process_frame(frame)
        else:
            face_locations = []
            face_encodings = []
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
            2,
        )
        cv2.putText(
            display_frame,
            f"FPS: {current_fps:.1f}",
            (display_frame.shape[1] - 150, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 255, 0),
            2,
        )

        # Uncomment for a local video preview:
        # cv2.imshow("Smart Door", display_frame)
        # if cv2.waitKey(1) & 0xFF == ord("q"):
        #     break

except KeyboardInterrupt:
    print("\n[INFO] Stopped by user.")
finally:
    cleanup()
