import unittest

from benchmarks.api_load import percentile, run


class PerformanceBaselineTest(unittest.IsolatedAsyncioTestCase):
    def test_percentile_is_deterministic(self) -> None:
        self.assertEqual(3, percentile([5, 1, 4, 2, 3], 0.5))
        self.assertEqual(5, percentile([5, 1, 4, 2, 3], 0.99))

    async def test_small_profile_has_no_http_errors(self) -> None:
        report = await run(iterations=30, concurrency=5)
        self.assertEqual(0, report["error_rate"])
        self.assertEqual(30, sum(report["statuses"].values()))
        self.assertGreater(report["throughput_rps"], 0)


if __name__ == "__main__":
    unittest.main()
