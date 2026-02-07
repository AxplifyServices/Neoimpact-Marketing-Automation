# app/api/routers/clients.py
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from app.storage import db
from app.storage.db import insert_client_if_new

router = APIRouter()


class ClientCreateIn(BaseModel):
    """
    Payload dynamique:
      - accepte toutes les colonnes envoyées (extra allowed)
      - ID_Client obligatoire
      - on filtrera ensuite sur le schéma réel de la table clients
    """
    model_config = ConfigDict(extra="allow")

    ID_Client: str  # forcé


@router.post("/clients")
def create_client(payload: ClientCreateIn):
    data: Dict[str, Any] = dict(payload.model_dump())

    # 1) Forcer ID_Client
    id_client = str(data.get("ID_Client") or "").strip()
    if not id_client:
        raise HTTPException(status_code=400, detail="ID_Client est obligatoire.")
    data["ID_Client"] = id_client

    # 2) Exclure radical_compte (même si le dev l'envoie)
    data.pop("radical_compte", None)
    data.pop("Radical_compte", None)
    data.pop("RADICAL_COMPTE", None)

    # 3) Garder UNIQUEMENT les colonnes existantes dans la table clients
    cols = db.get_table_columns("clients")  # [(name, type), ...]
    allowed_cols = set(str(c) for c, _ in cols)

    filtered = {k: v for k, v in data.items() if k in allowed_cols}

    # Sécurité: si la DB n'a pas ID_Client (cas anormal), on bloque
    if "ID_Client" not in allowed_cols:
        raise HTTPException(status_code=500, detail="Schéma DB invalide: colonne ID_Client absente de clients.")

    # 4) Insertion
    ok, msg = insert_client_if_new(filtered)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    return {"ok": True, "message": msg}
