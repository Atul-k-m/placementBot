import sqlite3
import os

db_path = "reminderbot.sqlite"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check current columns
    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]
    
    new_cols = [
        "twilio_sid_encrypted",
        "twilio_token_encrypted",
        "twilio_from_encrypted"
    ]
    
    for col in new_cols:
        if col not in columns:
            print(f"Adding column {col} to users table...")
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT DEFAULT ''")
    
    conn.commit()
    conn.close()
    print("Database schema updated successfully.")
else:
    print("Database file not found. It will be created with correct schema on next start.")
