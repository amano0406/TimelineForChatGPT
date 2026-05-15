from __future__ import annotations

import hashlib
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

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
    run_root: Path
    state_root: Path
    cache_root: Path
    allowed_extensions: list[str]
    recursive: bool = False
    profile: str = "timeline-default"
    instance_name: str = ""
    api_port: int = 19300


def default_settings_path() -> Path:
    configured = os.environ.get("TIMELINE_FOR_CHATGPT_SETTINGS")
    if configured:
        return Path(configured)
    return Path("settings.json")


def settings_example_path(settings_path: Path | None = None) -> Path:
    base = settings_path or default_settings_path()
    return base.expanduser().resolve().parent / "settings.example.json"


def init_settings(settings_path: Path | None = None, example_path: Path | None = None) -> Path:
    destination = (settings_path or default_settings_path()).expanduser()
    source = (example_path or settings_example_path(destination)).expanduser()
    if destination.exists():
        return destination
    if not source.exists():
        raise FileNotFoundError(f"settings example does not exist: {source}")
    ensure_dir(destination.parent)
    destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return destination


def load_runtime_config(path: Path | None = None) -> RuntimeConfig:
    settings_path = (path or default_settings_path()).expanduser()
    payload = load_json(settings_path)
    base_dir = settings_path.parent
    use_environment_roots = is_default_settings_path(settings_path)

    output_root = output_root_from_config(payload, base_dir, use_environment_roots=use_environment_roots)
    legacy_input_roots = input_roots_from_config(payload, base_dir)
    legacy_runtime_root = output_root if legacy_input_roots and not use_environment_roots else None
    run_root = internal_runtime_path(
        "TIMELINE_FOR_CHATGPT_OUTPUTS_ROOT",
        docker_default="/shared/app-data/runs",
        host_default=legacy_runtime_root or base_dir / ".app-data" / "runs",
        base_dir=base_dir,
        use_environment_roots=use_environment_roots,
    )
    state_root = internal_runtime_path(
        "TIMELINE_FOR_CHATGPT_STATE_ROOT",
        docker_default="/shared/app-data/state",
        host_default=legacy_path_from_config(payload.get("stateRoot"), base_dir) or base_dir / ".app-data" / "state",
        base_dir=base_dir,
        use_environment_roots=use_environment_roots,
    )
    cache_root = internal_runtime_path(
        "TIMELINE_FOR_CHATGPT_CACHE_ROOT",
        docker_default="/shared/cache",
        host_default=legacy_path_from_config(payload.get("cacheRoot"), base_dir) or base_dir / ".app-data" / "cache",
        base_dir=base_dir,
        use_environment_roots=use_environment_roots,
    )
    refresh_payload = payload.get("refresh") if isinstance(payload.get("refresh"), dict) else {}
    runtime_payload = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}

    return RuntimeConfig(
        output_root=output_root,
        input_roots=legacy_input_roots,
        run_root=run_root,
        state_root=state_root,
        cache_root=cache_root,
        allowed_extensions=allowed_extensions_from_config(payload),
        recursive=bool(refresh_payload.get("recursive", False)),
        profile=str(refresh_payload.get("profile") or "timeline-default"),
        instance_name=str(runtime_payload.get("instanceName") or ""),
        api_port=api_port_from_config(runtime_payload),
    )


def validate_runtime_config(config: RuntimeConfig, require_input_roots: bool = True) -> list[str]:
    warnings: list[str] = []
    enabled_roots = [input_root for input_root in config.input_roots if input_root.enabled]
    if require_input_roots and not enabled_roots:
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
    if require_input_roots and not existing_roots:
        raise ValueError("No enabled inputRoots directories exist.")

    ensure_writable_dir(config.output_root, "outputRoot")
    ensure_writable_dir(config.run_root, "runRoot")
    ensure_writable_dir(config.state_root, "stateRoot")
    ensure_writable_dir(config.cache_root, "cacheRoot")

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


def build_config_check(config_path: Path | None = None) -> dict[str, Any]:
    settings_path = config_path or default_settings_path()
    payload = load_json(settings_path)
    if not isinstance(payload, dict):
        raise ValueError(f"settings must be a JSON object: {settings_path}")
    config = load_runtime_config(settings_path)
    warnings = validate_runtime_config(config, require_input_roots=False)
    supported_settings_keys = ["schemaVersion", "runtime", "outputRoot"]
    unsupported_keys = sorted(key for key in payload if key not in supported_settings_keys)
    for key in unsupported_keys:
        warnings.append(f"Ignoring unsupported settings key: {key}")
    return {
        "schema_version": 1,
        "checked_at": now_iso(),
        "settings_path": str(settings_path),
        "settings_exists": settings_path.exists(),
        "output_root": str(config.output_root),
        "output_root_exists": config.output_root.exists(),
        "output_root_is_dir": config.output_root.is_dir(),
        "run_root": str(config.run_root),
        "state_root": str(config.state_root),
        "cache_root": str(config.cache_root),
        "supported_settings_keys": supported_settings_keys,
        "unsupported_settings_keys": unsupported_keys,
        "warnings": warnings,
    }


@contextmanager
def refresh_lock(state_root: Path) -> Iterator[Path]:
    ensure_dir(state_root)
    lock_path = state_root / "refresh.lock"
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f"Refresh is already running or a stale lock exists: {lock_path}") from exc

    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(f"pid={os.getpid()}\ncreated_at={now_iso()}\n")
    try:
        yield lock_path
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


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


def is_default_settings_path(settings_path: Path) -> bool:
    try:
        return settings_path.expanduser().resolve() == default_settings_path().expanduser().resolve()
    except OSError:
        return settings_path.expanduser() == default_settings_path().expanduser()


def output_root_from_config(payload: dict[str, Any], base_dir: Path, use_environment_roots: bool = True) -> Path:
    configured = os.environ.get("TIMELINE_FOR_CHATGPT_OUTPUT_ROOT") if use_environment_roots else None
    if configured:
        return resolve_config_path(configured, base_dir)
    output_root = payload.get("outputRoot")
    if isinstance(output_root, dict):
        output_root = output_root.get("path")
    if not isinstance(output_root, str) or not output_root.strip():
        raise ValueError("settings.json must include outputRoot as a path string")
    return resolve_config_path(output_root, base_dir)


def input_roots_from_config(payload: dict[str, Any], base_dir: Path) -> list[InputRootConfig]:
    roots = payload.get("inputRoots")
    if not isinstance(roots, list):
        return []
    parsed: list[InputRootConfig] = []
    for index, entry in enumerate(roots, start=1):
        if not isinstance(entry, dict):
            continue
        raw_path = entry.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        root_id = str(entry.get("id") or f"input-{index:04d}")
        parsed.append(
            InputRootConfig(
                root_id=root_id,
                display_name=str(entry.get("displayName") or root_id),
                path=resolve_config_path(raw_path, base_dir),
                enabled=bool(entry.get("enabled", True)),
            )
        )
    return parsed


def allowed_extensions_from_config(payload: dict[str, Any]) -> list[str]:
    configured = payload.get("allowedExtensions")
    if not isinstance(configured, list) or not configured:
        return [".zip"]
    return sorted({normalize_extension(item) for item in configured})


def api_port_from_config(payload: dict[str, Any]) -> int:
    configured = os.environ.get("TIMELINE_FOR_CHATGPT_API_PORT")
    value = configured if configured else payload.get("apiPort")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 19300
    return parsed if 1 <= parsed <= 65535 else 19300


def legacy_path_from_config(value: Any, base_dir: Path) -> Path | None:
    if isinstance(value, dict):
        value = value.get("path")
    if not isinstance(value, str) or not value.strip():
        return None
    return resolve_config_path(value, base_dir)


def internal_runtime_path(
    env_name: str,
    docker_default: str,
    host_default: Path,
    base_dir: Path,
    use_environment_roots: bool = True,
) -> Path:
    configured = os.environ.get(env_name) if use_environment_roots else None
    if configured:
        return resolve_config_path(configured, base_dir)
    if use_environment_roots and (truthy_env("TIMELINE_FOR_CHATGPT_DOCKER") or Path("/.dockerenv").exists()):
        return resolve_config_path(docker_default, base_dir)
    return host_default.expanduser().resolve()


def truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


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
        f"- Missing from input: `{summary.get('missing', 0)}`",
        f"- Duplicates: `{summary.get('duplicates', 0)}`",
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
        if item.get("run_id"):
            lines.append(f"- Run ID: `{item['run_id']}`")
        if item.get("run_dir"):
            lines.append(f"- Run: `{item['run_dir']}`")
        if item.get("previous_run_dir"):
            lines.append(f"- Previous run: `{item['previous_run_dir']}`")
        if item.get("duplicate_of"):
            lines.append(f"- Duplicate of: `{item['duplicate_of']}`")
        if item.get("duplicate_run_dir"):
            lines.append(f"- Duplicate run: `{item['duplicate_run_dir']}`")
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


def build_refresh_index(state: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    state_items = state.get("items") if isinstance(state.get("items"), dict) else {}
    report_items = report.get("items") if isinstance(report.get("items"), list) else []
    report_by_path = {
        str(item.get("input_path")): item
        for item in report_items
        if isinstance(item, dict) and item.get("input_path")
    }

    rows: list[dict[str, Any]] = []
    for input_path, state_item in sorted(state_items.items()):
        if not isinstance(state_item, dict):
            continue
        report_item = report_by_path.get(str(input_path), {})
        rows.append(
            {
                "input_path": input_path,
                "input_root_id": state_item.get("input_root_id"),
                "display_name": state_item.get("display_name"),
                "result_state": state_item.get("result_state"),
                "run_id": state_item.get("run_id"),
                "run_dir": state_item.get("run_dir"),
                "updated_at": state_item.get("updated_at"),
                "latest_success_run_id": state_item.get("latest_success_run_id"),
                "latest_success_run_dir": state_item.get("latest_success_run_dir"),
                "latest_success_at": state_item.get("latest_success_at"),
                "latest_refresh_status": report_item.get("status"),
                "fingerprint": state_item.get("fingerprint"),
            }
        )

    latest_success_count = sum(1 for row in rows if row.get("latest_success_run_dir"))
    failed_count = sum(1 for row in rows if row.get("result_state") == "failed")
    return {
        "schema_version": 1,
        "generated_at": now_iso(),
        "latest_refresh_report_path": report.get("report_path"),
        "latest_refresh_started_at": report.get("started_at"),
        "latest_refresh_completed_at": report.get("completed_at"),
        "latest_refresh_summary": report.get("summary"),
        "total_known_inputs": len(rows),
        "latest_success_count": latest_success_count,
        "failed_count": failed_count,
        "items": rows,
    }


def build_refresh_index_markdown(index: dict[str, Any]) -> str:
    summary = index.get("latest_refresh_summary") if isinstance(index.get("latest_refresh_summary"), dict) else {}
    items = index.get("items") if isinstance(index.get("items"), list) else []
    lines = [
        "# TimelineForChatGPT Index",
        "",
        "## Latest Refresh",
        "",
        f"- Started: `{index.get('latest_refresh_started_at') or '-'}`",
        f"- Completed: `{index.get('latest_refresh_completed_at') or '-'}`",
        f"- Report: `{index.get('latest_refresh_report_path') or '-'}`",
        f"- Discovered: `{summary.get('discovered', 0)}`",
        f"- Processed: `{summary.get('processed', 0)}`",
        f"- Skipped: `{summary.get('skipped', 0)}`",
        f"- Failed: `{summary.get('failed', 0)}`",
        f"- Missing: `{summary.get('missing', 0)}`",
        f"- Duplicates: `{summary.get('duplicates', 0)}`",
        "",
        "## Known Inputs",
        "",
        f"- Total known inputs: `{index.get('total_known_inputs', 0)}`",
        f"- Latest successful outputs: `{index.get('latest_success_count', 0)}`",
        f"- Latest failed inputs: `{index.get('failed_count', 0)}`",
        "",
    ]
    if not items:
        lines.extend(["No inputs have been processed yet.", ""])
        return "\n".join(lines)

    for item in items:
        title = item.get("display_name") or item.get("input_path") or "input"
        lines.append(f"### {title}")
        lines.append("")
        lines.append(f"- Input: `{item.get('input_path') or '-'}`")
        if item.get("input_root_id"):
            lines.append(f"- Input root: `{item['input_root_id']}`")
        if item.get("latest_refresh_status"):
            lines.append(f"- Latest refresh status: `{item['latest_refresh_status']}`")
        if item.get("result_state"):
            lines.append(f"- Latest result: `{item['result_state']}`")
        if item.get("run_dir"):
            lines.append(f"- Latest run: `{item['run_dir']}`")
        if item.get("latest_success_run_dir"):
            lines.append(f"- Latest successful run: `{item['latest_success_run_dir']}`")
        if item.get("updated_at"):
            lines.append(f"- Updated: `{item['updated_at']}`")
        lines.append("")

    return "\n".join(lines)


def write_refresh_index(output_root: Path, state: dict[str, Any], report: dict[str, Any]) -> tuple[Path, Path]:
    index = build_refresh_index(state, report)
    json_path = output_root / "index.json"
    markdown_path = output_root / "index.md"
    write_json(json_path, index)
    markdown_path.write_text(build_refresh_index_markdown(index), encoding="utf-8")
    return json_path, markdown_path


def build_refresh_run_id(root_id: str, source_path: Path, fingerprint: dict[str, Any], started_at: str) -> str:
    stamp = timestamp_token(started_at)
    name = slugify(source_path.stem)[:32]
    token = str(fingerprint.get("sha256") or "unknown")[:12]
    return f"run-{stamp}-{slugify(root_id)}-{name}-{token}"


def timestamp_token(value: str) -> str:
    return (
        value.replace("+00:00", "Z")
        .replace(":", "")
        .replace("-", "")
        .replace(".", "")
    )
