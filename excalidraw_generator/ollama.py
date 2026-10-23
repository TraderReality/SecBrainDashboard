"""Bounded call to the configured local Ollama service."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OllamaError(RuntimeError):
    pass


def request_scene(url: str, model: str, messages: list[dict], timeout: float = 120) -> str:
    payload = json.dumps({"model": model, "messages": messages, "stream": False,
                          "think": False, "format": "json",
                          "options": {"temperature": 0.2, "num_predict": 8192}}).encode("utf-8")
    request = Request(url.rstrip("/") + "/api/chat", data=payload,
                      headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(512 * 1024 + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise OllamaError("model_unavailable") from exc
    if len(body) > 512 * 1024:
        raise OllamaError("model_response_too_large")
    try:
        result = json.loads(body)
        content = result["message"]["content"]
    except (ValueError, TypeError, KeyError) as exc:
        raise OllamaError("invalid_model_response") from exc
    if result.get("done") is not True or result.get("done_reason") != "stop":
        raise OllamaError("incomplete_model_response")
    if not isinstance(content, str):
        raise OllamaError("invalid_model_response")
    return content
