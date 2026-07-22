import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.publish_history import main


class PublishHistoryTest(unittest.TestCase):
    def publish(self, pages: Path, run_number: int, run_id: int, mode: str) -> None:
        summary_path = pages.parent / f"summary-{run_id}.json"
        summary_path.write_text(json.dumps({
            "generated_at": f"2026-01-{run_number:02d}T00:00:00+00:00",
            "scenario": {
                "controller_install_order": mode,
                "workloads": 10,
                "nodes": 2,
            },
            "controller": {"max_cpu_mcores": 100, "max_memory_mib": 200},
            "data_status": "valid",
        }), encoding="utf-8")
        with patch.object(sys, "argv", [
            "publish_history.py",
            "--summary-json", str(summary_path),
            "--pages-dir", str(pages),
            "--repository", "example/perf",
            "--run-id", str(run_id),
            "--run-number", str(run_number),
            "--run-attempt", "1",
            "--sha", "abc123",
            "--ref-name", "main",
            "--status", "success",
        ]):
            self.assertEqual(main(), 0)

    def test_history_is_sorted_by_run_not_publish_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pages = Path(directory) / "pages"
            self.publish(pages, 20, 200, "before-workload-ramp")
            self.publish(pages, 19, 190, "after-workload-ramp")

            history = json.loads((pages / "history.json").read_text(encoding="utf-8"))
            self.assertEqual([entry["run_number"] for entry in history], [20, 19])
            latest = json.loads((pages / "latest.json").read_text(encoding="utf-8"))
            self.assertEqual(latest["run_number"], 20)


if __name__ == "__main__":
    unittest.main()
