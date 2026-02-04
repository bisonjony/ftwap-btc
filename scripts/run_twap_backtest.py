import duckdb
import numpy as np
import pandas as pd
from pathlib import Path

# ======================
# Configuration
# ======================
DB_PATH = "data/crypto.duckdb"

SIDE = "BUY"                  # currently supports BUY only
Q_TOTAL = 5.0                 # BTC
HORIZON_SEC = 30 * 60         # 1800 seconds

# Baseline tolerance: if behind schedule by more than this (BTC), cross
BEHIND_TOL = 0.02

# Factor-aware parameters
Q_LOW = 0.20                  # urgency quantile (more patient)
Q_HIGH = 0.80                 # urgency quantile (more aggressive)
BEHIND_TOL_LOW = 0.05
BEHIND_TOL_HIGH = 0.00

# Passive fill model (simple + defensible)
# Passive fill probability increases with normalized vol_60s in [0,1]
P_MIN = 0.05
P_MAX = 0.95
PASSIVE_FILL_FRACTION = 0.70  # queue/competition discount: even when you "fill", you get ~70% of desired slice

OUT_DIR = Path("results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SEED = 0


def clip(x, lo, hi):
    return np.minimum(np.maximum(x, lo), hi)


def add_passive_fill_probability(window: pd.DataFrame) -> pd.DataFrame:
    """
    Build a passive fill probability p_fill in [P_MIN, P_MAX]
    based on normalized vol_60s within the window.
    """
    w = window.copy()
    vol = w["vol_60s"].to_numpy(dtype=float)

    # Robust normalize to [0, 1] using percentiles to avoid a single spike dominating
    v_lo = np.nanpercentile(vol, 5)
    v_hi = np.nanpercentile(vol, 95)
    if not np.isfinite(v_lo) or not np.isfinite(v_hi) or v_hi <= v_lo:
        # fallback: constant probability
        vol_norm = np.full_like(vol, 0.5)
    else:
        vol_norm = (vol - v_lo) / (v_hi - v_lo)
        vol_norm = clip(vol_norm, 0.0, 1.0)

    p_fill = P_MIN + (P_MAX - P_MIN) * vol_norm
    p_fill = clip(p_fill, P_MIN, P_MAX)
    w["p_fill_passive"] = p_fill
    return w


def simulate_twap(window: pd.DataFrame, mode: str, rng: np.random.Generator) -> pd.DataFrame:
    """
    Simulate TWAP execution with a simple passive fill model.
    - Passive: fill only partially with probability p_fill_passive.
    - Cross: fill fully at best_ask immediately.
    """
    assert mode in {"baseline", "factor"}
    assert SIDE == "BUY", "v2 simulator currently supports BUY only."

    bid = window["best_bid"].to_numpy(float)
    ask = window["best_ask"].to_numpy(float)
    mid = window["mid"].to_numpy(float)
    urgency = window["urgency_pca1"].to_numpy(float)
    p_fill = window["p_fill_passive"].to_numpy(float)

    if mode == "factor":
        u_low = np.quantile(urgency, Q_LOW)
        u_high = np.quantile(urgency, Q_HIGH)
    else:
        u_low = u_high = np.nan

    target_rate = Q_TOTAL / HORIZON_SEC
    executed = 0.0
    records = []

    for i in range(len(window)):
        ts = window["ts"].iloc[i]
        target_qty = (i + 1) * target_rate
        behind = target_qty - executed
        remaining = Q_TOTAL - executed

        if remaining <= 1e-12:
            records.append({
                "ts": ts,
                "action": "done",
                "exec_qty": 0.0,
                "exec_px": np.nan,
                "cum_qty": executed,
                "target_qty": target_qty,
                "behind": behind,
                "mid": mid[i],
                "best_bid": bid[i],
                "best_ask": ask[i],
                "urgency": urgency[i],
                "p_fill_passive": p_fill[i],
            })
            continue

        # Determine crossing tolerance / proactive behavior
        behind_tol = BEHIND_TOL
        proactive = False
        if mode == "factor":
            if urgency[i] >= u_high:
                behind_tol = BEHIND_TOL_HIGH
                proactive = True
            elif urgency[i] <= u_low:
                behind_tol = BEHIND_TOL_LOW

        # Decide whether to cross
        cross = behind > behind_tol
        if mode == "factor" and proactive:
            cross = True

        # Desired trade amount this second: at least base slice, more if behind
        desired = min(max(behind, target_rate), remaining)

        if cross:
            exec_qty = desired
            exec_px = ask[i]
            action = "cross"
        else:
            # Passive fill is uncertain + partial
            fill_event = (rng.random() < p_fill[i])
            exec_qty = desired * PASSIVE_FILL_FRACTION if fill_event else 0.0
            exec_qty = min(exec_qty, remaining)
            exec_px = bid[i] if exec_qty > 0 else np.nan
            action = "passive_fill" if exec_qty > 0 else "passive_no_fill"

        executed += exec_qty

        records.append({
            "ts": ts,
            "action": action,
            "exec_qty": exec_qty,
            "exec_px": exec_px,
            "cum_qty": executed,
            "target_qty": target_qty,
            "behind": target_qty - executed,
            "mid": mid[i],
            "best_bid": bid[i],
            "best_ask": ask[i],
            "urgency": urgency[i],
            "p_fill_passive": p_fill[i],
        })

    out = pd.DataFrame(records)

    # If we somehow don't fully fill by the end, force completion at final ask
    # (This is a common "completion at end" assumption for TWAP comparisons.)
    if out["cum_qty"].iloc[-1] < Q_TOTAL - 1e-8:
        remaining = Q_TOTAL - out["cum_qty"].iloc[-1]
        last = out.iloc[-1].copy()
        last["ts"] = last["ts"]  # same timestamp
        last["action"] = "final_cross"
        last["exec_qty"] = remaining
        last["exec_px"] = window["best_ask"].iloc[-1]
        last["cum_qty"] = Q_TOTAL
        last["target_qty"] = Q_TOTAL
        last["behind"] = 0.0
        out = pd.concat([out, pd.DataFrame([last])], ignore_index=True)

    traded = out["exec_qty"].sum()
    vwap_exec = (out["exec_px"].fillna(0) * out["exec_qty"]).sum() / traded
    vwap_mid = (out["mid"] * out["exec_qty"]).sum() / traded

    out.attrs["summary"] = {
        "mode": mode,
        "Q_TOTAL": Q_TOTAL,
        "HORIZON_SEC": HORIZON_SEC,
        "filled_qty": float(traded),
        "vwap_exec": float(vwap_exec),
        "vwap_mid": float(vwap_mid),
        "slippage_vs_mid": float(vwap_exec - vwap_mid),
        "cross_events": int(out["action"].isin(["cross", "final_cross"]).sum()),
        "passive_fill_events": int((out["action"] == "passive_fill").sum()),
        "passive_no_fill_events": int((out["action"] == "passive_no_fill").sum()),
        "final_cross_used": int((out["action"] == "final_cross").sum()),
    }

    return out


def main():
    con = duckdb.connect(DB_PATH)

    # ---- Load data: features backbone, factor left-joined ----
    df = con.execute("""
        SELECT
            f.ts,
            f.mid,
            f.best_bid,
            f.best_ask,
            f.best_bid_sz,
            f.best_ask_sz,
            f.spread,
            f.rv_60s,
            f.ofi_60s,
            f.vol_60s,
            f.book_imbalance,
            fa.urgency_pca1
        FROM features_1s f
        LEFT JOIN factors_1s fa
          ON f.ts = fa.ts
        ORDER BY f.ts
    """).fetchdf()

    # ---- Align to 1-second grid + forward fill ----
    df["ts"] = pd.to_datetime(df["ts"])
    df = df.set_index("ts").sort_index()

    ffill_cols = [
        "mid", "best_bid", "best_ask",
        "best_bid_sz", "best_ask_sz", "spread",
        "rv_60s", "ofi_60s", "vol_60s",
        "book_imbalance", "urgency_pca1"
    ]

    df = df.asfreq("1s")
    df[ffill_cols] = df[ffill_cols].ffill()
    df = df.dropna(subset=["urgency_pca1"])

    if len(df) < HORIZON_SEC:
        raise RuntimeError("Not enough data for requested horizon after alignment.")

    # ---- Choose the first HORIZON_SEC seconds (simple, reproducible) ----
    window = df.iloc[:HORIZON_SEC].reset_index()
    print(f"Using window: {window['ts'].iloc[0]} → {window['ts'].iloc[-1]} (rows={len(window)})")

    # Add passive fill probability
    window = add_passive_fill_probability(window)

    # ---- Simulate ----
    rng0 = np.random.default_rng(SEED)
    rng1 = np.random.default_rng(SEED)  # same seed for fair comparison

    baseline = simulate_twap(window, mode="baseline", rng=rng0)
    factor = simulate_twap(window, mode="factor", rng=rng1)

    summary = pd.DataFrame([baseline.attrs["summary"], factor.attrs["summary"]])

    print("\n=== TWAP Backtest Summary (v2, passive fill model) ===")
    print(summary)

    # ---- Save outputs ----
    baseline.to_parquet(OUT_DIR / "twap_baseline_log_v2.parquet", index=False)
    factor.to_parquet(OUT_DIR / "twap_factor_log_v2.parquet", index=False)
    summary.to_csv(OUT_DIR / "twap_summary_v2.csv", index=False)

    print("\nSaved results to:")
    print("  results/twap_baseline_log_v2.parquet")
    print("  results/twap_factor_log_v2.parquet")
    print("  results/twap_summary_v2.csv")


if __name__ == "__main__":
    main()
