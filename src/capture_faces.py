"""Capture labeled face images using a Raspberry Pi camera.

Usage:
    python3 capture_faces.py --name "Pradip"
"""

import argparse
import os
import time
from datetime import datetime

import cv2
from picamera2 import Picamera2


def create_person_folder(name: str, dataset_dir: str = "dataset") -> str:
    person_folder = os.path.join(dataset_dir, name)
    os.makedirs(person_folder, exist_ok=True)
    return person_folder


def capture_photos(name: str, dataset_dir: str = "dataset") -> None:
    folder = create_person_folder(name, dataset_dir)

    camera = Picamera2()
    camera.configure(
        camera.create_preview_configuration(
            main={"format": "XRGB8888", "size": (640, 480)}
        )
    )
    camera.start()
    time.sleep(2)

    photo_count = 0
    print(f"Capturing photos for {name}. Press SPACE to save an image; Q to quit.")

    try:
        while True:
            frame = camera.capture_array()
            cv2.imshow("Face Capture", frame)
            key = cv2.waitKey(1) & 0xFF

            if key == ord(" "):
                photo_count += 1
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = f"{name}_{timestamp}.jpg"
                filepath = os.path.join(folder, filename)
                cv2.imwrite(filepath, frame)
                print(f"[INFO] Saved {filepath}")

            elif key in (ord("q"), ord("Q")):
                break
    finally:
        cv2.destroyAllWindows()
        camera.stop()

    print(f"[INFO] Capture complete: {photo_count} image(s) saved for {name}.")


def parse_args():
    parser = argparse.ArgumentParser(description="Capture training images for one person.")
    parser.add_argument("--name", required=True, help="Label/name for the person being enrolled.")
    parser.add_argument("--dataset", default="dataset", help="Dataset directory.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    capture_photos(args.name, args.dataset)
