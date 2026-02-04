import pandas as pd
from pathlib import Path

RAW = Path("data/raw/tardis")
OUT = Path("data/processed/tardis")
OUT.mkdir(parents=True, exist_ok=True)

# ---------- Quotes ----------
quotes = pd.read_csv(
    RAW / "quotes/deribit_quotes_2019-11-01_BTC-PERPETUAL.csv.gz",
    parse_dates=["timestamp"]
)

quotes = quotes.rename(columns={
    "bid_price": "best_bid",
    "ask_price": "best_ask",
    "bid_amount": "best_bid_sz",
    "ask_amount": "best_ask_sz",
})

quotes["mid"] = (quotes["best_bid"] + quotes["best_ask"]) / 2
quotes["spread"] = quotes["best_ask"] - quotes["best_bid"]

quotes.to_parquet(OUT / "quotes.parquet", index=False)

# ---------- Trades ----------
trades = pd.read_csv(
    RAW / "trades/deribit_trades_2019-11-01_BTC-PERPETUAL.csv.gz",
    parse_dates=["timestamp"]
)

trades = trades.rename(columns={
    "amount": "qty"
})

trades["side_sign"] = trades["side"].map({"buy": 1, "sell": -1})

trades.to_parquet(OUT / "trades.parquet", index=False)

print("Tardis data ingested and written to Parquet")
