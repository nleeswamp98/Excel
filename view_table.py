import sqlite3
import pandas as pd
import config_v2

conn = sqlite3.connect(config_v2.DATABASE_FILE)

df = pd.read_sql_query(
    "SELECT * FROM NCF_Analysis;",
    conn
)

print(df.to_string())

conn.close()
