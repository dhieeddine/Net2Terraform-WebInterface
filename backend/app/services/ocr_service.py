import logging
import re
import importlib
from functools import lru_cache
from typing import Any

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from ..core.config import PADDLEOCR_DEVICE, PADDLEOCR_LANG, PADDLEOCR_VERSION, TESSERACT_CMD

logger = logging.getLogger("uvicorn.error")

_ALLOWED_CHARS_RE = re.compile(r"[^a-zA-Z0-9 _.-]+")
_SPACE_RE = re.compile(r"\s+")
_INTERFACE_RE = re.compile(
    r"^(fa\d+|gig\d+/\d+/\d+|gig\d+/\d+|gi\d+/\d+/\d+|gi\d+/\d+|eth\d+|ethernet\d+|port\d+)$",
    re.IGNORECASE,
)
_DEVICE_NAME_RE = re.compile(
    r"^(pc|desktop|router|switch|server|firewall|ap|accesspoint|laptop|printer)[\s_-]*\d{0,3}$",
    re.IGNORECASE,
)
_CLASS_TEXT_RE = re.compile(
    r"^(pc-pt|router-pt|switch-pt|server-pt|desktop|router|switch|pc)$",
    re.IGNORECASE,
)
_LABEL_SEARCH_RE = re.compile(r"\b(pc|router|switch|server|desktop)\s*[-_]*\s*(\d{1,3})\b", re.IGNORECASE)
_CANONICAL_PREFIXES = {
    "pc": "PC",
    "desktop": "PC",
    "router": "Router",
    "switch": "Switch",
    "firewall": "Firewall",
    "server": "Server",
}


def _normalize_ocr_text(raw: str) -> str:
    text = (raw or "").strip()
    text = _ALLOWED_CHARS_RE.sub("", text)
    text = _SPACE_RE.sub(" ", text).strip()
    return text[:64]


def _canonicalize_device_kind(text: str) -> str:
    compact = _normalize_ocr_text(text).replace(" ", "")
    match = re.match(r"^(pc|desktop|router|switch|firewall|server)(?:-pt)?$", compact, re.IGNORECASE)
    if not match:
        return ""
    return _CANONICAL_PREFIXES[match.group(1).lower()]


def _sanitize_device_name(text: str) -> str:
    normalized = _normalize_ocr_text(text)
    if not normalized:
        return ""

    compact = normalized.replace(" ", "")
    if _INTERFACE_RE.match(compact):
        return ""

    class_name = _canonicalize_device_kind(compact)
    if class_name:
        return class_name

    # Keep only clear device-style labels, e.g. PC4, Router3, Switch0.
    compact_lower = compact.lower()
    if _DEVICE_NAME_RE.match(compact_lower):
        return compact

    # Accept generic labels like PC4 or Router12.
    if re.match(r"^(pc|router|switch|server|firewall|desktop)\d{1,3}$", compact_lower):
        return compact

    return ""


def _extract_device_label(text: str) -> str:
    normalized = _normalize_ocr_text(text)
    if not normalized:
        return ""

    direct = _sanitize_device_name(normalized)
    if direct:
        return direct

    compact = normalized.replace(" ", "")
    class_name = _canonicalize_device_kind(compact)
    if class_name:
        return class_name

    match = _LABEL_SEARCH_RE.search(normalized)
    if match:
        return f"{match.group(1).capitalize()}{match.group(2)}"

    match = re.search(r"\b(pc|router|switch|server|desktop)\b.*?(\d{1,3})\b", compact, re.IGNORECASE)
    if match:
        return f"{match.group(1).capitalize()}{match.group(2)}"

    return ""


def _canonicalize_device_label(text: str) -> str:
    normalized = _normalize_ocr_text(text)
    if not normalized:
        return ""

    compact = normalized.replace(" ", "")
    class_name = _canonicalize_device_kind(compact)
    if class_name:
        return class_name

    match = re.match(r"^(pc|desktop|router|switch|firewall|server)(\d{1,3})$", compact, re.IGNORECASE)
    if match:
        return f"{_CANONICAL_PREFIXES[match.group(1).lower()]}{match.group(2)}"

    match = re.match(r"^(pc|desktop|router|switch|firewall|server)\s*[-_]*\s*(\d{1,3})$", normalized, re.IGNORECASE)
    if match:
        return f"{_CANONICAL_PREFIXES[match.group(1).lower()]}{match.group(2)}"

    label = _extract_device_label(normalized)
    if not label:
        return ""

    compact_label = label.replace(" ", "")
    match = re.match(r"^(pc|desktop|router|switch|firewall|server)(\d{1,3})$", compact_label, re.IGNORECASE)
    if match:
        return f"{_CANONICAL_PREFIXES[match.group(1).lower()]}{match.group(2)}"

    return label


def _fallback_label_from_detection(item: dict[str, Any]) -> str:
    node_id = str(item.get("node_id", "")).strip()
    if not node_id:
        return ""

    class_label = _canonicalize_device_kind(str(item.get("label", "")))
    if class_label:
        return class_label

    prefix = node_id.split("_", 1)[0].strip().lower()
    if prefix in _CANONICAL_PREFIXES:
        return _CANONICAL_PREFIXES[prefix]

    return node_id


def _extract_label_from_raw(text: str) -> str:
    normalized = _normalize_ocr_text(text)
    if not normalized:
        return ""

    candidates = [
        _extract_device_label(normalized),
    ]

    compact = normalized.replace(" ", "")
    device_words = ["pc", "router", "switch", "firewall", "server", "desktop"]
    for device in device_words:
        # Match strings like "PC 4", "Router-3", "Desktop3".
        match = re.search(rf"\b{device}\s*[-_]*\s*(\d{{1,3}})\b", normalized, re.IGNORECASE)
        if match:
            candidates.append(f"{device.capitalize()}{match.group(1)}")
        match = re.search(rf"\b{device}(\d{{1,3}})\b", compact, re.IGNORECASE)
        if match:
            candidates.append(f"{device.capitalize()}{match.group(1)}")

    for candidate in candidates:
        if candidate:
            return _canonicalize_device_label(candidate)

    return ""


def _prepare_for_ocr(image: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(image)
    enlarged = gray.resize((max(1, gray.width * 3), max(1, gray.height * 3)), Image.Resampling.LANCZOS)
    contrast = ImageEnhance.Contrast(enlarged).enhance(2.5)
    sharpened = contrast.filter(ImageFilter.SHARPEN)
    binary = sharpened.point(lambda p: 255 if p > 160 else 0)
    return binary


def _prepare_for_paddleocr(image: Image.Image) -> Image.Image:
    rgb = image.convert("RGB")
    enlarged = rgb.resize((max(1, rgb.width * 2), max(1, rgb.height * 2)), Image.Resampling.LANCZOS)
    contrast = ImageEnhance.Contrast(enlarged).enhance(1.4)
    return contrast.filter(ImageFilter.SHARPEN)


@lru_cache(maxsize=1)
def _get_paddleocr_engine() -> Any:
    try:
        paddleocr_module = importlib.import_module("paddleocr")
        PaddleOCR = getattr(paddleocr_module, "PaddleOCR")
    except Exception as exc:
        logger.warning("[OCR] PaddleOCR import failed: %s", exc)
        return None

    kwargs: dict[str, Any] = {
        "lang": PADDLEOCR_LANG or "en",
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
    }
    if PADDLEOCR_VERSION:
        kwargs["ocr_version"] = PADDLEOCR_VERSION
    if PADDLEOCR_DEVICE:
        kwargs["device"] = PADDLEOCR_DEVICE

    try:
        return PaddleOCR(**kwargs)
    except Exception as exc:
        logger.warning("[OCR] PaddleOCR initialization failed: %s", exc)
        return None


def _lookup_result_value(result: Any, key: str, default: Any = None) -> Any:
    if result is None:
        return default

    if isinstance(result, dict):
        return result.get(key, default)

    getter = getattr(result, "get", None)
    if callable(getter):
        try:
            return getter(key, default)
        except Exception:
            pass

    try:
        return result[key]
    except Exception:
        return default


def _extract_paddleocr_lines(prediction: Any) -> list[tuple[str, float]]:
    if not prediction:
        return []

    page = prediction[0] if isinstance(prediction, list) else prediction
    nested_res = getattr(page, "res", None)
    if nested_res is not None and not callable(nested_res):
        page = nested_res

    texts = _lookup_result_value(page, "rec_texts", []) or []
    scores = _lookup_result_value(page, "rec_scores", []) or []

    if not texts:
        text = str(_lookup_result_value(page, "rec_text", "")).strip()
        if text:
            score = _lookup_result_value(page, "rec_score", 0.0) or 0.0
            try:
                return [(text, float(score) * 100.0)]
            except (TypeError, ValueError):
                return [(text, 0.0)]

    lines: list[tuple[str, float]] = []
    for index, text in enumerate(texts):
        normalized = str(text).strip()
        if not normalized:
            continue

        score = 0.0
        if index < len(scores):
            try:
                score = float(scores[index]) * 100.0
            except (TypeError, ValueError):
                score = 0.0

        lines.append((normalized, score))

    return lines


def _paddleocr_best_text(crops: list[tuple[str, Image.Image]]) -> str:
    engine = _get_paddleocr_engine()
    if engine is None:
        return ""

    best_text = ""
    best_score = float("-inf")

    for source, candidate in crops:
        prepared = _prepare_for_paddleocr(candidate)
        try:
            prediction = engine.predict(np.asarray(prepared))
        except Exception as exc:
            logger.debug("[OCR] PaddleOCR failed on crop '%s': %s", source, exc)
            continue

        lines = _extract_paddleocr_lines(prediction)
        if not lines:
            continue

        candidate_texts = [text for text, _ in lines if text]
        candidate_scores = [score for _, score in lines]

        for text, confidence in lines:
            label = _canonicalize_device_label(text) or _extract_label_from_raw(text)
            if not label:
                continue

            score = _score_ocr_text(label, source, confidence)
            if score > best_score:
                best_score = score
                best_text = label

        combined = _extract_label_from_raw(" ".join(candidate_texts))
        if combined:
            mean_conf = sum(candidate_scores) / len(candidate_scores) if candidate_scores else 0.0
            score = _score_ocr_text(combined, source, mean_conf)
            if score > best_score:
                best_score = score
                best_text = combined

    return best_text


def _region_crop(
    image: Image.Image,
    bbox: tuple[float, float, float, float],
    *,
    left_pad: int = 12,
    right_pad: int = 12,
    top_pad: int = 12,
    bottom_pad: int = 12,
) -> Image.Image:
    width, height = image.size
    x1, y1, x2, y2 = bbox

    left = max(0, int(x1) - left_pad)
    top = max(0, int(y1) - top_pad)
    right = min(width, int(x2) + right_pad)
    bottom = min(height, int(y2) + bottom_pad)

    if right <= left:
        right = min(width, left + 1)
    if bottom <= top:
        bottom = min(height, top + 1)

    return image.crop((left, top, right, bottom))


def _band_crop(
    image: Image.Image,
    bbox: tuple[float, float, float, float],
    *,
    x_pad: int = 24,
    y_start_offset: int = 4,
    y_end_offset: int = 90,
) -> Image.Image:
    width, height = image.size
    x1, y1, x2, y2 = bbox

    left = max(0, int(x1) - x_pad)
    right = min(width, int(x2) + x_pad)
    top = max(0, int(y2) + y_start_offset)
    bottom = min(height, int(y2) + y_end_offset)

    if right <= left:
        right = min(width, left + 1)
    if bottom <= top:
        bottom = min(height, top + 1)

    return image.crop((left, top, right, bottom))


def _candidate_crops(
    image: Image.Image,
    bbox: tuple[float, float, float, float],
) -> list[tuple[str, Image.Image]]:
    x1, y1, x2, y2 = bbox
    box_width = max(1, int(x2 - x1))
    box_height = max(1, int(y2 - y1))

    label_band_height = max(28, int(box_height * 0.85))
    label_band_width = max(40, int(box_width * 1.9))

    crops: list[tuple[str, Image.Image]] = []

    # The diagram usually places names below the icon in Packet Tracer-like layouts.
    crops.append((
        "below",
        _band_crop(
            image,
            bbox,
            x_pad=max(32, label_band_width // 2),
            y_start_offset=2,
            y_end_offset=max(80, label_band_height + 70),
        ),
    ))

    # Some diagrams place labels above or centered on the icon.
    crops.append((
        "above",
        _region_crop(
            image,
            bbox,
            left_pad=max(18, label_band_width // 5),
            right_pad=max(18, label_band_width // 5),
            top_pad=label_band_height + 30,
            bottom_pad=0,
        ),
    ))

    # Fallback: a slightly expanded box around the object.
    crops.append((
        "around",
        _region_crop(
            image,
            bbox,
            left_pad=16,
            right_pad=16,
            top_pad=16,
            bottom_pad=16,
        ),
    ))

    # Narrow label strip below the object, where device names usually appear.
    crops.append((
        "label_below",
        _band_crop(
            image,
            bbox,
            x_pad=max(36, box_width // 2),
            y_start_offset=0,
            y_end_offset=max(100, box_height + 120),
        ),
    ))

    return crops


def _score_ocr_text(text: str, source: str, confidence: float) -> float:
    score = confidence
    if not text:
        return score

    normalized = text.lower()
    if any(char.isdigit() for char in normalized):
        score += 18
    if len(normalized) <= 14:
        score += 14
    if len(normalized) <= 8:
        score += 10
    if len(normalized) >= 2:
        score += min(len(normalized), 12)
    if source == "below":
        score += 18
    elif source == "above":
        score += 5
    return score


def _tesseract_best_text(crops: list[tuple[str, Image.Image]]) -> str:
    try:
        import pytesseract  # Local import so API still works if OCR dependency is missing.
    except Exception as exc:
        logger.warning("[OCR] pytesseract import failed: %s", exc)
        return ""

    if TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

    best_text = ""
    best_score = float("-inf")
    configs = [
        "--oem 3 --psm 6 -c preserve_interword_spaces=1",
        "--oem 3 --psm 7 -c preserve_interword_spaces=1",
        "--oem 3 --psm 11 -c preserve_interword_spaces=1",
    ]

    for source, candidate in crops:
        prepared = _prepare_for_ocr(candidate)
        for config in configs:
            try:
                data = pytesseract.image_to_data(prepared, config=config, output_type=pytesseract.Output.DICT)
                raw_text = pytesseract.image_to_string(prepared, config=config)
            except Exception as exc:
                logger.debug("[OCR] failed on candidate crop: %s", exc)
                continue

            candidate_raw_texts = [raw_text]
            words: list[str] = []
            confidences: list[float] = []
            for text, conf_str in zip(data.get("text", []), data.get("conf", []), strict=False):
                normalized = _extract_device_label(str(text))
                if not normalized:
                    continue

                try:
                    conf_value = float(conf_str)
                except (TypeError, ValueError):
                    conf_value = -1.0

                if conf_value < 20:
                    continue

                words.append(normalized)
                confidences.append(conf_value)

            combined = _extract_label_from_raw(" ".join(words))
            if not combined:
                for text_variant in candidate_raw_texts:
                    combined = _extract_label_from_raw(text_variant)
                    if combined:
                        break
            if not combined:
                continue

            mean_conf = sum(confidences) / len(confidences) if confidences else 0.0
            score = _score_ocr_text(combined, source, mean_conf)
            if score > best_score:
                best_score = score
                best_text = combined

        # Last fallback: try the raw OCR text from the best candidate even if tokens were split or noisy.
        try:
            raw_text = pytesseract.image_to_string(prepared, config=configs[0])
        except Exception:
            raw_text = ""
        fallback = _extract_label_from_raw(raw_text)
        if fallback:
            fallback_score = _score_ocr_text(fallback, source, 45.0)
            if fallback_score > best_score:
                best_score = fallback_score
                best_text = fallback

        # Final fallback for the lower band: try a more permissive OCR pass without thresholding.
        if source in {"below", "label_below"}:
            try:
                text_variant = pytesseract.image_to_string(candidate, config="--oem 3 --psm 6")
            except Exception:
                text_variant = ""
            fallback = _extract_label_from_raw(text_variant)
            if fallback:
                fallback_score = _score_ocr_text(fallback, source, 38.0)
                if fallback_score > best_score:
                    best_score = fallback_score
                    best_text = fallback

    return best_text


def _score_final_label(label: str) -> float:
    normalized = _canonicalize_device_label(label) or _normalize_ocr_text(label)
    if not normalized:
        return float("-inf")

    compact = normalized.replace(" ", "")
    score = float(len(compact))

    if any(ch.isdigit() for ch in compact):
        score += 25.0
    if re.match(r"^(PC|Router|Switch|Firewall|Server)\d{1,3}$", compact):
        score += 30.0
    elif re.match(r"^(PC|Router|Switch|Firewall|Server)$", compact):
        score += 15.0

    return score


def _merge_ocr_texts(paddle_text: str, tesseract_text: str) -> str:
    paddle_label = _canonicalize_device_label(paddle_text) if paddle_text else ""
    tesseract_label = _canonicalize_device_label(tesseract_text) if tesseract_text else ""

    if not paddle_label and not tesseract_label:
        return ""
    if paddle_label and not tesseract_label:
        return paddle_label
    if tesseract_label and not paddle_label:
        return tesseract_label

    # If one engine extracts a numbered device and the other only extracts a class,
    # prefer the numbered label since it is usually more specific.
    paddle_has_number = bool(re.search(r"\d", paddle_label))
    tesseract_has_number = bool(re.search(r"\d", tesseract_label))
    if paddle_has_number and not tesseract_has_number:
        return paddle_label
    if tesseract_has_number and not paddle_has_number:
        return tesseract_label

    paddle_score = _score_final_label(paddle_label)
    tesseract_score = _score_final_label(tesseract_label)
    if tesseract_score > paddle_score:
        return tesseract_label
    return paddle_label


def _ocr_best_text(crops: list[tuple[str, Image.Image]]) -> str:
    paddle_text = _paddleocr_best_text(crops)
    tesseract_text = _tesseract_best_text(crops)
    return _merge_ocr_texts(paddle_text, tesseract_text)


def extract_object_names(
    image: Image.Image,
    detection_details: list[dict[str, Any]],
) -> dict[str, str]:
    """Extract likely text labels for detected objects, keyed by node_id."""
    labels_by_node: dict[str, str] = {}

    if not detection_details:
        return labels_by_node

    for item in detection_details:
        node_id = str(item.get("node_id", "")).strip()
        bbox_data = item.get("bbox", {})
        if not node_id:
            continue

        try:
            bbox = (
                float(bbox_data.get("x1", 0.0)),
                float(bbox_data.get("y1", 0.0)),
                float(bbox_data.get("x2", 0.0)),
                float(bbox_data.get("y2", 0.0)),
            )
        except (TypeError, ValueError):
            continue

        crops = _candidate_crops(image, bbox)
        best_text = _ocr_best_text(crops)
        if best_text:
            labels_by_node[node_id] = _canonicalize_device_label(best_text) or best_text
            continue

        fallback_text = _fallback_label_from_detection(item)
        if fallback_text:
            labels_by_node[node_id] = fallback_text

    return labels_by_node
