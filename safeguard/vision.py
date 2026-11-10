"""Adaptador de visión extraído de la interfaz. No descarga modelos."""

import numpy as np
import time
from threading import Lock
from PIL import ImageDraw
from safeguard.core import SafetyExpertSystem

INFERENCE_LOCK = Lock()

HELMET_COLORS = [
    ([20, 100, 100], [30, 255, 255]),  # yellow
    ([5, 100, 100], [15, 255, 255]),  # orange
    ([0, 100, 100], [10, 255, 255]),  # red1
    ([160, 100, 100], [180, 255, 255]),  # red2
    ([100, 100, 100], [130, 255, 255]),  # blue
    ([0, 0, 200], [180, 30, 255]),  # white
]

VEST_COLORS = [
    ([20, 100, 150], [35, 255, 255]),  # yellow-fl
    ([5, 150, 150], [20, 255, 255]),  # orange-fl
    ([35, 100, 100], [85, 255, 255]),  # lime
]


def _color_pct(region, ranges):
    import cv2

    if region is None or region.size == 0:
        return 0
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    mask = np.zeros(hsv.shape[:2], np.uint8)
    for lo, hi in ranges:
        mask |= cv2.inRange(hsv, np.array(lo), np.array(hi))
    return np.count_nonzero(mask) / (region.shape[0] * region.shape[1])


def enhance_detections(img_bgr, detections):
    enhanced = list(detections)
    persons = [d for d in detections if d["class"] == "person"]
    for p in persons:
        x1, y1, x2, y2 = p["bbox"]
        ph = y2 - y1
        if ph < 4 or x2 <= x1:
            continue
        head = img_bgr[y1 : int(y1 + ph * 0.25), x1:x2]
        torso = img_bgr[int(y1 + ph * 0.25) : int(y1 + ph * 0.75), x1:x2]
        if _color_pct(head, HELMET_COLORS) > 0.15:
            enhanced.append(
                {
                    "class": "helmet",
                    "confidence": 0.70,
                    "inferred": True,
                    "bbox": [x1, y1, x2, int(y1 + ph * 0.25)],
                    "area": (x2 - x1) * int(ph * 0.25),
                }
            )
        if _color_pct(torso, VEST_COLORS) > 0.20:
            enhanced.append(
                {
                    "class": "safety_vest",
                    "confidence": 0.65,
                    "inferred": True,
                    "bbox": [x1, int(y1 + ph * 0.25), x2, int(y1 + ph * 0.75)],
                    "area": (x2 - x1) * int(ph * 0.5),
                }
            )
    return enhanced


def run_detection(image_pil, model, conf, *, imgsz=640, use_color=True):
    import cv2

    img = np.array(image_pil)
    img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    results = model.predict(
        img_bgr,
        conf=conf,
        iou=0.45,
        imgsz=imgsz,
        device="cpu",
        half=False,
        augment=False,
        verbose=False,
        max_det=100,
    )
    dets = []
    for r in results:
        for box in r.boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            dets.append(
                {
                    "class": model.names[int(box.cls[0])].lower(),
                    "confidence": float(box.conf[0]),
                    "bbox": [int(x1), int(y1), int(x2), int(y2)],
                    "area": (x2 - x1) * (y2 - y1),
                    "inferred": False,
                }
            )
    if use_color:
        dets = enhance_detections(img_bgr, dets)
    return dets


def draw_boxes(image_pil, detections, conf):
    image = image_pil.copy()
    draw = ImageDraw.Draw(image)
    for index, d in enumerate(detections):
        if d["confidence"] < conf:
            continue
        color = "#D9B45D" if d.get("inferred") else "#32B6AC"
        box = tuple(d["bbox"])
        draw.rectangle(box, outline=color, width=3)
        label = f"{index} {d['class']} " + (
            "color experimental" if d.get("inferred") else f"{d['confidence']:.2f}"
        )
        draw.text((max(0, box[0]), max(0, box[1] - 14)), label, fill=color)
    return image


def analyze_image(image, model, conf, *, use_color=False, imgsz=640):
    if model is None:
        raise ValueError("No hay modelo autorizado; no se ejecutó inferencia.")
    if imgsz not in (320, 480, 640):
        raise ValueError("Resolución de inferencia fuera de los límites CPU.")
    started = time.perf_counter()
    with INFERENCE_LOCK:
        detections = run_detection(image, model, conf, imgsz=imgsz, use_color=use_color)
    elapsed = time.perf_counter() - started
    result = SafetyExpertSystem().analyze(detections, conf, (image.height, image.width))
    result["configuration"] = {
        "device": "cpu",
        "imgsz": imgsz,
        "threshold": conf,
        "use_color": use_color,
        "max_det": 100,
    }
    result["performance"] = {"detection_seconds_including_wait": elapsed}
    from safeguard.reporting import ppe_scene_rows

    classes = (
        list(model.names.values())
        if isinstance(model.names, dict)
        else list(model.names)
    )
    result["ppe_scene"] = ppe_scene_rows(result, classes)
    return result, draw_boxes(image, detections, conf)
