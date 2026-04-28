from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .fs_utils import ensure_dir, load_json, now_iso, slugify, write_json


@dataclass
class InputRootConfig:
    root_id: str
    display_name: str
    path: Path
    enabled: bool = True


@dataclass
class RuntimeConfig:
    input_roots: list[InputRootConfig]
    output_root: Path
    state_root: Path
    allowed_extensions: list[str]
    recursive: bool = False
    profile: str = "timeline-default"


def default_config_path() -> Path:
    configured = os.environ.get("TIMELINE_FOR_CHATGPT_RUNTIME_DEFAULTS")
    if configured:
        return Path(configured)
    return Path("configs/runtime.defaults.json")


def load_runtime_config(path: Path | None = None) -> RuntimeConfig:
    config_path = (path or default_config_path()).expanduser()
    payload = load_json(config_path)
    base_dir = config_path.parent

    allowed_extensions = [
        normalize_extension(value)
        for value in payload.get("allowedExtensions", [".zip"])
    ]
    refresh_payload = payload.get("refresh") or {}
    recursive = bool(refresh_payload.get("recursive", False))
    profile = str(refresh_payload.get("profile") or payload.get("profile") or "timeline-default")

    input_roots = [
        InputRootConfig(
            root_id=str(item.get("id") or slugify(str(item.get("path") or "input"))),
            display_name=str(item.get("displayName") or item.get("id") or item.get("path") or "Input"),
            path=resolve_config_path(str(item["path"]), base_dir),
            enabled=bool(item.get("enabled", True)),
        )
        for item in payload.get("inputRoots", [])
        if item.get("path")
    ]
    if not input_roots:
        raise ValueError("runtime config must include at least one inputRoots entry")

    output_root = output_root_from_config(payload, base_dir)
    state_root = state_root_from_config(payload, output_root, base_dir)

    return RuntimeConfig(
        input_roots=input_roots,
        output_root=output_root,
        state_root=state_root,
        allowed_extensions=allowed_extensions,
        recursive=recursive,
        profile=profile,
    )


def validate_runtime_config(config: RuntimeConfig) -> list[str]:
    warnings: list[str] = []
    enabled_roots = [input_root for input_root in config.input_roots if input_root.enabled]
    if not enabled_roots:
        raise ValueError("No enabled inputRoots entries are configured.")

    existing_roots = [
        input_root
        for input_root in enabled_roots
        if input_root.path.exists() and input_root.path.is_dir()
    ]
    missing_roots = [
        input_root
        for input_root in enabled_roots
        if not input_root.path.exists() or not input_root.path.is_dir()
    ]
    for input_root in missing_roots:
        warnings.append(f"Input root is missing or not a directory: {input_root.root_id}={input_root.path}")
    if not existing_roots:
        raise ValueError("No enabled inputRoots directories exist.")

    ensure_writable_dir(config.output_root, "outputRoot")
    ensure_writable_dir(config.state_root, "stateRoot")

    if config.recursive:
        for input_root in existing_roots:
            if is_relative_to(config.output_root, input_root.path):
                raise ValueError(
                    f"outputRoot must not be inside recursive inputRoot {input_root.root_id}: "
                    f"{config.output_root}"
                )
            if is_relative_to(config.state_root, input_root.path):
                raise ValueError(
                    f"stateRoot must not be inside recursive inputRoot {input_root.root_id}: "
                    f"{config.state_root}"
                )

    return warnings


def ensure_writable_dir(path: Path, label: str) -> None:
    ensure_dir(path)
    probe_path = path / ".write-test"
    try:
        probe_path.write_text("ok", encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"{label} is not writable: {path}") from exc
    finally:
        try:
            probe_path.unlink()
        except FileNotFoundError:
            pass


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def output_root_from_config(payload: dict[str, Any], base_dir: Path) -> Path:
    output_root = payload.get("outputRoot")
    if isinstance(output_root, dict) and output_root.get("path"):
        return resolve_config_path(str(output_root["path"]), base_dir)
    if isinstance(output_root, str):
        return resolve_config_path(output_root, base_dir)

    for item in payload.get("outputRoots", []):
        if item.get("enabled", True) and item.get("path"):
            return resolve_config_path(str(item["path"]), base_dir)

    raise ValueError("runtime config must include outputRoot or at least one enabled outputRoots entry")


def state_root_from_config(payload: dict[str, Any], output_root: Path, base_dir: Path) -> Path:
    state_root = payload.get("stateRoot")
    if isinstance(state_root, dict) and state_root.get("path"):
        return resolve_config_path(str(state_root["path"]), base_dir)
    if isinstance(state_root, str):
        return resolve_config_path(state_root, base_dir)
    return output_root / ".state"


def normalize_extension(value: Any) -> str:
    text = str(value).strip().lower()
    if not text:
        return ".zip"
    return text if text.startswith(".") else f".{text}"


def resolve_config_path(value: str, base_dir: Path) -> Path:
    path = Path(os.path.expandvars(value)).expanduser()
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def discover_inputs(config: RuntimeConfig) -> list[tuple[InputRootConfig, Path]]:
    rows: list[tuple[InputRootConfig, Path]] = []
    allowed = set(config.allowed_extensions)
    for input_root in config.input_roots:
        if not input_root.enabled or not input_root.path.exists() or not input_root.path.is_dir():
            continue
        candidates = input_root.path.rglob("*") if config.recursive else input_root.path.glob("*")
        for candidate in candidates:
            if candidate.is_file() and candidate.suffix.lower() in allowed:
                rows.append((input_root, candidate.resolve()))
    return sorted(rows, key=lambda row: (row[0].root_id, str(row[1]).lower()))


def load_refresh_state(state_root: Path) -> dict[str, Any]:
    state_path = state_root / "refresh_state.json"
    if not state_path.exists():
        return {"schema_version": 1, "items": {}}
    payload = load_json(state_path)
    if not isinstance(payload, dict):
        return {"schema_version": 1, "items": {}}
    payload.setdefault("schema_version", 1)
    payload.setdefault("items", {})
    return payload


def write_refresh_state(state_root: Path, payload: dict[str, Any]) -> None:
    write_json(state_root / "refresh_state.json", payload)


def fingerprint_file(path: Path, previous: dict[str, Any] | None = None) -> dict[str, Any]:
    stat = path.stat()
    size_bytes = int(stat.st_size)
    mtime_ns = int(stat.st_mtime_ns)
    previous_fingerprint = (previous or {}).get("fingerprint") or {}
    if (
        previous_fingerprint.get("size_bytes") == size_bytes
        and previous_fingerprint.get("mtime_ns") == mtime_ns
        and previous_fingerprint.get("sha256")
    ):
        sha256 = str(previous_fingerprint["sha256"])
    else:
        sha256 = hash_file_sha256(path)

    return {
        "path": str(path),
        "size_bytes": size_bytes,
        "mtime_ns": mtime_ns,
        "sha256": sha256,
    }


def hash_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def same_fingerprint(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        left.get("size_bytes") == right.get("size_bytes")
        and left.get("mtime_ns") == right.get("mtime_ns")
        and left.get("sha256") == right.get("sha256")
    )


def build_refresh_report_path(output_root: Path, started_at: str) -> Path:
    stamp = timestamp_token(started_at)
    return output_root / f"refresh-{stamp}.json"


def build_refresh_latest_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    items = report.get("items") if isinstance(report.get("items"), list) else []
    warnings = report.get("warnings") if isinstance(report.get("warnings"), list) else []

    lines = [
        "# TimelineForChatGPT Refresh",
        "",
        "## Summary",
        "",
        f"- Started: `{report.get('started_at') or '-'}`",
        f"- Completed: `{report.get('completed_at') or '-'}`",
        f"- Discovered: `{summary.get('discovered', 0)}`",
        f"- Processed: `{summary.get('processed', 0)}`",
        f"- Skipped: `{summary.get('skipped', 0)}`",
        f"- Failed: `{summary.get('failed', 0)}`",
        f"- Dry run: `{report.get('dry_run', False)}`",
        f"- Force: `{report.get('force', False)}`",
        f"- Output root: `{report.get('output_root') or '-'}`",
        f"- State root: `{report.get('state_root') or '-'}`",
        "",
    ]

    if warnings:
        lines.extend(["## Warnings", ""])
        for warning in warnings:
            lines.append(f"- {warning}")
        lines.append("")

    lines.extend(["## Items", ""])
    if not items:
        lines.extend(["No inputs were discovered.", ""])
        return "\n".join(lines)

    for item in items:
        status = item.get("status") or "unknown"
        input_path = item.get("input_path") or "-"
        lines.append(f"### {status}")
        lines.append("")
        lines.append(f"- Input: `{input_path}`")
        if item.get("input_root_id"):
            lines.append(f"- Input root: `{item['input_root_id']}`")
        if item.get("job_id"):
            lines.append(f"- Job: `{item['job_id']}`")
        if item.get("run_dir"):
            lines.append(f"- Run: `{item['run_dir']}`")
        if item.get("previous_run_dir"):
            lines.append(f"- Previous run: `{item['previous_run_dir']}`")
        if item.get("result_state"):
            lines.append(f"- Previous result: `{item['result_state']}`")
        if item.get("message"):
            lines.append(f"- Message: {item['message']}")
        fingerprint = item.get("fingerprint") if isinstance(item.get("fingerprint"), dict) else {}
        if fingerprint:
            lines.append(f"- Size: `{fingerprint.get('size_bytes', '-')}` bytes")
            lines.append(f"- SHA-256: `{fingerprint.get('sha256', '-')}`")
        lines.append("")

    return "\n".join(lines)


def write_refresh_latest_markdown(output_root: Path, report: dict[str, Any]) -> Path:
    path = output_root / "refresh-latest.md"
    path.write_text(build_refresh_latest_markdown(report), encoding="utf-8")
    return path


def build_refresh_job_id(root_id: str, source_path: Path, fingerprint: dict[str, Any], started_at: str) -> str:
    stamp = timestamp_token(started_at)
    name = slugify(source_path.stem)[:32]
    token = str(fingerprint.get("sha256") or "unknown")[:12]
    return f"job-{stamp}-{slugify(root_id)}-{name}-{token}"


def timestamp_token(value: str) -> str:
    return (
        value.replace("+00:00", "Z")
        .replace(":", "")
        .replace("-", "")
        .replace(".", "")
    )
