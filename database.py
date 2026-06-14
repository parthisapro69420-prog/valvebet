import sqlite3
import os

DB_FILE = "vaultbet.db"

def get_db_connection():
    """Returns a connection to the SQLite database with row factory enabled."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    """Initializes database tables if they do not exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create Users Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL, -- Stored as Base64 encoded plaintext (toy project only)
            balance INTEGER DEFAULT 500,
            banned INTEGER DEFAULT 0,    -- 0 = Active, 1 = Banned
            total_won INTEGER DEFAULT 0  -- All-time gross winnings for leaderboard
        );
    """)
    
    # Create Loans Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            repay_amount INTEGER NOT NULL,
            created_at TEXT NOT NULL,     -- ISO-8601 string
            deadline TEXT NOT NULL,       -- ISO-8601 string (created_at + 5 mins)
            active INTEGER DEFAULT 1,     -- 1 = Active/Unpaid, 0 = Repaid
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
    """)
    
    # Create Game History Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            game_name TEXT NOT NULL,
            bet INTEGER NOT NULL,
            payout INTEGER NOT NULL,
            result_details TEXT NOT NULL,
            timestamp TEXT NOT NULL,      -- ISO-8601 string
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
    """)
    
    conn.commit()
    conn.close()
    print("Database tables initialized successfully.")

if __name__ == "__main__":
    init_db()
