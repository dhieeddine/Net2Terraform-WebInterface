# Net2Terraform 🚀

**Net2Terraform** converts network designs into AWS Terraform (`main.tf`) using either images or conversational input.

1.  **🖼️ Image Topology**: Convert a photo or scan of a network diagram using computer vision (YOLOv8 + OCR).
2.  **💬 Architecture Chat**: Describe your network in natural language through an interactive AI-powered conversation (LLM + RAG).

---

## 🎯 Goal

The project removes manual Terraform drafting for common network topologies. Users can upload a topology diagram or describe an architecture and receive generated Terraform with deployment workflows.

Best suited for:
- **Rapid prototyping** from diagrams to IaC.
- **Modernizing legacy documentation** into editable Terraform.
- **Interactive architecture design** with validation prompts.

---

## 🧠 Two Ways to Build

### 1. Image Topology Method (Vision)
Pipeline stages:
- **YOLOv8**: Detects network components (routers, switches, PCs, firewalls).
- **Geometric Analysis**: Identifies cable connections between detected nodes.
- **PaddleOCR + Tesseract**: Both OCR engines are used together to extract labels and device names.
- **Vision LLM synthesis**: Builds Terraform from image + detections + links + OCR hints.

### 2. Architecture Chat Method (Conversational)
Pipeline stages:
- **Natural language extraction**: Structured components and links are extracted through the LLM gateway.
- **Interactive validation**: The assistant identifies missing information (for example, disconnected nodes).
- **RAG (Retrieval-Augmented Generation)**: Uses technical documentation (`rules.pdf`) to guide generation.

---

## 🗺️ Global Pipeline Architecture

```mermaid
flowchart LR
    U[User] --> FE[Frontend UI\nreception.html / index.html / chat.html]
    FE --> API[FastAPI Backend\nbackend/app/main.py]

    API --> A1[/api/analyze]
    API --> G1[/api/generate-terraform]
    API --> C1[/api/chat/send]
    API --> D1[/api/deploy]

    subgraph VisionPipeline[Vision Pipeline]
        IMG[Uploaded Network Diagram] --> YOLO[YOLO Service\nobject detection]
        YOLO --> VISION[Vision Service\nlink detection]
        YOLO --> OCR[OCR Service\nlabel extraction]
        VISION --> G1
        OCR --> G1
        YOLO --> G1
        G1 --> OR[OpenRouter/Oxlo via LLM Gateway\nTerraform synthesis from image + hints]
    end

    subgraph ChatPipeline[Conversational Pipeline]
        CHAT[User Architecture Description] --> CHATSRV[Chat Service]
        CHATSRV --> LLMTXT[Gemini/OpenRouter/Oxlo via LLM Gateway\nJSON extraction + validation]
        CHATSRV --> RAG[RAG Layer\nrules.pdf chunking + FAISS + BM25 + reranking]
        RAG --> CHATSRV
        LLMTXT --> CHATSRV
        CHATSRV --> TFCHAT[Terraform code from structured architecture]
        C1 --> CHATSRV
    end

    OR --> TF[Generated main.tf]
    TFCHAT --> TF

    TF --> D1
    D1 --> TFSVC[Terraform Service\nworkspace + terraform init/apply/destroy]
    TFSVC --> AWS[AWS Resources\nVPC / Subnets / EC2 / Routing]
    TFSVC --> STATE[Job Logs + Parsed State\n/api/deploy/{job_id}/logs, /state]
```

---


## 📂 Project Structure

```text
webInterface/
├── .env
├── .gitignore
├── README.md
├── backend/
│   ├── requirements.txt
│   ├── gpu_requirements.txt
│   ├── best.pt                  # YOLO model weights
│   ├── rules.pdf                # [Optional] Context for the RAG chat method
│   └── app/
│       ├── main.py              # FastAPI bootstrap & router mounting
│       ├── core/
│       │   └── config.py        # Environment + runtime settings
│       ├── routes/
│       │   ├── analyze.py       # Image analysis endpoints
│       │   ├── chat.py          # Conversational/RAG endpoints
│       │   ├── deploy.py        # AWS Deployment orchestration
│       │   └── health.py        # Health check
│       └── services/
│           ├── chat_service.py      # RAG + architecture extraction + validation
│           ├── llm_gateway.py       # Provider routing/fallback for LLM calls
│           ├── openrouter_service.py# Vision->Terraform prompt orchestration
│           ├── ocr_service.py       # PaddleOCR + Tesseract label extraction
│           ├── terraform_service.py # Terraform CLI job/workspace manager
│           ├── vision_service.py    # Geometric link detection
│           └── yolo_service.py      # Object detection
├── Dockerfile
├── docker-compose.yml
└── frontend/
    ├── reception.html           # Main landing page (Method selector)
    ├── index.html               # Image method interface
    ├── chat.html                # Conversational method interface
    ├── app.js                   # Logic for image method
    ├── chat.js                  # Logic for chat method
    └── styles.css               # Shared glass-morphic design system
```

## 🛠️ Prerequisites

1.  **Python 3.10+**
2.  **API Keys** (at least one configured provider per workflow):
    - **Google Gemini API Key** (optional, for chat/text provider)
    - **OpenRouter API Key** (optional, for vision/text provider)
    - **Oxlo API Key** (optional, for vision/text provider)
3.  **YOLO weights**: `best.pt` file in the `backend/` directory.
4.  **Hardware**: CPU works; GPU is optional and used when available.

## ⚙️ Environment Configuration

Edit `.env` at the project root:

```env
# AI & ML
GOOGLE_API_KEY=your_gemini_api_key
OPENROUTER_API_KEY=your_openrouter_api_key
OXLO_API_KEY=your_oxlo_api_key
YOLO_WEIGHTS=backend/best.pt
RULES_PDF_PATH=backend/rules.pdf

# Provider order / failover
CHAT_LLM_PROVIDERS=google,openrouter,oxlo
VISION_LLM_PROVIDERS=openrouter,oxlo

# AWS Credentials (for Deployment)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_DEFAULT_REGION=us-east-1

# Server Config
PORT=8000
```

## 🚀 Getting Started

### 1. Install Dependencies
```powershell
# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install backend requirements
pip install -r backend/requirements.txt
```

### 2. Run the Application
```powershell
# Start FastAPI backend
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Usage
Open `http://localhost:8000/` (or `http://localhost:8000/reception.html`) to choose your preferred method.

### 4. Optional GPU dependencies
If you want GPU OCR/inference support, install:

```powershell
pip install -r backend/gpu_requirements.txt
```

---

## 🐳 Run With Docker

This repository now includes a production-style container setup for the FastAPI service.

### 1. Build and Start
```powershell
docker compose up --build
```

### 2. Open the App
- Health check: `http://localhost:8000/api/health`
- Root status endpoint: `http://localhost:8000/`

If a `frontend` directory exists in the project root, static pages are also served by FastAPI (for example, `http://localhost:8000/reception.html`).

### 3. Stop
```powershell
docker compose down
```

Notes:
- The compose file forces Linux-compatible OCR path: `TESSERACT_CMD=/usr/bin/tesseract`.
- Terraform CLI is installed inside the container for `/api/deploy` endpoints.
- `backend/deployments` is mounted as a volume to persist deployment workspaces/logs.

---

## 🔌 API Documentation

### Conversational Method (Chat)
- `POST /api/chat/send`: Sends user message, returns assistant response and current architecture state.
- `POST /api/chat/reset`: Resets the conversational session.

### Vision Method (Image)
- `POST /api/analyze`: Runs YOLO + link detection + OCR and returns detections, links, OCR names, and an annotated image.
- `POST /api/generate-terraform`: Generates Terraform from image + detected hints + optional OCR name overrides.

### Deployment Service
- `POST /api/deploy`: Submits a Terraform code payload for AWS deployment.
- `GET /api/deploy/jobs`: Lists known deployment jobs.
- `GET /api/deploy/{job_id}`: Returns job status and metadata.
- `GET /api/deploy/{job_id}/logs`: Fetches real-time execution logs.
- `GET /api/deploy/{job_id}/state`: Retrieves parsed resource information from the deployment.
- `POST /api/deploy/{job_id}/destroy`: Triggers infrastructure teardown.

---

## 📝 Notes
- **RAG Capability**: Place a `rules.pdf` at `backend/rules.pdf` (or set `RULES_PDF_PATH`) to improve chat-grounded generation.
- **Glass-Morphic Design**: The frontend utilizes a shared modern CSS design system for a premium user experience across all modules.
- **Security**: AWS credentials and API keys are strictly managed via environment variables.
