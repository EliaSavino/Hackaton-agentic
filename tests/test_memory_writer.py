from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hackathon_agents.tools.memory_writer import append_project_memory


class MemoryWriterTests(unittest.TestCase):
    def test_append_project_memory_writes_jsonl_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jsonl_path = Path(tmp) / "project_memory.jsonl"
            markdown_path = Path(tmp) / "project_memory.md"

            result = append_project_memory(
                {
                    "jsonl_path": str(jsonl_path),
                    "markdown_path": str(markdown_path),
                    "event_type": "planner_completed",
                    "summary": "Created a plan for follow-up users.",
                    "run_id": "run-1",
                    "run_dir": "runs/run-1",
                    "user_request": "Find candidates",
                    "node": "planner",
                    "iteration": 0,
                    "run_mode": "cheap",
                    "candidate_count": 0,
                    "recent_messages": ["planner: created deterministic discovery plan"],
                }
            )

            self.assertTrue(result.ok)
            self.assertTrue(jsonl_path.exists())
            self.assertTrue(markdown_path.exists())

            entries = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(entries[0]["event_type"], "planner_completed")
            self.assertEqual(entries[0]["summary"], "Created a plan for follow-up users.")
            markdown = markdown_path.read_text(encoding="utf-8")
            self.assertIn("Project Memory", markdown)
            self.assertIn("Created a plan for follow-up users.", markdown)


if __name__ == "__main__":
    unittest.main()
