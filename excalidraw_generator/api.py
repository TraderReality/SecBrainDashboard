"""Private, token-protected generation worker."""

import os
from pathlib import Path
import secrets
import threading

from fastapi import FastAPI, Header, HTTPException

from .service import GenerationError, generate_diagram


app = FastAPI(title="SECBrain Excalidraw Worker", docs_url=None, redoc_url=None,
              openapi_url=None)
_generation_lock = threading.Lock()


@app.get("/healthz")
def healthz():
    configured = bool(os.environ.get("SECBRAIN_EXCALIDRAW_TOKEN"))
    output = Path(os.environ.get("SECBRAIN_EXCALIDRAW_OUTPUT_DIR", "/work/excalidraw"))
    if not configured or not output.is_dir() or output.is_symlink():
        raise HTTPException(status_code=503, detail="not_ready")
    return {"status": "ok"}


@app.post("/generate")
def generate(payload: dict, x_worker_token: str = Header(default="")):
    token = os.environ.get("SECBRAIN_EXCALIDRAW_TOKEN", "")
    if not token:
        raise HTTPException(status_code=503, detail="not_ready")
    if not secrets.compare_digest(x_worker_token, token):
        raise HTTPException(status_code=401, detail="unauthorized")
    prompt = payload.get("prompt")
    model = payload.get("model")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
        raise HTTPException(status_code=422, detail="invalid_prompt")
    if not isinstance(model, str) or not model.strip() or len(model) > 100:
        raise HTTPException(status_code=422, detail="missing_model")
    if not _generation_lock.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="busy")
    try:
        return generate_diagram(
            prompt, model, os.environ.get("SECBRAIN_EXCALIDRAW_OLLAMA_URL", ""),
            Path(os.environ.get("SECBRAIN_EXCALIDRAW_OUTPUT_DIR", "/work/excalidraw")),
            os.environ.get("SECBRAIN_EXCALIDRAW_SHARE_PREFIX", ""))
    except GenerationError as exc:
        status = 503 if exc.code in ("model_unavailable", "output_unavailable") else 422
        raise HTTPException(status_code=status, detail=exc.code) from exc
    finally:
        _generation_lock.release()
