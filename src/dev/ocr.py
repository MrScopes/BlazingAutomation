import json
import time
from datetime import datetime

import cv2
import numpy as np

from src.api.driver import Driver
from src.api.capture import ScrcpyHeadlessCapture

def choose_verbosity():
    print("\n=== LIVE OCR VERBOSITY ===")
    print("1. Text only (same text as macro; changes only)")
    print("2. Text + confidence")
    print("3. Detailed (confidence + box center)")
    print("4. Raw RapidOCR (full polygon and confidence)")
    print("Q. Back")
    while True:
        choice = input("Select [1-4] (default 1): ").strip().lower() or "1"
        if choice in ("1", "2", "3", "4"):
            return int(choice)
        if choice in ("q", "quit", "back"):
            return None
        print("Invalid selection")

def clean_number(value):
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, (list, tuple)):
        return [clean_number(v) for v in value]
    return value

def macro_preprocess(frame):
    h, w = frame.shape[:2]
    scale = min(1.0, 1500 / max(h, w))
    return cv2.resize(frame, None, fx=scale, fy=scale) if scale < 1 else frame

def main():
    verbosity = choose_verbosity()
    if verbosity is None:
        return
    driver = Driver()
    live = None
    try:
        driver.find_display()
        print("[OCR] Starting shared headless scrcpy stream...", flush=True)
        live = ScrcpyHeadlessCapture(driver.width, driver.height, display_id=driver.input_display)
        live.start()
        print("[OCR] Ctrl+C to stop. Capture and OCR preprocessing match the macro.", flush=True)
        frame_number = 0
        last_text = None
        while True:
            started = time.monotonic()
            frame = live.get()
            result = driver.reader.detect(frame)
            texts = getattr(result, "txts", None) or []
            boxes = getattr(result, "boxes", None)
            scores = getattr(result, "scores", None)
            detections = []
            for i, value in enumerate(texts):
                polygon = boxes[i].tolist() if boxes is not None else []
                confidence = float(scores[i]) if scores is not None else 0.0
                detections.append((polygon, value, confidence))
            frame_number += 1
            elapsed = time.monotonic() - started
            timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
            if verbosity == 1:
                joined = driver.reader.text(result)
                if joined != last_text:
                    print(f"\n[OCR {frame_number}] {timestamp} ({elapsed:.2f}s)\n{joined or '(no text)'}", flush=True)
                    last_text = joined
                continue
            print(f"\n[OCR FRAME {frame_number}] {timestamp} elapsed={elapsed:.2f}s detections={len(detections)}", flush=True)
            for i, (polygon, value, confidence) in enumerate(detections, 1):
                if verbosity == 2:
                    print(f"  {i:03d} [{confidence:.1%}] {value}", flush=True)
                elif verbosity == 3:
                    center_x = round(sum(float(point[0]) for point in polygon) / len(polygon)) if polygon else 0
                    center_y = round(sum(float(point[1]) for point in polygon) / len(polygon)) if polygon else 0
                    print(f"  {i:03d} [{confidence:.1%}] OCR-center=({center_x},{center_y}) {value}", flush=True)
                else:
                    print("  " + json.dumps({"index": i, "polygon": clean_number(polygon), "text": value, "confidence": confidence}, ensure_ascii=False), flush=True)
            if not detections:
                print("  (no text detected)", flush=True)
    except KeyboardInterrupt:
        print("\n[OCR] Stopped", flush=True)
    finally:
        if live is not None:
            live.close()

if __name__ == "__main__":
    main()
