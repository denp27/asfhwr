import sqlite3

def db_init():
    conn = sqlite3.connect("shop.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            name TEXT,
            price REAL,
            geo TEXT,
            is_warmed INTEGER DEFAULT 0,
            data TEXT,
            is_sold INTEGER DEFAULT 0,
            date_added TEXT,
            created_at REAL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance REAL DEFAULT 0.0,
            purchases_count INTEGER DEFAULT 0,
            total_spent REAL DEFAULT 0.0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            sales_count INTEGER,
            total_earned REAL
        )
    """)
    cursor.execute("SELECT COUNT(*) FROM stats")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO stats VALUES (0, 0.0)")
    conn.commit()
    conn.close()

def get_db_connection():
    return sqlite3.connect("shop.db")
