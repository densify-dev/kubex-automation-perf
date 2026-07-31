import subprocess
import unittest
from unittest.mock import patch

from scripts.count_resources import POD_QUERY, collect_counts, kubectl_count


class CountResourcesTest(unittest.TestCase):
    def test_counts_workloads_and_other_resources(self) -> None:
        def run(command, **kwargs):
            resource = command[2]
            if resource == "deploy":
                output = "one\ntwo\n"
            elif resource in {"statefulsets", "cronjobs", "daemonsets"}:
                output = "one\n"
            elif resource == "rs":
                output = "one\ntwo\n"
            elif "-A" in command:
                output = "one\ntwo\nthree\n"
            else:
                output = "controller\n"
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

    def test_pod_query_counts_table_rows(self) -> None:
        result = subprocess.CompletedProcess([], 0, "pod-one\npod-two\n\n", "")
        with patch("scripts.count_resources.subprocess.run", return_value=result) as run:
            self.assertEqual(kubectl_count(POD_QUERY, 60), 2)

        command = run.call_args.args[0]
        self.assertEqual(command[2:6], ["pod", "-A", "-l", "app.kubernetes.io/name=kwok-perf"])
        self.assertIn("--request-timeout=60s", command)


if __name__ == "__main__":
    unittest.main()
