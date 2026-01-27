from __future__ import annotations

from typing import Any, Dict, Optional

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


@router.get("/cibles")
def list_cibles():
    """
    Retourne la liste des cibles + champs:
    - locked: True/False
    - lock_reason: str | None
    pour permettre à l'UI d'afficher directement l'état verrouillé.
    """
    cibles = list_cibles_for_ui()

    # get_locked_cibles_for_ui() retourne (locked_ids, reasons) dans ton code actuel
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
    path = save_uploaded_file_for_ui(file)
    new_id = create_cible_file_for_ui(nom_cible, path)
    return {"ok": True, "id_cible": new_id, "file_path": path}


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


from fastapi import HTTPException

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
    path = save_uploaded_file_for_ui(file)
    inserted, skipped = import_leads_into_clients_for_ui(path)
    return {"ok": True, "inserted": inserted, "skipped": skipped, "file_path": path}
