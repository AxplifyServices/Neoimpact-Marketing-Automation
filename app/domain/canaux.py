from __future__ import annotations

from typing import Dict, List


# =========================================================
# Source de vérité : Mapping Canal -> {action, compteur, resultats}
# =========================================================
CANAL_MAPPING: Dict[str, Dict[str, object]] = {
    "Appel": {
        "action": "Appeler",
        "compteur": "NB_appel",
        "resultats": [
            "Joignable avec succès",
            "Joignable sans succès",
            "Injoignable",
            "Messagerie",
            "Faux numéro",
            "Numero qui ne marche pas",
        ],
    },
    "SMS": {
        "action": "SMS",
        "compteur": "NB_sms",
        "resultats": ["Transmis", "Non transmis"],
    },
    "Mail": {
        # ✅ on laisse "Mail" côté mapping, mais l'engine accepte aussi Action="Message"
        "action": "Mail",
        "compteur": "NB_mail",
        "resultats": ["Transmis", "Non transmis"],
    },
    "Whatsapp information": {
        "action": "Message",
        "compteur": "NB_message",
        "resultats": ["Délivré", "Non Délivré", "Lu", "Non Lu", "Numéro non associé Wtsp" ],
    },

        "Whatsapp questionnaire": {
        "action": "Message",
        "compteur": "NB_message",
        "resultats": ["Délivré", "Non Délivré", "Lu", "Non Lu", "Numéro non associé Wtsp", "Réponse Oui", "Réponse Non" ],
    },

    # ✅ IMPORTANT: DA / CC (selon ton mapping final)
    "Directeur d'agence": {
        "action": "Directeur d'agence",
        "compteur": "NB_approche_commercial",
        "resultats": ["Non Aboutit", "Aboutit"],
    },
    "Conseiller client": {
        "action": "Conseiller client",
        "compteur": "NB_approche_commercial",
        "resultats": ["Non Aboutit", "Aboutit"],
    },
}


def list_canaux() -> List[str]:
    return list(CANAL_MAPPING.keys())


def action_for_canal(canal: str) -> str:
    d = CANAL_MAPPING.get(canal) or {}
    a = d.get("action")
    return str(a) if a else ""


def compteur_for_canal(canal: str) -> str:
    d = CANAL_MAPPING.get(canal) or {}
    c = d.get("compteur")
    return str(c) if c else ""


def resultats_for_canal(canal: str) -> List[str]:
    d = CANAL_MAPPING.get(canal) or {}
    r = d.get("resultats") or []
    return list(r) if isinstance(r, list) else []


# =========================================================
# Backward compatibility (si d'autres modules utilisent ces noms)
# =========================================================
def canaux() -> List[str]:
    return list_canaux()
