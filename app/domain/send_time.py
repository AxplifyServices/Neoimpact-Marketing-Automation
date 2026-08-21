from __future__ import annotations

from typing import Any

VALID_CRENEAUX = ("Indifferent", "Matin", "Apres-midi", "Soir")


def normalize_creneau(value: Any) -> str:
    """Normalise le créneau sérialisé dans un bloc de modèle.

    Les libellés DB restent sans accent pour garder un contrat stable, tandis que
    le front peut afficher « Après-midi ». Les anciens modèles sans paramètre
    continuent à fonctionner via ``Indifferent``.
    """
    raw = "" if value is None else str(value).strip()
    if not raw:
        return "Indifferent"

    key = raw.lower().replace("_", "-").replace(" ", "-")
    aliases = {
        "indifferent": "Indifferent",
        "indifférent": "Indifferent",
        "matin": "Matin",
        "apres-midi": "Apres-midi",
        "après-midi": "Apres-midi",
        "apresmidi": "Apres-midi",
        "aprèsmidi": "Apres-midi",
        "soir": "Soir",
    }
    return aliases.get(key, "Indifferent")
