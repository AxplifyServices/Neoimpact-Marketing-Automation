from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Optional

from app.domain.canaux import CANAL_MAPPING
from app.domain.workflow_nav import find_bloc_by_id

TABLE = "dm_best_channel_interactions"

CANONICAL_CHANNELS = [
    "Appel",
    "SMS",
    "Mail",
    "Whatsapp",
    "Directeur d'agence",
    "Conseiller client",
    "Push notification",
]


def canonical_channel(value: Any) -> str:
    canal = "" if value is None else str(value).strip()
    if canal in {"Whatsapp information", "Whatsapp questionnaire", "WhatsApp", "Whatsapp"}:
        return "Whatsapp"
    return canal


def age_band(age: Any) -> str:
    try:
        value = int(age)
    except (TypeError, ValueError):
        return "Inconnu"
    if value <= 17:
        return "0-17"
    if value <= 24:
        return "18-24"
    if value <= 34:
        return "25-34"
    if value <= 49:
        return "35-49"
    if value <= 59:
        return "50-59"
    return "60+"


def result_quality(result: Any) -> float:
    value = "" if result is None else str(result).strip().lower()
    high = (
        "aboutit", "joignable avec succès", "réponse oui", "reponse oui",
        "lu", "délivré", "delivre", "transmis",
    )
    low = (
        "non aboutit", "injoignable", "faux numéro", "faux numero",
        "ne marche pas", "non transmis", "non délivré", "non delivre",
        "non lu", "réponse non", "reponse non", "messagerie",
    )
    if any(token in value for token in low):
        return 0.2
    if any(token in value for token in high):
        return 0.9
    if value:
        return 0.55
    return 0.4


def training_weight(result: Any, objective_validated: int) -> float:
    quality = result_quality(result)
    if int(objective_validated or 0) == 1:
        return 0.55 + (1.75 * quality)
    return 0.55 + (1.75 * (1.0 - quality))


def _message_from_block(bloc: Optional[Dict[str, Any]]) -> str:
    if not isinstance(bloc, dict):
        return ""
    for key in ("Contenu", "Message", "Texte", "Objet"):
        raw = bloc.get(key)
        if raw is not None and str(raw).strip():
            return str(raw).strip()[:4000]
    return ""


def record_block_result_by_rid(
    conn,
    rid: int,
    *,
    resultat: str,
    observed_at: Optional[str] = None,
) -> bool:
    """Historise un bloc exécuté avant navigation vers le bloc suivant.

    La ligne reste non finalisée jusqu'à l'évaluation du prochain bloc Objectif.
    Les séquences d'une campagne sont séparées par best_channel_sequence_no.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            cc.ID_CAMPAGNE,
            cc.Radical_compte,
            cc.ID_Action,
            cc.Canal,
            COALESCE(cc.action_execution_seq, 0) AS action_execution_seq,
            COALESCE(cc.best_channel_sequence_no, 1) AS best_channel_sequence_no,
            c.id_modele,
            cl.Age,
            cl.Region,
            m.liste_action,
            cc.Date_last_action
        FROM clients_campagnes cc
        LEFT JOIN campagnes c ON c.id_campagne = cc.ID_CAMPAGNE
        LEFT JOIN clients cl ON cl.radical_compte = cc.Radical_compte
        LEFT JOIN modeles m ON m.id_modele = c.id_modele
        WHERE cc.id = ?
        LIMIT 1
        """,
        (int(rid),),
    )
    row = cur.fetchone()
    if not row:
        return False
    data = dict(row)
    canal = canonical_channel(data.get("Canal"))
    if canal not in CANONICAL_CHANNELS:
        return False

    block_id = str(data.get("ID_Action") or "").strip()
    radical = str(data.get("Radical_compte") or "").strip()
    campaign = str(data.get("ID_CAMPAGNE") or "").strip()
    if not block_id or not radical or not campaign:
        return False

    actions_raw = data.get("liste_action")
    actions = []
    if isinstance(actions_raw, list):
        actions = actions_raw
    elif isinstance(actions_raw, str) and actions_raw.strip():
        try:
            decoded = json.loads(actions_raw)
            if isinstance(decoded, list):
                actions = decoded
        except Exception:
            actions = []
    bloc = find_bloc_by_id(actions, block_id)
    message = _message_from_block(bloc)
    sequence_no = max(1, int(data.get("best_channel_sequence_no") or 1))
    execution_seq = max(0, int(data.get("action_execution_seq") or 0))
    observed = str(observed_at or data.get("Date_last_action") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    cur.execute(
        """
        SELECT COALESCE(MAX(block_order), 0) + 1
        FROM dm_best_channel_interactions
        WHERE id_campagne = ? AND radical_compte = ? AND sequence_no = ?
        """,
        (campaign, radical, sequence_no),
    )
    next_order = int((cur.fetchone() or [1])[0] or 1)
    raw_key = f"{campaign}|{radical}|{sequence_no}|{block_id}|{execution_seq}|{observed}"
    event_key = hashlib.sha256(raw_key.encode("utf-8", errors="replace")).hexdigest()

    cur.execute(
        """
        INSERT INTO dm_best_channel_interactions (
            source, id_campagne, radical_compte, sequence_no,
            block_id, block_order, action_execution_seq, canal,
            message, resultat_bloc, qualite_resultat,
            objectif_valide, tranche_age, region, observed_at,
            event_key, updated_at
        ) VALUES (
            'reel', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            0, ?, ?, ?::timestamptz, ?, NOW()
        )
        ON CONFLICT (event_key) DO UPDATE SET
            resultat_bloc = EXCLUDED.resultat_bloc,
            qualite_resultat = EXCLUDED.qualite_resultat,
            message = EXCLUDED.message,
            updated_at = NOW()
        """,
        (
            campaign, radical, sequence_no, block_id, next_order, execution_seq,
            canal, message, str(resultat or ""), result_quality(resultat),
            age_band(data.get("Age")), str(data.get("Region") or "Inconnue"),
            observed, event_key,
        ),
    )
    return True


def finalize_current_sequence(
    conn,
    rid: int,
    *,
    objective_validated: int,
    objective_id_action: str,
) -> int:
    """Finalise la séquence depuis le précédent objectif (ou le début campagne)."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT ID_CAMPAGNE, Radical_compte,
               COALESCE(best_channel_sequence_no, 1) AS sequence_no
        FROM clients_campagnes
        WHERE id = ?
        LIMIT 1
        """,
        (int(rid),),
    )
    row = cur.fetchone()
    if not row:
        return 0
    campaign, radical, sequence_no = row[0], row[1], int(row[2] or 1)
    target = 1 if int(objective_validated or 0) == 1 else 0
    cur.execute(
        """
        UPDATE dm_best_channel_interactions
        SET objectif_valide = ?,
            objectif_id_action = ?,
            finalized_at = COALESCE(finalized_at, NOW()),
            updated_at = NOW()
        WHERE id_campagne = ?
          AND radical_compte = ?
          AND sequence_no = ?
          AND finalized_at IS NULL
        """,
        (target, str(objective_id_action or ""), campaign, radical, sequence_no),
    )
    updated = int(cur.rowcount or 0)
    if target == 0 and updated > 0:
        cur.execute(
            """
            UPDATE clients_campagnes
            SET best_channel_sequence_no = COALESCE(best_channel_sequence_no, 1) + 1
            WHERE id = ?
            """,
            (int(rid),),
        )
    return updated


def finalize_terminated_sequences(conn) -> int:
    """Une campagne terminée sans objectif validé reste un exemple négatif."""
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE dm_best_channel_interactions i
        SET objectif_valide = 0,
            finalized_at = NOW(),
            updated_at = NOW()
        FROM campagnes c
        WHERE c.id_campagne = i.id_campagne
          AND c.etat_campagne = 'Terminée'
          AND i.finalized_at IS NULL
        """
    )
    return int(cur.rowcount or 0)
