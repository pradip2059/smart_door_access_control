"""Generate face encodings from images stored under dataset/<person_name>/."""

import argparse
import os
import pickle

import cv2
import face_recognition
from imutils import paths


def train(dataset_dir: str, output_file: str) -> None:
    image_paths = list(paths.list_images(dataset_dir))
    known_encodings = []
    known_names = []

    print(f"[INFO] Found {len(image_paths)} training image(s).")

    for index, image_path in enumerate(image_paths, start=1):
        name = os.path.basename(os.path.dirname(image_path))
        print(f"[INFO] Processing {index}/{len(image_paths)}: {image_path}")

        image = cv2.imread(image_path)
        if image is None:
            print(f"[WARN] Could not read image; skipping: {image_path}")
            continue

        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        boxes = face_recognition.face_locations(rgb, model="hog")
        encodings = face_recognition.face_encodings(rgb, boxes)

        if not encodings:
            print(f"[WARN] No face detected; skipping: {image_path}")
            continue

        for encoding in encodings:
            known_encodings.append(encoding)
            known_names.append(name)

    if not known_encodings:
        raise RuntimeError("No face encodings were generated. Check the dataset images.")

    data = {"encodings": known_encodings, "names": known_names}
    with open(output_file, "wb") as file:
        pickle.dump(data, file)

    print(
        f"[INFO] Training complete: {len(known_encodings)} encoding(s) "
        f"saved to {output_file}"
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Train facial-recognition encodings.")
    parser.add_argument("--dataset", default="dataset", help="Dataset directory.")
    parser.add_argument("--output", default="encodings.pickle", help="Output pickle file.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    train(args.dataset, args.output)
