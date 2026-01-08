from __future__ import annotations

import os
import json
import sqlite3
from typing import Any, List, Dict


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "clients.db")


def _safe_load_actions(raw: str) -> List[Dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        return []
    except Exception:
        return []


def _safe_dump_actions(actions: List[Dict[str, Any]]) -> str:
    return json.dumps(actions, ensure_ascii=False)


def backfill_objet(verbose: bool = True) -> int:
    """
    Ajoute la clé "Objet": "" dans chaque bloc de liste_action si absente.
    - Si Canal == "Mail" : l'utilisateur pourra la remplir en UI (mais on la backfill à vide)
    - Si Canal != "Mail" : elle reste vide
    Ne modifie rien d'autre.
    Retourne le nombre de modèles modifiés.
    """
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"DB introuvable: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT ID_MODELE, liste_action FROM modeles")
    rows = cur.fetchall()

    updated_count = 0

    for r in rows:
        id_modele = r["ID_MODELE"]
        raw = r["liste_action"] or ""

        actions = _safe_load_actions(raw)
        if not actions:
            continue

        changed = False
        for blk in actions:
            if "Objet" not in blk:
                blk["Objet"] = ""  # vide pour tous, y compris Mail
                changed = True

        if changed:
            cur.execute(
                "UPDATE modeles SET liste_action = ? WHERE ID_MODELE = ?",
                (_safe_dump_actions(actions), id_modele),
            )
            updated_count += 1
            if verbose:
                print(f"[OK] Backfill Objet -> ID_MODELE={id_modele}")

    conn.commit()
    conn.close()

    if verbose:
        print(f"\nTerminé. Modèles modifiés: {updated_count}")

    return updated_count


if __name__ == "__main__":
    backfill_objet(verbose=True)
