import base64
import http.client
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.inject_host_aliases import inject
from scripts.validate_stack_upload import _load_state, main as validate_main


class StackValidationHelpersTest(unittest.TestCase):
    def test_load_state_retries_disconnected_port_forward(self) -> None:
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"uploads": []}'
        with (
            patch(
                "scripts.validate_stack_upload.urllib.request.urlopen",
                side_effect=[http.client.RemoteDisconnected(), response],
            ) as urlopen,
            patch("scripts.validate_stack_upload.time.sleep"),
        ):
            self.assertEqual(_load_state("http://127.0.0.1/state", 10), {"uploads": []})

        self.assertEqual(urlopen.call_count, 2)

    def test_inject_host_aliases_into_job_and_cronjob(self) -> None:
        rendered = "\n".join(
            [
                "apiVersion: batch/v1",
                "kind: Job",
                "metadata:",
                "  name: example",
                "spec:",
                "  template:",
                "    spec:",
                "      initContainers:",
                "      - name: init",
                "      containers:",
                "      - name: main",
                "      restartPolicy: Never",
                "---",
                "apiVersion: batch/v1",
                "kind: CronJob",
                "metadata:",
                "  name: example-cron",
                "spec:",
                "  jobTemplate:",
                "    spec:",
                "      template:",
                "        spec:",
                "          containers:",
                "          - name: main",
                "          restartPolicy: Never",
            ]
        )

        transformed = inject(rendered, "fake.kubex.ai", "10.0.0.10")
        self.assertIn("hostAliases:", transformed)
        self.assertIn("- ip: 10.0.0.10", transformed)
        self.assertIn("- fake.kubex.ai", transformed)

    def test_validate_upload_accepts_zip_archive_members(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.json"

            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, mode="w") as archive:
                for path in [
                    "cluster/config.csv",
                    "cluster/attributes.csv",
                    "node/config.csv",
                    "node/attributes.csv",
                    "container/config.csv",
                    "container/attributes.csv",
                ]:
                    archive.writestr(path, "name,value\n")

            state.write_text(
                json.dumps(
                    {
                        "uploads": [
                            {
                                "body_b64": base64.b64encode(buffer.getvalue()).decode("ascii"),
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with patch("sys.argv", ["validate_stack_upload.py", "--state", str(state)]):
                self.assertEqual(validate_main(), 0)


if __name__ == "__main__":
    unittest.main()
