from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
from pathlib import Path
import logging

from ..net2tf_v3.extractor import extract_architecture
from ..net2tf_v3.validator import validate_architecture
from ..net2tf_v3.app import compile_prompt

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/chat", tags=["chat"])

class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = "default"

class ChatSession:
    def __init__(self):
        self.history = []
        self.combined_prompt = ""
        self.architecture = {}
        self.validation = {"ready": False, "missing": []}
        self.last_result = None

# Simple in-memory session storage
sessions: Dict[str, ChatSession] = {}

def get_session(session_id: str) -> ChatSession:
    if session_id not in sessions:
        sessions[session_id] = ChatSession()
    return sessions[session_id]

@router.post("/send")
async def send_message(payload: ChatMessage):
    session = get_session(payload.session_id)
    user_msg = payload.message.strip()
    
    if not user_msg:
        raise HTTPException(status_code=400, detail="Empty message")

    try:
        # Update session history
        session.history.append({"role": "user", "content": user_msg})
        if session.combined_prompt:
            session.combined_prompt += "\n" + user_msg
        else:
            session.combined_prompt = user_msg

        # Extract architecture
        arch_model = extract_architecture(session.combined_prompt)
        arch_data = (
            arch_model.model_dump(by_alias=True)
            if hasattr(arch_model, "model_dump")
            else arch_model.dict(by_alias=True) if hasattr(arch_model, "dict") else arch_model
        )
        session.architecture = arch_data

        # Validate
        issues = validate_architecture(arch_model)
        validation = {
            "ready": len(issues) == 0,
            "missing": issues,
        }
        session.validation = validation
        
        response = {
            "status": "waiting",
            "message": "",
            "architecture": arch_data,
            "validation": validation,
            "terraform": None
        }

        if not validation["ready"]:
            response["message"] = "I need some more information: " + "; ".join(validation["missing"])
            session.history.append({"role": "assistant", "content": response["message"]})
        else:
            # Generate Terraform if ready
            repo_root = Path(__file__).resolve().parents[3]
            out_dir = repo_root / "backend" / "deployments" / "chat" / payload.session_id
            out_dir.mkdir(parents=True, exist_ok=True)

            result = compile_prompt(prompt=session.combined_prompt, out_dir=str(out_dir))
            session.last_result = result

            main_tf_path = (out_dir / "main.tf")
            terraform = ""
            if main_tf_path.exists():
                terraform = main_tf_path.read_text(encoding="utf-8")

            response["status"] = "ready"
            response["message"] = "I've analyzed your request and generated the Terraform code below."
            response["terraform"] = terraform
            response["result"] = result
            session.history.append({"role": "assistant", "content": response["message"]})

        return response

    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reset")
async def reset_chat(session_id: str = "default"):
    if session_id in sessions:
        del sessions[session_id]
    return {"status": "ok", "message": "Session reset"}
