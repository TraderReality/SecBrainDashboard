"""Turn a bounded user request into one validated Excalidraw file."""

from pathlib import Path
from time import monotonic

from .ollama import OllamaError, request_scene
from .scene import SceneValidationError, validate_scene
from .storage import StorageError, publish_scene


SYSTEM_PROMPT = """Create an editable Excalidraw version 2 diagram as one pure JSON object.
Return only {"elements": [...]} without Markdown or commentary. Use at most 80 elements.
Allowed element types: rectangle, ellipse, diamond, arrow, line, text.
Every element needs a unique string id and finite numeric x, y, width, height.
Text elements need text of at most 500 characters. Use containerId, boundElements,
startBinding and endBinding only when their referenced element IDs exist.
Keep labels short and legible. Never include images, files, external links or scripts.
Do not choose a filename or output path. The server handles the destination."""
GENERATION_BUDGET_SECONDS = 240
ATTEMPT_TIMEOUT_SECONDS = 120


class GenerationError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def generate_diagram(prompt: str, model: str, ollama_url: str,
                     output_dir: Path, share_prefix: str) -> dict:
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
        raise GenerationError("invalid_prompt")
    if not isinstance(model, str) or not model.strip() or len(model) > 100:
        raise GenerationError("missing_model")
    if not isinstance(ollama_url, str) or not ollama_url.startswith("http://"):
        raise GenerationError("model_unavailable")

    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt.strip()}]
    deadline = monotonic() + GENERATION_BUDGET_SECONDS
    for attempt in range(2):
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise GenerationError("model_unavailable")
        try:
            raw = request_scene(ollama_url, model, messages,
                                timeout=min(ATTEMPT_TIMEOUT_SECONDS, remaining))
        except OllamaError as exc:
            raise GenerationError("model_unavailable") from exc
        if monotonic() >= deadline:
            raise GenerationError("model_unavailable")
        try:
            scene = validate_scene(raw)
        except SceneValidationError as exc:
            if attempt == 1:
                raise GenerationError("invalid_scene") from exc
            messages.append({"role": "user", "content":
                             f"Your JSON failed validation ({exc.code}). Return a corrected pure JSON scene."})
            continue
        try:
            result = publish_scene(scene, output_dir, share_prefix)
        except StorageError as exc:
            raise GenerationError("output_unavailable") from exc
        return {**result, "model": model}
    raise GenerationError("invalid_scene")
