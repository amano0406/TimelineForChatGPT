from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
NORMAL_SETTINGS_PATH = REPO_ROOT / "settings.json"
FIXTURE_CONVERSATION_ID = "conv-cli-ps1-smoke"
CLI_TIMEOUT_SECONDS = 240


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a local Windows cli.ps1 refresh and download smoke test.",
    )
    parser.add_argument(
        "--preserve-output",
        action="store_true",
        help="Keep the temporary C:\\TimelineData smoke output for manual inspection.",
    )
    parser.add_argument(
        "--keep-compose-project",
        action="store_true",
        help="Do not remove the temporary Docker Compose project after the smoke test.",
    )
    args = parser.parse_args(argv)

    powershell = _resolve_powershell()
    timeline_data = _timeline_data_root()
    smoke_root = timeline_data / f"tfcg-cli-ps1-smoke-{int(time.time())}"
    output_root = smoke_root / "output"
    refresh_download_root = smoke_root / "refresh-downloads"
    download_root = smoke_root / "downloads"
    settings_root = smoke_root / "settings"
    appdata_root = smoke_root / "app-data"
    cache_root = smoke_root / "cache-data"
    long_export_name = f"chatgpt export smoke {'long-name-' * 12}2026.zip"
    export_path = smoke_root / long_export_name
    settings_path = settings_root / "settings.json"
    for directory in (output_root, refresh_download_root, download_root, settings_root, appdata_root, cache_root):
        directory.mkdir(parents=True, exist_ok=True)
    _write_sample_export(export_path)

    compose_project_name = f"tfcg-cli-ps1-smoke-{int(time.time())}"
    mount_env = _build_smoke_mount_env(
        settings_path=settings_path,
        appdata_root=appdata_root,
        cache_root=cache_root,
    )
    mount_env["COMPOSE_PROJECT_NAME"] = compose_project_name
    normal_settings_snapshot = _read_optional_bytes(NORMAL_SETTINGS_PATH)

    try:
        _write_settings(settings_path, output_root)
        refresh = _json_from_stdout(
            _run_cli(
                powershell,
                [
                    "items",
                    "refresh",
                    "--file",
                    _to_windows_path(export_path),
                    "--download-to",
                    _to_windows_path(refresh_download_root),
                    "--json",
                    "--overwrite",
                ],
                mount_env,
            ).stdout
        )
        _assert_refresh_payload(refresh)
        refresh_archive_path = _assert_refresh_download_payload(refresh, refresh_download_root)
        items_default = _json_from_stdout(
            _run_cli(
                powershell,
                ["items", "list", "--json"],
                mount_env,
            ).stdout
        )
        _assert_items_list_payload(items_default, paged=False)
        items_paged = _json_from_stdout(
            _run_cli(
                powershell,
                ["items", "list", "--page", "1", "--page-size", "1", "--json"],
                mount_env,
            ).stdout
        )
        _assert_items_list_payload(items_paged, paged=True)
        download = _json_from_stdout(
            _run_cli(
                powershell,
                [
                    "items",
                    "download",
                    "--to",
                    _to_windows_path(download_root),
                    "--json",
                    "--overwrite",
                ],
                mount_env,
            ).stdout
        )
        archive_path = _host_path_from_cli(str(download.get("download_path") or ""))
        _assert_master_output(output_root)
        _assert_download_archive(archive_path)
        overwrite_failure = _run_cli_expect_failure(
            powershell,
            [
                "items",
                "download",
                "--to",
                _to_windows_path(archive_path),
                "--json",
            ],
            mount_env,
        )
        _assert_download_without_overwrite_rejected(overwrite_failure, archive_path)
        _assert_file_unchanged(NORMAL_SETTINGS_PATH, normal_settings_snapshot)
        print(
            json.dumps(
                {
                    "state": "ok",
                    "entrypoint": "cli.ps1",
                    "output_root": str(output_root),
                    "refresh_download_archive": str(refresh_archive_path),
                    "download_archive": str(archive_path),
                    "fixture_conversation": FIXTURE_CONVERSATION_ID,
                    "long_input_name": export_path.name,
                    "download_without_overwrite_rejected": True,
                    "normal_settings_unchanged": True,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        if not args.keep_compose_project:
            _cleanup_smoke_compose_project(mount_env)
            _assert_smoke_compose_project_removed(compose_project_name)
        if not args.preserve_output:
            shutil.rmtree(smoke_root, ignore_errors=True)
            if smoke_root.exists():
                raise AssertionError(f"Smoke output directory was not removed: {smoke_root}")


def _resolve_powershell() -> str:
    candidates = ["powershell.exe", "powershell"]
    for candidate in candidates:
        if shutil.which(candidate):
            return candidate
    raise RuntimeError("PowerShell was not found. Run this smoke test on Windows or WSL with powershell.exe available.")


def _timeline_data_root() -> Path:
    if os.name == "nt":
        return Path("C:/TimelineData")
    if Path("/mnt/c").exists():
        return Path("/mnt/c/TimelineData")
    raise RuntimeError("This smoke test requires Windows C: drive access.")


def _build_smoke_mount_env(
    *,
    settings_path: Path,
    appdata_root: Path,
    cache_root: Path,
) -> dict[str, str]:
    return {
        "TIMELINE_FOR_CHATGPT_HOST_SETTINGS_PATH": _to_windows_path(settings_path),
        "TIMELINE_FOR_CHATGPT_HOST_APPDATA_ROOT": _to_windows_path(appdata_root),
        "TIMELINE_FOR_CHATGPT_HOST_CACHE_ROOT": _to_windows_path(cache_root),
    }


def _write_settings(settings_path: Path, output_root: Path) -> None:
    settings_path.write_text(
        json.dumps({"outputRoot": _to_windows_path(output_root)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _read_optional_bytes(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


def _assert_file_unchanged(path: Path, expected: bytes | None) -> None:
    actual = _read_optional_bytes(path)
    if actual != expected:
        raise AssertionError(f"Smoke test changed a protected file: {path}")


def _run_cli(
    powershell: str,
    args: list[str],
    mount_env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    completed = _run_cli_process(powershell, args, mount_env)
    if completed.returncode != 0:
        raise RuntimeError(_format_command_error(_cli_command(powershell, args, mount_env), completed))
    return completed


def _run_cli_expect_failure(
    powershell: str,
    args: list[str],
    mount_env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    completed = _run_cli_process(powershell, args, mount_env)
    if completed.returncode == 0:
        raise AssertionError(f"Command should have failed but completed successfully: {' '.join(args)}")
    return completed


def _run_cli_process(
    powershell: str,
    args: list[str],
    mount_env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(mount_env)
    return subprocess.run(
        _cli_command(powershell, args, mount_env),
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=CLI_TIMEOUT_SECONDS,
    )


def _cli_command(powershell: str, args: list[str], mount_env: dict[str, str]) -> list[str]:
    return [
        powershell,
        "-NoLogo",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        _powershell_invocation_script(args, mount_env),
    ]


def _powershell_invocation_script(args: list[str], mount_env: dict[str, str]) -> str:
    # Build the argument array inside PowerShell so WSL interop cannot split paths containing spaces.
    statements = [
        f"$env:{name} = {_ps_single_quote(value)}"
        for name, value in mount_env.items()
    ]
    statements.append(
        "$cliArgs = @("
        + ", ".join(_ps_single_quote(value) for value in args)
        + ")"
    )
    statements.append(f"& {_ps_single_quote(_to_windows_path(REPO_ROOT / 'cli.ps1'))} @cliArgs")
    return "; ".join(statements)


def _cleanup_smoke_compose_project(mount_env: dict[str, str]) -> None:
    project_name = mount_env.get("COMPOSE_PROJECT_NAME") or "tfcg-cli-ps1-smoke"
    env = os.environ.copy()
    env.update(mount_env)
    completed = subprocess.run(
        ["docker", "compose", "-p", project_name, "down", "--remove-orphans", "-v", "--rmi", "local"],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=CLI_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        raise RuntimeError(_format_command_error(["docker", "compose", "-p", project_name, "down"], completed))


def _assert_smoke_compose_project_removed(project_name: str) -> None:
    containers = _docker_output_lines(["ps", "-a", "--format", "{{.Names}}"])
    leftover_containers = sorted(name for name in containers if name.startswith(f"{project_name}-"))
    if leftover_containers:
        raise AssertionError(f"Smoke Docker containers were not removed: {leftover_containers}")

    volumes = _docker_output_lines(["volume", "ls", "--format", "{{.Name}}"])
    leftover_volumes = sorted(name for name in volumes if name.startswith(f"{project_name}_"))
    if leftover_volumes:
        raise AssertionError(f"Smoke Docker volumes were not removed: {leftover_volumes}")


def _docker_output_lines(args: list[str]) -> list[str]:
    completed = subprocess.run(
        ["docker", *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=CLI_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        raise RuntimeError(_format_command_error(["docker", *args], completed))
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def _format_command_error(command: list[str], completed: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(
        [
            f"Command failed: {' '.join(command)}",
            f"exit_code: {completed.returncode}",
            f"stdout: {completed.stdout}",
            f"stderr: {completed.stderr}",
            "Run .\\start.bat once if the worker image has not been built.",
        ]
    )


def _write_sample_export(path: Path) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("export_manifest.json", "{}")
        archive.writestr(
            "conversations.json",
            json.dumps(
                [
                    {
                        "id": FIXTURE_CONVERSATION_ID,
                        "conversation_id": FIXTURE_CONVERSATION_ID,
                        "title": "CLI ps1 smoke",
                        "create_time": "2026-01-01T00:00:00Z",
                        "update_time": "2026-01-01T00:02:00Z",
                        "current_node": "n2",
                        "mapping": {
                            "n1": {
                                "id": "n1",
                                "parent": None,
                                "children": ["n2"],
                                "message": {
                                    "id": "m-user",
                                    "author": {"role": "user"},
                                    "create_time": "2026-01-01T00:01:00Z",
                                    "content": {
                                        "content_type": "text",
                                        "parts": ["hello from cli ps1 smoke"],
                                    },
                                },
                            },
                            "n2": {
                                "id": "n2",
                                "parent": "n1",
                                "children": [],
                                "message": {
                                    "id": "m-assistant",
                                    "author": {"role": "assistant"},
                                    "create_time": "2026-01-01T00:02:00Z",
                                    "content": {
                                        "content_type": "text",
                                        "parts": ["answer from smoke"],
                                    },
                                },
                            },
                        },
                    }
                ]
            ),
        )


def _assert_refresh_payload(payload: dict[str, Any]) -> None:
    if payload.get("state") != "completed":
        raise AssertionError(f"Refresh did not complete: {payload!r}")
    manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else {}
    if int(manifest.get("item_count") or 0) != 1:
        raise AssertionError(f"Refresh should contain exactly 1 fixture conversation: {payload!r}")


def _assert_refresh_download_payload(payload: dict[str, Any], download_root: Path) -> Path:
    current = payload.get("current") if isinstance(payload.get("current"), dict) else {}
    copied_download_path = str(current.get("copied_download_path") or "")
    if not copied_download_path:
        raise AssertionError(f"Refresh did not report a copied download path: {payload!r}")
    archive_path = _host_path_from_cli(copied_download_path)
    if download_root.resolve() not in archive_path.resolve().parents:
        raise AssertionError(f"Refresh download was not copied under the expected root: {archive_path}")
    _assert_download_archive(archive_path)
    return archive_path


def _assert_items_list_payload(payload: dict[str, Any], *, paged: bool) -> None:
    if int(payload.get("item_count") or 0) != 1:
        raise AssertionError(f"Item list should report exactly 1 fixture conversation: {payload!r}")
    if int(payload.get("total_items") or 0) != 1:
        raise AssertionError(f"Item list should contain exactly 1 fixture conversation: {payload!r}")

    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    if len(items) != 1:
        raise AssertionError(f"Item list should return exactly 1 fixture conversation: {payload!r}")
    item = items[0] if isinstance(items[0], dict) else {}
    item_id = str(item.get("conversation_id") or item.get("id") or "")
    if item_id != FIXTURE_CONVERSATION_ID:
        raise AssertionError(f"Item list returned unexpected conversation id: {payload!r}")

    pagination = payload.get("pagination") if isinstance(payload.get("pagination"), dict) else {}
    expected_mode = "page" if paged else "all"
    if pagination.get("mode") != expected_mode:
        raise AssertionError(f"Item list used unexpected pagination mode: {payload!r}")
    if int(pagination.get("returned_items") or 0) != 1:
        raise AssertionError(f"Item list should return 1 item in pagination metadata: {payload!r}")
    if paged:
        if int(pagination.get("page") or 0) != 1:
            raise AssertionError(f"Paged item list should return page 1: {payload!r}")
        if int(pagination.get("page_size") or 0) != 1:
            raise AssertionError(f"Paged item list should use page size 1: {payload!r}")


def _assert_master_output(output_root: Path) -> None:
    timeline_path = output_root / FIXTURE_CONVERSATION_ID / "timeline.json"
    convert_info_path = output_root / FIXTURE_CONVERSATION_ID / "convert_info.json"
    if not timeline_path.exists():
        raise AssertionError(f"Missing timeline output: {timeline_path}")
    if not convert_info_path.exists():
        raise AssertionError(f"Missing conversion output: {convert_info_path}")
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    if timeline.get("title") != "CLI ps1 smoke":
        raise AssertionError(f"Unexpected timeline title: {timeline.get('title')!r}")


def _assert_download_archive(archive_path: Path) -> None:
    if not archive_path.exists():
        raise AssertionError(f"Download ZIP was not created: {archive_path}")
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        required = {
            "README.md",
            f"items/{FIXTURE_CONVERSATION_ID}/timeline.json",
            f"items/{FIXTURE_CONVERSATION_ID}/convert_info.json",
        }
        missing = sorted(required - names)
        if missing:
            raise AssertionError(f"Download ZIP is missing required entries: {missing}")
        if any(name.endswith("/thread.json") for name in names):
            raise AssertionError("Download ZIP must not contain legacy thread.json entries.")


def _assert_download_without_overwrite_rejected(
    completed: subprocess.CompletedProcess[str],
    archive_path: Path,
) -> None:
    output = f"{completed.stdout}\n{completed.stderr}"
    expected_path = _to_windows_path(archive_path)
    if "Download target already exists" not in output:
        raise AssertionError(f"Download without --overwrite failed for the wrong reason: {output!r}")
    compact_output = "".join(output.split())
    if "".join(expected_path.split()) not in compact_output and archive_path.name not in output:
        raise AssertionError(f"Download overwrite rejection did not mention the target path: {output!r}")


def _json_from_stdout(stdout: str) -> dict[str, Any]:
    stripped = stdout.strip()
    start = stripped.find("{")
    if start < 0:
        raise AssertionError(f"Command stdout did not contain a JSON object: {stdout!r}")
    try:
        payload = json.loads(stripped[start:])
    except json.JSONDecodeError as exc:
        raise AssertionError(f"Command stdout did not contain valid JSON: {stdout!r}") from exc
    if not isinstance(payload, dict):
        raise AssertionError(f"Command stdout JSON was not an object: {stdout!r}")
    return payload


def _ps_single_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _host_path_from_cli(value: str) -> Path:
    text = str(value or "")
    if len(text) >= 3 and text[1] == ":" and text[2] in ("\\", "/"):
        drive = text[0].lower()
        rest = text[3:].replace("\\", "/")
        if os.name != "nt" and Path(f"/mnt/{drive}").exists():
            return Path(f"/mnt/{drive}/{rest}")
    return Path(text)


def _to_windows_path(path: Path) -> str:
    text = str(path)
    if len(text) >= 3 and text[1] == ":":
        return text.replace("/", "\\")
    if text.startswith("/mnt/") and len(text) >= 7 and text[6] == "/":
        drive = text[5].upper()
        rest = text[7:].replace("/", "\\")
        return f"{drive}:\\{rest}"
    return text


if __name__ == "__main__":
    raise SystemExit(main())
