from __future__ import annotations

from pathlib import Path

from .fs_utils import load_json, write_json
from .refresh import load_runtime_config, validate_runtime_config


def settings_status_payload(settings_path: Path) -> dict[str, object]:
    config = load_runtime_config(settings_path)
    warnings = validate_runtime_config(config, require_input_roots=False)
    return {
        "schema_version": 1,
        "settings_path": str(settings_path),
        "settings_exists": settings_path.exists(),
        "output_root": str(config.output_root),
        "run_root": str(config.run_root),
        "state_root": str(config.state_root),
        "cache_root": str(config.cache_root),
        "runtime": {
            "instance_name": config.instance_name,
            "api_port": config.api_port,
        },
        "warnings": warnings,
        "summary": (
            f"output={config.output_root} runs={config.run_root} "
            f"state={config.state_root} cache={config.cache_root} api={config.api_port}"
        ),
    }


def settings_output_show_payload(settings_path: Path) -> dict[str, object]:
    config = load_runtime_config(settings_path)
    return {
        "schema_version": 1,
        "settings_path": str(settings_path),
        "output_root": str(config.output_root),
    }


def settings_output_set_payload(settings_path: Path, path_value: str) -> dict[str, object]:
    payload = load_json(settings_path)
    if not isinstance(payload, dict):
        raise ValueError(f"settings must be a JSON object: {settings_path}")
    payload["outputRoot"] = path_value
    write_json(settings_path, payload)
    return settings_output_show_payload(settings_path)
