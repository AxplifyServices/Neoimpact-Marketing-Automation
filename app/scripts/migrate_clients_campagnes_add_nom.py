import sqlite3
from app.storage.db import DB_PATH

OLD = "clients_campagnes"
NEW = "clients_campagnes__fixed"

CREATE_NEW = f"""
CREATE TABLE {NEW} (
    Nom_campagne            TEXT,
    ID_CAMPAGNE             TEXT NOT NULL,
    Radical_compte          TEXT NOT NULL,

    statut_avant_campagne   TEXT,
    statut_actuel           TEXT,
    Etat_campagne           TEXT,

    NB_jour_campagne        INTEGER DEFAULT 0,

    ID_Action               TEXT,
    Canal                   TEXT,
    Action                  TEXT,

    Last_action             TEXT,
    Resultat_last_action    TEXT,
    Date_last_action        TEXT,

    NB_jour_last_action     INTEGER,

    NB_appel                INTEGER DEFAULT 0,
    NB_mail                 INTEGER DEFAULT 0,
    NB_sms                  INTEGER DEFAULT 0,
    NB_message              INTEGER DEFAULT 0,
    NB_approche_commercial  INTEGER DEFAULT 0,

    PRIMARY KEY (ID_CAMPAGNE, Radical_compte)
);
"""

# Colonnes source possibles (ta table actuelle peut avoir des ordres différents)
SRC_COLS = {
    "Nom_campagne", "ID_CAMPAGNE", "Radical_compte",
    "statut_avant_campagne", "statut_actuel", "Etat_campagne",
    "NB_jour_campagne", "ID_Action", "Canal", "Action",
    "Last_action", "Resultat_last_action", "Date_last_action",
    "NB_jour_last_action", "NB_appel", "NB_mail", "NB_sms",
    "NB_message", "NB_approche_commercial"
}

def _table_cols(cur, table):
    cur.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1) lire colonnes existantes
    existing = set(_table_cols(cur, OLD))
    common = [c for c in SRC_COLS if c in existing]

    if not common:
        raise RuntimeError("Aucune colonne commune trouvée dans clients_campagnes, arrêt.")

    # 2) créer nouvelle table
    cur.execute(f"DROP TABLE IF EXISTS {NEW}")
    cur.execute(CREATE_NEW)

    # 3) copier les données (colonnes communes uniquement)
    cols_csv = ", ".join([f'"{c}"' for c in common])
    cur.execute(f'INSERT INTO {NEW} ({cols_csv}) SELECT {cols_csv} FROM {OLD}')

    # 4) remplacer
    cur.execute(f"DROP TABLE {OLD}")
    cur.execute(f"ALTER TABLE {NEW} RENAME TO {OLD}")

    conn.commit()
    conn.close()
    print("✅ clients_campagnes réparée (PK restaurée + Nom_campagne en premier).")

if __name__ == "__main__":
    main()
