-- sql/20_trades_1s.sql
CREATE OR REPLACE TABLE trades_1s AS
WITH tr AS (
  SELECT
    date_trunc('second', to_timestamp(CAST(timestamp AS BIGINT) / 1e6)) AS ts,
    price,
    CAST(qty AS DOUBLE) AS qty,
    side
  FROM trades
)
SELECT
  ts,
  COUNT(*) AS n_trades,
  SUM(qty) AS vol_1s,
  SUM(CASE WHEN side = 'buy'  THEN qty ELSE 0 END) AS buy_vol_1s,
  SUM(CASE WHEN side = 'sell' THEN qty ELSE 0 END) AS sell_vol_1s,
  SUM(CASE WHEN side = 'buy'  THEN qty ELSE -qty END) AS signed_vol_1s,
  SUM(price * qty) / NULLIF(SUM(qty), 0) AS vwap_1s
FROM tr
GROUP BY 1
ORDER BY 1;
