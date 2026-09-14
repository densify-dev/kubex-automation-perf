import unittest

from scripts.compare_memory_releases import compare


def summary(release: str, mib: float, mode: str = "passive"):
    return {"release": release, "mode": mode, "status": "valid", "manager": {"post_gc_memory_bytes": mib * 1024 * 1024}}


class ReleaseComparisonTest(unittest.TestCase):
    def test_requires_both_absolute_and_percentage_thresholds(self):
        result = compare([summary("1.8.0", 200), summary("1.9.0", 250)])[0]
        self.assertTrue(result["flagged"])
        result = compare([summary("1.8.0", 400), summary("1.9.0", 449)])[0]
        self.assertFalse(result["flagged"])

    def test_does_not_compare_modes(self):
        result = compare([summary("1.10.0", 200, "passive"), summary("1.10.0", 500, "active")])
        self.assertEqual(result, [])
