
import sqlite3
conn = sqlite3.connect('/app/data/wc26.db')
print('player_statistics count:', conn.execute('SELECT COUNT(*) FROM player_statistics').fetchone()[0])
print('events types:', conn.execute('SELECT type, COUNT(*) FROM events GROUP BY type').fetchall())

