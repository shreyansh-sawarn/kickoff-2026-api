import sqlite3
import os

db_path = './data/wc26.db'
if not os.path.exists(db_path):
    for p in ['../data/wc26.db', 'app/data/wc26.db', '/app/data/wc26.db']:
        if os.path.exists(p):
            db_path = p
            break

conn = sqlite3.connect(db_path)
print('player_statistics count:', conn.execute('SELECT COUNT(*) FROM player_statistics').fetchone()[0])
print('events types:', conn.execute('SELECT type, COUNT(*) FROM events GROUP BY type').fetchall())

