from __future__ import annotations

import sqlite3
from typing import Any, Dict

from app.storage.db import DB_PATH


def _safe_str(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip()


def get_cc_context_from_db(id_campagne: str, radical_compte: str) -> Dict[str, Any]:
    """
    Contexte CC minimal et pérenne (sans legacy: statut_actuel / objectif / variable_cible).

    Retourne uniquement :
      - nom
      - prenom
      - nom_campagne
    """
    ctx: Dict[str, Any] = {
        "nom": "",
        "prenom": "",
        "nom_campagne": "",
    }

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            cl.Nom AS Nom,
            cl.Prenom AS Prenom,
            c.nom_campagne AS nom_campagne
        FROM clients_campagnes cc
        LEFT JOIN clients cl ON cl.radical_compte = cc.Radical_compte
        LEFT JOIN campagnes c ON c.id_campagne = cc.ID_CAMPAGNE
        WHERE cc.ID_CAMPAGNE = ? AND cc.Radical_compte = ?
        LIMIT 1
        """,
        (id_campagne, radical_compte),
    )

    r = cur.fetchone()
    if r:
        ctx["nom"] = _safe_str(r["Nom"])
        ctx["prenom"] = _safe_str(r["Prenom"])
        ctx["nom_campagne"] = _safe_str(r["nom_campagne"])

    conn.close()
    return ctx
