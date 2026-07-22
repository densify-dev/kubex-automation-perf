import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.summarize_metrics import main, parse_top_pod


class ParseTopPodTest(unittest.TestCase):
    def test_tracks_cpu_and_memory_maxima_independently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "top-pod.txt"
            snapshot.write_text(
                "NAME CPU(cores) MEMORY(bytes)\n"
                "cpu-heavy 750m 128Mi\n"
                "memory-heavy 125m 2Gi\n",
                encoding="utf-8",
            )
            self.assertEqual(
                parse_top_pod(snapshot),
                {"cpu_mcores": 750.0, "memory_bytes": 2 * 1024**3},
            )

    def test_summary_uses_latest_nonempty_metrics_and_counts_valid_top_samples(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metrics = root / "metrics"
            final = root / "final"
            report = root / "report"
            (metrics / "metrics").mkdir(parents=True)
            (metrics / "top").mkdir()
            (metrics / "snapshots").mkdir()
            final.mkdir()
            metadata = root / "metadata.json"
            metadata.write_text(json.dumps({
                "workloads": 4,
                "nodes": 2,
                "namespace_count": 1,
                "batch_files": 1,
                "controller_install_order": "before-workload-ramp",
                "workload_kind_counts": {
                    "Deployment": 1,
                    "StatefulSet": 1,
                    "CronJob": 1,
                    "DaemonSet": 1,
                },
            }), encoding="utf-8")
            (metrics / "metrics" / "metrics-001.prom").write_text(
                "go_goroutines 12\nworkqueue_depth{controller=\"a\"} 3\n",
                encoding="utf-8",
            )
            (metrics / "metrics" / "metrics-001.status").write_text(
                "status=success\nbytes=60\n", encoding="utf-8"
            )
            (metrics / "metrics" / "metrics-002.prom").write_text("", encoding="utf-8")
            (metrics / "metrics" / "metrics-002.status").write_text(
                "status=error\nreason=curl_failed\n", encoding="utf-8"
            )
            (metrics / "top" / "top-pod-001.txt").write_text(
                "NAME CPU(cores) MEMORY(bytes)\ncontroller 250m 512Mi\n",
                encoding="utf-8",
            )
            (metrics / "top" / "top-pod-002.txt").write_text(
                "error: Metrics API not available\n", encoding="utf-8"
            )
            (final / "counts.txt").write_text(
                "deployments=1\nstatefulsets=1\ncronjobs=1\ndaemonsets=1\npods=4\n",
                encoding="utf-8",
            )

            with patch.object(sys, "argv", [
                "summarize_metrics.py",
                "--metadata", str(metadata),
                "--metrics-dir", str(metrics),
                "--final-dir", str(final),
                "--output-dir", str(report),
            ]):
                self.assertEqual(main(), 0)

            summary = json.loads((report / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["metrics"]["go_goroutines"], 12)
            self.assertEqual(summary["samples"]["valid_metrics_snapshots"], 1)
            self.assertEqual(summary["samples"]["top_snapshots"], 2)
            self.assertEqual(summary["samples"]["valid_top_snapshots"], 1)
            self.assertEqual(summary["controller"]["max_cpu_mcores"], 250)
            self.assertEqual(summary["controller"]["max_memory_mib"], 512)
            self.assertEqual(summary["data_status"], "degraded")

    def test_missing_measurements_are_null_instead_of_zero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metrics = root / "metrics"
            final = root / "final"
            report = root / "report"
            (metrics / "metrics").mkdir(parents=True)
            (metrics / "top").mkdir()
            (metrics / "snapshots").mkdir()
            final.mkdir()
            metadata = root / "metadata.json"
            metadata.write_text(json.dumps({
                "workloads": 0,
                "nodes": 0,
                "namespace_count": 1,
                "batch_files": 0,
                "workload_kind_counts": {},
            }), encoding="utf-8")
            (final / "counts.txt").write_text("pods=unavailable\n", encoding="utf-8")

            with patch.object(sys, "argv", [
                "summarize_metrics.py",
                "--metadata", str(metadata),
                "--metrics-dir", str(metrics),
                "--final-dir", str(final),
                "--output-dir", str(report),
            ]):
                self.assertEqual(main(), 0)

            summary = json.loads((report / "summary.json").read_text(encoding="utf-8"))
            self.assertIsNone(summary["controller"]["max_cpu_mcores"])
            self.assertIsNone(summary["controller"]["max_memory_mib"])
            self.assertEqual(summary["data_status"], "degraded")
            self.assertTrue(any("pods" in issue for issue in summary["data_issues"]))

if __name__ == "__main__":
    unittest.main()
