"""
SECBrain Watcher
Ollama Connector

Zentrale Kommunikation zwischen SECBrain Backend und Ollama.
"""

from __future__ import annotations

import json
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class OllamaConnector:

    def __init__(
        self,
        url: str = "http://127.0.0.1:11434",
        state_path: str | Path | None = None,
    ):

        self.url = url.rstrip("/")

        self.timeout = 5

        self.state_path = Path(state_path).expanduser() if state_path else self._default_state_path()
        persisted = self._load_persisted_config()
        default_model = str(persisted.get("default_model") or "").strip()
        default_vision_model = str(persisted.get("default_vision_model") or "").strip()

        self.config = {
            "url": self.url,
            "model": default_model,
            "default_model": default_model,
            "default_vision_model": default_vision_model,
            "health_interval": 5,
            "keep_alive": "5m",
            "temperature": 0.2,
            "context": 8192,
            "num_predict": 2048,
            "auto_sync": True,
        }


    @staticmethod
    def _default_state_path() -> Path:

        configured = os.environ.get("SECBRAIN_WATCHER_STATE_DIR", "").strip()
        root = Path(configured).expanduser() if configured else Path.home() / ".local/state/secbrain-watcher"
        return root / "ollama-config.json"


    def _load_persisted_config(self) -> dict[str, Any]:

        try:
            if self.state_path.is_file():
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            pass

        return {}


    def _persist_default_model(self) -> None:

        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".ollama-config.",
            dir=self.state_path.parent,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "default_model": self.config.get("default_model", ""),
                        "default_vision_model": self.config.get("default_vision_model", ""),
                    },
                    handle,
                    ensure_ascii=False,
                    indent=2,
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self.state_path)
        finally:
            Path(temporary_name).unlink(missing_ok=True)


    # ========================================================
    # CONFIG
    # ========================================================

    def configure(self, data: dict[str, Any]):

        if "url" in data:

            url = str(data["url"]).strip()

            if url:

                self.url = url.rstrip("/")

                self.config["url"] = self.url


        for key in (
            "model",
            "health_interval",
            "keep_alive",
            "temperature",
            "context",
            "num_predict",
            "auto_sync",
        ):

            if key in data:

                self.config[key] = data[key]


        if "default_model" in data:

            default_model = str(data["default_model"] or "").strip()
            self.config["default_model"] = default_model
            if default_model:
                self.config["model"] = default_model
            self._persist_default_model()


        if "default_vision_model" in data:

            self.config["default_vision_model"] = str(
                data["default_vision_model"] or ""
            ).strip()
            self._persist_default_model()


        return self.config


    def get_config(self):

        return dict(self.config)


    # ========================================================
    # HTTP
    # ========================================================

    def _request(
        self,
        endpoint: str,
        method: str = "GET",
        payload: dict | None = None,
        timeout: int | None = None,
    ):

        url = self.url + endpoint

        data = None

        headers = {
            "Accept": "application/json",
        }


        if payload is not None:

            data = json.dumps(
                payload
            ).encode("utf-8")

            headers["Content-Type"] = (
                "application/json"
            )


        request = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method=method,
        )


        with urllib.request.urlopen(
            request,
            timeout=timeout or self.timeout,
        ) as response:

            raw = response.read()

            if not raw:

                return {}


            return json.loads(
                raw.decode("utf-8")
            )


    # ========================================================
    # HEALTH
    # ========================================================

    def health(self):

        try:

            response = self._request(
                "/api/tags",
                timeout=3,
            )

            models = response.get(
                "models",
                []
            )


            return {
                "online": True,
                "status": "online",
                "url": self.url,
                "models": models,
                "model_count": len(models),
            }


        except Exception as exc:

            return {
                "online": False,
                "status": "offline",
                "url": self.url,
                "models": [],
                "model_count": 0,
                "error": str(exc),
            }


    # ========================================================
    # MODELS
    # ========================================================

    def models(self):

        result = self._request(
            "/api/tags"
        )

        return result.get(
            "models",
            []
        )


    # ========================================================
    # VERSION
    # ========================================================

    def version(self):

        try:

            result = self._request(
                "/api/version"
            )

            return result

        except Exception as exc:

            return {
                "error": str(exc)
            }


    # ========================================================
    # STATUS
    # ========================================================

    def status(self):

        health = self.health()

        version = self.version()

        selected_model = (
            self.config.get("model")
            or ""
        )


        return {

            "status":
                health.get(
                    "status",
                    "offline"
                ),

            "online":
                health.get(
                    "online",
                    False
                ),

            "url":
                self.url,

            "model":
                selected_model,

            "models":
                health.get(
                    "models",
                    []
                ),

            "model_count":
                health.get(
                    "model_count",
                    0
                ),

            "version":
                version.get(
                    "version"
                ),

            "config":
                self.get_config(),

            "error":
                health.get(
                    "error"
                ),

        }


    # ========================================================
    # CHAT
    # ========================================================

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
    ):
        """Send a non-streaming, session-local conversation to Ollama."""

        selected_model = (
            str(model or self.config.get("model") or "").strip()
        )

        if not selected_model:
            raise ValueError(
                "Bitte zuerst im Ollama-Popup ein Modell auswählen."
            )

        cleaned_messages = []

        for message in messages:
            role = str(message.get("role", "")).strip()
            content = str(message.get("content", "")).strip()

            if role not in {"system", "user", "assistant"} or not content:
                continue

            cleaned_messages.append({
                "role": role,
                "content": content,
            })

        if not cleaned_messages:
            raise ValueError("Die Chat-Nachricht ist leer.")

        result = self._request(
            "/api/chat",
            method="POST",
            payload={
                "model": selected_model,
                "messages": cleaned_messages,
                "stream": False,
                "think": False,
                "keep_alive": self.config.get("keep_alive", "5m"),
                "options": {
                    "temperature": self.config.get("temperature", 0.2),
                    "num_ctx": self.config.get("context", 8192),
                    "num_predict": self.config.get("num_predict", 2048),
                },
            },
            timeout=120,
        )

        message = result.get("message") or {}
        content = str(message.get("content") or "").strip()

        if not content:
            raise RuntimeError("Ollama hat keine Chat-Antwort geliefert.")

        return {
            "model": selected_model,
            "message": {
                "role": "assistant",
                "content": content,
            },
        }


    # ========================================================
    # LEGACY / RUNTIME COMPATIBILITY
    # ========================================================

    def scan(self):
        """
        Compatibility adapter for RuntimeManager.

        RuntimeManager historically calls scan().
        The current connector uses status() internally.
        """

        result = self.status()

        return {
            "status": (
                "ONLINE"
                if result.get("online", False)
                else "OFFLINE"
            ),
            "online": result.get(
                "online",
                False
            ),
            "model": result.get(
                "model",
                ""
            ),
            "model_count": result.get(
                "model_count",
                0
            ),
            "version": result.get(
                "version"
            ),
            "url": result.get(
                "url",
                self.url
            ),
            "error": result.get(
                "error"
            ),
        }
