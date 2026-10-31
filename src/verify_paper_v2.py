"""Bind the reviewed independent manuscript to both protocol versions and complete results."""

import ast, hashlib, json
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
read = lambda n: json.loads((ROOT / n).read_bytes())


def main():
    tex = (ROOT / "paper/main.tex").read_text(encoding="utf-8")
    pdf = PdfReader(ROOT / "paper/manuscript.pdf")
    assert len(pdf.pages) == 6
    pages = [p.extract_text() or "" for p in pdf.pages]
    assert all(p.strip() for p in pages)
    flat = "\n".join(pages)
    checks = 0
    bindings = read("paper_bindings_v2.json")
    for name, item in bindings.items():
        path = (ROOT / item["file"]).resolve()
        assert path.is_relative_to(ROOT) and path.suffix == ".json"
        value = json.loads(path.read_bytes())
        for key in item["pointer"]:
            value = value[key]
        assert item["value"] == value
        checks += 1
        fmt = item["format"]
        assert fmt in ["integer", "percent", "million", "six", "text"]
        display = (
            f"{value:,}"
            if fmt == "integer"
            else (
                f"{value*100:.2f}"
                if fmt == "percent"
                else (
                    f"{value/1e6:.2f}"
                    if fmt == "million"
                    else f"{value:.6f}" if fmt == "six" else str(value)
                )
            )
        )
        assert item["display"] == display
        checks += 1
        assert (
            "\\newcommand{\\" + name + "}{" + display + "}" in tex
            and "\\" + name + "{}" in tex
        )
        checks += 1
        assert display in flat
        checks += 1
    assert len(bindings) == 43
    checks += 1
    failure = read("results/SOURCE_FAILURE.json")
    assert (
        failure["released"] is False
        and failure["source_gate"].startswith("FAIL")
        and [x["usable_approved_days"] for x in failure["failed_station_years"]]
        == [64, 322, 335]
    )
    checks += 1
    source = read("data/v2/SOURCE_CHECK.json")
    assert (
        source["original_v1_gate"] == "FAILED_UNCHANGED"
        and source["station_year_coverage_gates"] == 40
        and source["source_rows"] == 14864
    )
    checks += 1
    panels = read("results/v2/final/panel_metrics.json")
    summary = read("results/v2/final/summary.json")
    assert len(panels) == 192 and all(
        r["pair_minus_local"] > 0 for r in summary["primary_panels"]
    )
    checks += 1
    comparisons = []
    for pair in [p for p in panels if p["model"] == "pair"]:
        local = next(
            p
            for p in panels
            if p["model"] == "local"
            and all(
                p[k] == pair[k]
                for k in ["basin", "year", "lag", "scenario", "qualifier_rule"]
            )
        )
        comparisons.append(
            pair["log_mse_skill_vs_persistence"] - local["log_mse_skill_vs_persistence"]
        )
    assert len(comparisons) == 64 and min(comparisons) > 0
    checks += 1
    target = [
        p
        for p in panels
        if p["basin"] == "susquehanna"
        and p["year"] == 2023
        and p["lag"] == 3
        and p["scenario"] == "normal"
        and p["qualifier_rule"] == "all-approved"
    ]
    local = next(p for p in target if p["model"] == "local")
    pair = next(p for p in target if p["model"] == "pair")
    assert pair["log_mse"] < local["log_mse"] and pair["cfs_mse"] > local["cfs_mse"]
    checks += 1
    assert all(
        p["conditional_90_percent_intervals"]["pair_minus_local"]["lower"] > 0
        for p in read("results/v2/final/bootstrap.json")
    )
    checks += 1
    assert read("data/v2/frozen_dependencies.json")["dependency_count"] == 34
    checks += 1
    methods = sum(
        isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
        for p in (ROOT / "tests").glob("test_*.py")
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8")))
    )
    assert methods == 23
    checks += 1
    for suffix, version in [("310", "3.10.11"), ("312", "3.12.14")]:
        r = read(f"results/v2/reproduction_cpython{suffix}.json")
        assert (
            r["status"] == "PASS_ANALYSIS_ONLY_REPLAY"
            and r["python"] == version
            and r["exact_fields"] == 1079126
            and r["numeric_fields"] == 298395
            and r["source_files_unchanged"] == 3
        )
        checks += 1
    for phrase in [
        "Not peer reviewed",
        "not a win on every loss",
        "It does not certify that version 1 passed",
        "approval-informed choice",
        "not a blinded collection",
        "There is no validation refit",
        "geographic separation for configuration selection",
        "not 64 independent replications",
        "reverses the model ordering",
        "does not reacquire mutable historical API responses",
        "No deployment, realized resource saving",
        "no new estimator",
    ]:
        assert phrase in tex, phrase
        checks += 1
    build = read("paper/build_receipt.json")
    assert (
        build["status"] == "PASS_COMPILE_AND_SIX_PAGE_VISUAL_REVIEW"
        and not build["layout_warnings"]
        and build["pages"] == 6
    )
    checks += 1
    for name, digest in build["artifact_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
        checks += 1
    for p in (ROOT / "paper/images").glob("*.pdf"):
        assert p.read_bytes() == (ROOT / "figures" / p.name).read_bytes()
        checks += 1
    result = dict(
        status="PASS_SOURCE_BOUND_V2_MANUSCRIPT",
        pages=6,
        bound_values=len(bindings),
        conditions=checks,
        manuscript_sha256=hashlib.sha256(
            (ROOT / "paper/manuscript.pdf").read_bytes()
        ).hexdigest(),
        page_characters=[len(p) for p in pages],
        v1_failure_and_physical_unit_reversal_explicit=True,
        rendering="All six current Poppler renders inspected; CI checks source bindings and reviewed artifact bytes without compiling TeX.",
    )
    (ROOT / "paper_verification_v2.json").write_bytes(
        (json.dumps(result, indent=2) + "\n").encode()
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
