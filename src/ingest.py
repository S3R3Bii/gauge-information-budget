"""Validate complete source accounting and exact Approved-day coverage; no outcome metrics."""

import csv, gzip, hashlib, json
from collections import Counter
from datetime import date
from decimal import Decimal
from config import ROOT, PAIRS


def main():
    manifest = json.loads((ROOT / "data/source/manifest.json").read_text())
    path = ROOT / manifest["public_file"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest["public_sha256"]
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    seen = set()
    quality = Counter()
    usable = Counter()
    allcounts = Counter()
    normalized = []
    lookup = {
        site["site"]: (basin, role, site["series"])
        for basin, pair in PAIRS.items()
        for role, site in zip(["target", "additional"], pair)
    }
    for r in rows:
        station = r["station"]
        assert (r["basin"], r["role"], r["series"]) == lookup[station]
        d = date.fromisoformat(r["date"])
        key = station, r["date"]
        assert key not in seen
        seen.add(key)
        assert "2019-12-01" <= r["date"] <= "2025-12-31"
        assert r["unit"] == "ft^3/s" and r["approval"] in ["Approved", "Provisional"]
        assert r["quality"] in ["usable", "missing_or_nonnumeric", "unapproved"]
        allcounts[station, d.year] += 1
        quality[station, d.year, r["quality"], bool(r["qualifier"])] += 1
        if r["quality"] == "usable":
            q = Decimal(r["source_value"])
            assert q.is_finite() and q >= 0 and r["approval"] == "Approved"
            usable[station, d.year] += 1
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
    assert len(rows) == manifest["selected_rows"]
    summary = []
    for station, (basin, role, series) in sorted(lookup.items()):
        for year in range(2020, 2026):
            days = (date(year + 1, 1, 1) - date(year, 1, 1)).days
            n = usable[station, year]
            assert n * 100 >= 95 * days, "Fixed 95percent Approved coverage gate failed"
            summary.append(
                {
                    "basin": basin,
                    "role": role,
                    "station": station,
                    "year": year,
                    "calendar_days": days,
                    "source_rows": allcounts[station, year],
                    "usable_approved_days": n,
                    "missing_or_unusable_days": days - n,
                    "qualified_usable_days": sum(
                        1
                        for r in normalized
                        if r["station"] == station
                        and r["date"].startswith(str(year))
                        and r["qualifier"]
                    ),
                }
            )
    for name, data in [
        ("data/measurements.csv", normalized),
        ("results/source_coverage.csv", summary),
    ]:
        with (ROOT / name).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(data)
    cert = {
        "status": "PASS",
        "source_rows": len(rows),
        "usable_rows_including_prewarm": len(normalized),
        "stations": 8,
        "station_year_coverage_gates": 48,
        "qualified_usable_rows": sum(bool(r["qualifier"]) for r in normalized),
        "all_inputs_not_blinded": True,
        "this_command_computes_no_predictive_metrics": True,
        "scope": "Exact source fields/counts/units/duplicates and fixed Approved coverage; no station/window swaps or imputation",
        "vintage_limit": "Later approved daily values; actual historical availability and warning latency remain unverified",
    }
    (ROOT / "results/SOURCE_CHECK.json").write_text(
        json.dumps(cert, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(cert))


if __name__ == "__main__":
    main()
