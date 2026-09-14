import tempfile
import unittest
from pathlib import Path

from scripts.build_memory_scenario import compaction_supported, crd_version_for, main


class MemoryScenarioTest(unittest.TestCase):
    def test_release_crd_mapping_and_support(self):
        self.assertEqual(crd_version_for("1.9.1"), "1.9.0")
        self.assertFalse(compaction_supported("1.9.1"))
        self.assertTrue(compaction_supported("1.10.0"))

    def test_passive_old_release_has_no_compaction_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            main_args = ["--output-dir", directory, "--release", "1.8.0", "--workloads", "4", "--nodes", "2", "--namespace-count", "1", "--deployments", "1", "--statefulsets", "1", "--cronjobs", "1", "--daemonsets", "1"]
            import sys
            old = sys.argv
            sys.argv = ["build_memory_scenario.py", *main_args]
            try:
                self.assertEqual(main(), 0)
            finally:
                sys.argv = old
            self.assertFalse((Path(directory) / "compaction-policy.yaml").exists())

    def test_active_scenario_writes_compaction_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            import sys
            old = sys.argv
            sys.argv = ["build_memory_scenario.py", "--output-dir", directory, "--release", "1.10.0", "--mode", "active", "--workloads", "4", "--nodes", "2", "--namespace-count", "1", "--deployments", "1", "--statefulsets", "1", "--cronjobs", "1", "--daemonsets", "1"]
            try:
                self.assertEqual(main(), 0)
            finally:
                sys.argv = old
            self.assertTrue((Path(directory) / "compaction-policy.yaml").exists())
