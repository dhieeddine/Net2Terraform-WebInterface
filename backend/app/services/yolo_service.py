from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from PIL import Image
from ultralytics import YOLO

from ..core.config import YOLO_WEIGHTS


@lru_cache(maxsize=1)
def get_yolo_model() -> YOLO:
    weights_path = Path(YOLO_WEIGHTS)
    if not weights_path.exists():
        raise FileNotFoundError(
            f"YOLO weights not found at '{weights_path}'. Set YOLO_WEIGHTS correctly in .env."
        )
    return YOLO(str(weights_path))


def run_yolo_inference(image: Image.Image) -> Any:
    try:
        model = get_yolo_model()
        results = model.predict(source=image, conf=0.4, verbose=False)
        return results[0]
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"YOLO inference failed: {exc}") from exc


def extract_nodes(result: Any) -> dict[str, Any]:
    detections: list[str] = []
    detected_nodes: list[str] = []
    detection_details: list[dict[str, Any]] = []
    node_centers: dict[str, tuple[float, float]] = {}
    node_boxes: dict[str, tuple[float, float, float, float]] = {}
    class_counts: dict[str, int] = {}

    if result.boxes is not None:
        names = result.names
        for box in result.boxes:
            conf = float(box.conf[0])
            if conf < 0.65:
                continue
            cls_id = int(box.cls[0])
            cls_name = str(names.get(cls_id, cls_id)) if isinstance(names, dict) else str(names[cls_id])
            cls_name = cls_name.lower()
            detections.append(cls_name)

            class_counts[cls_name] = class_counts.get(cls_name, 0) + 1
            node_id = f"{cls_name}_{class_counts[cls_name]}"
            detected_nodes.append(node_id)

            x1, y1, x2, y2 = box.xyxy[0].tolist()
            center_x = (x1 + x2) / 2
            center_y = (y1 + y2) / 2
            node_centers[node_id] = (center_x, center_y)
            node_boxes[node_id] = (x1, y1, x2, y2)
            detection_details.append(
                {
                    "node_id": node_id,
                    "label": cls_name,
                    "confidence": round(conf, 4),
                    "bbox": {
                        "x1": round(x1, 2),
                        "y1": round(y1, 2),
                        "x2": round(x2, 2),
                        "y2": round(y2, 2),
                    },
                }
            )

    unique_detections: list[str] = list(dict.fromkeys(detections))

    return {
        "detections": unique_detections,
        "detected_nodes": detected_nodes,
        "detection_details": detection_details,
        "node_centers": node_centers,
        "node_boxes": node_boxes,
    }
