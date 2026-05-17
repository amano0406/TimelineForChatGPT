from __future__ import annotations

import os
import json
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from timeline_for_chatgpt_worker.item_service import (
    items_download_latest,
    items_list_payload,
    items_refresh_from_file,
)
from timeline_for_chatgpt_worker.processor import process_run
from timeline_for_chatgpt_worker.refresh import build_config_check, init_settings
from timeline_for_chatgpt_worker.run_requests import create_run_from_input
from timeline_for_chatgpt_worker.runtime_guard import docker_only_worker_guard_message


class ProcessRunTests(unittest.TestCase):
    def test_worker_service_rejects_host_execution_without_explicit_test_override(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TIMELINE_FOR_CHATGPT_DOCKER": "",
                "TIMELINE_FOR_CHATGPT_ALLOW_HOST_RUN": "",
            },
        ):
            self.assertIn(
                "Docker-only",
                docker_only_worker_guard_message(is_docker_file=False) or "",
            )

    def test_settings_init_creates_settings_from_example(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings_path = root / "settings.json"
            example_path = root / "settings.example.json"
            example_payload = {"outputRoot": str(root / "output")}
            example_path.write_text(json.dumps(example_payload), encoding="utf-8")

            created_path = init_settings(settings_path=settings_path, example_path=example_path)

            self.assertEqual(created_path, settings_path)
            self.assertTrue(settings_path.exists())
            self.assertEqual(
                json.loads(settings_path.read_text(encoding="utf-8")),
                example_payload,
            )

    def test_config_check_reports_resolved_settings_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_root = root / "output"
            config_path = root / "settings.json"
            config_path.write_text(json.dumps({"outputRoot": str(output_root)}), encoding="utf-8")

            report = build_config_check(config_path)

            self.assertEqual(report["output_root"], str(output_root))
            self.assertEqual(report["supported_settings_keys"], ["schemaVersion", "runtime", "outputRoot"])
            self.assertEqual(report["unsupported_settings_keys"], [])
            self.assertEqual(report["warnings"], [])

    def test_output_setting_update_preserves_other_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings_path = root / "settings.json"
            settings_path.write_text(
                json.dumps(
                    {
                        "outputRoot": str(root / "old"),
                        "runtime": {
                            "instanceName": "test-instance",
                            "apiPort": 19300,
                        },
                        "huggingFaceToken": "secret-token",
                    }
                ),
                encoding="utf-8",
            )

            from timeline_for_chatgpt_worker.settings_service import settings_output_set_payload

            settings_output_set_payload(settings_path, str(root / "new"))

            payload = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["outputRoot"], str(root / "new"))
            self.assertEqual(payload["runtime"]["instanceName"], "test-instance")
            self.assertEqual(payload["runtime"]["apiPort"], 19300)
            self.assertEqual(payload["huggingFaceToken"], "secret-token")

    def test_items_refresh_rebuilds_master_and_download_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            export_path = root / "chatgpt-export.zip"
            write_thread_export_with_tool(export_path)
            settings_path = root / "settings.json"
            output_root = root / "output"
            runs_root = root / ".app-data" / "runs"
            settings_path.write_text(
                json.dumps(
                    {"outputRoot": str(output_root)}
                ),
                encoding="utf-8",
            )

            report = items_refresh_from_file(
                file_path=export_path,
                settings_path=settings_path,
                download_to=root / "handoff",
            )
            listed = items_list_payload(settings_path)
            copied = items_download_latest(settings_path, root / "second-handoff")

            self.assertEqual(report["state"], "completed")
            self.assertEqual(report["manifest"]["item_count"], 1)
            self.assertEqual(listed["item_count"], 1)
            timeline_path = output_root / "conv-master" / "timeline.json"
            convert_path = output_root / "conv-master" / "convert_info.json"
            self.assertTrue(timeline_path.exists())
            self.assertTrue(convert_path.exists())
            thread = json.loads(timeline_path.read_text(encoding="utf-8"))
            convert_info = json.loads(convert_path.read_text(encoding="utf-8"))
            self.assertEqual(thread["title"], "Final exported title")
            self.assertNotIn("title_source", thread)
            self.assertNotIn("title_history_available", thread)
            self.assertEqual([message["role"] for message in thread["messages"]], ["system", "user", "assistant"])
            self.assertEqual(convert_info["title"], "Final exported title")
            self.assertIn("sha256", convert_info["source_export"])
            download_zip_path = Path(str(report["current"]["download_zip_path"]))
            self.assertTrue(download_zip_path.exists())
            self.assertTrue(Path(str(report["current"]["copied_download_path"])).exists())
            self.assertTrue(Path(str(copied["download_path"])).exists())
            with zipfile.ZipFile(download_zip_path) as archive:
                names = set(archive.namelist())
                self.assertIn("README.md", names)
                self.assertIn("items/conv-master/convert_info.json", names)
                self.assertIn("items/conv-master/timeline.json", names)
                self.assertNotIn("items/conv-master/thread.json", names)
                self.assertNotIn("manifest.json", names)
                readme = archive.read("README.md").decode("utf-8")
            self.assertIn("TimelineForChatGPT", readme)
            self.assertTrue((runs_root / "current.json").exists())
            self.assertTrue((runs_root / "refresh-history.jsonl").exists())

    def test_api_server_dispatches_refresh_list_detail_and_download(self) -> None:
        from timeline_for_chatgpt_worker.api_server import handle_request

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            export_path = root / "chatgpt-export.zip"
            write_thread_export_with_tool(export_path)
            settings_path = root / "settings.json"
            output_root = root / "output"
            settings_path.write_text(json.dumps({"outputRoot": str(output_root)}), encoding="utf-8")
            env = {
                "TIMELINE_FOR_CHATGPT_SETTINGS": str(settings_path),
                "TIMELINE_FOR_CHATGPT_OUTPUTS_ROOT": str(root / ".app-data" / "runs"),
                "TIMELINE_FOR_CHATGPT_STATE_ROOT": str(root / ".app-data" / "state"),
                "TIMELINE_FOR_CHATGPT_CACHE_ROOT": str(root / ".app-data" / "cache"),
            }

            with patch.dict(os.environ, env, clear=False):
                status, health = handle_request("GET", "/health", None)
                self.assertEqual(int(status), 200)
                self.assertIs(health, True)

                status, refresh_payload = handle_request(
                    "POST",
                    "/items/refresh",
                    {
                        "filePath": str(export_path),
                        "downloadTo": str(root / "handoff"),
                    },
                )
                self.assertEqual(int(status), 200)
                self.assertEqual(refresh_payload["state"], "completed")
                self.assertEqual(refresh_payload["manifest"]["item_count"], 1)

                status, list_payload = handle_request("POST", "/items/list", {"page": 1, "pageSize": 10})
                self.assertEqual(int(status), 200)
                self.assertEqual(list_payload["item_count"], 1)
                self.assertEqual(list_payload["pagination"]["returned_items"], 1)

                status, detail_payload = handle_request("POST", "/items/detail", {"itemId": "conv-master"})
                self.assertEqual(int(status), 200)
                self.assertTrue(detail_payload["available"])
                self.assertEqual(detail_payload["itemId"], "conv-master")
                self.assertEqual([message["role"] for message in detail_payload["messages"]], ["system", "user", "assistant"])

                status, download_payload = handle_request(
                    "POST",
                    "/items/download",
                    {"to": str(root / "second-handoff"), "overwrite": True},
                )
                self.assertEqual(int(status), 200)
                self.assertTrue(Path(str(download_payload["download_path"])).exists())

    def test_api_server_converts_docker_paths_to_host_paths(self) -> None:
        from timeline_for_chatgpt_worker.api_server import convert_response_paths
        from timeline_for_chatgpt_worker.api_server import to_container_path

        with patch.dict(
            os.environ,
            {
                "TIMELINE_FOR_CHATGPT_DOCKER": "1",
                "TIMELINE_FOR_CHATGPT_HOST_OUTPUT_ROOT": "C:\\TimelineData\\chatgpt",
                "TIMELINE_FOR_CHATGPT_HOST_SETTINGS_PATH": "C:\\apps\\TimelineForChatGPT\\settings.json",
            },
            clear=False,
        ):
            self.assertEqual(to_container_path("C:\\Exports\\chatgpt.zip"), "/mnt/c/Exports/chatgpt.zip")
            converted = convert_response_paths(
                {
                    "settings_path": "/workspace/settings.json",
                    "output_root": "/workspace/output",
                    "timeline_path": "/workspace/output/conv-master/timeline.json",
                    "download_path": "/mnt/c/Users/amano/Downloads/export.zip",
                }
            )

        self.assertEqual(converted["settings_path"], "C:\\apps\\TimelineForChatGPT\\settings.json")
        self.assertEqual(converted["output_root"], "C:\\TimelineData\\chatgpt")
        self.assertEqual(converted["timeline_path"], "C:\\TimelineData\\chatgpt\\conv-master\\timeline.json")
        self.assertEqual(converted["download_path"], "C:\\Users\\amano\\Downloads\\export.zip")

    def test_items_list_paginates_latest_first(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings_path = root / "settings.json"
            output_root = root / "output"
            output_root.mkdir()
            settings_path.write_text(json.dumps({"outputRoot": str(output_root)}), encoding="utf-8")
            (output_root / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "application": "TimelineForChatGPT",
                        "item_count": 3,
                        "items": [
                            {
                                "conversation_id": "old",
                                "title": "Old",
                                "created_at": "2026-01-01T00:00:00+00:00",
                                "updated_at": "2026-01-01T00:01:00+00:00",
                            },
                            {
                                "conversation_id": "new",
                                "title": "New",
                                "created_at": "2026-01-03T00:00:00+00:00",
                                "updated_at": "2026-01-03T00:01:00+00:00",
                            },
                            {
                                "conversation_id": "middle",
                                "title": "Middle",
                                "created_at": "2026-01-02T00:00:00+00:00",
                                "updated_at": "2026-01-02T00:01:00+00:00",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            first_page = items_list_payload(settings_path, page=1, page_size=2)
            second_page = items_list_payload(settings_path, page=2, page_size=2)
            default_items = items_list_payload(settings_path)
            all_items = items_list_payload(settings_path, include_all=True)

            self.assertEqual([item["conversation_id"] for item in default_items["items"]], ["new", "middle", "old"])
            self.assertEqual([item["conversation_id"] for item in all_items["items"]], ["new", "middle", "old"])
            self.assertEqual([item["conversation_id"] for item in first_page["items"]], ["new", "middle"])
            self.assertEqual([item["conversation_id"] for item in second_page["items"]], ["old"])
            self.assertEqual(default_items["pagination"]["mode"], "all")
            self.assertEqual(first_page["pagination"]["page"], 1)
            self.assertEqual(first_page["pagination"]["page_size"], 2)
            self.assertEqual(first_page["pagination"]["total_items"], 3)
            self.assertEqual(first_page["pagination"]["total_pages"], 2)
            self.assertTrue(first_page["pagination"]["has_next"])
            self.assertFalse(second_page["pagination"]["has_next"])

    def test_worker_service_run_creation_processes_zip_without_copying_input(self) -> None:
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
                                "title": "Worker service",
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
                                                "parts": ["hello from worker service"],
                                            },
                                        },
                                    }
                                },
                            }
                        ]
                    ),
                )

            output_root = root / "outputs"
            run_dir = create_run_from_input(
                input_path=upload_path,
                output_root=output_root,
                profile="timeline-default",
                run_id="run-service",
            )
            process_run(run_dir)

            request = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))

            self.assertEqual(request["input_items"][0]["uploaded_path"], str(upload_path))
            self.assertTrue(upload_path.exists())
            self.assertEqual(status["state"], "completed")
            self.assertTrue((run_dir / "run-service.zip").exists())

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

            run_dir = root / "run-test"
            run_dir.mkdir()
            request = {
                "schema_version": 1,
                "run_id": "run-test",
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
                json.dumps({"schema_version": 1, "run_id": "run-test", "state": "pending"}),
                encoding="utf-8",
            )

            process_run(run_dir)

            archive_path = run_dir / "run-test.zip"
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


def write_thread_export_with_tool(path: Path) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("export_manifest.json", "{}")
        archive.writestr(
            "conversations.json",
            json.dumps(
                [
                    {
                        "id": "conv-master",
                        "conversation_id": "conv-master",
                        "title": "Final exported title",
                        "create_time": "2026-01-01T00:00:00Z",
                        "update_time": "2026-01-01T00:03:00Z",
                        "current_node": "n4",
                        "mapping": {
                            "n1": {
                                "id": "n1",
                                "parent": None,
                                "children": ["n2"],
                                "message": {
                                    "id": "m-system",
                                    "author": {"role": "system"},
                                    "create_time": "2026-01-01T00:00:00Z",
                                    "content": {
                                        "content_type": "text",
                                        "parts": ["system context"],
                                    },
                                },
                            },
                            "n2": {
                                "id": "n2",
                                "parent": "n1",
                                "children": ["n3"],
                                "message": {
                                    "id": "m-user",
                                    "author": {"role": "user"},
                                    "create_time": "2026-01-01T00:01:00Z",
                                    "content": {
                                        "content_type": "text",
                                        "parts": ["hello"],
                                    },
                                },
                            },
                            "n3": {
                                "id": "n3",
                                "parent": "n2",
                                "children": ["n4"],
                                "message": {
                                    "id": "m-tool",
                                    "author": {"role": "tool"},
                                    "create_time": "2026-01-01T00:02:00Z",
                                    "content": {
                                        "content_type": "execution_output",
                                        "parts": ["tool output"],
                                    },
                                },
                            },
                            "n4": {
                                "id": "n4",
                                "parent": "n3",
                                "children": [],
                                "message": {
                                    "id": "m-assistant",
                                    "author": {"role": "assistant"},
                                    "create_time": "2026-01-01T00:03:00Z",
                                    "content": {
                                        "content_type": "text",
                                        "parts": ["answer"],
                                    },
                                },
                            },
                        },
                    }
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()
