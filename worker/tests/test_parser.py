from __future__ import annotations

import unittest

from timeline_for_chatgpt_worker.contracts import ParserOptions, RunRequest
from timeline_for_chatgpt_worker.parser import normalize_conversation


def make_request() -> RunRequest:
    return RunRequest(
        schema_version=1,
        run_id="run-test",
        created_at="2026-04-05T00:00:00+00:00",
        output_root_id="default",
        output_root_path="/tmp",
        profile="timeline-default",
        reprocess_duplicates=False,
        parser_options=ParserOptions(),
        input_items=[],
    )


class NormalizeConversationTests(unittest.TestCase):
    def test_current_branch_produces_event_envelope_and_turn_segments(self) -> None:
        conversation = {
            "id": "conv-1",
            "conversation_id": "conv-1",
            "title": "Branching test",
            "create_time": "2026-01-01T00:00:00Z",
            "update_time": "2026-01-01T00:02:00Z",
            "current_node": "n3b",
            "mapping": {
                "n1": {
                    "id": "n1",
                    "parent": None,
                    "children": ["n2"],
                    "message": {
                        "id": "m1",
                        "author": {"role": "user"},
                        "create_time": "2026-01-01T00:00:00Z",
                        "content": {"content_type": "text", "parts": ["hello world from user"]},
                    },
                },
                "n2": {
                    "id": "n2",
                    "parent": "n1",
                    "children": ["n3a", "n3b"],
                    "message": {
                        "id": "m2",
                        "author": {"role": "assistant"},
                        "create_time": "2026-01-01T00:01:00Z",
                        "content": {"content_type": "text", "parts": ["first answer branch"]},
                    },
                },
                "n3a": {
                    "id": "n3a",
                    "parent": "n2",
                    "children": [],
                    "message": {
                        "id": "m3a",
                        "author": {"role": "assistant"},
                        "create_time": "2026-01-01T00:01:30Z",
                        "content": {"content_type": "text", "parts": ["unselected branch"]},
                    },
                },
                "n3b": {
                    "id": "n3b",
                    "parent": "n2",
                    "children": [],
                    "message": {
                        "id": "m3b",
                        "author": {"role": "assistant"},
                        "create_time": "2026-01-01T00:02:00Z",
                        "content": {"content_type": "text", "parts": ["selected branch"]},
                    },
                },
            },
        }

        normalized = normalize_conversation(conversation, make_request())

        self.assertEqual(
            [message["message_id"] for message in normalized["messages"]],
            ["m1", "m2", "m3b"],
        )
        self.assertEqual(normalized["summary"]["event_count"], 3)
        self.assertEqual(normalized["summary"]["segment_count"], 1)

        first_event = normalized["events"][0]
        self.assertEqual(first_event["source_type"], "chatgpt_export")
        self.assertEqual(first_event["source_unit_id"], "conv-1")
        self.assertEqual(first_event["event_id"], "m1")
        self.assertEqual(first_event["actor"], "user")
        self.assertEqual(first_event["kind"], "message")
        self.assertIn("payload", first_event)

        first_segment = normalized["segments"][0]
        self.assertEqual(first_segment["event_ids"], ["m1", "m2", "m3b"])
        self.assertIn("user -> assistant", first_segment["summary"])

    def test_second_user_message_starts_new_segment_and_assets_stay_in_artifacts(self) -> None:
        conversation = {
            "id": "conv-2",
            "conversation_id": "conv-2",
            "title": "Second turn",
            "current_node": "n4",
            "mapping": {
                "n1": {
                    "id": "n1",
                    "parent": None,
                    "children": ["n2"],
                    "message": {
                        "id": "m1",
                        "author": {"role": "user"},
                        "create_time": "2026-01-01T00:00:00Z",
                        "content": {"content_type": "text", "parts": ["first turn question"]},
                    },
                },
                "n2": {
                    "id": "n2",
                    "parent": "n1",
                    "children": ["n3"],
                    "message": {
                        "id": "m2",
                        "author": {"role": "assistant"},
                        "create_time": "2026-01-01T00:00:10Z",
                        "content": {
                            "content_type": "multimodal_text",
                            "parts": [
                                "first turn answer",
                                {
                                    "attachment_id": "att-1",
                                    "logical_path": "images/example.png",
                                },
                            ],
                        },
                    },
                },
                "n3": {
                    "id": "n3",
                    "parent": "n2",
                    "children": ["n4"],
                    "message": {
                        "id": "m3",
                        "author": {"role": "user"},
                        "create_time": "2026-01-01T00:05:00Z",
                        "content": {"content_type": "text", "parts": ["second turn question"]},
                    },
                },
                "n4": {
                    "id": "n4",
                    "parent": "n3",
                    "children": [],
                    "message": {
                        "id": "m4",
                        "author": {"role": "tool"},
                        "create_time": "2026-01-01T00:05:05Z",
                        "content": {"content_type": "execution_output", "parts": ["tool output"]},
                    },
                },
            },
        }

        normalized = normalize_conversation(conversation, make_request())

        self.assertEqual(len(normalized["segments"]), 2)
        self.assertEqual(normalized["segments"][0]["event_ids"], ["m1", "m2"])
        self.assertEqual(normalized["segments"][1]["event_ids"], ["m3", "m4"])
        self.assertEqual(normalized["events"][1]["artifacts"][0]["kind"], "image")
        self.assertEqual(normalized["events"][1]["artifacts"][0]["conversation_id"], "conv-2")
        self.assertEqual(normalized["events"][1]["artifacts"][0]["message_id"], "m2")
        self.assertEqual(normalized["events"][1]["artifacts"][0]["relative_path"], "images/example.png")
        self.assertIsNone(normalized["events"][1]["artifacts"][0]["hash_sha256"])
        self.assertEqual(normalized["events"][3]["kind"], "tool_result")
        self.assertIn("Segments: `2`", normalized["timeline_markdown"])


if __name__ == "__main__":
    unittest.main()
