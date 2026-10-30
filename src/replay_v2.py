"""Recompute all fixed v2 results from public selected cells in a full-history clone."""

import argparse, csv, json, math, platform, subprocess, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


class Comparison:
    def __init__(self):
        self.exact = 0
        self.numeric = 0
        self.max_fraction = 0.0
        self.as_run = 0

    def value(self, a, b, path=""):
        if isinstance(a, dict):
            assert set(a) == set(b), path
            for k in a:
                if k in [
                    "maximum_log_space_difference",
                    "maximum_cfs_difference_fraction_of_declared_tolerance",
                ]:
                    assert (
                        math.isfinite(b[k])
                        and b[k] >= 0
                        and b[k]
                        <= (1e-8 if k == "maximum_log_space_difference" else 1.0)
                    )
                    self.as_run += 1
                else:
                    self.value(a[k], b[k], path + "/" + k)
        elif isinstance(a, list):
            assert len(a) == len(b), path
            for x, y in zip(a, b):
                self.value(x, y, path)
        elif isinstance(a, float):
            assert isinstance(b, (int, float)) and math.isfinite(b), path
            field = path.rsplit("/", 1)[-1]
            tolerance = (
                1e-4 + 1e-10 * abs(a)
                if ("cfs" in field and field != "train_mean_normalized_cfs_rmse")
                else 1e-8
            )
            difference = abs(a - b)
            assert difference <= tolerance, (path, a, b, tolerance)
            self.numeric += 1
            self.max_fraction = max(self.max_fraction, difference / tolerance)
        else:
            assert a == b, (path, a, b)
            self.exact += 1

    def file(self, a, b):
        if a.suffix == ".json":
            self.value(json.loads(a.read_bytes()), json.loads(b.read_bytes()), a.name)
        elif a.suffix == ".csv":
            with a.open(encoding="utf-8", newline="") as f:
                x = list(csv.DictReader(f))
            with b.open(encoding="utf-8", newline="") as f:
                y = list(csv.DictReader(f))
            assert len(x) == len(y)
            for left, right in zip(x, y):
                assert set(left) == set(right)
                for key, value in left.items():
                    if key in [
                        "actual_log",
                        "actual_cfs",
                        "predicted_log",
                        "predicted_cfs",
                    ]:
                        self.value(float(value), float(right[key]), key)
                    else:
                        self.value(value, right[key], key)
        else:
            assert a.read_bytes() == b.read_bytes()
            self.exact += 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--analysis-only", action="store_true")
    a = p.parse_args()
    if a.out.exists():
        raise ValueError("Fresh replay output required")
    a.out.mkdir(parents=True)
    assert (
        subprocess.check_output(
            ["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT, text=True
        ).strip()
        == "false"
    )

    def run(name, *args):
        subprocess.run(
            [sys.executable, str(ROOT / "src" / name), *map(str, args)],
            cwd=ROOT,
            check=True,
        )

    run("verify_public_source_v2.py")
    comparison = Comparison()
    proofs = {}
    for phase in ["development", "final"]:
        folder = a.out / phase
        run("analyze_v2.py", "--phase", phase, "--out", folder)
        run("verify_analysis_v2.py", "--phase", phase, "--out", folder)
        for source in (ROOT / "results/v2" / phase).iterdir():
            if source.name != "runtime.json":
                comparison.file(source, folder / source.name)
        proofs[phase] = json.loads(
            (folder / "independent_verification.json").read_bytes()
        )["conditions"]
    subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=ROOT,
        check=True,
    )
    run("check_exercise_v2.py")
    if not a.analysis_only:
        run("verify_figures_v2.py")
        run("verify_paper_v2.py")
    result = dict(
        status=(
            "PASS_ANALYSIS_ONLY_REPLAY"
            if a.analysis_only
            else "PASS_COMPLETE_V2_OFFLINE_REPLAY"
        ),
        python=platform.python_version(),
        numpy=np.__version__,
        exact_fields=comparison.exact,
        numeric_fields=comparison.numeric,
        independently_bounded_as_run_diagnostics=comparison.as_run,
        maximum_difference_fraction_of_declared_tolerance=comparison.max_fraction,
        phase_conditions=proofs,
        source="Selected public USGS facts; original private captures separately verified and hash-bound",
        original_v1_gate="FAILED_UNCHANGED",
        full_history_repository=True,
        source_requests=0,
        fixtures=23,
        authored_cases=3,
    )
    (a.out / "replay_receipt.json").write_bytes(
        (json.dumps(result, indent=2) + "\n").encode()
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
