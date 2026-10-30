"""Independent SQL feature joins, augmented least-squares fits and scalar resampling.

No production feature, fit, prediction, metric or selection helpers are imported.
"""

import argparse
import csv
import hashlib
import json
import math
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEV = ["wisconsin", "delaware"]
HELD = ["susquehanna", "mississippi"]
PENALTIES = [0.001, 0.01, 0.1, 1.0]
LOCAL = [
    "target_level",
    "target_one_day_change",
    "target_seven_day_change",
    "season_sine",
    "season_cosine",
]
PAIR = LOCAL + [
    "additional_level",
    "additional_one_day_change",
    "additional_seven_day_change",
]


class Checker:
    def __init__(self):
        self.conditions = 0
        self.max_log_difference = 0.0
        self.max_cfs_tolerance_fraction = 0.0

    def exact(self, actual, expected, label):
        assert actual == expected, (label, actual, expected)
        self.conditions += 1

    def numeric(self, actual, expected, kind, label):
        if expected is None:
            self.exact(actual, None, label)
            return
        assert (
            actual is not None and math.isfinite(actual) and math.isfinite(expected)
        ), label
        tolerance = 1e-8 if kind == "log" else 1e-4 + 1e-10 * abs(expected)
        difference = abs(actual - expected)
        assert difference <= tolerance, (label, actual, expected, tolerance)
        if kind == "log":
            self.max_log_difference = max(self.max_log_difference, difference)
        else:
            self.max_cfs_tolerance_fraction = max(
                self.max_cfs_tolerance_fraction, difference / tolerance
            )
        self.conditions += 1


def native():
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE source(basin TEXT,role TEXT,day TEXT,q REAL,flag INT,PRIMARY KEY(basin,role,day))"
    )
    with (ROOT / "data/v2/measurements.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    db.executemany(
        "INSERT INTO source VALUES(?,?,?,?,?)",
        [
            (
                r["basin"],
                r["role"],
                r["date"],
                float(r["source_value"]),
                int(bool(r["qualifier"])),
            )
            for r in rows
        ],
    )
    available = {(r["basin"], r["role"], r["date"]) for r in rows}
    return db, available


def joined(db, basin, lag, years):
    # Both models use the same seven required records, including the target label.
    sql = (
        """SELECT t.day,t.q,t0.q,t1.q,t7.q,u0.q,u1.q,u7.q,
    MAX(t.flag,t0.flag,t1.flag,t7.flag,u0.flag,u1.flag,u7.flag)
    FROM source t
    JOIN source t0 ON t0.basin=t.basin AND t0.role='target' AND t0.day=date(t.day,?)
    JOIN source t1 ON t1.basin=t.basin AND t1.role='target' AND t1.day=date(t.day,?)
    JOIN source t7 ON t7.basin=t.basin AND t7.role='target' AND t7.day=date(t.day,?)
    JOIN source u0 ON u0.basin=t.basin AND u0.role='additional' AND u0.day=date(t.day,?)
    JOIN source u1 ON u1.basin=t.basin AND u1.role='additional' AND u1.day=date(t.day,?)
    JOIN source u7 ON u7.basin=t.basin AND u7.role='additional' AND u7.day=date(t.day,?)
    WHERE t.role='target' AND t.basin=? AND substr(t.day,1,4) IN ("""
        + ",".join("?" for _ in years)
        + ") ORDER BY t.day"
    )
    shifts = [f"-{lag+k} days" for k in [0, 1, 7]]
    out = []
    for row in db.execute(sql, shifts + shifts + [basin] + [str(y) for y in years]):
        day = date.fromisoformat(row[0])
        z = np.log1p(np.asarray(row[1:8], dtype=np.float64))
        angle = 2 * np.pi * (int(day.strftime("%j")) - 1) / 365.25
        local = [
            z[1],
            z[1] - z[2],
            z[1] - z[3],
            float(np.sin(angle)),
            float(np.cos(angle)),
        ]
        out.append(
            dict(
                date=row[0],
                basin=basin,
                lag=lag,
                q=row[1],
                z=float(z[0]),
                baseline=float(z[1]),
                qualified=bool(row[8]),
                local=local,
                pair=local + [z[4], z[4] - z[5], z[4] - z[6]],
                latest=(day - timedelta(days=lag)).isoformat(),
                earliest=(day - timedelta(days=lag + 7)).isoformat(),
            )
        )
    return out


def independent_fit(rows, model, penalty):
    x = np.array([r[model] for r in rows])
    y = np.array([r["z"] - r["baseline"] for r in rows])
    mean = x.mean(axis=0)
    scale = np.sqrt(np.mean((x - mean) ** 2, axis=0))
    zero = scale == 0
    scale[zero] = 1
    standardized = (x - mean) / scale
    intercept = float(y.mean())
    augmented = np.concatenate(
        [standardized, math.sqrt(len(rows) * penalty) * np.eye(x.shape[1])]
    )
    target = np.concatenate([y - intercept, np.zeros(x.shape[1])])
    coefficient = np.linalg.lstsq(augmented, target, rcond=None)[0]
    return dict(
        means=mean,
        scales=scale,
        zero=zero,
        intercept=intercept,
        coefficient=coefficient,
        train_mean=math.fsum(r["q"] for r in rows) / len(rows),
    )


def forecast(fitted, row, model):
    if model == "persistence":
        raw = row["baseline"]
    else:
        raw = (
            row["baseline"]
            + fitted["intercept"]
            + math.fsum(
                (float(x) - float(m)) / float(s) * float(b)
                for x, m, s, b in zip(
                    row[model], fitted["means"], fitted["scales"], fitted["coefficient"]
                )
            )
        )
    log = max(0.0, raw)
    return dict(z=log, q=math.expm1(log), clipped=raw < 0)


def panel_key(basin, lag, model, penalty, scenario, qualifier):
    return (
        basin,
        int(lag),
        model,
        "" if penalty is None else str(float(penalty)),
        scenario,
        qualifier,
    )


def check(phase, out):
    c = Checker()
    db, available = native()
    basins = DEV if phase == "development" else DEV + HELD
    years = [2020, 2021, 2022] if phase == "development" else [2020, 2021, 2023, 2024]
    rows = {(b, lag): joined(db, b, lag, years) for b in basins for lag in [3, 1]}
    lookup = {(b, lag, r["date"]): r for (b, lag), rr in rows.items() for r in rr}
    fits = json.loads((out / "fits.json").read_bytes())
    qr = {}
    c.exact(len(fits), 32 if phase == "development" else 16, "fit count")
    selected = (
        json.loads((ROOT / "results/v2/development/selection.json").read_bytes())[
            "selected"
        ]
        if phase == "final"
        else None
    )
    for name, fit in fits.items():
        b, lag, model, penalty = fit["basin"], fit["lag"], fit["model"], fit["penalty"]
        c.exact(b in basins, True, "fit geography")
        c.exact(lag in [3, 1], True, "fit lag")
        c.exact(penalty in PENALTIES, True, "fit grid")
        if phase == "final":
            c.exact(penalty, selected[f"lag{lag}--{model}"], "frozen penalty")
        train = [r for r in rows[b, lag] if r["date"][:4] in ["2020", "2021"]]
        f = independent_fit(train, model, penalty)
        qr[b, lag, model, float(penalty)] = f
        c.exact(fit["n_train"], len(train), "training support")
        c.exact(
            fit["feature_names"],
            LOCAL if model == "local" else PAIR,
            "feature identity",
        )
        c.exact(fit["train_first_date"], train[0]["date"], "train first")
        c.exact(fit["train_last_date"], train[-1]["date"], "train last")
        c.exact(
            fit["training_date_sha256"],
            hashlib.sha256(
                ("\n".join(r["date"] for r in train) + "\n").encode()
            ).hexdigest(),
            "all training dates",
        )
        c.exact(fit["zero_scale_flags"], f["zero"].tolist(), "zero-scale flags")
        for key, values in [
            ("means", f["means"]),
            ("scales", f["scales"]),
            ("coefficients", f["coefficient"]),
        ]:
            c.exact(len(fit[key]), len(values), "fit vector length")
            for actual, expected in zip(fit[key], values):
                c.numeric(actual, float(expected), "log", "fit " + key)
        c.numeric(fit["response_mean"], f["intercept"], "log", "unpenalized intercept")
        c.numeric(fit["train_mean_cfs"], f["train_mean"], "cfs", "train-only flow mean")
    ledger = json.loads((out / "support_ledger.json").read_bytes())
    c.exact(
        len(ledger),
        sum(len(list(_days(y))) for y in years) * len(basins) * 2,
        "complete date ledger",
    )
    seen = set()
    for row in ledger:
        key = row["basin"], row["lag"], row["date"]
        c.exact(key in seen, False, "unique support ledger")
        seen.add(key)
        d = date.fromisoformat(row["date"])
        missing = []
        for role, day in [("target", d)] + [
            (role, d - timedelta(days=row["lag"] + k))
            for role in ["target", "additional"]
            for k in [0, 1, 7]
        ]:
            if (row["basin"], role, day.isoformat()) not in available:
                missing.append(f"{role}:{day.isoformat()}")
        c.exact(row["missing"], missing, "required source dates")
        c.exact(row["eligible"], not missing, "complete common support")
        c.exact(
            row["qualified"],
            None if missing else lookup[key]["qualified"],
            "qualifier union",
        )
    db.execute(
        "CREATE TABLE prediction(basin TEXT,lag INT,model TEXT,penalty TEXT,scenario TEXT,qualifier TEXT,year INT,day TEXT,ez REAL,eq REAL,clipped INT,fallback INT,PRIMARY KEY(basin,lag,model,penalty,scenario,qualifier,day))"
    )
    primary_errors = {}
    prediction_count = 0
    with (out / "predictions.csv").open(encoding="utf-8", newline="") as file:
        for p in csv.DictReader(file):
            b, lag, model = p["basin"], int(p["lag"]), p["model"]
            r = lookup[b, lag, p["date"]]
            penalty = None if p["penalty"] == "" else float(p["penalty"])
            c.exact(model in ["persistence", "local", "pair"], True, "model identity")
            c.exact(p["latest_input_date"], r["latest"], "latest feature date")
            c.exact(p["earliest_input_date"], r["earliest"], "earliest feature date")
            c.exact(
                p["source_window_has_qualifier"] == "True",
                r["qualified"],
                "source qualifier",
            )
            c.exact(int(p["year"]), int(p["date"][:4]), "target year")
            if phase == "development":
                c.exact(p["year"], "2022", "validation only")
                c.exact(b in DEV, True, "development only")
                c.exact(p["scenario"], "normal", "development scenario")
                c.exact(p["qualifier_rule"], "all-approved", "development qualifier")
            else:
                c.exact(p["year"] in ["2023", "2024"], True, "final year")
                if p["qualifier_rule"] == "empty-qualifiers":
                    c.exact(r["qualified"], False, "qualifier exclusion")
                if model != "persistence":
                    c.exact(
                        penalty,
                        selected[f"lag{lag}--{model}"],
                        "selected final configuration",
                    )
            d = date.fromisoformat(p["date"])
            fallback = (
                model == "pair"
                and p["scenario"] == "seven-day-outage"
                and ((d - timedelta(days=lag) - date(2023, 1, 1)).days % 28) < 7
            )
            c.exact(p["local_fallback"] == "True", fallback, "outage routing")
            routed = "local" if fallback else model
            qr_penalty = selected[f"lag{lag}--local"] if fallback else penalty
            f = (
                None
                if model == "persistence"
                else qr[b, lag, routed, float(qr_penalty)]
            )
            expected = forecast(f, r, routed)
            for field, value, kind in [
                ("actual_log", r["z"], "log"),
                ("actual_cfs", r["q"], "cfs"),
                ("predicted_log", expected["z"], "log"),
                ("predicted_cfs", expected["q"], "cfs"),
            ]:
                c.numeric(float(p[field]), value, kind, field)
            c.exact(p["clipped"] == "True", expected["clipped"], "natural lower clip")
            key = panel_key(b, lag, model, penalty, p["scenario"], p["qualifier_rule"])
            db.execute(
                "INSERT INTO prediction VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                key
                + (
                    int(p["year"]),
                    p["date"],
                    expected["z"] - r["z"],
                    expected["q"] - r["q"],
                    int(expected["clipped"]),
                    int(fallback),
                ),
            )
            if (
                phase == "final"
                and b in HELD
                and lag == 3
                and p["scenario"] == "normal"
                and p["qualifier_rule"] == "all-approved"
            ):
                primary_errors.setdefault((b, int(p["year"]), model), []).append(
                    (p["date"], (expected["z"] - r["z"]) ** 2)
                )
            prediction_count += 1
    scored = json.loads(
        (
            out
            / (
                "validation_metrics.json"
                if phase == "development"
                else "panel_metrics.json"
            )
        ).read_bytes()
    )
    c.exact(len(scored), 36 if phase == "development" else 192, "complete metric grid")
    metric_lookup = {}
    for metric in scored:
        key = panel_key(
            metric["basin"],
            metric["lag"],
            metric["model"],
            (
                metric["penalty"]
                if phase == "development"
                else (
                    None
                    if metric["model"] == "persistence"
                    else selected[f"lag{metric['lag']}--{metric['model']}"]
                )
            ),
            metric.get("scenario", "normal"),
            metric.get("qualifier_rule", "all-approved"),
        )
        year = 2022 if phase == "development" else metric["year"]
        sql = "SELECT COUNT(*),AVG(ABS(ez)),AVG(ez*ez),AVG(ABS(eq)),AVG(eq*eq),AVG(eq),SUM(clipped),SUM(fallback) FROM prediction WHERE basin=? AND lag=? AND model=? AND penalty=? AND scenario=? AND qualifier=? AND year=?"
        n, mae, mse, qmae, qmse, bias, clip, fallback = db.execute(
            sql, key + (year,)
        ).fetchone()
        required_rows = [
            r
            for r in rows[metric["basin"], metric["lag"]]
            if int(r["date"][:4]) == year
            and (
                metric.get("qualifier_rule", "all-approved") == "all-approved"
                or not r["qualified"]
            )
        ]
        c.exact(
            n, len(required_rows), "all independently eligible target dates retained"
        )
        c.exact(metric["n"], n, "metric support")
        c.exact(
            metric["state"],
            "AVAILABLE" if n else "UNAVAILABLE_EMPTY_SUPPORT",
            "availability",
        )
        train = [
            r
            for r in rows[metric["basin"], metric["lag"]]
            if r["date"][:4] in ["2020", "2021"]
        ]
        train_mean = math.fsum(r["q"] for r in train) / len(train)
        expected = dict(
            log_mae=mae,
            log_mse=mse,
            log_rmse=None if mse is None else math.sqrt(mse),
            cfs_mae=qmae,
            cfs_mse=qmse,
            cfs_rmse=None if qmse is None else math.sqrt(qmse),
            cfs_mean_signed_error=bias,
            train_mean_normalized_cfs_rmse=(
                None if not train_mean or qmse is None else math.sqrt(qmse) / train_mean
            ),
        )
        for field, value in expected.items():
            c.numeric(
                metric[field],
                value,
                (
                    "cfs"
                    if field.startswith("cfs") and not field.startswith("train")
                    else "log"
                ),
                field,
            )
        c.exact(metric["clipped_count"], clip or 0, "clip aggregate")
        if phase == "final":
            c.exact(metric["local_fallback_count"], fallback or 0, "fallback aggregate")
        metric_lookup[key + (year,)] = expected
    if phase == "development":
        candidates = json.loads((out / "candidate_scores.json").read_bytes())
        c.exact(len(candidates), 16, "all candidate objectives")
        chosen = {}
        for lag in [3, 1]:
            for model in ["local", "pair"]:
                values = {}
                for penalty in PENALTIES:
                    value = (
                        sum(
                            metric_lookup[
                                panel_key(
                                    b, lag, model, penalty, "normal", "all-approved"
                                )
                                + (2022,)
                            ]["log_mse"]
                            for b in DEV
                        )
                        / 2
                    )
                    actual = next(
                        x
                        for x in candidates
                        if x["lag"] == lag
                        and x["model"] == model
                        and x["penalty"] == penalty
                    )
                    c.numeric(
                        actual["equal_basin_validation_log_mse"],
                        value,
                        "log",
                        "equal-basin objective",
                    )
                    values[penalty] = value
                best = min(values.values())
                chosen[f"lag{lag}--{model}"] = max(
                    k for k, v in values.items() if v <= best + 1e-12
                )
        selection = json.loads((out / "selection.json").read_bytes())
        c.exact(selection["selected"], chosen, "declared selector")
        c.exact(selection["final_scores_computed"], False, "no final selection score")
    else:

        def skill(b, year, model):
            base = metric_lookup[
                panel_key(b, 3, "persistence", None, "normal", "all-approved") + (year,)
            ]["log_mse"]
            return (
                1
                - metric_lookup[
                    panel_key(
                        b,
                        3,
                        model,
                        selected[f"lag3--{model}"],
                        "normal",
                        "all-approved",
                    )
                    + (year,)
                ]["log_mse"]
                / base
            )

        for metric in scored:
            key = panel_key(
                metric["basin"],
                metric["lag"],
                metric["model"],
                (
                    None
                    if metric["model"] == "persistence"
                    else selected[f"lag{metric['lag']}--{metric['model']}"]
                ),
                metric["scenario"],
                metric["qualifier_rule"],
            ) + (metric["year"],)
            basekey = panel_key(
                metric["basin"],
                metric["lag"],
                "persistence",
                None,
                metric["scenario"],
                metric["qualifier_rule"],
            ) + (metric["year"],)
            base = metric_lookup[basekey]["log_mse"]
            expected = (
                None
                if base is None or base == 0
                else 1 - metric_lookup[key]["log_mse"] / base
            )
            c.numeric(
                metric["log_mse_skill_vs_persistence"], expected, "log", "panel skill"
            )
            if metric["qualifier_rule"] == "all-approved":
                c.exact(metric["n"] >= 300, True, "fixed300-date gate")
        summary = json.loads((out / "summary.json").read_bytes())
        c.exact(summary["new_selection_made"], False, "no reselection")
        c.exact(
            summary["v1_original_gate"],
            "FAILED_UNCHANGED",
            "preserved original failure",
        )
        for p in summary["primary_panels"]:
            b, year = p["panel"].split("--")
            year = int(year)
            for model in ["local", "pair"]:
                c.numeric(
                    p[model + "_skill"], skill(b, year, model), "log", "primary skill"
                )
            c.numeric(
                p["pair_minus_local"],
                skill(b, year, "pair") - skill(b, year, "local"),
                "log",
                "primary comparison",
            )
        for field in ["local_skill", "pair_skill", "pair_minus_local"]:
            values = [
                (
                    skill(b, y, "local")
                    if field == "local_skill"
                    else (
                        skill(b, y, "pair")
                        if field == "pair_skill"
                        else skill(b, y, "pair") - skill(b, y, "local")
                    )
                )
                for b in HELD
                for y in [2023, 2024]
            ]
            c.numeric(
                summary["equal_panel_mean"][field],
                math.fsum(values) / 4,
                "log",
                "equal-panel mean",
            )
        rng = np.random.Generator(np.random.PCG64(20261029))
        boot = json.loads((out / "bootstrap.json").read_bytes())
        c.exact(len(boot), 4, "bootstrap panels")
        for panel in boot:
            b, year = panel["panel"].split("--")
            year = int(year)
            n = panel["n"]
            dates = [x[0] for x in primary_errors[b, year, "pair"]]
            c.exact(panel["target_dates"], dates, "bootstrap target dates")
            c.exact(
                all(
                    (date.fromisoformat(v) - date.fromisoformat(u)).days == 1
                    for u, v in zip(dates, dates[1:])
                ),
                True,
                "calendar-day block support",
            )
            expected_starts = rng.integers(0, n, size=(500, math.ceil(n / 14))).tolist()
            values = {k: [] for k in ["pair_skill", "local_skill", "pair_minus_local"]}
            c.exact(len(panel["draws"]), 500, "all bootstrap draws")
            for row, starts in zip(panel["draws"], expected_starts):
                c.exact(row["block_starts"], starts, "retained random draws")
                indices = [(s + k) % n for s in starts for k in range(14)][:n]
                means = {
                    model: math.fsum(
                        primary_errors[b, year, model][i][1] for i in indices
                    )
                    / n
                    for model in ["persistence", "local", "pair"]
                }
                expected = {
                    k: 1 - means[model] / means["persistence"]
                    for k, model in [("pair_skill", "pair"), ("local_skill", "local")]
                }
                expected["pair_minus_local"] = (
                    expected["pair_skill"] - expected["local_skill"]
                )
                for field, value in expected.items():
                    c.numeric(row[field], value, "log", "bootstrap estimate")
                    values[field].append(value)
            for field, vv in values.items():
                vv.sort()
                interval = panel["conditional_90_percent_intervals"][field]
                c.exact(interval["available_replicates"], 500, "available draws")
                for key, p in [("lower", 0.05), ("upper", 0.95)]:
                    position = (len(vv) - 1) * p
                    i = math.floor(position)
                    value = vv[i] + (position - i) * (
                        vv[min(i + 1, len(vv) - 1)] - vv[i]
                    )
                    c.numeric(interval[key], value, "log", "linear percentile")
    result = dict(
        status="PASS_INDEPENDENT_V2_ANALYSIS",
        phase=phase,
        conditions=c.conditions,
        predictions=prediction_count,
        fits=len(fits),
        metric_rows=len(scored),
        maximum_log_space_difference=c.max_log_difference,
        maximum_cfs_difference_fraction_of_declared_tolerance=c.max_cfs_tolerance_fraction,
        method="Separate source CSV/SQLite date joins; augmented-design least-squares SVD rather than normal equations; scalar forecasts; SQL error aggregates, independent selector and retained-draw scalar circular-block checks; no production helpers imported",
        original_v1_gate="FAILED_UNCHANGED",
    )
    (out / "independent_verification.json").write_bytes(
        (json.dumps(result, indent=2) + "\n").encode()
    )
    print(json.dumps(result))


def _days(year):
    d = date(year, 1, 1)
    while d.year == year:
        yield d
        d += timedelta(days=1)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--phase", choices=["development", "final"], required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    check(a.phase, a.out)
