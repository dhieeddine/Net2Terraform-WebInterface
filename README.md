# Net2Terraform 🚀

**Net2Terraform** is an intelligent automation tool that bridges the gap between manual network design and Infrastructure as Code (IaC). It offers two powerful methods to generate ready-to-deploy AWS Terraform configurations:

1.  **🖼️ Image Topology**: Convert a photo or scan of a network diagram using computer vision (YOLOv8 + OCR).
2.  **💬 Architecture Chat**: Describe your network in natural language through an interactive AI-powered conversation (Gemini + RAG).

---

## 🎯 The Goal

The primary objective of this project is to **eliminate the manual overhead** of translating visual or conceptual network designs into cloud infrastructure. Instead of manually writing VPCs, subnets, instances, and routing tables, users can simply upload a diagram or describe their intent to receive a functional `main.tf` file in seconds.

This tool is ideal for:
- **Rapid Prototyping**: Moving from a whiteboard sketch to a cloud environment instantly.
- **Legacy Documentation**: Converting old network diagrams into modern IaC.
- **Interactive Design**: Building complex architectures through a guided conversational agent.

---

## 🧠 Two Ways to Build

### 1. Image Topology Method (Vision)
Uses a multi-stage pipeline combining **Computer Vision**, **Topological Analysis**, and **LLMs**:
- **YOLOv8**: Detects network components (routers, switches, PCs, firewalls).
- **Geometric Analysis**: Identifies cable connections between detected nodes.
- **PaddleOCR**: Extracts labels and device names directly from the image.
- **LLM Refinement**: Translates the detected graph into optimized Terraform code.

### 2. Architecture Chat Method (Conversational)
Provides a guided dialogue to specify infrastructure requirements:
- **Natural Language Extraction**: Gemini extracts structured components and links from user text.
- **Interactive Validation**: The assistant identifies missing information (e.g., disconnected nodes) and asks clarifying questions.
- **RAG (Retrieval-Augmented Generation)**: Uses technical documentation (like `rules.pdf`) to ensure configurations meet specific best practices.
- **Automated IP Addressing**: Implements VLSM logic to calculate subnets and CIDRs automatically.

---

## 📂 Project Structure

```text
webInterface/
├── .env
├── .gitignore
├── README.md
├── rules.pdf                    # [Optional] Context for the RAG chat method
├── backend/
│   ├── requirements.txt
│   ├── best.pt                  # YOLO model weights
│   └── app/
│       ├── main.py              # FastAPI bootstrap & router mounting
│       ├── routes/
│       │   ├── analyze.py       # Image analysis endpoints
│       │   ├── chat.py          # Conversational/RAG endpoints
│       │   ├── deploy.py        # AWS Deployment orchestration
│       │   └── health.py        # Health check
│       └── services/
│           ├── chat_service.py  # Gemini + RAG logic
│           ├── deploy_service.py# Terraform CLI wrapper
│           ├── vision_service.py# Geometric link detection
│           └── yolo_service.py  # Object detection
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
2.  **API Keys**:
    - **Google Gemini API Key** (for Chat/RAG method)
    - **OpenRouter API Key** (for Image method LLM)
3.  **YOLO weights**: `best.pt` file in the `backend/` directory.
4.  **Hardware**: CPU or GPU (Sentence-transformers and YOLO will utilize CUDA if available).

## ⚙️ Environment Configuration

Edit `.env` at the project root:

```env
# AI & ML
GOOGLE_API_KEY=your_gemini_api_key
OPENROUTER_API_KEY=your_openrouter_api_key
YOLO_WEIGHTS=backend/best.pt

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

# Serve frontend (in a separate terminal)
python -m http.server 5173 --directory frontend
```

### 3. Usage
Open `http://localhost:5173/reception.html` to choose your preferred method.

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
- `POST /api/analyze`: Orchestrates YOLO, Vision, and LLM services to return a topology JSON + main.tf.
- `POST /api/generate-terraform`: Specific endpoint for iterative LLM refinement of detected topologies.

### Deployment Service
- `POST /api/deploy`: Submits a Terraform code payload for AWS deployment.
- `GET /api/deploy/{job_id}/logs`: Fetches real-time execution logs.
- `GET /api/deploy/{job_id}/state`: Retrieves parsed resource information from the deployment.
- `POST /api/deploy/{job_id}/destroy`: Triggers infrastructure teardown.

---

## 📝 Notes
- **RAG Capability**: Place a `rules.pdf` in the root directory to ground the Chat Assistant in specific infrastructure rules.
- **Glass-Morphic Design**: The frontend utilizes a shared modern CSS design system for a premium user experience across all modules.
- **Security**: AWS credentials and API keys are strictly managed via environment variables.
