# Net2Terraform

Net2Terraform converts network diagrams or conversational architecture descriptions into Terraform code and (optionally) deploys it to AWS.

This repository contains a FastAPI backend that exposes both a vision-based pipeline (YOLO + OCR + geometric link detection) and a conversational RAG-enabled pipeline to generate Terraform code. A small static frontend (HTML/JS) is included for demos.

---

## Quick status
- Backend: FastAPI (entry: `backend/app/main.py`)
- Frontend: static files served from `frontend/` when present
- Model weights: `backend/best.pt` (YOLO)
- **NEW**: Test & Evaluation page for RAG/LLM quality assessment (`frontend/test_evaluation.html`)
 - **NEW**: Notebook-parity pipeline under `backend/app/net2tf_v3` wired into chat + test endpoints

---

## Prerequisites
- Python 3.10+
- Docker (optional, recommended for reproducible environment)
- API keys for any LLM providers you plan to use (see `.env` section)

---

## Workspace layout

See the main pieces used by the README:

- Backend API: `backend/app/` (routes, services, config)
- Notebook pipeline: `backend/app/net2tf_v3/` (ported from final-rag.ipynb)
- Requirements: `backend/requirements.txt` and `backend/requirements.docker.txt`
- Frontend static: `frontend/` (reception.html, index.html, chat.html)
- Docker: `Dockerfile`, `docker-compose.yml`
- Knowledge base: `kb/` (markdown files used by the notebook pipeline)

---

## Environment configuration

Create a `.env` file at the project root (next to this README). See [`.env.example`](.env.example) for a complete template with all available variables.

### Required Variables
At least **one** LLM API key is required:
- `GOOGLE_API_KEY` — Google Gemini API
- `OPENROUTER_API_KEY` — OpenRouter API
- `OXLO_API_KEY` — Oxlo API

If you use the notebook-parity pipeline (compile_prompt), also set:
- `GROQ_API_KEY` — Groq API key (required by `backend/app/net2tf_v3`)

### Optional but Recommended (AWS Deployment)
If deploying generated Terraform to AWS:
- `AWS_ACCESS_KEY_ID` — AWS access key
- `AWS_SECRET_ACCESS_KEY` — AWS secret key
- `AWS_DEFAULT_REGION` — AWS region (defaults to `us-east-1`)

### Optional (Most Have Defaults)
- `PORT` — Server port (default: `8000`)
- `YOLO_WEIGHTS` — Path to YOLO model weights (default: `best.pt`)
- `RULES_PDF_PATH` — Path to architecture rules PDF (default: `backend/rules.pdf`)
- `CHAT_LLM_PROVIDERS` — Comma-separated fallback order (default: `google,openrouter,oxlo`)
- `VISION_LLM_PROVIDERS` — Vision model providers (default: `openrouter,oxlo`)
- `TESSERACT_CMD` — Path to tesseract (only if non-standard location)
- `PADDLEOCR_LANG` — OCR language code (default: `en`)
- `PADDLEOCR_DEVICE` — OCR device (auto-detected if not set)

### Quick Start
```powershell
# Copy the example template
copy .env.example .env

# Edit .env with your API keys
notepad .env
```

---

## Install (recommended: virtual environment)

Windows PowerShell (recommended):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
```

If you plan to run inside Docker (CPU image), the image installs the appropriate wheel indexes — use `backend/requirements.docker.txt` inside the Docker build.

GPU / optional heavy dependencies:

```powershell
pip install -r backend/gpu_requirements.txt
```

---

## Run locally (development)

From the project root, run the FastAPI app with uvicorn:

```powershell
# From project root
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

The app exposes the API under `/api/*`. If the `frontend/` directory exists, static pages are mounted and the root (`/`) will serve `reception.html`.

Open the demo pages in a browser:

- Reception / selector: http://localhost:8000/reception.html
- Image method: http://localhost:8000/index.html
- Chat method: http://localhost:8000/chat.html
- Test & Evaluation: http://localhost:8000/test_evaluation.html

If you prefer to serve the frontend separately (development), you can run a simple static server inside the `frontend/` folder:

```powershell
# serve static files on port 8001 for example
cd frontend
python -m http.server 8001
# then open http://localhost:8001/index.html
```

---

## Notebook-parity pipeline (net2tf_v3)

The app includes a port of the notebook pipeline under `backend/app/net2tf_v3`. This path powers:
- `POST /api/chat/send`
- `POST /api/test/run/{test_name}`

The pipeline relies on:
- `kb/` markdown files (knowledge base)
- A Groq API key (`GROQ_API_KEY`)
- Optional Terraform CLI if you want quality checks to pass (fmt/init/validate)

If `kb/` is missing, retrieve it from Kaggle and place it at repo root.

---

## Run with Docker (recommended for reproducible environment)

Build and start with docker-compose (from project root):

```powershell
# build and start
docker compose up --build

# stop and remove
docker compose down
```

Health check endpoint (after container starts):

- `http://localhost:8000/api/health`

Notes about Docker:
- The compose file and Dockerfile are configured to install OCR/Tesseract and Terraform inside the service image. If you encounter CPU/GPU wheel issues, prefer building on a Linux host or using the provided `requirements.docker.txt` settings.

---

## APIs (short summary)

### Image & Chat Methods
- `POST /api/analyze` — analyze uploaded image (YOLO + link detection + OCR)
- `POST /api/generate-terraform` — synthesize Terraform from image + hints
- `POST /api/chat/send` — conversational architecture extraction + RAG
- `POST /api/deploy` — submit Terraform to the deploy/workspace service
- `GET /api/deploy/{job_id}/logs` — fetch logs for a deployment job

### Test & Evaluation (Quality Assurance)
- `GET /api/test/cases` — list all available test cases
- `GET /api/test/cases/{test_name}` — retrieve a specific test case
- `POST /api/test/run/{test_name}` — run a test and evaluate results
- `GET /api/test/summary` — get evaluation summary statistics
- `POST /api/test/reset` — clear evaluation history
- `GET /api/test/health` — check test service status

See `backend/app/routes/` for full route definitions and request/response schemas.

---

## Test & Evaluation Feature

The Test & Evaluation page provides a user-friendly interface to assess RAG and LLM result quality:

### Features
- **Pre-defined Test Cases**: 5 test scenarios covering single router, manual addressing, NAT, peering, and Transit Gateway configurations
- **Automated Testing**: Run test cases with a single click and receive detailed pass/fail results
- **Quality Metrics**: Terraform code validation, connectivity mode verification, and architecture property checks
- **Evaluation Summary**: Track total evaluations, pass rates, and historical results
- **Visual Feedback**: Color-coded results (green=pass, red=fail) with detailed issue reporting

### Test Case Coverage
1. **Single Router (Auto)** — Basic topology with automatic addressing
2. **Single Router (Manual)** — Manual CIDR assignment for single router
3. **Public/Private with NAT** — Multi-subnet with internet gateway and NAT
4. **Two Router Peering** — VPC peering between two routers
5. **Three Router Transit Gateway** — Multi-router connectivity via Transit Gateway

### Accessing Test & Evaluation

From the reception page, click "Test & Evaluation" or navigate directly to:
```
http://localhost:8000/test_evaluation.html
```

The test page communicates with the backend API endpoints under `/api/test/` to run evaluations and collect metrics.

### Running Tests Programmatically

```bash
# Get all test cases
curl http://localhost:8000/api/test/cases

# Run a specific test
curl -X POST http://localhost:8000/api/test/run/01_easy_auto_single_router

# Get evaluation summary
curl http://localhost:8000/api/test/summary
```

---

## Minor clarifications / compatibility notes

- The README has been updated to use Windows PowerShell activation commands by default (the repo is cross-platform).
- The FastAPI entrypoint used here is `backend.app.main:app` (use this with uvicorn from the workspace root).
- Environment variables are read by `backend/app/core/config.py`; place `.env` at the project root so those values are loaded.
- Docker build uses `backend/requirements.docker.txt` which includes the PyTorch extra index for CPU wheels.
- Test evaluation endpoints run the notebook-parity pipeline; ensure `GROQ_API_KEY` is set and `kb/` is present.

If you want, I can also:
- add a `.env.example` file with the variables listed above, or
- create a short `scripts/` folder with convenient run scripts for Windows and bash.

---

## License & attribution
This README does not change licensing. Check repository root for license information.

---

If you want a `.env.example` or a simple `Makefile`/PowerShell script to make local runs even easier, tell me which you prefer and I will add it.
