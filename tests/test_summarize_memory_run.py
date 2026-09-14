import tempfile
import unittest
from pathlib import Path

from scripts.summarize_memory_run import summarize


class MemorySummaryTest(unittest.TestCase):
    def test_uses_post_gc_rss_not_heap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "metrics" / "phases").mkdir(parents=True)
            (root / "metrics" / "metrics").mkdir()
            (root / "metrics" / "phases" / "soak-start.timestamp").write_text("2026-01-01T00:00:00Z")
            (root / "metrics" / "phases" / "soak-end.timestamp").write_text("2026-01-01T00:10:00Z")
            samples = [
                ("000000Z", 100, 50),
                ("000015Z", 120, 50),
                ("000030Z", 130, 60),
                ("000045Z", 140, 60),
            ]
            for stamp, rss, gc in samples:
                (root / "metrics" / "metrics" / f"metrics-20260101T{stamp}.prom").write_text(
                    f"process_resident_memory_bytes {rss * 1024 * 1024}\n"
                    f"go_memstats_heap_alloc_bytes 999999\n"
                    f"go_memstats_last_gc_time_seconds {gc}\n"
                )
            summary, rows = summarize(root / "metrics", {"release": "1.10.0", "mode": "passive"})
            self.assertEqual(summary["status"], "valid")
            self.assertEqual(summary["manager"]["post_gc_memory_bytes"], 130 * 1024 * 1024)
            self.assertEqual(len(rows), 4)
