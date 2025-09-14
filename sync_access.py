import os
import argparse
import sqlite3
import pyodbc

# ⚠️ Mets ici le chemin exact de ta base Access
ACCESS_DB = r"C:\Users\benza\OneDrive\Desktop\pal - Copie.accde"
SQLITE_DB = os.path.join(os.path.dirname(__file__), "instance", "local.sqlite")

def sync(access_path, sqlite_path):
    if not os.path.exists(access_path):
        raise FileNotFoundError(f"Fichier Access introuvable: {access_path}")

    # Connexion Access
    conn_acc = pyodbc.connect(
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=" + access_path + ";"
    )
    cur_acc = conn_acc.cursor()

    # Connexion SQLite
    os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)
    conn_sql = sqlite3.connect(sqlite_path)
    cur_sql = conn_sql.cursor()

    # ==============================
    # TABLE client
    # ==============================
    cur_sql.execute("DROP TABLE IF EXISTS client")
    cur_sql.execute("""
        CREATE TABLE client (
            N INTEGER PRIMARY KEY,
            Entreprise TEXT,
            Contact TEXT,
            Tel TEXT,
            Email TEXT
        )
    """)
    rows = cur_acc.execute("SELECT NUM_CLIENT, ENTREPRISE, CONTACT, TELEPHONE, EMAIL FROM client")
    for row in rows:
        cur_sql.execute("INSERT INTO client VALUES (?, ?, ?, ?, ?)", row)

    # ==============================
    # TABLE matérialisée "orders"
    # ==============================
    cur_sql.execute("DROP TABLE IF EXISTS 'orders'")
    cur_sql.execute("""
        CREATE TABLE "orders" (
            nr TEXT,
            num_reservation INTEGER,
            num_commande INTEGER,
            client TEXT,
            produit TEXT,
            somme_qte INTEGER,
            situation TEXT,
            utilisateur TEXT,
            date_reservation TEXT,
            num_client INTEGER,
            observation TEXT,
            code_maquette TEXT
        )
    """)

    # Exécution de la requête Access corrigée
    rows = cur_acc.execute("""
        SELECT 
            RESERVATION.NUM_RESERVATION & MAQUETTE.CODE_MAQUETTE AS nr,
            RESERVATION.NUM_RESERVATION,
            RESERVATION.NUM_COMMANDE,
            CLIENT.ENTREPRISE,
            MAQUETTE.DESCRIPTION as produit,
            SUM(RESERVATION_TABLE.QTE) AS SommeDeQTE,
            RESERVATION.SITUATION,
            UTILISATEUR.NOM,
            RESERVATION.DATE_RESERVATION,
            CLIENT.NUM_CLIENT,
            RESERVATION.OBSERVATION,
            MAQUETTE.CODE_MAQUETTE
        FROM UTILISATEUR
        INNER JOIN ((CLIENT 
            INNER JOIN RESERVATION ON CLIENT.NUM_CLIENT = RESERVATION.CODE_CLIENT)
            INNER JOIN (MAQUETTE 
                INNER JOIN RESERVATION_TABLE ON MAQUETTE.CODE_MAQUETTE = RESERVATION_TABLE.CODE_PIECE
            ) ON RESERVATION.NUM_RESERVATION = RESERVATION_TABLE.NUM_RESERVATION
        ) ON UTILISATEUR.[N°] = RESERVATION.NUM_UTILISATEUR
        GROUP BY 
            RESERVATION.NUM_RESERVATION & MAQUETTE.CODE_MAQUETTE,
            RESERVATION.NUM_RESERVATION,
            RESERVATION.NUM_COMMANDE,
            CLIENT.ENTREPRISE,
            MAQUETTE.DESCRIPTION,
            RESERVATION.SITUATION,
            UTILISATEUR.NOM,
            RESERVATION.DATE_RESERVATION,
            CLIENT.NUM_CLIENT,
            RESERVATION.OBSERVATION,
            MAQUETTE.CODE_MAQUETTE
    """)

    for row in rows:
        cur_sql.execute("""
            INSERT INTO "orders" VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, row)

    # ==============================
    # COMMIT & CLOSE
    # ==============================
    conn_sql.commit()
    conn_sql.close()
    conn_acc.close()
    print(f"✅ Synchronisation terminée depuis {access_path} vers {sqlite_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--access", default=ACCESS_DB, help="Chemin du fichier Access (.accdb ou .accde)")
    parser.add_argument("--sqlite", default=SQLITE_DB, help="Chemin du fichier SQLite cible")
    args = parser.parse_args()
    sync(args.access, args.sqlite)
