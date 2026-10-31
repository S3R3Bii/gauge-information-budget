"""Run only the declared v2 development phase until a committed analytical freeze exists."""

import argparse
import csv
import json
import math
import platform
import time
from datetime import date
from pathlib import Path

import numpy as np

from config import (
    ROOT,
    DEVELOPMENT_BASINS,
    HELD_BASINS,
    LAMBDAS,
    LAGS,
    SEED,
    BOOTSTRAP_BLOCK,
    BOOTSTRAP_REPLICATES,
)
from model_v2 import (
    TRAIN_YEARS,
    VALIDATION_YEAR,
    EVALUATION_YEARS,
    load,
    support,
    fit,
    predict,
    metrics,
    select,
    outage,
    check_freeze,
)


def write(path, value):
    path.write_bytes((json.dumps(value, indent=2, allow_nan=False) + "\n").encode())


def baseline(row):
    return dict(z=row["baseline"], q=math.expm1(row["baseline"]), clipped=False)


def export_prediction(
    row,
    prediction,
    model,
    penalty=None,
    scenario="normal",
    qualifier="all-approved",
    fallback=False,
):
    return dict(
        basin=row["basin"],
        date=row["date"],
        year=int(row["date"][:4]),
        lag=row["lag"],
        model=model,
        penalty=penalty,
        scenario=scenario,
        qualifier_rule=qualifier,
        latest_input_date=row["latest_input_date"],
        earliest_input_date=row["earliest_input_date"],
        source_window_has_qualifier=row["qualified"],
        actual_log=row["z"],
        actual_cfs=row["q"],
        predicted_log=prediction["z"],
        predicted_cfs=prediction["q"],
        clipped=prediction["clipped"],
        local_fallback=fallback,
    )


def csv_write(path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def development(out):
    records = load()
    fits = {}
    predictions = []
    scores = []
    ledger = []
    for basin in DEVELOPMENT_BASINS:
        for lag in LAGS:
            train, account = support(records, basin, TRAIN_YEARS, lag)
            ledger += account
            validation, account = support(records, basin, [VALIDATION_YEAR], lag)
            ledger += account
            if not train or not validation:
                raise ValueError("Unavailable development support")
            training_mean = float(np.mean([r["q"] for r in train]))
            pp = [baseline(r) for r in validation]
            scores.append(
                dict(
                    basin=basin,
                    lag=lag,
                    model="persistence",
                    penalty=None,
                    **metrics(validation, pp, training_mean),
                )
            )
            predictions += [
                export_prediction(r, p, "persistence") for r, p in zip(validation, pp)
            ]
            for model in ["local", "pair"]:
                for penalty in LAMBDAS:
                    key = f"{basin}--lag{lag}--{model}--lambda{penalty}"
                    fitted = fit(train, model, penalty)
                    fits[key] = dict(basin=basin, lag=lag, **fitted)
                    pp = [predict(fitted, r) for r in validation]
                    scores.append(
                        dict(
                            basin=basin,
                            lag=lag,
                            model=model,
                            penalty=penalty,
                            **metrics(validation, pp, training_mean),
                        )
                    )
                    predictions += [
                        export_prediction(r, p, model, penalty)
                        for r, p in zip(validation, pp)
                    ]
    selected = {}
    candidate_scores = []
    for lag in LAGS:
        for model in ["local", "pair"]:
            values = {}
            for penalty in LAMBDAS:
                per = [
                    x
                    for x in scores
                    if x["lag"] == lag
                    and x["model"] == model
                    and x["penalty"] == penalty
                ]
                assert len(per) == 2 and {x["basin"] for x in per} == set(
                    DEVELOPMENT_BASINS
                )
                values[penalty] = sum(x["log_mse"] for x in per) / 2
                candidate_scores.append(
                    dict(
                        lag=lag,
                        model=model,
                        penalty=penalty,
                        equal_basin_validation_log_mse=values[penalty],
                    )
                )
            chosen = select(values)
            selected[f"lag{lag}--{model}"] = chosen
    assert len(fits) == 32 and len(scores) == 36
    write(out / "fits.json", fits)
    write(out / "validation_metrics.json", scores)
    write(out / "candidate_scores.json", candidate_scores)
    write(
        out / "selection.json",
        dict(
            status="DEVELOPMENT_SELECTION_ONLY",
            training_years=TRAIN_YEARS,
            validation_year=VALIDATION_YEAR,
            development_basins=DEVELOPMENT_BASINS,
            selected=selected,
            tie_rule="within absolute1e-12 of best; larger lambda",
            boundary_winners={
                k: v in [min(LAMBDAS), max(LAMBDAS)] for k, v in selected.items()
            },
            final_scores_computed=False,
        ),
    )
    write(out / "support_ledger.json", ledger)
    csv_write(out / "predictions.csv", predictions)
    return dict(
        status="EXECUTED_V2_DEVELOPMENT",
        fits=len(fits),
        fold_scores=len(scores),
        candidate_scores=len(candidate_scores),
        predictions=len(predictions),
        selected=selected,
        final_scores_computed=False,
    )


def final(out):
    frozen = check_freeze()
    selection = json.loads(
        (ROOT / "results/v2/development/selection.json").read_bytes()
    )["selected"]
    assert selection == frozen["selected"]
    records = load()
    fits = {}
    predictions = []
    scores = []
    ledger = []
    primary = {}
    for basin in DEVELOPMENT_BASINS + HELD_BASINS:
        for lag in LAGS:
            train, account = support(records, basin, TRAIN_YEARS, lag)
            ledger += account
            training_mean = float(np.mean([r["q"] for r in train]))
            fitted = {
                model: fit(train, model, selection[f"lag{lag}--{model}"])
                for model in ["local", "pair"]
            }
            for model, fit_row in fitted.items():
                fits[f"{basin}--lag{lag}--{model}"] = dict(
                    basin=basin, lag=lag, **fit_row
                )
            for year in EVALUATION_YEARS:
                common, account = support(records, basin, [year], lag)
                ledger += account
                if len(common) < 300:
                    raise ValueError("Fixed300-date primary common-support gate failed")
                for qualifier in ["all-approved", "empty-qualifiers"]:
                    rows = [
                        r
                        for r in common
                        if qualifier == "all-approved" or not r["qualified"]
                    ]
                    for scenario in ["normal", "seven-day-outage"]:
                        panel = {}
                        for model in ["persistence", "local", "pair"]:
                            pp = []
                            fallbacks = []
                            for row in rows:
                                fallback = (
                                    model == "pair"
                                    and scenario == "seven-day-outage"
                                    and outage(date.fromisoformat(row["date"]), lag)
                                )
                                p = (
                                    baseline(row)
                                    if model == "persistence"
                                    else predict(
                                        fitted["local" if fallback else model], row
                                    )
                                )
                                pp.append(p)
                                fallbacks.append(fallback)
                                predictions.append(
                                    export_prediction(
                                        row,
                                        p,
                                        model,
                                        (
                                            None
                                            if model == "persistence"
                                            else fitted[model]["penalty"]
                                        ),
                                        scenario,
                                        qualifier,
                                        fallback,
                                    )
                                )
                            metric = metrics(rows, pp, training_mean)
                            entry = dict(
                                basin=basin,
                                geographic_role=(
                                    "configuration-held"
                                    if basin in HELD_BASINS
                                    else "development-context"
                                ),
                                year=year,
                                lag=lag,
                                model=model,
                                scenario=scenario,
                                qualifier_rule=qualifier,
                                local_fallback_count=sum(fallbacks),
                                **metric,
                            )
                            scores.append(entry)
                            panel[model] = (entry, pp)
                        mse = panel["persistence"][0]["log_mse"]
                        for entry, pp in panel.values():
                            entry["log_mse_skill_vs_persistence"] = (
                                None
                                if mse is None or mse == 0
                                else 1 - entry["log_mse"] / mse
                            )
                        if (
                            basin in HELD_BASINS
                            and lag == 3
                            and qualifier == "all-approved"
                            and scenario == "normal"
                        ):
                            primary[f"{basin}--{year}"] = (rows, panel)
    assert len(fits) == 16 and len(scores) == 192 and len(primary) == 4
    rng = np.random.default_rng(SEED)
    boot = []
    primary_summary = []
    for key, (rows, panel) in sorted(primary.items()):
        n = len(rows)
        starts = rng.integers(
            0, n, size=(BOOTSTRAP_REPLICATES, math.ceil(n / BOOTSTRAP_BLOCK))
        )
        e = {
            model: np.asarray([(p["z"] - r["z"]) ** 2 for r, p in zip(rows, pp)])
            for model, (metric, pp) in panel.items()
        }
        draws = []
        for ss in starts:
            indices = np.concatenate(
                [(s + np.arange(BOOTSTRAP_BLOCK)) % n for s in ss]
            )[:n]
            base = float(e["persistence"][indices].mean())
            pair = None if base == 0 else 1 - float(e["pair"][indices].mean()) / base
            local = None if base == 0 else 1 - float(e["local"][indices].mean()) / base
            draws.append(
                dict(
                    block_starts=ss.tolist(),
                    pair_skill=pair,
                    local_skill=local,
                    pair_minus_local=None if pair is None else pair - local,
                )
            )
        intervals = {}
        for field in ["pair_skill", "local_skill", "pair_minus_local"]:
            vals = [d[field] for d in draws if d[field] is not None]
            intervals[field] = dict(
                available_replicates=len(vals),
                lower=(
                    None
                    if not vals
                    else float(np.quantile(vals, 0.05, method="linear"))
                ),
                upper=(
                    None
                    if not vals
                    else float(np.quantile(vals, 0.95, method="linear"))
                ),
            )
        boot.append(
            dict(
                panel=key,
                n=n,
                block_days=BOOTSTRAP_BLOCK,
                replicates=BOOTSTRAP_REPLICATES,
                target_dates=[r["date"] for r in rows],
                draws=draws,
                conditional_90_percent_intervals=intervals,
            )
        )
        primary_summary.append(
            dict(
                panel=key,
                n=n,
                persistence_log_mse=panel["persistence"][0]["log_mse"],
                local_log_mse=panel["local"][0]["log_mse"],
                pair_log_mse=panel["pair"][0]["log_mse"],
                local_skill=panel["local"][0]["log_mse_skill_vs_persistence"],
                pair_skill=panel["pair"][0]["log_mse_skill_vs_persistence"],
                pair_minus_local=panel["pair"][0]["log_mse_skill_vs_persistence"]
                - panel["local"][0]["log_mse_skill_vs_persistence"],
            )
        )
    write(out / "fits.json", fits)
    write(out / "panel_metrics.json", scores)
    write(out / "support_ledger.json", ledger)
    write(out / "bootstrap.json", boot)
    csv_write(out / "predictions.csv", predictions)
    summary = dict(
        status="EXECUTED_FROZEN_V2_FINAL",
        primary_panels=primary_summary,
        equal_panel_mean={
            key: sum(x[key] for x in primary_summary) / 4
            for key in ["local_skill", "pair_skill", "pair_minus_local"]
        },
        selected=selection,
        model_panel_rows=len(scores),
        prediction_rows=len(predictions),
        new_selection_made=False,
        operational_availability="unverified; later Approved daily values under synthetic date lags",
        v1_original_gate="FAILED_UNCHANGED",
    )
    write(out / "summary.json", summary)
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--phase", choices=["development", "final"], required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if a.phase == "final":
        check_freeze()
    if a.out.exists():
        raise ValueError("Fresh output required; retain prior runs")
    a.out.mkdir(parents=True)
    start = time.perf_counter()
    result = development(a.out) if a.phase == "development" else final(a.out)
    write(
        a.out / "runtime.json",
        dict(
            python=platform.python_version(),
            numpy=np.__version__,
            elapsed_seconds=time.perf_counter() - start,
            scope="Measured local execution only; not a production-latency benchmark",
        ),
    )
    print(json.dumps(result, allow_nan=False))
