import base64
import json
import logging
from io import BytesIO
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from PIL import Image

from ..services.openrouter_service import call_openrouter
from ..services.ocr_service import extract_object_names
from ..services.vision_service import detect_links_from_image, draw_links, draw_ocr_labels
from ..services.yolo_service import extract_nodes, run_yolo_inference

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/api", tags=["analyze"])


@router.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
) -> dict[str, Any]:
    logger.info("[ANALYZE] Received request file=%s content_type=%s", file.filename, file.content_type)
    
    if not file.content_type or file.content_type.lower() not in {"image/png", "image/jpeg", "image/jpg"}:
        logger.warning(f"Invalid file type: {file.content_type}")
        raise HTTPException(status_code=400, detail="Only PNG/JPG images are supported.")

    image_bytes = await file.read()
    if not image_bytes:
        logger.warning("Uploaded file is empty")
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    logger.info(f"File size: {len(image_bytes)} bytes")
    
    try:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        logger.info(f"Image loaded successfully: {image.size}")
    except Exception as exc:
        logger.error(f"Failed to load image: {str(exc)}")
        raise HTTPException(status_code=400, detail="Invalid image file.") from exc

    logger.info("Starting YOLO inference...")
    result = run_yolo_inference(image)
    nodes_data = extract_nodes(result)
    
    logger.info(f"YOLO detected {len(nodes_data['detections'])} component types: {nodes_data['detections']}")
    logger.info(f"Found {len(nodes_data['node_boxes'])} nodes")
    confidence_entries = [
        f"{item['node_id']}={item['confidence']:.3f}"
        for item in nodes_data.get("detection_details", [])
    ]
    if confidence_entries:
        logger.info("YOLO object confidences: %s", ", ".join(confidence_entries))

    logger.info("Detecting topology links...")
    links = detect_links_from_image(image, nodes_data["node_boxes"])
    logger.info(f"Detected {len(links)} connections: {links}")

    logger.info("Running OCR for detected object labels...")
    ocr_names = extract_object_names(
        image=image,
        detection_details=nodes_data.get("detection_details", []),
    )

    if ocr_names:
        logger.info("OCR extracted names: %s", ", ".join(f"{k}={v}" for k, v in ocr_names.items()))
    else:
        logger.info("OCR extracted names: none")

    try:
        annotated_np = result.plot()
        annotated_rgb = annotated_np[:, :, ::-1]
        annotated_image = Image.fromarray(annotated_rgb)
        annotated_image = draw_links(annotated_image, links, nodes_data["node_centers"])
        annotated_image = draw_ocr_labels(annotated_image, ocr_names, nodes_data["node_centers"])

        annotated_buffer = BytesIO()
        annotated_image.save(annotated_buffer, format="PNG")
        annotated_b64 = base64.b64encode(annotated_buffer.getvalue()).decode("utf-8")
        logger.info("Annotated image generated successfully")
    except Exception as exc:
        logger.error(f"Failed to encode annotated image: {str(exc)}")
        raise HTTPException(status_code=500, detail=f"Failed to encode annotated image: {exc}") from exc

    response = {
        "detections": nodes_data["detections"],
        "links": [{"from": from_id, "to": to_id} for from_id, to_id in links],
        "ocr_names": ocr_names,
        "annotated_image": annotated_b64,
    }
    
    logger.info("Analyze request completed successfully")
    return response


@router.post("/generate-terraform")
async def generate_terraform(
    file: UploadFile = File(...),
    yolo_hints: str = Form(default="[]"),
    topology_links: str = Form(default="[]"),
    detected_ocr_names: str = Form(default="{}"),
    ocr_name_overrides: str = Form(default="{}"),
) -> dict[str, Any]:
    logger.info("[GENERATE] Received request file=%s", file.filename)

    if not file.content_type or file.content_type.lower() not in {"image/png", "image/jpeg", "image/jpg"}:
        raise HTTPException(status_code=400, detail="Only PNG/JPG images are supported.")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        parsed_hints = json.loads(yolo_hints)
        parsed_links = json.loads(topology_links)
        parsed_detected_names = json.loads(detected_ocr_names)
        parsed_overrides = json.loads(ocr_name_overrides)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload for generation fields") from exc

    hints = [str(item) for item in parsed_hints] if isinstance(parsed_hints, list) else []

    links: list[tuple[str, str]] = []
    if isinstance(parsed_links, list):
        for item in parsed_links:
            if not isinstance(item, dict):
                continue
            from_id = str(item.get("from", "")).strip()
            to_id = str(item.get("to", "")).strip()
            if from_id and to_id:
                links.append((from_id, to_id))

    ocr_names: dict[str, str] = {}
    if isinstance(parsed_detected_names, dict):
        for key, value in parsed_detected_names.items():
            k = str(key).strip()
            v = str(value).strip() if value is not None else ""
            if k and v:
                ocr_names[k] = v[:64]

    if isinstance(parsed_overrides, dict):
        for key, value in parsed_overrides.items():
            k = str(key).strip()
            v = str(value).strip() if value is not None else ""
            if k and v:
                ocr_names[k] = v[:64]

    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    image_for_llm = image
    if image.size[0] > 1024 or image.size[1] > 1024:
        image_for_llm.thumbnail((1024, 1024), Image.Resampling.LANCZOS)

    llm_buffer = BytesIO()
    image_for_llm.save(llm_buffer, format="PNG", optimize=True)
    image_llm_bytes = llm_buffer.getvalue()
    image_b64 = base64.b64encode(image_llm_bytes).decode("utf-8")

    logger.info("[GENERATE] Calling LLM with %d hints, %d links, %d ocr names", len(hints), len(links), len(ocr_names))
    terraform_code = await call_openrouter(
        image_b64=image_b64,
        mime_type=file.content_type,
        yolo_hints=hints,
        topology_links=links,
        node_name_hints=ocr_names,
    )

    return {
        "terraform": terraform_code,
        "ocr_names": ocr_names,
    }
