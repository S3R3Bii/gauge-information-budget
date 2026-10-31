"""Fixed retrospective discharge features and mean-loss ridge; no operational-vintage claim."""

import csv
import hashlib
import json
import math
import subprocess
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from config import ROOT, PAIRS, LAMBDAS, LAGS

TRAIN_YEARS = [2020, 2021]
VALIDATION_YEAR = 2022
EVALUATION_YEARS = [2023, 2024]
LOCAL_FEATURES = [
    "target_level",
    "target_one_day_change",
    "target_seven_day_change",
    "season_sine",
    "season_cosine",
]
PAIR_FEATURES = LOCAL_FEATURES + [
    "additional_level",
    "additional_one_day_change",
    "additional_seven_day_change",
]


def load():
    records = {}
    with (ROOT / "data/v2/measurements.csv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            key = r["basin"], r["role"], date.fromisoformat(r["date"])
            if key in records:
                raise ValueError("Duplicate measurement")
            flow = float(r["source_value"])
            if not math.isfinite(flow) or flow < 0:
                raise ValueError("Invalid discharge")
            records[key] = dict(
                q=flow, z=math.log1p(flow), qualified=bool(r["qualifier"])
            )
    return records


def days(year):
    d = date(year, 1, 1)
    while d.year == year:
        yield d
        d += timedelta(days=1)


def observation(records, basin, day, lag):
    dates = [day - timedelta(days=lag + k) for k in [0, 1, 7]]
    required = [(basin, "target", day)] + [
        (basin, role, d) for role in ["target", "additional"] for d in dates
    ]
    missing = [
        f"{role}:{d.isoformat()}"
        for b, role, d in required
        if (b, role, d) not in records
    ]
    if missing:
        return None, missing
    t = [records[basin, "target", d]["z"] for d in dates]
    u = [records[basin, "additional", d]["z"] for d in dates]
    # January 1 has phase zero; the declared period is 365.25 days.
    angle = 2 * math.pi * (day.timetuple().tm_yday - 1) / 365.25
    local = [t[0], t[0] - t[1], t[0] - t[2], math.sin(angle), math.cos(angle)]
    truth = records[basin, "target", day]
    return (
        dict(
            date=day.isoformat(),
            basin=basin,
            lag=lag,
            latest_input_date=dates[0].isoformat(),
            earliest_input_date=dates[-1].isoformat(),
            qualified=any(records[k]["qualified"] for k in required),
            q=truth["q"],
            z=truth["z"],
            baseline=t[0],
            local=local,
            pair=local + [u[0], u[0] - u[1], u[0] - u[2]],
        ),
        [],
    )


def support(records, basin, years, lag):
    rows, ledger = [], []
    for year in years:
        for day in days(year):
            row, missing = observation(records, basin, day, lag)
            ledger.append(
                dict(
                    basin=basin,
                    lag=lag,
                    date=day.isoformat(),
                    eligible=row is not None,
                    missing=missing,
                    qualified=None if row is None else row["qualified"],
                )
            )
            if row is not None:
                rows.append(row)
    return rows, ledger


def fit(rows, model, penalty):
    if model not in ["local", "pair"] or penalty not in LAMBDAS or len(rows) < 2:
        raise ValueError("Invalid fixed fit")
    x = np.asarray([r[model] for r in rows], dtype=np.float64)
    y = np.asarray([r["z"] - r["baseline"] for r in rows], dtype=np.float64)
    means = x.mean(axis=0)
    scales = x.std(axis=0, ddof=0)
    zero = scales == 0
    scales[zero] = 1
    standardized = (x - means) / scales
    response_mean = float(y.mean())
    coef = np.linalg.solve(
        standardized.T @ standardized + len(rows) * penalty * np.eye(x.shape[1]),
        standardized.T @ (y - response_mean),
    )
    return dict(
        model=model,
        penalty=penalty,
        n_train=len(rows),
        feature_names=LOCAL_FEATURES if model == "local" else PAIR_FEATURES,
        means=means.tolist(),
        scales=scales.tolist(),
        zero_scale_flags=zero.tolist(),
        response_mean=response_mean,
        coefficients=coef.tolist(),
        train_mean_cfs=float(np.mean([r["q"] for r in rows])),
        train_first_date=rows[0]["date"],
        train_last_date=rows[-1]["date"],
        training_date_sha256=hashlib.sha256(
            ("\n".join(r["date"] for r in rows) + "\n").encode()
        ).hexdigest(),
        objective="mean squared residual plus lambda*sum(beta^2); intercept unpenalized",
    )


def predict(fitted, row):
    x = np.asarray(row[fitted["model"]], dtype=np.float64)
    residual = fitted["response_mean"] + float(
        ((x - np.asarray(fitted["means"])) / np.asarray(fitted["scales"]))
        @ np.asarray(fitted["coefficients"])
    )
    raw = row["baseline"] + residual
    z = max(0.0, raw)
    return dict(z=z, q=math.expm1(z), clipped=raw < 0)


def metrics(rows, predictions, train_mean):
    if len(rows) != len(predictions):
        raise ValueError("Common support mismatch")
    if not rows:
        return dict(
            state="UNAVAILABLE_EMPTY_SUPPORT",
            n=0,
            log_mae=None,
            log_mse=None,
            log_rmse=None,
            cfs_mae=None,
            cfs_mse=None,
            cfs_rmse=None,
            cfs_mean_signed_error=None,
            train_mean_normalized_cfs_rmse=None,
            clipped_count=0,
        )
    a = np.asarray([p["z"] - r["z"] for r, p in zip(rows, predictions)])
    b = np.asarray([p["q"] - r["q"] for r, p in zip(rows, predictions)])
    log_mse = float(np.mean(a * a))
    cfs_mse = float(np.mean(b * b))
    return dict(
        state="AVAILABLE",
        n=len(rows),
        log_mae=float(np.mean(np.abs(a))),
        log_mse=log_mse,
        log_rmse=math.sqrt(log_mse),
        cfs_mae=float(np.mean(np.abs(b))),
        cfs_mse=cfs_mse,
        cfs_rmse=math.sqrt(cfs_mse),
        cfs_mean_signed_error=float(np.mean(b)),
        train_mean_normalized_cfs_rmse=(
            math.sqrt(cfs_mse) / train_mean if train_mean else None
        ),
        clipped_count=sum(p["clipped"] for p in predictions),
    )


def select(scores):
    if set(scores) != set(LAMBDAS):
        raise ValueError("All four candidates required")
    best = min(scores.values())
    return max(k for k, v in scores.items() if v <= best + 1e-12)


def outage(day, lag):
    return ((day - timedelta(days=lag) - date(2023, 1, 1)).days % 28) < 7


def check_freeze():
    path = ROOT / "data/v2/frozen_dependencies.json"
    if not path.exists():
        raise ValueError("Committed v2 freeze required before final outcomes")
    frozen = json.loads(path.read_bytes())
    version = frozen["development_commit"]
    if (
        subprocess.check_output(
            ["git", "show", "HEAD:data/v2/frozen_dependencies.json"], cwd=ROOT
        )
        != path.read_bytes()
    ):
        raise ValueError("The v2 freeze must already be committed")
    for name, digest in frozen["dependencies"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Frozen v2 dependency changed: " + name)
        blob = subprocess.check_output(["git", "show", version + ":" + name], cwd=ROOT)
        if hashlib.sha256(blob).hexdigest() != digest:
            raise ValueError("Dependency differs from committed development checkpoint")
    return frozen
