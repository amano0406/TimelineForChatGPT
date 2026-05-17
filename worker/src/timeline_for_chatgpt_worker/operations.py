from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

from .directory_refresh_operations import refresh_from_config
from .items_operations import (
    DEFAULT_ITEMS_LIST_PAGE_SIZE,
    items_download_latest,
    items_list_payload,
    items_refresh_from_file,
)
from .processor import outputs_root, process_pending_runs, process_run
from .refresh import build_config_check, default_settings_path, init_settings
from .run_requests import create_run_from_input
from .runs_operations import runs_list_payload, runs_show_payload
from .settings_operations import (
    settings_output_set_payload,
    settings_output_show_payload,
    settings_status_payload,
)

HOST_RUN_ALLOW_ENV = "TIMELINE_FOR_CHATGPT_ALLOW_HOST_RUN"
DOCKER_RUNTIME_ENV = "TIMELINE_FOR_CHATGPT_DOCKER"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TimelineForChatGPT worker")
    subparsers = parser.add_subparsers(dest="operation", required=True)

    process = subparsers.add_parser("process", help="Create and run a run for one ChatGPT export.")
    process.add_argument("input_path", help="Path to a ChatGPT export ZIP or extracted export directory.")
    process.add_argument("--output-root", help="Directory where run output folders are written.")
    process.add_argument("--profile", default="timeline-default")
    process.add_argument("--run-id", help="Optional explicit run id. Defaults to a generated run id.")
    process.add_argument("--enqueue-only", action="store_true", help="Create request/status files without processing.")

    refresh = subparsers.add_parser("refresh", help="Scan configured input roots and process changed exports.")
    refresh.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    refresh.add_argument("--config", help="Deprecated alias for --settings.")
    refresh.add_argument("--dry-run", action="store_true", help="Write a refresh report without processing runs.")
    refresh.add_argument("--force", action="store_true", help="Process every discovered input even when unchanged.")

    config_check = subparsers.add_parser("config-check", help="Validate refresh configuration without processing.")
    config_check.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    config_check.add_argument("--config", help="Deprecated alias for --settings.")

    settings = subparsers.add_parser("settings", help="Manage persistent settings.")
    settings_subparsers = settings.add_subparsers(dest="settings_operation", required=True)
    settings_init = settings_subparsers.add_parser("init", help="Create settings.json if it does not exist.")
    settings_init.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    settings_init.add_argument("--example", help="Example settings JSON path. Defaults to settings.example.json.")
    settings_status = settings_subparsers.add_parser("status", help="Show resolved settings and storage paths.")
    settings_status.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    settings_status.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    settings_output = settings_subparsers.add_parser("output", help="Manage the fixed output root.")
    settings_output_subparsers = settings_output.add_subparsers(dest="settings_output_operation", required=True)
    settings_output_show = settings_output_subparsers.add_parser("show", help="Show the resolved output root.")
    settings_output_show.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    settings_output_show.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    settings_output_set = settings_output_subparsers.add_parser("set", help="Set outputRoot in settings.json.")
    settings_output_set.add_argument("path", help="New output root path.")
    settings_output_set.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    settings_output_set.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    items = subparsers.add_parser("items", help="Refresh, list, and download ChatGPT conversation items.")
    items_subparsers = items.add_subparsers(dest="items_operation", required=True)
    items_list = items_subparsers.add_parser("list", help="List current output items.")
    items_list.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    items_list.add_argument(
        "--page",
        type=positive_int,
        help="1-based page number. When omitted with --page-size, list returns every item.",
    )
    items_list.add_argument(
        "--page-size",
        type=positive_int,
        help=(
            f"Items per page. Defaults to {DEFAULT_ITEMS_LIST_PAGE_SIZE} when paging is requested."
        ),
    )
    items_list.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    items_refresh = items_subparsers.add_parser("refresh", help="Rebuild master artifacts from one ChatGPT export ZIP.")
    items_refresh.add_argument("--file", required=True, help="ChatGPT export ZIP to read.")
    items_refresh.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    items_refresh.add_argument("--download-to", help="Copy the generated ZIP to this directory or file path.")
    items_refresh.add_argument("--overwrite", action="store_true", help="Allow replacing an existing download ZIP.")
    items_refresh.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    items_download = items_subparsers.add_parser("download", help="Copy the latest generated ZIP.")
    items_download.add_argument("--to", required=True, help="Destination directory or ZIP file path.")
    items_download.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    items_download.add_argument("--overwrite", action="store_true", help="Allow replacing an existing ZIP.")
    items_download.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    runs = subparsers.add_parser("runs", help="Inspect refresh runs.")
    runs_subparsers = runs.add_subparsers(dest="runs_operation", required=True)
    runs_list = runs_subparsers.add_parser("list", help="List known runs.")
    runs_list.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    runs_list.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runs_show = runs_subparsers.add_parser("show", help="Show one run.")
    runs_show.add_argument("--run-id", required=True, help="Run id to inspect.")
    runs_show.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    runs_show.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    daemon = subparsers.add_parser("daemon", help="Poll for pending runs.")
    daemon.add_argument("--poll-interval", type=int, default=5)

    subparsers.add_parser("run-once", help="Process pending runs once.")
    return parser


def main(argv: list[str] | None = None) -> int:
    guard_message = docker_only_operation_guard_message()
    if guard_message:
        print(guard_message, file=sys.stderr)
        return 2

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.operation == "process":
        run_dir = create_run_from_input(
            input_path=Path(args.input_path),
            output_root=Path(args.output_root) if args.output_root else outputs_root(),
            profile=str(args.profile),
            run_id=args.run_id,
        )
        if not args.enqueue_only:
            process_run(run_dir)
        print(run_dir)
        return 0

    if args.operation == "refresh":
        report = refresh_from_config(
            config_path=resolve_settings_arg(args),
            dry_run=bool(args.dry_run),
            force=bool(args.force),
        )
        print(report["report_path"])
        return 0

    if args.operation == "config-check":
        report = build_config_check(resolve_settings_arg(args))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.operation == "settings" and args.settings_operation == "init":
        settings_path = init_settings(
            settings_path=Path(args.settings) if args.settings else default_settings_path(),
            example_path=Path(args.example) if args.example else None,
        )
        print(settings_path)
        return 0

    if args.operation == "settings" and args.settings_operation == "status":
        payload = settings_status_payload(resolve_settings_arg(args))
        print_payload(payload, bool(args.json), text_key="summary")
        return 0

    if args.operation == "settings" and args.settings_operation == "output":
        if args.settings_output_operation == "show":
            payload = settings_output_show_payload(resolve_settings_arg(args))
            print_payload(payload, bool(args.json), text_key="output_root")
            return 0
        if args.settings_output_operation == "set":
            payload = settings_output_set_payload(
                settings_path=resolve_settings_arg(args),
                path_value=str(args.path),
            )
            print_payload(payload, bool(args.json), text_key="output_root")
            return 0

    if args.operation == "items" and args.items_operation == "list":
        paging_requested = args.page is not None or args.page_size is not None
        payload = items_list_payload(
            resolve_settings_arg(args),
            page=int(args.page or 1),
            page_size=int(args.page_size or DEFAULT_ITEMS_LIST_PAGE_SIZE),
            include_all=not paging_requested,
        )
        print_payload(payload, bool(args.json), text_key="summary")
        return 0

    if args.operation == "items" and args.items_operation == "refresh":
        payload = items_refresh_from_file(
            file_path=Path(args.file),
            settings_path=resolve_settings_arg(args),
            download_to=Path(args.download_to) if args.download_to else None,
            overwrite=bool(args.overwrite),
        )
        print_payload(payload, bool(args.json), text_key="summary")
        return 0

    if args.operation == "items" and args.items_operation == "download":
        payload = items_download_latest(
            settings_path=resolve_settings_arg(args),
            destination=Path(args.to),
            overwrite=bool(args.overwrite),
        )
        print_payload(payload, bool(args.json), text_key="download_path")
        return 0

    if args.operation == "runs" and args.runs_operation == "list":
        payload = runs_list_payload(resolve_settings_arg(args))
        print_payload(payload, bool(args.json), text_key="summary")
        return 0

    if args.operation == "runs" and args.runs_operation == "show":
        payload = runs_show_payload(resolve_settings_arg(args), str(args.run_id))
        print_payload(payload, bool(args.json), text_key="summary")
        return 0

    if args.operation == "run-once":
        process_pending_runs()
        return 0

    while True:
        process_pending_runs()
        time.sleep(max(1, int(args.poll_interval)))


def docker_only_operation_guard_message(is_docker_file: bool | None = None) -> str | None:
    detected_docker_file = Path("/.dockerenv").exists() if is_docker_file is None else is_docker_file
    if truthy_env(DOCKER_RUNTIME_ENV) or detected_docker_file:
        return None
    if truthy_env(HOST_RUN_ALLOW_ENV):
        return None
    return (
        "TimelineForChatGPT worker operations are Docker-only in normal use. "
        "Run it with `docker compose exec -T worker python -m timeline_for_chatgpt_worker <operation>`, "
        f"or set {HOST_RUN_ALLOW_ENV}=1 for tests only."
    )


def truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be 1 or greater")
    return parsed


def resolve_settings_arg(args: argparse.Namespace) -> Path:
    value = getattr(args, "settings", None) or getattr(args, "config", None)
    return Path(value) if value else default_settings_path()


def print_payload(payload: dict[str, object], json_output: bool, text_key: str | None = None) -> None:
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    value = payload.get(text_key or "") if text_key else None
    if isinstance(value, str):
        print(value)
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
