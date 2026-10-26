import os
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
        return self.text(self.detect(frame))
