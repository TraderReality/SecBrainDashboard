import io
import json

import pytest

from excalidraw_generator.ollama import OllamaError, request_scene


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def test_request_uses_bounded_json_protocol(monkeypatch):
    import excalidraw_generator.ollama as ollama
    captured = {}

    def fake_open(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response(json.dumps({"done": True, "done_reason": "stop",
                                    "message": {"content": '{"elements":[]}'}}).encode())

    monkeypatch.setattr(ollama, "urlopen", fake_open)
    assert request_scene("http://127.0.0.1:11434", "local", [{"role": "user", "content": "draw"}]) == '{"elements":[]}'
    body = json.loads(captured["request"].data)
    assert captured["timeout"] == 120
    assert body["stream"] is False and body["think"] is False
    assert captured["request"].full_url.endswith("/api/chat")


@pytest.mark.parametrize("done,reason", [(False, "stop"), (True, "length"), (None, None)])
def test_incomplete_response_rejected(monkeypatch, done, reason):
    import excalidraw_generator.ollama as ollama
    payload = {"done": done, "done_reason": reason, "message": {"content": '{"elements":[]}'}}
    monkeypatch.setattr(ollama, "urlopen", lambda *_args, **_kwargs: Response(json.dumps(payload).encode()))
    with pytest.raises(OllamaError):
        request_scene("http://127.0.0.1:11434", "local", [])
