"""Publish validated scenes inside an existing NAS Work mount."""

import json
import os
from pathlib import Path
import stat
from datetime import datetime, timezone
from uuid import uuid4


class StorageError(RuntimeError):
    pass


def _filename() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"diagram-{stamp}-{uuid4().hex[:12]}.excalidraw"


def publish_scene(scene: dict, output_dir: Path, share_prefix: str) -> dict:
    output_dir = Path(output_dir)
    if share_prefix not in ("Local/Work/excalidraw", "Local/Work/excalidraw-dev"):
        raise StorageError("invalid_share_prefix")
    try:
        if not stat.S_ISDIR(output_dir.lstat().st_mode):
            raise StorageError("missing_output_mount")
        data = (json.dumps(scene, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")
        directory_fd = os.open(output_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except (OSError, ValueError, TypeError) as exc:
        raise StorageError("missing_output_mount") from exc

    filename = _filename()
    temp_name = f".{filename}.{uuid4().hex}.tmp"
    published = False
    try:
        fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory_fd)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            raise
        os.link(temp_name, filename, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        published = True
        os.unlink(temp_name, dir_fd=directory_fd)
        try:
            os.fsync(directory_fd)
        except OSError:
            # Some SMB implementations do not support directory fsync.
            pass
        return {"filename": filename, "relative_path": f"{share_prefix}/{filename}",
                "element_count": len(scene["elements"])}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise StorageError("publish_failed") from exc
    finally:
        try:
            os.unlink(temp_name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        os.close(directory_fd)
