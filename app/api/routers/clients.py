# app/api/routers/clients.py
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.storage.db import insert_client_if_new

router = APIRouter()

class ClientCreateIn(BaseModel):
    # → mets ici toutes les colonnes attendues dans "clients"
    # au minimum ID_Client + les champs principaux
    ID_Client: str
    Nom: str | None = None
    Prenom: str | None = None
    # ... etc ...

@router.post("/clients")
def create_client(payload: ClientCreateIn):
    ok, msg = insert_client_if_new(payload.model_dump())
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}
