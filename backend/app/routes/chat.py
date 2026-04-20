from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from ..services.chat_service import chat_service
import logging

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
        arch_data = chat_service.extract_architecture(session.combined_prompt)
        session.architecture = arch_data
        
        # Validate
        validation = chat_service.validate_architecture(arch_data)
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
            terraform = chat_service.generate_terraform(arch_data)
            response["status"] = "ready"
            response["message"] = "I've analyzed your request and generated the Terraform code below."
            response["terraform"] = terraform
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
