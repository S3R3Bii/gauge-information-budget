"""Project the explicit v2 window from retained captures; compute no model outcomes."""

import argparse
import csv
import gzip
import hashlib
import io
import json
from collections import Counter
from datetime import date
from pathlib import Path

from config import ROOT
from retrieve import FIELDS, project


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--originals", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists():
        raise ValueError("Fresh output required; preserve earlier evidence")
    out.mkdir(parents=True)
    prior = args.originals / "selected-projection-held/manifest.json"
    assert (
        digest(prior)
        == "60f7609f76b948154cbc4fb2b0ecfdffb859b40ab3937b36ef3659a981a5d58b"
    )
    source = json.loads(prior.read_bytes())
    held = args.originals / "selected-projection-held/observations.csv.gz"
    assert (
        digest(held)
        == source["public_sha256"]
        == "24463a6029001035aa48401dc2a0d99eb1bb5ef4cc2a194e30f4a758a5e75845"
    )
    stations = {r["station"]: r for r in source["stations"]}
    selected = []
    per_page = []
    for page in source["pages"]:
        original = args.originals / page["original_file"]
        assert digest(original) == page["sha256"]
        native = json.loads(original.read_bytes())
        assert len(native["features"]) == page["rows"]
        station = stations[page["station"]]
        n = 0
        for feature in native["features"]:
            p = feature["properties"]
            if "2019-12-01" <= p["time"] <= "2024-12-31":
                selected.append(
                    project(
                        p,
                        station["basin"],
                        station["role"],
                        station["station"],
                        station["series"],
                    )
                )
                n += 1
        per_page.append(dict(page, selected_v2_rows=n))
    keys = [(r["station"], r["date"]) for r in selected]
    assert len(set(keys)) == len(keys)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(selected)
    zipped = io.BytesIO()
    with gzip.GzipFile(
        fileobj=zipped, mode="wb", filename="", mtime=0, compresslevel=9
    ) as f:
        f.write(stream.getvalue().encode())
    (out / "source_cells.csv.gz").write_bytes(zipped.getvalue())
    manifest = dict(
        source="USGS Daily Mean Discharge, explicit Study14 v2 projection",
        parameter_code="00060",
        statistic_id="00003",
        start="2019-12-01",
        end="2024-12-31",
        captured_date_utc=source["captured_date_utc"],
        stations=source["stations"],
        pages=per_page,
        selected_rows=len(selected),
        public_file="data/v2/source_cells.csv.gz",
        public_sha256=digest(out / "source_cells.csv.gz"),
        original_capture_manifest_sha256=digest(prior),
        original_v1_approval_gate="FAILED_AND_PRESERVED",
        period_choice="Approval-coverage-informed v2 specified before any model; source values already present, not blinded",
        source_originals_private=True,
    )
    (out / "source_manifest.json").write_bytes(
        (json.dumps(manifest, indent=2) + "\n").encode()
    )
    usable = Counter()
    counts = Counter()
    qualified = Counter()
    normalized = []
    for r in selected:
        key = r["station"], int(r["date"][:4])
        counts[key] += 1
        if r["quality"] == "usable":
            usable[key] += 1
            qualified[key] += bool(r["qualifier"])
            normalized.append(
                {
                    k: r[k]
                    for k in [
                        "basin",
                        "role",
                        "station",
                        "date",
                        "source_value",
                        "qualifier",
                    ]
                }
            )
    coverage = []
    failures = []
    for station in source["stations"]:
        for year in range(2020, 2025):
            key = station["station"], year
            days = (date(year + 1, 1, 1) - date(year, 1, 1)).days
            row = dict(
                basin=station["basin"],
                role=station["role"],
                station=station["station"],
                year=year,
                calendar_days=days,
                source_rows=counts[key],
                usable_approved_days=usable[key],
                qualified_usable_days=qualified[key],
                missing_or_unusable_days=days - usable[key],
            )
            coverage.append(row)
            if usable[key] * 100 < 95 * days:
                failures.append(row)
    for name, rows in [
        ("measurements.csv", normalized),
        ("source_coverage.csv", coverage),
    ]:
        with (out / name).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    proof = dict(
        status="FAIL_V2_SOURCE_COVERAGE" if failures else "PASS_V2_SOURCE_COVERAGE",
        source_rows=len(selected),
        usable_rows_including_prewarm=len(normalized),
        stations=len(stations),
        station_year_coverage_gates=len(coverage),
        qualified_usable_rows=sum(bool(r["qualifier"]) for r in normalized),
        failed_station_years=failures,
        original_v1_gate="FAILED_UNCHANGED",
        predictive_metrics_computed=False,
        period_selection="Source-approval-informed and fixed before modelling; not blinded",
        source_archive_requests=0,
    )
    (out / "SOURCE_CHECK.json").write_bytes(
        (json.dumps(proof, indent=2) + "\n").encode()
    )
    print(json.dumps(proof))
    if failures:
        raise RuntimeError("V2 source gate failed; preserve output and stop")


if __name__ == "__main__":
    main()
