from __future__ import annotations

import os
from pathlib import Path


HOST_RUN_ALLOW_ENV = "TIMELINE_FOR_CHATGPT_ALLOW_HOST_RUN"
DOCKER_RUNTIME_ENV = "TIMELINE_FOR_CHATGPT_DOCKER"


def docker_only_operation_guard_message(is_docker_file: bool | None = None) -> str | None:
    detected_docker_file = Path("/.dockerenv").exists() if is_docker_file is None else is_docker_file
    if truthy_env(DOCKER_RUNTIME_ENV) or detected_docker_file:
        return None
    if truthy_env(HOST_RUN_ALLOW_ENV):
        return None
    return (
        "TimelineForChatGPT worker operations are Docker-only in normal use. "
        "Call the local product API, or set "
        f"{HOST_RUN_ALLOW_ENV}=1 for tests only."
    )


def truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}
