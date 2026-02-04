import duckdb

con = duckdb.connect("data/crypto.duckdb")

con.execute(open("sql/10_quotes_1s.sql", "r").read())

con.execute(open("sql/20_trades_1s.sql", "r").read())

con.execute(open("sql/30_features_1s.sql", "r").read())


