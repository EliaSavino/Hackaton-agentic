from __future__ import annotations

import math
import random
import statistics
from typing import Any, Literal

from pydantic import BaseModel, Field

from hackathon_agents.tools.base import error_result, ok_result


class SeriesInput(BaseModel):
    values: list[float] | None = None
    rows: list[dict[str, Any]] | None = None
    column: str | None = None


class LinearRegressionInput(BaseModel):
    x: list[float]
    y: list[float]


class GroupComparisonInput(BaseModel):
    control: list[float]
    treatment: list[float]


class BootstrapCIInput(BaseModel):
    values: list[float]
    statistic: str = "mean"
    iterations: int = Field(default=1000, ge=100, le=20000)
    confidence_level: float = Field(default=0.95, gt=0.0, lt=1.0)
    seed: int = 1729


class CorrelationInput(BaseModel):
    x: list[float]
    y: list[float]
    method: Literal["pearson", "spearman"] = "pearson"


class OutlierDetectionInput(BaseModel):
    values: list[float]
    method: Literal["iqr", "zscore"] = "iqr"
    threshold: float | None = None


class OneWayAnovaInput(BaseModel):
    groups: dict[str, list[float]]


class ClassificationMetricsInput(BaseModel):
    y_true: list[str | int | bool]
    y_pred: list[str | int | bool]
    positive_label: str | int | bool = 1


def describe_series(input_data: SeriesInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, SeriesInput) else SeriesInput.model_validate(input_data)
    try:
        values = _extract_values(parsed)
        if not values:
            return error_result("No numeric values were provided.")
        sorted_values = sorted(values)
        data = {
            "count": len(values),
            "mean": statistics.fmean(values),
            "median": statistics.median(values),
            "min": sorted_values[0],
            "max": sorted_values[-1],
            "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
            "variance": statistics.variance(values) if len(values) > 1 else 0.0,
            "q1": _quantile(sorted_values, 0.25),
            "q3": _quantile(sorted_values, 0.75),
            "missing_count": _missing_count(parsed),
        }
        data["iqr"] = data["q3"] - data["q1"]
        return ok_result(data)
    except Exception as exc:
        return error_result(str(exc), {"column": parsed.column})


def linear_regression(input_data: LinearRegressionInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, LinearRegressionInput) else LinearRegressionInput.model_validate(input_data)
    try:
        if len(parsed.x) != len(parsed.y):
            return error_result("x and y must have the same length.")
        if len(parsed.x) < 2:
            return error_result("At least two observations are required.")
        x_mean = statistics.fmean(parsed.x)
        y_mean = statistics.fmean(parsed.y)
        sxx = sum((x - x_mean) ** 2 for x in parsed.x)
        if sxx == 0:
            return error_result("x values have zero variance.")
        sxy = sum((x - x_mean) * (y - y_mean) for x, y in zip(parsed.x, parsed.y))
        slope = sxy / sxx
        intercept = y_mean - slope * x_mean
        fitted = [intercept + slope * x for x in parsed.x]
        residuals = [y - y_hat for y, y_hat in zip(parsed.y, fitted)]
        rss = sum(residual**2 for residual in residuals)
        tss = sum((y - y_mean) ** 2 for y in parsed.y)
        r_squared = 1.0 - rss / tss if tss else 1.0
        rmse = math.sqrt(rss / len(parsed.y))
        return ok_result(
            {
                "slope": slope,
                "intercept": intercept,
                "r_squared": r_squared,
                "rmse": rmse,
                "residuals": residuals,
                "fitted": fitted,
            }
        )
    except Exception as exc:
        return error_result(str(exc), {"n": len(parsed.x)})


def compare_groups(input_data: GroupComparisonInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, GroupComparisonInput) else GroupComparisonInput.model_validate(input_data)
    try:
        if len(parsed.control) < 2 or len(parsed.treatment) < 2:
            return error_result("Both groups need at least two observations.")
        control_mean = statistics.fmean(parsed.control)
        treatment_mean = statistics.fmean(parsed.treatment)
        control_var = statistics.variance(parsed.control)
        treatment_var = statistics.variance(parsed.treatment)
        delta = treatment_mean - control_mean
        pooled_sd = math.sqrt(
            ((len(parsed.control) - 1) * control_var + (len(parsed.treatment) - 1) * treatment_var)
            / (len(parsed.control) + len(parsed.treatment) - 2)
        )
        standard_error = math.sqrt(control_var / len(parsed.control) + treatment_var / len(parsed.treatment))
        t_statistic = delta / standard_error if standard_error else math.inf
        cohens_d = delta / pooled_sd if pooled_sd else math.inf
        return ok_result(
            {
                "control_mean": control_mean,
                "treatment_mean": treatment_mean,
                "difference": delta,
                "fold_change": treatment_mean / control_mean if control_mean else math.inf,
                "t_statistic_welch": t_statistic,
                "cohens_d": cohens_d,
                "control_n": len(parsed.control),
                "treatment_n": len(parsed.treatment),
            }
        )
    except Exception as exc:
        return error_result(str(exc))


def bootstrap_confidence_interval(input_data: BootstrapCIInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, BootstrapCIInput) else BootstrapCIInput.model_validate(input_data)
    try:
        if not parsed.values:
            return error_result("No values were provided.")
        statistic_fn = _statistic(parsed.statistic)
        rng = random.Random(parsed.seed)
        estimates = []
        for _ in range(parsed.iterations):
            sample = [rng.choice(parsed.values) for _ in parsed.values]
            estimates.append(float(statistic_fn(sample)))
        estimates.sort()
        alpha = 1.0 - parsed.confidence_level
        lower = _quantile(estimates, alpha / 2.0)
        upper = _quantile(estimates, 1.0 - alpha / 2.0)
        return ok_result(
            {
                "statistic": parsed.statistic,
                "estimate": float(statistic_fn(parsed.values)),
                "lower": lower,
                "upper": upper,
                "confidence_level": parsed.confidence_level,
                "iterations": parsed.iterations,
                "seed": parsed.seed,
            }
        )
    except Exception as exc:
        return error_result(str(exc), {"statistic": parsed.statistic})


def correlation(input_data: CorrelationInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, CorrelationInput) else CorrelationInput.model_validate(input_data)
    try:
        if len(parsed.x) != len(parsed.y):
            return error_result("x and y must have the same length.")
        if len(parsed.x) < 2:
            return error_result("At least two paired observations are required.")
        x = _ranks(parsed.x) if parsed.method == "spearman" else parsed.x
        y = _ranks(parsed.y) if parsed.method == "spearman" else parsed.y
        coefficient = _pearson(x, y)
        return ok_result({"method": parsed.method, "correlation": coefficient, "n": len(parsed.x)})
    except Exception as exc:
        return error_result(str(exc), {"method": parsed.method})


def detect_outliers(input_data: OutlierDetectionInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, OutlierDetectionInput) else OutlierDetectionInput.model_validate(input_data)
    try:
        if len(parsed.values) < 3:
            return error_result("At least three values are required for outlier detection.")
        rows = []
        if parsed.method == "iqr":
            threshold = parsed.threshold if parsed.threshold is not None else 1.5
            sorted_values = sorted(parsed.values)
            q1 = _quantile(sorted_values, 0.25)
            q3 = _quantile(sorted_values, 0.75)
            iqr = q3 - q1
            lower = q1 - threshold * iqr
            upper = q3 + threshold * iqr
            rows = [
                {"index": index, "value": value, "score": None, "reason": "outside_iqr_fence"}
                for index, value in enumerate(parsed.values)
                if value < lower or value > upper
            ]
            return ok_result({"method": parsed.method, "outliers": rows, "lower_fence": lower, "upper_fence": upper, "threshold": threshold})
        threshold = parsed.threshold if parsed.threshold is not None else 3.0
        mean = statistics.fmean(parsed.values)
        stdev = statistics.stdev(parsed.values)
        if stdev == 0:
            return ok_result({"method": parsed.method, "outliers": [], "threshold": threshold, "mean": mean, "stdev": stdev})
        rows = []
        for index, value in enumerate(parsed.values):
            z_score = (value - mean) / stdev
            if abs(z_score) > threshold:
                rows.append({"index": index, "value": value, "score": z_score, "reason": "abs_zscore_gt_threshold"})
        return ok_result({"method": parsed.method, "outliers": rows, "threshold": threshold, "mean": mean, "stdev": stdev})
    except Exception as exc:
        return error_result(str(exc), {"method": parsed.method})


def one_way_anova(input_data: OneWayAnovaInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, OneWayAnovaInput) else OneWayAnovaInput.model_validate(input_data)
    try:
        groups = {name: values for name, values in parsed.groups.items() if values}
        if len(groups) < 2:
            return error_result("At least two non-empty groups are required.")
        all_values = [value for values in groups.values() for value in values]
        if len(all_values) <= len(groups):
            return error_result("Each group needs enough observations to estimate within-group variance.")
        grand_mean = statistics.fmean(all_values)
        ss_between = sum(len(values) * (statistics.fmean(values) - grand_mean) ** 2 for values in groups.values())
        ss_within = sum(sum((value - statistics.fmean(values)) ** 2 for value in values) for values in groups.values())
        df_between = len(groups) - 1
        df_within = len(all_values) - len(groups)
        ms_between = ss_between / df_between
        ms_within = ss_within / df_within if df_within else math.inf
        f_statistic = ms_between / ms_within if ms_within else math.inf
        eta_squared = ss_between / (ss_between + ss_within) if (ss_between + ss_within) else 0.0
        return ok_result(
            {
                "f_statistic": f_statistic,
                "df_between": df_between,
                "df_within": df_within,
                "ss_between": ss_between,
                "ss_within": ss_within,
                "eta_squared": eta_squared,
                "group_means": {name: statistics.fmean(values) for name, values in groups.items()},
            }
        )
    except Exception as exc:
        return error_result(str(exc), {"group_count": len(parsed.groups)})


def classification_metrics(input_data: ClassificationMetricsInput | dict[str, Any]):
    parsed = input_data if isinstance(input_data, ClassificationMetricsInput) else ClassificationMetricsInput.model_validate(input_data)
    try:
        if len(parsed.y_true) != len(parsed.y_pred):
            return error_result("y_true and y_pred must have the same length.")
        if not parsed.y_true:
            return error_result("At least one label is required.")
        positive = parsed.positive_label
        tp = sum(1 for truth, pred in zip(parsed.y_true, parsed.y_pred) if truth == positive and pred == positive)
        tn = sum(1 for truth, pred in zip(parsed.y_true, parsed.y_pred) if truth != positive and pred != positive)
        fp = sum(1 for truth, pred in zip(parsed.y_true, parsed.y_pred) if truth != positive and pred == positive)
        fn = sum(1 for truth, pred in zip(parsed.y_true, parsed.y_pred) if truth == positive and pred != positive)
        accuracy = (tp + tn) / len(parsed.y_true)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        specificity = tn / (tn + fp) if tn + fp else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return ok_result(
            {
                "positive_label": positive,
                "true_positive": tp,
                "true_negative": tn,
                "false_positive": fp,
                "false_negative": fn,
                "accuracy": accuracy,
                "precision": precision,
                "recall": recall,
                "specificity": specificity,
                "f1": f1,
            }
        )
    except Exception as exc:
        return error_result(str(exc), {"positive_label": parsed.positive_label})


def _extract_values(input_data: SeriesInput) -> list[float]:
    if input_data.values is not None:
        return [float(value) for value in input_data.values if value is not None]
    if input_data.rows is None or input_data.column is None:
        return []
    values = []
    for row in input_data.rows:
        value = row.get(input_data.column)
        if value in (None, ""):
            continue
        values.append(float(value))
    return values


def _missing_count(input_data: SeriesInput) -> int:
    if input_data.values is not None:
        return sum(1 for value in input_data.values if value is None)
    if input_data.rows is None or input_data.column is None:
        return 0
    return sum(1 for row in input_data.rows if row.get(input_data.column) in (None, ""))


def _quantile(sorted_values: list[float], probability: float) -> float:
    if not sorted_values:
        raise ValueError("Cannot compute quantile of empty data.")
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    position = probability * (len(sorted_values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(sorted_values[lower])
    fraction = position - lower
    return float(sorted_values[lower] * (1.0 - fraction) + sorted_values[upper] * fraction)


def _statistic(name: str):
    normalized = name.strip().lower()
    if normalized == "mean":
        return statistics.fmean
    if normalized == "median":
        return statistics.median
    if normalized == "stdev":
        return statistics.stdev
    raise ValueError(f"Unsupported bootstrap statistic: {name}")


def _pearson(x: list[float], y: list[float]) -> float:
    x_mean = statistics.fmean(x)
    y_mean = statistics.fmean(y)
    numerator = sum((left - x_mean) * (right - y_mean) for left, right in zip(x, y))
    x_ss = sum((left - x_mean) ** 2 for left in x)
    y_ss = sum((right - y_mean) ** 2 for right in y)
    denominator = math.sqrt(x_ss * y_ss)
    if denominator == 0:
        raise ValueError("Cannot compute correlation with zero-variance input.")
    return numerator / denominator


def _ranks(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(indexed):
        end = index
        while end + 1 < len(indexed) and indexed[end + 1][1] == indexed[index][1]:
            end += 1
        average_rank = (index + end + 2) / 2.0
        for ranked_index in range(index, end + 1):
            ranks[indexed[ranked_index][0]] = average_rank
        index = end + 1
    return ranks
