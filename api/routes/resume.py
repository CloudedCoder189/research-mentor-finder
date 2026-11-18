"""Authenticated parsing preview; files/text are not persisted or sent to AI."""
import base64
import json
import subprocess
import sys
import threading

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from api.auth.dependencies import AuthenticatedUser, require_user_and_csrf
from api.resume_parser import MAX_BYTES
from runtime_config import PROJECT_ROOT

router = APIRouter(prefix="/api/profile", tags=["profile"])
slots = threading.BoundedSemaphore(2)


class ResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_user_id: str = Field(max_length=300)
    kind: str = Field(max_length=10)
    content: str = Field(max_length=700000)


@router.post("/resume-preview")
def preview(payload: ResumeRequest, user: AuthenticatedUser = Depends(require_user_and_csrf)):
    if payload.expected_user_id != user.user_id:
        raise HTTPException(409, "The signed-in account changed. Choose the file again.")
    if payload.kind not in {"pdf", "docx", "txt"}:
        raise HTTPException(422, "Choose a PDF, DOCX or TXT résumé.")
    try:
        size = len(base64.b64decode(payload.content, validate=True))
    except ValueError:
        raise HTTPException(422, "The file could not be read.") from None
    if not 0 < size <= MAX_BYTES:
        raise HTTPException(422, "Choose a nonempty file no larger than 512 KB.")
    if not slots.acquire(blocking=False):
        raise HTTPException(503, "Résumé processing is busy. Please try again shortly.")
    try:
        run = subprocess.run([sys.executable, "-m", "api.resume_worker"],
            input=json.dumps({"kind": payload.kind, "content": payload.content}),
            capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=8)
        if run.returncode:
            raise HTTPException(422, "This file is too complex to process. Export a text résumé instead.")
        result = json.loads(run.stdout)
        if "error" in result:
            raise HTTPException(422, result["error"])
        return result
    except subprocess.TimeoutExpired:
        raise HTTPException(422, "Processing took too long. Export a text résumé instead.") from None
    except (OSError, json.JSONDecodeError):
        raise HTTPException(503, "Résumé processing is unavailable. Please try again shortly.") from None
    finally:
        slots.release()
