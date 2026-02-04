import duckdb
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

DB_PATH = "data/crypto.duckdb"
OUT_PARQUET = Path("data/processed/factors_1s.parquet")

# ---------- config: choose factor inputs ----------
FEATURE_COLS = [
    "spread",
    "rv_60s",
    "ofi_60s",
    "vol_60s",
    "book_imbalance",
]

def main():
    con = duckdb.connect(DB_PATH)

    # Pull features
    # We keep ts + mid for later backtest alignment
    query = f"""
    SELECT
      ts,
      mid,
      {", ".join(FEATURE_COLS)}
    FROM features_1s
    ORDER BY ts
    """
    df = con.execute(query).fetchdf()

    # Drop rows where any of the factor inputs are missing
    df_clean = df.dropna(subset=FEATURE_COLS).copy()
    if df_clean.empty:
        raise RuntimeError("After dropping NA rows for factor inputs, df_clean is empty. Check your feature columns.")

    X = df_clean[FEATURE_COLS].astype(float).values

    # Standardize
    scaler = StandardScaler()
    Xz = scaler.fit_transform(X)

    # PCA: 1 component = "urgency factor"
    pca = PCA(n_components=1, random_state=0)
    factor = pca.fit_transform(Xz).reshape(-1)

    # Make factor direction intuitive:
    # We want higher factor -> "more urgent to cross".
    # A simple choice: enforce positive correlation with spread + volatility.
    corr_spread = np.corrcoef(factor, df_clean["spread"].values)[0, 1]
    corr_rv = np.corrcoef(factor, df_clean["rv_60s"].values)[0, 1]
    if (corr_spread + corr_rv) < 0:
        factor = -factor
        pca.components_[0, :] *= -1

    df_clean["urgency_pca1"] = factor

    # Print PCA info
    loadings = pd.Series(pca.components_[0], index=FEATURE_COLS).sort_values(key=np.abs, ascending=False)
    print("\nPCA explained variance ratio (PC1):", float(pca.explained_variance_ratio_[0]))
    print("\nPC1 loadings (sorted by abs value):")
    print(loadings)

    print("\nPreview:")
    print(df_clean[["ts", "mid"] + FEATURE_COLS + ["urgency_pca1"]].head())

    # Save to Parquet
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df_clean.to_parquet(OUT_PARQUET, index=False)
    print(f"\n Wrote: {OUT_PARQUET}")

    # also create DuckDB table for SQL joins later
    con.execute("CREATE OR REPLACE TABLE factors_1s AS SELECT * FROM read_parquet(?)", [str(OUT_PARQUET)])
    print("Created DuckDB table: factors_1s")

    # Quick counts
    n_features = con.execute("SELECT COUNT(*) FROM features_1s").fetchone()[0]
    n_factors = con.execute("SELECT COUNT(*) FROM factors_1s").fetchone()[0]
    print(f"\nCounts: features_1s={n_features}, factors_1s={n_factors} (dropped warmup NAs)")

if __name__ == "__main__":
    main()
