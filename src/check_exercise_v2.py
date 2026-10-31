"""Three authored comparison cases, independent of recorded discharge outcomes."""

import json
from review_cli_v2 import compare


def main():
    dates = {
        "persistence": {"2024-01-01", "2024-01-02"},
        "local": {"2024-01-01", "2024-01-02"},
        "pair": {"2024-01-01", "2024-01-02"},
    }
    rows = {
        "persistence": dict(log_mse=0.2, cfs_mse=200.0),
        "local": dict(log_mse=0.1, cfs_mse=100.0),
        "pair": dict(log_mse=0.09, cfs_mse=121.0),
    }
    reversal = compare(rows, dates)
    assert (
        reversal["status"] == "SAVED_COMMON_SUPPORT_COMPARISON"
        and reversal["days"] == 2
    )
    assert reversal["comparisons"]["log-flow"]["pair_beats_local"] is True
    assert reversal["comparisons"]["cubic-feet-per-second"]["pair_beats_local"] is False
    rows["pair"]["cfs_mse"] = 81.0
    same = compare(rows, dates)
    assert all(x["pair_beats_local"] for x in same["comparisons"].values())
    dates["pair"] = {"2024-01-02", "2024-01-03"}
    unavailable = compare(rows, dates)
    assert unavailable["status"] == "UNAVAILABLE_COMMON_SUPPORT"
    print(
        json.dumps(
            dict(
                status="PASS_THREE_AUTHORED_PANEL_REVIEWS",
                conditions=6,
                source="Authored metrics/date sets; not measured outcomes",
            )
        )
    )


if __name__ == "__main__":
    main()
