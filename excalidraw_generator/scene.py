"""Validate the small, editable Excalidraw subset emitted by the local model."""

import json
import math

MAX_JSON_BYTES = 256 * 1024
MAX_ELEMENTS = 80
ALLOWED_TYPES = frozenset({"rectangle", "ellipse", "diamond", "arrow", "line", "text"})


class SceneValidationError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _size(value):
    try:
        return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError, RecursionError) as exc:
        raise SceneValidationError("invalid_json") from exc


def validate_scene(raw: str | dict) -> dict:
    if isinstance(raw, str):
        if len(raw.encode("utf-8")) > MAX_JSON_BYTES:
            raise SceneValidationError("oversized_json")
        try:
            source = json.loads(raw)
        except (ValueError, RecursionError) as exc:
            raise SceneValidationError("invalid_json") from exc
    elif isinstance(raw, dict):
        source = raw
    else:
        raise SceneValidationError("invalid_json")
    if _size(source) > MAX_JSON_BYTES:
        raise SceneValidationError("oversized_json")
    if not isinstance(source, dict):
        raise SceneValidationError("invalid_scene")
    if source.get("type", "excalidraw") != "excalidraw" or source.get("version", 2) != 2:
        raise SceneValidationError("invalid_scene")
    if source.get("files") not in (None, {}):
        raise SceneValidationError("files_not_allowed")
    elements = source.get("elements")
    if not isinstance(elements, list):
        raise SceneValidationError("invalid_scene")
    if not elements:
        raise SceneValidationError("invalid_scene")
    if len(elements) > MAX_ELEMENTS:
        raise SceneValidationError("too_many_elements")

    ids = set()
    for element in elements:
        if not isinstance(element, dict):
            raise SceneValidationError("invalid_element")
        element_id = element.get("id")
        if not isinstance(element_id, str) or not element_id:
            raise SceneValidationError("invalid_element")
        if element_id in ids:
            raise SceneValidationError("duplicate_id")
        ids.add(element_id)
        element_type = element.get("type")
        if not isinstance(element_type, str) or element_type not in ALLOWED_TYPES:
            raise SceneValidationError("unsupported_element")
        for key in ("x", "y", "width", "height"):
            value = element.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise SceneValidationError("invalid_coordinate")
        if element_type == "text":
            if not isinstance(element.get("text"), str):
                raise SceneValidationError("invalid_element")
            if len(element["text"]) > 500:
                raise SceneValidationError("oversized_text")

    for element in elements:
        container_id = element.get("containerId")
        if container_id is not None and (not isinstance(container_id, str) or container_id not in ids):
            raise SceneValidationError("invalid_reference")
        bound = element.get("boundElements")
        if bound is not None:
            if not isinstance(bound, list):
                raise SceneValidationError("invalid_reference")
            for reference in bound:
                if (not isinstance(reference, dict) or not isinstance(reference.get("id"), str)
                        or reference["id"] not in ids):
                    raise SceneValidationError("invalid_reference")
        for key in ("startBinding", "endBinding"):
            binding = element.get(key)
            if (binding is not None and (not isinstance(binding, dict)
                                        or not isinstance(binding.get("elementId"), str)
                                        or binding["elementId"] not in ids)):
                raise SceneValidationError("invalid_reference")

    result = {"type": "excalidraw", "version": 2, "elements": elements,
              "appState": {"viewBackgroundColor": "#ffffff"}, "files": {}}
    if _size(result) > MAX_JSON_BYTES:
        raise SceneValidationError("oversized_json")
    return result
