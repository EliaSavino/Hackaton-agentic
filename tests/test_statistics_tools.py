from __future__ import annotations

import unittest

from hackathon_agents.tools.statistics_tools import (
    bootstrap_confidence_interval,
    classification_metrics,
    compare_groups,
    correlation,
    describe_series,
    detect_outliers,
    linear_regression,
    one_way_anova,
)


class StatisticsToolsTests(unittest.TestCase):
    def test_describe_series_from_rows(self) -> None:
        result = describe_series({"rows": [{"yield": "0.1"}, {"yield": "0.3"}, {"yield": "0.5"}], "column": "yield"})

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data["count"], 3)
        self.assertAlmostEqual(result.data["mean"], 0.3)

    def test_linear_regression_recovers_line(self) -> None:
        result = linear_regression({"x": [0, 1, 2, 3], "y": [1, 3, 5, 7]})

        self.assertTrue(result.ok, result.error)
        self.assertAlmostEqual(result.data["slope"], 2.0)
        self.assertAlmostEqual(result.data["intercept"], 1.0)
        self.assertAlmostEqual(result.data["r_squared"], 1.0)

    def test_compare_groups_returns_effect_size(self) -> None:
        result = compare_groups({"control": [1, 2, 3], "treatment": [3, 4, 5]})

        self.assertTrue(result.ok, result.error)
        self.assertGreater(result.data["cohens_d"], 0)

    def test_bootstrap_confidence_interval_is_deterministic(self) -> None:
        first = bootstrap_confidence_interval({"values": [1, 2, 3, 4], "iterations": 200, "seed": 123})
        second = bootstrap_confidence_interval({"values": [1, 2, 3, 4], "iterations": 200, "seed": 123})

        self.assertTrue(first.ok, first.error)
        self.assertEqual(first.data["lower"], second.data["lower"])
        self.assertLessEqual(first.data["lower"], first.data["estimate"])
        self.assertGreaterEqual(first.data["upper"], first.data["estimate"])

    def test_correlation_supports_spearman(self) -> None:
        result = correlation({"x": [1, 2, 3], "y": [3, 2, 1], "method": "spearman"})

        self.assertTrue(result.ok, result.error)
        self.assertAlmostEqual(result.data["correlation"], -1.0)

    def test_detect_outliers_iqr(self) -> None:
        result = detect_outliers({"values": [1, 2, 2, 3, 100]})

        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data["outliers"][0]["value"], 100)

    def test_one_way_anova_returns_effect_size(self) -> None:
        result = one_way_anova({"groups": {"low": [1, 2, 3], "high": [5, 6, 7]}})

        self.assertTrue(result.ok, result.error)
        self.assertGreater(result.data["f_statistic"], 0)
        self.assertGreater(result.data["eta_squared"], 0)

    def test_classification_metrics(self) -> None:
        result = classification_metrics({"y_true": [1, 0, 1, 0], "y_pred": [1, 0, 0, 0], "positive_label": 1})

        self.assertTrue(result.ok, result.error)
        self.assertAlmostEqual(result.data["precision"], 1.0)
        self.assertAlmostEqual(result.data["recall"], 0.5)


if __name__ == "__main__":
    unittest.main()
