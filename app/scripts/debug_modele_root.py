from __future__ import annotations

import json
import sqlite3

from app.storage.db import DB_PATH


def safe_load(x):
    if x is None:
        return None
    if isinstance(x, (list, dict)):
        return x
    try:
        return json.loads(x)
    except Exception:
        return None


def find_root(liste_action):
    if not isinstance(liste_action, list) or not liste_action:
        return None
    roots = []
    for b in liste_action:
        bm = b.get("Bloc_mère", None)
        if bm is None or str(bm).strip() == "":
            roots.append(b)
    if not roots:
        return None

    def id_num(v):
        try:
            return int(str(v))
        except Exception:
            return 10**9

    roots.sort(key=lambda r: id_num(r.get("ID")))
    return roots[0]


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1) liste des modèles
    cur.execute("SELECT ID_MODELE, Nom_modele, liste_action FROM modeles ORDER BY ID_MODELE DESC LIMIT 10")
    rows = cur.fetchall()

    if not rows:
        print("Aucun modèle trouvé dans la table modeles.")
        return

    print("\n=== 10 derniers modèles (ID, Nom, taille liste_action) ===")
    for mid, nom, la in rows:
        size = len(la) if isinstance(la, str) else 0
        print(f"- {mid} | {nom} | liste_action chars={size}")

    # 2) demande ID
    mid = input("\nEntre l'ID_MODELE à inspecter (ex: M000001): ").strip()
    cur.execute("SELECT ID_MODELE, Nom_modele, variable_cible, Objectif, liste_action FROM modeles WHERE ID_MODELE = ?", (mid,))
    row = cur.fetchone()
    if not row:
        print(f"Modèle introuvable: {mid}")
        return

    mid, nom, var, obj, la = row
    print("\n=== MODELE ===")
    print("ID_MODELE:", mid)
    print("Nom_modele:", nom)
    print("variable_cible:", var)
    print("Objectif:", obj)
    print("liste_action type:", type(la).__name__)
    print("liste_action chars:", len(la) if isinstance(la, str) else 0)

    parsed = safe_load(la)
    if parsed is None:
        print("\n❌ liste_action n'est pas un JSON valide (ou est vide).")
        print("Aperçu brut (300 chars):", (la[:300] if isinstance(la, str) else la))
        return

    if not isinstance(parsed, list):
        print("\n❌ liste_action JSON valide mais PAS une liste.")
        print("Type JSON:", type(parsed).__name__)
        return

    print(f"\n✅ liste_action est une liste, nb blocs={len(parsed)}")
    root = find_root(parsed)
    print("\n=== ROOT BLOC DÉTECTÉ ===")
    if not root:
        print("❌ Aucun bloc racine (Bloc_mère vide) trouvé.")
        return

    print(json.dumps(root, ensure_ascii=False, indent=2))

    # 3) check clés attendues
    missing = [k for k in ["ID", "Bloc_mère", "Canal", "Action"] if k not in root]
    if missing:
        print("\n⚠️ Clés manquantes dans le root:", missing)
    else:
        print("\n✅ Root contient ID/Canal/Action (OK).")

    conn.close()


if __name__ == "__main__":
    main()
