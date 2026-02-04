import pandas as pd
import sqlite3

conn = sqlite3.connect('assets.db')
df_check = pd.read_sql("SELECT * FROM assets LIMIT 5;", conn)
print(df_check)
conn.close()
