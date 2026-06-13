import sqlite3

def update_db():
    conn = sqlite3.connect('data/wc26.db')
    cursor = conn.cursor()
    
    # Alter match_stats table
    try:
        cursor.execute("ALTER TABLE match_stats ADD COLUMN yellow_cards INTEGER DEFAULT 0;")
        print("Added yellow_cards column")
    except sqlite3.OperationalError as e:
        print(f"Column yellow_cards might already exist: {e}")
        
    try:
        cursor.execute("ALTER TABLE match_stats ADD COLUMN red_cards INTEGER DEFAULT 0;")
        print("Added red_cards column")
    except sqlite3.OperationalError as e:
        print(f"Column red_cards might already exist: {e}")
        
    # Delete bad events from ESPN
    cursor.execute("DELETE FROM events WHERE source = 'espn';")
    deleted = cursor.rowcount
    print(f"Deleted {deleted} bad ESPN timeline events.")
    
    conn.commit()
    conn.close()
    
if __name__ == "__main__":
    update_db()
