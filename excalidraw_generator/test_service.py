import json

import pytest

from excalidraw_generator.service import GenerationError, generate_diagram


VALID = json.dumps({"elements": [{"id": "one", "type": "rectangle", "x": 0, "y": 0,
                                  "width": 100, "height": 50}]})


def run(tmp_path, monkeypatch, responses, prompt="Draw a flow", model="gemma4:12b"):
    import excalidraw_generator.service as service
    calls = []

    def fake_request(url, selected_model, messages, timeout=120):
        calls.append((url, selected_model, messages))
        value = responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(service, "request_scene", fake_request)
    result = generate_diagram(prompt, model, "http://192.168.0.116:11434", tmp_path,
                              "Local/Work/excalidraw")
    return result, calls


def test_valid_generation(tmp_path, monkeypatch):
    result, calls = run(tmp_path, monkeypatch, [VALID])
    assert result["model"] == "gemma4:12b"
    assert result["element_count"] == 1
    assert result["relative_path"].startswith("Local/Work/excalidraw/")
    assert len(calls) == 1
    assert "Draw a flow" in calls[0][2][-1]["content"]


@pytest.mark.parametrize("prompt,model,code", [
    ("", "gemma4:12b", "invalid_prompt"), ("x" * 4001, "gemma4:12b", "invalid_prompt"),
    ("draw", "", "missing_model"),
])
def test_bad_input_does_not_write(tmp_path, monkeypatch, prompt, model, code):
    with pytest.raises(GenerationError) as error:
        run(tmp_path, monkeypatch, [VALID], prompt=prompt, model=model)
    assert error.value.code == code
    assert list(tmp_path.iterdir()) == []


def test_retry_has_total_budget_and_never_publishes_after_expiry(tmp_path, monkeypatch):
    import excalidraw_generator.service as service
    clock = [0]
    timeouts = []
    monkeypatch.setattr(service, "monotonic", lambda: clock[0])

    def fake_request(_url, _model, _messages, timeout):
        timeouts.append(timeout)
        clock[0] += 80 if len(timeouts) == 1 else 170
        return "{" if len(timeouts) == 1 else VALID

    monkeypatch.setattr(service, "request_scene", fake_request)
    with pytest.raises(GenerationError) as error:
        generate_diagram("draw", "m", "http://127.0.0.1:11434", tmp_path,
                         "Local/Work/excalidraw")
    assert error.value.code == "model_unavailable"
    assert timeouts == [120, 120]
    assert list(tmp_path.iterdir()) == []


def test_two_slow_attempts_finish_within_budget(tmp_path, monkeypatch):
    import excalidraw_generator.service as service
    clock = [0]
    timeouts = []
    monkeypatch.setattr(service, "monotonic", lambda: clock[0])

    def fake_request(_url, _model, _messages, timeout):
        timeouts.append(timeout)
        clock[0] += 80
        return "{" if len(timeouts) == 1 else VALID

    monkeypatch.setattr(service, "request_scene", fake_request)
    result = generate_diagram("draw", "m", "http://127.0.0.1:11434", tmp_path,
                              "Local/Work/excalidraw")
    assert result["element_count"] == 1
    assert timeouts == [120, 120]


def test_path_like_prompt_not_used_for_filename(tmp_path, monkeypatch):
    result, _ = run(tmp_path, monkeypatch, [VALID], prompt="../secret /etc/passwd")
    assert "secret" not in result["filename"]
    assert "passwd" not in result["relative_path"]


@pytest.mark.parametrize("responses", [
    ["", ""], ["```json\n" + VALID + "\n```"] * 2,
    ["{"] * 2, [" " * (256 * 1024 + 1)] * 2,
])
def test_bad_model_output_never_publishes(tmp_path, monkeypatch, responses):
    with pytest.raises(GenerationError) as error:
        run(tmp_path, monkeypatch, list(responses))
    assert error.value.code == "invalid_scene"
    assert list(tmp_path.iterdir()) == []


def test_retry_once_then_publish(tmp_path, monkeypatch):
    result, calls = run(tmp_path, monkeypatch, ["{", VALID])
    assert result["element_count"] == 1
    assert len(calls) == 2
    assert "invalid_json" in calls[1][2][-1]["content"]


def test_wrong_reference_type_gets_controlled_retry(tmp_path, monkeypatch):
    malformed = json.dumps({"elements": [{"id": "one", "type": "rectangle", "x": 0,
                                          "y": 0, "width": 1, "height": 1,
                                          "boundElements": [{"id": []}]}]})
    result, calls = run(tmp_path, monkeypatch, [malformed, VALID])
    assert result["element_count"] == 1
    assert len(calls) == 2
    assert "invalid_reference" in calls[1][2][-1]["content"]


def test_model_timeout_does_not_write(tmp_path, monkeypatch):
    from excalidraw_generator.ollama import OllamaError
    with pytest.raises(GenerationError) as error:
        run(tmp_path, monkeypatch, [OllamaError("timeout")])
    assert error.value.code == "model_unavailable"
    assert list(tmp_path.iterdir()) == []
