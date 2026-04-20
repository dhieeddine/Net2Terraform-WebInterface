import cv2
import numpy as np
from PIL import Image, ImageDraw


def point_to_box_distance(px: float, py: float, box: tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = box
    dx = max(x1 - px, 0.0, px - x2)
    dy = max(y1 - py, 0.0, py - y2)
    return (dx * dx + dy * dy) ** 0.5


def nearest_node_for_endpoint(
    point: tuple[float, float],
    node_boxes: dict[str, tuple[float, float, float, float]],
    snap_distance: float,
) -> str | None:
    px, py = point
    best_node: str | None = None
    best_distance = float("inf")

    for node_id, box in node_boxes.items():
        distance = point_to_box_distance(px, py, box)
        if distance < best_distance:
            best_distance = distance
            best_node = node_id

    if best_node is None or best_distance > snap_distance:
        return None
    return best_node


def build_connector_mask(image: Image.Image) -> np.ndarray:
    rgb = np.array(image)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)

    edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 45, 140)

    lower_red_1 = np.array([0, 90, 60], dtype=np.uint8)
    upper_red_1 = np.array([12, 255, 255], dtype=np.uint8)
    lower_red_2 = np.array([168, 90, 60], dtype=np.uint8)
    upper_red_2 = np.array([180, 255, 255], dtype=np.uint8)
    red_mask = cv2.bitwise_or(
        cv2.inRange(hsv, lower_red_1, upper_red_1),
        cv2.inRange(hsv, lower_red_2, upper_red_2),
    )

    connector = cv2.morphologyEx(
        red_mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)),
        iterations=2,
    )
    connector = cv2.dilate(
        connector,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)),
        iterations=1,
    )

    binary = (connector > 0).astype(np.uint8)
    height, width = binary.shape
    min_area = max(20, int(min(height, width) * 0.02))
    max_area = int(height * width * 0.20)

    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    filtered = np.zeros_like(binary, dtype=np.uint8)

    for label_id in range(1, n_labels):
        x = stats[label_id, cv2.CC_STAT_LEFT]
        y = stats[label_id, cv2.CC_STAT_TOP]
        w = stats[label_id, cv2.CC_STAT_WIDTH]
        h = stats[label_id, cv2.CC_STAT_HEIGHT]
        area = stats[label_id, cv2.CC_STAT_AREA]

        touches_border = x <= 0 or y <= 0 or (x + w) >= (width - 1) or (y + h) >= (height - 1)
        if touches_border:
            continue
        if area < min_area or area > max_area:
            continue

        filtered[labels == label_id] = 255

    return filtered


def mask_node_regions(image: Image.Image, node_boxes: dict[str, tuple[float, float, float, float]]) -> np.ndarray:
    rgb = np.array(image).copy()
    height, width = rgb.shape[:2]
    if not node_boxes:
        return rgb

    corner_samples = np.array(
        [
            rgb[0:12, 0:12],
            rgb[0:12, max(0, width - 12):width],
            rgb[max(0, height - 12):height, 0:12],
            rgb[max(0, height - 12):height, max(0, width - 12):width],
        ]
    )
    background = np.median(corner_samples.reshape(-1, 3), axis=0).astype(np.uint8)

    for box in node_boxes.values():
        x1, y1, x2, y2 = box
        margin = max(6, int(min(height, width) * 0.015))
        xi1 = max(0, int(x1) - margin)
        yi1 = max(0, int(y1) - margin)
        xi2 = min(width - 1, int(x2) + margin)
        yi2 = min(height - 1, int(y2) + margin)
        rgb[yi1:yi2 + 1, xi1:xi2 + 1] = background

    return rgb


def build_dark_connector_mask(image: Image.Image, node_boxes: dict[str, tuple[float, float, float, float]]) -> np.ndarray:
    masked_rgb = mask_node_regions(image, node_boxes)
    gray = cv2.cvtColor(masked_rgb, cv2.COLOR_RGB2GRAY)

    dark_mask = cv2.inRange(gray, 0, 95)
    dark_mask = cv2.morphologyEx(
        dark_mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)),
        iterations=2,
    )
    dark_mask = cv2.dilate(
        dark_mask,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)),
        iterations=1,
    )

    binary = (dark_mask > 0).astype(np.uint8)
    height, width = binary.shape
    min_area = max(20, int(min(height, width) * 0.015))
    max_area = int(height * width * 0.15)

    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    filtered = np.zeros_like(binary, dtype=np.uint8)

    for label_id in range(1, n_labels):
        x = stats[label_id, cv2.CC_STAT_LEFT]
        y = stats[label_id, cv2.CC_STAT_TOP]
        w = stats[label_id, cv2.CC_STAT_WIDTH]
        h = stats[label_id, cv2.CC_STAT_HEIGHT]
        area = stats[label_id, cv2.CC_STAT_AREA]

        touches_border = x <= 0 or y <= 0 or (x + w) >= (width - 1) or (y + h) >= (height - 1)
        if touches_border:
            continue
        if area < min_area or area > max_area:
            continue
        if max(w, h) < 10:
            continue

        filtered[labels == label_id] = 255

    return filtered


def labels_touching_box(
    labels: np.ndarray,
    box: tuple[float, float, float, float],
    margin: int,
) -> set[int]:
    height, width = labels.shape
    x1, y1, x2, y2 = box
    xi1 = max(0, int(x1) - margin)
    yi1 = max(0, int(y1) - margin)
    xi2 = min(width - 1, int(x2) + margin)
    yi2 = min(height - 1, int(y2) + margin)

    if xi1 >= xi2 or yi1 >= yi2:
        return set()

    roi = labels[yi1:yi2 + 1, xi1:xi2 + 1]
    touched = np.unique(roi)
    return {int(value) for value in touched if int(value) > 0}


def links_from_connected_components(
    connector_mask: np.ndarray,
    node_boxes: dict[str, tuple[float, float, float, float]],
) -> list[tuple[str, str]]:
    if len(node_boxes) < 2:
        return []

    labels_count, labels = cv2.connectedComponents((connector_mask > 0).astype(np.uint8), connectivity=8)
    if labels_count <= 1:
        return []

    height, width = labels.shape
    box_margin = max(5, int(min(height, width) * 0.012))

    label_to_nodes: dict[int, set[str]] = {}
    for node_id, box in node_boxes.items():
        touched_labels = labels_touching_box(labels, box, margin=box_margin)
        for label_id in touched_labels:
            label_to_nodes.setdefault(label_id, set()).add(node_id)

    link_set: set[tuple[str, str]] = set()
    for nodes in label_to_nodes.values():
        if len(nodes) != 2:
            continue
        node_a, node_b = sorted(nodes)
        link_set.add((node_a, node_b))

    return sorted(link_set)


def detect_links_from_image(
    image: Image.Image,
    node_boxes: dict[str, tuple[float, float, float, float]],
) -> list[tuple[str, str]]:
    if len(node_boxes) < 2:
        return []

    red_connector_mask = build_connector_mask(image)
    dark_connector_mask = build_dark_connector_mask(image, node_boxes)
    component_links = links_from_connected_components(red_connector_mask, node_boxes)
    component_links.extend(links_from_connected_components(dark_connector_mask, node_boxes))

    masked_rgb = mask_node_regions(image, node_boxes)
    gray = cv2.cvtColor(masked_rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 40, 130)
    edges = cv2.morphologyEx(
        edges,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)),
        iterations=1,
    )

    height, width = gray.shape
    min_dim = min(height, width)
    min_line_length = max(18, int(min_dim * 0.045))
    max_line_gap = max(8, int(min_dim * 0.018))
    snap_distance = max(16.0, min_dim * 0.04)

    raw_lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=28,
        minLineLength=min_line_length,
        maxLineGap=max_line_gap,
    )

    hough_links: set[tuple[str, str]] = set()
    if raw_lines is not None:
        for line in raw_lines:
            x1, y1, x2, y2 = line[0]
            node_a = nearest_node_for_endpoint((float(x1), float(y1)), node_boxes, snap_distance)
            node_b = nearest_node_for_endpoint((float(x2), float(y2)), node_boxes, snap_distance)

            if not node_a or not node_b or node_a == node_b:
                continue

            ordered = tuple(sorted((node_a, node_b)))
            hough_links.add(ordered)

    all_links = set(component_links)
    all_links.update(hough_links)

    return sorted(all_links)


def draw_links(
    image: Image.Image,
    links: list[tuple[str, str]],
    node_centers: dict[str, tuple[float, float]],
) -> Image.Image:
    if not links:
        return image

    draw = ImageDraw.Draw(image)
    for from_id, to_id in links:
        if from_id not in node_centers or to_id not in node_centers:
            continue

        x1, y1 = node_centers[from_id]
        x2, y2 = node_centers[to_id]
        draw.line((x1, y1, x2, y2), fill=(0, 255, 0), width=4)
        draw.ellipse((x1 - 4, y1 - 4, x1 + 4, y1 + 4), fill=(0, 255, 0))
        draw.ellipse((x2 - 4, y2 - 4, x2 + 4, y2 + 4), fill=(0, 255, 0))

    return image


def draw_ocr_labels(
    image: Image.Image,
    ocr_names: dict[str, str],
    node_centers: dict[str, tuple[float, float]],
) -> Image.Image:
    if not ocr_names:
        return image

    draw = ImageDraw.Draw(image)
    for node_id, text in ocr_names.items():
        if node_id not in node_centers:
            continue

        label = str(text).strip()
        if not label:
            continue

        x, y = node_centers[node_id]
        tx = int(x + 8)
        ty = int(y - 22)
        # Cyan text with black stroke for strong contrast over YOLO overlays.
        draw.text((tx, ty), label[:40], fill=(0, 255, 255), stroke_fill=(0, 0, 0), stroke_width=2)

    return image
