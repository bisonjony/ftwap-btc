import duckdb

con = duckdb.connect("data/crypto.duckdb")

con.execute("""
CREATE TABLE quotes AS
SELECT * FROM read_parquet('data/processed/tardis/quotes.parquet');
""")

con.execute("""
CREATE TABLE trades AS
SELECT * FROM read_parquet('data/processed/tardis/trades.parquet');
""")

print(con.execute("SELECT COUNT(*) FROM quotes").fetchone())
print(con.execute("SELECT COUNT(*) FROM trades").fetchone())

# df = con.execute("DESCRIBE quotes").fetchdf()
# print(df)
# print(con.execute("DESCRIBE trades").fetchdf())
