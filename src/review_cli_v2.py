"""Review a verified saved panel, keeping metric choice and common support explicit."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def compare(rows, date_sets):
    if (
        set(rows) != set(["persistence", "local", "pair"])
        or not date_sets
        or not date_sets["pair"]
        or any(date_sets[k] != date_sets["pair"] for k in rows)
    ):
        return dict(
            status="UNAVAILABLE_COMMON_SUPPORT",
            recommendation="Obtain comparable dated observations before assessing an additional gauge.",
        )
    result = {}
    for unit, field in [("log-flow", "log_mse"), ("cubic-feet-per-second", "cfs_mse")]:
        values = {k: rows[k][field] for k in rows}
        if any(v is None or not math.isfinite(v) or v < 0 for v in values.values()):
            return dict(status="UNAVAILABLE_METRIC")
        result[unit] = dict(
            mse=values, pair_beats_local=values["pair"] < values["local"]
        )
    return dict(
        status="SAVED_COMMON_SUPPORT_COMPARISON",
        days=len(date_sets["pair"]),
        support_date_sha256=hashlib.sha256(
            ("\n".join(sorted(date_sets["pair"])) + "\n").encode()
        ).hexdigest(),
        comparisons=result,
        recommendation="Use the decision-relevant loss and prospective source availability before selecting a gauge or operational forecast.",
        scope="Retrospective saved-source comparison; no live prediction, sensor purchase, safety advice or measured deployment benefit.",
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--basin",
        choices=["wisconsin", "delaware", "susquehanna", "mississippi"],
        required=True,
    )
    p.add_argument("--year", type=int, choices=[2023, 2024], required=True)
    p.add_argument("--lag", type=int, choices=[3, 1], default=3)
    p.add_argument(
        "--scenario", choices=["normal", "seven-day-outage"], default="normal"
    )
    p.add_argument(
        "--qualifiers",
        choices=["all-approved", "empty-qualifiers"],
        default="all-approved",
    )
    a = p.parse_args()
    match = (
        lambda r: r["basin"] == a.basin
        and int(r["year"]) == a.year
        and int(r["lag"]) == a.lag
        and r["scenario"] == a.scenario
        and r["qualifier_rule"] == a.qualifiers
    )
    metrics = json.loads((ROOT / "results/v2/final/panel_metrics.json").read_bytes())
    rows = {r["model"]: r for r in metrics if match(r)}
    dates = {k: set() for k in ["persistence", "local", "pair"]}
    with (ROOT / "results/v2/final/predictions.csv").open(
        encoding="utf-8", newline=""
    ) as f:
        for row in csv.DictReader(f):
            if match(row):
                dates[row["model"]].add(row["date"])
    print(json.dumps(compare(rows, dates), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
