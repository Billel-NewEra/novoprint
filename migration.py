import sqlite3
import os
from datetime import datetime

DB = "instance/auth.sqlite"

print("📦 Migration DB pour ajouter role 'planning'")

conn = sqlite3.connect(DB)
cur = conn.cursor()

try:
    cur.execute("BEGIN")

    print("➡️ Création table temporaire")

    cur.execute("""
    CREATE TABLE users_new (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      username      TEXT    NOT NULL UNIQUE,
      password_hash TEXT    NOT NULL,
      role          TEXT    NOT NULL CHECK (role IN ('admin','planning','client')),
      client_id     INTEGER,
      is_active     INTEGER NOT NULL DEFAULT 1,
      created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)

    print("➡️ Copie des données")

    cur.execute("""
    INSERT INTO users_new
    SELECT * FROM users
    """)

    print("➡️ Suppression ancienne table")
    cur.execute("DROP TABLE users")

    print("➡️ Renommage")
    cur.execute("ALTER TABLE users_new RENAME TO users")

    print("➡️ Recréation index")
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_users_client_id
    ON users(client_id)
    """)

    conn.commit()

    print("✅ MIGRATION TERMINÉE")
    print("🕒", datetime.now())

except Exception as e:
    conn.rollback()
    print("❌ ERREUR :", e)

finally:
    conn.close()
