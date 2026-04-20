import sqlite3
import os

db_path = "reminderbot.sqlite"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]
    
    new_cols = [
        "watch_keywords_encrypted",
        "enable_devpost_encrypted",
        "enable_unstop_encrypted"
    ]
    
    for col in new_cols:
        if col not in columns:
            print(f"Adding column {col} to users table...")
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT DEFAULT ''")
    
    conn.commit()
    conn.close()
    print("Database schema updated (v2) successfully.")
else:
    print("Database file not found.")
