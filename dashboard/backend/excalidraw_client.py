"""Bounded Dashboard request to the private Excalidraw worker."""

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class WorkerError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


_NAME = re.compile(r"^diagram-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}\.excalidraw$")
_PREFIXES = ("Local/Work/excalidraw/", "Local/Work/excalidraw-dev/")
WORKER_TIMEOUT_SECONDS = 270  # Worker caps two model attempts at 240 seconds total.


def request_diagram(prompt: str, model: str) -> dict:
    url = os.environ.get("SECBRAIN_EXCALIDRAW_WORKER_URL", "").rstrip("/")
    token = os.environ.get("SECBRAIN_EXCALIDRAW_TOKEN", "")
    if not url.startswith("http://") or not token:
        raise WorkerError("worker_unavailable")
    data = json.dumps({"prompt": prompt, "model": model}).encode("utf-8")
    request = Request(url + "/generate", data=data, method="POST",
                      headers={"Content-Type": "application/json", "X-Worker-Token": token})
    try:
        with urlopen(request, timeout=WORKER_TIMEOUT_SECONDS) as response:
            body = response.read(4097)
    except HTTPError as exc:
        if exc.code == 422:
            raise WorkerError("invalid_scene") from exc
        if exc.code == 429:
            raise WorkerError("worker_busy") from exc
        raise WorkerError("worker_unavailable") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise WorkerError("worker_unavailable") from exc
    if len(body) > 4096:
        raise WorkerError("invalid_worker_response")
    try:
        result = json.loads(body)
        filename = result["filename"]
        relative_path = result["relative_path"]
        count = result["element_count"]
        result_model = result["model"]
    except (ValueError, KeyError, TypeError) as exc:
        raise WorkerError("invalid_worker_response") from exc
    if (not isinstance(filename, str) or not _NAME.fullmatch(filename)
            or not isinstance(relative_path, str)
            or not any(relative_path == prefix + filename for prefix in _PREFIXES)
            or isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 80
            or result_model != model):
        raise WorkerError("invalid_worker_response")
    return {"filename": filename, "relative_path": relative_path,
            "element_count": count, "model": result_model}
