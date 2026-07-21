import sqlite3
import os
from datetime import datetime, date
import datetime as dt
from flask import Flask, g, request, jsonify, render_template

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 1. Raw file system path (used for os.path operations and getmtime)
DB_PATH = os.path.join(BASE_DIR, "database", "finance_tracker.db")

# 2. SQLite URI connection string (bypasses SMB locks on Azure Files)
DB_URI = f"file:{DB_PATH}?nolock=1"

def get_db():
    if 'db' not in g:
        # Pass uri=True so SQLite parses ?nolock=1
        g.db = sqlite3.connect(DB_URI, uri=True, timeout=30.0)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ---------------------------------------------------------------------------
# Schema migrations
# ---------------------------------------------------------------------------
# Each migration is a plain function that receives a cursor and makes exactly
# one logical change to the schema.  Migrations are numbered from 1 and run
# in order.  The current version is stored in the database itself so the
# system always knows what has and hasn't been applied — on any machine.
#
# HOW TO ADD A NEW MIGRATION:
#   1. Write a new function  migrate_vN(cursor)
#   2. Add it to MIGRATIONS below with the next integer key
#   That's it.  It will run exactly once on the next startup, on every machine.
# ---------------------------------------------------------------------------

def migrate_v1(cursor):
    """Add interest_rate column to accounts."""
    cursor.execute("ALTER TABLE accounts ADD COLUMN interest_rate REAL")

def migrate_v2(cursor):
    """Add display_order column to accounts and seed sensible initial values."""
    cursor.execute("ALTER TABLE accounts ADD COLUMN display_order INTEGER")
    cursor.execute("""
        UPDATE accounts SET display_order = (
            SELECT COUNT(*) FROM accounts a2
            WHERE a2.name < accounts.name AND a2.is_active = 1
        ) + 1 WHERE is_active = 1
    """)

def migrate_v3(cursor):
    """Add show_on_overview flag to accounts (default visible)."""
    cursor.execute(
        "ALTER TABLE accounts ADD COLUMN show_on_overview INTEGER NOT NULL DEFAULT 1"
    )

def migrate_v4(cursor):
    """Add is_void flag to investment_valuations."""
    cursor.execute(
        "ALTER TABLE investment_valuations ADD COLUMN is_void INTEGER NOT NULL DEFAULT 0"
    )

def migrate_v5(cursor):
    """Create the notes table."""
    cursor.execute("""
        CREATE TABLE notes (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            title         TEXT NOT NULL,
            body          TEXT NOT NULL DEFAULT '',
            display_order INTEGER,
            is_active     INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

def migrate_v6(cursor):
    """Create pension_accounts table."""
    cursor.execute("""
        CREATE TABLE pension_accounts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            subtype       TEXT NOT NULL,
            provider      TEXT,
            notes         TEXT,
            display_order INTEGER,
            is_active     INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

def migrate_v7(cursor):
    """Create pension_entries table."""
    cursor.execute("""
        CREATE TABLE pension_entries (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id   INTEGER NOT NULL REFERENCES pension_accounts(id),
            entry_date   TEXT NOT NULL,
            value_pence  INTEGER,
            annual_pence INTEGER,
            notes        TEXT,
            is_void      INTEGER NOT NULL DEFAULT 0,
            created_at   TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

def migrate_v8(cursor):
    """Add display_order to pension_accounts and seed initial values."""
    cursor.execute("ALTER TABLE pension_accounts ADD COLUMN display_order INTEGER")
    cursor.execute("""
        UPDATE pension_accounts SET display_order = (
            SELECT COUNT(*) FROM pension_accounts p2
            WHERE p2.id <= pension_accounts.id AND p2.is_active = 1
        ) WHERE is_active = 1
    """)

def migrate_v9(cursor):
    """Add void_reason audit column to transactions and investment_valuations."""
    cursor.execute("ALTER TABLE transactions ADD COLUMN void_reason TEXT")
    cursor.execute("ALTER TABLE investment_valuations ADD COLUMN void_reason TEXT")

def migrate_v10(cursor):
    """Create export_log table to record a history of data exports."""
    cursor.execute("""
        CREATE TABLE export_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            format     TEXT NOT NULL,
            row_count  INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)


# Registry — add new migrations here, incrementing the key each time.
MIGRATIONS = {
    1: migrate_v1,
    2: migrate_v2,
    3: migrate_v3,
    4: migrate_v4,
    5: migrate_v5,
    6: migrate_v6,
    7: migrate_v7,
    8: migrate_v8,
    9: migrate_v9,
    10: migrate_v10,
}

LATEST_VERSION = max(MIGRATIONS)


def run_migrations():
    conn = sqlite3.connect(DB_URI, uri=True, timeout=30.0)
    cursor = conn.cursor()

    # Create the version-tracking table if this is a brand-new database
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL
        )
    """)

    row = cursor.execute("SELECT version FROM schema_version").fetchone()

    if row is None:
        # Database exists but has never been versioned.
        # It was created by the old migration system, so we need to figure out
        # which migrations have already been applied rather than running them all.
        # We do this by inspecting the schema directly — exactly what the old
        # system did — and set the version to wherever we currently are.
        existing_accounts = [
            r[1] for r in cursor.execute("PRAGMA table_info(accounts)").fetchall()
        ]
        existing_val = [
            r[1] for r in cursor.execute("PRAGMA table_info(investment_valuations)").fetchall()
        ]
        existing_tx = [
            r[1] for r in cursor.execute("PRAGMA table_info(transactions)").fetchall()
        ]
        tables = [
            r[0] for r in cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        existing_pa = (
            [r[1] for r in cursor.execute("PRAGMA table_info(pension_accounts)").fetchall()]
            if "pension_accounts" in tables else []
        )

        # Work out the highest migration already applied
        current_version = 0
        if "interest_rate"    in existing_accounts: current_version = max(current_version, 1)
        if "display_order"    in existing_accounts: current_version = max(current_version, 2)
        if "show_on_overview" in existing_accounts: current_version = max(current_version, 3)
        if "is_void"          in existing_val:       current_version = max(current_version, 4)
        if "notes"            in tables:             current_version = max(current_version, 5)
        if "pension_accounts" in tables:             current_version = max(current_version, 6)
        if "pension_entries"  in tables:             current_version = max(current_version, 7)
        if "display_order"    in existing_pa:        current_version = max(current_version, 8)
        if "void_reason"      in existing_tx:        current_version = max(current_version, 9)
        if "export_log"       in tables:             current_version = max(current_version, 10)

        cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (current_version,))
        conn.commit()
        print(f"Schema versioning initialised at v{current_version}.")
    else:
        current_version = row[0]

    # Run any migrations newer than the current version, in order
    migrations_run = 0
    for version, migrate_fn in sorted(MIGRATIONS.items()):
        if version > current_version:
            print(f"Applying migration v{version}: {migrate_fn.__doc__}")
            migrate_fn(cursor)
            cursor.execute("UPDATE schema_version SET version = ?", (version,))
            conn.commit()
            migrations_run += 1

    if migrations_run == 0:
        print(f"Database schema up to date (v{current_version}).")
    else:
        print(f"Migrations complete. Schema now at v{current_version + migrations_run}.")

    # --- Indexes ---
    # These use IF NOT EXISTS so they are always safe to verify on startup.
    # They live outside the versioned migrations because CREATE INDEX IF NOT EXISTS
    # is genuinely idempotent — no need to track whether they exist.

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tx_account_date
        ON transactions(account_id, date)
        WHERE is_void = 0
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tx_date_transfer
        ON transactions(date, is_transfer)
        WHERE is_void = 0
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tx_category
        ON transactions(category_id)
        WHERE is_void = 0 AND is_transfer = 0
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_val_account_date
        ON investment_valuations(account_id, valuation_date)
        WHERE is_void = 0
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pension_entries_account
        ON pension_entries(account_id, entry_date)
        WHERE is_void = 0
    """)

    conn.commit()
    conn.close()


try:
    run_migrations()
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e):
        print("Database schema already up to date. Skipping migrations.")
    else:
        raise e


import bisect as _bisect


def build_balance_cache(db):
    # Load ALL accounts (active and inactive) so historical balance lookups
    # include deactivated accounts. A deactivated account still existed and
    # had a real balance on past dates — excluding it causes incorrect dips
    # in historical net worth charts.
    # The returned `accounts` list is filtered to active-only so callers that
    # use it for display purposes (account toggles, allocations, etc.) are unaffected.
    all_accounts = [dict(a) for a in db.execute(
        "SELECT * FROM accounts ORDER BY COALESCE(display_order, 9999), name"
    ).fetchall()]

    active_accounts = [a for a in all_accounts if a["is_active"] == 1]

    opening = {a["id"]: a["opening_balance_pence"] for a in all_accounts}
    inv_ids = {a["id"] for a in all_accounts if a["type"] in ("investment", "isa")}

    tx_rows = db.execute(
        """SELECT account_id, date, amount_pence
           FROM transactions
           WHERE is_void=0
           ORDER BY account_id ASC, date ASC, id ASC"""
    ).fetchall()

    tx_cumulative = {}
    for row in tx_rows:
        aid = row["account_id"]
        if aid not in tx_cumulative:
            tx_cumulative[aid] = []
        prev = tx_cumulative[aid][-1][1] if tx_cumulative[aid] else 0
        tx_cumulative[aid].append((row["date"], prev + row["amount_pence"]))

    tx_dates = {aid: [t[0] for t in txs] for aid, txs in tx_cumulative.items()}

    val_rows = db.execute(
        """SELECT account_id, valuation_date, value_pence
           FROM investment_valuations
           WHERE is_void=0
           ORDER BY account_id ASC, valuation_date ASC, id ASC"""
    ).fetchall()

    val_history = {}
    for row in val_rows:
        aid = row["account_id"]
        if aid not in val_history:
            val_history[aid] = []
        val_history[aid].append((row["valuation_date"], row["value_pence"]))

    val_dates = {aid: [v[0] for v in vals] for aid, vals in val_history.items()}

    def balance_at(account, as_of_str):
        aid = account["id"] if isinstance(account, dict) else account
        if aid in inv_ids:
            dates = val_dates.get(aid, [])
            if not dates:
                return opening.get(aid, 0)
            idx = _bisect.bisect_right(dates, as_of_str) - 1
            return val_history[aid][idx][1] if idx >= 0 else opening.get(aid, 0)
        else:
            dates = tx_dates.get(aid, [])
            op    = opening.get(aid, 0)
            if not dates:
                return op
            idx = _bisect.bisect_right(dates, as_of_str) - 1
            return op + (tx_cumulative[aid][idx][1] if idx >= 0 else 0)

    def current_balance(account):
        aid = account["id"] if isinstance(account, dict) else account
        if aid in inv_ids:
            vals = val_history.get(aid)
            return vals[-1][1] if vals else opening.get(aid, 0)
        else:
            txs = tx_cumulative.get(aid)
            return opening.get(aid, 0) + (txs[-1][1] if txs else 0)

    def net_worth_at(as_of_str):
        # Use all_accounts so deactivated accounts contribute to historical totals
        return sum(balance_at(a, as_of_str) for a in all_accounts)

    def current_net_worth():
        # Use active_accounts only — deactivated accounts have zero balance now
        return sum(current_balance(a) for a in active_accounts)

    def account_balance(account_id):
        acct = next((a for a in all_accounts if a["id"] == account_id), None)
        if not acct:
            return 0
        return current_balance(acct)

    return {
        # active_accounts: used by callers that display account lists/cards/allocations
        "accounts":          active_accounts,
        "balance_at":        balance_at,
        "current_balance":   current_balance,
        "net_worth_at":      net_worth_at,
        "current_net_worth": current_net_worth,
        "account_balance":   account_balance,
    }


def calc_net_worth_at(db, as_of_date_str):
    """Convenience wrapper — use build_balance_cache directly for multiple lookups."""
    cache = build_balance_cache(db)
    return cache["net_worth_at"](as_of_date_str)


def calc_current_net_worth(db):
    """Convenience wrapper — use build_balance_cache directly for multiple lookups."""
    cache = build_balance_cache(db)
    return cache["current_net_worth"]()


def get_account_balance(db, account_id):
    """Convenience wrapper — use build_balance_cache directly for multiple lookups."""
    cache = build_balance_cache(db)
    return cache["account_balance"](account_id)


# --- Shared inflation helper ---

def get_category_spend_for_period(db, date_from, date_to):
    """
    Returns a dict of {cat_id: {name, total_pence}} for all spending
    in the given date range, rolled up to top-level categories.
    Also includes an entry for uncategorised spend under key 0.
    """
    rows = db.execute(
        """SELECT
               COALESCE(pc.id,   c.id)   as cat_id,
               COALESCE(pc.name, c.name) as cat_name,
               COALESCE(SUM(ABS(t.amount_pence)), 0) as total_pence
           FROM transactions t
           JOIN categories c ON t.category_id = c.id
           LEFT JOIN categories pc ON c.parent_id = pc.id
           WHERE t.is_void = 0
             AND t.is_transfer = 0
             AND t.amount_pence < 0
             AND t.date >= ?
             AND t.date <= ?
           GROUP BY COALESCE(pc.id, c.id)""",
        (date_from, date_to)
    ).fetchall()
    result = {r["cat_id"]: {"name": r["cat_name"], "total": r["total_pence"]} for r in rows}

    uncat = db.execute(
        """SELECT COALESCE(SUM(ABS(amount_pence)), 0) as total
           FROM transactions
           WHERE is_void=0 AND is_transfer=0 AND amount_pence<0
             AND category_id IS NULL AND date >= ? AND date <= ?""",
        (date_from, date_to)
    ).fetchone()["total"]

    if uncat > 0:
        result[0] = {"name": "Uncategorised", "total": uncat}

    return result


# --- Page routes ---

@app.route("/")
def index():
    return render_template("overview_v2.html", active_page="overview")

@app.route("/transactions")
def transactions():
    return render_template("transactions.html", active_page="transactions")

@app.route("/transfers")
def transfers():
    return render_template("transfers.html", active_page="transfers")

@app.route("/valuations")
def valuations():
    return render_template("valuations.html", active_page="valuations")

@app.route("/pensions")
def pensions():
    return render_template("pensions.html", active_page="pensions")

@app.route("/notes")
def notes():
    return render_template("notes.html", active_page="notes")

@app.route("/accounts")
def accounts():
    return render_template("accounts.html", active_page="accounts")

@app.route("/categories")
def categories():
    return render_template("categories.html", active_page="categories")

@app.route("/payees")
def payees():
    return render_template("payees.html", active_page="payees")

@app.route("/export")
def export_page():
    return render_template("export.html", active_page="export")


# --- API: Export ---

@app.route("/api/export")
def export_data():
    """
    Export all transactions and transfers as CSV or JSON.
    Records the export in export_log.
    Query params:
      format : csv | json  (default: csv)
    """
    import csv, io, json as _json
    from flask import Response

    db      = get_db()
    fmt     = request.args.get("format", "csv").lower()
    if fmt not in ("csv", "json"):
        return jsonify({"error": "Invalid format. Use csv or json."}), 400

    # --- Fetch transactions (non-transfer, non-void) ---
    tx_rows = db.execute(
        """SELECT t.date, t.amount_pence, t.notes,
                  a.name  AS account,
                  c.name  AS category,
                  pc.name AS parent_category,
                  p.name  AS payee,
                  t.is_void,
                  t.void_reason,
                  t.created_at
           FROM transactions t
           JOIN accounts a      ON t.account_id  = a.id
           LEFT JOIN categories c  ON t.category_id = c.id
           LEFT JOIN categories pc ON c.parent_id    = pc.id
           LEFT JOIN payees p      ON t.payee_id     = p.id
           WHERE t.is_transfer = 0
           ORDER BY t.date ASC, t.id ASC"""
    ).fetchall()

    # --- Fetch transfers ---
    tr_rows = db.execute(
        """SELECT t_out.date,
                  t_out.amount_pence,
                  t_out.notes,
                  a_from.name AS from_account,
                  a_to.name   AS to_account,
                  t_out.is_void,
                  t_out.void_reason,
                  t_out.created_at
           FROM transactions t_out
           JOIN accounts a_from ON t_out.account_id = a_from.id
           JOIN transactions t_in
               ON t_in.transfer_pair_id = t_out.transfer_pair_id
               AND t_in.id != t_out.id
           JOIN accounts a_to ON t_in.account_id = a_to.id
           WHERE t_out.is_transfer = 1
             AND t_out.amount_pence < 0
           ORDER BY t_out.date ASC, t_out.id ASC"""
    ).fetchall()

    # Build unified row list
    rows = []
    for r in tx_rows:
        cat = r["category"] or ""
        if r["parent_category"] and r["category"]:
            cat = f"{r['parent_category']} > {r['category']}"
        rows.append({
            "type":         "transaction",
            "date":         r["date"],
            "amount_gbp":   round(r["amount_pence"] / 100, 2),
            "account":      r["account"],
            "payee":        r["payee"] or "",
            "category":     cat,
            "notes":        r["notes"] or "",
            "is_void":      "yes" if r["is_void"] else "no",
            "void_reason":  r["void_reason"] or "",
            "created_at":   r["created_at"],
        })
    for r in tr_rows:
        rows.append({
            "type":         "transfer",
            "date":         r["date"],
            "amount_gbp":   round(abs(r["amount_pence"]) / 100, 2),
            "account":      r["from_account"],
            "payee":        f"→ {r['to_account']}",
            "category":     "",
            "notes":        r["notes"] or "",
            "is_void":      "yes" if r["is_void"] else "no",
            "void_reason":  r["void_reason"] or "",
            "created_at":   r["created_at"],
        })

    # Sort combined list by date then created_at
    rows.sort(key=lambda x: (x["date"], x["created_at"]))
    row_count = len(rows)

    # Log the export
    db.execute(
        "INSERT INTO export_log (format, row_count) VALUES (?, ?)",
        (fmt, row_count)
    )
    db.commit()

    if fmt == "json":
        output   = _json.dumps(rows, indent=2)
        mimetype = "application/json"
        filename = f"finance_export_{date.today().strftime('%Y%m%d')}.json"
        return Response(
            output,
            mimetype=mimetype,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    else:
        # CSV
        si      = io.StringIO()
        writer  = csv.DictWriter(si, fieldnames=rows[0].keys() if rows else [
            "type","date","amount_gbp","account","payee",
            "category","notes","is_void","void_reason","created_at"
        ])
        writer.writeheader()
        writer.writerows(rows)
        filename = f"finance_export_{date.today().strftime('%Y%m%d')}.csv"
        return Response(
            si.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )


@app.route("/api/export/history")
def export_history():
    """Returns the log of previous exports, most recent first."""
    db   = get_db()
    rows = db.execute(
        "SELECT id, format, row_count, created_at FROM export_log ORDER BY id DESC LIMIT 50"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


# --- API: Settings ---

@app.route("/api/settings/<key>", methods=["GET"])
def get_setting(key):
    db  = get_db()
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if not row:
        return jsonify({"error": "Setting not found."}), 404
    return jsonify({"key": key, "value": row["value"]})


@app.route("/api/settings/<key>", methods=["POST"])
def update_setting(key):
    data  = request.get_json()
    value = data.get("value", "").strip()
    if not value:
        return jsonify({"error": "Value is required."}), 400
    db = get_db()
    db.execute(
        """INSERT INTO settings (key, value, updated_at)
           VALUES (?, ?, datetime('now'))
           ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
        (key, value)
    )
    db.commit()
    return jsonify({"success": True})


@app.route("/reports/net-worth")
def report_net_worth():
    return render_template("report_net_worth.html", active_page="report-net-worth")

@app.route("/reports/pension-value")
def report_pension_value():
    return render_template("report_pension_value.html", active_page="report-pension-value")

@app.route("/reports/allocations")
def report_allocations():
    return render_template("report_allocations.html", active_page="report-allocations")

@app.route("/reports/income-expenditure")
def report_income_expenditure():
    return render_template("report_income_expenditure.html", active_page="report-income-expenditure")

@app.route("/reports/breakdown")
def report_breakdown():
    return render_template("report_breakdown.html", active_page="report-breakdown")

@app.route("/reports/category-trends")
def report_category_trends():
    return render_template("report_category_trends.html", active_page="report-category-trends")

@app.route("/reports/inflation")
def report_inflation():
    return render_template("report_inflation.html", active_page="report-inflation")

@app.route("/reports/runway")
def report_runway():
    return render_template("report_runway.html", active_page="report-runway")

@app.route("/reports/interest")
def report_interest():
    return render_template("report_interest.html", active_page="report-interest")

@app.route("/reports/investment-projections")
def report_investment_projections():
    return render_template("report_investment_projections.html", active_page="report-investment-projections")


# --- API: DB info ---

@app.route("/api/db-info")
def db_info():
    try:
        mtime = os.path.getmtime(DB_PATH)
        formatted = datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")
        return jsonify({"last_modified": formatted})
    except Exception:
        return jsonify({"last_modified": "unavailable"})


@app.route("/api/health")
def health_check():
    """
    Verifies the database is reachable and writable.
    Does a real write (INSERT + DELETE in a transaction) so that a read-only
    file — e.g. locked by OneDrive sync — is caught and reported correctly.
    Returns {"status": "ok"} or {"status": "error", "detail": "..."}.
    """
    try:
        conn = sqlite3.connect(DB_URI, uri=True, timeout=30.0)
        conn.execute("BEGIN")
        conn.execute("CREATE TABLE IF NOT EXISTS _health_check (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO _health_check (id) VALUES (1)")
        conn.execute("DELETE FROM _health_check")
        conn.execute("DROP TABLE _health_check")
        conn.execute("COMMIT")
        conn.close()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 500


# --- API: Accounts ---

@app.route("/api/accounts", methods=["GET"])
def get_accounts():
    db = get_db()
    accounts = db.execute(
        """SELECT * FROM accounts WHERE is_active = 1
           ORDER BY COALESCE(display_order, 9999), name"""
    ).fetchall()

    today = date.today()
    first_of_this_month = today.replace(day=1)
    last_of_prev_month  = first_of_this_month - dt.timedelta(days=1)
    last_of_prev_month_str = last_of_prev_month.strftime("%Y-%m-%d")

    result = []
    for account in accounts:
        a = dict(account)
        if a["type"] in ("investment", "isa"):
            latest_val = db.execute(
                """SELECT value_pence FROM investment_valuations
                   WHERE account_id = ? AND is_void = 0
                   ORDER BY valuation_date DESC, id DESC LIMIT 1""",
                (a["id"],)
            ).fetchone()
            a["current_balance_pence"] = latest_val["value_pence"] if latest_val else a["opening_balance_pence"]

            # Prior month balance — last valuation on or before end of last month
            prior_val = db.execute(
                """SELECT value_pence FROM investment_valuations
                   WHERE account_id = ? AND is_void = 0 AND valuation_date <= ?
                   ORDER BY valuation_date DESC, id DESC LIMIT 1""",
                (a["id"], last_of_prev_month_str)
            ).fetchone()
            prior_balance = prior_val["value_pence"] if prior_val else a["opening_balance_pence"]
        else:
            tx_sum = db.execute(
                """SELECT COALESCE(SUM(amount_pence), 0) as total
                   FROM transactions WHERE account_id = ? AND is_void = 0""",
                (a["id"],)
            ).fetchone()
            a["current_balance_pence"] = a["opening_balance_pence"] + tx_sum["total"]

            # Prior month balance — all transactions up to end of last month
            prior_tx = db.execute(
                """SELECT COALESCE(SUM(amount_pence), 0) as total
                   FROM transactions WHERE account_id = ? AND is_void = 0 AND date <= ?""",
                (a["id"], last_of_prev_month_str)
            ).fetchone()
            prior_balance = a["opening_balance_pence"] + prior_tx["total"]

        a["month_change_pence"] = a["current_balance_pence"] - prior_balance
        result.append(a)
    return jsonify(result)


@app.route("/api/accounts", methods=["POST"])
def add_account():
    data = request.get_json()
    name = data.get("name", "").strip()
    account_type = data.get("type", "").strip()
    opening_date = data.get("opening_date", "").strip()

    try:
        opening_balance_pence = round(float(data.get("opening_balance", 0)) * 100)
    except (ValueError, TypeError):
        opening_balance_pence = 0

    interest_rate = None
    if account_type in ("savings", "isa", "investment"):
        try:
            raw = data.get("interest_rate", "")
            if raw != "" and raw is not None:
                interest_rate = float(raw)
        except (ValueError, TypeError):
            interest_rate = None

    if not name or not account_type or not opening_date:
        return jsonify({"error": "Name, type and opening date are required."}), 400

    db = get_db()
    max_order = db.execute(
        "SELECT COALESCE(MAX(display_order), 0) FROM accounts WHERE is_active = 1"
    ).fetchone()[0]
    db.execute(
        """INSERT INTO accounts (name, type, opening_balance_pence, opening_date, interest_rate, display_order)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (name, account_type, opening_balance_pence, opening_date, interest_rate, max_order + 1)
    )
    db.commit()
    return jsonify({"success": True}), 201


@app.route("/api/accounts/<int:account_id>", methods=["PATCH"])
def update_account(account_id):
    data = request.get_json()
    db = get_db()
    account = db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not account:
        return jsonify({"error": "Account not found."}), 404

    name         = data.get("name", account["name"]).strip()
    account_type = data.get("type", account["type"]).strip()
    opening_date = data.get("opening_date", account["opening_date"]).strip()

    try:
        opening_balance_pence = round(float(data.get("opening_balance", account["opening_balance_pence"] / 100)) * 100)
    except (ValueError, TypeError):
        opening_balance_pence = account["opening_balance_pence"]

    interest_rate = account["interest_rate"]
    if account_type in ("savings", "isa", "investment"):
        raw = data.get("interest_rate", "")
        if raw == "" or raw is None:
            interest_rate = None
        else:
            try:
                interest_rate = float(raw)
            except (ValueError, TypeError):
                pass

    show_on_overview = account["show_on_overview"] if account["show_on_overview"] is not None else 1
    if "show_on_overview" in data:
        show_on_overview = 1 if data["show_on_overview"] else 0            

    if not name or not account_type or not opening_date:
        return jsonify({"error": "Name, type and opening date are required."}), 400

    db.execute(
    """UPDATE accounts SET name=?, type=?, opening_balance_pence=?, opening_date=?, interest_rate=?, show_on_overview=?
       WHERE id=?""",
    (name, account_type, opening_balance_pence, opening_date, interest_rate, show_on_overview, account_id)
    )
    db.commit()
    return jsonify({"success": True})


@app.route("/api/accounts/<int:account_id>/deactivate", methods=["POST"])
def deactivate_account(account_id):
    db = get_db()
    db.execute("UPDATE accounts SET is_active = 0 WHERE id = ?", (account_id,))
    db.commit()
    return jsonify({"success": True})


@app.route("/api/accounts/<int:account_id>/move", methods=["POST"])
def move_account(account_id):
    data = request.get_json()
    direction = data.get("direction")
    db = get_db()
    accounts = db.execute(
        """SELECT id, display_order FROM accounts WHERE is_active = 1
           ORDER BY COALESCE(display_order, 9999), name"""
    ).fetchall()
    ids = [a["id"] for a in accounts]
    if account_id not in ids:
        return jsonify({"error": "Account not found."}), 404
    idx = ids.index(account_id)
    if direction == "up" and idx == 0:
        return jsonify({"success": True})
    if direction == "down" and idx == len(ids) - 1:
        return jsonify({"success": True})
    swap_idx = idx - 1 if direction == "up" else idx + 1
    id_a, id_b = ids[idx], ids[swap_idx]
    for i, aid in enumerate(ids):
        db.execute("UPDATE accounts SET display_order = ? WHERE id = ?", (i + 1, aid))
    db.execute("UPDATE accounts SET display_order = ? WHERE id = ?", (swap_idx + 1, id_a))
    db.execute("UPDATE accounts SET display_order = ? WHERE id = ?", (idx + 1, id_b))
    db.commit()
    return jsonify({"success": True})


# --- API: Categories ---

@app.route("/api/categories", methods=["GET"])
def get_categories():
    db = get_db()
    rows = db.execute(
        """SELECT id, name, parent_id, colour FROM categories
           WHERE is_active = 1
           ORDER BY COALESCE(parent_id, id), parent_id IS NOT NULL, name"""
    ).fetchall()
    return jsonify([dict(row) for row in rows])


@app.route("/api/categories", methods=["POST"])
def add_category():
    data = request.get_json()
    name = data.get("name", "").strip()
    parent_id = data.get("parent_id") or None
    if not name:
        return jsonify({"error": "Name is required."}), 400
    db = get_db()
    colour = None
    if parent_id:
        parent = db.execute("SELECT colour FROM categories WHERE id = ?", (parent_id,)).fetchone()
        if parent:
            colour = parent["colour"]
    db.execute("INSERT INTO categories (name, parent_id, colour) VALUES (?, ?, ?)", (name, parent_id, colour))
    db.commit()
    return jsonify({"success": True}), 201


@app.route("/api/categories/<int:category_id>", methods=["PATCH"])
def update_category(category_id):
    data = request.get_json()
    db = get_db()
    category = db.execute("SELECT * FROM categories WHERE id = ?", (category_id,)).fetchone()
    if not category:
        return jsonify({"error": "Category not found."}), 404
    name = data.get("name", category["name"]).strip()
    parent_id = data.get("parent_id") if "parent_id" in data else category["parent_id"]
    if parent_id == "" or parent_id == "null":
        parent_id = None
    if not name:
        return jsonify({"error": "Name is required."}), 400
    if parent_id and int(parent_id) == category_id:
        return jsonify({"error": "A category cannot be its own parent."}), 400
    colour = category["colour"]
    if parent_id and parent_id != category["parent_id"]:
        parent = db.execute("SELECT colour FROM categories WHERE id = ?", (parent_id,)).fetchone()
        if parent:
            colour = parent["colour"]
    db.execute("UPDATE categories SET name=?, parent_id=?, colour=? WHERE id=?",
               (name, parent_id, colour, category_id))
    db.commit()
    return jsonify({"success": True})


@app.route("/api/categories/<int:category_id>/deactivate", methods=["POST"])
def deactivate_category(category_id):
    db = get_db()
    db.execute("UPDATE categories SET is_active = 0 WHERE id = ? OR parent_id = ?",
               (category_id, category_id))
    db.commit()
    return jsonify({"success": True})


# --- API: Payees ---

@app.route("/api/payees", methods=["GET"])
def get_payees():
    db = get_db()
    rows = db.execute(
        """SELECT p.id, p.name, p.default_category_id,
                  c.name as default_category_name,
                  pc.name as default_parent_category_name
           FROM payees p
           LEFT JOIN categories c ON p.default_category_id = c.id
           LEFT JOIN categories pc ON c.parent_id = pc.id
           WHERE p.is_active = 1
           ORDER BY p.name"""
    ).fetchall()
    return jsonify([dict(row) for row in rows])


@app.route("/api/payees", methods=["POST"])
def add_payee():
    data = request.get_json()
    name = data.get("name", "").strip()
    default_category_id = data.get("default_category_id") or None
    if not name:
        return jsonify({"error": "Payee name is required."}), 400
    db = get_db()
    db.execute("INSERT INTO payees (name, default_category_id) VALUES (?, ?)", (name, default_category_id))
    db.commit()
    return jsonify({"success": True}), 201


@app.route("/api/payees/<int:payee_id>", methods=["PATCH"])
def update_payee(payee_id):
    data = request.get_json()
    db = get_db()
    payee = db.execute("SELECT * FROM payees WHERE id = ?", (payee_id,)).fetchone()
    if not payee:
        return jsonify({"error": "Payee not found."}), 404
    name = data.get("name", payee["name"]).strip()
    default_category_id = data.get("default_category_id") or None
    if not name:
        return jsonify({"error": "Payee name is required."}), 400
    db.execute("UPDATE payees SET name=?, default_category_id=? WHERE id=?",
               (name, default_category_id, payee_id))
    db.commit()
    return jsonify({"success": True})


@app.route("/api/payees/<int:payee_id>/deactivate", methods=["POST"])
def deactivate_payee(payee_id):
    db = get_db()
    db.execute("UPDATE payees SET is_active = 0 WHERE id = ?", (payee_id,))
    db.commit()
    return jsonify({"success": True})


# --- API: Transactions ---

@app.route("/api/transactions", methods=["GET"])
def get_transactions():
    db = get_db()
    try:
        limit  = int(request.args.get("limit", 100))
        offset = int(request.args.get("offset", 0))
    except (ValueError, TypeError):
        limit, offset = 100, 0

    include_voided = request.args.get("include_voided", "0") == "1"
    if limit <= 0:
        limit = None

    # Note: We removed the 't.' alias here to match the CTE output
    void_filter = "" if include_voided else "AND is_void = 0"

    query = f"""
    WITH TransactionHistory AS (
    SELECT 
        t.*,
        a.name AS account_name,
        c.name AS category_name,
        p.name AS payee_name,
        a.opening_balance_pence + SUM(
            CASE 
                WHEN t.is_void = 0 THEN t.amount_pence 
                ELSE 0 
            END
        ) OVER (
            PARTITION BY t.account_id
            ORDER BY t.date ASC, t.id ASC
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_balance
    FROM transactions t
    JOIN accounts a ON t.account_id = a.id
    LEFT JOIN categories c ON t.category_id = c.id
    LEFT JOIN payees p ON t.payee_id = p.id
    )
    SELECT 
        id, date, amount_pence, notes, created_at, account_id, 
        category_id, payee_id, is_void, account_name, category_name, 
        payee_name,
            CASE WHEN is_void = 0 THEN running_balance ELSE NULL END AS balance_after_pence
    FROM TransactionHistory
    WHERE 1=1 {void_filter}
    AND is_transfer = 0  -- <--- THIS LINE HIDES TRANSFERS FROM THE LIST
    ORDER BY date DESC, id DESC
    """

    if limit:
        query += f" LIMIT {limit} OFFSET {offset}"

    rows = db.execute(query).fetchall()
    return jsonify([dict(row) for row in rows])


@app.route("/api/transactions/count", methods=["GET"])
def count_transactions():
    """Returns the total number of non-transfer transactions matching the
    current void filter. Used by the frontend before a Load All to warn
    the user if the result set is large."""
    db = get_db()
    include_voided = request.args.get("include_voided", "0") == "1"
    void_filter    = "" if include_voided else "AND is_void = 0"
    row = db.execute(
        f"SELECT COUNT(*) as n FROM transactions WHERE is_transfer = 0 {void_filter}"
    ).fetchone()
    return jsonify({"count": row["n"]})


@app.route("/api/transactions", methods=["POST"])
def add_transaction():
    data = request.get_json()
    account_id  = data.get("account_id")
    date        = data.get("date", "").strip()
    notes       = data.get("notes", "").strip()
    direction   = data.get("direction")
    category_id = data.get("category_id") or None
    payee_id    = data.get("payee_id") or None

    try:
        amount_pence = round(float(data.get("amount", 0)) * 100)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid amount."}), 400

    if amount_pence <= 0:
        return jsonify({"error": "Amount must be greater than zero."}), 400
    if direction == "out":
        amount_pence = -amount_pence
    if not account_id or not date:
        return jsonify({"error": "Account and date are required."}), 400

    db = get_db()
    db.execute(
        """INSERT INTO transactions (account_id, date, amount_pence, notes, category_id, payee_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (account_id, date, amount_pence, notes or None, category_id, payee_id)
    )
    db.commit()
    return jsonify({"success": True}), 201


@app.route("/api/transactions/<int:transaction_id>/void", methods=["POST"])
def void_transaction(transaction_id):
    data = request.get_json(silent=True) or {}
    void_reason = (data.get("void_reason") or "").strip() or None
    db = get_db()
    tx = db.execute("SELECT id FROM transactions WHERE id = ? AND is_void = 0", (transaction_id,)).fetchone()
    if not tx:
        return jsonify({"error": "Transaction not found or already void."}), 404
    db.execute(
        "UPDATE transactions SET is_void = 1, void_reason = ?, updated_at = datetime('now') WHERE id = ?",
        (void_reason, transaction_id)
    )
    db.commit()
    return jsonify({"success": True})


@app.route("/api/transactions/<int:transaction_id>/unvoid", methods=["POST"])
def unvoid_transaction(transaction_id):
    db = get_db()
    tx = db.execute("SELECT id, is_void FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    if not tx:
        return jsonify({"error": "Transaction not found."}), 404
    if not tx["is_void"]:
        return jsonify({"error": "Transaction is not voided."}), 400

    # Check if this transaction is part of a correction chain
    # i.e. it appears as an original_transaction_id in the adjustments table
    is_corrected = db.execute(
        "SELECT id FROM adjustments WHERE original_transaction_id = ?", (transaction_id,)
    ).fetchone()
    if is_corrected:
        return jsonify({
            "error": "This transaction was voided as part of a correction and cannot be un-voided. "
                     "To restore it, void the correcting transaction instead."
        }), 400

    db.execute("UPDATE transactions SET is_void = 0, updated_at = datetime('now') WHERE id = ?", (transaction_id,))
    db.commit()
    return jsonify({"success": True})


@app.route("/api/transactions/<int:transaction_id>/correct", methods=["POST"])
def correct_transaction(transaction_id):
    data = request.get_json()
    db = get_db()
    original = db.execute(
        "SELECT * FROM transactions WHERE id = ? AND is_void = 0", (transaction_id,)
    ).fetchone()
    if not original:
        return jsonify({"error": "Transaction not found or already void."}), 404

    account_id  = data.get("account_id", original["account_id"])
    date        = data.get("date", original["date"]).strip()
    notes       = data.get("notes", original["notes"] or "").strip()
    category_id = data.get("category_id") or None
    payee_id    = data.get("payee_id") or None
    direction   = data.get("direction")

    try:
        amount_pence = round(float(data.get("amount", 0)) * 100)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid amount."}), 400

    if amount_pence <= 0:
        return jsonify({"error": "Amount must be greater than zero."}), 400
    if direction == "out":
        amount_pence = -amount_pence

    db.execute("UPDATE transactions SET is_void = 1, updated_at = datetime('now') WHERE id = ?", (transaction_id,))
    cursor = db.execute(
        """INSERT INTO transactions (account_id, date, amount_pence, notes, category_id, payee_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (account_id, date, amount_pence, notes or None, category_id, payee_id)
    )
    new_id = cursor.lastrowid
    db.execute(
        """INSERT INTO adjustments (original_transaction_id, correcting_transaction_id, reason)
           VALUES (?, ?, ?)""",
        (transaction_id, new_id, "Corrected via UI")
    )
    db.commit()
    return jsonify({"success": True, "new_id": new_id}), 201


# --- API: Transfers ---

@app.route("/api/transfers", methods=["GET"])
def get_transfers():
    db = get_db()
    rows = db.execute(
        """SELECT t_out.id, t_out.date, t_out.amount_pence, t_out.notes,
                  t_out.created_at,
                  a_from.name as from_account,
                  a_to.name as to_account
           FROM transactions t_out
           JOIN accounts a_from ON t_out.account_id = a_from.id
           JOIN transactions t_in
               ON t_in.transfer_pair_id = t_out.transfer_pair_id
               AND t_in.id != t_out.id
           JOIN accounts a_to ON t_in.account_id = a_to.id
           WHERE t_out.is_void = 0
             AND t_out.is_transfer = 1
             AND t_out.amount_pence < 0
           ORDER BY t_out.date DESC, t_out.id DESC
           LIMIT 50"""
    ).fetchall()
    return jsonify([dict(row) for row in rows])


@app.route("/api/transfers", methods=["POST"])
def add_transfer():
    data = request.get_json()
    from_account_id = data.get("from_account_id")
    to_account_id   = data.get("to_account_id")
    date            = data.get("date", "").strip()
    notes           = data.get("notes", "").strip()

    try:
        amount_pence = round(float(data.get("amount", 0)) * 100)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid amount."}), 400

    if amount_pence <= 0:
        return jsonify({"error": "Amount must be greater than zero."}), 400
    if not from_account_id or not to_account_id or not date:
        return jsonify({"error": "From account, to account and date are required."}), 400
    if str(from_account_id) == str(to_account_id):
        return jsonify({"error": "From and To accounts must be different."}), 400

    db = get_db()
    cursor = db.execute(
        """INSERT INTO transactions (account_id, date, amount_pence, description, notes, is_transfer)
           VALUES (?, ?, ?, ?, ?, 1)""",
        (from_account_id, date, -amount_pence, "Transfer out", notes or None)
    )
    out_id = cursor.lastrowid
    cursor = db.execute(
        """INSERT INTO transactions (account_id, date, amount_pence, description, notes, is_transfer)
           VALUES (?, ?, ?, ?, ?, 1)""",
        (to_account_id, date, amount_pence, "Transfer in", notes or None)
    )
    in_id = cursor.lastrowid
    db.execute("UPDATE transactions SET transfer_pair_id = ? WHERE id IN (?, ?)", (out_id, out_id, in_id))
    db.commit()
    return jsonify({"success": True}), 201


@app.route("/api/transfers/<int:transfer_id>/void", methods=["POST"])
def void_transfer(transfer_id):
    data = request.get_json(silent=True) or {}
    void_reason = (data.get("void_reason") or "").strip() or None
    db = get_db()
    out_tx = db.execute(
        """SELECT id, transfer_pair_id FROM transactions
           WHERE id = ? AND is_transfer = 1 AND is_void = 0""",
        (transfer_id,)
    ).fetchone()
    if not out_tx:
        return jsonify({"error": "Transfer not found or already void."}), 404
    db.execute(
        """UPDATE transactions SET is_void = 1, void_reason = ?, updated_at = datetime('now')
           WHERE transfer_pair_id = ? AND is_transfer = 1""",
        (void_reason, out_tx["transfer_pair_id"],)
    )
    db.commit()
    return jsonify({"success": True})


# --- API: Valuations ---

@app.route("/api/valuations", methods=["GET"])
def get_valuations():
    db = get_db()
    rows = db.execute(
        """SELECT iv.id, iv.valuation_date, iv.value_pence, iv.notes,
                  iv.created_at,
                  a.id as account_id, a.name as account_name
           FROM investment_valuations iv
           JOIN accounts a ON iv.account_id = a.id
           WHERE iv.is_void = 0
           ORDER BY iv.valuation_date DESC, iv.id DESC
           LIMIT 100"""
    ).fetchall()
    return jsonify([dict(row) for row in rows])


@app.route("/api/valuations/latest", methods=["GET"])
def get_latest_valuations():
    db = get_db()
    rows = db.execute(
        """SELECT iv.value_pence, iv.valuation_date,
                  a.id as account_id, a.name as account_name
           FROM investment_valuations iv
           JOIN accounts a ON iv.account_id = a.id
           WHERE iv.is_void = 0
             AND iv.id = (
               SELECT id FROM investment_valuations iv2
               WHERE iv2.account_id = iv.account_id AND iv2.is_void = 0
               ORDER BY iv2.valuation_date DESC, iv2.id DESC LIMIT 1
           )"""
    ).fetchall()
    return jsonify([dict(row) for row in rows])


@app.route("/api/valuations", methods=["POST"])
def add_valuation():
    data = request.get_json()
    account_id     = data.get("account_id")
    valuation_date = data.get("valuation_date", "").strip()
    notes          = data.get("notes", "").strip()

    try:
        value_pence = round(float(data.get("value", 0)) * 100)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid value."}), 400

    if value_pence <= 0:
        return jsonify({"error": "Value must be greater than zero."}), 400
    if not account_id or not valuation_date:
        return jsonify({"error": "Account and date are required."}), 400

    db = get_db()
    account = db.execute("SELECT type FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not account or account["type"] not in ("investment", "isa"):
        return jsonify({"error": "Valuations can only be added to investment or ISA accounts."}), 400

    db.execute(
        "INSERT INTO investment_valuations (account_id, valuation_date, value_pence, notes) VALUES (?, ?, ?, ?)",
        (account_id, valuation_date, value_pence, notes or None)
    )
    db.commit()
    return jsonify({"success": True}), 201


@app.route("/api/valuations/<int:valuation_id>/void", methods=["POST"])
def void_valuation(valuation_id):
    data = request.get_json(silent=True) or {}
    void_reason = (data.get("void_reason") or "").strip() or None
    db = get_db()
    val = db.execute(
        "SELECT id FROM investment_valuations WHERE id = ? AND is_void = 0", (valuation_id,)
    ).fetchone()
    if not val:
        return jsonify({"error": "Valuation not found or already void."}), 404
    db.execute(
        "UPDATE investment_valuations SET is_void = 1, void_reason = ? WHERE id = ?",
        (void_reason, valuation_id)
    )
    db.commit()
    return jsonify({"success": True})


# --- API: Notes ---

@app.route("/api/notes", methods=["GET"])
def get_notes():
    db = get_db()
    rows = db.execute(
        """SELECT id, title, body, display_order, created_at, updated_at
           FROM notes WHERE is_active = 1
           ORDER BY COALESCE(display_order, 9999), id DESC"""
    ).fetchall()
    return jsonify([dict(row) for row in rows])


@app.route("/api/notes", methods=["POST"])
def add_note():
    data = request.get_json()
    title = data.get("title", "").strip()
    body  = data.get("body", "").strip()
    if not title:
        return jsonify({"error": "Title is required."}), 400
    db = get_db()
    max_order = db.execute(
        "SELECT COALESCE(MAX(display_order), 0) FROM notes WHERE is_active = 1"
    ).fetchone()[0]
    db.execute(
        "INSERT INTO notes (title, body, display_order) VALUES (?, ?, ?)",
        (title, body, max_order + 1)
    )
    db.commit()
    return jsonify({"success": True}), 201


@app.route("/api/notes/<int:note_id>", methods=["PATCH"])
def update_note(note_id):
    data = request.get_json()
    db = get_db()
    note = db.execute("SELECT * FROM notes WHERE id = ? AND is_active = 1", (note_id,)).fetchone()
    if not note:
        return jsonify({"error": "Note not found."}), 404
    title = data.get("title", note["title"]).strip()
    body  = data.get("body", note["body"]).strip()
    if not title:
        return jsonify({"error": "Title is required."}), 400
    db.execute(
        "UPDATE notes SET title=?, body=?, updated_at=datetime('now') WHERE id=?",
        (title, body, note_id)
    )
    db.commit()
    return jsonify({"success": True})


@app.route("/api/notes/<int:note_id>/archive", methods=["POST"])
def archive_note(note_id):
    db = get_db()
    db.execute("UPDATE notes SET is_active = 0 WHERE id = ?", (note_id,))
    db.commit()
    return jsonify({"success": True})


@app.route("/api/notes/<int:note_id>/move", methods=["POST"])
def move_note(note_id):
    data = request.get_json()
    direction = data.get("direction")
    db = get_db()
    notes = db.execute(
        "SELECT id FROM notes WHERE is_active = 1 ORDER BY COALESCE(display_order, 9999), id DESC"
    ).fetchall()
    ids = [n["id"] for n in notes]
    if note_id not in ids:
        return jsonify({"error": "Note not found."}), 404
    idx = ids.index(note_id)
    if direction == "up" and idx == 0:
        return jsonify({"success": True})
    if direction == "down" and idx == len(ids) - 1:
        return jsonify({"success": True})
    swap_idx = idx - 1 if direction == "up" else idx + 1
    id_a, id_b = ids[idx], ids[swap_idx]
    for i, nid in enumerate(ids):
        db.execute("UPDATE notes SET display_order = ? WHERE id = ?", (i + 1, nid))
    db.execute("UPDATE notes SET display_order = ? WHERE id = ?", (swap_idx + 1, id_a))
    db.execute("UPDATE notes SET display_order = ? WHERE id = ?", (idx + 1, id_b))
    db.commit()
    return jsonify({"success": True})


# --- API: Recent activity ---

@app.route("/api/recent-activity")
def recent_activity():
    db = get_db()

    # Regular (non-transfer) transactions
    tx_rows = db.execute(
        """SELECT t.created_at, t.date, t.amount_pence, t.notes,
                  a.name as account_name,
                  p.name as payee_name,
                  c.name as category_name,
                  pc.name as parent_category_name
           FROM transactions t
           JOIN accounts a ON t.account_id = a.id
           LEFT JOIN payees p ON t.payee_id = p.id
           LEFT JOIN categories c ON t.category_id = c.id
           LEFT JOIN categories pc ON c.parent_id = pc.id
           WHERE t.is_void = 0 AND t.is_transfer = 0
           ORDER BY t.created_at DESC, t.id DESC
           LIMIT 100"""
    ).fetchall()

    # Transfers — one row per pair, using the outgoing leg to get both account names
    transfer_rows = db.execute(
        """SELECT t_out.created_at, t_out.date, t_out.amount_pence, t_out.notes,
                  a_from.name as from_account,
                  a_to.name as to_account
           FROM transactions t_out
           JOIN accounts a_from ON t_out.account_id = a_from.id
           JOIN transactions t_in
               ON t_in.transfer_pair_id = t_out.transfer_pair_id
               AND t_in.id != t_out.id
           JOIN accounts a_to ON t_in.account_id = a_to.id
           WHERE t_out.is_void = 0
             AND t_out.is_transfer = 1
             AND t_out.amount_pence < 0
           ORDER BY t_out.created_at DESC, t_out.id DESC
           LIMIT 50"""
    ).fetchall()

    # Valuations — in chronological order per account to compute diffs
    val_all = db.execute(
        """SELECT iv.id, iv.created_at, iv.valuation_date as date,
                  iv.value_pence, iv.notes,
                  a.id as account_id, a.name as account_name
           FROM investment_valuations iv
           JOIN accounts a ON iv.account_id = a.id
           WHERE iv.is_void = 0
           ORDER BY iv.account_id ASC, iv.valuation_date ASC, iv.id ASC"""
    ).fetchall()

    combined = []

    for row in tx_rows:
        r = dict(row)
        category_str = None
        if r.get("parent_category_name") and r.get("category_name"):
            category_str = f"{r['parent_category_name']} · {r['category_name']}"
        elif r.get("category_name"):
            category_str = r["category_name"]
        combined.append({
            "created_at":   r["created_at"],
            "date":         r["date"],
            "type":         "transaction",
            "amount_pence": r["amount_pence"],
            "account_name": r["account_name"],
            "payee_name":   r.get("payee_name") or "",
            "category_str": category_str,
            "notes":        r.get("notes") or "",
        })

    for row in transfer_rows:
        r = dict(row)
        combined.append({
            "created_at":     r["created_at"],
            "date":           r["date"],
            "type":           "transfer",
            "amount_pence":   abs(r["amount_pence"]),
            "from_account":   r["from_account"],
            "to_account":     r["to_account"],
            "notes":          r.get("notes") or "",
        })

    prev_by_account = {}
    for row in val_all:
        r = dict(row)
        acct_id = r["account_id"]
        prev = prev_by_account.get(acct_id)
        diff = r["value_pence"] - prev if prev is not None else r["value_pence"]
        prev_by_account[acct_id] = r["value_pence"]
        combined.append({
            "created_at":   r["created_at"],
            "date":         r["date"],
            "type":         "valuation",
            "amount_pence": diff,
            "account_name": r["account_name"],
            "notes":        r.get("notes") or "",
        })

    combined.sort(key=lambda x: x["created_at"] or "", reverse=True)
    return jsonify(combined[:50])


# --- API: Net worth summary ---

@app.route("/api/net-worth-summary")
def net_worth_summary():
    db = get_db()
    today = date.today()
    first_of_this_month = today.replace(day=1)
    last_of_prev_month  = first_of_this_month - dt.timedelta(days=1)
    last_of_prev_month_str = last_of_prev_month.strftime("%Y-%m-%d")
    last_of_prev_year_str  = date(today.year - 1, 12, 31).strftime("%Y-%m-%d")

    def net_worth_at(as_of_str=None):
        """
        Calculate total net worth as of a date using targeted aggregate queries.
        If as_of_str is None, returns current net worth (active accounts only).
        If as_of_str is set, returns historical net worth (all accounts, inc. deactivated).
        """
        is_current  = as_of_str is None
        date_clause = "AND t.date <= ?" if not is_current else ""

        # Current = active only; historical = all accounts (deactivated ones existed then)
        active_filter     = "AND a.is_active = 1" if is_current else ""
        inv_active_filter = "WHERE type IN ('investment', 'isa') AND is_active = 1" if is_current else "WHERE type IN ('investment', 'isa')"

        tx_rows = db.execute(
            f"""SELECT a.opening_balance_pence +
                       COALESCE((
                           SELECT SUM(t.amount_pence)
                           FROM transactions t
                           WHERE t.account_id = a.id
                             AND t.is_void = 0
                             {date_clause}
                       ), 0) AS balance
                FROM accounts a
                WHERE a.type NOT IN ('investment', 'isa')
                {active_filter}""",
            (as_of_str,) if not is_current else ()
        ).fetchall()
        tx_total = sum(r["balance"] for r in tx_rows)

        inv_accounts = db.execute(
            f"SELECT id, opening_balance_pence FROM accounts {inv_active_filter}"
        ).fetchall()

        inv_total = 0
        for acct in inv_accounts:
            val = db.execute(
                "SELECT value_pence FROM investment_valuations "
                "WHERE account_id = ? AND is_void = 0 "
                + ("AND valuation_date <= ? " if not is_current else "")
                + "ORDER BY valuation_date DESC, id DESC LIMIT 1",
                (acct["id"], as_of_str) if not is_current else (acct["id"],)
            ).fetchone()
            inv_total += val["value_pence"] if val else acct["opening_balance_pence"]

        return tx_total + inv_total

    current     = net_worth_at()
    prior_month = net_worth_at(last_of_prev_month_str)
    prior_year  = net_worth_at(last_of_prev_year_str)

    def change_info(current_val, prior_val):
        change = current_val - prior_val
        pct = round((change / abs(prior_val)) * 100, 4) if prior_val != 0 else 0.0
        return {"change_pence": change, "change_pct": pct}

    mc = change_info(current, prior_month)
    yc = change_info(current, prior_year)

    return jsonify({
        "current_net_worth_pence": current,
        "month_change_pence":      mc["change_pence"],
        "month_change_pct":        mc["change_pct"],
        "prior_month_label":       last_of_prev_month.strftime("%d %b %Y"),
        "ytd_change_pence":        yc["change_pence"],
        "ytd_change_pct":          yc["change_pct"],
        "prior_year_label":        f"01 Jan {today.year}"
    })


# --- API: Reports ---

@app.route("/api/reports/allocations")
def allocations():
    db    = get_db()
    cache = build_balance_cache(db)
    result = [
        {
            "id":      a["id"],
            "name":    a["name"],
            "type":    a["type"],
            "balance": round(cache["current_balance"](a) / 100, 2)
        }
        for a in cache["accounts"]
    ]
    return jsonify({"accounts": result})


@app.route("/api/reports/net-worth-history")
def net_worth_history():
    db    = get_db()
    cache = build_balance_cache(db)

    earliest_tx  = db.execute("SELECT MIN(date) as d FROM transactions WHERE is_void = 0").fetchone()["d"]
    earliest_val = db.execute("SELECT MIN(valuation_date) as d FROM investment_valuations WHERE is_void = 0").fetchone()["d"]
    candidates   = [d for d in [earliest_tx, earliest_val] if d]
    if not candidates:
        return jsonify({"labels": [], "total": [], "accounts": []})

    earliest_date = datetime.strptime(min(candidates), "%Y-%m-%d").date()
    accounts      = cache["accounts"]
    today         = date.today()

    month_ends = []
    y, m = earliest_date.year, earliest_date.month
    while True:
        last_day = date(y, m + 1, 1) - dt.timedelta(days=1) if m < 12 else date(y, 12, 31)
        month_ends.append(last_day)
        if last_day >= today:
            break
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)

    labels, total_series = [], []
    account_series = {a["id"]: [] for a in accounts}

    for month_end in month_ends:
        as_of = min(month_end, today).strftime("%Y-%m-%d")
        labels.append(month_end.strftime("%b %Y"))
        total = 0
        for account in accounts:
            balance = cache["balance_at"](account, as_of)
            account_series[account["id"]].append(round(balance / 100, 2))
            total += balance
        total_series.append(round(total / 100, 2))

    return jsonify({
        "labels": labels, "total": total_series,
        "accounts": [{"id": a["id"], "name": a["name"], "type": a["type"], "values": account_series[a["id"]]} for a in accounts]
    })


@app.route("/api/reports/net-worth-history-v2")
def net_worth_history_v2():
    """
    Net worth history with configurable timeframe and granularity.
    Query params:
      period      : all | 12m | 6m | 3m | 1m   (default: all)
      granularity : month | week | day           (default: month)
    """
    db          = get_db()
    period      = request.args.get("period",      "all")
    granularity = request.args.get("granularity", "month")
    today       = date.today()

    # --- Determine start date from period ---
    if period == "1m":
        start_date = today.replace(day=1)
    elif period == "3m":
        m = today.month - 3; y = today.year
        if m <= 0: m += 12; y -= 1
        start_date = date(y, m, 1)
    elif period == "6m":
        m = today.month - 6; y = today.year
        if m <= 0: m += 12; y -= 1
        start_date = date(y, m, 1)
    elif period == "12m":
        m = today.month - 12; y = today.year
        if m <= 0: m += 12; y -= 1
        start_date = date(y, m, 1)
    else:  # all
        earliest_tx  = db.execute("SELECT MIN(date) as d FROM transactions WHERE is_void = 0").fetchone()["d"]
        earliest_val = db.execute("SELECT MIN(valuation_date) as d FROM investment_valuations WHERE is_void = 0").fetchone()["d"]
        candidates   = [d for d in [earliest_tx, earliest_val] if d]
        if not candidates:
            return jsonify({"labels": [], "total": [], "accounts": []})
        start_date = datetime.strptime(min(candidates), "%Y-%m-%d").date()

    accounts = [dict(a) for a in db.execute(
        "SELECT id, name, type FROM accounts WHERE is_active = 1 ORDER BY COALESCE(display_order, 9999), name"
    ).fetchall()]

    # --- Build list of snapshot dates based on granularity ---
    # Each entry is the "as of" date for that data point
    snapshot_dates = []

    if granularity == "day":
        d = start_date
        while d <= today:
            snapshot_dates.append(d)
            d += dt.timedelta(days=1)
    elif granularity == "week":
        # Advance to the first Sunday on or after start_date
        d = start_date
        # Move to end of first week (Sunday = weekday 6)
        days_until_sunday = (6 - d.weekday()) % 7
        if days_until_sunday == 0 and d != start_date:
            days_until_sunday = 7
        d = d + dt.timedelta(days=days_until_sunday)
        while d <= today:
            snapshot_dates.append(d)
            d += dt.timedelta(weeks=1)
        # Always include today as the final point if not already included
        if not snapshot_dates or snapshot_dates[-1] < today:
            snapshot_dates.append(today)
    else:  # month
        y, m = start_date.year, start_date.month
        while True:
            last_day = date(y, m + 1, 1) - dt.timedelta(days=1) if m < 12 else date(y, 12, 31)
            snapshot_dates.append(min(last_day, today))
            if last_day >= today:
                break
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)

    # --- Format labels based on granularity ---
    def fmt_label(d):
        if granularity == "day":
            return d.strftime("%d %b")
        elif granularity == "week":
            return d.strftime("%d %b")
        else:
            return d.strftime("%b %Y")

    # --- Build balance cache (two bulk queries, then O(log n) lookups) ---
    cache    = build_balance_cache(db)
    accounts = cache["accounts"]  # active accounts only — used for per-account toggles

    # --- Calculate balances at each snapshot using in-memory lookups ---
    labels, total_series = [], []
    account_series = {a["id"]: [] for a in accounts}

    for snap in snapshot_dates:
        as_of = snap.strftime("%Y-%m-%d")
        labels.append(fmt_label(snap))
        # Use net_worth_at from cache — it internally includes ALL accounts
        # (active + inactive) so deactivated accounts contribute correctly
        # to historical totals
        total = cache["net_worth_at"](as_of)
        for account in accounts:
            balance = cache["balance_at"](account, as_of)
            account_series[account["id"]].append(round(balance / 100, 2))
        total_series.append(round(total / 100, 2))

    return jsonify({
        "labels":   labels,
        "total":    total_series,
        "accounts": [{"id": a["id"], "name": a["name"], "type": a["type"], "values": account_series[a["id"]]} for a in accounts]
    })


@app.route("/api/reports/income-expenditure")
def income_expenditure():
    """
    Income vs Expenditure report.
    Query params:
      period      : all | 12m | 6m | 3m | 1m   (default: all)
      granularity : month | week | day           (default: month)
    """
    db          = get_db()
    period      = request.args.get("period",      "all")
    granularity = request.args.get("granularity", "month")
    today       = date.today()

    # --- Determine start date from period ---
    if period == "1m":
        start_date = today.replace(day=1)
    elif period == "3m":
        m = today.month - 3; y = today.year
        if m <= 0: m += 12; y -= 1
        start_date = date(y, m, 1)
    elif period == "6m":
        m = today.month - 6; y = today.year
        if m <= 0: m += 12; y -= 1
        start_date = date(y, m, 1)
    elif period == "12m":
        m = today.month - 12; y = today.year
        if m <= 0: m += 12; y -= 1
        start_date = date(y, m, 1)
    else:  # all
        earliest = db.execute(
            "SELECT MIN(date) as d FROM transactions WHERE is_void=0 AND is_transfer=0"
        ).fetchone()["d"]
        if not earliest:
            return jsonify({"labels": [], "income": [], "expenditure": [], "net": []})
        start_date = datetime.strptime(earliest, "%Y-%m-%d").date()

    start_str = start_date.strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    # --- Fetch all relevant transactions in one query ---
    rows = db.execute(
        """SELECT date,
                  CASE WHEN amount_pence > 0 THEN  amount_pence ELSE 0 END AS income_pence,
                  CASE WHEN amount_pence < 0 THEN -amount_pence ELSE 0 END AS expenditure_pence
           FROM transactions
           WHERE is_void = 0 AND is_transfer = 0
             AND date >= ? AND date <= ?""",
        (start_str, today_str)
    ).fetchall()

    # --- Build snapshot buckets and accumulate totals ---
    # We build an ordered list of (bucket_key, label) pairs, then
    # assign each transaction to its bucket via a lookup function.

    if granularity == "day":
        # One bucket per calendar day from start_date to today
        buckets = []
        d = start_date
        while d <= today:
            key   = d.strftime("%Y-%m-%d")
            label = d.strftime("%d %b")
            buckets.append((key, label))
            d += dt.timedelta(days=1)

        def bucket_key_for(date_str):
            return date_str  # exact match

    elif granularity == "week":
        # One bucket per week — bucket key is the Monday of that week (ISO).
        # We generate week-start Mondays from the Monday on/before start_date
        # through to today.
        buckets = []
        # Rewind start_date to the Monday of its week
        week_start = start_date - dt.timedelta(days=start_date.weekday())
        d = week_start
        seen = set()
        while d <= today:
            key   = d.strftime("%Y-%m-%d")  # Monday date as key
            label = d.strftime("%d %b")
            if key not in seen:
                buckets.append((key, label))
                seen.add(key)
            d += dt.timedelta(weeks=1)
        # Ensure today's week is included
        last_monday = today - dt.timedelta(days=today.weekday())
        key = last_monday.strftime("%Y-%m-%d")
        if key not in seen:
            buckets.append((key, last_monday.strftime("%d %b")))

        def bucket_key_for(date_str):
            # Return the Monday of the week containing date_str
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            monday = d - dt.timedelta(days=d.weekday())
            return monday.strftime("%Y-%m-%d")

    else:  # month
        # One bucket per calendar month
        buckets = []
        y, m = start_date.year, start_date.month
        while True:
            key   = f"{y:04d}-{m:02d}"
            label = date(y, m, 1).strftime("%b %Y")
            buckets.append((key, label))
            if y == today.year and m == today.month:
                break
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)

        def bucket_key_for(date_str):
            return date_str[:7]  # "YYYY-MM"

    # Build lookup dict: key -> {income_pence, expenditure_pence}
    totals = {key: {"inc": 0, "exp": 0} for key, _ in buckets}
    for row in rows:
        k = bucket_key_for(row["date"])
        if k in totals:
            totals[k]["inc"] += row["income_pence"]
            totals[k]["exp"] += row["expenditure_pence"]

    labels, income, expenditure, net = [], [], [], []
    for key, label in buckets:
        t = totals[key]
        labels.append(label)
        income.append(round(t["inc"] / 100, 2))
        expenditure.append(round(t["exp"] / 100, 2))
        net.append(round((t["inc"] - t["exp"]) / 100, 2))

    return jsonify({"labels": labels, "income": income, "expenditure": expenditure, "net": net})


@app.route("/api/reports/breakdown")
def breakdown():
    db = get_db()
    period    = request.args.get("period", "all")
    mode      = request.args.get("mode", "spend")
    parent_id = request.args.get("parent_id", "") or None
    today     = date.today()

    if period == "1m":
        date_filter = f"AND t.date >= '{today.replace(day=1).strftime('%Y-%m-%d')}'"
    elif period == "3m":
        m = today.month - 3; y = today.year
        if m <= 0: m += 12; y -= 1
        date_filter = f"AND t.date >= '{date(y, m, 1).strftime('%Y-%m-%d')}'"
    elif period == "6m":
        m = today.month - 6; y = today.year
        if m <= 0: m += 12; y -= 1
        date_filter = f"AND t.date >= '{date(y, m, 1).strftime('%Y-%m-%d')}'"
    elif period == "12m":
        m = today.month - 12; y = today.year
        if m <= 0: m += 12; y -= 1
        date_filter = f"AND t.date >= '{date(y, m, 1).strftime('%Y-%m-%d')}'"
    else:
        date_filter = ""

    amount_filter = "AND t.amount_pence < 0" if mode == "spend" else "AND t.amount_pence > 0"

    if parent_id:
        rows = db.execute(
            f"""SELECT c.id, c.name, COALESCE(SUM(ABS(t.amount_pence)),0) as total_pence
                FROM categories c
                LEFT JOIN transactions t ON t.category_id=c.id AND t.is_void=0 AND t.is_transfer=0 {amount_filter} {date_filter}
                WHERE c.parent_id=? AND c.is_active=1 GROUP BY c.id ORDER BY total_pence DESC""",
            (parent_id,)
        ).fetchall()
        categories = [{"id": r["id"], "name": r["name"], "amount": round(r["total_pence"]/100, 2), "has_children": False}
                      for r in rows if r["total_pence"] > 0]
    else:
        rows = db.execute(
            f"""SELECT c.id, c.name, COALESCE(SUM(ABS(t.amount_pence)),0) as total_pence
                FROM categories c
                LEFT JOIN transactions t ON (t.category_id=c.id OR t.category_id IN (SELECT id FROM categories WHERE parent_id=c.id))
                    AND t.is_void=0 AND t.is_transfer=0 {amount_filter} {date_filter}
                WHERE c.parent_id IS NULL AND c.is_active=1 GROUP BY c.id ORDER BY total_pence DESC"""
        ).fetchall()
        children_ids = {r["id"] for r in db.execute("SELECT DISTINCT parent_id as id FROM categories WHERE parent_id IS NOT NULL AND is_active=1").fetchall()}
        categories = [{"id": r["id"], "name": r["name"], "amount": round(r["total_pence"]/100, 2), "has_children": r["id"] in children_ids}
                      for r in rows if r["total_pence"] > 0]

    return jsonify({"categories": categories, "total": round(sum(c["amount"] for c in categories), 2)})


@app.route("/api/reports/category-trends")
def category_trends():
    """
    Category trends report.
    Query params:
      period      : all | 12m | 6m | 3m | 1m   (default: all)
      granularity : month | week | day           (default: month)
      mode        : spend | income               (default: spend)
    """
    db          = get_db()
    period      = request.args.get("period",      "all")
    granularity = request.args.get("granularity", "month")
    mode        = request.args.get("mode",        "spend")
    today       = date.today()

    is_income = (mode == "income")

    # --- Determine start date from period ---
    if period == "1m":
        from_date = today.replace(day=1)
    elif period == "3m":
        m = today.month - 3; y = today.year
        if m <= 0: m += 12; y -= 1
        from_date = date(y, m, 1)
    elif period == "6m":
        m = today.month - 6; y = today.year
        if m <= 0: m += 12; y -= 1
        from_date = date(y, m, 1)
    elif period == "12m":
        m = today.month - 12; y = today.year
        if m <= 0: m += 12; y -= 1
        from_date = date(y, m, 1)
    else:  # all
        sign_filter = "AND amount_pence > 0" if is_income else "AND amount_pence < 0"
        earliest = db.execute(
            f"SELECT MIN(date) as d FROM transactions WHERE is_void=0 AND is_transfer=0 {sign_filter} AND category_id IS NOT NULL"
        ).fetchone()["d"]
        if not earliest:
            return jsonify({"labels": [], "categories": []})
        from_date = datetime.strptime(earliest, "%Y-%m-%d").date().replace(day=1)

    from_str  = from_date.strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    # --- Build ordered bucket list (same pattern as income-expenditure) ---
    buckets = []  # list of (bucket_key, label)

    if granularity == "day":
        d = from_date
        while d <= today:
            buckets.append((d.strftime("%Y-%m-%d"), d.strftime("%d %b")))
            d += dt.timedelta(days=1)

        def bucket_key_for(date_str):
            return date_str

    elif granularity == "week":
        week_start = from_date - dt.timedelta(days=from_date.weekday())
        d = week_start
        seen = set()
        while d <= today:
            key = d.strftime("%Y-%m-%d")
            if key not in seen:
                buckets.append((key, d.strftime("%d %b")))
                seen.add(key)
            d += dt.timedelta(weeks=1)
        last_monday = today - dt.timedelta(days=today.weekday())
        key = last_monday.strftime("%Y-%m-%d")
        if key not in seen:
            buckets.append((key, last_monday.strftime("%d %b")))

        def bucket_key_for(date_str):
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            monday = d - dt.timedelta(days=d.weekday())
            return monday.strftime("%Y-%m-%d")

    else:  # month
        y, m = from_date.year, from_date.month
        while True:
            buckets.append((f"{y:04d}-{m:02d}", date(y, m, 1).strftime("%b %Y")))
            if y == today.year and m == today.month:
                break
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)

        def bucket_key_for(date_str):
            return date_str[:7]

    bucket_keys = [k for k, _ in buckets]
    labels      = [l for _, l in buckets]

    # --- Determine relevant categories ---
    # For income: subcategory level. For spend: top-level (rolled up).
    if is_income:
        relevant_cats = db.execute(
            """SELECT DISTINCT c.id, c.name, c.parent_id
               FROM categories c
               JOIN transactions t ON t.category_id = c.id
               WHERE c.is_active = 1
                 AND c.parent_id IS NOT NULL
                 AND t.is_void = 0 AND t.is_transfer = 0
                 AND t.amount_pence > 0
                 AND t.date >= ? AND t.date <= ?
               ORDER BY c.name""",
            (from_str, today_str)
        ).fetchall()
    else:
        relevant_cats = db.execute(
            "SELECT id, name FROM categories WHERE parent_id IS NULL AND is_active=1 ORDER BY name"
        ).fetchall()

    if not relevant_cats:
        return jsonify({"labels": labels, "categories": []})

    # --- Fetch raw transaction rows (one query, bucket in Python) ---
    if is_income:
        raw_rows = db.execute(
            f"""SELECT t.date, t.category_id AS cat_id, t.amount_pence
                FROM transactions t
                WHERE t.is_void = 0 AND t.is_transfer = 0
                  AND t.amount_pence > 0
                  AND t.date >= ? AND t.date <= ?
                  AND t.category_id IN ({",".join("?" * len(relevant_cats))})""",
            (from_str, today_str, *[c["id"] for c in relevant_cats])
        ).fetchall()
    else:
        raw_rows = db.execute(
            """SELECT t.date,
                      COALESCE(pc.id, c.id) AS cat_id,
                      ABS(t.amount_pence)   AS amount_pence
               FROM transactions t
               JOIN categories c  ON t.category_id = c.id
               LEFT JOIN categories pc ON c.parent_id = pc.id
               WHERE t.is_void = 0 AND t.is_transfer = 0
                 AND t.amount_pence < 0
                 AND t.date >= ? AND t.date <= ?""",
            (from_str, today_str)
        ).fetchall()

    # --- Accumulate into {cat_id: {bucket_key: total_pence}} ---
    cat_bucket_totals = {}
    for row in raw_rows:
        bk     = bucket_key_for(row["date"])
        cat_id = row["cat_id"]
        if bk not in (k for k in bucket_keys):
            continue
        if cat_id not in cat_bucket_totals:
            cat_bucket_totals[cat_id] = {}
        cat_bucket_totals[cat_id][bk] = cat_bucket_totals[cat_id].get(bk, 0) + row["amount_pence"]

    # --- Build result, only including categories with any data ---
    result_cats = []
    for cat in relevant_cats:
        cat_data = cat_bucket_totals.get(cat["id"], {})
        if not cat_data:
            continue
        monthly = [round(cat_data.get(bk, 0) / 100, 2) for bk in bucket_keys]
        result_cats.append({"id": cat["id"], "name": cat["name"], "monthly": monthly})

    return jsonify({"labels": labels, "categories": result_cats})


# --- API: Inflation reports ---

@app.route("/api/reports/inflation-years")
def inflation_years():
    """Returns the list of years that have spending transaction data."""
    db = get_db()
    rows = db.execute(
        """SELECT DISTINCT strftime('%Y', date) as yr
           FROM transactions
           WHERE is_void=0 AND is_transfer=0 AND amount_pence<0
           ORDER BY yr ASC"""
    ).fetchall()
    years = [int(r["yr"]) for r in rows]
    return jsonify({"years": years})


@app.route("/api/reports/inflation")
def inflation_report():
    """Period-based inflation: compares two equal back-to-back periods."""
    db     = get_db()
    period = request.args.get("period", "3m")
    today  = date.today()

    n_months = {"3m": 3, "6m": 6, "12m": 12}.get(period, 3)

    first_of_this_month = today.replace(day=1)
    later_end = first_of_this_month - dt.timedelta(days=1)

    lm = later_end.month - n_months
    ly = later_end.year
    while lm <= 0:
        lm += 12; ly -= 1
    later_start = date(ly, lm, 1)

    earlier_end = later_start - dt.timedelta(days=1)
    em = earlier_end.month - n_months + 1
    ey = earlier_end.year
    while em <= 0:
        em += 12; ey -= 1
    earlier_start = date(ey, em, 1)

    earliest_tx = db.execute(
        "SELECT MIN(date) as d FROM transactions WHERE is_void=0 AND is_transfer=0 AND amount_pence<0"
    ).fetchone()["d"]

    if not earliest_tx:
        return jsonify({"insufficient": True, "message": "No spending data found yet."})

    earliest_date = datetime.strptime(earliest_tx, "%Y-%m-%d").date()
    if earliest_date > earlier_end:
        months_available = (later_end.year - earliest_date.year) * 12 + (later_end.month - earliest_date.month)
        return jsonify({
            "insufficient": True,
            "message": f"Not enough history for a {n_months}-month comparison. "
                       f"You have approximately {max(0, months_available)} month(s) of data — "
                       f"need at least {n_months * 2} months. "
                       f"Try a shorter comparison period, or come back when more data has built up."
        })

    def period_label(start, end):
        if start.year == end.year:
            return f"{start.strftime('%b')}–{end.strftime('%b %Y')}"
        return f"{start.strftime('%b %Y')}–{end.strftime('%b %Y')}"

    es, ee = earlier_start.strftime("%Y-%m-%d"), earlier_end.strftime("%Y-%m-%d")
    ls, le = later_start.strftime("%Y-%m-%d"),   later_end.strftime("%Y-%m-%d")

    earlier_spend = get_category_spend_for_period(db, es, ee)
    later_spend   = get_category_spend_for_period(db, ls, le)

    all_ids = set(earlier_spend.keys()) | set(later_spend.keys())
    categories = []
    for cat_id in all_ids:
        e_data = earlier_spend.get(cat_id, {"name": None, "total": 0})
        l_data = later_spend.get(cat_id,   {"name": None, "total": 0})
        name   = l_data["name"] or e_data["name"] or "Unknown"
        earlier_avg = round((e_data["total"] / n_months) / 100, 2)
        later_avg   = round((l_data["total"] / n_months) / 100, 2)
        change_pct  = round(((later_avg - earlier_avg) / earlier_avg) * 100, 2) if earlier_avg > 0 and later_avg > 0 else None
        categories.append({"name": name, "earlier_avg": earlier_avg, "later_avg": later_avg, "change_pct": change_pct})

    def sort_key(c):
        if c["change_pct"] is not None:
            return (0, -c["change_pct"])
        elif c["earlier_avg"] == 0:
            return (1, 0)
        else:
            return (2, 0)
    categories.sort(key=sort_key)

    earlier_total_all = sum(v["total"] for v in earlier_spend.values())
    later_total_all   = sum(v["total"] for v in later_spend.values())
    earlier_total_avg = round((earlier_total_all / n_months) / 100, 2)
    later_total_avg   = round((later_total_all   / n_months) / 100, 2)
    overall_change_pct = round(((later_total_avg - earlier_total_avg) / earlier_total_avg) * 100, 2) if earlier_total_avg > 0 else 0.0

    return jsonify({
        "insufficient":       False,
        "earlier_label":      period_label(earlier_start, earlier_end),
        "later_label":        period_label(later_start,   later_end),
        "earlier_total_avg":  earlier_total_avg,
        "later_total_avg":    later_total_avg,
        "overall_change_pct": overall_change_pct,
        "categories":         categories
    })


@app.route("/api/reports/inflation-yoy")
def inflation_yoy():
    """
    Year-on-year inflation across a range of years.
    For each year, calculates average monthly spend per category.
    Returns columns for each year plus change columns between adjacent years.
    """
    db = get_db()
    try:
        year_from = int(request.args.get("from", 0))
        year_to   = int(request.args.get("to",   0))
    except (ValueError, TypeError):
        return jsonify({"insufficient": True, "message": "Invalid year range."}), 400

    if not year_from or not year_to:
        return jsonify({"insufficient": True, "message": "Please select a year range."})

    year_from = min(year_from, year_to)
    year_to   = max(year_from, year_to)
    years     = list(range(year_from, year_to + 1))

    if len(years) < 1:
        return jsonify({"insufficient": True, "message": "Invalid year range."})

    # Check we actually have data for at least one of the requested years
    earliest_tx = db.execute(
        "SELECT MIN(date) as d FROM transactions WHERE is_void=0 AND is_transfer=0 AND amount_pence<0"
    ).fetchone()["d"]

    if not earliest_tx:
        return jsonify({"insufficient": True, "message": "No spending data found yet."})

    # Gather spend per year
    # For each year we use Jan 1 – Dec 31 and divide by 12 for avg monthly spend.
    # For the current partial year we divide by the number of completed months so far.
    today = date.today()

    year_spends = []   # list of {cat_id: {name, total}} per year, in order
    year_months = []   # number of months to divide by for each year

    for yr in years:
        year_start = f"{yr}-01-01"
        year_end   = f"{yr}-12-31"
        if yr == today.year:
            # Partial year: use months completed so far (at least 1)
            n_months = max(1, today.month - 1) if today.day < 28 else today.month
        else:
            n_months = 12
        spend = get_category_spend_for_period(db, year_start, year_end)
        year_spends.append(spend)
        year_months.append(n_months)

    # Collect all category ids across all years
    all_ids = set()
    for spend in year_spends:
        all_ids |= set(spend.keys())

    if not all_ids:
        return jsonify({"insufficient": True, "message": "No categorised spending found for the selected years."})

    # Build category rows
    # For each category: list of avg monthly spend per year, list of % changes between adjacent years
    categories = []
    for cat_id in all_ids:
        # Get name from whichever year has it
        name = "Unknown"
        for spend in year_spends:
            if cat_id in spend and spend[cat_id]["name"]:
                name = spend[cat_id]["name"]
                break

        yearly_avgs = []
        for i, spend in enumerate(year_spends):
            total    = spend.get(cat_id, {"total": 0})["total"]
            avg      = round((total / year_months[i]) / 100, 2)
            yearly_avgs.append(avg)

        # Changes between adjacent years
        changes = []
        for i in range(len(yearly_avgs) - 1):
            prev = yearly_avgs[i]
            nxt  = yearly_avgs[i + 1]
            if prev > 0 and nxt > 0:
                changes.append(round(((nxt - prev) / prev) * 100, 2))
            else:
                changes.append(None)

        # Only include if there's spend in at least one year
        if any(a > 0 for a in yearly_avgs):
            categories.append({
                "name":        name,
                "yearly_avgs": yearly_avgs,
                "changes":     changes
            })

    # Sort by name alphabetically
    categories.sort(key=lambda c: c["name"].lower())

    # Totals row
    totals = []
    for i, spend in enumerate(year_spends):
        total_all = sum(v["total"] for v in spend.values())
        totals.append(round((total_all / year_months[i]) / 100, 2))

    total_changes = []
    for i in range(len(totals) - 1):
        if totals[i] > 0 and totals[i + 1] > 0:
            total_changes.append(round(((totals[i + 1] - totals[i]) / totals[i]) * 100, 2))
        else:
            total_changes.append(None)

    return jsonify({
        "insufficient":  False,
        "years":         years,
        "categories":    categories,
        "totals":        totals,
        "total_changes": total_changes
    })


@app.route("/api/reports/runway")
def savings_runway():
    db = get_db()
    period   = request.args.get("period", "all")
    mode     = request.args.get("mode", "spend")
    acct_raw = request.args.get("accounts", "")
    today    = date.today()

    try:
        account_ids = [int(x) for x in acct_raw.split(",") if x.strip()]
    except ValueError:
        account_ids = []

    if not account_ids:
        return jsonify({"error": "No accounts selected."}), 400

    available_pence = sum(get_account_balance(db, aid) for aid in account_ids)
    available_funds = round(available_pence / 100, 2)

    if period == "1m":
        from_date        = today.replace(day=1)
        period_label     = "this month"
        from_str         = from_date.strftime("%Y-%m-%d")
        to_str           = today.strftime("%Y-%m-%d")
        months_in_period = 1
    elif period == "3m":
        m = today.month - 2; y = today.year
        if m <= 0: m += 12; y -= 1
        from_date        = date(y, m, 1)
        period_label     = "last 3 months"
        from_str         = from_date.strftime("%Y-%m-%d")
        to_str           = today.strftime("%Y-%m-%d")
        months_in_period = 3
    elif period == "6m":
        m = today.month - 5; y = today.year
        if m <= 0: m += 12; y -= 1
        from_date        = date(y, m, 1)
        period_label     = "last 6 months"
        from_str         = from_date.strftime("%Y-%m-%d")
        to_str           = today.strftime("%Y-%m-%d")
        months_in_period = 6
    elif period == "12m":
        m = today.month - 11; y = today.year
        if m <= 0: m += 12; y -= 1
        from_date        = date(y, m, 1)
        period_label     = "last 12 months"
        from_str         = from_date.strftime("%Y-%m-%d")
        to_str           = today.strftime("%Y-%m-%d")
        months_in_period = 12
    else:
        earliest = db.execute("SELECT MIN(date) as d FROM transactions WHERE is_void=0 AND is_transfer=0").fetchone()["d"]
        from_date    = datetime.strptime(earliest, "%Y-%m-%d").date().replace(day=1) if earliest else today.replace(day=1)
        period_label = "all time"
        from_str         = from_date.strftime("%Y-%m-%d")
        to_str           = today.strftime("%Y-%m-%d")
        months_in_period = max(1, (today.year - from_date.year) * 12 + (today.month - from_date.month) + 1)

    placeholders = ",".join("?" * len(account_ids))

    exp_row = db.execute(
        f"SELECT COALESCE(SUM(ABS(amount_pence)),0) as total FROM transactions "
        f"WHERE is_void=0 AND is_transfer=0 AND amount_pence<0 AND date>=? AND date<=? "
        f"AND account_id IN ({placeholders})",
        (from_str, to_str, *account_ids)
    ).fetchone()
    inc_row = db.execute(
        f"SELECT COALESCE(SUM(amount_pence),0) as total FROM transactions "
        f"WHERE is_void=0 AND is_transfer=0 AND amount_pence>0 AND date>=? AND date<=? "
        f"AND account_id IN ({placeholders})",
        (from_str, to_str, *account_ids)
    ).fetchone()

    # For named periods, replace the fixed denominator with the actual number of
    # distinct calendar months that have at least one transaction in the window.
    # This avoids empty months (where you had no data yet) dragging the average down.
    # "This Month" always uses 1 — no change needed there.
    if period != "1m":
        months_with_data = db.execute(
            f"SELECT COUNT(DISTINCT strftime('%Y-%m', date)) as n FROM transactions "
            f"WHERE is_void=0 AND is_transfer=0 AND date>=? AND date<=? "
            f"AND account_id IN ({placeholders})",
            (from_str, to_str, *account_ids)
        ).fetchone()["n"]
        months_in_period = max(1, months_with_data)

    monthly_spend     = round((exp_row["total"] / months_in_period) / 100, 2)
    net_outflow_pence = exp_row["total"] - inc_row["total"]

    # For net mode, also factor in valuation changes on investment/ISA accounts
    # in the selected set. A valuation increase reduces net outflow; a drop increases it.
    inv_accounts = db.execute(
        f"SELECT id FROM accounts WHERE is_active=1 AND type IN ('investment','isa') "
        f"AND id IN ({placeholders})",
        (*account_ids,)
    ).fetchall()

    for acct in inv_accounts:
        aid = acct["id"]
        # Latest valuation on or before today
        latest = db.execute(
            "SELECT value_pence FROM investment_valuations "
            "WHERE account_id=? AND is_void=0 AND valuation_date<=? "
            "ORDER BY valuation_date DESC, id DESC LIMIT 1",
            (aid, to_str)
        ).fetchone()
        # Latest valuation strictly before the period start
        prior = db.execute(
            "SELECT value_pence FROM investment_valuations "
            "WHERE account_id=? AND is_void=0 AND valuation_date<? "
            "ORDER BY valuation_date DESC, id DESC LIMIT 1",
            (aid, from_str)
        ).fetchone()
        if latest and prior:
            # Positive delta = value went up = reduces net outflow
            val_delta = latest["value_pence"] - prior["value_pence"]
            net_outflow_pence -= val_delta

    monthly_net_outflow = round((net_outflow_pence / months_in_period) / 100, 2)
    monthly_burn        = monthly_spend if mode == "spend" else monthly_net_outflow

    if monthly_burn <= 0:
        runway_months = None
        runway_date   = None
    else:
        runway_months = int(available_funds / monthly_burn)
        run_out = today
        remaining = runway_months
        while remaining >= 12:
            run_out = run_out.replace(year=run_out.year + 1)
            remaining -= 12
        m2 = run_out.month + remaining
        y2 = run_out.year
        if m2 > 12: m2 -= 12; y2 += 1
        try:
            run_out = run_out.replace(year=y2, month=m2)
        except ValueError:
            run_out = date(y2, m2, 1)
        runway_date = run_out.strftime("%B %Y")

    projection = []
    balance    = available_funds
    # burn is positive when we are losing money, negative when we are gaining money
    burn       = monthly_burn if monthly_burn > 0 else monthly_burn
    proj_y, proj_m = today.year, today.month

    for _ in range(37):
        projection.append({"label": date(proj_y, proj_m, 1).strftime("%b %Y"), "balance": round(balance, 2)})
        balance -= burn                    # subtract a positive burn (spend), add when burn is negative (net gain)
        proj_m += 1
        if proj_m > 12: 
            proj_m = 1
            proj_y += 1
        if balance < -(available_funds * 2):
            break

    return jsonify({
        "available_funds": available_funds,
        "monthly_spend":   monthly_spend,
        "monthly_net":     monthly_net_outflow,
        "period_label":    period_label,
        "runway_months":   runway_months,
        "runway_date":     runway_date,
        "projection":      projection
    })


@app.route("/api/reports/interest-projections")
def interest_projections():
    db = get_db()
    today = date.today()

    # Get all active accounts with an interest rate set
    accounts = db.execute(
        """SELECT id, name, type, interest_rate
           FROM accounts
           WHERE is_active = 1 AND interest_rate IS NOT NULL AND interest_rate > 0
           ORDER BY COALESCE(display_order, 9999), name"""
    ).fetchall()

    if not accounts:
        return jsonify({"accounts": [], "months": [], "totals": []})

    # 1. FIX: Start labels from the CURRENT month (March)
    months = []
    curr_y, curr_m = today.year, today.month
    for _ in range(12):
        months.append(date(curr_y, curr_m, 1).strftime("%b %Y"))
        curr_m += 1
        if curr_m > 12:
            curr_m = 1
            curr_y += 1

    # 2. FIX: Calculate fraction of the CURRENT month remaining
    # If today is March 31, next_month_start is April 1
    if today.month == 12:
        next_month_start = date(today.year + 1, 1, 1)
    else:
        next_month_start = date(today.year, today.month + 1, 1)
    
    days_in_month = (next_month_start - date(today.year, today.month, 1)).days
    
    # On March 31: (April 1 - March 31) = 1 day. 1 - 1 = 0 days left.
    days_remaining = (next_month_start - today).days - 1
    fraction_remaining = max(0, days_remaining / days_in_month)

    result_accounts = []
    total_monthly_interest = [0.0] * 12
    total_projected_balances = []

    # We need starting balances for totals line
    starting_total = 0

    total_theoretical_interest = 0.0

    for account in accounts:
        a = dict(account)
        current_balance = get_account_balance(db, a["id"]) / 100  # convert to £

        # Monthly rate from AER — approximation: (1 + AER)^(1/12) - 1
        aer = a["interest_rate"] / 100
        monthly_rate = (1 + aer) ** (1 / 12) - 1

        total_theoretical_interest += (current_balance * monthly_rate)

        # Project 12 months with monthly compounding
        monthly_balances = []
        monthly_interest = []
        balance = current_balance
        total_interest_earned = 0

        for i in range(12):
            if i == 0:
                first_month_rate = (1 + monthly_rate) ** fraction_remaining - 1
                interest_this_month = balance * first_month_rate
            else:
                interest_this_month = balance * monthly_rate

            balance += interest_this_month
            monthly_balances.append(round(balance, 2))
            monthly_interest.append(round(interest_this_month, 2))
            total_monthly_interest[i] += interest_this_month
            total_interest_earned += interest_this_month

        result_accounts.append({
            "id":                   a["id"],
            "name":                 a["name"],
            "type":                 a["type"],
            "interest_rate":        a["interest_rate"],
            "current_balance":      round(current_balance, 2),
            "projected_balances":   monthly_balances,
            "monthly_interest":     monthly_interest,
            "total_interest_12m":   round(total_interest_earned, 2),
            "projected_balance_12m": round(monthly_balances[-1], 2)
        })

        starting_total += current_balance

    # Build totals line
    total_balance = starting_total
    for i in range(12):
        total_balance += total_monthly_interest[i]
        total_projected_balances.append(round(total_balance, 2))

    total_interest_12m = round(sum(total_monthly_interest), 2)

    # Calculate the True Blended AER
    blended_rate = 0
    annual_earning_power = 0
    
    if starting_total > 0:
        # Use the THEORETICAL interest (a full month) to find the rate
        monthly_growth_rate = total_theoretical_interest / starting_total
        
        # Annual Equivalent Rate (AER) formula
        blended_rate = ((1 + monthly_growth_rate) ** 12 - 1) * 100
        
        # Annual Earning Power = Current Balance * AER
        # This is the "Valid 12 months out" number you want
        annual_earning_power = starting_total * (blended_rate / 100)

    return jsonify({
        "accounts":          result_accounts,
        "months":            months,
        "total_interest_12m": total_interest_12m,
        "total_current":     round(starting_total, 2),
        "total_projected":   total_projected_balances,
        "total_balance_12m": round(total_projected_balances[-1] if total_projected_balances else starting_total, 2),
        "estimated_interest_full_month": round(total_theoretical_interest, 2), # Use the summed variable
        "blended_rate": round(blended_rate, 2),
        "annual_earning_power": round(annual_earning_power, 2)
    })

@app.route("/api/reports/investment-projections")
def investment_projections():
    db = get_db()
    today = date.today()

    # Get all active investment/ISA accounts that have NO interest rate set
    # (those with rates are covered by the interest page)
    accounts = db.execute(
        """SELECT id, name, type
           FROM accounts
           WHERE is_active = 1
             AND type IN ('investment', 'isa')
             AND (interest_rate IS NULL OR interest_rate = 0)
           ORDER BY COALESCE(display_order, 9999), name"""
    ).fetchall()

    if not accounts:
        return jsonify({"accounts": [], "months": []})

 # --- FIXED: Start labels from CURRENT month ---
    months = []
    y, m = today.year, today.month

    for _ in range(12):
        months.append(date(y, m, 1).strftime("%b %Y"))
        m += 1
        if m > 12:
            m = 1
            y += 1

    # --- NEW: Calculate fraction of the current month remaining ---
    # Find the first day of the *next* month so we can reliably count days in the *current* month
    if today.month == 12:
        next_month_start = date(today.year + 1, 1, 1)
    else:
        next_month_start = date(today.year, today.month + 1, 1)
        
    days_in_month = (next_month_start - date(today.year, today.month, 1)).days
    days_remaining = days_in_month - today.day
    fraction_remaining = days_remaining / days_in_month # e.g., 0.5 if halfway through the month

    result_accounts = []

    for account in accounts:
        a = dict(account)

        # Fetch all valuations in date order
        valuations = db.execute(
            """SELECT valuation_date, value_pence
               FROM investment_valuations
               WHERE account_id = ? AND is_void = 0
               ORDER BY valuation_date ASC, id ASC""",
            (a["id"],)
        ).fetchall()

        if len(valuations) == 0:
            result_accounts.append({
                "id":             a["id"],
                "name":           a["name"],
                "type":           a["type"],
                "status":         "no_data",
                "message":        "No valuations recorded yet.",
                "current_value":  None,
                "projections":    None
            })
            continue

        latest = dict(valuations[-1])
        current_value = round(latest["value_pence"] / 100, 2)

        if len(valuations) < 2:
            result_accounts.append({
                "id":            a["id"],
                "name":          a["name"],
                "type":          a["type"],
                "status":        "insufficient",
                "message":       "Only one valuation recorded — need at least two to calculate a growth rate. Check back after your next valuation.",
                "current_value": current_value,
                "projections":   None,
                "history":       [{"date": v["valuation_date"], "value": round(v["value_pence"] / 100, 2)} for v in valuations]
            })
            continue

        # Calculate implied annualised return from first to latest valuation
        first = dict(valuations[0])
        first_value  = first["value_pence"] / 100
        first_date   = datetime.strptime(first["valuation_date"], "%Y-%m-%d").date()
        latest_date  = datetime.strptime(latest["valuation_date"], "%Y-%m-%d").date()
        days_elapsed = (latest_date - first_date).days

        if days_elapsed < 1 or first_value <= 0:
            result_accounts.append({
                "id":            a["id"],
                "name":          a["name"],
                "type":          a["type"],
                "status":        "insufficient",
                "message":       "Not enough valuation history to calculate a reliable growth rate yet.",
                "current_value": current_value,
                "projections":   None,
                "history":       [{"date": v["valuation_date"], "value": round(v["value_pence"] / 100, 2)} for v in valuations]
            })
            continue

        # Calculate estimated return this month ---
        start_of_month = latest_date.replace(day=1)

        # Find the last valuation on or before start of month
        val_start_month = next(
        (v["value_pence"] / 100 for v in reversed(valuations)
        if datetime.strptime(v["valuation_date"], "%Y-%m-%d").date() <= start_of_month),
        first_value  # fallback if no valuation before month
        )

        monthly_return_amount = current_value - val_start_month
        monthly_return_pct = (monthly_return_amount / val_start_month) * 100 if val_start_month > 0 else 0

        # Annualised return: (latest / first) ^ (365 / days) - 1
        years_elapsed    = days_elapsed / 365.0
        annualised_return = (current_value / first_value) ** (1 / years_elapsed) - 1

        # Monthly rate from annualised
        monthly_base = (1 + annualised_return) ** (1 / 12) - 1
        monthly_pess = (1 + annualised_return * 0.5) ** (1 / 12) - 1
        monthly_opti = (1 + annualised_return * 1.5) ** (1 / 12) - 1

        # --- NEW: Pro-rated projection function ---
        def project(start, monthly_rate, fraction, n=12):
            vals = []
            bal  = start
            
            # Month 1: Pro-rate the growth based on days remaining
            # We use an exponent here so the compounding math stays accurate
            first_month_rate = (1 + monthly_rate) ** fraction - 1
            bal = bal * (1 + first_month_rate)
            vals.append(round(bal, 2))
            
            # Months 2-12: Apply the full monthly rate
            for _ in range(n - 1):
                bal = bal * (1 + monthly_rate)
                vals.append(round(bal, 2))
                
            return vals

        # Pass the fraction_remaining into our updated function
        proj_base = project(current_value, monthly_base, fraction_remaining)
        proj_pess = project(current_value, monthly_pess, fraction_remaining)
        proj_opti = project(current_value, monthly_opti, fraction_remaining)

        # Total gain/loss from history
        total_gain     = current_value - first_value
        total_gain_pct = round((total_gain / first_value) * 100, 2) if first_value > 0 else 0

        result_accounts.append({
            "id":                       a["id"],
            "name":                     a["name"],
            "type":                     a["type"],
            "status":                   "ok",
            "current_value":            current_value,
            "first_value":              round(first_value, 2),
            "first_date":               first["valuation_date"],
            "latest_date":              latest["valuation_date"],
            "total_gain":               round(total_gain, 2),
            "total_gain_pct":           total_gain_pct,
            "annualised_return":        round(annualised_return * 100, 2),
            "monthly_return":           round(monthly_return_amount, 2),             # actual £ this month so far
            "monthly_return_pct":       round(monthly_return_pct, 2),                # actual % this month so far
            "proj_monthly_return":      round(current_value * monthly_base, 2),      # projected £ full month
            "proj_monthly_return_pct":  round(monthly_base * 100, 2),              # projected % full month
            "proj_base":                proj_base,
            "proj_pessimistic":         proj_pess,
            "proj_optimistic":          proj_opti,
            "history":                  [{"date": v["valuation_date"], "value": round(v["value_pence"] / 100, 2)} for v in valuations]
        })

    return jsonify({
        "accounts": result_accounts,
        "months":   months
    })


# --- API: Pensions ---

PENSION_SUBTYPES_POT    = ("workplace", "lisa", "sipp")
PENSION_SUBTYPES_INCOME = ("lgps", "state_pension")

@app.route("/api/pensions", methods=["GET"])
def get_pensions():
    db = get_db()
    accounts = db.execute(
        """SELECT * FROM pension_accounts WHERE is_active = 1
           ORDER BY COALESCE(display_order, 9999), id"""
    ).fetchall()

    result = []
    for account in accounts:
        a = dict(account)
        is_pot = a["subtype"] in PENSION_SUBTYPES_POT

        # Fetch all entries in date order
        entries = db.execute(
            """SELECT * FROM pension_entries
               WHERE account_id = ? AND is_void = 0
               ORDER BY entry_date DESC, id DESC""",
            (a["id"],)
        ).fetchall()

        a["entries"]  = [dict(e) for e in entries]
        a["latest"]   = dict(entries[0]) if entries else None
        a["is_pot"]   = is_pot
        result.append(a)

    return jsonify(result)


@app.route("/api/pensions", methods=["POST"])
def add_pension():
    data    = request.get_json()
    name    = data.get("name", "").strip()
    subtype = data.get("subtype", "").strip()
    provider = data.get("provider", "").strip() or None
    notes   = data.get("notes", "").strip() or None

    if not name or not subtype:
        return jsonify({"error": "Name and type are required."}), 400

    db = get_db()
    max_order = db.execute(
        "SELECT COALESCE(MAX(display_order), 0) FROM pension_accounts WHERE is_active = 1"
    ).fetchone()[0]
    db.execute(
        """INSERT INTO pension_accounts (name, subtype, provider, notes, display_order)
           VALUES (?, ?, ?, ?, ?)""",
        (name, subtype, provider, notes, max_order + 1)
    )
    db.commit()
    return jsonify({"success": True}), 201


@app.route("/api/pensions/<int:account_id>", methods=["PATCH"])
def update_pension(account_id):
    data = request.get_json()
    db   = get_db()
    account = db.execute(
        "SELECT * FROM pension_accounts WHERE id = ?", (account_id,)
    ).fetchone()
    if not account:
        return jsonify({"error": "Pension not found."}), 404

    name     = data.get("name",     account["name"]).strip()
    provider = data.get("provider", account["provider"] or "").strip() or None
    notes    = data.get("notes",    account["notes"]    or "").strip() or None

    db.execute(
        """UPDATE pension_accounts SET name=?, provider=?, notes=?,
           updated_at=datetime('now') WHERE id=?""",
        (name, provider, notes, account_id)
    )
    db.commit()
    return jsonify({"success": True})


@app.route("/api/pensions/<int:account_id>/deactivate", methods=["POST"])
def deactivate_pension(account_id):
    db = get_db()
    db.execute(
        "UPDATE pension_accounts SET is_active=0 WHERE id=?", (account_id,)
    )
    db.commit()
    return jsonify({"success": True})


@app.route("/api/pensions/<int:account_id>/move", methods=["POST"])
def move_pension(account_id):
    data      = request.get_json()
    direction = data.get("direction")
    db        = get_db()
    accounts  = db.execute(
        """SELECT id FROM pension_accounts WHERE is_active = 1
           ORDER BY COALESCE(display_order, 9999), id"""
    ).fetchall()
    ids = [a["id"] for a in accounts]
    if account_id not in ids:
        return jsonify({"error": "Pension not found."}), 404
    idx = ids.index(account_id)
    if direction == "up" and idx == 0:
        return jsonify({"success": True})
    if direction == "down" and idx == len(ids) - 1:
        return jsonify({"success": True})
    swap_idx = idx - 1 if direction == "up" else idx + 1
    id_a, id_b = ids[idx], ids[swap_idx]
    for i, aid in enumerate(ids):
        db.execute("UPDATE pension_accounts SET display_order=? WHERE id=?", (i + 1, aid))
    db.execute("UPDATE pension_accounts SET display_order=? WHERE id=?", (swap_idx + 1, id_a))
    db.execute("UPDATE pension_accounts SET display_order=? WHERE id=?", (idx + 1, id_b))
    db.commit()
    return jsonify({"success": True})


@app.route("/api/pension-entries", methods=["POST"])
def add_pension_entry():
    data       = request.get_json()
    account_id = data.get("account_id")
    entry_date = data.get("entry_date", "").strip()
    notes      = data.get("notes", "").strip() or None

    if not account_id or not entry_date:
        return jsonify({"error": "Account and date are required."}), 400

    db      = get_db()
    account = db.execute(
        "SELECT subtype FROM pension_accounts WHERE id=? AND is_active=1",
        (account_id,)
    ).fetchone()
    if not account:
        return jsonify({"error": "Pension account not found."}), 404

    is_pot = account["subtype"] in PENSION_SUBTYPES_POT

    if is_pot:
        try:
            value_pence = round(float(data.get("value", 0)) * 100)
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid value."}), 400
        if value_pence <= 0:
            return jsonify({"error": "Value must be greater than zero."}), 400
        db.execute(
            """INSERT INTO pension_entries (account_id, entry_date, value_pence, notes)
               VALUES (?, ?, ?, ?)""",
            (account_id, entry_date, value_pence, notes)
        )
    else:
        try:
            annual_pence = round(float(data.get("annual", 0)) * 100)
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid annual amount."}), 400
        if annual_pence <= 0:
            return jsonify({"error": "Annual amount must be greater than zero."}), 400
        db.execute(
            """INSERT INTO pension_entries (account_id, entry_date, annual_pence, notes)
               VALUES (?, ?, ?, ?)""",
            (account_id, entry_date, annual_pence, notes)
        )

    db.commit()
    return jsonify({"success": True}), 201


@app.route("/api/pension-entries-list")
def list_pension_entries():
    """Returns all non-void entries for a pension account, newest first."""
    account_id = request.args.get("account_id")
    if not account_id:
        return jsonify([])
    db = get_db()
    rows = db.execute(
        """SELECT id, entry_date, value_pence, annual_pence, notes
           FROM pension_entries
           WHERE account_id = ? AND is_void = 0
           ORDER BY entry_date DESC, id DESC""",
        (account_id,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/pension-entries/<int:entry_id>", methods=["PATCH"])
def update_pension_entry(entry_id):
    data = request.get_json()
    db   = get_db()
    entry = db.execute(
        "SELECT * FROM pension_entries WHERE id = ? AND is_void = 0", (entry_id,)
    ).fetchone()
    if not entry:
        return jsonify({"error": "Entry not found or already void."}), 404

    entry_date = data.get("entry_date", entry["entry_date"]).strip()
    notes      = data.get("notes") or None

    # Determine whether this is a pot or income entry
    account = db.execute(
        "SELECT subtype FROM pension_accounts WHERE id = ?", (entry["account_id"],)
    ).fetchone()
    is_pot = account and account["subtype"] in PENSION_SUBTYPES_POT

    if is_pot:
        try:
            value_pence = round(float(data.get("value", entry["value_pence"] / 100)) * 100)
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid value."}), 400
        if value_pence <= 0:
            return jsonify({"error": "Value must be greater than zero."}), 400
        db.execute(
            "UPDATE pension_entries SET entry_date=?, value_pence=?, notes=? WHERE id=?",
            (entry_date, value_pence, notes, entry_id)
        )
    else:
        try:
            annual_pence = round(float(data.get("annual", entry["annual_pence"] / 100)) * 100)
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid annual amount."}), 400
        if annual_pence <= 0:
            return jsonify({"error": "Annual amount must be greater than zero."}), 400
        db.execute(
            "UPDATE pension_entries SET entry_date=?, annual_pence=?, notes=? WHERE id=?",
            (entry_date, annual_pence, notes, entry_id)
        )

    db.commit()
    return jsonify({"success": True})


@app.route("/api/pension-entries/<int:entry_id>/void", methods=["POST"])
def void_pension_entry(entry_id):
    db = get_db()
    entry = db.execute(
        "SELECT id FROM pension_entries WHERE id=? AND is_void=0", (entry_id,)
    ).fetchone()
    if not entry:
        return jsonify({"error": "Entry not found or already void."}), 404
    db.execute(
        "UPDATE pension_entries SET is_void=1 WHERE id=?", (entry_id,)
    )
    db.commit()
    return jsonify({"success": True})


@app.route("/api/pensions/summary", methods=["GET"])
def pension_summary():
    db = get_db()
    accounts = db.execute(
        "SELECT * FROM pension_accounts WHERE is_active=1"
    ).fetchall()

    total_pot_pence    = 0
    total_annual_pence = 0

    for account in accounts:
        a      = dict(account)
        is_pot = a["subtype"] in PENSION_SUBTYPES_POT
        latest = db.execute(
            """SELECT value_pence, annual_pence FROM pension_entries
               WHERE account_id=? AND is_void=0
               ORDER BY entry_date DESC, id DESC LIMIT 1""",
            (a["id"],)
        ).fetchone()
        if not latest:
            continue
        if is_pot and latest["value_pence"]:
            total_pot_pence += latest["value_pence"]
        elif not is_pot and latest["annual_pence"]:
            total_annual_pence += latest["annual_pence"]

    return jsonify({
        "total_pot_pence":      total_pot_pence,
        "total_annual_pence":   total_annual_pence,
        "total_monthly_pence":  round(total_annual_pence / 12)
    })


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, port=port)
