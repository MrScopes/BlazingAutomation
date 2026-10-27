import os
import time
import cv2
import onnxruntime as ort
from rapidocr import RapidOCR

class OCR:
    def __init__(self):
        available = ort.get_available_providers()
        requested = os.environ.get("BLAZING_OCR_BACKEND", "auto").lower()
        if requested not in ("auto", "gpu", "cpu"):
            raise ValueError(f"Invalid BLAZING_OCR_BACKEND: {requested}")
        use_dml = requested != "cpu" and "DmlExecutionProvider" in available
        if requested == "gpu" and not use_dml:
            print("[OCR] DirectML unavailable; using CPU", flush=True)
        self.backend = "DirectML" if use_dml else "CPU"
        self.reader = RapidOCR(params={
            "Global.log_level": "ERROR",
            "EngineConfig.onnxruntime.use_dml": use_dml
        })
        print(f"[OCR] RapidOCR ONNX Runtime ({self.backend})", flush=True)
        # testing only: BLAZING_OCR_DELAY_MS=3000 makes every read take 3 seconds longer, like a slow machine
        try:
            self.delay = max(0, int(os.environ.get("BLAZING_OCR_DELAY_MS", "0") or 0)) / 1000
        except ValueError:
            raise ValueError(f"Invalid BLAZING_OCR_DELAY_MS: {os.environ['BLAZING_OCR_DELAY_MS']!r} (use whole milliseconds)")
        if self.delay:
            print(f"[OCR] Test delay: every read takes {self.delay * 1000:.0f} ms longer", flush=True)

    @staticmethod
    def preprocess(frame):
        h, w = frame.shape[:2]
        scale = min(1.0, 1500 / max(h, w))
        return cv2.resize(frame, None, fx=scale, fy=scale) if scale < 1 else frame

    def detect(self, frame):
        return self.reader(self.preprocess(frame))

    @staticmethod
    def text(result):
        return " ".join(str(value) for value in (getattr(result, "txts", None) or []))

    def read(self, frame):
        result = self.detect(frame)
        if self.delay:
            time.sleep(self.delay)
        self.items = self.boxes(result, frame)
        return self.text(result)

    @staticmethod
    def boxes(result, frame):
        h, w = frame.shape[:2]
        scale = min(1.0, 1500 / max(h, w))
        texts = getattr(result, "txts", None) or ()
        boxes = getattr(result, "boxes", None)
        items = []
        if boxes is None:
            return items
        for text, box in zip(texts, boxes):
            try:
                xs = [float(point[0]) for point in box]
                ys = [float(point[1]) for point in box]
                items.append((str(text), sum(xs) / len(xs) / scale, sum(ys) / len(ys) / scale))
            except Exception:
                continue
        return items
