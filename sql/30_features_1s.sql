-- sql/30_features_1s.sql
CREATE OR REPLACE TABLE features_1s AS
WITH base AS (
  SELECT
    q.ts,
    q.mid,
    q.spread,
    q.best_bid,
    q.best_ask,
    q.best_bid_sz,
    q.best_ask_sz,

    COALESCE(t.n_trades, 0)        AS n_trades,
    COALESCE(t.vol_1s, 0.0)        AS vol_1s,
    COALESCE(t.buy_vol_1s, 0.0)    AS buy_vol_1s,
    COALESCE(t.sell_vol_1s, 0.0)   AS sell_vol_1s,
    COALESCE(t.signed_vol_1s, 0.0) AS signed_vol_1s,
    t.vwap_1s
  FROM quotes_1s q
  LEFT JOIN trades_1s t
    ON q.ts = t.ts
),
rets AS (
  SELECT
    *,
    CASE
      WHEN lag(mid) OVER (ORDER BY ts) IS NULL THEN NULL
      WHEN mid <= 0 OR lag(mid) OVER (ORDER BY ts) <= 0 THEN NULL
      ELSE ln(mid) - ln(lag(mid) OVER (ORDER BY ts))
    END AS r1
  FROM base
)
SELECT
  *,

  -- Top-of-book size imbalance
  (best_bid_sz - best_ask_sz)
    / NULLIF(best_bid_sz + best_ask_sz, 0) AS book_imbalance,

  -- Rolling 30s
  SUM(vol_1s) OVER w30                       AS vol_30s,
  SUM(signed_vol_1s) OVER w30                AS signed_vol_30s,
  (SUM(signed_vol_1s) OVER w30)
    / NULLIF(SUM(vol_1s) OVER w30, 0)        AS ofi_30s,
  stddev_samp(r1) OVER w30                   AS rv_30s,

  -- Rolling 60s
  SUM(vol_1s) OVER w60                       AS vol_60s,
  (SUM(signed_vol_1s) OVER w60)
    / NULLIF(SUM(vol_1s) OVER w60, 0)        AS ofi_60s,
  stddev_samp(r1) OVER w60                   AS rv_60s

FROM rets
WINDOW
  w30 AS (ORDER BY ts ROWS BETWEEN 29 PRECEDING AND CURRENT ROW),
  w60 AS (ORDER BY ts ROWS BETWEEN 59 PRECEDING AND CURRENT ROW)
ORDER BY ts;
