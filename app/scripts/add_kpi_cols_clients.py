import os
import shutil
import sqlite3
import random
from datetime import datetime

# -----------------------------
# CONFIG
# -----------------------------
# Colonnes à ajouter (noms SQL propres, sans espaces/accents)
NEW_COLUMNS = [
    ("nb_transaction", "INTEGER"),
    ("vol_transaction", "REAL"),
    ("nb_retrait_gab", "INTEGER"),
    ("vol_retrait_gab", "REAL"),
    ("nb_transaction_ecom", "INTEGER"),
    ("vol_transaction_ecom", "REAL"),
    ("nb_virement", "INTEGER"),
    ("vol_virement", "REAL"),
    ("solde_moyen_depots", "REAL"),
    ("encours_moyen", "REAL"),
    ("encours_global", "REAL"),
    ("encours_conso", "REAL"),
    ("encours_immo", "REAL"),
    ("revenu_domicilie", "TEXT"),  # Oui/Non
    ("montant_revenu", "REAL"),
]

def backup_db(db_path: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(os.path.dirname(db_path), f"database_backup_{ts}.db")
    shutil.copy2(db_path, backup_path)
    return backup_path

def get_existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    cur = conn.execute(f"PRAGMA table_info({table});")
    return {row[1] for row in cur.fetchall()}  # row[1] = name

def add_missing_columns(conn: sqlite3.Connection, table: str) -> None:
    existing = get_existing_columns(conn, table)
    for col, col_type in NEW_COLUMNS:
        if col not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type};")
            print(f"[ADD] {table}.{col} ({col_type})")
        else:
            print(f"[SKIP] {table}.{col} existe déjà")

def generate_fake_row():
    # Génération cohérente (simple, mais réaliste)
    nb_tx = random.randint(0, 120)
    vol_tx = round(random.uniform(0, 250000), 2)

    nb_gab = random.randint(0, 40)
    vol_gab = round(nb_gab * random.uniform(100, 1200), 2)

    nb_ecom = random.randint(0, 60)
    vol_ecom = round(nb_ecom * random.uniform(20, 900), 2)

    nb_virm = random.randint(0, 50)
    vol_virm = round(nb_virm * random.uniform(200, 8000), 2)

    solde_moy = round(random.uniform(0, 300000), 2)

    enc_conso = round(random.uniform(0, 200000), 2)
    enc_immo = round(random.uniform(0, 1500000), 2)

    # Encours global et moyen
    enc_global = round(enc_conso + enc_immo + random.uniform(0, 200000), 2)
    enc_moy = round(enc_global * random.uniform(0.4, 0.9), 2)

    # Revenu domicilié
    revenu_dom = "Oui" if random.random() < 0.65 else "Non"
    montant_rev = round(random.uniform(2000, 45000), 2) if revenu_dom == "Oui" else round(random.uniform(0, 12000), 2)

    return {
        "nb_transaction": nb_tx,
        "vol_transaction": vol_tx,
        "nb_retrait_gab": nb_gab,
        "vol_retrait_gab": vol_gab,
        "nb_transaction_ecom": nb_ecom,
        "vol_transaction_ecom": vol_ecom,
        "nb_virement": nb_virm,
        "vol_virement": vol_virm,
        "solde_moyen_depots": solde_moy,
        "encours_moyen": enc_moy,
        "encours_global": enc_global,
        "encours_conso": enc_conso,
        "encours_immo": enc_immo,
        "revenu_domicilie": revenu_dom,
        "montant_revenu": montant_rev,
    }

def fill_fake_data(conn: sqlite3.Connection, table: str) -> None:
    # On récupère la liste des clients (clé primaire probable : radical_compte)
    # Si ta PK n’est pas radical_compte, adapte la requête.
    cur = conn.execute(f"SELECT radical_compte FROM {table};")
    ids = [r[0] for r in cur.fetchall()]
    if not ids:
        print("[WARN] Aucun client trouvé dans la table clients.")
        return

    cols = [c for c, _ in NEW_COLUMNS]
    set_clause = ", ".join([f"{c} = ?" for c in cols])

    sql = f"UPDATE {table} SET {set_clause} WHERE radical_compte = ?;"
    total = 0

    for rc in ids:
        data = generate_fake_row()
        params = [data[c] for c in cols] + [rc]
        conn.execute(sql, params)
        total += 1

    print(f"[OK] Fake data injectées sur {total} clients.")

def main():
    import sys

    db_path = sys.argv[1] if len(sys.argv) > 1 else "database.db"
    db_path = os.path.abspath(db_path)

    if not os.path.isfile(db_path):
        print(f"[ERREUR] Fichier DB introuvable: {db_path}")
        print(r'Usage: python add_kpi_cols_clients.py "C:\...\database.db"')
        raise SystemExit(1)

    backup = backup_db(db_path)
    print(f"[OK] Backup créé: {backup}")

    # Seed pour reproductibilité (optionnel)
    random.seed(42)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("BEGIN;")
        add_missing_columns(conn, "clients")
        fill_fake_data(conn, "clients")
        conn.execute("COMMIT;")
        print("[OK] Commit terminé.")
    except Exception as e:
        conn.execute("ROLLBACK;")
        print("[ERREUR] Rollback effectué.")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()
