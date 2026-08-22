from __future__ import annotations

import unicodedata
from collections import deque
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List

PRESSURE_LEVELS = ["Faible", "Modere", "Eleve"]

CHANNEL_WEIGHTS: Dict[str, float] = {
    "Push notification": 0.5,
    "Mail": 0.7,
    "SMS": 1.0,
    "Whatsapp": 1.2,
    "Appel": 1.5,
    "Conseiller client": 1.7,
    "Directeur d'agence": 2.0,
}

HUMAN_CHANNELS = {"Appel", "Conseiller client", "Directeur d'agence"}


def _norm(value: Any) -> str:
    raw = "" if value is None else str(value).strip().lower()
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", raw)
        if not unicodedata.combining(ch)
    )


def canonical_channel(value: Any) -> str:
    raw = "" if value is None else str(value).strip()
    normalized = _norm(raw)
    if normalized in {"whatsapp", "whatsapp information", "whatsapp questionnaire"}:
        return "Whatsapp"
    if normalized in {"email", "e-mail", "mail"}:
        return "Mail"
    return raw


def result_exposure_weight(result: Any) -> float:
    """Poids d'exposition réellement ressentie par le client.

    Un échec technique/injoignable compte peu. Une action délivrée compte
    normalement. Une lecture/réponse ou une interaction humaine aboutie ou
    non aboutie compte davantage car la sollicitation a réellement eu lieu.
    """
    value = _norm(result)
    if not value:
        return 1.0

    technical_failure = (
        "non transmis",
        "non delivre",
        "numero non associe",
        "injoignable",
        "messagerie",
        "faux numero",
        "numero qui ne marche pas",
        "ne marche pas",
    )
    if any(token in value for token in technical_failure):
        return 0.20

    interaction = (
        "aboutit",
        "joignable",
        "reponse oui",
        "reponse non",
    )
    if any(token in value for token in interaction):
        return 1.20

    # "non lu" est bien une exposition délivrée, mais pas une lecture.
    if "non lu" in value:
        return 1.00
    if "lu" in value or "ouvert" in value:
        return 1.10
    if "transmis" in value or "delivre" in value:
        return 1.00
    return 1.00


def recency_weight(days_old: int) -> float:
    if days_old <= 7:
        return 1.00
    if days_old <= 14:
        return 0.80
    if days_old <= 21:
        return 0.60
    return 0.40


def repetition_weight(rolling_count: int) -> float:
    if rolling_count <= 1:
        return 1.00
    if rolling_count == 2:
        return 1.10
    if rolling_count == 3:
        return 1.25
    if rolling_count == 4:
        return 1.40
    return 1.60


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def score_client_pressure(interactions: Iterable[Dict[str, Any]], *, run_date: date) -> Dict[str, Any]:
    """Calcule la pression absolue d'un client sur les 30 derniers jours.

    Seuils métier :
      Faible  : score < 4
      Modéré  : 4 <= score < 8
      Élevé   : score >= 8

    Garde-fous :
      - >= 6 actions sur 7 jours => Élevé
      - >= 10 actions sur 30 jours => Élevé
      - >= 4 interactions humaines sur 7 jours => Élevé
      - >= 4 canaux différents sur 7 jours => Élevé
      - >= 4 actions sur 7 jours => au minimum Modéré
    """
    window_start = run_date - timedelta(days=29)
    last7_start = run_date - timedelta(days=6)

    rows: List[Dict[str, Any]] = []
    for raw in interactions:
        observed = _as_datetime(raw.get("observed_at"))
        if observed is None:
            continue
        observed_date = observed.date()
        if observed_date < window_start or observed_date > run_date:
            continue
        canal = canonical_channel(raw.get("canal"))
        if canal not in CHANNEL_WEIGHTS:
            continue
        rows.append({
            "observed_at": observed,
            "canal": canal,
            "resultat_bloc": raw.get("resultat_bloc"),
        })
    rows.sort(key=lambda item: item["observed_at"])

    rolling: deque[datetime] = deque()
    score = 0.0
    channels_7d: set[str] = set()
    channels_30d: set[str] = set()
    actions_7d = 0
    human_7d = 0
    last_contact: datetime | None = None

    for item in rows:
        observed: datetime = item["observed_at"]
        canal = str(item["canal"])
        while rolling and (observed - rolling[0]) > timedelta(days=7):
            rolling.popleft()
        rolling.append(observed)

        days_old = max(0, (run_date - observed.date()).days)
        score += (
            CHANNEL_WEIGHTS[canal]
            * recency_weight(days_old)
            * result_exposure_weight(item.get("resultat_bloc"))
            * repetition_weight(len(rolling))
        )
        channels_30d.add(canal)
        if observed.date() >= last7_start:
            actions_7d += 1
            channels_7d.add(canal)
            if canal in HUMAN_CHANNELS:
                human_7d += 1
        if last_contact is None or observed > last_contact:
            last_contact = observed

    # Le multicanal rapproché augmente la sensation de pression.
    if len(channels_7d) >= 4:
        score *= 1.30
    elif len(channels_7d) >= 3:
        score *= 1.15

    actions_30d = len(rows)
    if actions_7d >= 6:
        level, rule = "Eleve", "actions_7j"
    elif actions_30d >= 10:
        level, rule = "Eleve", "actions_30j"
    elif human_7d >= 4:
        level, rule = "Eleve", "humain_7j"
    elif len(channels_7d) >= 4:
        level, rule = "Eleve", "canaux_7j"
    elif score >= 8.0:
        level, rule = "Eleve", "score"
    elif score >= 4.0:
        level, rule = "Modere", "score"
    elif actions_7d >= 4:
        level, rule = "Modere", "actions_7j_minimum"
    else:
        level, rule = "Faible", "score"

    return {
        "score_pression": round(float(score), 6),
        "niveau_pression": level,
        "regle_niveau": rule,
        "nb_actions_7j": actions_7d,
        "nb_actions_30j": actions_30d,
        "nb_interactions_humaines_7j": human_7d,
        "nb_canaux_7j": len(channels_7d),
        "nb_canaux_30j": len(channels_30d),
        "dernier_contact": last_contact,
        "window_start": window_start,
        "window_end": run_date,
    }
