from __future__ import annotations

import sqlite3
from typing import Any, Dict

from app.storage.db import DB_PATH


def _safe_str(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip()


def get_da_context_from_db(id_campagne: str, radical_compte: str) -> Dict[str, Any]:
    """
    Copie fidèle de l'ancienne logique _get_context_from_db (déplacée hors Streamlit).
    Retourne:
      nom, prenom, nom_campagne, variable_cible, valeur_cible, objectif, statut_actuel
    """
    ctx: Dict[str, Any] = {
        "nom": "",
        "prenom": "",
        "nom_campagne": "",
        "variable_cible": "",
        "valeur_cible": "",
        "objectif": "",
        "statut_actuel": "",
    }

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            cl.Nom AS Nom,
            cl.Prenom AS Prenom,
            c.nom_campagne AS nom_campagne,
            m.variable_cible AS variable_cible,
            m.objectif AS objectif,
            cc.statut_actuel AS statut_actuel
        FROM clients_campagnes cc
        LEFT JOIN clients cl ON cl.radical_compte = cc.Radical_compte
        LEFT JOIN campagnes c ON c.id_campagne = cc.ID_CAMPAGNE
        LEFT JOIN modeles m ON m.id_modele = c.id_modele
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
        ctx["variable_cible"] = _safe_str(r["variable_cible"])
        # ⚠️ ton code DA utilise m.objectif mais la colonne peut s'appeler "objectif"
        ctx["objectif"] = _safe_str(r["objectif"])
        ctx["statut_actuel"] = _safe_str(r["statut_actuel"])

    var = ctx["variable_cible"]
    if var:
        cur.execute("PRAGMA table_info(clients)")
        client_cols = {row[1] for row in cur.fetchall()}
        if var in client_cols:
            cur.execute(
                f'SELECT "{var}" AS v FROM clients WHERE radical_compte = ? LIMIT 1',
                (radical_compte,),
            )
            r2 = cur.fetchone()
            if r2:
                ctx["valeur_cible"] = "" if r2["v"] is None else _safe_str(r2["v"])

    conn.close()
    return ctx
