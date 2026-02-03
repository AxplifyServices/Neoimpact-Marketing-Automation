from __future__ import annotations

from typing import Any, Dict, Optional, List

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel

from app.domain.ui_facades.cibles_ui_facade import (
    list_cibles_for_ui,
    get_cible_for_ui,
    get_locked_cibles_for_ui,
    get_distinct_values_for_ui,
    create_cible_db_for_ui,
    create_cible_file_for_ui,
    update_cible_for_ui,
    delete_cible_for_ui,
    preview_cible_for_ui,
    save_uploaded_file_for_ui,
    import_leads_into_clients_for_ui,
    get_cible_filtre_dict_for_ui,
)

router = APIRouter()

# Colonnes indispensables (STRICT) — alignées DB
STRICT_REQUIRED_COLS = ["ID_Client", "Numero_Tel", "Mail"]


# =========================================================
# Helpers: erreurs 400 structurées (schema strict)
# =========================================================
def _parse_strict_schema_error(err: Exception) -> Dict[str, Any]:
    """
    Convertit un ValueError/Exception (message multi-lignes) en JSON exploitable par le front.
    Compatible avec les messages du type:
      - "Fichier invalide (STRICT)..."
      - "Colonnes manquantes (N): ..."
      - "Colonnes en trop (N): ..."
      - "colonne obligatoire manquante..."
      - "contient des valeurs vides..."
    """
    raw = str(err).strip()
    lines = [l.strip() for l in raw.splitlines() if l.strip()]

    missing: List[str] = []
    extra: List[str] = []

    for line in lines:
        low = line.lower()

        # Colonnes manquantes
        if low.startswith("colonnes manquantes"):
            # "Colonnes manquantes (12): a, b, c"
            parts = line.split(":", 1)
            if len(parts) == 2:
                missing = [c.strip() for c in parts[1].split(",") if c.strip()]

        # Colonnes en trop
        if low.startswith("colonnes en trop") or low.startswith("colonnes en trop"):
            parts = line.split(":", 1)
            if len(parts) == 2:
                extra = [c.strip() for c in parts[1].split(",") if c.strip()]

    # Message principal (1ère ligne si possible)
    message = lines[0] if lines else raw

    detail: Dict[str, Any] = {
        "error": "IMPORT_CLIENTS_STRICT_FAILED",
        "message": message,
        "required_columns": STRICT_REQUIRED_COLS,
        "missing_columns": missing,
        "extra_columns": extra,
        "raw": raw,  # utile pour debug (tu peux le retirer si tu veux)
        "hint": "Le fichier doit correspondre EXACTEMENT au schéma de la table clients (noms + colonnes).",
    }
    return detail


def _raise_400_import_clients(e: Exception) -> None:
    """
    400 standardisé pour tous les imports clients.
    """
    detail = _parse_strict_schema_error(e)
    raise HTTPException(status_code=400, detail=detail)


# =========================================================
# Models
# =========================================================
class CibleDbCreateIn(BaseModel):
    nom_cible: str
    filtre: Dict[str, Any]


class CibleUpdateIn(BaseModel):
    id_cible: str
    nom_cible: str
    source: str
    date_creation: str
    filtre: Optional[Dict[str, Any]] = None
    chemin: str = ""


# =========================================================
# Routes
# =========================================================
@router.get("/cibles")
def list_cibles():
    """
    Ajoute locked + lock_reason pour l'UI.
    """
    cibles = list_cibles_for_ui()

    locked_ids, reasons = get_locked_cibles_for_ui()
    locked_ids = set(locked_ids or [])
    reasons = reasons or {}

    for c in cibles:
        if isinstance(c, dict):
            cid = c.get("id_cible") or c.get("id") or c.get("ID")
            is_locked = bool(cid in locked_ids)
            c["locked"] = is_locked
            c["lock_reason"] = (reasons.get(str(cid)) or reasons.get(cid)) if is_locked else None
        else:
            cid = getattr(c, "id_cible", None) or getattr(c, "id", None) or getattr(c, "ID", None)
            is_locked = bool(cid in locked_ids)
            try:
                setattr(c, "locked", is_locked)
                setattr(c, "lock_reason", (reasons.get(str(cid)) or reasons.get(cid)) if is_locked else None)
            except Exception:
                pass

    return cibles


@router.get("/cibles/{id_cible}")
def get_cible(id_cible: str):
    return get_cible_for_ui(id_cible)


@router.get("/cibles/{id_cible}/filtre")
def get_cible_filtre(id_cible: str):
    row = get_cible_for_ui(id_cible)
    if not row:
        return {"filtre": {}}
    return {"filtre": get_cible_filtre_dict_for_ui(row)}


@router.get("/cibles/locked")
def locked_cibles():
    locked_ids, reasons = get_locked_cibles_for_ui()
    return {"locked_ids": sorted(list(locked_ids or [])), "reasons": reasons or {}}


@router.post("/cibles/db")
def create_cible_db(payload: CibleDbCreateIn):
    new_id = create_cible_db_for_ui(payload.nom_cible, payload.filtre)
    return {"ok": True, "id_cible": new_id}


@router.post("/cibles/file")
async def create_cible_file(
    nom_cible: str = Form(...),
    file: UploadFile = File(...),
):
    """
    ✅ Auto-update clients puis création de cible fichier plat.
    - upload fichier
    - import/upsert clients automatiquement (STRICT)
    - création cible fichier plat ensuite
    """
    try:
        path = save_uploaded_file_for_ui(file)
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": "UPLOAD_FAILED", "message": str(e)})

    # 1) auto import/upsert clients
    try:
        inserted, updated = import_leads_into_clients_for_ui(path)
    except Exception as e:
        _raise_400_import_clients(e)

    # 2) create cible file
    try:
        new_id = create_cible_file_for_ui(nom_cible, path)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": "CREATE_CIBLE_FAILED", "message": str(e)})

    return {
        "ok": True,
        "id_cible": new_id,
        "file_path": path,
        "clients_inserted": inserted,
        "clients_updated": updated,
    }


@router.put("/cibles/{id_cible}")
def update_cible(id_cible: str, payload: CibleUpdateIn):
    update_cible_for_ui(
        id_cible=id_cible,
        nom_cible=payload.nom_cible,
        source=payload.source,
        date_creation=payload.date_creation,
        filtre_dict=payload.filtre,
        chemin=payload.chemin,
    )
    return {"ok": True}


@router.delete("/cibles/{id_cible}")
def delete_cible(id_cible: str):
    id_cible = (id_cible or "").strip()

    locked_ids, reasons = get_locked_cibles_for_ui()
    locked_ids = set(str(x).strip() for x in (locked_ids or []))
    reasons = reasons or {}

    if id_cible in locked_ids:
        reason = reasons.get(id_cible) or reasons.get(str(id_cible))
        msg = "Suppression impossible : cette cible est liée à une campagne active/planifiée."
        if reason:
            msg += f" ({reason})"
        raise HTTPException(status_code=409, detail=msg)

    delete_cible_for_ui(id_cible)
    return {"ok": True}


@router.get("/cibles/{id_cible}/preview")
def preview_cible(id_cible: str, limit: int = 200):
    df_head, total = preview_cible_for_ui(id_cible, limit=limit)
    return {"total": total, "rows": df_head.to_dict(orient="records")}


@router.get("/clients/distinct")
def clients_distinct(column: str):
    return {"column": column, "values": get_distinct_values_for_ui(column)}


@router.post("/clients/import-leads")
async def import_leads(file: UploadFile = File(...)):
    """
    Retourne inserted + updated.
    """
    try:
        path = save_uploaded_file_for_ui(file)
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": "UPLOAD_FAILED", "message": str(e)})

    try:
        inserted, updated = import_leads_into_clients_for_ui(path)
    except Exception as e:
        _raise_400_import_clients(e)

    return {"ok": True, "inserted": inserted, "updated": updated, "skipped": 0, "file_path": path}
