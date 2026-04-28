from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from timeline_for_chatgpt_worker.processor import process_job


class ProcessJobTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
