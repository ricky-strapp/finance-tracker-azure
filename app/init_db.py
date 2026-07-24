import sqlite3
import os

# Build path relative to script location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 1. Raw file path string (for OS functions & print statements)
DB_PATH = os.path.join(BASE_DIR, "database", "finance_tracker.db")

# 2. Connection URI (for SQLite over SMB)
DB_URI = f"file:{DB_PATH}?nolock=1"

def get_connection():
    """Create and return a database connection with foreign keys enabled."""
    # Ensure the parent directory (database/) exists before trying to open the file
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DB_URI, uri=True, timeout=30.0)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # --- accounts ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            name                    TEXT NOT NULL,
            type                    TEXT NOT NULL CHECK(type IN (
                                        'current', 'savings', 'credit_card',
                                        'isa', 'investment', 'cash', 'other'
                                    )),
            currency                TEXT NOT NULL DEFAULT 'GBP',
            is_active               INTEGER NOT NULL DEFAULT 1,
            opening_balance_pence   INTEGER NOT NULL DEFAULT 0,
            opening_date            TEXT NOT NULL,
            created_at              TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # --- categories ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            parent_id   INTEGER REFERENCES categories(id),
            colour      TEXT,
            icon        TEXT,
            is_active   INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # --- payees ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payees (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            name                TEXT NOT NULL,
            default_category_id INTEGER REFERENCES categories(id),
            is_active           INTEGER NOT NULL DEFAULT 1,
            created_at          TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # --- transactions ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id          INTEGER NOT NULL REFERENCES accounts(id),
            date                TEXT NOT NULL,
            amount_pence        INTEGER NOT NULL,
            description         TEXT,
            category_id         INTEGER REFERENCES categories(id),
            payee_id            INTEGER REFERENCES payees(id),
            notes               TEXT,
            is_transfer         INTEGER NOT NULL DEFAULT 0,
            transfer_pair_id    INTEGER,
            is_void             INTEGER NOT NULL DEFAULT 0,
            created_at          TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # --- adjustments ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS adjustments (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            original_transaction_id     INTEGER NOT NULL REFERENCES transactions(id),
            correcting_transaction_id   INTEGER NOT NULL REFERENCES transactions(id),
            reason                      TEXT NOT NULL,
            created_at                  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # --- investment_valuations ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS investment_valuations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id      INTEGER NOT NULL REFERENCES accounts(id),
            valuation_date  TEXT NOT NULL,
            value_pence     INTEGER NOT NULL,
            notes           TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # --- budgets ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id     INTEGER NOT NULL REFERENCES categories(id),
            period          TEXT NOT NULL,
            amount_pence    INTEGER NOT NULL,
            start_date      TEXT NOT NULL,
            end_date        TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    #	---	settings ---
    cursor.execute("""
		CREATE TABLE IF	NOT	EXISTS	settings (
			key				TEXT	PRIMARY	KEY,
		    value			TEXT	NOT	NULL,
			updated_at	    TEXT	NOT	NULL	DEFAULT	(datetime('now'))
		)
	""")

    conn.commit()
    conn.close()
    print(f"Database initialised at: {DB_PATH}")

if __name__ == "__main__":
    init_db()
