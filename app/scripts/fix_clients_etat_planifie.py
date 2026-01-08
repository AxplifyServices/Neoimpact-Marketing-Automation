import os
import sqlite3

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "clients.db")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("""
UPDATE clients_campagnes
SET Etat_campagne = 'Planifiée'
WHERE ID_CAMPAGNE IN (
    SELECT id_campagne
    FROM campagnes
    WHERE etat_campagne = 'Planifiée'
)
""")

conn.commit()
conn.close()
print("OK: Etat_campagne clients mis à jour pour les campagnes Planifiées")
