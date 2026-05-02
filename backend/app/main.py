import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .core.config import PORT
from .routes.analyze import router as analyze_router
from .routes.deploy import router as deploy_router
from .routes.health import router as health_router
from .routes.chat import router as chat_router
from .routes.test_evaluation import router as test_evaluation_router

logger = logging.getLogger("uvicorn.error")

ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT_DIR / "frontend"

app = FastAPI(title="Net2Terraform API")

logger.info(f"Initializing Net2Terraform API on port {PORT}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info("CORS middleware enabled")

app.include_router(health_router)
app.include_router(analyze_router)
app.include_router(deploy_router)
app.include_router(chat_router)
app.include_router(test_evaluation_router)

logger.info("All routers registered successfully")

if FRONTEND_DIR.exists():
    @app.get("/", include_in_schema=False)
    async def serve_reception() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "reception.html")

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    logger.info("Frontend static files mounted from %s", FRONTEND_DIR)
else:
    @app.get("/", include_in_schema=False)
    async def serve_api_status() -> dict[str, str]:
        return {
            "status": "ok",
            "message": "Net2Terraform API is running. Frontend directory not found.",
        }

    logger.warning("Frontend directory not found at %s", FRONTEND_DIR)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=PORT,
        reload=True,
    )
