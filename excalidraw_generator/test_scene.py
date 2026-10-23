import json
import math

import pytest

from excalidraw_generator.scene import SceneValidationError, validate_scene


def sample():
    return {"elements": [
        {"id": "box", "type": "rectangle", "x": 1, "y": 2, "width": 100, "height": 50,
         "boundElements": [{"id": "label", "type": "text"}]},
        {"id": "label", "type": "text", "x": 3, "y": 4, "width": 50, "height": 20,
         "text": "Hello", "containerId": "box"},
        {"id": "arrow", "type": "arrow", "x": 5, "y": 6, "width": 30, "height": 0,
         "startBinding": {"elementId": "box"}},
    ]}


def test_valid_scene_normalizes_envelope():
    scene = validate_scene(json.dumps(sample()))
    assert scene == {"type": "excalidraw", "version": 2, "elements": sample()["elements"],
                     "appState": {"viewBackgroundColor": "#ffffff"}, "files": {}}


@pytest.mark.parametrize("change,category", [
    (lambda s: s["elements"].append(dict(s["elements"][0])), "duplicate_id"),
    (lambda s: s["elements"][1].update(containerId="missing"), "invalid_reference"),
    (lambda s: s["elements"][0].update(type="image"), "unsupported_element"),
    (lambda s: s["elements"][0].update(x=math.inf), "invalid_coordinate"),
    (lambda s: s["elements"][1].update(text="x" * 501), "oversized_text"),
    (lambda s: s.update(files={"x": "data"}), "files_not_allowed"),
    (lambda s: s["elements"][2].update(endBinding={"elementId": "gone"}), "invalid_reference"),
    (lambda s: s["elements"][0].update(type=[]), "unsupported_element"),
    (lambda s: s["elements"][1].update(containerId=[]), "invalid_reference"),
    (lambda s: s["elements"][0].update(boundElements=[{"id": []}]), "invalid_reference"),
    (lambda s: s["elements"][2].update(startBinding={"elementId": {}}), "invalid_reference"),
])
def test_invalid_scene(change, category):
    scene = sample()
    change(scene)
    with pytest.raises(SceneValidationError) as error:
        validate_scene(scene)
    assert error.value.code == category


@pytest.mark.parametrize("raw,category", [
    ("", "invalid_json"), ("```json\n{}\n```", "invalid_json"),
    (" " * (256 * 1024 + 1), "oversized_json"),
])
def test_invalid_raw_input(raw, category):
    with pytest.raises(SceneValidationError) as error:
        validate_scene(raw)
    assert error.value.code == category


def test_element_limit():
    scene = sample()
    scene["elements"] = [{"id": str(i), "type": "ellipse", "x": 0, "y": 0,
                          "width": 1, "height": 1} for i in range(81)]
    with pytest.raises(SceneValidationError) as error:
        validate_scene(scene)
    assert error.value.code == "too_many_elements"


def test_empty_scene_is_rejected():
    with pytest.raises(SceneValidationError) as error:
        validate_scene({"elements": []})
    assert error.value.code == "invalid_scene"
