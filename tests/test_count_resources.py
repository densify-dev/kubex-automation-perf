import subprocess
import unittest
from unittest.mock import patch

from scripts.count_resources import collect_counts


class CountResourcesTest(unittest.TestCase):
    def test_counts_combined_workloads_and_other_resources(self) -> None:
        def run(command, **kwargs):
            resource = command[2]
            if resource.startswith("deploy,"):
                output = "\n".join([
                    "deployment.apps/one",
                    "deployment.apps/two",
                    "statefulset.apps/one",
                    "cronjob.batch/one",
                    "daemonset.apps/one",
                ])
            elif resource == "rs":
                output = "replicaset.apps/one\nreplicaset.apps/two\n"
            elif "-A" in command:
                output = "pod/one\npod/two\npod/three\n"
            else:
                output = "pod/controller\n"
            return subprocess.CompletedProcess(command, 0, output, "")

        with patch("scripts.count_resources.subprocess.run", side_effect=run):
            self.assertEqual(collect_counts("kubex", 90), {
                "deployments": 2,
                "statefulsets": 1,
                "cronjobs": 1,
                "daemonsets": 1,
                "pods": 3,
                "replicasets": 2,
                "controller_pods": 1,
                "workloads": 5,
            })

    def test_marks_only_failed_query_as_unavailable(self) -> None:
        def run(command, **kwargs):
            if command[2] == "pod" and "-A" in command:
                raise subprocess.TimeoutExpired(command, kwargs["timeout"])
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch("scripts.count_resources.subprocess.run", side_effect=run):
            counts = collect_counts("kubex", 90)

        self.assertIsNone(counts["pods"])
        self.assertEqual(counts["workloads"], 0)
        self.assertEqual(counts["controller_pods"], 0)


if __name__ == "__main__":
    unittest.main()
