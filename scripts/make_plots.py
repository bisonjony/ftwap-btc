import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

BASELINE_PATH = Path("results/twap_baseline_log_v2.parquet")
FACTOR_PATH   = Path("results/twap_factor_log_v2.parquet")
FIG_DIR       = Path("results/figures")
FIG_DIR.mkdir(parents=True, exist_ok=True)

Q_TOTAL = 5.0
HORIZON_SEC = 1800  # 30 minutes


def load_logs():
    b = pd.read_parquet(BASELINE_PATH)
    f = pd.read_parquet(FACTOR_PATH)

    # ensure datetime
    b["ts"] = pd.to_datetime(b["ts"])
    f["ts"] = pd.to_datetime(f["ts"])

    # keep only the first HORIZON_SEC rows for consistent plotting
    b = b.sort_values("ts").reset_index(drop=True)
    f = f.sort_values("ts").reset_index(drop=True)

    # sometimes final_cross adds an extra row
    if len(b) > HORIZON_SEC:
        b = b.iloc[:HORIZON_SEC].copy()
    if len(f) > HORIZON_SEC:
        f = f.iloc[:HORIZON_SEC].copy()

    return b, f


def plot_cum_qty_vs_schedule(b, f):
    # schedule target
    t = np.arange(1, len(b) + 1)
    target = Q_TOTAL * t / HORIZON_SEC

    plt.figure()
    plt.plot(b["ts"], b["cum_qty"], label="Baseline TWAP")
    plt.plot(f["ts"], f["cum_qty"], label="Factor-aware TWAP")
    plt.plot(b["ts"], target, label="TWAP target (linear)")

    plt.xlabel("Time")
    plt.ylabel("Cumulative executed qty (BTC)")
    plt.title("Cumulative execution vs TWAP schedule")
    plt.legend()
    plt.tight_layout()
    plt.savefig(FIG_DIR / "01_cum_qty_vs_schedule.png", dpi=200)
    plt.close()


def plot_urgency_and_crosses(b, f):
    # We only have urgency in logs; baseline urgency is recorded too (from window)
    # Mark cross events
    b_cross = b[b["action"].isin(["cross", "final_cross"])]
    f_cross = f[f["action"].isin(["cross", "final_cross"])]

    plt.figure()
    plt.plot(b["ts"], b["urgency"], label="Urgency factor (PCA1)")

    # vertical markers for cross decisions
    plt.scatter(b_cross["ts"], b_cross["urgency"], marker="x", label="Baseline cross", s=20)
    plt.scatter(f_cross["ts"], f_cross["urgency"], marker="o", label="Factor cross", s=10)

    plt.xlabel("Time")
    plt.ylabel("Urgency factor (standardized PCA1)")
    plt.title("Urgency factor with aggressive-cross decisions")
    plt.legend()
    plt.tight_layout()
    plt.savefig(FIG_DIR / "02_urgency_with_cross_markers.png", dpi=200)
    plt.close()


def plot_slippage_time_series(b, f):
    # Slippage per executed slice: (exec_px - mid) for BUY
    # For no-fill rows exec_px is NaN; treat those as 0 impact for plotting
    def per_step_slip(df):
        slip = df["exec_px"] - df["mid"]
        slip = slip.where(df["exec_qty"] > 0)  # only where trades occurred
        return slip

    b_slip = per_step_slip(b)
    f_slip = per_step_slip(f)

    plt.figure()
    plt.plot(b["ts"], b_slip, label="Baseline per-step (exec_px - mid)")
    plt.plot(f["ts"], f_slip, label="Factor per-step (exec_px - mid)")

    plt.xlabel("Time")
    plt.ylabel("Per-step slippage ($)")
    plt.title("Per-step slippage over time (BUY)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(FIG_DIR / "03_slippage_time_series.png", dpi=200)
    plt.close()


def main():
    b, f = load_logs()

    plot_cum_qty_vs_schedule(b, f)
    plot_urgency_and_crosses(b, f)
    plot_slippage_time_series(b, f)

    print("Saved figures to:", FIG_DIR)
    for p in sorted(FIG_DIR.glob("*.png")):
        print(" -", p)


if __name__ == "__main__":
    main()
