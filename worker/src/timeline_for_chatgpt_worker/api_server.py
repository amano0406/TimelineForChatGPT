from __future__ import annotations

import json
import os
import re
import shutil
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .item_service import DEFAULT_ITEMS_LIST_PAGE_SIZE
from .item_service import items_download_latest
from .item_service import items_list_payload
from .item_service import items_refresh_from_file
from .refresh import default_settings_path
from .refresh import init_settings
from .settings_service import settings_status_payload


WINDOWS_DRIVE_RE = re.compile(r"^([A-Za-z]):[\\/](.*)$")


def handle_request(method: str, path: str, request: dict[str, Any] | None) -> tuple[int, Any]:
    route = path.rstrip("/") or "/"
    if method == "GET" and route == "/health":
        return HTTPStatus.OK, True
    if method != "POST":
        return HTTPStatus.NOT_FOUND, error_payload(f"Endpoint not found: {method} {path}")

    try:
        payload = request or {}
        if route == "/settings/init":
            return HTTPStatus.OK, convert_response_paths(settings_init_payload(payload))
        if route == "/settings/status":
            return HTTPStatus.OK, convert_response_paths(settings_status_payload(default_settings_path()))
        if route == "/items/list":
            return HTTPStatus.OK, convert_response_paths(items_list_response(payload))
        if route == "/items/detail":
            return HTTPStatus.OK, convert_response_paths(items_detail_response(payload))
        if route == "/items/refresh":
            return HTTPStatus.OK, convert_response_paths(items_refresh_response(payload))
        if route == "/items/download":
            return HTTPStatus.OK, convert_response_paths(items_download_response(payload))
    except Exception as exc:
        return HTTPStatus.INTERNAL_SERVER_ERROR, error_payload(str(exc), exc.__class__.__name__)

    return HTTPStatus.NOT_FOUND, error_payload(f"Endpoint not found: {method} {path}")


def settings_init_payload(request: dict[str, Any]) -> dict[str, Any]:
    target = default_settings_path()
    force = get_bool_any(request, ["force"], False)
    if target.exists() and not force:
        return {
            "ok": True,
            "settingsPath": str(target),
            "created": False,
        }

    example = Path(os.environ.get("TIMELINE_FOR_CHATGPT_SETTINGS_EXAMPLE", "/app/settings.example.json"))
    target.parent.mkdir(parents=True, exist_ok=True)
    if example.exists():
        shutil.copyfile(example, target)
    else:
        target.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "runtime": {"instanceName": "", "apiPort": 19300},
                    "outputRoot": "C:\\TimelineData\\chatgpt",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return {
        "ok": True,
        "settingsPath": str(init_settings(target)),
        "created": True,
    }


def items_list_response(request: dict[str, Any]) -> dict[str, object]:
    paging_requested = has_any(request, ["page", "pageSize", "page_size"])
    return items_list_payload(
        default_settings_path(),
        page=get_optional_positive_int(request, ["page"]) or 1,
        page_size=get_optional_positive_int(request, ["pageSize", "page_size"]) or DEFAULT_ITEMS_LIST_PAGE_SIZE,
        include_all=not paging_requested,
    )


def items_refresh_response(request: dict[str, Any]) -> dict[str, object]:
    file_path = get_string_any(request, ["filePath", "file", "inputPath", "input"])
    if not file_path:
        raise ValueError("ChatGPT export ZIP is required.")

    download_to = get_string_any(request, ["downloadTo", "download_to", "to"])
    return items_refresh_from_file(
        file_path=Path(to_container_path(file_path)),
        settings_path=default_settings_path(),
        download_to=Path(to_container_path(download_to)) if download_to else None,
        overwrite=get_bool_any(request, ["overwrite"], False),
    )


def items_download_response(request: dict[str, Any]) -> dict[str, object]:
    destination = get_string_any(request, ["to", "downloadTo", "download_to", "outputPath", "output_path"])
    if not destination:
        raise ValueError("Download destination is required.")
    return items_download_latest(
        settings_path=default_settings_path(),
        destination=Path(to_container_path(destination)),
        overwrite=get_bool_any(request, ["overwrite"], False),
    )


def items_detail_response(request: dict[str, Any]) -> dict[str, Any]:
    item_id = get_string_any(request, ["itemId", "item_id", "threadId", "thread_id", "conversationId", "conversation_id", "id"])
    if not item_id:
        return unavailable_thread_detail("", "", "", "", "Item id is required.")

    list_payload = items_list_payload(default_settings_path(), include_all=True)
    output_root = Path(str(list_payload.get("output_root") or ""))
    if not output_root:
        return unavailable_thread_detail(item_id, "", "", "", "Output directory is not configured.")

    try:
        item_dir = safe_child_directory(output_root, item_id)
    except ValueError as exc:
        return unavailable_thread_detail(item_id, str(output_root), "", "", str(exc))

    timeline_path = item_dir / "timeline.json"
    convert_info_path = item_dir / "convert_info.json"
    if not timeline_path.exists():
        return unavailable_thread_detail(
            item_id,
            str(item_dir),
            str(timeline_path),
            str(convert_info_path),
            "Thread was not found.",
            item_id,
        )

    timeline = read_json_object(timeline_path)
    if timeline is None:
        return unavailable_thread_detail(
            item_id,
            str(item_dir),
            str(timeline_path),
            str(convert_info_path),
            "Thread could not be read.",
            item_id,
        )

    messages = [
        convert_thread_message(message, index)
        for index, message in enumerate(timeline.get("messages") or [])
        if isinstance(message, dict)
    ]
    resolved_item_id = get_string_from_mapping(timeline, ["conversation_id", "thread_id", "item_id", "id"], item_id)
    title = get_string_from_mapping(timeline, ["title"], resolved_item_id)
    return {
        "available": True,
        "itemId": resolved_item_id,
        "title": title,
        "createdAt": get_string_from_mapping(timeline, ["created_at", "createdAt"], ""),
        "updatedAt": get_string_from_mapping(timeline, ["updated_at", "updatedAt"], ""),
        "messageCount": len(messages),
        "messages": messages,
        "directoryPath": str(item_dir),
        "timelinePath": str(timeline_path),
        "convertInfoPath": str(convert_info_path),
        "message": "",
    }


def convert_thread_message(message: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "index": index,
        "role": get_string_from_mapping(message, ["role"], ""),
        "createdAt": get_string_from_mapping(message, ["created_at", "createdAt"], ""),
        "text": get_string_from_mapping(message, ["text"], ""),
    }


def unavailable_thread_detail(
    item_id: str,
    directory_path: str,
    timeline_path: str,
    convert_info_path: str,
    message: str,
    title: str = "",
) -> dict[str, Any]:
    return {
        "available": False,
        "itemId": item_id,
        "title": title,
        "createdAt": "",
        "updatedAt": "",
        "messageCount": 0,
        "messages": [],
        "directoryPath": directory_path,
        "timelinePath": timeline_path,
        "convertInfoPath": convert_info_path,
        "message": message,
    }


def safe_child_directory(root: Path, child_name: str) -> Path:
    full_root = root.expanduser().resolve()
    normalized_child = child_name.replace("\\", "/").strip("/")
    candidate = (full_root / normalized_child).resolve()
    try:
        candidate.relative_to(full_root)
    except ValueError as exc:
        raise ValueError("Invalid item id.") from exc
    return candidate


def read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def to_container_path(value: str) -> str:
    text = value.strip().strip('"').strip("'")
    if not text:
        return ""
    if not in_container_runtime():
        return text
    match = WINDOWS_DRIVE_RE.match(text)
    if match:
        drive = match.group(1).lower()
        rest = match.group(2).replace("\\", "/")
        return f"/mnt/{drive}/{rest}"
    return text


def to_host_path(value: str) -> str:
    text = value.strip()
    if not text:
        return text

    host_settings = os.environ.get("TIMELINE_FOR_CHATGPT_HOST_SETTINGS_PATH", "").strip()
    if host_settings and text == "/workspace/settings.json":
        return host_settings

    host_output = os.environ.get("TIMELINE_FOR_CHATGPT_HOST_OUTPUT_ROOT", "").strip()
    if host_output:
        if text == "/workspace/output":
            return host_output
        if text.startswith("/workspace/output/"):
            suffix = text[len("/workspace/output/") :].replace("/", "\\")
            return host_output.rstrip("\\/") + "\\" + suffix

    match = re.match(r"^/mnt/([a-zA-Z])(?:/(.*))?$", text)
    if match:
        drive = match.group(1).upper()
        rest = (match.group(2) or "").replace("/", "\\")
        return f"{drive}:\\" + rest

    return text


def in_container_runtime() -> bool:
    return os.environ.get("TIMELINE_FOR_CHATGPT_DOCKER", "").strip().lower() in {"1", "true", "yes", "on"} or Path("/.dockerenv").exists()


def convert_response_paths(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: convert_response_paths(row) for key, row in value.items()}
    if isinstance(value, list):
        return [convert_response_paths(row) for row in value]
    if isinstance(value, str):
        return to_host_path(value)
    return value


def get_optional_positive_int(request: dict[str, Any], names: list[str]) -> int | None:
    for name in names:
        value = get_node(request, name)
        if isinstance(value, int):
            return value if value > 0 else None
        if isinstance(value, str):
            try:
                parsed = int(value)
            except ValueError:
                continue
            return parsed if parsed > 0 else None
    return None


def get_bool_any(request: dict[str, Any], names: list[str], fallback: bool) -> bool:
    for name in names:
        value = get_node(request, name)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
    return fallback


def get_string_any(request: dict[str, Any], names: list[str]) -> str:
    for name in names:
        value = get_node(request, name)
        if value is None:
            continue
        text = convert_json_text(value)
        if text:
            return text
    return ""


def get_string_from_mapping(source: dict[str, Any], names: list[str], fallback: str) -> str:
    for name in names:
        if name in source:
            text = convert_json_text(source[name])
            if text:
                return text
    lowered = {key.lower(): value for key, value in source.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value is not None:
            text = convert_json_text(value)
            if text:
                return text
    return fallback


def get_node(request: dict[str, Any], name: str) -> Any:
    if name in request:
        return request[name]
    lowered = name.lower()
    for key, value in request.items():
        if key.lower() == lowered:
            return value
    return None


def has_any(request: dict[str, Any], names: list[str]) -> bool:
    return any(get_node(request, name) is not None for name in names)


def convert_json_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    return json.dumps(value, ensure_ascii=False).strip()


def error_payload(message: str, error_type: str = "Error") -> dict[str, Any]:
    return {"ok": False, "error": {"type": error_type, "message": message}}


class TimelineForChatGptApiHandler(BaseHTTPRequestHandler):
    server_version = "TimelineForChatGptWorkerApi/1.0"

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _handle(self) -> None:
        try:
            request = self._read_json()
            status_code, payload = handle_request(self.command, self.path.split("?", 1)[0], request)
        except Exception as exc:
            status_code, payload = HTTPStatus.INTERNAL_SERVER_ERROR, error_payload(str(exc), exc.__class__.__name__)
        self._write_json(status_code, payload)

    def _read_json(self) -> dict[str, Any] | None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return None
        raw = self.rfile.read(length)
        if not raw.strip():
            return None
        loaded = json.loads(raw.decode("utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("JSON request body must be an object.")
        return loaded

    def _write_json(self, status_code: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status_code))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    host = os.environ.get("TIMELINE_FOR_CHATGPT_API_BIND_HOST", "0.0.0.0")
    port = int(os.environ.get("TIMELINE_FOR_CHATGPT_API_BIND_PORT", "8080"))
    server = ThreadingHTTPServer((host, port), TimelineForChatGptApiHandler)
    print(f"TimelineForChatGPT worker API listening on http://{host}:{port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
