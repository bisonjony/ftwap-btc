-- sql/10_quotes_1s.sql
CREATE OR REPLACE TABLE quotes_1s AS
WITH q AS (
  SELECT
    CAST(timestamp AS BIGINT) AS ts_us,
    best_bid,
    best_ask,
    best_bid_sz,
    best_ask_sz,
    mid,
    spread
  FROM quotes
)
SELECT
  date_trunc('second', to_timestamp(ts_us / 1e6)) AS ts,

  -- last observation in each second
  arg_max(mid, ts_us)         AS mid,
  arg_max(spread, ts_us)      AS spread,
  arg_max(best_bid, ts_us)    AS best_bid,
  arg_max(best_ask, ts_us)    AS best_ask,
  arg_max(best_bid_sz, ts_us) AS best_bid_sz,
  arg_max(best_ask_sz, ts_us) AS best_ask_sz

FROM q
GROUP BY 1
ORDER BY 1;
