import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[3]
load_dotenv(dotenv_path=ROOT_DIR / ".env", override=True)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL_NAME = os.getenv("OPENROUTER_MODEL_NAME", "google/gemma-3-4b-it:free")
YOLO_WEIGHTS = os.getenv("YOLO_WEIGHTS", "best.pt")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

OXLO_API_KEY = os.getenv("OXLO_API_KEY", "")
OXLO_URL = os.getenv("OXLO_URL", "https://api.oxlo.ai/v1/chat/completions")
OXLO_MODEL_NAME = os.getenv("OXLO_MODEL_NAME", "gpt-4o-mini")

CHAT_LLM_PROVIDERS = os.getenv("CHAT_LLM_PROVIDERS", "google,openrouter,oxlo")
VISION_LLM_PROVIDERS = os.getenv("VISION_LLM_PROVIDERS", "openrouter,oxlo")

PORT = int(os.getenv("PORT", "8000"))
PADDLEOCR_LANG = os.getenv("PADDLEOCR_LANG", "en")
PADDLEOCR_VERSION = os.getenv("PADDLEOCR_VERSION", "PP-OCRv5")
PADDLEOCR_DEVICE = os.getenv("PADDLEOCR_DEVICE", "")

# AWS credentials — read from .env, passed to Terraform subprocess
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")

# Directory where per-job Terraform workspaces are stored
DEPLOYMENTS_DIR = Path(os.getenv("DEPLOYMENTS_DIR", "backend/deployments"))

_rules_pdf_path = os.getenv("RULES_PDF_PATH", "backend/rules.pdf")
_rules_pdf_path_obj = Path(_rules_pdf_path)
RULES_PDF_PATH = str(
	_rules_pdf_path_obj
	if _rules_pdf_path_obj.is_absolute()
	else (ROOT_DIR / _rules_pdf_path_obj)
)
