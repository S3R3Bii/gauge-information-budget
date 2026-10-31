"""Authored closed-form fixtures; no recorded discharge outcomes are used."""

import math
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import model_v2 as m


def records(day=date(2020, 1, 10), lag=3):
    rows = {("test", "target", day): dict(q=9.0, z=math.log(10), qualified=False)}
    for role, start in [("target", 2.0), ("additional", 5.0)]:
        for offset, increment in [(0, 0.0), (1, -0.5), (7, -1.0)]:
            z = start + increment
            rows["test", role, day - timedelta(days=lag + offset)] = dict(
                q=math.expm1(z), z=z, qualified=False
            )
    return rows


def training():
    return [
        dict(
            date=f"2020-01-0{i+1}",
            local=[float(i), 0.0, 0.0, 0.0, 0.0],
            pair=[float(i), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            baseline=0.0,
            z=2.0 * i + 3.0,
            q=math.expm1(2.0 * i + 3.0),
        )
        for i in range(3)
    ]


class Features(unittest.TestCase):
    def test_log_levels_and_lag_differences(self):
        row, missing = m.observation(records(), "test", date(2020, 1, 10), 3)
        self.assertEqual(missing, [])
        self.assertEqual(row["local"][:3], [2.0, 0.5, 1.0])
        self.assertEqual(row["pair"][-3:], [5.0, 0.5, 1.0])

    def test_feature_date_bounds_cross_leap_day(self):
        d = date(2020, 3, 2)
        row, _ = m.observation(records(d, 3), "test", d, 3)
        self.assertEqual(row["latest_input_date"], "2020-02-28")
        self.assertEqual(row["earliest_input_date"], "2020-02-21")

    def test_no_target_day_additional_value_is_needed(self):
        r = records()
        r["test", "additional", date(2020, 1, 10)] = dict(
            q=1e9, z=math.log1p(1e9), qualified=True
        )
        row, _ = m.observation(r, "test", date(2020, 1, 10), 3)
        self.assertFalse(row["qualified"])
        self.assertEqual(row["pair"][-3:], [5.0, 0.5, 1.0])

    def test_missing_additional_lag_removes_common_support(self):
        r = records()
        del r["test", "additional", date(2020, 1, 6)]
        row, missing = m.observation(r, "test", date(2020, 1, 10), 3)
        self.assertIsNone(row)
        self.assertEqual(missing, ["additional:2020-01-06"])

    def test_missing_target_label_stays_unavailable(self):
        r = records()
        del r["test", "target", date(2020, 1, 10)]
        self.assertIsNone(m.observation(r, "test", date(2020, 1, 10), 3)[0])

    def test_qualifier_union_includes_every_required_record(self):
        r = records()
        for key in list(r):
            changed = {k: dict(v, qualified=k == key) for k, v in r.items()}
            self.assertTrue(
                m.observation(changed, "test", date(2020, 1, 10), 3)[0]["qualified"]
            )

    def test_january_first_season_phase_is_zero(self):
        d = date(2020, 1, 1)
        row, _ = m.observation(records(d, 1), "test", d, 1)
        self.assertEqual(row["local"][3:], [0.0, 1.0])

    def test_calendar_contains_february29(self):
        self.assertEqual(len(list(m.days(2020))), 366)
        self.assertEqual(len(list(m.days(2021))), 365)


class RidgeAndMetrics(unittest.TestCase):
    def test_mean_loss_ridge_has_n_times_penalty(self):
        f = m.fit(training(), "local", 0.1)
        self.assertAlmostEqual(
            f["coefficients"][0], 2 * math.sqrt(2 / 3) / 1.1, places=13
        )

    def test_intercept_is_unpenalized(self):
        self.assertAlmostEqual(m.fit(training(), "local", 1.0)["response_mean"], 5.0)

    def test_population_scale_and_constant_flags(self):
        f = m.fit(training(), "local", 0.01)
        self.assertAlmostEqual(f["scales"][0], math.sqrt(2 / 3))
        self.assertEqual(f["zero_scale_flags"], [False, True, True, True, True])
        self.assertEqual(f["scales"][1:], [1.0, 1.0, 1.0, 1.0])

    def test_validation_extreme_does_not_refit_normalization(self):
        f = m.fit(training(), "local", 0.1)
        before = f["means"][:]
        p = m.predict(f, dict(local=[100.0, 0.0, 0.0, 0.0, 0.0], baseline=0.0))
        self.assertEqual(f["means"], before)
        self.assertAlmostEqual(p["z"], 5.0 + 99.0 * 2.0 / 1.1, places=12)

    def test_negative_log_forecast_clips_before_inverse(self):
        f = m.fit(training(), "local", 0.1)
        p = m.predict(f, dict(local=[-10.0, 0.0, 0.0, 0.0, 0.0], baseline=0.0))
        self.assertEqual(p, dict(z=0.0, q=0.0, clipped=True))

    def test_declared_tie_chooses_larger_penalty(self):
        self.assertEqual(
            m.select({0.001: 1.0, 0.01: 1.0 + 0.5e-12, 0.1: 2.0, 1.0: 3.0}), 0.01
        )

    def test_tie_threshold_is_not_rounded_to_a_pass(self):
        self.assertEqual(
            m.select({0.001: 1.0, 0.01: 1.0 + 2e-12, 0.1: 2.0, 1.0: 3.0}), 0.001
        )

    def test_missing_grid_candidate_rejected(self):
        with self.assertRaises(ValueError):
            m.select({0.001: 1.0})

    def test_distinct_mae_mse_rmse_and_cfs_bias(self):
        r = [dict(z=0.0, q=0.0), dict(z=0.0, q=0.0)]
        p = [dict(z=1.0, q=3.0, clipped=False), dict(z=-3.0, q=-1.0, clipped=False)]
        metric = m.metrics(r, p, 2.0)
        self.assertEqual(metric["log_mae"], 2.0)
        self.assertEqual(metric["log_mse"], 5.0)
        self.assertEqual(metric["log_rmse"], math.sqrt(5.0))
        self.assertEqual(metric["cfs_mean_signed_error"], 1.0)
        self.assertEqual(metric["train_mean_normalized_cfs_rmse"], math.sqrt(5.0) / 2.0)

    def test_empty_support_is_unavailable(self):
        self.assertEqual(m.metrics([], [], 1.0)["state"], "UNAVAILABLE_EMPTY_SUPPORT")

    def test_comparison_requires_identical_support_lengths(self):
        with self.assertRaises(ValueError):
            m.metrics([dict(z=0.0, q=0.0)], [], 1.0)

    def test_zero_training_flow_normalizer_stays_undefined(self):
        r = m.metrics([dict(z=0.0, q=0.0)], [dict(z=0.0, q=0.0, clipped=False)], 0.0)
        self.assertIsNone(r["train_mean_normalized_cfs_rmse"])


class PhaseBoundaries(unittest.TestCase):
    def test_seven_outage_input_days_then_twentyone_available(self):
        origin = date(2023, 1, 1)
        self.assertEqual(
            [m.outage(origin + timedelta(days=i + 3), 3) for i in range(28)],
            [True] * 7 + [False] * 21,
        )

    def test_outage_uses_lagged_input_date(self):
        d = date(2023, 1, 9)
        self.assertTrue(m.outage(d, 3))
        self.assertFalse(m.outage(d, 1))

    def test_final_refuses_missing_committed_freeze(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(
            m, "ROOT", Path(folder)
        ):
            with self.assertRaisesRegex(ValueError, "freeze required"):
                m.check_freeze()


if __name__ == "__main__":
    unittest.main()
