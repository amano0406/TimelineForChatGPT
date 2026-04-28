from __future__ import annotations

import json
import hashlib
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from timeline_for_chatgpt_worker.cli import create_job_from_input, main, refresh_from_config
from timeline_for_chatgpt_worker.processor import process_job
from timeline_for_chatgpt_worker.refresh import build_config_check


class ProcessJobTests(unittest.TestCase):
    def test_settings_init_creates_settings_from_example(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings_path = root / "settings.json"
            example_path = root / "settings.example.json"
            example_payload = {
                "allowedExtensions": [".zip"],
                "inputRoots": [
                    {
                        "id": "exports",
                        "displayName": "Exports",
                        "path": str(root / "inputs"),
                        "enabled": True,
                    }
                ],
                "outputRoot": {"path": str(root / "outputs")},
                "stateRoot": {"path": str(root / "state")},
            }
            example_path.write_text(json.dumps(example_payload), encoding="utf-8")

            exit_code = main(
                [
                    "settings",
                    "init",
                    "--settings",
                    str(settings_path),
                    "--example",
                    str(example_path),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue(settings_path.exists())
            self.assertEqual(
                json.loads(settings_path.read_text(encoding="utf-8")),
                example_payload,
            )

    def test_refresh_processes_changed_inputs_and_skips_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_root = root / "inputs"
            output_root = root / "outputs"
            state_root = root / "state"
            input_root.mkdir()
            export_path = input_root / "export.zip"
            write_sample_export(export_path, conversation_id="conv-refresh", title="Refresh")
            config_path = root / "runtime.json"
            config_path.write_text(
                json.dumps(
                    {
                        "allowedExtensions": [".zip"],
                        "refresh": {"recursive": False, "profile": "timeline-default"},
                        "inputRoots": [
                            {
                                "id": "exports",
                                "displayName": "Exports",
                                "path": str(input_root),
                                "enabled": True,
                            }
                        ],
                        "outputRoot": {"path": str(output_root)},
                        "stateRoot": {"path": str(state_root)},
                    }
                ),
                encoding="utf-8",
            )

            first_report = refresh_from_config(config_path)
            second_report = refresh_from_config(config_path)

            self.assertEqual(first_report["summary"]["processed"], 1)
            self.assertEqual(first_report["summary"]["skipped"], 0)
            self.assertEqual(second_report["summary"]["processed"], 0)
            self.assertEqual(second_report["summary"]["skipped"], 1)
            self.assertEqual(second_report["summary"]["missing"], 0)
            self.assertEqual(second_report["summary"]["duplicates"], 0)
            self.assertEqual(second_report["items"][0]["status"], "skipped_unchanged")
            self.assertTrue((state_root / "refresh_state.json").exists())
            self.assertTrue(Path(str(first_report["report_path"])).name.startswith("refresh-"))
            latest_path = output_root / "refresh-latest.md"
            self.assertEqual(first_report["latest_markdown_path"], str(latest_path))
            self.assertTrue(latest_path.exists())
            latest_markdown = latest_path.read_text(encoding="utf-8")
            self.assertIn("TimelineForChatGPT Refresh", latest_markdown)
            self.assertIn("skipped_unchanged", latest_markdown)
            index_json_path = output_root / "index.json"
            index_markdown_path = output_root / "index.md"
            self.assertEqual(first_report["index_json_path"], str(index_json_path))
            self.assertEqual(first_report["index_markdown_path"], str(index_markdown_path))
            self.assertTrue(index_json_path.exists())
            self.assertTrue(index_markdown_path.exists())
            index = json.loads(index_json_path.read_text(encoding="utf-8"))
            self.assertEqual(index["total_known_inputs"], 1)
            self.assertEqual(index["latest_success_count"], 1)
            self.assertEqual(index["items"][0]["latest_success_run_dir"], index["items"][0]["run_dir"])
            self.assertIn("duration_seconds", second_report["summary"])
            self.assertIn("fingerprint_seconds", second_report["items"][0]["timing"])

    def test_config_check_reports_processable_input_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_root = root / "inputs"
            input_root.mkdir()
            write_sample_export(input_root / "export.zip", conversation_id="conv-check", title="Check")
            config_path = write_runtime_config(root, input_root)

            report = build_config_check(config_path)

            self.assertEqual(report["processable_input_count"], 1)
            self.assertEqual(report["warnings"], [])
            self.assertEqual(report["input_roots"][0]["id"], "exports")

    def test_refresh_reports_missing_inputs_without_deleting_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_root = root / "inputs"
            input_root.mkdir()
            export_path = input_root / "export.zip"
            write_sample_export(export_path, conversation_id="conv-missing", title="Missing")
            config_path = write_runtime_config(root, input_root)

            first_report = refresh_from_config(config_path)
            export_path.unlink()
            second_report = refresh_from_config(config_path)

            self.assertEqual(first_report["summary"]["processed"], 1)
            self.assertEqual(second_report["summary"]["missing"], 1)
            self.assertEqual(second_report["items"][0]["status"], "missing_from_input")

    def test_refresh_skips_duplicate_inputs_by_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_root = root / "inputs"
            input_root.mkdir()
            first = input_root / "first.zip"
            second = input_root / "second.zip"
            write_sample_export(first, conversation_id="conv-duplicate", title="Duplicate")
            shutil.copyfile(first, second)
            config_path = write_runtime_config(root, input_root)

            report = refresh_from_config(config_path)

            statuses = [item["status"] for item in report["items"]]
            self.assertIn("completed", statuses)
            self.assertIn("duplicate_skipped", statuses)
            self.assertEqual(report["summary"]["processed"], 1)
            self.assertEqual(report["summary"]["duplicates"], 1)

    def test_refresh_rejects_existing_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_root = root / "inputs"
            state_root = root / "state"
            input_root.mkdir()
            state_root.mkdir()
            write_sample_export(input_root / "export.zip", conversation_id="conv-lock", title="Lock")
            config_path = write_runtime_config(root, input_root, state_root=state_root)
            (state_root / "refresh.lock").write_text("locked", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "Refresh is already running"):
                refresh_from_config(config_path)

    def test_refresh_rejects_missing_enabled_input_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "runtime.json"
            config_path.write_text(
                json.dumps(
                    {
                        "allowedExtensions": [".zip"],
                        "inputRoots": [
                            {
                                "id": "missing",
                                "displayName": "Missing",
                                "path": str(root / "missing"),
                                "enabled": True,
                            }
                        ],
                        "outputRoot": {"path": str(root / "outputs")},
                        "stateRoot": {"path": str(root / "state")},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "No enabled inputRoots directories exist"):
                refresh_from_config(config_path)

    def test_cli_job_creation_processes_zip_without_copying_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_dir = root / "source"
            source_dir.mkdir()
            upload_path = source_dir / "export.zip"
            with zipfile.ZipFile(upload_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("export_manifest.json", "{}")
                archive.writestr(
                    "conversations.json",
                    json.dumps(
                        [
                            {
                                "id": "conv-1",
                                "conversation_id": "conv-1",
                                "title": "CLI",
                                "current_node": "n1",
                                "mapping": {
                                    "n1": {
                                        "id": "n1",
                                        "parent": None,
                                        "children": [],
                                        "message": {
                                            "id": "m1",
                                            "author": {"role": "user"},
                                            "create_time": "2026-01-01T00:00:00Z",
                                            "content": {
                                                "content_type": "text",
                                                "parts": ["hello from cli"],
                                            },
                                        },
                                    }
                                },
                            }
                        ]
                    ),
                )

            output_root = root / "outputs"
            run_dir = create_job_from_input(
                input_path=upload_path,
                output_root=output_root,
                profile="timeline-default",
                job_id="job-cli",
            )
            process_job(run_dir)

            request = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))

            self.assertEqual(request["input_items"][0]["uploaded_path"], str(upload_path))
            self.assertTrue(upload_path.exists())
            self.assertEqual(status["state"], "completed")
            self.assertTrue((run_dir / "job-cli.zip").exists())

    def test_archive_contains_final_run_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            upload_path = root / "export.zip"
            with zipfile.ZipFile(upload_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("export_manifest.json", "{}")
                archive.writestr("images/example.png", b"example image bytes")
                archive.writestr(
                    "conversations.json",
                    json.dumps(
                        [
                            {
                                "id": "conv-1",
                                "conversation_id": "conv-1",
                                "title": "Final metadata",
                                "current_node": "n1",
                                "mapping": {
                                    "n1": {
                                        "id": "n1",
                                        "parent": None,
                                        "children": [],
                                        "message": {
                                            "id": "m1",
                                            "author": {"role": "user"},
                                            "create_time": "2026-01-01T00:00:00Z",
                                            "content": {
                                                "content_type": "multimodal_text",
                                                "parts": [
                                                    "hello",
                                                    {
                                                        "attachment_id": "att-1",
                                                        "logical_path": "images/example.png",
                                                    },
                                                ],
                                            },
                                        },
                                    }
                                },
                            }
                        ]
                    ),
                )

            run_dir = root / "job-test"
            run_dir.mkdir()
            request = {
                "schema_version": 1,
                "job_id": "job-test",
                "created_at": "2026-04-27T00:00:00+00:00",
                "output_root_id": "runs",
                "output_root_path": str(root),
                "profile": "timeline-default",
                "reprocess_duplicates": False,
                "parser_options": {},
                "input_items": [
                    {
                        "input_id": "upload-0001",
                        "source_kind": "upload_zip",
                        "source_id": "uploads",
                        "original_path": "export.zip",
                        "display_name": "export.zip",
                        "size_bytes": upload_path.stat().st_size,
                        "uploaded_path": str(upload_path),
                    }
                ],
            }
            (run_dir / "request.json").write_text(json.dumps(request), encoding="utf-8")
            (run_dir / "status.json").write_text(
                json.dumps({"schema_version": 1, "job_id": "job-test", "state": "pending"}),
                encoding="utf-8",
            )

            process_job(run_dir)

            archive_path = run_dir / "job-test.zip"
            with zipfile.ZipFile(archive_path) as archive:
                status = json.loads(archive.read("status.json"))
                result = json.loads(archive.read("result.json"))
                manifest = json.loads(archive.read("manifest.json"))
                attachments = json.loads(
                    archive.read("conversations/conv-1/attachments.json")
                )

            self.assertEqual(status["state"], "completed")
            self.assertEqual(result["state"], "completed")
            self.assertEqual(result["archive_path"], str(archive_path))
            self.assertEqual(manifest["items"][0]["status"], "completed")
            attachment = attachments["items"][0]
            self.assertEqual(attachment["conversation_id"], "conv-1")
            self.assertEqual(attachment["message_id"], "m1")
            self.assertEqual(attachment["relative_path"], "images/example.png")
            self.assertTrue(attachment["file_exists"])
            self.assertEqual(attachment["size_bytes"], len(b"example image bytes"))
            self.assertEqual(
                attachment["hash_sha256"],
                hashlib.sha256(b"example image bytes").hexdigest(),
            )
            self.assertIsNotNone(attachment["mtime_utc"])


def write_runtime_config(root: Path, input_root: Path, state_root: Path | None = None) -> Path:
    output_root = root / "outputs"
    resolved_state_root = state_root or root / "state"
    config_path = root / "runtime.json"
    config_path.write_text(
        json.dumps(
            {
                "allowedExtensions": [".zip"],
                "refresh": {"recursive": False, "profile": "timeline-default"},
                "inputRoots": [
                    {
                        "id": "exports",
                        "displayName": "Exports",
                        "path": str(input_root),
                        "enabled": True,
                    }
                ],
                "outputRoot": {"path": str(output_root)},
                "stateRoot": {"path": str(resolved_state_root)},
            }
        ),
        encoding="utf-8",
    )
    return config_path


def write_sample_export(path: Path, conversation_id: str, title: str) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("export_manifest.json", "{}")
        archive.writestr(
            "conversations.json",
            json.dumps(
                [
                    {
                        "id": conversation_id,
                        "conversation_id": conversation_id,
                        "title": title,
                        "create_time": 1767225600,
                        "update_time": 1767225600,
                        "current_node": "n1",
                        "mapping": {
                            "n1": {
                                "id": "n1",
                                "parent": None,
                                "children": [],
                                "message": {
                                    "id": "m1",
                                    "author": {"role": "user"},
                                    "create_time": 1767225600,
                                    "content": {
                                        "content_type": "text",
                                        "parts": ["hello from refresh"],
                                    },
                                },
                            }
                        },
                    }
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()
